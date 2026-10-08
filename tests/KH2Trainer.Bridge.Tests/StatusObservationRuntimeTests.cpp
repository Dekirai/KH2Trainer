#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdio.h>
#include "../../src/KH2Trainer.Bridge/StatusBootstrapContract.h"
#include "../../src/KH2Trainer.Bridge/StatusOriginalTrampolines.h"
#include "../../src/KH2Trainer.Bridge/StatusBreakpointRouter.h"
#include "../../src/KH2Trainer.Bridge/StatusThreadDrain.h"

// These four test doubles exercise coordinator ordering/failure decisions. The
// Observer, typed Entrypoints and retained owner HANDLE are real. No game image,
// native patch, trampoline, remote stack capture or real suspension is used.
namespace status_runtime_test {
enum Call { PrepareContract,Roots,PrepareOriginals,Bindings,PrepareRouter,Original,
    CommitRouter,Gated,BeginDrain,PollDrain,ReadyDrain,ReleaseOriginals };
Call calls[1024]{};unsigned callCount=0,nativeCalls[5]{};
void Record(Call value){if(callCount<1024)calls[callCount++]=value;}
void (*duringOriginal)()=nullptr;
uint64_t __fastcall Init(uintptr_t value){++nativeCalls[0];if(duringOriginal)duringOriginal();return value+11;}
uint64_t __fastcall Rebuild(uintptr_t value,const unsigned char*){++nativeCalls[1];return value+22;}
uint64_t __fastcall Coefficient(uintptr_t value,int a,int b){++nativeCalls[2];return value+static_cast<uint64_t>(a+b);}
void __fastcall Reset(uintptr_t){++nativeCalls[3];}
uint64_t __fastcall Release(uintptr_t value){++nativeCalls[4];return value+55;}
struct Contract {
    bool prepare=true,original=true,gated=true,ranges=true;uintptr_t module=0;
    bool Prepare(uintptr_t value) noexcept {Record(PrepareContract);module=value;return prepare;}
    bool Verify(status_bootstrap::EntryMode mode) noexcept {
        Record(mode==status_bootstrap::EntryMode::Original?Original:Gated);
        return mode==status_bootstrap::EntryMode::Original?original:gated;
    }
    bool RootRanges(status_bootstrap::Range (&out)[5]) noexcept {
        Record(Roots);
        for(unsigned i=0;i<5;++i){const auto* d=status_entry_plan::Get(static_cast<status_entry_plan::Kind>(i));out[i]={module+d->rva,module+d->rva+d->originalSize};}
        if(!ranges)++out[2].end;
        return true;
    }
};
struct Originals {
    bool prepare=true,bindings=true,badBinding=false;unsigned cleanupFailures=0,cleanupCalls=0;
    status_originals::State state=status_originals::State::Empty;
    bool Prepare(uintptr_t) noexcept {Record(PrepareOriginals);state=prepare?status_originals::State::Prepared:status_originals::State::Fault;return prepare;}
    bool Bindings(status_observer::Originals& out) noexcept {
        Record(status_runtime_test::Bindings);if(!bindings)return false;
        state=status_originals::State::Bound;
        out={badBinding?nullptr:&Init,&Rebuild,&Coefficient,&Reset,&Release};return true;
    }
    status_originals::State Status() const noexcept {return state;}
    bool ReleaseUnpublished() noexcept {
        Record(ReleaseOriginals);++cleanupCalls;
        if(cleanupFailures){--cleanupFailures;return false;}
        state=status_originals::State::Closed;return true;
    }
};
struct Router {
    bool prepare=true,commit=true,verify=true,callDuringCommit=false;
    unsigned preparedCount=0,commits=0;const status_breakpoint::Candidate* borrowed=nullptr;
    status_breakpoint::Error Prepare(const status_breakpoint::Candidate (&c)[5]) noexcept {
        Record(PrepareRouter);borrowed=c;preparedCount=5;
        return prepare?status_breakpoint::Error::None:status_breakpoint::Error::Candidate;
    }
    status_breakpoint::Error Commit() noexcept {
        Record(CommitRouter);++commits;
        if(callDuringCommit)reinterpret_cast<status_observer::InitOriginal>(borrowed[0].target)(7);
        return commit?status_breakpoint::Error::None:status_breakpoint::Error::Changed;
    }
    bool Verify() noexcept {return verify;}
};
struct Drain {
    bool begin=true,ready=false,pending=false,failPoll=false;
    unsigned polls=0,readies=0,retryFailures=0,remaining=3;
    const status_thread_drain::Range* borrowed=nullptr;
    status_thread_drain::GateCheck check=nullptr;void* context=nullptr;
    status_thread_drain::Phase phase=status_thread_drain::Phase::Empty;
    bool Begin(const status_thread_drain::Range (&r)[5],status_thread_drain::GateCheck fn,void* c) noexcept {
        Record(BeginDrain);borrowed=r;check=fn;context=c;
        const bool good=begin && check(context);phase=good?status_thread_drain::Phase::Scanning:status_thread_drain::Phase::Fault;return good;
    }
    status_thread_drain::PollResult Poll(unsigned) noexcept {
        Record(PollDrain);++polls;
        if(pending){if(retryFailures)--retryFailures;else pending=false;phase=status_thread_drain::Phase::Fault;}
        if(phase!=status_thread_drain::Phase::Fault) {
            if(failPoll || !check(context))phase=status_thread_drain::Phase::Fault;
            else if(ready){phase=status_thread_drain::Phase::Drained;remaining=0;}
        }
        return {phase,remaining};
    }
    bool Ready() noexcept {
        Record(ReadyDrain);++readies;
        if(phase!=status_thread_drain::Phase::Drained || pending)return false;
        if(!check(context)){phase=status_thread_drain::Phase::Fault;return false;}
        return true;
    }
    bool ResumePending() const noexcept {return pending;}
    status_thread_drain::Phase Status() const noexcept {return phase;}
    unsigned Remaining() const noexcept {return remaining;}
};
} // namespace status_runtime_test

#define KH2_STATUS_OBSERVATION_RUNTIME_TESTS
#include "../../src/KH2Trainer.Bridge/StatusObservationRuntime.h"
namespace status_observation {
struct RuntimeTestAccess {
    template<class T> static auto& ContractOf(){return T::contract;}
    template<class T> static auto& OriginalsOf(){return T::originals;}
    template<class T> static auto& RouterOf(){return T::router;}
    template<class T> static auto& DrainOf(){return T::drain;}
    template<class T> static auto ObserverState(){return T::observer.Inspect();}
    template<class T> static bool CorrectCandidates(uintptr_t module) {
        const uintptr_t expected[]={reinterpret_cast<uintptr_t>(&T::Entries::Initialize),
            reinterpret_cast<uintptr_t>(&T::Entries::Rebuild),reinterpret_cast<uintptr_t>(&T::Entries::Coefficient),
            reinterpret_cast<uintptr_t>(&T::Entries::Reset),reinterpret_cast<uintptr_t>(&T::Entries::Release)};
        for(unsigned i=0;i<5;++i) {
            const auto* d=status_entry_plan::Get(static_cast<status_entry_plan::Kind>(i));
            const auto& c=T::candidates[i];const auto& r=T::roots[i];
            if(c.entry!=module+d->rva || c.target!=expected[i] || c.original!=d->original || c.size!=d->originalSize ||
                r.begin!=c.entry || r.end!=c.entry+c.size)return false;
        }
        return T::router.borrowed==T::candidates && T::drain.borrowed==T::roots;
    }
    template<class T> static uint64_t InvokeInit(){return T::Entries::Initialize(7);}
    template<class T> static bool ForwardAll() {
        return reinterpret_cast<status_observer::InitOriginal>(T::candidates[0].target)(7)==18 &&
            reinterpret_cast<status_observer::RebuildOriginal>(T::candidates[1].target)(7,nullptr)==29 &&
            reinterpret_cast<status_observer::CoefficientOriginal>(T::candidates[2].target)(7,3,4)==14 &&
            (reinterpret_cast<status_observer::ResetOriginal>(T::candidates[3].target)(7),true) &&
            reinterpret_cast<status_observer::ReleaseOriginal>(T::candidates[4].target)(7)==62;
    }
    template<class T> static void SimulateEndedOwner() {
        // Replace only the coordinator's test HANDLE with a signaled object;
        // this checks the retained-identity gate, not OS thread-ID recycling.
        CloseHandle(T::ownerHandle);T::ownerHandle=CreateEventW(nullptr,TRUE,TRUE,nullptr);
    }
};
}
namespace {
using namespace status_observation;
using Access=RuntimeTestAccess;
template<unsigned N> struct Tag;
template<unsigned N> using Case=Runtime<Tag<N>>;
unsigned checks=0,failures=0;
constexpr uintptr_t Module=0x140000000,Pool=Module+0x2a17290;
void Check(bool value,const char* label){++checks;if(!value){++failures;printf("FAIL %s\n",label);}}
template<class T> bool Start(){return T::Start(Module,Pool,123,GetCurrentThreadId());}
void SuccessAndDeferral() {
    using T=Case<1>;
    status_runtime_test::callCount=0;Access::RouterOf<T>().callDuringCommit=true;
    Check(Start<T>(),"start concrete coordinator flow with test dependencies");
    const auto state=T::InspectOnOwner();
    Check(state.phase==Phase::Bootstrap && !state.resumePending,"start only establishes bootstrap");
    Check(Access::DrainOf<T>().polls==0 && Access::DrainOf<T>().readies==0,"start never polls or arms");
    const status_runtime_test::Call expected[]={status_runtime_test::PrepareContract,status_runtime_test::Roots,
        status_runtime_test::PrepareOriginals,status_runtime_test::Bindings,status_runtime_test::PrepareRouter,
        status_runtime_test::Original,status_runtime_test::CommitRouter,status_runtime_test::Gated,
        status_runtime_test::BeginDrain,status_runtime_test::Gated};
    Check(status_runtime_test::callCount==sizeof(expected)/sizeof(expected[0]) && !memcmp(expected,status_runtime_test::calls,sizeof(expected)),
        "prepare, publish, five-gate contract, retained-thread begin occur in order");
    Check(status_runtime_test::nativeCalls[0]==1,"real typed wrapper already forwards inside synthetic Commit");
    Check(Access::CorrectCandidates<T>(Module),"all five exact definitions/ranges and typed targets remain in static storage");
    Check(!Start<T>() && T::InspectOnOwner().phase==Phase::Bootstrap,"second start cannot rebind singleton Observer");
    Check(T::Tick().phase==Phase::Bootstrap,"unfinished drain defers arm");
    auto& drain=Access::DrainOf<T>();drain.ready=true;
    status_runtime_test::duringOriginal=[] {
        const auto result=T::Tick();
        Check(result.phase==Phase::Bootstrap && result.sampledInFlight==1,"old bootstrap ticket defers Arm after completed drain");
    };
    Check(Access::InvokeInit<T>()==18,"nested tick preserves native return value");
    status_runtime_test::duringOriginal=nullptr;
    Check(T::Tick().phase==Phase::Observing,"next tick arms after ticket exits");
    const unsigned readyCount=drain.readies;
    Check(T::Tick().phase==Phase::Observing && drain.readies>readyCount,"retained identity/gates checked again after arm");
    Access::RouterOf<T>().verify=false;
    Check(T::Tick().phase==Phase::Fault && Access::ObserverState<T>().phase==status_observer::Phase::Fault,
        "post-arm gate loss permanently faults observation");
    Access::RouterOf<T>().verify=true;
    Check(T::Tick().phase==Phase::Fault && !Start<T>(),"restored gate cannot restart or rearm faulted singleton");
    unsigned before[5]{};memcpy(before,status_runtime_test::nativeCalls,sizeof(before));
    Check(Access::ForwardAll<T>(),"every typed wrapper still forwards after permanent fault");
    for(unsigned i=0;i<5;++i)Check(status_runtime_test::nativeCalls[i]==before[i]+1,"exactly one original call per faulted wrapper");
    Check(Access::OriginalsOf<T>().cleanupCalls==0,"published originals never released on fault");
}
template<unsigned N,Error Expected> void Failure() {
    using T=Case<N>;auto& c=Access::ContractOf<T>();auto& o=Access::OriginalsOf<T>();auto& r=Access::RouterOf<T>();
    if constexpr(Expected==Error::ContractPrepare)c.prepare=false;
    if constexpr(Expected==Error::Candidates)c.ranges=false;
    if constexpr(Expected==Error::OriginalsPrepare)o.prepare=false;
    if constexpr(Expected==Error::Bindings)o.bindings=false;
    if constexpr(Expected==Error::ObserverBind)o.badBinding=true;
    if constexpr(Expected==Error::RouterPrepare)r.prepare=false;
    if constexpr(Expected==Error::ContractOriginal)c.original=false;
    if constexpr(Expected==Error::RouterCommit){r.commit=false;r.callDuringCommit=true;}
    if constexpr(Expected==Error::ContractGated)c.gated=false;
    if constexpr(Expected==Error::DrainBegin)Access::DrainOf<T>().begin=false;
    Check(!Start<T>(),"injected preparation/publication failure rejects Start");
    auto d=T::InspectOnOwner();Check(d.phase==Phase::Fault && d.error==Expected,"first failure reason preserved");
    Check(Access::DrainOf<T>().polls==0,"failed start also never polls");
    Check(!Start<T>() && T::Tick().phase==Phase::Fault,"failure does not reopen initialization");
    if constexpr(Expected==Error::OriginalsPrepare || Expected==Error::Bindings)
        Check(o.cleanupCalls==1,"unpublished originals cleaned on failure");
    if constexpr(Expected==Error::ObserverBind || Expected==Error::RouterPrepare || Expected==Error::ContractOriginal ||
        Expected==Error::RouterCommit || Expected==Error::ContractGated || Expected==Error::DrainBegin)
        Check(o.cleanupCalls==0,"Bindings seals lifetime across every later failure");
    if constexpr(Expected==Error::RouterCommit)Check(Access::ForwardAll<T>(),"partial-publication fault leaves all typed forwarders usable");
}
void ResumeMaintenance() {
    using T=Case<30>;Check(Start<T>(),"start resume-maintenance case");
    auto& d=Access::DrainOf<T>();d.pending=true;d.retryFailures=2;
    auto value=T::Tick();
    Check(value.phase==Phase::Fault && value.resumePending && value.observerFaultPending,"resume debt records local fault before locking Observer");
    Check(Access::ObserverState<T>().phase==status_observer::Phase::Bootstrap,"observer fault intentionally deferred while resume debt exists");
    value=T::Tick(0);Check(value.resumePending && value.observerFaultPending,"fault tick services failed resume even with zero scan budget");
    value=T::Tick(status_thread_drain::MaxThreads+1);
    Check(!value.resumePending && !value.observerFaultPending && value.phase==Phase::Fault,"repaid debt permits fault propagation without rearm");
    Check(Access::ObserverState<T>().phase==status_observer::Phase::Fault && d.polls==3,"Observer lock reached only after synthetic debt clears");
    Check(Access::ForwardAll<T>(),"resume-debt fault preserves typed forwarding");
    using U=Case<31>;auto& o=Access::OriginalsOf<U>();o.prepare=false;o.cleanupFailures=2;
    Check(!Start<U>() && o.cleanupCalls==1,"unpublished cleanup failure remains retryable");
    U::Tick();U::Tick();Check(o.cleanupCalls==3 && o.Status()==status_originals::State::Closed,"fault ticks retry unpublished cleanup until successful");
}
struct ForeignResult {Diagnostic tick{},inspect{};bool started=false;DWORD expected=0;};
DWORD WINAPI Foreign(void* raw) {
    auto& result=*static_cast<ForeignResult*>(raw);
    result.started=Case<40>::Start(Module,Pool,123,result.expected);
    result.tick=Case<40>::Tick();result.inspect=Case<40>::InspectOnOwner();return 0;
}
void Ownership() {
    using T=Case<40>;
    Check(!T::Start(Module,Pool,123,0),"missing confirmed game thread cannot claim runtime");
    Check(!T::Start(Module,Pool,0,GetCurrentThreadId()),"missing instance cannot claim runtime");
    Check(!T::Start(Module,Pool+4,123,GetCurrentThreadId()),"plausible aligned but nonretail pool cannot claim runtime");
    Check(!T::Start(UINTPTR_MAX-4,Pool,123,GetCurrentThreadId()),"module-plus-pool overflow cannot claim runtime");
    Check(Start<T>(),"valid owner claims runtime after rejected configuration");
    Check(T::Tick(0).phase==Phase::Bootstrap && T::Tick(status_thread_drain::MaxThreads+1).phase==Phase::Bootstrap &&
        Access::DrainOf<T>().polls==0,"invalid bootstrap budget cannot scan or arm");
    ForeignResult result{};result.expected=GetCurrentThreadId();
    const HANDLE thread=CreateThread(nullptr,0,&Foreign,&result,0,nullptr);
    Check(thread!=nullptr,"create own test thread for rejected foreign calls");
    if(thread){if(WaitForSingleObject(thread,10000)!=WAIT_OBJECT_0)ExitProcess(90);CloseHandle(thread);}
    Check(!result.started && result.tick.phase==Phase::Invalid && result.inspect.phase==Phase::Invalid,
        "foreign thread receives conservative diagnostics and cannot start/tick");
    Check(Access::DrainOf<T>().polls==0 && T::InspectOnOwner().phase==Phase::Bootstrap,"foreign calls leave owner state untouched");
    Access::DrainOf<T>().ready=true;Check(T::Tick().phase==Phase::Observing,"owner arms normally");
    const unsigned before=Access::DrainOf<T>().polls;Access::SimulateEndedOwner<T>();
    Check(T::Tick().phase==Phase::Invalid && T::InspectOnOwner().phase==Phase::Invalid && Access::DrainOf<T>().polls==before,
        "signaled retained owner object rejects Tick/diagnostics despite matching DWORD ID");
}
}
int main() {
    SuccessAndDeferral();
    Failure<10,Error::ContractPrepare>();Failure<11,Error::Candidates>();Failure<12,Error::OriginalsPrepare>();
    Failure<13,Error::Bindings>();Failure<14,Error::ObserverBind>();Failure<15,Error::RouterPrepare>();
    Failure<16,Error::ContractOriginal>();Failure<17,Error::RouterCommit>();Failure<18,Error::ContractGated>();
    Failure<19,Error::DrainBegin>();ResumeMaintenance();Ownership();
    printf("Status observation coordinator synthetic checks: %u; failures: %u\n",checks,failures);
    return failures?1:0;
}
