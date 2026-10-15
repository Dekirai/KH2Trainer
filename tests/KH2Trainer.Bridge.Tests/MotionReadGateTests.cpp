#include <cstdio>
#include <cstdlib>
#include <new>
#include "../../src/KH2Trainer.Bridge/MotionReadGate.h"

#ifdef MOTION_READ_GATE_PRODUCTION_COMPILE
motion_read_gate::Outcome CompileGate(motion_read_gate::Gate& gate,motion_read_gate::CopyJob& job,
                                      motion_payload_copy::ReadScope& scope) {
    return gate.TryCopy(job,scope);
}
motion_observer::BeforeFn CompileBefore=&motion_read_gate::Gate::Before;
motion_observer::AfterFn CompileAfter=&motion_read_gate::Gate::After;
#else
namespace heap_probe {
thread_local motion_read_gate::Gate* watched=nullptr;
volatile LONG allocations=0,deallocations=0;
}
void* operator new(size_t size) {
    if(heap_probe::watched && heap_probe::watched->ReadingOnThisThread())InterlockedIncrement(&heap_probe::allocations);
    if(void* p=std::malloc(size?size:1))return p;
    throw std::bad_alloc();
}
void TestDelete(void* p) noexcept {
    if(heap_probe::watched && heap_probe::watched->ReadingOnThisThread())InterlockedIncrement(&heap_probe::deallocations);
    std::free(p);
}
void operator delete(void* p) noexcept {TestDelete(p);}
void operator delete(void* p,size_t) noexcept {TestDelete(p);}

namespace {
using namespace motion_read_gate;
using Error=motion_payload_copy::Error;
volatile LONG checks=0,failures=0;
constexpr DWORD NativeException=0xe0424d32,Incoming=0x1234abcd,Outgoing=0xabcd4321;
constexpr uintptr_t Module=0x140000000ull,Actor=0x400000000ull,Resource=0x600000000ull;
constexpr size_t Inner=256,Motion=1024,Payload=32,Controller=344;
constexpr motion_payload_copy::Limits Limits{Payload,3};
void Check(bool okay,const char* label) {
    InterlockedIncrement(&checks);
    if(!okay){InterlockedIncrement(&failures);std::printf("FAIL %s\n",label);}
}
void Wait(HANDLE event,const char* label) {
    if(WaitForSingleObject(event,5000)!=WAIT_OBJECT_0){Check(false,label);ExitProcess(3);}
}
HANDLE Event() {
    HANDLE h=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    if(!h){Check(false,"private event creation");ExitProcess(3);}return h;
}
bool Inside(uintptr_t address,size_t size,uintptr_t base,size_t extent) {
    return address>=base && address-base<=extent && size<=extent-(address-base);
}
template<class T,size_t N> void Put(std::array<uint8_t,N>& data,size_t offset,T value) {
    std::memcpy(data.data()+offset,&value,sizeof(value));
}
uint32_t Packed(size_t offset){return 0x80000000u|static_cast<uint32_t>(offset);}
bool Empty(const motion_payload_copy::Result& result) {
    const auto& i=result.SourceIdentity();
    return result.Payload().empty() && !i.issuer && !i.actorGeneration && !i.cacheRevision && !i.bindingRevision && !i.decoderRevision;
}
bool Pattern(const motion_payload_copy::Result& result,uint8_t value) {
    if(result.Status()!=Error::None || result.Payload().size()!=Payload || result.Payload()[0]!=1)return false;
    for(size_t i=4;i<Payload;++i)if(result.Payload()[i]!=value)return false;
    return true;
}
struct Fixture;
enum class ReadMode {Normal,Pause,ReadReentry,MutationReentry,MutationReentryCaught,Fault,PartialFailure};
enum NativeMode {Write,Hold,Nested,Child,Throw,CompletionHold,SecondHold};
struct Scope final : motion_payload_copy::ReadScope {
    Fixture* fixture;
    ReadMode mode=ReadMode::Normal;
    unsigned reads=0,captures=0,lockErrors=0;
    explicit Scope(Fixture* f):fixture(f){}
    bool Capture(motion_payload_copy::Admission&) noexcept override;
    bool Current(const motion_payload_copy::Admission&) noexcept override;
    bool Read(uintptr_t,void*,size_t) noexcept override;
};
struct Fixture {
    Gate gate;
    motion_observer::Observer observer;
    CopyJob job,otherJob;
    Scope scope{this};
    motion_payload_copy::Admission admission{};
    std::array<uint8_t,1024> actor{};
    std::array<uint8_t,4096> resource{};
    std::array<uint64_t,64> regions{};
    HANDLE nativeEntered=Event(),releaseNative=Event(),readPaused=Event(),releaseRead=Event(),writerAttempt=Event();
    HANDLE secondEntered=Event(),releaseSecond=Event();
    volatile LONG originals=0,clock=0,lastRead=0,writeOrder=0,originalInRead=0;
    uint8_t marker=0x66;
    bool queueEmpty=true;
    DWORD reentryException=0;
    Outcome nestedCopy{},threadCopy{};
    void* faultPage=nullptr;
    Fixture();
    ~Fixture() {
        if(faultPage)VirtualFree(faultPage,0,MEM_RELEASE);
        for(HANDLE h:{nativeEntered,releaseNative,readPaused,releaseRead,writerAttempt,secondEntered,releaseSecond})CloseHandle(h);
    }
    Fixture(const Fixture&)=delete;
    Fixture& operator=(const Fixture&)=delete;
};
uint8_t __fastcall Original(uintptr_t controller,int32_t selection,float blend,float frame) {
    auto& f=*reinterpret_cast<Fixture*>(controller);
    InterlockedIncrement(&f.originals);
    if(f.gate.ReadingOnThisThread())InterlockedIncrement(&f.originalInRead);
    Check(blend==1.25f && frame==3.5f,"typed Original retains float arguments");
    Check(GetLastError()==Incoming,"Before preserves incoming LastError");
    if(selection==Nested) {
        Check(f.gate.Inspect().activeCalls==1,"outer native call is counted without holding gate");
        f.nestedCopy=f.gate.TryCopy(f.otherJob,f.scope);
        Check(f.nestedCopy.status==Status::Busy,"copy requested from active native body returns Busy");
        SetLastError(Incoming);
        f.observer.Select(controller,Child,blend,frame);
        Check(f.gate.Inspect().activeCalls==1,"inner After cannot remove outer active call");
    } else if(selection==Child)Check(f.gate.Inspect().activeCalls==2,"nested typed call owns a separate counted ticket");
    if(selection==Throw) {
        SetLastError(Outgoing);RaiseException(NativeException,0,0,nullptr);
    }
    if(selection==CompletionHold)f.queueEmpty=true;
    if(selection==Hold || selection==CompletionHold) {
        SetEvent(f.nativeEntered);
        Wait(f.releaseNative,"release held private native fixture");
    } else if(selection==SecondHold) {
        SetEvent(f.secondEntered);
        Wait(f.releaseSecond,"release second simultaneous native fixture");
    }
    InterlockedExchange(&f.writeOrder,InterlockedIncrement(&f.clock));
    for(size_t i=4;i<Payload;++i)f.resource[Motion+144+i]=f.marker;
    SetLastError(Outgoing);return 0x7b;
}
DWORD CatchInvoke(Fixture& f,NativeMode mode) {
    __try {f.observer.Select(reinterpret_cast<uintptr_t>(&f),mode,1.25f,3.5f);return 0;}
    __except(EXCEPTION_EXECUTE_HANDLER){return GetExceptionCode();}
}
DWORD CatchCopy(Fixture& f) {
    __try {f.threadCopy=f.gate.TryCopy(f.job,f.scope);return 0;}
    __except(EXCEPTION_EXECUTE_HANDLER){return GetExceptionCode();}
}
Fixture::Fixture() {
    admission.module={Module,0x3000000};admission.actor={Actor,actor.size()};admission.reservation={Resource,resource.size()};
    admission.identity={1,2,3,4,5};admission.kind=motion_payload_copy::ReservationKind::ObservedOrdinary;
    regions[0]=Resource;admission.regions=regions;
    Put<uint64_t>(actor,Controller,Resource);Put<uint64_t>(actor,Controller+16,Actor);
    Put<uint64_t>(actor,Controller+24,Resource+Motion);Put<int32_t>(actor,Controller+40,-1);
    Put<int32_t>(actor,Controller+44,0);Put<int32_t>(actor,Controller+48,-1);
    Put<uint64_t>(actor,Controller+328,Actor+128);
    for(size_t offset:{size_t(0),Inner}) {
        resource[offset]='B';resource[offset+1]='A';resource[offset+2]='R';resource[offset+3]=0x81;
        Put<int32_t>(resource,offset+4,1);Put<uint32_t>(resource,offset+8,Packed(offset));
    }
    Put<uint16_t>(resource,16,17);Put<uint32_t>(resource,24,Packed(Inner));Put<uint32_t>(resource,28,2048);
    Put<uint16_t>(resource,Inner+16,9);Put<uint32_t>(resource,Inner+24,Packed(Motion));Put<uint32_t>(resource,Inner+28,144+Payload);
    Put<uint64_t>(resource,Motion,Module+0x5B4A38);Put<uint64_t>(resource,Motion+8,Resource+Motion+144);
    Put<uint32_t>(resource,Motion+144,1);
    for(size_t i=4;i<Payload;++i)resource[Motion+144+i]=0x22;
    Check(job.Prepare(Limits) && otherJob.Prepare(Limits),"prepare both private workspaces before read interval");
    Check(observer.Bind(Original,&Gate::Before,&Gate::After,&gate),"existing typed Observer binds Gate callbacks");
}
bool Scope::Capture(motion_payload_copy::Admission& value) noexcept {
    ++captures;if(!fixture->gate.ReadingOnThisThread())++lockErrors;
    if(fixture->gate.Inspect().available)++lockErrors; // Reentrant inspection must not acquire SRW again.
    if(!fixture->queueEmpty)return false; // Declared fixture provider policy only.
    value=fixture->admission;return true;
}
bool Scope::Current(const motion_payload_copy::Admission& expected) noexcept {
    if(!fixture->gate.ReadingOnThisThread())++lockErrors;
    return !std::memcmp(&expected.identity,&fixture->admission.identity,sizeof(expected.identity));
}
bool Scope::Read(uintptr_t address,void* destination,size_t size) noexcept {
    auto& f=*fixture;++reads;if(!f.gate.ReadingOnThisThread())++lockErrors;
    const uint8_t* source=nullptr;
    if(Inside(address,size,Actor,f.actor.size()))source=f.actor.data()+address-Actor;
    else if(Inside(address,size,Resource,f.resource.size()))source=f.resource.data()+address-Resource;
    else if(Inside(address,size,Module+motion_payload_copy::RegionTableRva,sizeof(f.regions)))
        source=reinterpret_cast<const uint8_t*>(f.regions.data())+address-Module-motion_payload_copy::RegionTableRva;
    else return false;
    if(address==Resource+Motion+144) {
        const auto action=mode;mode=ReadMode::Normal;
        if(action==ReadMode::Pause) {
            // TEST ONLY: a third coordinator pauses an actual held read to put
            // the writer in contention. Production scopes must never wait.
            SetEvent(f.readPaused);Wait(f.releaseRead,"release paused reader fixture");
        } else if(action==ReadMode::ReadReentry)f.nestedCopy=f.gate.TryCopy(f.otherJob,*this);
        else if(action==ReadMode::MutationReentry)f.observer.Select(reinterpret_cast<uintptr_t>(&f),Write,1.25f,3.5f);
        else if(action==ReadMode::MutationReentryCaught)f.reentryException=CatchInvoke(f,Write);
        else if(action==ReadMode::Fault) {
            *static_cast<volatile LONG*>(destination)=*static_cast<volatile LONG*>(f.faultPage);
        } else if(action==ReadMode::PartialFailure) {
            std::memcpy(destination,source,size/2);return false;
        }
    }
    std::memcpy(destination,source,size);
    InterlockedExchange(&f.lastRead,InterlockedIncrement(&f.clock));return true;
}
Outcome Copy(Fixture& f) {
    const LONG allocations=heap_probe::allocations,deallocations=heap_probe::deallocations;
    heap_probe::watched=&f.gate;
    const auto result=f.gate.TryCopy(f.job,f.scope);
    heap_probe::watched=nullptr;
    Check(heap_probe::allocations==allocations && heap_probe::deallocations==deallocations,"no new/delete while actual reader ownership is held");
    Check(!f.scope.lockErrors,"all Capture/Current/Read callbacks occur under actual gate ownership");
    return result;
}
struct Worker {Fixture* fixture;NativeMode mode;};
DWORD WINAPI Writer(void* argument) {
    auto& w=*static_cast<Worker*>(argument);auto& f=*w.fixture;
    SetLastError(Incoming);SetEvent(f.writerAttempt);
    const uint8_t value=f.observer.Select(reinterpret_cast<uintptr_t>(&f),w.mode,1.25f,3.5f);
    const DWORD error=GetLastError();
    Check(value==0x7b && error==Outgoing,"worker typed return and LastError preserved");return 0;
}
DWORD WINAPI Reader(void* argument) {
    auto& f=*static_cast<Fixture*>(argument);
    f.threadCopy=Copy(f);return 0;
}
HANDLE Start(LPTHREAD_START_ROUTINE routine,void* argument) {
    HANDLE thread=CreateThread(nullptr,0,routine,argument,0,nullptr);
    if(!thread){Check(false,"private native thread creation");ExitProcess(3);}return thread;
}
void Join(HANDLE thread) {Wait(thread,"private thread completes");CloseHandle(thread);}

void WriterFirstAndStaleResult() {
    Fixture f;
    Check(Copy(f).status==Status::Copied,"initial copy succeeds before writer");
    const unsigned captured=f.scope.captures;
    Worker w{&f,Hold};HANDLE writer=Start(Writer,&w);Wait(f.nativeEntered,"writer reached actual original");
    Check(f.gate.Inspect().activeCalls==1,"worker is counted through original wait");
    Check(Copy(f).status==Status::Busy && f.scope.captures==captured,"active writer makes reader Busy before any provider call");
    const auto stale=f.job.TakeResult();
    Check(stale.Status()==Error::NoAdmission && Empty(stale),"Busy invalidates older successful job publication");
    SetEvent(f.releaseNative);Join(writer);
    Check(!f.gate.Faulted() && !f.gate.Inspect().activeCalls,"normal worker exit leaves healthy zero activity");
    Check(Copy(f).status==Status::Copied && Pattern(f.job.TakeResult(),f.marker),"copy after After sees the complete new payload");
    Check(!f.originalInRead,"native original ran outside reader lock");
}
void ReaderFirst() {
    Fixture f;f.scope.mode=ReadMode::Pause;
    HANDLE reader=Start(Reader,&f);Wait(f.readPaused,"reader paused inside held gate");
    Worker w{&f,Write};HANDLE writer=Start(Writer,&w);Wait(f.writerAttempt,"worker attempting typed entry");
    Check(WaitForSingleObject(writer,100)==WAIT_TIMEOUT,"writer cannot complete while reader holds SRW lock");
    Check(f.originals==0 && !f.gate.Inspect().available,"original has not begun and another thread cannot acquire the held gate");
    SetEvent(f.releaseRead);Join(reader);Join(writer);
    Check(f.threadCopy.status==Status::Copied && Pattern(f.job.TakeResult(),0x22),"held reader publishes complete pre-mutation payload");
    Check(f.writeOrder>f.lastRead,"actual writer store follows every source read");
    Check(f.job.Prepare(Limits),"reprepare after taking protected payload");
    Check(Copy(f).status==Status::Copied && Pattern(f.job.TakeResult(),f.marker),"subsequent copy obtains complete post-mutation payload");
}
void TwoNativeWorkers() {
    Fixture f;Worker first{&f,Hold},second{&f,SecondHold};
    HANDLE a=Start(Writer,&first);Wait(f.nativeEntered,"first simultaneous worker entered original");
    HANDLE b=Start(Writer,&second);Wait(f.secondEntered,"second simultaneous worker entered original");
    Check(f.gate.Inspect().activeCalls==2,"two foreign native originals remain independently counted");
    Check(Copy(f).status==Status::Busy && !f.scope.captures,"two workers exclude read before provider capture");
    SetEvent(f.releaseNative);Join(a);
    Check(f.gate.Inspect().activeCalls==1 && Copy(f).status==Status::Busy && !f.scope.captures,
        "first worker After cannot admit a read while second original remains active");
    SetEvent(f.releaseSecond);Join(b);
    Check(!f.gate.Inspect().activeCalls && Copy(f).status==Status::Copied && Pattern(f.job.TakeResult(),f.marker),
        "both real worker completions are required before copying");
}
void NestedAndCompletionGap() {
    Fixture f;SetLastError(Incoming);
    const auto value=f.observer.Select(reinterpret_cast<uintptr_t>(&f),Nested,1.25f,3.5f);
    Check(value==0x7b && f.originals==2 && !f.gate.Inspect().activeCalls,"nested originals balance two real tickets");
    Check(f.scope.captures==0 && !f.gate.Faulted(),"nested Busy path does not invoke provider or fault forwarding");
    f.queueEmpty=false;
    Check(Copy(f).status==Status::CopyRejected,"trusted fixture provider can reject idle gate for pending queue work");
    Worker w{&f,CompletionHold};HANDLE writer=Start(Writer,&w);Wait(f.nativeEntered,"completion cleared fixture queue before returning");
    const unsigned captured=f.scope.captures;
    Check(f.queueEmpty && Copy(f).status==Status::Busy && f.scope.captures==captured,
        "empty queue does not admit read before the active completion original returns");
    SetEvent(f.releaseNative);Join(writer);
    Check(Copy(f).status==Status::Copied,"scope copy begins only after completion After");
}
void ExceptionsAndReentry() {
    {
        Fixture f;SetLastError(Incoming);
        const DWORD code=CatchInvoke(f,Throw),error=GetLastError();
        Check(code==NativeException && error==Outgoing,"native exception and native LastError propagate unchanged");
        Check(f.gate.Faulted() && f.observer.Faulted() && !f.gate.Inspect().activeCalls,"abnormal After faults gate and balances its ticket");
        Check(Copy(f).status==Status::Faulted && !f.scope.captures,"faulted gate performs no provider reads");
        SetLastError(Incoming);Check(f.observer.Select(reinterpret_cast<uintptr_t>(&f),Write,1.25f,3.5f)==0x7b,"fault keeps original forwarding available");
    }
    for(ReadMode mode:{ReadMode::MutationReentry,ReadMode::MutationReentryCaught,ReadMode::ReadReentry}) {
        Fixture f;f.scope.mode=mode;heap_probe::watched=&f.gate;
        const DWORD code=CatchCopy(f);heap_probe::watched=nullptr;
        if(mode==ReadMode::MutationReentry)Check(code==ReadMutationException && f.job.Inspect().status==Status::Unwound,
            "read-to-mutator raises before Acquire and propagates through reader finally");
        else if(mode==ReadMode::MutationReentryCaught)Check(!code && f.reentryException==ReadMutationException && f.job.Inspect().status==Status::Faulted,
            "provider catching forbidden reentry still cannot publish a successful copy");
        else Check(!code && f.nestedCopy.status==Status::Reentrant && f.job.Inspect().status==Status::Faulted,
            "read-to-read fails without recursive SRW acquisition");
        Check(f.gate.Faulted() && f.gate.Inspect().available && !f.gate.Inspect().activeCalls,
            "reentry faults permanently and releases reader lock, including Observer After(false)");
        Check(f.originals==0 && Empty(f.job.TakeResult()),"forbidden reentry neither executes original nor publishes payload");
    }
    {
        Fixture f;Check(Copy(f).status==Status::Copied,"old successful copy precedes real provider AV");
        f.faultPage=VirtualAlloc(nullptr,4096,MEM_RESERVE|MEM_COMMIT,PAGE_NOACCESS);
        if(!f.faultPage){Check(false,"private noaccess page allocation");ExitProcess(3);}
        f.scope.mode=ReadMode::Fault;heap_probe::watched=&f.gate;
        const DWORD code=CatchCopy(f);heap_probe::watched=nullptr;
        Check(code==EXCEPTION_ACCESS_VIOLATION && f.gate.Faulted() && f.gate.Inspect().available,
            "actual private-page AV propagates and reader finally releases lock");
        Check(f.job.Inspect().status==Status::Unwound && Empty(f.job.TakeResult()),"SEH cannot export an earlier successful payload");
    }
    {
        Fixture f;f.scope.mode=ReadMode::PartialFailure;
        Check(Copy(f).status==Status::CopyRejected && Empty(f.job.TakeResult()) && !f.gate.Faulted(),
            "ordinary provider false publishes no partial result and releases lock without exception fault");
        Check(Copy(f).status==Status::Copied,"retained prepared buffers can retry after ordinary rejection");
    }
}
struct ForeignAfter {Gate* gate;uint64_t ticket;};
DWORD WINAPI WrongThreadAfter(void* argument) {
    auto& value=*static_cast<ForeignAfter*>(argument);
    Gate::After(value.gate,10,value.ticket,true,true);return 0;
}
void TicketFaults() {
    {
        Gate gate;const auto a=Gate::Before(&gate,10),b=Gate::Before(&gate,20);
        Gate::After(&gate,10,a,true,true);Gate::After(&gate,10,a,true,true);
        Check(gate.Faulted() && gate.Inspect().activeCalls==1,"duplicate After cannot consume another invocation's ticket");
        Gate::After(&gate,20,b,true,true);Check(!gate.Inspect().activeCalls,"known outstanding ticket still drains after fault");
    }
    {
        Gate gate;const auto a=Gate::Before(&gate,10);
        Gate::After(&gate,20,a,true,true);
        Check(gate.Faulted() && gate.Inspect().activeCalls==1,"wrong-controller After cannot consume a known ticket");
        Gate::After(&gate,10,a,true,true);
    }
    {
        Gate gate;Gate::After(&gate,10,999,true,true);
        Check(gate.Faulted(),"unknown After permanently faults read confidence");
    }
    {
        Gate gate;const auto ticket=Gate::Before(&gate,10);
        ForeignAfter argument{&gate,ticket};HANDLE thread=Start(WrongThreadAfter,&argument);Join(thread);
        Check(gate.Faulted() && gate.Inspect().activeCalls==1,"foreign-thread After cannot consume another thread's ticket");
        Gate::After(&gate,10,ticket,true,true);
        Check(!gate.Inspect().activeCalls && gate.Faulted(),"real owner can drain ticket but cannot clear foreign-After fault");
    }
    {
        Gate gate;uint64_t tickets[MaxActiveCalls]{};
        for(unsigned i=0;i<MaxActiveCalls;++i)tickets[i]=Gate::Before(&gate,i);
        const auto overflow=Gate::Before(&gate,1000);
        Check(!overflow && gate.Faulted() && gate.Inspect().activeCalls==MaxActiveCalls,"bounded ticket exhaustion cannot wrap active count or reopen admission");
        for(unsigned i=0;i<MaxActiveCalls;++i)Gate::After(&gate,i,tickets[i],true,true);
        Check(!gate.Inspect().activeCalls && gate.Faulted(),"draining exhausted gate cannot clear sticky fault");
    }
}
DWORD WINAPI Watchdog(void* finished) {
    if(WaitForSingleObject(static_cast<HANDLE>(finished),15000)!=WAIT_OBJECT_0) {
        std::printf("FAIL private test process deadlock watchdog\n");TerminateProcess(GetCurrentProcess(),4);
    }
    return 0;
}
}
int main() {
    HANDLE finished=Event();HANDLE watchdog=Start(Watchdog,finished);
    WriterFirstAndStaleResult();ReaderFirst();TwoNativeWorkers();NestedAndCompletionGap();ExceptionsAndReentry();TicketFaults();
    Check(heap_probe::allocations==0 && heap_probe::deallocations==0,"all measured held read intervals have zero C++ allocations and deallocations");
    SetEvent(finished);Join(watchdog);CloseHandle(finished);
    std::printf("MotionReadGateTests: %ld checks, %ld failures. Real private Windows threads/SRW/SEH; no game admission or bootstrap proof.\n",checks,failures);
    return failures?1:0;
}
#endif
