#pragma once
#include "MotionOriginalTrampoline.h"
#include "MotionBreakpointRouter.h"

// One immutable binding per process. This observes entries that reach the
// installed breakpoint; it does not drain calls already inside the native body.
// The owner serializes management on its retained thread. Callbacks can arrive
// on any native caller thread and must synchronize their own metadata. Callback
// context, source continuation and all published objects live until process exit.
namespace motion_observation {
enum class Phase { Invalid,Empty,Starting,Installed,Fault };
enum class Error { None,OwnerHandle,SourcePin,CallbackPin,OriginalPrepare,
    OriginalBind,ObserverBind,RouterPrepare,RouterCommit,Integrity,ObserverFault };
struct Diagnostic {
    Phase phase=Phase::Invalid;
    Error error=Error::None;
    bool exposed=false,patched=false,rollbackFailed=false;
    bool observerFault=false,unpublishedCleanupPending=false;
};
#ifdef KH2_MOTION_RUNTIME_TESTS
struct RuntimeTestAccess;
#endif

template<class Identity> class Runtime final {
    Runtime()=delete;
    inline static motion_observer::Observer observer{};
    using Entry=motion_observer::Entrypoints<observer>;
    inline static motion_original::Image original{};
    inline static motion_breakpoint::Router router{};
    inline static volatile LONG owner=0;
    inline static HANDLE ownerHandle=nullptr;
    inline static Phase phase=Phase::Empty;
    inline static Error error=Error::None;
    inline static bool sealed=false,cleanupPending=false;
#ifdef KH2_MOTION_RUNTIME_TESTS
    friend struct RuntimeTestAccess;
#endif
    static bool OnOwner() noexcept {
        return static_cast<DWORD>(InterlockedCompareExchange(&owner,0,0))==GetCurrentThreadId() &&
            ownerHandle && WaitForSingleObject(ownerHandle,0)==WAIT_TIMEOUT;
    }
    static bool PinAddress(uintptr_t address,uintptr_t expectedBase=0) noexcept {
        HMODULE module=nullptr;
        return address && GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,
            reinterpret_cast<LPCWSTR>(address),&module) &&
            (!expectedBase || reinterpret_cast<uintptr_t>(module)==expectedBase);
    }
    static bool PinSource(uintptr_t module) noexcept {
        const auto* def=motion_entry_plan::Get(motion_entry_plan::Kind::NormalBind);
        if(!module || !def || def->rva>UINTPTR_MAX-module)return false;
#ifdef KH2_MOTION_RUNTIME_TESTS
        MEMORY_BASIC_INFORMATION page{};
        if(VirtualQuery(reinterpret_cast<void*>(module+def->rva),&page,sizeof(page))==sizeof(page) &&
            page.Type==MEM_PRIVATE && reinterpret_cast<uintptr_t>(page.AllocationBase)==module)return true;
#endif
        return PinAddress(module+def->rva,module);
    }
    static void CleanupBeforeSeal() noexcept {
        if(sealed)return;
        const auto state=original.Status();
        if(state==motion_original::State::Empty || state==motion_original::State::Closed){cleanupPending=false;return;}
        cleanupPending=!original.ReleaseUnpublished();
    }
    static bool Fail(Error reason) noexcept {
        if(phase!=Phase::Fault){phase=Phase::Fault;error=reason;}
        CleanupBeforeSeal();return false;
    }
public:
    // The supplied ID identifies the caller's management thread, not proof that
    // engine state is safe to read there. The caller must retain callback context
    // before Start; callbacks may execute as soon as Commit publishes its byte.
    static bool Start(uintptr_t module,DWORD confirmedOwnerThread,
                      motion_observer::BeforeFn before,motion_observer::AfterFn after,void* context) noexcept {
        if(!module || !confirmedOwnerThread || confirmedOwnerThread!=GetCurrentThreadId() || !before || !after)return false;
        if(InterlockedCompareExchange(&owner,static_cast<LONG>(confirmedOwnerThread),0)!=0)return false;
        phase=Phase::Starting;
        ownerHandle=OpenThread(SYNCHRONIZE|THREAD_QUERY_LIMITED_INFORMATION,FALSE,confirmedOwnerThread);
        if(!ownerHandle || GetThreadId(ownerHandle)!=confirmedOwnerThread ||
            GetProcessIdOfThread(ownerHandle)!=GetCurrentProcessId())return Fail(Error::OwnerHandle);
        if(!PinSource(module))return Fail(Error::SourcePin);
        if(!PinAddress(reinterpret_cast<uintptr_t>(before)) || !PinAddress(reinterpret_cast<uintptr_t>(after)))return Fail(Error::CallbackPin);
        if(!original.Prepare(module))return Fail(Error::OriginalPrepare);
        motion_observer::OriginalFn native=nullptr;
        if(!original.Bind(native))return Fail(Error::OriginalBind);
        sealed=true; // Bind publishes a callable pointer and seals OS unwind storage.
        if(!observer.Bind(native,before,after,context))return Fail(Error::ObserverBind);
        if(router.Prepare(module,&Entry::Select)!=motion_breakpoint::Error::None)return Fail(Error::RouterPrepare);
        if(router.Commit()!=motion_breakpoint::Error::None)return Fail(Error::RouterCommit);
        if(observer.Faulted())return Fail(Error::ObserverFault);
        phase=Phase::Installed;
        return true;
    }
    static Diagnostic InspectOnOwner() noexcept {
        if(!OnOwner())return {};
        return {phase,error,router.Exposed(),router.Patched(),router.RollbackFailed(),observer.Faulted(),cleanupPending};
    }
    static Diagnostic Tick() noexcept {
        if(!OnOwner())return {};
        if(phase==Phase::Installed) {
            if(!router.Verify())Fail(Error::Integrity);
            else if(observer.Faulted())Fail(Error::ObserverFault);
        } else if(phase==Phase::Fault)CleanupBeforeSeal();
        return InspectOnOwner();
    }
};
} // namespace motion_observation
