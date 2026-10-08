#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define KH2_STATUS_OBSERVER_TESTS
#include "../../src/KH2Trainer.Bridge/StatusObserverSupport.h"
#include <stdio.h>
#include <string.h>
#include <limits.h>
#include <type_traits>
#include <initializer_list>

using namespace status_observer;
using namespace status_revision;
static volatile LONG checks=0,failures=0;
static void Check(bool result,const char* label) {
    InterlockedIncrement(&checks);
    if(!result) { InterlockedIncrement(&failures);printf("FAIL: %s\n",label); }
}
namespace status_observer {
struct ObserverTestAccess {
    static void ForceCounter(Observer& observer,uint64_t value) { observer.inFlight=value; }
};
}
enum Kind { Init,RebuildKind,Coeff,ResetKind,ReleaseKind };
constexpr DWORD OriginalException=0xe0424567, MetadataException=0xe0424568;
constexpr DWORD IncomingError=0x2468ace0, OutgoingError=0x76543210;
constexpr uint64_t ReturnBase=0xfedcba9876543200ull;
struct Scenario {
    Observer* observer=nullptr;
    uintptr_t argument=0;
    const unsigned char* save=nullptr;
    int index=6,percent=147;
    volatile LONG calls[5]{};
    unsigned expectedFrames=1;
    unsigned recursiveCalls=0;
    bool raise=false,nest=false,mutate=false;
    HANDLE entered=nullptr,proceed=nullptr;
};
static thread_local Scenario* active=nullptr;
static void InOriginal(Kind kind,uintptr_t value) {
    Scenario& s=*active;
    Check(GetLastError()==IncomingError,"original receives caller LastError");
    Check(value==s.argument,"original receives exact first argument");
    InterlockedIncrement(&s.calls[kind]);
    // Reenter the metadata lock from inside every original. A lock held across
    // forwarding would deadlock here even in the single-thread tests.
    const State state=s.observer->Inspect();
    Check(state.inFlight>=1,"original has in-flight ticket");
    Check(state.ledgerFrames==s.expectedFrames,"entry invalidated before original");
    if(s.entered) {
        SetEvent(s.entered);
        Check(WaitForSingleObject(s.proceed,5000)==WAIT_OBJECT_0,"worker released by test barrier");
    }
    if(s.raise) {
        SetLastError(OutgoingError);
        RaiseException(OriginalException,0,0,nullptr);
    }
}
static uint64_t __fastcall OriginalInit(uintptr_t status) {
    InOriginal(Init,status);
    if(active->mutate)*reinterpret_cast<int*>(status+RefCountOffset)=1;
    SetLastError(OutgoingError);return ReturnBase+Init;
}
static uint64_t __fastcall OriginalRebuild(uintptr_t status,const unsigned char* save) {
    Check(save==active->save,"rebuild optional save pointer preserved");
    InOriginal(RebuildKind,status);
    if(active->nest) {
        active->expectedFrames=2;
        SetLastError(IncomingError);
        Check(active->observer->Coefficient(status,active->index,active->percent)==ReturnBase+Coeff,"nested return preserved");
        active->expectedFrames=1;
        Check(active->observer->Inspect().ledgerFrames==1,"nested finally drains only nested frame");
    }
    SetLastError(OutgoingError);return ReturnBase+RebuildKind;
}
static uint64_t __fastcall OriginalCoefficient(uintptr_t status,int index,int percent) {
    Check(index==active->index && percent==active->percent,"signed coefficient arguments preserved");
    InOriginal(Coeff,status);
    if(active->recursiveCalls) {
        --active->recursiveCalls;
        const unsigned outerFrames=active->expectedFrames;
        if(active->expectedFrames<FrameCapacity)++active->expectedFrames;
        SetLastError(IncomingError);
        Check(active->observer->Coefficient(status,index,percent)==ReturnBase+Coeff,"recursive callback return preserved");
        active->expectedFrames=outerFrames;
    }
    if(active->mutate && index==6)*reinterpret_cast<unsigned char*>(status+430)=static_cast<unsigned char>(percent);
    SetLastError(OutgoingError);return ReturnBase+Coeff;
}
static void __fastcall OriginalReset(uintptr_t pool) {
    InOriginal(ResetKind,pool);
    if(active->mutate) {
        for(unsigned i=0;i<SlotCount;++i)*reinterpret_cast<int*>(pool+FreeListOffset+i*sizeof(int))=i;
        *reinterpret_cast<int*>(pool+FreeCountOffset)=SlotCount;
    }
    SetLastError(OutgoingError);
}
static uint64_t __fastcall OriginalRelease(uintptr_t status) {
    InOriginal(ReleaseKind,status);
    if(active->mutate)--*reinterpret_cast<int*>(status+RefCountOffset);
    SetLastError(OutgoingError);return ReturnBase+ReleaseKind;
}
static const Originals Native{OriginalInit,OriginalRebuild,OriginalCoefficient,OriginalReset,OriginalRelease};
struct Fixture {
    alignas(16) unsigned char bytes[PoolSize]{};
    Observer observer{};
    uintptr_t Base() { return reinterpret_cast<uintptr_t>(bytes); }
    uintptr_t Status(unsigned slot=7) { return Base()+slot*StatusSize; }
    int& Count() { return *reinterpret_cast<int*>(bytes+FreeCountOffset); }
    int& Free(unsigned slot) { return *reinterpret_cast<int*>(bytes+FreeListOffset+sizeof(int)*slot); }
    int& Ref(unsigned slot=7) { return *reinterpret_cast<int*>(bytes+slot*StatusSize+RefCountOffset); }
    void Prepare(bool arm=true) {
        for(unsigned i=0;i<SlotCount;++i)Ref(i)=1;
        Check(observer.Bind(Native,Base(),0x543210abcdef,GetCurrentThreadId()),"bind once");
        if(arm)Check(observer.ArmAfterProvenBarrier(0x543210abcdef),"explicit test barrier arms metadata");
    }
};
struct CaptureRequest { uintptr_t status=0; Stamp stamp{}; };
static bool Capture(TransactionContext& context,void* value) noexcept {
    auto& request=*static_cast<CaptureRequest*>(value);unsigned slot=SlotCount;int refs=0;
    return context.pool.Owns(request.status,slot,refs) && context.ledger.Capture(slot,request.stamp,true);
}
struct CompareRequest { Stamp stamp{}; uint32_t mask=AllFields; Observation result{}; };
static bool Compare(TransactionContext& context,void* value) noexcept {
    auto& request=*static_cast<CompareRequest*>(value);
    request.result=context.ledger.Compare(request.stamp,request.mask);return true;
}
static Stamp Take(Fixture& f,unsigned slot=7) {
    CaptureRequest request{f.Status(slot)};
    Check(f.observer.WithMetadata(Capture,&request),"capture allocated pool slot");return request.stamp;
}
static Observation Observe(Fixture& f,const Stamp& stamp,uint32_t mask=AllFields) {
    CompareRequest request{stamp,mask};
    Check(f.observer.WithMetadata(Compare,&request),"compare metadata while idle");return request.result;
}
static uint64_t Invoke(Observer& o,Kind kind,uintptr_t argument,const unsigned char* save=nullptr,int index=6,int percent=147) {
    switch(kind) {
    case Init:return o.Initialize(argument);
    case RebuildKind:return o.Rebuild(argument,save);
    case Coeff:return o.Coefficient(argument,index,percent);
    case ResetKind:o.Reset(argument);return 0;
    case ReleaseKind:return o.Release(argument);
    }
    return 0;
}
static DWORD CatchOriginal(Observer& o,Kind kind,uintptr_t argument) {
    __try { Invoke(o,kind,argument); }
    __except(EXCEPTION_EXECUTE_HANDLER) { return GetExceptionCode(); }
    return 0;
}
static void Call(Fixture& f,Kind kind,Scenario& s) {
    active=&s;s.observer=&f.observer;
    if(!s.argument)s.argument=kind==ResetKind?f.Base():f.Status();
    SetLastError(IncomingError);
    const uint64_t result=Invoke(f.observer,kind,s.argument,s.save,s.index,s.percent);
    Check(result==(kind==ResetKind?0:ReturnBase+kind),"all return bits preserved");
    Check(GetLastError()==OutgoingError,"native LastError survives finally");
    Check(s.calls[kind]==1,"original forwarded exactly once");
    const State state=f.observer.Inspect();
    Check(state.inFlight==0 && state.ledgerFrames==0,"normal finally drains all tickets");
}

Observer BoundEntry;
using ActualEntry=Entrypoints<BoundEntry>;
static_assert(std::is_same_v<decltype(&ActualEntry::Initialize),InitOriginal>);
static_assert(std::is_same_v<decltype(&ActualEntry::Rebuild),RebuildOriginal>);
static_assert(std::is_same_v<decltype(&ActualEntry::Coefficient),CoefficientOriginal>);
static_assert(std::is_same_v<decltype(&ActualEntry::Reset),ResetOriginal>);
static_assert(std::is_same_v<decltype(&ActualEntry::Release),ReleaseOriginal>);
static void Basic() {
    unsigned invalidSlot=0;
    Check(!PoolView{0}.Initializable(0,invalidSlot),"null pool rejected");
    Check(!PoolView{UINTPTR_MAX-15}.Slot(UINTPTR_MAX-15,invalidSlot),"public pool view rejects overflow");
    for(unsigned kind=Init;kind<=ReleaseKind;++kind) {
        Fixture f;f.Prepare();Scenario s{};
        unsigned char save[16]{};s.save=save;
        const Stamp stamp=Take(f);
        Call(f,static_cast<Kind>(kind),s);
        Check(f.observer.Inspect().phase==Phase::Observing,"ordinary callback keeps observer healthy");
        const auto result=Observe(f,stamp);
        Check(result.result==(kind==Init || kind==ResetKind || kind==ReleaseKind?
            Match::AllocationEnded:Match::Superseded),"entry family invalidates old ownership");
        if(kind==Coeff)Check(result.changedFields==(1u<<General),"coefficient write only invalidates general");
    }
    Fixture f;f.Prepare();Scenario s{};s.nest=true;const Stamp stamp=Take(f);
    Call(f,RebuildKind,s);
    Check(s.calls[Coeff]==1,"same-thread nested native callback forwarded");
    Check(Observe(f,stamp).changedFields==AllFields,"rebuild invalidates all fields despite nested writer");

    alignas(16) static unsigned char pool[PoolSize]{};
    *reinterpret_cast<int*>(pool+RefCountOffset)=1;
    Check(BoundEntry.Bind(Native,reinterpret_cast<uintptr_t>(pool),42,GetCurrentThreadId()),"actual ABI entry binds");
    Check(BoundEntry.ArmAfterProvenBarrier(42),"actual ABI entry arms");
    s={};s.observer=&BoundEntry;s.argument=reinterpret_cast<uintptr_t>(pool);active=&s;
    SetLastError(IncomingError);Check(ActualEntry::Initialize(s.argument)==ReturnBase+Init,"native Init ABI entry");
    SetLastError(IncomingError);Check(ActualEntry::Rebuild(s.argument,nullptr)==ReturnBase+RebuildKind,"native Rebuild ABI entry");
    SetLastError(IncomingError);Check(ActualEntry::Coefficient(s.argument,6,147)==ReturnBase+Coeff,"native Coeff ABI entry");
    SetLastError(IncomingError);Check(ActualEntry::Release(s.argument)==ReturnBase+ReleaseKind,"native Release ABI entry");
    s.expectedFrames=1;SetLastError(IncomingError);ActualEntry::Reset(s.argument);
    Check(s.calls[ResetKind]==1,"native Reset ABI entry");
}
static void LifecycleAndErrors() {
    Fixture f;
    Check(f.observer.Inspect().phase==Phase::Dormant,"new observer dormant");
    Check(!f.observer.ArmAfterProvenBarrier(1),"unbound observer cannot arm");
    CaptureRequest request{f.Status()};Check(!f.observer.WithMetadata(Capture,&request),"dormant capture rejected");
    Check(!f.observer.Bind({},f.Base(),1,GetCurrentThreadId()),"missing originals rejected");
    Check(!f.observer.Bind(Native,0,1,GetCurrentThreadId()),"null pool binding rejected");
    Check(!f.observer.Bind(Native,UINTPTR_MAX-15,1,GetCurrentThreadId()),"overflow pool binding rejected");
    Check(!f.observer.Bind(Native,f.Base()+1,1,GetCurrentThreadId()),"unaligned pool binding rejected");
    Check(!f.observer.Bind(Native,f.Base(),0,GetCurrentThreadId()),"zero instance binding rejected");
    Check(!f.observer.Bind(Native,f.Base(),1,0),"zero thread binding rejected");
    f.Prepare(false);
    Check(!f.observer.WithMetadata(Capture,&request),"bootstrap cannot acquire ownership");
    Check(!f.observer.ArmAfterProvenBarrier(3),"wrong instance cannot arm");
    Scenario s{};s.expectedFrames=0;Call(f,RebuildKind,s);
    Check(f.observer.Inspect().phase==Phase::Bootstrap,"bootstrap forwarding does not imply readiness");
    Check(f.observer.ArmAfterProvenBarrier(0x543210abcdef),"bootstrap needs explicit confirmed barrier");
    Check(!f.observer.ArmAfterProvenBarrier(0x543210abcdef),"cannot silently remint ledger");
    Check(f.observer.Inspect().phase==Phase::Observing,"repeat arm has no state mutation");
    f.observer.Fault();
    Check(!f.observer.ArmAfterProvenBarrier(0x543210abcdef),"fault cannot be reset");
    s={};s.expectedFrames=0;Call(f,Coeff,s);
    Check(!f.observer.WithMetadata(Capture,&request),"fault blocks ownership but not native forwarding");
    Check(!f.observer.Bind(Native,f.Base(),99,GetCurrentThreadId()),"cannot rebind originals after publication");
    s={};s.expectedFrames=0;Call(f,Init,s);

    for(unsigned kind=Init;kind<=ReleaseKind;++kind) {
        Fixture each;each.Prepare();Scenario exception{};
        exception.observer=&each.observer;exception.argument=kind==ResetKind?each.Base():each.Status();
        exception.raise=true;active=&exception;Take(each);
        SetLastError(IncomingError);
        Check(CatchOriginal(each.observer,static_cast<Kind>(kind),exception.argument)==OriginalException,"original SEH propagates unchanged");
        Check(GetLastError()==OutgoingError,"original exception LastError preserved");
        Check(exception.calls[kind]==1,"throwing original still called only once");
        const State state=each.observer.Inspect();
        Check(state.phase==Phase::Fault && state.inFlight==0 && state.ledgerFrames==0,"abnormal finally faults then drains");
        CaptureRequest q{each.Status()};Check(!each.observer.WithMetadata(Capture,&q),"abnormal original cannot prove ownership ended");
        Check(each.Ref()==1,"throw-before-write leaves actual refcount unchanged");
    }
}
static void PoolAndArguments() {
    for(unsigned slot=0;slot<SlotCount;++slot) {
        Fixture f;f.Prepare();const Stamp before=Take(f,slot);
        Scenario s{};s.argument=f.Status(slot);s.percent=INT_MIN;s.index=6;Call(f,Coeff,s);
        const auto after=Observe(f,before);
        Check(after.result==Match::Superseded && after.changedFields==(1u<<General),"every pool slot maps to its correct generation");
    }
    for(int index=0;index<=6;++index) {
        Fixture f;f.Prepare();const Stamp before=Take(f);Scenario s{};s.index=index;s.percent=INT_MAX;Call(f,Coeff,s);
        Check(Observe(f,before).result==(index==6?Match::Superseded:Match::Current),"only native general index changes watched coefficient");
    }
    for(int index:{-1,7,INT_MIN,INT_MAX}) {
        Fixture f;f.Prepare();Scenario s{};s.index=index;s.percent=INT_MIN;Call(f,Coeff,s);
        Check(f.observer.Inspect().phase==Phase::Fault,"unbounded native index faults observation without changing arguments");
    }
    for(unsigned failure=0;failure<10;++failure) {
        Fixture f;f.Prepare();Scenario s{};s.expectedFrames=0;
        switch(failure) {
        case 0:f.Count()=-1;break;
        case 1:f.Count()=SlotCount+1;break;
        case 2:f.Count()=2;f.Free(0)=2;f.Free(1)=2;break;
        case 3:f.Count()=1;f.Free(0)=SlotCount;break;
        case 4:f.Count()=1;f.Free(0)=-1;break;
        case 5:f.Count()=1;f.Free(0)=7;break;
        case 6:f.Ref()=0;break;
        case 7:f.Ref()=-1;break;
        case 8:s.argument=f.Status()+1;break;
        case 9:s.argument=f.Base()+FreeListOffset;break;
        }
        Call(f,ReleaseKind,s);
        Check(f.observer.Inspect().phase==Phase::Fault,"invalid release allocation never retires a trusted generation");
    }
    { Fixture f;f.Prepare();Scenario s{};f.Ref()=2;const Stamp before=Take(f);s.mutate=true;Call(f,ReleaseKind,s);
      Check(f.Ref()==1 && Observe(f,before).result==Match::Current,"pre-release refcount greater than one preserves allocation"); }
    { Fixture f;f.Prepare();Scenario s{};s.mutate=true;const Stamp before=Take(f);Call(f,ReleaseKind,s);
      Check(f.Ref()==0 && Observe(f,before).result==Match::AllocationEnded,"pre-release refcount one retires allocation before free"); }
    { Fixture f;f.Prepare();f.Count()=SlotCount;
      for(unsigned i=0;i<SlotCount;++i) { f.Free(i)=i;f.Ref(i)=0; }
      for(unsigned i=0;i<SlotCount;++i) { Scenario s{};s.argument=f.Status(i);s.mutate=true;Call(f,Init,s);
          CaptureRequest q{f.Status(i)};Check(!f.observer.WithMetadata(Capture,&q),"startup Init does not turn a free slot into an owned slot"); }
      Check(f.observer.Inspect().phase==Phase::Observing,"startup initialization accepts free slots and stale refcounts"); }
    { Fixture f;f.Prepare();f.Count()=-9;Scenario s{};s.mutate=true;Call(f,ResetKind,s);
      Check(f.Count()==SlotCount && f.observer.Inspect().phase==Phase::Observing,"reset validates pool identity independently of old contents"); }
    { Fixture f;f.Prepare();Scenario s{};s.argument=f.Base()+16;s.expectedFrames=0;Call(f,ResetKind,s);
      Check(f.observer.Inspect().phase==Phase::Fault,"wrong pool reset pointer forwarded but invalidates confidence"); }
    { Fixture f;f.Prepare();Scenario s{};s.argument=1;s.expectedFrames=0;Call(f,Init,s);
      Check(f.observer.Inspect().phase==Phase::Fault,"out-of-pool Init is not silently ignored"); }
    { Fixture f;f.Prepare();ObserverTestAccess::ForceCounter(f.observer,UINT64_MAX);Scenario s{};s.expectedFrames=0;
      active=&s;s.observer=&f.observer;s.argument=f.Status();SetLastError(IncomingError);
      Check(f.observer.Coefficient(s.argument,6,147)==ReturnBase+Coeff,"counter overflow still forwards original");
      Check(s.calls[Coeff]==1 && f.observer.Inspect().phase==Phase::Fault,"counter overflow faults without wrapping"); }
    { Fixture f;f.Prepare();Scenario s{};s.recursiveCalls=39;s.observer=&f.observer;s.argument=f.Status();active=&s;
      SetLastError(IncomingError);Check(f.observer.Coefficient(s.argument,6,147)==ReturnBase+Coeff,"ledger frame overflow preserves outer return");
      const State state=f.observer.Inspect();
      Check(s.calls[Coeff]==40,"every overflowing nested invocation forwards exactly once");
      Check(state.phase==Phase::Fault && state.inFlight==0 && state.ledgerFrames==0,"frame overflow faults yet drains prior frames"); }
}
struct Worker {
    Scenario scenario{}; Kind kind=Coeff; bool tryArm=false,catchOriginal=false;
    bool armResult=true,transactionResult=true;DWORD exceptionCode=0;
};
static DWORD WINAPI RunWorker(void* value) {
    auto& w=*static_cast<Worker*>(value);active=&w.scenario;
    if(w.tryArm) {
        w.armResult=w.scenario.observer->ArmAfterProvenBarrier(0x543210abcdef);
        CaptureRequest q{w.scenario.argument};w.transactionResult=w.scenario.observer->WithMetadata(Capture,&q);
    } else if(w.catchOriginal) {
        SetLastError(IncomingError);w.exceptionCode=CatchOriginal(*w.scenario.observer,w.kind,w.scenario.argument);
    } else {
        SetLastError(IncomingError);Invoke(*w.scenario.observer,w.kind,w.scenario.argument);
    }
    return 0;
}
static void Concurrency() {
    Fixture f;f.Prepare(false);
    Worker worker{};worker.tryArm=true;worker.scenario.observer=&f.observer;worker.scenario.argument=f.Status();
    HANDLE thread=CreateThread(nullptr,0,RunWorker,&worker,0,nullptr);
    Check(thread && WaitForSingleObject(thread,5000)==WAIT_OBJECT_0,"foreign thread probe completes");if(thread)CloseHandle(thread);
    Check(!worker.armResult && !worker.transactionResult,"game-thread ownership is enforced");
    for(unsigned bootstrap=0;bootstrap<2;++bootstrap) {
        if(bootstrap)Check(f.observer.ArmAfterProvenBarrier(0x543210abcdef),"arm after all bootstrap callbacks returned");
        Worker workers[2]{};HANDLE threads[2]{};
        for(unsigned i=0;i<2;++i) {
            auto& s=workers[i].scenario;s.observer=&f.observer;s.argument=f.Status(i);
            s.expectedFrames=bootstrap?i+1:0;
            s.entered=CreateEventW(nullptr,TRUE,FALSE,nullptr);s.proceed=CreateEventW(nullptr,TRUE,FALSE,nullptr);
            threads[i]=CreateThread(nullptr,0,RunWorker,&workers[i],0,nullptr);
            Check(threads[i] && WaitForSingleObject(s.entered,5000)==WAIT_OBJECT_0,"worker reaches native original without metadata lock held");
        }
        const State running=f.observer.Inspect();
        Check(running.inFlight==2 && running.ledgerFrames==(bootstrap?2u:0u),"overlapping threads have independent in-flight records");
        Check(!f.observer.ArmAfterProvenBarrier(0x543210abcdef),"cannot arm during a callback");
        CaptureRequest q{f.Status()};Check(!f.observer.WithMetadata(Capture,&q),"transactions wait for every active original");
        // Older frame returns first: global LIFO would reject this legal order.
        for(unsigned i=0;i<2;++i) {
            SetEvent(workers[i].scenario.proceed);
            Check(WaitForSingleObject(threads[i],5000)==WAIT_OBJECT_0,"overlapping callback finishes");
            CloseHandle(threads[i]);CloseHandle(workers[i].scenario.entered);CloseHandle(workers[i].scenario.proceed);
        }
        Check(f.observer.Inspect().inFlight==0 && f.observer.Inspect().ledgerFrames==0,"cross-thread exits drain independently");
        Check(f.observer.Inspect().phase==(bootstrap?Phase::Observing:Phase::Bootstrap),"worker overlap preserves lifecycle phase");
    }
    Worker foreign{};foreign.tryArm=true;foreign.scenario.observer=&f.observer;foreign.scenario.argument=f.Status();
    thread=CreateThread(nullptr,0,RunWorker,&foreign,0,nullptr);
    Check(thread && WaitForSingleObject(thread,5000)==WAIT_OBJECT_0,"observing foreign-thread probe completes");if(thread)CloseHandle(thread);
    Check(!foreign.transactionResult,"worker cannot run a field transaction after bootstrap");

    Worker waiting{},throwing{};
    waiting.scenario.observer=&f.observer;waiting.scenario.argument=f.Status();
    waiting.scenario.entered=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    waiting.scenario.proceed=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    HANDLE first=CreateThread(nullptr,0,RunWorker,&waiting,0,nullptr);
    Check(first && WaitForSingleObject(waiting.scenario.entered,5000)==WAIT_OBJECT_0,"overlap exception fixture enters first original");
    throwing.scenario.observer=&f.observer;throwing.scenario.argument=f.Status(8);
    throwing.scenario.expectedFrames=2;throwing.scenario.raise=true;throwing.catchOriginal=true;
    HANDLE second=CreateThread(nullptr,0,RunWorker,&throwing,0,nullptr);
    Check(second && WaitForSingleObject(second,5000)==WAIT_OBJECT_0,"throwing overlapping callback returns through SEH");
    State state=f.observer.Inspect();
    Check(throwing.exceptionCode==OriginalException && state.phase==Phase::Fault && state.inFlight==1 && state.ledgerFrames==1,
        "one worker's exception faults confidence while retaining other worker's frame");
    SetEvent(waiting.scenario.proceed);
    Check(WaitForSingleObject(first,5000)==WAIT_OBJECT_0,"other worker drains after confidence loss");
    state=f.observer.Inspect();
    Check(state.phase==Phase::Fault && state.inFlight==0 && state.ledgerFrames==0,"faulted observer drains outstanding cross-thread frame");
    CloseHandle(first);CloseHandle(second);CloseHandle(waiting.scenario.entered);CloseHandle(waiting.scenario.proceed);
}
static bool ManualWrite(TransactionContext& context,void* argument) noexcept {
    auto& request=*static_cast<CaptureRequest*>(argument);unsigned slot=SlotCount;int refs=0;
    if(!context.pool.Owns(request.status,slot,refs) || !context.ledger.Capture(slot,request.stamp,true))return false;
    const Frame frame=context.ledger.Enter(Event::ManualWrite,slot,0,1u<<General,GetCurrentThreadId());
    *reinterpret_cast<unsigned char*>(request.status+430)=100;
    context.ledger.Exit(frame);return true;
}
static bool ThrowingTransaction(TransactionContext&,void*) noexcept { RaiseException(MetadataException,0,0,nullptr);return true; }
static void TransactionsAndUnreadable() {
    Fixture f;f.Prepare();*reinterpret_cast<unsigned char*>(f.Status()+430)=100;
    CaptureRequest request{f.Status()};
    Check(f.observer.WithMetadata(ManualWrite,&request),"guard/receipt/write fit inside one lock acquisition");
    Check(Observe(f,request.stamp).result==Match::Superseded,"equal-value manual write invalidates ownership");
    Check(!f.observer.WithMetadata(nullptr,nullptr),"null transaction rejected");
    Check(!f.observer.WithMetadata(ThrowingTransaction,nullptr),"metadata SEH is contained");
    Check(f.observer.Inspect().phase==Phase::Fault,"metadata SEH faults observer");
    Scenario s{};s.expectedFrames=0;Call(f,Coeff,s);

    void* memory=VirtualAlloc(nullptr,PoolSize,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    Check(memory!=nullptr,"private unreadable-pool fixture allocated");
    if(memory) {
        Observer observer;const uintptr_t base=reinterpret_cast<uintptr_t>(memory);
        Check(observer.Bind(Native,base,77,GetCurrentThreadId()) && observer.ArmAfterProvenBarrier(77),"unreadable fixture binds");
        DWORD old=0;Check(VirtualProtect(memory,PoolSize,PAGE_READWRITE|PAGE_GUARD,&old)!=FALSE,"private pool made guard protected");
        s={};s.expectedFrames=0;s.observer=&observer;s.argument=base;active=&s;SetLastError(IncomingError);
        Check(observer.Release(base)==ReturnBase+ReleaseKind,"observation refuses guard page and still forwards exactly once");
        MEMORY_BASIC_INFORMATION mbi{};VirtualQuery(memory,&mbi,sizeof(mbi));
        Check((mbi.Protect&PAGE_GUARD)!=0,"observer does not consume a guard-page exception");
        Check(observer.Inspect().phase==Phase::Fault && s.calls[ReleaseKind]==1,"unreadable native pool loses confidence");
        VirtualFree(memory,0,MEM_RELEASE);
    }
}
int main() {
    Basic();LifecycleAndErrors();PoolAndArguments();Concurrency();TransactionsAndUnreadable();
    printf("StatusObserverTests: %ld checks, %ld failures\n",checks,failures);
    return failures?1:0;
}
