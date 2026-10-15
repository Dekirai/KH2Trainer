#pragma once
#include <windows.h>
#include "MotionEntryPlan.h"
#include "MotionObserverSupport.h"

// One verified normal-bind original-call image. Preparing does not patch or
// route an entry. One owner serializes all methods before publishing a wrapper.
// Source code/continuation must remain loaded and immutable for every call.
// Bind seals code and Windows unwind storage for process lifetime; destruction
// deliberately performs no cleanup. ReleaseUnpublished is the explicit cleanup
// route before any callable pointer escapes, including retry after OS failure.
namespace motion_original {
constexpr size_t PageSize=4096;
enum class State { Empty,Prepared,Bound,Fault,Closed };
enum class Error { None,State,Source,Allocate,Plan,Protect,Flush,Register,Unregister,Free };

inline bool ReadableSpan(uintptr_t address,size_t size) noexcept {
    if(!address || !size || size>UINTPTR_MAX-address)return false;
    const uintptr_t end=address+size;
    while(address<end) {
        MEMORY_BASIC_INFORMATION page{};
        if(VirtualQuery(reinterpret_cast<void*>(address),&page,sizeof(page))!=sizeof(page) ||
           page.State!=MEM_COMMIT || (page.Protect&(PAGE_GUARD|PAGE_NOACCESS)))return false;
        const DWORD access=page.Protect&0xff;
        if(access!=PAGE_READONLY && access!=PAGE_READWRITE && access!=PAGE_WRITECOPY &&
           access!=PAGE_EXECUTE_READ && access!=PAGE_EXECUTE_READWRITE && access!=PAGE_EXECUTE_WRITECOPY)return false;
        const uintptr_t start=reinterpret_cast<uintptr_t>(page.BaseAddress);
        if(page.RegionSize>UINTPTR_MAX-start || start+page.RegionSize<=address)return false;
        address=start+page.RegionSize;
    }
    return true;
}

class Image {
    unsigned char* memory=nullptr;
    bool registered=false;
    State state=State::Empty;
    Error error=Error::None;
#ifdef KH2_MOTION_ORIGINAL_TESTS
public:
    bool testFailAdd=false,testFailDelete=false,testFailFree=false;
    unsigned testAddCalls=0,testDeleteCalls=0,testFreeCalls=0;
private:
#endif
    PRUNTIME_FUNCTION Table() const noexcept {
        return reinterpret_cast<PRUNTIME_FUNCTION>(memory+motion_entry_plan::RuntimeOffset);
    }
    bool Register() noexcept {
#ifdef KH2_MOTION_ORIGINAL_TESTS
        ++testAddCalls;if(testFailAdd)return false;
#endif
        return RtlAddFunctionTable(Table(),1,reinterpret_cast<DWORD64>(memory))!=FALSE;
    }
    bool Delete() noexcept {
#ifdef KH2_MOTION_ORIGINAL_TESTS
        ++testDeleteCalls;if(testFailDelete)return false;
#endif
        return RtlDeleteFunctionTable(Table())!=FALSE;
    }
    bool Free() noexcept {
#ifdef KH2_MOTION_ORIGINAL_TESTS
        ++testFreeCalls;if(testFailFree)return false;
#endif
        return VirtualFree(memory,0,MEM_RELEASE)!=FALSE;
    }
    bool Cleanup() noexcept {
        if(registered) {
            if(!Delete()){error=Error::Unregister;return false;}
            registered=false;
        }
        if(memory && !Free()){error=Error::Free;return false;}
        memory=nullptr;return true;
    }
    bool Fail(Error why) noexcept {state=State::Fault;error=why;Cleanup();return false;}
public:
    Image()=default;Image(const Image&)=delete;Image& operator=(const Image&)=delete;
    State Status() const noexcept {return state;}
    Error LastError() const noexcept {return error;}
    // Inspection only until Bind succeeds; the borrowed address can disappear
    // during cleanup of an unpublished image and conveys no callable lease.
    uintptr_t Entry() const noexcept {return reinterpret_cast<uintptr_t>(memory);}
    bool Prepare(uintptr_t moduleBase) noexcept {
        if(state!=State::Empty){error=Error::State;return false;}
        const auto* def=motion_entry_plan::Get(motion_entry_plan::Kind::NormalBind);
        SYSTEM_INFO info{};GetSystemInfo(&info);
        if(!def || !moduleBase || def->rva>UINTPTR_MAX-moduleBase || info.dwPageSize!=PageSize ||
           !ReadableSpan(moduleBase+def->rva,def->originalSize))return Fail(Error::Source);
        memory=static_cast<unsigned char*>(VirtualAlloc(nullptr,PageSize,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
        if(!memory)return Fail(Error::Allocate);
        motion_entry_plan::Plan plan{};bool okay=false;
        __try {
            okay=motion_entry_plan::BuildBreakpoint(motion_entry_plan::Kind::NormalBind,moduleBase,
                reinterpret_cast<const void*>(moduleBase+def->rva),def->originalSize,Entry(),plan)==motion_entry_plan::Error::None;
        } __except(EXCEPTION_EXECUTE_HANDLER) {okay=false;}
        if(!okay)return Fail(Error::Plan);
        memcpy(memory,plan.image,sizeof(plan.image));
        DWORD old=0;
        if(!VirtualProtect(memory,PageSize,PAGE_EXECUTE_READ,&old))return Fail(Error::Protect);
        if(!FlushInstructionCache(GetCurrentProcess(),memory,PageSize))return Fail(Error::Flush);
        if(!Register())return Fail(Error::Register);
        registered=true;state=State::Prepared;return true;
    }
    bool Bind(motion_observer::OriginalFn& out) noexcept {
        if(state!=State::Prepared && state!=State::Bound)return false;
        state=State::Bound; // Seal before the pointer escapes.
        out=reinterpret_cast<motion_observer::OriginalFn>(memory);return true;
    }
    bool ReleaseUnpublished() noexcept {
        if(state==State::Bound){error=Error::State;return false;}
        if(!Cleanup()){state=State::Fault;return false;}
        state=State::Closed;error=Error::None;return true;
    }
};
} // namespace motion_original
