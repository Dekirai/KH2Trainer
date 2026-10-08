#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define KH2_STATUS_BREAKPOINT_TESTS
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../../src/KH2Trainer.Bridge/StatusBreakpointRouter.h"
#include "../../src/KH2Trainer.Bridge/StatusEntryPlan.h"
namespace {
using namespace status_breakpoint;
unsigned checks=0,failures=0;
void Check(bool okay,const char* name){++checks;if(!okay){++failures;printf("FAIL %s\n",name);}}
using Fn=uint64_t (__fastcall*)(uint64_t,uint64_t,uint64_t,uint64_t);
Fn originals[EntryCount]{};
volatile LONG calls[EntryCount]{};
volatile LONG originalCalls[EntryCount]{};
volatile LONG badResult=0;
template<unsigned N> __declspec(noinline) uint64_t __fastcall Hook(uint64_t a,uint64_t b,uint64_t c,uint64_t d) {
    InterlockedIncrement(&calls[N]);
    return originals[N](a,b,c,d)+0x100+N;
}
const Fn hooks[]={&Hook<0>,&Hook<1>,&Hook<2>,&Hook<3>,&Hook<4>};
// Four-argument leaf, no stack adjustment: RAX = RCX+RDX+R8+R9.
const unsigned char body[]={0x48,0x8b,0xc1,0x48,0x03,0xc2,0x49,0x03,0xc0,0x49,0x03,0xc1,0xc3,0x90,0x90,0x90};
struct Fixture {
    unsigned char* memory=nullptr;
    Candidate candidates[EntryCount]{};
    unsigned char expected[EntryCount][32]{};
    Router router;
    bool Setup() {
        memset(const_cast<LONG*>(calls),0,sizeof(calls));
        memset(const_cast<LONG*>(originalCalls),0,sizeof(originalCalls));badResult=0;
        memory=static_cast<unsigned char*>(VirtualAlloc(nullptr,8192,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
        if(!memory)return false;
        for(unsigned i=0;i<EntryCount;++i) {
            // MOV R10,counter; LOCK INC DWORD[R10], followed by the leaf.
            // Count actual original executions, including entries racing Commit.
            memset(expected[i],0x90,sizeof(expected[i]));expected[i][0]=0x49;expected[i][1]=0xba;
            const uintptr_t counter=reinterpret_cast<uintptr_t>(&originalCalls[i]);
            memcpy(expected[i]+2,&counter,8);
            const unsigned char increment[]={0xf0,0x41,0xff,0x02};
            memcpy(expected[i]+10,increment,4);memcpy(expected[i]+14,body,sizeof(body));
            memcpy(memory+i*128,expected[i],sizeof(expected[i]));
            memcpy(memory+4096+i*128,expected[i],sizeof(expected[i]));
            originals[i]=reinterpret_cast<Fn>(memory+4096+i*128);
            candidates[i]={reinterpret_cast<uintptr_t>(memory+i*128),reinterpret_cast<uintptr_t>(hooks[i]),expected[i],sizeof(expected[i])};
        }
        DWORD old=0;
        return VirtualProtect(memory,8192,PAGE_EXECUTE_READ,&old) && FlushInstructionCache(GetCurrentProcess(),memory,8192);
    }
    uint64_t Call(unsigned i) {
        return reinterpret_cast<Fn>(candidates[i].entry)(0x1111222233334444ull,0x123456789ull,0xabcdef012ull,0x9988ull);
    }
    static constexpr uint64_t Sum=0x1111222233334444ull+0x123456789ull+0xabcdef012ull+0x9988ull;
    void Dispose() {
        Check(router.TestRemoveAfterJoin(),"test-only teardown after joined callers");
        if(memory){Check(VirtualFree(memory,0,MEM_RELEASE)!=FALSE,"release isolated code");memory=nullptr;}
    }
};
void WriteByte(uintptr_t address,unsigned char value) {
    DWORD old=0,unused=0;
    Check(VirtualProtect(reinterpret_cast<void*>(address),1,PAGE_EXECUTE_READWRITE,&old)!=FALSE,"fixture writable");
    *reinterpret_cast<unsigned char*>(address)=value;
    Check(VirtualProtect(reinterpret_cast<void*>(address),1,old,&unused)!=FALSE,"fixture RX restored");
    Check(FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(address),1)!=FALSE,"fixture cache flushed");
}
DWORD WINAPI Worker(void* value) {
    auto* f=static_cast<Fixture*>(value);
    for(unsigned repeat=0;repeat<200;++repeat)for(unsigned i=0;i<EntryCount;++i)
        if(f->Call(i)!=Fixture::Sum+0x100+i)InterlockedExchange(&badResult,1);
    return 0;
}
void Dispatch() {
    Fixture f;Check(f.Setup(),"allocate executable private fixture");if(!f.memory)return;
    for(unsigned i=0;i<EntryCount;++i)Check(f.Call(i)==Fixture::Sum,"baseline leaf preserves all four full-width arguments");
    Check(f.router.Prepare(f.candidates)==Error::None,"prepare exact fixture");
    Check(f.router.Status()==State::Prepared && f.router.PatchedMask()==0,"prepare performs no code write");
    Check(f.router.Commit()==Error::None,"real Windows VEH and one-byte gates commit");
    Check(f.router.Verify() && f.router.PatchedMask()==31,"all bodies retain exact tails and breakpoints");
    for(unsigned i=0;i<EntryCount;++i) {
        Check(*reinterpret_cast<unsigned char*>(f.candidates[i].entry)==0xcc,"only entry byte changed");
        Check(!memcmp(reinterpret_cast<void*>(f.candidates[i].entry+1),f.expected[i]+1,sizeof(f.expected[i])-1),"every remaining instruction byte unchanged");
        Check(f.Call(i)==Fixture::Sum+0x100+i && calls[i]==1,"real trap redirects to typed wrapper and original exactly once");
    }
    HANDLE workers[4]{};
    for(auto& h:workers){h=CreateThread(nullptr,0,&Worker,&f,0,nullptr);Check(h!=nullptr,"start concurrent private callers");}
    for(auto h:workers)if(h){Check(WaitForSingleObject(h,30000)==WAIT_OBJECT_0,"all private callers joined");CloseHandle(h);}
    Check(!badResult,"concurrent traps preserve independent call arguments/returns");
    for(unsigned i=0;i<EntryCount;++i) {
        Check(calls[i]==801,"all concurrent wrappers invoked exactly once");
        Check(originalCalls[i]==802,"actual leaf executes once per baseline/wrapped call");
    }
    EXCEPTION_RECORD record{};CONTEXT context{},before{};EXCEPTION_POINTERS pointers{&record,&context};
    memset(&context,0x5a,sizeof(context));context.ContextFlags=CONTEXT_ALL;
    record.ExceptionCode=EXCEPTION_BREAKPOINT;record.ExceptionAddress=reinterpret_cast<void*>(f.candidates[2].entry);
    context.Rip=f.candidates[2].entry;before=context;
    Check(Router::TestHandle(&pointers)==EXCEPTION_CONTINUE_EXECUTION,"exact owned breakpoint handled");
    Check(context.Rip==f.candidates[2].target,"only target RIP chosen");context.Rip=before.Rip;
    Check(!memcmp(&context,&before,sizeof(context)),"all other integer/vector/flags/context state untouched");
    for(unsigned mode=0;mode<5;++mode) {
        context=before;record.ExceptionCode=EXCEPTION_BREAKPOINT;record.ExceptionFlags=0;
        record.ExceptionAddress=reinterpret_cast<void*>(f.candidates[2].entry);
        if(mode==0)record.ExceptionCode=EXCEPTION_ACCESS_VIOLATION;
        if(mode==1)record.ExceptionFlags=EXCEPTION_NONCONTINUABLE;
        if(mode==2)context.Rip++;
        if(mode==3)record.ExceptionAddress=reinterpret_cast<void*>(f.candidates[2].entry+1);
        if(mode==4)context.ContextFlags=CONTEXT_INTEGER;
        const CONTEXT expected=context;
        Check(Router::TestHandle(&pointers)==EXCEPTION_CONTINUE_SEARCH,"foreign or inconsistent exceptions are not consumed");
        Check(!memcmp(&context,&expected,sizeof(context)),"foreign context unchanged");
    }
    Check(Router::TestHandle(nullptr)==EXCEPTION_CONTINUE_SEARCH,"null exception ignored");
    WriteByte(f.candidates[3].entry+31,0x91);
    Check(!f.router.Verify() && f.router.Status()==State::Fault,"tail mutation permanently faults confidence");
    WriteByte(f.candidates[3].entry+31,0x90);
    Check(!f.router.Verify(),"restoring bytes does not erase an observation gap");
    Check(f.Call(0)==Fixture::Sum+0x100,"faulted resident router still forwards old entry");
    f.Dispose();
}
struct ConcurrentInstall {
    Fixture* fixture;
    HANDLE started=nullptr;
    volatile LONG ready=0,stop=0,total[EntryCount]{};
};
DWORD WINAPI InstallingWorker(void* argument) {
    auto& s=*static_cast<ConcurrentInstall*>(argument);bool first=true;
    while(!InterlockedCompareExchange(&s.stop,0,0)) {
        for(unsigned i=0;i<EntryCount;++i) {
            const uint64_t result=s.fixture->Call(i);
            if(result!=Fixture::Sum && result!=Fixture::Sum+0x100+i)InterlockedExchange(&badResult,1);
            InterlockedIncrement(&s.total[i]);
        }
        if(first) { first=false;if(InterlockedIncrement(&s.ready)==4)SetEvent(s.started); }
    }
    return 0;
}
void LivePublication() {
    Fixture f;Check(f.Setup(),"concurrent publication private fixture");if(!f.memory)return;
    Check(f.router.Prepare(f.candidates)==Error::None,"prepare without stopping original callers");
    ConcurrentInstall s{&f};s.started=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    Check(s.started!=nullptr,"publication start event");if(!s.started){f.Dispose();return;}
    HANDLE threads[4]{};
    for(auto& h:threads){h=CreateThread(nullptr,0,&InstallingWorker,&s,0,nullptr);Check(h!=nullptr,"original callers start before Commit");}
    Check(WaitForSingleObject(s.started,5000)==WAIT_OBJECT_0,"all four threads have executed old originals");
    Check(f.router.Commit()==Error::None,"publish single-byte gates while old originals execute");
    const DWORD started=GetTickCount();
    while(InterlockedCompareExchange(&calls[4],0,0)<1000 && GetTickCount()-started<5000)SwitchToThread();
    InterlockedExchange(&s.stop,1);
    for(auto h:threads)if(h){Check(WaitForSingleObject(h,10000)==WAIT_OBJECT_0,"publication caller joined");CloseHandle(h);}
    Check(!badResult && f.router.Verify(),"every racing result is intact original or wrapper result");
    for(unsigned i=0;i<EntryCount;++i) {
        Check(s.total[i]>=4 && calls[i]>0 && calls[i]<=s.total[i],"both publication phases executed");
        Check(originalCalls[i]==s.total[i],"no racing original call duplicated or lost");
        Check(!memcmp(reinterpret_cast<void*>(f.candidates[i].entry+1),f.expected[i]+1,sizeof(f.expected[i])-1),"concurrent publication preserves complete instruction tails");
    }
    CloseHandle(s.started);f.Dispose();
}
void CandidateFailures() {
    for(unsigned mode=0;mode<9;++mode) {
        Fixture f;Check(f.Setup(),"rejection fixture");if(!f.memory)return;
        if(mode==0)f.candidates[0].size=0;
        if(mode==1)f.candidates[0].size=MaxBody+1;
        if(mode==2)f.candidates[0].entry=UINTPTR_MAX-1;
        if(mode==3)f.candidates[0].original=nullptr;
        if(mode==4)f.candidates[0].target=f.candidates[1].entry;
        if(mode==5)f.candidates[1].entry=f.candidates[0].entry+1;
        if(mode==6)f.candidates[0].target=reinterpret_cast<uintptr_t>(f.memory+4096);
        if(mode==7)WriteByte(f.candidates[2].entry+1,0x90);
        if(mode==8)f.router.testDebugger=true;
        Check(f.router.Prepare(f.candidates)!=Error::None,"invalid candidate rejected");
        Check(f.router.PatchedMask()==0 && f.router.Status()==State::Fault,"prepare failure cannot publish any gate");
        f.Dispose();
    }
    Fixture f;Check(f.Setup(),"post-prepare debugger fixture");if(!f.memory)return;
    Check(f.router.Prepare(f.candidates)==Error::None,"prepare before debugger appears");f.router.testDebugger=true;
    Check(f.router.Commit()==Error::Debugger && f.router.PatchedMask()==0,"debugger at commit blocks all patches");f.Dispose();
}
void ChangeBeforeCas(uintptr_t address){*reinterpret_cast<unsigned char*>(address)=0xc3;}
void PartialFailures() {
    for(unsigned mode=0;mode<4;++mode)for(unsigned i=0;i<EntryCount;++i) {
        Fixture f;Check(f.Setup(),"partial publication fixture");if(!f.memory)return;
        Check(f.router.Prepare(f.candidates)==Error::None,"prepare partial publication");
        if(mode==0)f.router.testProtectFailure=static_cast<int>(i);
        if(mode==1)f.router.testRestoreFailure=static_cast<int>(i);
        if(mode==2)f.router.testFlushFailure=static_cast<int>(i);
        if(mode==3){f.router.testBeforeCasIndex=i;f.router.testBeforeCas=&ChangeBeforeCas;}
        Check(f.router.Commit()!=Error::None && f.router.Status()==State::Fault,"publication failure permanently faults confidence");
        const unsigned count=(mode==1 || mode==2)?i+1:i;
        Check(f.router.PatchedMask()==((1u<<count)-1),"exact partial ownership mask retained");
        for(unsigned j=0;j<count;++j)Check(f.Call(j)==Fixture::Sum+0x100+j,"partially published gate still forwards");
        if(mode==3)Check(*reinterpret_cast<unsigned char*>(f.candidates[i].entry)==0xc3,"CAS preserves concurrent foreign byte");
        Check(!f.router.Verify(),"partial installation cannot claim complete observation");
        f.Dispose();
    }
}
void Planner() {
    using namespace status_entry_plan;
    for(unsigned i=0;i<static_cast<unsigned>(Kind::Count);++i) {
        const auto kind=static_cast<Kind>(i);const auto* d=Get(kind);Plan jump{},trap{};
        Check(Build(kind,0x140000000,d->original,d->originalSize,0x160000000,0x140500000,jump)==status_entry_plan::Error::None,"existing relative plan retained");
        Check(BuildBreakpoint(kind,0x140000000,d->original,d->originalSize,0x160000000,trap)==status_entry_plan::Error::None,"breakpoint plan prepared");
        Check(trap.patchSize==1 && trap.entryPatch[0]==0xcc && trap.relay==0,"breakpoint plan changes exactly one byte");
        Check(jump.patchSize==jump.prefixSize,"relative plan retains full prefix patch size");
        Check(!memcmp(jump.image,trap.image,ImageSize),"both modes use identical verified original/unwind image");
        for(unsigned j=1;j<sizeof(trap.entryPatch);++j)Check(trap.entryPatch[j]==0,"no breakpoint tail bytes proposed");
        Plan before=trap;
        Check(BuildBreakpoint(kind,0x140000000,d->original,d->originalSize,0x160000001,trap)==status_entry_plan::Error::InvalidAddress,"unaligned trampoline rejected");
        Check(!memcmp(&before,&trap,sizeof(trap)),"failed breakpoint planning preserves output");
    }
}
}
int main() {
    Planner();CandidateFailures();Dispatch();LivePublication();PartialFailures();
    printf("StatusBreakpointTests: %u checks, %u failures. Private code and real Windows VEH only.\n",checks,failures);
    return failures?1:0;
}
