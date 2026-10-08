#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define KH2_STATUS_THREAD_DRAIN_TESTS
#include <windows.h>
#include <stdio.h>
#include "../../src/KH2Trainer.Bridge/StatusThreadDrain.h"
namespace {
using namespace status_thread_drain;
unsigned checks=0,failures=0;
void Check(bool okay,const char* name) {++checks;if(!okay){++failures;printf("FAIL %s\n",name);}}
Range syntheticRoots[RootCount]={{0x140001000,0x140001020},{0x140002000,0x140002050},
    {0x140003000,0x140003100},{0x140004000,0x140004010},{0x140005000,0x140005030}};
void PureScans() {
    Snapshot s{};Check(s.Allocate(4096),"allocate isolated stack storage");if(!s.bytes)return;
    s.context.ContextFlags=CONTEXT_FULL;s.context.Rip=0x140000050;s.context.Rsp=0x500000;
    s.low=s.context.Rsp;s.high=s.low+512;s.size=512;s.complete=true;
    Check(Inspect(s,syntheticRoots)==Scan::Clear,"entire clean copied stack accepted");
    for(unsigned r=0;r<RootCount;++r) {
        for(uintptr_t pc=syntheticRoots[r].begin;pc<syntheticRoots[r].end;++pc) {
            s.context.Rip=pc;Check(Inspect(s,syntheticRoots)==Scan::PotentialWriter,"every original instruction byte defers");
        }
        s.context.Rip=0x140000050;
        for(unsigned slot=0;slot<64;++slot) {
            const uintptr_t pc=syntheticRoots[r].begin+1;
            memcpy(s.bytes+8*slot,&pc,8);
            Check(Inspect(s,syntheticRoots)==Scan::PotentialWriter,"root continuation at every stack slot defers");
            memset(s.bytes+8*slot,0,8);
        }
        const uintptr_t end=syntheticRoots[r].end;memcpy(s.bytes,&end,8);
        Check(Inspect(s,syntheticRoots)==Scan::Clear,"one-past-body pointer is not a root continuation");memset(s.bytes,0,8);
    }
    s.complete=false;Check(Inspect(s,syntheticRoots)==Scan::Unknown,"incomplete copy cannot be clean");s.complete=true;
    --s.size;Check(Inspect(s,syntheticRoots)==Scan::Unknown,"short copy cannot be clean");++s.size;
    s.context.ContextFlags=CONTEXT_CONTROL;Check(Inspect(s,syntheticRoots)==Scan::Unknown,"partial context rejected");s.context.ContextFlags=CONTEXT_FULL;
    ++s.context.Rsp;Check(Inspect(s,syntheticRoots)==Scan::Unknown,"mismatched stack position rejected");--s.context.Rsp;
    ++s.low;++s.context.Rsp;++s.high;Check(Inspect(s,syntheticRoots)==Scan::Unknown,"unaligned active stack rejected");--s.low;--s.context.Rsp;--s.high;
    const size_t capacity=s.capacity;s.capacity=1;Check(Inspect(s,syntheticRoots)==Scan::Unknown,"over-capacity copy rejected");s.capacity=capacity;
    Range bad[RootCount];memcpy(bad,syntheticRoots,sizeof(bad));bad[1]=bad[0];
    Check(Inspect(s,bad)==Scan::Unknown,"overlapping writer definitions rejected");
    s.Free();Check(Inspect(s,syntheticRoots)==Scan::Unknown,"released snapshot cannot be reused");
}

HANDLE entered=nullptr,releaseWriter=nullptr;
volatile LONG iterations=0;
volatile LONG afterWriter=0,releaseOuter=0;
__declspec(noinline) void WriterHelper() {
    SetEvent(entered);
    WaitForSingleObject(releaseWriter,INFINITE);
    InterlockedIncrement(&iterations);
}
__declspec(noinline) DWORD OldWriter() {
    WriterHelper();
    // An observable operation prevents replacing this call with a tail jump.
    return static_cast<DWORD>(InterlockedIncrement(&iterations));
}
DWORD WINAPI Worker(void*) {
    const DWORD result=OldWriter();
    InterlockedExchange(&afterWriter,1);
    while(!InterlockedCompareExchange(&releaseOuter,0,0))YieldProcessor();
    return result;
}
Range realRoots[RootCount]{};
// Keep writer address construction off the captured caller's active stack.
__declspec(noinline) bool BuildRealRoots() {
    DWORD64 base=0;auto* fn=RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(&OldWriter),&base,nullptr);
    if(!fn)return false;
    realRoots[0]={base+fn->BeginAddress,base+fn->EndAddress};
    for(unsigned i=1;i<RootCount;++i)realRoots[i]=syntheticRoots[i];
    return ValidRoots(realRoots);
}
void Join(HANDLE thread) {
    SetEvent(releaseWriter);
    InterlockedExchange(&releaseOuter,1);
    if(WaitForSingleObject(thread,10000)!=WAIT_OBJECT_0) {
        // Never free storage/handles under a still-running test caller.
        printf("FATAL own worker did not exit\n");ExitProcess(90);
    }
    CloseHandle(thread);
}
HANDLE Start(DWORD& id) {
    ResetEvent(entered);ResetEvent(releaseWriter);iterations=0;afterWriter=0;releaseOuter=0;
    HANDLE thread=CreateThread(nullptr,0,Worker,nullptr,0,&id);
    Check(thread!=nullptr,"start own native test worker");
    if(thread && WaitForSingleObject(entered,10000)!=WAIT_OBJECT_0) {printf("FATAL own worker not ready\n");ExitProcess(91);}
    return thread;
}
void RealCaptures() {
    Check(BuildRealRoots(),"own writer has static native unwind extent");
    Snapshot s{};Check(s.Allocate(),"preallocate touched remote stack storage");
    DWORD id=0;HANDLE thread=Start(id);if(!thread){s.Free();return;}
    const auto query=ResolveQuery();const uintptr_t teb=QueryTeb(query,thread,id);
    Check(teb!=0,"retained handle resolves own worker TEB");ResumeDebt debt{};
    Check(CaptureRemote(thread,id,teb,s,debt)==Capture::Complete,"capture and resume real blocked worker");
    Check(!debt.owed && debt.lastCount==1,"exactly one owned suspension removed");
    Check(Inspect(s,realRoots)==Scan::PotentialWriter,"deeper Windows wait leaves original writer continuation");
    Check(iterations==0,"observation does not release native wait");
    const auto hashSample=*reinterpret_cast<const uintptr_t*>(s.bytes+s.size-8);
    SetEvent(releaseWriter);
    for(unsigned i=0;i<10000 && !InterlockedCompareExchange(&afterWriter,0,0);++i)Sleep(1);
    Check(afterWriter==1 && WaitForSingleObject(thread,0)==WAIT_TIMEOUT,"writer returns while retained thread stays alive");
    Check(Inspect(s,realRoots)==Scan::PotentialWriter,"frozen stack retains prior writer after it returns");
    Check(*reinterpret_cast<const uintptr_t*>(s.bytes+s.size-8)==hashSample,"snapshot owns unchanged bytes");
    Check(CaptureRemote(thread,id,teb,s,debt)==Capture::Complete && Inspect(s,realRoots)==Scan::Clear,
        "fresh full stack proves a live thread drained after root return");
    InterlockedExchange(&releaseOuter,1);
    if(WaitForSingleObject(thread,10000)!=WAIT_OBJECT_0){printf("FATAL own drained worker did not exit\n");ExitProcess(92);}
    Check(CaptureRemote(thread,id,teb,s,debt)==Capture::Exited && !s.complete,"signaled retained handle proves thread ended");
    CloseHandle(thread);
    Check(CaptureRemote(thread,id,teb,s,debt)==Capture::Unavailable,"closed handle cannot reuse old observation");

    thread=Start(id);if(!thread){s.Free();return;}
    const uintptr_t teb2=QueryTeb(query,thread,id);
    const size_t capacity=s.capacity;s.capacity=1;
    Check(CaptureRemote(thread,id,teb2,s,debt)==Capture::TooLarge && !debt.owed,"oversize stack defers and resumes");s.capacity=capacity;
    Check(Inspect(s,realRoots)==Scan::Unknown,"oversize never reuses prior clean snapshot");
    Check(CaptureRemote(thread,id,1,s,debt)==Capture::Unavailable && !debt.owed,"invalid TIB read still resumes");
    Check(CaptureRemote(thread,id+1,teb2,s,debt)==Capture::Unavailable,"wrong handle identity rejected before suspension");
    Check(CaptureRemote(GetCurrentThread(),id,teb2,s,debt)==Capture::Unavailable,"self handle cannot be disguised as remote");
    Check(SuspendThread(thread)==0,"test owns an external suspension");
    Check(CaptureRemote(thread,id,teb2,s,debt)==Capture::ExternalSuspend && !debt.owed,"preexisting suspension remains unresolved");
    Check(ResumeThread(thread)==1,"capture preserved external suspend count");
    debt.testResumeFailures=1;
    Check(CaptureRemote(thread,id,teb2,s,debt)==Capture::ResumeFailed && debt.owed && !s.complete,"failed resume retains debt and invalidates snapshot");
    Check(debt.Retry() && !debt.owed && debt.lastCount==1,"resume debt repaid before cleanup");
    Join(thread);
    const auto current=CaptureCurrent(s);const auto currentScan=Inspect(s,syntheticRoots);
    if(current!=Capture::Complete || currentScan==Scan::Unknown)
        printf("current capture=%u scan=%u flags=%lx bytes=%llu rsp=%llx low=%llx high=%llx\n",
            unsigned(current),unsigned(currentScan),s.context.ContextFlags,static_cast<unsigned long long>(s.size),
            s.context.Rsp,static_cast<unsigned long long>(s.low),static_cast<unsigned long long>(s.high));
    Check(current==Capture::Complete && currentScan!=Scan::Unknown,"current thread copied completely without self suspension");
    bool witness=false;
    if(currentScan==Scan::PotentialWriter) {
        for(size_t offset=0;offset<s.size;offset+=8) {
            uintptr_t value=0;memcpy(&value,s.bytes+offset,8);
            for(const auto& root:syntheticRoots)witness=witness || Contains(root,value);
        }
    }
    Check(currentScan!=Scan::PotentialWriter || witness,"an incidental current-stack pointer remains conservatively deferred");
    s.Free();
}
bool gatesOkay=true;
bool Gates(void*) noexcept {return gatesOkay;}
Drain session{}; // Process-lifetime metadata must not add root pointers to stack.
Drain debtSession{};
void DrainResumeDebt() {
    Check(!debtSession.ResumePending(),"unstarted drain has no resume debt");
    DWORD id=0;HANDLE thread=Start(id);if(!thread)return;
    gatesOkay=true;Check(debtSession.Begin(realRoots,Gates,nullptr),"begin retained debt test");
    debtSession.TestFailNextResumes(2);
    for(unsigned i=0;i<100 && debtSession.Status()!=Phase::Fault;++i)debtSession.Poll(1);
    Check(debtSession.Status()==Phase::Fault && debtSession.ResumePending(),"failed capture reports pending resume before any metadata lock may be entered");
    debtSession.Poll(1);
    Check(debtSession.Status()==Phase::Fault && debtSession.ResumePending(),"fault-state poll retains still-failed resume debt");
    debtSession.Poll(1);
    Check(debtSession.Status()==Phase::Fault && !debtSession.ResumePending(),"later fault-state poll repays debt without restoring confidence");
    if(debtSession.ResumePending()){printf("FATAL own test resume remains pending\n");ExitProcess(93);}
    Join(thread);
    Check(debtSession.Close(),"debt-free fault can release retained handles");
}
void WholeDrain() {
    DWORD id=0;HANDLE thread=Start(id);if(!thread)return;
    gatesOkay=true;Check(session.Begin(realRoots,Gates,nullptr),"capture old thread handle set after published gate witness");
    Check(!session.Ready(),"begin alone does not prove writer drain");
    bool observedWriter=false,prematureReady=false;
    for(unsigned i=0;i<100 && !observedWriter;++i) {
        const auto p=session.Poll(1);
        observedWriter=p.thread==id && p.scan==Scan::PotentialWriter;
        prematureReady=prematureReady || p.phase==Phase::Drained;
    }
    Check(!prematureReady,"waiting old writer prevents bootstrap");
    Check(observedWriter,"retained-set polling observes blocked old writer");
    Join(thread);
    bool ready=false;
    for(unsigned i=0;i<100 && !ready;++i) {
        session.Poll(MaxThreads);ready=session.Ready();
        if(!ready)Sleep(1);
    }
    Check(ready,"retained exited writer and complete other stacks drain");
    gatesOkay=false;Check(!session.Ready() && session.Status()==Phase::Fault,"lost gates permanently fault prior drain");
    gatesOkay=true;Check(!session.Ready(),"restoring gate bytes cannot reset uncertainty");
    Check(session.Close(),"explicit close releases retained handles after no resume debt");
    Check(!session.Begin(realRoots,Gates,nullptr),"closed instance cannot mint a fresh barrier");
}
}
int main() {
    entered=CreateEventW(nullptr,TRUE,FALSE,nullptr);releaseWriter=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    Check(entered && releaseWriter,"isolated test events allocated");
    PureScans();RealCaptures();WholeDrain();DrainResumeDebt();
    CloseHandle(entered);CloseHandle(releaseWriter);
    printf("StatusThreadDrainTests: %u checks, %u failures. Own process threads only.\n",checks,failures);
    return failures?1:0;
}
