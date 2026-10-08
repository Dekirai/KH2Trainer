#pragma once
#include <windows.h>
#include <intrin.h>
#include <stdint.h>
#include <string.h>

// A resident, one-byte entry gate. The caller supplies the independently
// verified full bodies, immutable original trampolines and typed wrappers.
// This component does not establish writer quiescence or STATUS ownership.
// Once published, Router and its wrappers must live until process exit.
namespace status_breakpoint {
constexpr unsigned EntryCount=5, MaxBody=2048;
enum class State : LONG { Empty, Prepared, Resident, Fault };
enum class Error : unsigned { None, State, Candidate, Memory, Fingerprint, Debugger,
    Pin, Handler, Protect, Changed, Flush, RestoreProtection };
struct Candidate {
    uintptr_t entry=0,target=0;
    const unsigned char* original=nullptr;
    size_t size=0;
};
class Router {
    struct Entry {
        uintptr_t entry=0,target=0;
        size_t size=0;
        unsigned char original[MaxBody]{};
    } entries[EntryCount]{};
    volatile LONG state=static_cast<LONG>(State::Empty);
    volatile LONG patched=0;
    PVOID handler=nullptr;
    inline static Router* volatile active=nullptr;
#ifdef KH2_STATUS_BREAKPOINT_TESTS
public:
    bool testDebugger=false;
    int testProtectFailure=-1,testRestoreFailure=-1,testFlushFailure=-1;
    unsigned testBeforeCasIndex=EntryCount;
    void (*testBeforeCas)(uintptr_t)=nullptr;
private:
#endif
    void Fail() noexcept { InterlockedExchange(&state,static_cast<LONG>(State::Fault)); }
    static bool Span(uintptr_t p,size_t n) noexcept { return p && n && n<=UINTPTR_MAX-p; }
    static bool Executable(DWORD p) noexcept {
        return !(p&(PAGE_GUARD|PAGE_NOACCESS)) &&
            ((p&255)==PAGE_EXECUTE_READ || (p&255)==PAGE_EXECUTE_READWRITE || (p&255)==PAGE_EXECUTE_WRITECOPY);
    }
    static bool ReadableCode(uintptr_t p,size_t n,bool entry) noexcept {
        if(!Span(p,n))return false;
        uintptr_t at=p;
        while(at<p+n) {
            MEMORY_BASIC_INFORMATION m{};
            if(VirtualQuery(reinterpret_cast<const void*>(at),&m,sizeof(m))!=sizeof(m) ||
               m.State!=MEM_COMMIT || !Executable(m.Protect))return false;
            bool type=m.Type==MEM_IMAGE;
#ifdef KH2_STATUS_BREAKPOINT_TESTS
            if(entry && m.Type==MEM_PRIVATE)type=true;
#else
            (void)entry;
#endif
            if(!type)return false;
            const uintptr_t start=reinterpret_cast<uintptr_t>(m.BaseAddress);
            if(!Span(start,m.RegionSize) || start>at || start+m.RegionSize<=at)return false;
            const uintptr_t end=start+m.RegionSize;
            at=end<p+n?end:p+n;
        }
        return true;
    }
    bool Debugger() const noexcept {
#ifdef KH2_STATUS_BREAKPOINT_TESTS
        if(testDebugger)return true;
#endif
        return IsDebuggerPresent()!=FALSE;
    }
    bool Match(const Entry& e,bool armed) const noexcept {
        if(!ReadableCode(e.entry,e.size,true))return false;
        __try {
            const auto* code=reinterpret_cast<const unsigned char*>(e.entry);
            return code[0]==(armed?0xcc:e.original[0]) &&
                !memcmp(code+1,e.original+1,e.size-1);
        } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
    }
    static LONG WINAPI Handle(PEXCEPTION_POINTERS info) noexcept {
        Router* const r=static_cast<Router*>(InterlockedCompareExchangePointer(
            reinterpret_cast<PVOID volatile*>(&active),nullptr,nullptr));
        if(!r || !info || !info->ExceptionRecord || !info->ContextRecord)return EXCEPTION_CONTINUE_SEARCH;
        const auto* x=info->ExceptionRecord;
        auto* c=info->ContextRecord;
        if(x->ExceptionCode!=EXCEPTION_BREAKPOINT || x->ExceptionFlags ||
           (c->ContextFlags&CONTEXT_CONTROL)!=CONTEXT_CONTROL)return EXCEPTION_CONTINUE_SEARCH;
        const uintptr_t address=reinterpret_cast<uintptr_t>(x->ExceptionAddress);
        for(const auto& e:r->entries) {
            // Real x64 Windows INT3 reports RIP at the breakpoint instruction.
            // No allocation, locking, native call or memory probe in the VEH.
            if(address==e.entry && c->Rip==e.entry) {
                c->Rip=e.target;
                return EXCEPTION_CONTINUE_EXECUTION;
            }
        }
        return EXCEPTION_CONTINUE_SEARCH;
    }
public:
    Router()=default;
    Router(const Router&)=delete;
    Router& operator=(const Router&)=delete;
    State Status() const noexcept {
        return static_cast<State>(InterlockedCompareExchange(const_cast<volatile LONG*>(&state),0,0));
    }
    unsigned PatchedMask() const noexcept {
        return static_cast<unsigned>(InterlockedCompareExchange(const_cast<volatile LONG*>(&patched),0,0));
    }
    // Call once before publication. Full original bodies must be the exact
    // independently pinned STATUS definitions. Original trampolines must already
    // be RX, cache-flushed and registered for unwind before these targets run.
    Error Prepare(const Candidate (&candidate)[EntryCount]) noexcept {
        if(Status()!=State::Empty)return Error::State;
        if(Debugger()){Fail();return Error::Debugger;}
        for(unsigned i=0;i<EntryCount;++i) {
            const auto& c=candidate[i];
            if(!Span(c.entry,c.size) || !c.original || c.size<2 || c.size>MaxBody ||
               !Span(reinterpret_cast<uintptr_t>(c.original),c.size) || !c.target) { Fail();return Error::Candidate; }
            for(unsigned j=0;j<EntryCount;++j) {
                if(i!=j && Span(candidate[j].entry,candidate[j].size) &&
                   c.entry<candidate[j].entry+candidate[j].size && candidate[j].entry<c.entry+c.size) {
                    Fail();return Error::Candidate;
                }
                if(Span(candidate[j].entry,candidate[j].size) &&
                   c.target>=candidate[j].entry && c.target<candidate[j].entry+candidate[j].size) {
                    Fail();return Error::Candidate;
                }
            }
            if(!ReadableCode(c.entry,c.size,true) || !ReadableCode(c.target,1,false)) {Fail();return Error::Memory;}
            __try {
                if(c.original[0]==0xcc || memcmp(reinterpret_cast<const void*>(c.entry),c.original,c.size)) {
                    Fail();return Error::Fingerprint;
                }
                auto& e=entries[i];e.entry=c.entry;e.target=c.target;e.size=c.size;
                memcpy(e.original,c.original,c.size);
            } __except(EXCEPTION_EXECUTE_HANDLER) { Fail();return Error::Memory; }
        }
        InterlockedExchange(&state,static_cast<LONG>(State::Prepared));return Error::None;
    }
    // Typed wrapper bindings must be fully published before Commit. Resident
    // means all entry bytes were installed, NOT that old writers have drained.
    Error Commit() noexcept {
        if(Status()!=State::Prepared)return Error::State;
        if(Debugger()){Fail();return Error::Debugger;}
        HMODULE module=nullptr;
        if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,
            reinterpret_cast<LPCWSTR>(&Handle),&module)) {Fail();return Error::Pin;}
        for(const auto& e:entries) {
            if(!Match(e,false)) {Fail();return Error::Fingerprint;}
            if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,
                reinterpret_cast<LPCWSTR>(e.target),&module)) {Fail();return Error::Pin;}
        }
        if(InterlockedCompareExchangePointer(reinterpret_cast<PVOID volatile*>(&active),this,nullptr)!=nullptr) {
            Fail();return Error::State;
        }
        handler=AddVectoredExceptionHandler(1,&Handle);
        if(!handler) {
            InterlockedCompareExchangePointer(reinterpret_cast<PVOID volatile*>(&active),nullptr,this);
            Fail();return Error::Handler;
        }
        for(unsigned i=0;i<EntryCount;++i) {
            auto& e=entries[i];DWORD old=0,unused=0;
#ifdef KH2_STATUS_BREAKPOINT_TESTS
            if(testProtectFailure==static_cast<int>(i)){Fail();return Error::Protect;}
#endif
            if(!VirtualProtect(reinterpret_cast<void*>(e.entry),1,PAGE_EXECUTE_READWRITE,&old)) {
                Fail();return Error::Protect;
            }
            bool matched=false,changed=false;
            __try {
                matched=Match(e,false);
#ifdef KH2_STATUS_BREAKPOINT_TESTS
                if(i==testBeforeCasIndex && testBeforeCas)testBeforeCas(e.entry);
#endif
                if(matched)changed=_InterlockedCompareExchange8(reinterpret_cast<volatile char*>(e.entry),
                    static_cast<char>(0xcc),static_cast<char>(e.original[0]))==static_cast<char>(e.original[0]);
            } __except(EXCEPTION_EXECUTE_HANDLER) { matched=false; }
            if(changed)InterlockedOr(&patched,1L<<i);
            const bool restored=VirtualProtect(reinterpret_cast<void*>(e.entry),1,old,&unused)!=FALSE;
            const bool flushed=!changed || FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(e.entry),1)!=FALSE;
#ifdef KH2_STATUS_BREAKPOINT_TESTS
            const bool restoreOkay=restored && testRestoreFailure!=static_cast<int>(i);
            const bool flushOkay=flushed && testFlushFailure!=static_cast<int>(i);
#else
            const bool restoreOkay=restored,flushOkay=flushed;
#endif
            if(!restoreOkay){Fail();return Error::RestoreProtection;}
            if(!flushOkay){Fail();return Error::Flush;}
            if(!matched || !changed){Fail();return Error::Changed;}
        }
        InterlockedExchange(&state,static_cast<LONG>(State::Resident));
        return Verify()?Error::None:Error::Changed;
    }
    bool Verify() noexcept {
        if(Status()!=State::Resident)return false;
        if(Debugger()){Fail();return false;}
        if(PatchedMask()!=((1u<<EntryCount)-1)){Fail();return false;}
        for(const auto& e:entries)if(!Match(e,true)){Fail();return false;}
        return true;
    }
#ifdef KH2_STATUS_BREAKPOINT_TESTS
    static LONG TestHandle(PEXCEPTION_POINTERS p) noexcept { return Handle(p); }
    // Isolated test process only: caller has joined every test worker and proves
    // no trapped call/VEH is in flight. Production intentionally has no teardown.
    bool TestRemoveAfterJoin() noexcept {
        bool okay=true;
        for(unsigned i=0;i<EntryCount;++i)if(PatchedMask()&(1u<<i)) {
            DWORD old=0,unused=0;
            if(!VirtualProtect(reinterpret_cast<void*>(entries[i].entry),1,PAGE_EXECUTE_READWRITE,&old)){okay=false;continue;}
            _InterlockedCompareExchange8(reinterpret_cast<volatile char*>(entries[i].entry),
                static_cast<char>(entries[i].original[0]),static_cast<char>(0xcc));
            if(!VirtualProtect(reinterpret_cast<void*>(entries[i].entry),1,old,&unused))okay=false;
            if(!FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(entries[i].entry),1))okay=false;
        }
        if(!okay)return false;
        if(handler && !RemoveVectoredExceptionHandler(handler))return false;
        handler=nullptr;
        InterlockedCompareExchangePointer(reinterpret_cast<PVOID volatile*>(&active),nullptr,this);
        return true;
    }
#endif
};
} // namespace status_breakpoint
