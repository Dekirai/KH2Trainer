#pragma once
#include <windows.h>
#include <intrin.h>
#include "MotionEntryPlan.h"
#include "MotionObserverSupport.h"

// One resident INT3 route for the exact normal Motion entry. This observes new
// admissions only: it does not drain older calls or establish resource ownership.
// One owner serializes Prepare/Commit/Verify, outside DllMain and engine locks.
// The owner retains the source module before Prepare (including while creating
// its original-call Image). Prepare pins source, wrapper and handler modules.
// Before Commit the typed wrapper must already bind its immutable Observer and
// registered RX original Image. Router, Observer, callbacks/context and original
// code/unwind storage remain alive until process exit after handler publication,
// including failure/rollback. There is deliberately no production teardown.
// The original continuation is in the pinned source module; only byte zero may
// change. Concurrent foreign patches/unmapping violate this ownership contract:
// a one-byte CAS and full-body checks cannot make the whole body transactional.
namespace motion_breakpoint {
constexpr unsigned EntryCount=1;
constexpr size_t BodySize=sizeof(motion_entry_plan::Body3C8CD0);
enum class State : LONG { Empty,Prepared,Resident,Fault };
enum class Error : LONG { None,State,Candidate,Memory,Fingerprint,Debugger,Pin,
    Handler,Protect,Changed,Flush,RestoreProtection };
class Router final {
    uintptr_t module=0,entry=0,target=0,targetModule=0;
    unsigned char expected[BodySize]{};
    volatile LONG state=static_cast<LONG>(State::Empty),error=0,exposed=0,patched=0,rollbackFailed=0;
    PVOID handler=nullptr;
    inline static Router* volatile active=nullptr;
#ifdef KH2_MOTION_BREAKPOINT_TESTS
public:
    // Test process alone owns this private source until all calls/handlers join.
    const unsigned char* testExpectedBody=nullptr;
    bool testRequireImageSource=false,testDebugger=false,testFailHandler=false;
    int testFailPin=-1; // 0=source, 1=wrapper, 2=handler.
    bool testProtectFailure=false,testRestoreFailure=false,testFlushFailure=false;
    bool testRollbackProtectFailure=false,testRollbackRestoreFailure=false,testRollbackFlushFailure=false;
    void (*testBeforeCas)(uintptr_t)=nullptr;
    void (*testAfterCas)(uintptr_t)=nullptr;
private:
#endif
    static LONG Load(const volatile LONG& value) noexcept {
        return InterlockedCompareExchange(const_cast<volatile LONG*>(&value),0,0);
    }
    static bool Span(uintptr_t p,size_t n) noexcept { return p && n && n<=UINTPTR_MAX-p; }
    bool Debugger() const noexcept {
#ifdef KH2_MOTION_BREAKPOINT_TESTS
        if(testDebugger)return true;
#endif
        return IsDebuggerPresent()!=FALSE;
    }
    // Source allocation identity is checked on every covered region. Only the
    // temporarily writable entry page may differ from strict RX during CAS.
    bool SourceCode(bool writing=false) const noexcept {
        if(!Span(entry,BodySize))return false;
        uintptr_t at=entry;
        while(at<entry+BodySize) {
            MEMORY_BASIC_INFORMATION page{};
            if(VirtualQuery(reinterpret_cast<void*>(at),&page,sizeof(page))!=sizeof(page) ||
                page.State!=MEM_COMMIT || reinterpret_cast<uintptr_t>(page.AllocationBase)!=module)return false;
            bool type=page.Type==MEM_IMAGE;
#ifdef KH2_MOTION_BREAKPOINT_TESTS
            if(!testRequireImageSource && page.Type==MEM_PRIVATE)type=true;
#endif
            const uintptr_t begin=reinterpret_cast<uintptr_t>(page.BaseAddress);
            if(!type || !Span(begin,page.RegionSize) || begin>at || begin+page.RegionSize<=at)return false;
            if(page.Protect!=PAGE_EXECUTE_READ &&
                !(writing && begin<=entry && entry<begin+page.RegionSize && page.Protect==PAGE_EXECUTE_READWRITE))return false;
            const uintptr_t end=begin+page.RegionSize;at=end<entry+BodySize?end:entry+BodySize;
        }
        return true;
    }
    static bool ImageCode(uintptr_t address,uintptr_t& base) noexcept {
        MEMORY_BASIC_INFORMATION page{};
        if(!address || VirtualQuery(reinterpret_cast<void*>(address),&page,sizeof(page))!=sizeof(page) ||
            page.State!=MEM_COMMIT || page.Type!=MEM_IMAGE || page.Protect!=PAGE_EXECUTE_READ)return false;
        base=reinterpret_cast<uintptr_t>(page.AllocationBase);return base!=0;
    }
    bool Pin(uintptr_t address,uintptr_t base,unsigned stage) noexcept {
#ifdef KH2_MOTION_BREAKPOINT_TESTS
        if(testFailPin==static_cast<int>(stage))return false;
        MEMORY_BASIC_INFORMATION page{};
        if(stage==0 && !testRequireImageSource && VirtualQuery(reinterpret_cast<void*>(address),&page,sizeof(page))==sizeof(page) &&
            page.Type==MEM_PRIVATE)return reinterpret_cast<uintptr_t>(page.AllocationBase)==base;
#else
        (void)stage;
#endif
        HMODULE held=nullptr;
        return GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,
            reinterpret_cast<LPCWSTR>(address),&held)!=FALSE && reinterpret_cast<uintptr_t>(held)==base;
    }
    bool Match(bool armed,bool writing=false) const noexcept {
        if(!SourceCode(writing))return false;
        __try {
            const auto* code=reinterpret_cast<const unsigned char*>(entry);
            return code[0]==(armed?0xcc:expected[0]) && !memcmp(code+1,expected+1,BodySize-1);
        } __except(EXCEPTION_EXECUTE_HANDLER) {return false;}
    }
    void Fault(Error why) noexcept {
        InterlockedCompareExchange(&error,static_cast<LONG>(why),0);
        InterlockedExchange(&state,static_cast<LONG>(State::Fault));
    }
    // Best effort restoration, never a release. A foreign byte is not replaced.
    // Even successful restoration cannot recall already raised INT3 exceptions.
    void RestoreEntry() noexcept {
        bool protect=true,restore=true,flush=true,byteOkay=true;
#ifdef KH2_MOTION_BREAKPOINT_TESTS
        protect=!testRollbackProtectFailure;
#endif
        DWORD old=0,unused=0;
        if(!protect || !VirtualProtect(reinterpret_cast<void*>(entry),1,PAGE_EXECUTE_READWRITE,&old)) {
            InterlockedExchange(&rollbackFailed,1);return;
        }
        if(Patched()) {
            __try {
                const char prior=_InterlockedCompareExchange8(reinterpret_cast<volatile char*>(entry),
                    static_cast<char>(expected[0]),static_cast<char>(0xcc));
                byteOkay=prior==static_cast<char>(0xcc) || prior==static_cast<char>(expected[0]);
                if(byteOkay)InterlockedExchange(&patched,0);
            } __except(EXCEPTION_EXECUTE_HANDLER) {byteOkay=false;}
        }
#ifdef KH2_MOTION_BREAKPOINT_TESTS
        restore=!testRollbackRestoreFailure;flush=!testRollbackFlushFailure;
#endif
        // Prepare requires RX; restore that known protection even if the first
        // restore failed and this call observed a temporary RWX page.
        restore=restore && VirtualProtect(reinterpret_cast<void*>(entry),1,PAGE_EXECUTE_READ,&unused)!=FALSE;
        flush=flush && FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(entry),1)!=FALSE;
        if(!byteOkay || !restore || !flush)InterlockedExchange(&rollbackFailed,1);
    }
    Error FailedCommit(Error why,bool restore) noexcept {
        Fault(why);if(restore)RestoreEntry();return why;
    }
    static LONG WINAPI Handle(PEXCEPTION_POINTERS info) noexcept {
        Router* const r=static_cast<Router*>(InterlockedCompareExchangePointer(
            reinterpret_cast<PVOID volatile*>(&active),nullptr,nullptr));
        if(!r || !info || !info->ExceptionRecord || !info->ContextRecord)return EXCEPTION_CONTINUE_SEARCH;
        const auto* x=info->ExceptionRecord;auto* c=info->ContextRecord;
        if(x->ExceptionCode!=EXCEPTION_BREAKPOINT || x->ExceptionFlags ||
            (c->ContextFlags&CONTEXT_CONTROL)!=CONTEXT_CONTROL ||
            reinterpret_cast<uintptr_t>(x->ExceptionAddress)!=r->entry || c->Rip!=r->entry)return EXCEPTION_CONTINUE_SEARCH;
        // Windows x64 reports RIP at the INT3 itself. No probes, allocations,
        // callbacks or locks here. Status/Patched intentionally are not gates:
        // publication and delayed exceptions must work during Fault/rollback.
        c->Rip=r->target;return EXCEPTION_CONTINUE_EXECUTION;
    }
public:
    Router()=default;Router(const Router&)=delete;Router& operator=(const Router&)=delete;
    State Status() const noexcept {return static_cast<State>(Load(state));}
    Error LastError() const noexcept {return static_cast<Error>(Load(error));}
    bool Exposed() const noexcept {return Load(exposed)!=0;}
    // Installer's unrecovered write, not a fresh claim about foreign code edits.
    bool Patched() const noexcept {return Load(patched)!=0;}
    bool RollbackFailed() const noexcept {return Load(rollbackFailed)!=0;}
    Error Prepare(uintptr_t moduleBase,motion_observer::OriginalFn wrapper) noexcept {
        if(Status()!=State::Empty)return Error::State;
        if(Debugger()){Fault(Error::Debugger);return Error::Debugger;}
        const auto* def=motion_entry_plan::Get(motion_entry_plan::Kind::NormalBind);
        if(!moduleBase || !wrapper || def->rva>UINTPTR_MAX-moduleBase || !Span(moduleBase+def->rva,BodySize)) {
            Fault(Error::Candidate);return Error::Candidate;
        }
        module=moduleBase;entry=module+def->rva;target=reinterpret_cast<uintptr_t>(wrapper);
        uintptr_t handlerModule=0;
        if((target>=entry && target<entry+BodySize) || !SourceCode() ||
            !ImageCode(target,targetModule) || !ImageCode(reinterpret_cast<uintptr_t>(&Handle),handlerModule)) {
            Fault(Error::Memory);return Error::Memory;
        }
        const unsigned char* body=def->original;
#ifdef KH2_MOTION_BREAKPOINT_TESTS
        if(testExpectedBody)body=testExpectedBody;
#endif
        __try {memcpy(expected,body,BodySize);}
        __except(EXCEPTION_EXECUTE_HANDLER) {Fault(Error::Memory);return Error::Memory;}
        if(expected[0]!=def->original[0] || !Match(false)){Fault(Error::Fingerprint);return Error::Fingerprint;}
        if(!Pin(entry,module,0) || !Pin(target,targetModule,1) || !Pin(reinterpret_cast<uintptr_t>(&Handle),handlerModule,2)) {
            Fault(Error::Pin);return Error::Pin;
        }
        InterlockedExchange(&state,static_cast<LONG>(State::Prepared));return Error::None;
    }
    Error Commit() noexcept {
        if(Status()!=State::Prepared)return Error::State;
        if(Debugger())return FailedCommit(Error::Debugger,false);
        uintptr_t freshTargetModule=0;
        if(!Match(false))return FailedCommit(Error::Fingerprint,false);
        if(!ImageCode(target,freshTargetModule) || freshTargetModule!=targetModule)return FailedCommit(Error::Memory,false);
        if(InterlockedCompareExchangePointer(reinterpret_cast<PVOID volatile*>(&active),this,nullptr)!=nullptr)
            return FailedCommit(Error::State,false);
#ifdef KH2_MOTION_BREAKPOINT_TESTS
        if(!testFailHandler)
#endif
            handler=AddVectoredExceptionHandler(1,&Handle);
        if(!handler) {
            InterlockedCompareExchangePointer(reinterpret_cast<PVOID volatile*>(&active),nullptr,this);
            return FailedCommit(Error::Handler,false);
        }
        // Handler publication seals the owner lifetime even before the CAS.
        // Every subsequent exit keeps this immutable route resident.
        DWORD old=0,unused=0;
#ifdef KH2_MOTION_BREAKPOINT_TESTS
        if(testProtectFailure)return FailedCommit(Error::Protect,false);
#endif
        if(!VirtualProtect(reinterpret_cast<void*>(entry),1,PAGE_EXECUTE_READWRITE,&old))return FailedCommit(Error::Protect,false);
        bool matched=false,changed=false;
        __try {
            matched=Match(false,true);
#ifdef KH2_MOTION_BREAKPOINT_TESTS
            if(testBeforeCas)testBeforeCas(entry);
#endif
            if(matched) {
                // Conservative sticky exposure starts before attempting the
                // atomic write. No owner may infer a teardown lease from false.
                InterlockedExchange(&exposed,1);
                changed=_InterlockedCompareExchange8(reinterpret_cast<volatile char*>(entry),
                    static_cast<char>(0xcc),static_cast<char>(expected[0]))==static_cast<char>(expected[0]);
            }
        } __except(EXCEPTION_EXECUTE_HANDLER) {matched=false;}
        if(changed)InterlockedExchange(&patched,1);
#ifdef KH2_MOTION_BREAKPOINT_TESTS
        if(changed && testAfterCas)testAfterCas(entry);
#endif
        bool restore=true,flush=true;
#ifdef KH2_MOTION_BREAKPOINT_TESTS
        restore=!testRestoreFailure;flush=!testFlushFailure;
#endif
        restore=restore && VirtualProtect(reinterpret_cast<void*>(entry),1,old,&unused)!=FALSE;
        flush=flush && (!changed || FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(entry),1)!=FALSE);
        if(!restore)return FailedCommit(Error::RestoreProtection,true);
        if(!flush)return FailedCommit(Error::Flush,true);
        if(!matched || !changed)return FailedCommit(Error::Changed,true);
        InterlockedExchange(&state,static_cast<LONG>(State::Resident));
        if(!Verify())return FailedCommit(Error::Changed,true);
        return Error::None;
    }
    bool Verify() noexcept {
        if(Status()!=State::Resident)return false;
        if(Debugger()){Fault(Error::Debugger);return false;}
        uintptr_t freshTargetModule=0;
        if(!Patched() || !Match(true) || !ImageCode(target,freshTargetModule) || freshTargetModule!=targetModule) {
            Fault(Error::Changed);return false;
        }
        return true;
    }
#ifdef KH2_MOTION_BREAKPOINT_TESTS
    static LONG TestHandle(PEXCEPTION_POINTERS info) noexcept {return Handle(info);}
    // Isolated test process only. All callers and earlier VEH dispatches must be
    // joined, and no future caller can use the fixture. Never compiled in product.
    bool TestRemoveAfterJoin() noexcept {
        if(handler) {
            testRollbackProtectFailure=testRollbackRestoreFailure=testRollbackFlushFailure=false;
            RestoreEntry();if(Patched())return false;
            MEMORY_BASIC_INFORMATION page{};
            if(VirtualQuery(reinterpret_cast<void*>(entry),&page,sizeof(page))!=sizeof(page) || page.Protect!=PAGE_EXECUTE_READ)return false;
            if(!RemoveVectoredExceptionHandler(handler))return false;handler=nullptr;
        }
        InterlockedCompareExchangePointer(reinterpret_cast<PVOID volatile*>(&active),nullptr,this);return true;
    }
#endif
};
} // namespace motion_breakpoint
