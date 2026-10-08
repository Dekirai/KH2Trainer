#pragma once
#include "StatusBootstrapContract.h"
#include "StatusOriginalTrampolines.h"
#include "StatusBreakpointRouter.h"
#include "StatusThreadDrain.h"

// One process-lifetime coordinator per Identity. No object can be constructed,
// copied or rebound. Native wrappers directly name its static Observer; there is
// no mutable wrapper dispatch pointer. This component does not enable a Journal,
// prove Actor lifetime, or publish an IPC endpoint.
namespace status_observation {
// Retail reset caller: RVA 0x3c0844 loads this address into RCX immediately before
// its call to PoolReset at 0x3c084b. Full evidence: status-rebuild-ownership-20261007.
constexpr uintptr_t RetailPoolRva=0x2a17290;
enum class Phase { Invalid,Empty,Starting,Bootstrap,Observing,Fault };
enum class Error { None,WrongThread,OwnerHandle,ContractPrepare,OriginalsPrepare,
    Bindings,ObserverBind,Candidates,RouterPrepare,ContractOriginal,RouterCommit,
    ContractGated,DrainBegin,Integrity,DrainPoll,ObserverFault };
struct Diagnostic {
    Phase phase=Phase::Invalid;
    Error error=Error::WrongThread;
    unsigned remaining=0;
    bool resumePending=false,observerFaultPending=false;
    // A cached sample taken on the owner thread, never permission to transact.
    uint64_t sampledInFlight=0;
};
#ifdef KH2_STATUS_OBSERVATION_RUNTIME_TESTS
using Contract=status_runtime_test::Contract;
using Originals=status_runtime_test::Originals;
using Router=status_runtime_test::Router;
using Drain=status_runtime_test::Drain;
struct RuntimeTestAccess;
#else
using Contract=status_bootstrap::Contract;
using Originals=status_originals::Batch;
using Router=status_breakpoint::Router;
using Drain=status_thread_drain::Drain;
#endif

template<class Identity> class Runtime final {
    Runtime()=delete;
    inline static status_observer::Observer observer{};
    using Entries=status_observer::Entrypoints<observer>;
    inline static Contract contract{};
    inline static Originals originals{};
    inline static Router router{};
    inline static Drain drain{};
    inline static status_breakpoint::Candidate candidates[5]{};
    inline static status_bootstrap::Range contractRoots[5]{};
    inline static status_thread_drain::Range roots[5]{};
    inline static volatile LONG owner=0;
    inline static HANDLE ownerHandle=nullptr;
    inline static uint64_t instance=0;
    inline static Phase phase=Phase::Empty;
    inline static Error error=Error::None;
    inline static bool bound=false,published=false,drainAttempted=false,faultPending=false;
    inline static unsigned gateIdentity=0;
    inline static Diagnostic diagnostic{};
#ifdef KH2_STATUS_OBSERVATION_RUNTIME_TESTS
    friend struct RuntimeTestAccess;
#endif
    static bool OnOwner() noexcept {
        // Only this atomic word is touched by a foreign caller. A retained
        // handle prevents a recycled thread ID from acquiring the static state.
        return static_cast<DWORD>(InterlockedCompareExchange(&owner,0,0))==GetCurrentThreadId() &&
            ownerHandle && WaitForSingleObject(ownerHandle,0)==WAIT_TIMEOUT;
    }
    static bool ResumePending() noexcept {return drainAttempted && drain.ResumePending();}
    static bool VerifyGates(void* context) noexcept {
        return context==&gateIdentity && OnOwner() && phase!=Phase::Fault &&
            router.Verify() && contract.Verify(status_bootstrap::EntryMode::FiveGates);
    }
    static void Sample() noexcept {
        diagnostic.phase=phase;diagnostic.error=error;
        diagnostic.remaining=drainAttempted?drain.Remaining():0;
        diagnostic.resumePending=ResumePending();diagnostic.observerFaultPending=faultPending;
        // Even Inspect takes the Observer lock. A suspended thread may hold it.
        if(bound && !diagnostic.resumePending)diagnostic.sampledInFlight=observer.Inspect().inFlight;
    }
    static void ServiceFault() noexcept {
        if(ResumePending())return;
        if(faultPending && bound)observer.Fault();
        faultPending=false;
        // Once Bindings has returned, originals stay resident forever, even if
        // Bind/Commit subsequently fails. Failed unpublished cleanup may retry.
        if(!published && originals.Status()!=status_originals::State::Empty &&
            originals.Status()!=status_originals::State::Closed)originals.ReleaseUnpublished();
    }
    static bool Fail(Error reason) noexcept {
        if(phase!=Phase::Fault){phase=Phase::Fault;error=reason;faultPending=bound;}
        ServiceFault();Sample();return false;
    }
    static uintptr_t Target(unsigned index) noexcept {
        switch(index) {
        case 0:return reinterpret_cast<uintptr_t>(&Entries::Initialize);
        case 1:return reinterpret_cast<uintptr_t>(&Entries::Rebuild);
        case 2:return reinterpret_cast<uintptr_t>(&Entries::Coefficient);
        case 3:return reinterpret_cast<uintptr_t>(&Entries::Reset);
        default:return reinterpret_cast<uintptr_t>(&Entries::Release);
        }
    }
    static bool Candidates(uintptr_t module) noexcept {
        static_assert(status_bootstrap::RootCount==5 && status_breakpoint::EntryCount==5 &&
            static_cast<unsigned>(status_entry_plan::Kind::Count)==5,"All five typed roots required");
        if(!contract.RootRanges(contractRoots))return false;
        for(unsigned i=0;i<5;++i) {
            const auto* def=status_entry_plan::Get(static_cast<status_entry_plan::Kind>(i));
            if(!def || def->rva>UINTPTR_MAX-module || def->originalSize>UINTPTR_MAX-module-def->rva ||
                contractRoots[i].begin!=module+def->rva || contractRoots[i].end!=module+def->rva+def->originalSize)return false;
            roots[i]={contractRoots[i].begin,contractRoots[i].end};
            candidates[i]={roots[i].begin,Target(i),def->original,def->originalSize};
        }
        return status_thread_drain::ValidRoots(roots);
    }
public:
    // The host must supply an independently confirmed GameThread ID and a fresh
    // nonzero bridge instance. Start never infers that any calling thread is the
    // game thread. All later coordinator work stays on this retained owner.
    // Call outside DllMain and all engine/Actor/STATUS metadata locks.
    static bool Start(uintptr_t module,uintptr_t pool,uint64_t bridgeInstance,DWORD confirmedGameThread) noexcept {
        if(!module || RetailPoolRva>UINTPTR_MAX-module || pool!=module+RetailPoolRva ||
            (pool&3) || status_observer::PoolSize>UINTPTR_MAX-pool ||
            !bridgeInstance || !confirmedGameThread || confirmedGameThread!=GetCurrentThreadId())return false;
        // Permanent singleton claim BEFORE the first Observer/component access.
        if(InterlockedCompareExchange(&owner,static_cast<LONG>(confirmedGameThread),0)!=0)return false;
        phase=Phase::Starting;instance=bridgeInstance;
        ownerHandle=OpenThread(SYNCHRONIZE|THREAD_QUERY_LIMITED_INFORMATION,FALSE,confirmedGameThread);
        if(!ownerHandle || GetThreadId(ownerHandle)!=confirmedGameThread ||
            GetProcessIdOfThread(ownerHandle)!=GetCurrentProcessId())return Fail(Error::OwnerHandle);
        if(!contract.Prepare(module))return Fail(Error::ContractPrepare);
        if(!Candidates(module))return Fail(Error::Candidates);
        if(!originals.Prepare(module))return Fail(Error::OriginalsPrepare);
        status_observer::Originals functions{};
        if(!originals.Bindings(functions))return Fail(Error::Bindings);
        published=true;
        if(!observer.Bind(functions,pool,instance,confirmedGameThread))return Fail(Error::ObserverBind);
        bound=true;
        if(router.Prepare(candidates)!=status_breakpoint::Error::None)return Fail(Error::RouterPrepare);
        if(!contract.Verify(status_bootstrap::EntryMode::Original))return Fail(Error::ContractOriginal);
        if(router.Commit()!=status_breakpoint::Error::None)return Fail(Error::RouterCommit);
        if(!contract.Verify(status_bootstrap::EntryMode::FiveGates))return Fail(Error::ContractGated);
        phase=Phase::Bootstrap;drainAttempted=true;
        if(!drain.Begin(roots,&VerifyGates,&gateIdentity))return Fail(Error::DrainBegin);
        Sample();return true; // Intentionally no Poll/Arm in the preparation frame.
    }
    static Diagnostic InspectOnOwner() noexcept {
        return OnOwner()?diagnostic:Diagnostic{};
    }
    // A later fresh frame keeps preparation arrays/addresses off the current
    // active stack. A positive stack scan or in-flight wrapper only defers Arm.
    // Even Fault must continue receiving Tick calls to repay any resume debt.
    static Diagnostic Tick(unsigned budget=1) noexcept {
        if(!OnOwner())return {};
        if(phase==Phase::Fault) {
            // Resume maintenance takes precedence over a malformed caller's
            // scan budget; skipping it could leave our suspension in place.
            if(drainAttempted)drain.Poll(budget && budget<=status_thread_drain::MaxThreads?budget:1);
            ServiceFault();Sample();return diagnostic;
        }
        if(!budget || budget>status_thread_drain::MaxThreads)return diagnostic;
        if(phase!=Phase::Bootstrap && phase!=Phase::Observing)return diagnostic;
        const auto polled=drain.Poll(budget);
        if(ResumePending() || polled.phase==status_thread_drain::Phase::Fault) {
            Fail(Error::DrainPoll);return diagnostic;
        }
        if(!VerifyGates(&gateIdentity)){Fail(Error::Integrity);return diagnostic;}
        const auto observed=observer.Inspect();
        if(observed.phase==status_observer::Phase::Fault){Fail(Error::ObserverFault);return diagnostic;}
        if(phase==Phase::Bootstrap && drain.Ready()) {
            if(observer.ArmAfterProvenBarrier(instance))phase=Phase::Observing;
            else if(observer.Inspect().phase==status_observer::Phase::Fault)Fail(Error::ObserverFault);
        }
        // Ready performs a fresh retained-identity/gate check. Its failure after
        // Arm is confidence loss, not a reason to reopen bootstrap or rebind.
        if(phase==Phase::Observing && !drain.Ready())Fail(Error::Integrity);
        else if(drain.Status()==status_thread_drain::Phase::Fault)Fail(Error::Integrity);
        Sample();return diagnostic;
    }
};
struct RetailIdentity;
using RetailRuntime=Runtime<RetailIdentity>;
} // namespace status_observation
