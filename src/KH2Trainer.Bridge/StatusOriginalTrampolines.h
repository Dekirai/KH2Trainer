#pragma once
#include <windows.h>
#include "StatusEntryPlan.h"
#include "StatusObserverSupport.h"

// Allocate and register the five exact original-call trampolines before a gate
// can publish their wrappers. This does not patch the game or establish a drain.
// Once Bindings publishes pointers, storage/unwind records have process lifetime.
// One installer owner must serialize every Batch method; concurrent Bindings
// versus ReleaseUnpublished is not supported. Native entrants call the resulting
// trampolines directly and do not access Batch metadata. The source module and
// original continuations must remain loaded and intact for every possible call.
// No destructor tears down registered storage, including after the Batch object's
// own lifetime ends. The owner should explicitly release unpublished batches.
namespace status_originals {
constexpr unsigned Count=static_cast<unsigned>(status_entry_plan::Kind::Count);
constexpr size_t PageSize=4096;
enum class State { Empty,Prepared,Bound,Fault,Closed };
enum class Error { None,State,Source,Allocate,Plan,Protect,Flush,Register,Unregister,Free };
class Batch {
    unsigned char* memory=nullptr;
    bool registered[Count]{};
    State state=State::Empty;
    Error error=Error::None;
#ifdef KH2_STATUS_ORIGINALS_TESTS
public:
    int testFailAddAt=-1,testFailDeleteAt=-1,testFailFreeAt=-1;
    int testAddCalls=0,testDeleteCalls=0,testFreeCalls=0;
    uintptr_t testLastAllocation=0;
private:
#endif
    bool Register(PRUNTIME_FUNCTION table,DWORD64 base) noexcept {
#ifdef KH2_STATUS_ORIGINALS_TESTS
        if(testAddCalls++==testFailAddAt)return false;
#endif
        return RtlAddFunctionTable(table,1,base)!=FALSE;
    }
    bool Delete(PRUNTIME_FUNCTION table) noexcept {
#ifdef KH2_STATUS_ORIGINALS_TESTS
        if(testDeleteCalls++==testFailDeleteAt)return false;
#endif
        return RtlDeleteFunctionTable(table)!=FALSE;
    }
    bool Free() noexcept {
#ifdef KH2_STATUS_ORIGINALS_TESTS
        if(testFreeCalls++==testFailFreeAt)return false;
#endif
        return VirtualFree(memory,0,MEM_RELEASE)!=FALSE;
    }
    bool Unregister() noexcept {
        bool okay=true;
        for(unsigned i=0;i<Count;++i)if(registered[i]) {
            auto* table=reinterpret_cast<PRUNTIME_FUNCTION>(memory+PageSize*i+status_entry_plan::RuntimeOffset);
            if(Delete(table))registered[i]=false;
            else okay=false;
        }
        // A failed deletion retains both table and executable storage. Freeing
        // a still-registered table would leave a dangling OS unwind pointer.
        if(!okay){error=Error::Unregister;return false;}
        // Even after the OS tables are gone a failed free must retain the exact
        // allocation address so an unpublished owner can retry its cleanup.
        if(memory && !Free()){error=Error::Free;return false;}
        memory=nullptr;return true;
    }
    bool Fail(Error why) noexcept {state=State::Fault;error=why;Unregister();return false;}
public:
    Batch()=default;Batch(const Batch&)=delete;Batch& operator=(const Batch&)=delete;
    State Status() const noexcept {return state;}
    Error LastError() const noexcept {return error;}
    // Borrowed inspection/planning address only. Entry does not publish a
    // callable pointer or seal lifetime; callers may call originals only after
    // successful Bindings. A failed/unpublished batch may still retain storage.
    uintptr_t Entry(status_entry_plan::Kind kind) const noexcept {
        const unsigned index=static_cast<unsigned>(kind);
        return memory && index<Count?reinterpret_cast<uintptr_t>(memory+PageSize*index):0;
    }
    bool Prepare(uintptr_t moduleBase) noexcept {
        if(state!=State::Empty){error=Error::State;return false;}
        SYSTEM_INFO info{};GetSystemInfo(&info);
        if(!moduleBase || info.dwPageSize!=PageSize)return Fail(Error::Source);
        for(unsigned i=0;i<Count;++i) {
            const auto* def=status_entry_plan::Get(static_cast<status_entry_plan::Kind>(i));
            if(!def || def->rva>UINTPTR_MAX-moduleBase ||
               !status_observer::ReadableSpan(moduleBase+def->rva,def->originalSize))return Fail(Error::Source);
        }
        memory=static_cast<unsigned char*>(VirtualAlloc(nullptr,PageSize*Count,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
        if(!memory)return Fail(Error::Allocate);
#ifdef KH2_STATUS_ORIGINALS_TESTS
        testLastAllocation=reinterpret_cast<uintptr_t>(memory);
#endif
        for(unsigned i=0;i<Count;++i) {
            const auto kind=static_cast<status_entry_plan::Kind>(i);const auto& def=*status_entry_plan::Get(kind);
            status_entry_plan::Plan plan{};bool planned=false;
            __try {
                planned=status_entry_plan::BuildBreakpoint(kind,moduleBase,
                    reinterpret_cast<const unsigned char*>(moduleBase+def.rva),def.originalSize,Entry(kind),plan)==status_entry_plan::Error::None;
            } __except(EXCEPTION_EXECUTE_HANDLER) {planned=false;}
            if(!planned)return Fail(Error::Plan);
            memcpy(memory+PageSize*i,plan.image,sizeof(plan.image));
        }
        DWORD old=0;
        if(!VirtualProtect(memory,PageSize*Count,PAGE_EXECUTE_READ,&old))return Fail(Error::Protect);
        if(!FlushInstructionCache(GetCurrentProcess(),memory,PageSize*Count))return Fail(Error::Flush);
        for(unsigned i=0;i<Count;++i) {
            auto* table=reinterpret_cast<PRUNTIME_FUNCTION>(memory+PageSize*i+status_entry_plan::RuntimeOffset);
            if(!Register(table,reinterpret_cast<DWORD64>(memory+PageSize*i)))return Fail(Error::Register);
            registered[i]=true;
        }
        state=State::Prepared;return true;
    }
    bool Bindings(status_observer::Originals& out) noexcept {
        if(state!=State::Prepared && state!=State::Bound)return false;
        using status_entry_plan::Kind;
        // Seal BEFORE pointers can escape to a concurrent native entrant.
        state=State::Bound;
        out={reinterpret_cast<status_observer::InitOriginal>(Entry(Kind::Init)),
            reinterpret_cast<status_observer::RebuildOriginal>(Entry(Kind::Rebuild)),
            reinterpret_cast<status_observer::CoefficientOriginal>(Entry(Kind::Coefficient)),
            reinterpret_cast<status_observer::ResetOriginal>(Entry(Kind::PoolReset)),
            reinterpret_cast<status_observer::ReleaseOriginal>(Entry(Kind::Release))};
        return true;
    }
    bool ReleaseUnpublished() noexcept {
        if(state==State::Bound){error=Error::State;return false;}
        if(!Unregister()){state=State::Fault;return false;}
        state=State::Closed;error=Error::None;return true;
    }
};
} // namespace status_originals
