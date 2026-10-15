#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#ifndef MOTION_BREAKPOINT_PRODUCTION_COMPILE
#define KH2_MOTION_BREAKPOINT_TESTS
#endif
#include "../../src/KH2Trainer.Bridge/MotionBreakpointRouter.h"
#include "../../src/KH2Trainer.Bridge/MotionOriginalTrampoline.h"
#include <stdio.h>
#include <string.h>

#ifdef MOTION_BREAKPOINT_PRODUCTION_COMPILE
motion_breakpoint::Error CompileMotionBreakpointRoute(motion_breakpoint::Router& router,
    uintptr_t module,motion_observer::OriginalFn target) noexcept {
    auto result=router.Prepare(module,target);
    if(result!=motion_breakpoint::Error::None)return result;
    result=router.Commit();if(result!=motion_breakpoint::Error::None)return result;
    return router.Verify() && router.Exposed() && router.Patched() && !router.RollbackFailed()
        ?motion_breakpoint::Error::None:motion_breakpoint::Error::Changed;
}
#else
namespace {
using namespace motion_breakpoint;
unsigned checks=0,failures=0;
void Check(bool okay,const char* label){++checks;if(!okay){++failures;printf("FAIL %s\n",label);}}
constexpr size_t ModuleSize=4*1024*1024;
constexpr DWORD InputError=0x43214321,OutputError=0x67896789,NativeException=0xe0424d31;
const auto& Def(){return *motion_entry_plan::Get(motion_entry_plan::Kind::NormalBind);}
uint32_t Bits(float value){uint32_t bits;memcpy(&bits,&value,4);return bits;}
float Float(uint32_t bits){float value;memcpy(&value,&bits,4);return value;}
LONG Read(const volatile LONG& value){return InterlockedCompareExchange(const_cast<volatile LONG*>(&value),0,0);}
struct Calls {
    motion_observer::OriginalFn entry=nullptr;
    volatile LONG before=0,original=0,after=0,bad=0,total=0;
};
struct Frame {
    Calls* owner;
    uintptr_t controller=0xfedcba9876543210ull;
    int32_t selection=INT32_MIN;
    uint32_t blend=0x80000000,frame=0x7fc12345;
    bool throws=false;
    unsigned before=0,original=0,after=0;
};
thread_local Frame* current=nullptr;
void Require(bool okay){if(!okay && current)InterlockedExchange(&current->owner->bad,1);}
uint64_t __fastcall Before(void* owner,uintptr_t controller) {
    auto& f=*current;Require(owner==f.owner && controller==f.controller && !f.before && !f.original && !f.after);
    Require(GetLastError()==InputError);++f.before;InterlockedIncrement(&f.owner->before);
    SetLastError(0x11112222);return reinterpret_cast<uintptr_t>(&f);
}
__declspec(noinline) uint8_t __fastcall Original(uintptr_t controller,int32_t selection,float blend,float frame) {
    auto& f=*current;Require(controller==f.controller && selection==f.selection && Bits(blend)==f.blend && Bits(frame)==f.frame);
    Require(GetLastError()==InputError && !f.original && !f.after);++f.original;InterlockedIncrement(&f.owner->original);
    SetLastError(OutputError);if(f.throws)RaiseException(NativeException,0,0,nullptr);
    return 0xa7;
}
void __fastcall After(void* owner,uintptr_t controller,uint64_t ticket,bool entered,bool normal) {
    auto& f=*current;Require(owner==f.owner && controller==f.controller && ticket==reinterpret_cast<uintptr_t>(&f));
    Require(f.before==1 && f.original==1 && !f.after && entered && normal==!f.throws && GetLastError()==OutputError);
    ++f.after;InterlockedIncrement(&f.owner->after);SetLastError(0x33334444);
}
uint8_t Invoke(Calls& owner,bool throws=false) {
    Frame frame{&owner};frame.throws=throws;Frame* prior=current;current=&frame;SetLastError(InputError);
    __try {
        const uint8_t value=owner.entry(frame.controller,frame.selection,Float(frame.blend),Float(frame.frame));
        Require(value==0xa7 && frame.original==1 && frame.before==frame.after && GetLastError()==OutputError);
        InterlockedIncrement(&owner.total);return value;
    } __finally {current=prior;}
}
DWORD Catch(Calls& owner) {
    __try {Invoke(owner,true);}
    __except(EXCEPTION_EXECUTE_HANDLER) {return GetExceptionCode();}
    return 0;
}
void WriteByte(uintptr_t address,unsigned char byte) {
    DWORD old=0,unused=0;
    Check(VirtualProtect(reinterpret_cast<void*>(address),1,PAGE_EXECUTE_READWRITE,&old)!=FALSE,"fixture writable for deliberate mutation");
    *reinterpret_cast<unsigned char*>(address)=byte;
    Check(VirtualProtect(reinterpret_cast<void*>(address),1,old,&unused)!=FALSE,"fixture prior protection restored");
    Check(FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(address),1)!=FALSE,"fixture mutation flushed");
}
DWORD Protection(uintptr_t address) {
    MEMORY_BASIC_INFORMATION page{};return VirtualQuery(reinterpret_cast<void*>(address),&page,sizeof(page))==sizeof(page)?page.Protect:0;
}
template<unsigned Identity> struct Fixture : Calls {
    inline static motion_observer::Observer observer{};
    motion_original::Image originalImage;
    Router router;
    unsigned char* module=nullptr;
    unsigned char expected[BodySize]{};
    uintptr_t Address() const {return reinterpret_cast<uintptr_t>(module)+Def().rva;}
    static auto Target(){return &motion_observer::Entrypoints<observer>::Select;}
    bool Setup() {
        module=static_cast<unsigned char*>(VirtualAlloc(nullptr,ModuleSize,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
        Check(module!=nullptr,"allocate private source");if(!module)return false;
        memcpy(module+Def().rva,Def().original,BodySize);
        Check(originalImage.Prepare(reinterpret_cast<uintptr_t>(module)),"prepare real Motion original prefix and unwind image");
        motion_observer::OriginalFn native=nullptr;
        Check(originalImage.Bind(native) && native,"seal process-lifetime original image");if(!native)return false;
        // This test's explicit synthetic fingerprint preserves the retail five
        // byte prefix and substitutes only its continuation with a typed fixture.
        // Root's composed test separately executes the unchanged retail body.
        memcpy(expected,Def().original,BodySize);
        unsigned char jump[12]={0x48,0xb8};const uintptr_t target=reinterpret_cast<uintptr_t>(&Original);
        memcpy(jump+2,&target,8);jump[10]=0xff;jump[11]=0xe0;memcpy(expected+Def().prefixSize,jump,sizeof(jump));
        memcpy(module+Def().rva,expected,BodySize);DWORD old=0;
        Check(VirtualProtect(module,ModuleSize,PAGE_EXECUTE_READ,&old)!=FALSE,"private source is RX before prepare");
        Check(FlushInstructionCache(GetCurrentProcess(),module,ModuleSize)!=FALSE,"private source flushed");
        Check(observer.Bind(native,&Before,&After,this),"publish actual typed Observer entry binding");
        entry=reinterpret_cast<motion_observer::OriginalFn>(Address());router.testExpectedBody=expected;return true;
    }
    Error Prepare(){return router.Prepare(reinterpret_cast<uintptr_t>(module),Target());}
    void CloseAfterJoin() {
        Check(router.TestRemoveAfterJoin(),"test-only removal after no future or in-flight callers");
        // Fixture object is static; source, Observer and bound Image/unwind data
        // are retained until this isolated process exits. No production unload.
    }
};
void ContextDispatch(uintptr_t address,uintptr_t target) {
    EXCEPTION_RECORD record{};CONTEXT context{},prior{};EXCEPTION_POINTERS info{&record,&context};
    memset(&context,0x5a,sizeof(context));context.ContextFlags=CONTEXT_ALL;context.Rip=address;
    record.ExceptionCode=EXCEPTION_BREAKPOINT;record.ExceptionAddress=reinterpret_cast<void*>(address);prior=context;
    Check(Router::TestHandle(&info)==EXCEPTION_CONTINUE_EXECUTION && context.Rip==target,"owned exact exception routes to immutable target");
    context.Rip=prior.Rip;Check(!memcmp(&context,&prior,sizeof(context)),"RIP is the only modified context byte");
    for(unsigned mode=0;mode<5;++mode) {
        context=prior;record.ExceptionCode=EXCEPTION_BREAKPOINT;record.ExceptionFlags=0;record.ExceptionAddress=reinterpret_cast<void*>(address);
        if(mode==0)record.ExceptionCode=EXCEPTION_ACCESS_VIOLATION;
        if(mode==1)record.ExceptionFlags=EXCEPTION_NONCONTINUABLE;
        if(mode==2)context.Rip++;
        if(mode==3)record.ExceptionAddress=reinterpret_cast<void*>(address+1);
        if(mode==4)context.ContextFlags=CONTEXT_INTEGER;
        const CONTEXT before=context;
        Check(Router::TestHandle(&info)==EXCEPTION_CONTINUE_SEARCH,"foreign or inconsistent exception forwarded");
        Check(!memcmp(&context,&before,sizeof(context)),"foreign context left byte-identical");
    }
    Check(Router::TestHandle(nullptr)==EXCEPTION_CONTINUE_SEARCH,"null exception forwarded");
    info.ExceptionRecord=nullptr;Check(Router::TestHandle(&info)==EXCEPTION_CONTINUE_SEARCH,"missing exception record forwarded");
    info.ExceptionRecord=&record;info.ContextRecord=nullptr;Check(Router::TestHandle(&info)==EXCEPTION_CONTINUE_SEARCH,"missing context forwarded");
}
void Dispatch() {
    static Fixture<0> f;if(!f.Setup())return;
    Check(Invoke(f)==0xa7 && f.before==0 && f.original==1,"baseline calls private prefix without any wrapper");
    Check(f.Prepare()==Error::None && f.router.Status()==State::Prepared && !f.router.Exposed(),"prepare validates and publishes no breakpoint");
    Check(f.router.Commit()==Error::None && f.router.Verify(),"real Windows INT3/VEH route installs");
    Check(f.router.Exposed() && f.router.Patched() && !f.router.RollbackFailed(),"successful installation has exact exposure state");
    Check(f.Prepare()==Error::State && f.router.Commit()==Error::State && f.router.Verify(),"published route cannot be prepared or committed twice");
    static Fixture<2> contender;if(contender.Setup()) {
        Check(contender.Prepare()==Error::None,"independent contender has a valid private body");
        Check(contender.router.Commit()==Error::State && !contender.router.Exposed() && !contender.router.Patched(),"only one immutable active Motion route may be published");
        contender.CloseAfterJoin();
        Check(f.router.Verify(),"failed contender cannot clear another owner's active route");
    }
    Check(*reinterpret_cast<unsigned char*>(f.Address())==0xcc && !memcmp(reinterpret_cast<void*>(f.Address()+1),f.expected+1,BodySize-1),"only byte zero changed in whole fingerprint");
    Check(Protection(f.Address())==PAGE_EXECUTE_READ,"entry protection restored RX");
    Check(Invoke(f)==0xa7 && f.before==1 && f.original==2 && f.after==1 && !f.bad,"real trap traverses compiled typed entry and original trampoline once");
    Check(Catch(f)==NativeException && GetLastError()==OutputError && !f.bad,"native SEH crosses real trap, typed wrapper and registered original");
    Check(f.before==2 && f.original==3 && f.after==2 && Fixture<0>::observer.Faulted(),"native SEH finishes After once and faults Observer");
    ContextDispatch(f.Address(),reinterpret_cast<uintptr_t>(f.Target()));
    WriteByte(f.Address()+BodySize-1,0x90);
    Check(!f.router.Verify() && f.router.Status()==State::Fault,"complete-tail mutation faults integrity");
    WriteByte(f.Address()+BodySize-1,f.expected[BodySize-1]);
    Check(!f.router.Verify() && Invoke(f)==0xa7 && !f.bad,"fault is permanent but exposed entry still forwards");
    f.CloseAfterJoin();
}
struct Running {
    Calls* owner;HANDLE ready=nullptr;volatile LONG stop=0,started=0;
};
DWORD WINAPI Worker(void* argument) {
    auto& run=*static_cast<Running*>(argument);bool first=true;
    while(!Read(run.stop)) {
        Invoke(*run.owner);
        if(first){first=false;if(InterlockedIncrement(&run.started)==4)SetEvent(run.ready);}
    }
    return 0;
}
void LivePublication() {
    static Fixture<1> f;if(!f.Setup())return;Check(f.Prepare()==Error::None,"concurrent fixture prepared");
    Running run{&f};run.ready=CreateEventW(nullptr,TRUE,FALSE,nullptr);Check(run.ready!=nullptr,"concurrent start event");
    HANDLE workers[4]{};
    for(auto& thread:workers){thread=CreateThread(nullptr,0,&Worker,&run,0,nullptr);Check(thread!=nullptr,"start original caller before CAS");}
    Check(WaitForSingleObject(run.ready,5000)==WAIT_OBJECT_0 && Read(f.original)>=4,"all callers entered originals before commit");
    Check(f.router.Commit()==Error::None,"commit one byte while original callers run");
    const DWORD start=GetTickCount();while(Read(f.after)<100 && GetTickCount()-start<5000)SwitchToThread();
    InterlockedExchange(&run.stop,1);
    for(auto thread:workers)if(thread){Check(WaitForSingleObject(thread,10000)==WAIT_OBJECT_0,"caller joined before removal");CloseHandle(thread);}
    Check(!Read(f.bad) && Read(f.original)==Read(f.total),"no racing original duplicated or lost and mixed ABI stays exact");
    Check(Read(f.before)>0 && Read(f.before)==Read(f.after) && Read(f.before)<Read(f.total),"both plain and observed admissions executed");
    Check(f.router.Verify() && !memcmp(reinterpret_cast<void*>(f.Address()+1),f.expected+1,BodySize-1),"publication preserves entire instruction tail");
    CloseHandle(run.ready);f.CloseAfterJoin();
}
template<unsigned Mode> void Rejection() {
    static Fixture<10+Mode> f;if(!f.Setup())return;
    uintptr_t base=reinterpret_cast<uintptr_t>(f.module);auto target=f.Target();Error expected=Error::Memory;
    if constexpr(Mode==0){base=0;expected=Error::Candidate;}
    if constexpr(Mode==1){base=UINTPTR_MAX-1;expected=Error::Candidate;}
    if constexpr(Mode==2){target=nullptr;expected=Error::Candidate;}
    if constexpr(Mode==3)target=reinterpret_cast<motion_observer::OriginalFn>(f.Address()+5);
    if constexpr(Mode==4)f.router.testRequireImageSource=true;
    if constexpr(Mode==5){DWORD old=0;Check(VirtualProtect(f.module,ModuleSize,PAGE_EXECUTE_READWRITE,&old)!=FALSE,"deliberately writable source");}
    if constexpr(Mode==6){WriteByte(f.Address()+BodySize-1,0x90);expected=Error::Fingerprint;}
    if constexpr(Mode==7)base+=4096; // readable span, wrong AllocationBase identity.
    if constexpr(Mode==8)target=reinterpret_cast<motion_observer::OriginalFn>(f.module);
    if constexpr(Mode==9){f.expected[0]=0xcc;expected=Error::Fingerprint;}
    if constexpr(Mode==10)f.router.testExpectedBody=reinterpret_cast<unsigned char*>(1);
    if constexpr(Mode==11){f.router.testDebugger=true;expected=Error::Debugger;}
    if constexpr(Mode>=12){f.router.testFailPin=Mode-12;expected=Error::Pin;}
    Check(f.router.Prepare(base,target)==expected,"invalid candidate or unavailable module pin rejected precisely");
    Check(f.router.Status()==State::Fault && !f.router.Exposed() && !f.router.Patched(),"prepare rejection cannot expose a breakpoint");
    Check(f.router.Commit()==Error::State,"failed preparation cannot commit");f.CloseAfterJoin();
}
void ForeignByte(uintptr_t entry){*reinterpret_cast<unsigned char*>(entry)=0xc3;}
void ForeignTail(uintptr_t entry){*reinterpret_cast<unsigned char*>(entry+BodySize-1)=0x90;}
template<unsigned Mode> void PublicationFailure() {
    static Fixture<30+Mode> f;if(!f.Setup())return;Check(f.Prepare()==Error::None,"failure fixture prepared");
    Error expected=Error::Flush;
    if constexpr(Mode==0){f.router.testDebugger=true;expected=Error::Debugger;}
    if constexpr(Mode==1){WriteByte(f.Address()+BodySize-1,0x90);expected=Error::Fingerprint;}
    if constexpr(Mode==2){f.router.testFailHandler=true;expected=Error::Handler;}
    if constexpr(Mode==3){f.router.testProtectFailure=true;expected=Error::Protect;}
    if constexpr(Mode==4){f.router.testBeforeCas=&ForeignByte;expected=Error::Changed;}
    if constexpr(Mode==5){f.router.testRestoreFailure=true;expected=Error::RestoreProtection;}
    if constexpr(Mode>=6)f.router.testFlushFailure=true;
    if constexpr(Mode==7)f.router.testRollbackProtectFailure=true;
    if constexpr(Mode==8)f.router.testRollbackRestoreFailure=true;
    if constexpr(Mode==9)f.router.testRollbackFlushFailure=true;
    if constexpr(Mode==10)f.router.testAfterCas=&ForeignByte;
    if constexpr(Mode==11){f.router.testAfterCas=&ForeignTail;f.router.testFlushFailure=false;expected=Error::Changed;}
    Check(f.router.Commit()==expected && f.router.LastError()==expected && f.router.Status()==State::Fault,"publication failure retains primary reason and sticky Fault");
    Check(f.router.Exposed()==(Mode>=4),"exposure remains conservative across CAS and rollback");
    Check(f.router.RollbackFailed()==(Mode>=7 && Mode<=10),"rollback failures remain separately visible");
    const auto byte=*reinterpret_cast<unsigned char*>(f.Address());
    if constexpr(Mode==4 || Mode==10)Check(byte==0xc3,"foreign byte survives CAS and error rollback");
    else if constexpr(Mode==7) {
        Check(byte==0xcc && f.router.Patched(),"failed rollback leaves owned breakpoint and immutable route");
        Check(Invoke(f)==0xa7 && f.before==1 && f.original==1 && f.after==1 && !f.bad,"real entry still forwards after failed rollback");
    } else Check(byte==f.expected[0] && !f.router.Patched(),"unexposed or rolled back entry retains exact original first byte");
    if constexpr(Mode==8)Check(Protection(f.Address())==PAGE_EXECUTE_READWRITE,"unrepaired protection debt is observable");
    else Check(Protection(f.Address())==PAGE_EXECUTE_READ,"successful protection restoration leaves RX");
    if constexpr(Mode>=3)ContextDispatch(f.Address(),reinterpret_cast<uintptr_t>(f.Target()));
    if constexpr(Mode==4 || Mode==10)WriteByte(f.Address(),f.expected[0]);
    if constexpr(Mode==11)Check(*reinterpret_cast<unsigned char*>(f.Address()+BodySize-1)==0x90,"post-CAS full-body failure leaves foreign tail unchanged");
    f.CloseAfterJoin();
}
struct Delayed {
    Calls* calls=nullptr;uintptr_t entry=0;HANDLE trapped=nullptr,resume=nullptr,worker=nullptr;PVOID handler=nullptr;
    volatile LONG result=0;
};
Delayed delayed{};
LONG WINAPI DelayHandler(PEXCEPTION_POINTERS info) {
    if(!info || !info->ExceptionRecord || info->ExceptionRecord->ExceptionCode!=EXCEPTION_BREAKPOINT ||
        reinterpret_cast<uintptr_t>(info->ExceptionRecord->ExceptionAddress)!=delayed.entry)return EXCEPTION_CONTINUE_SEARCH;
    const DWORD last=GetLastError();SetEvent(delayed.trapped);WaitForSingleObject(delayed.resume,10000);SetLastError(last);
    return EXCEPTION_CONTINUE_SEARCH;
}
DWORD WINAPI DelayedWorker(void*) {InterlockedExchange(&delayed.result,Invoke(*delayed.calls)==0xa7?1:-1);return 0;}
void DelayAfterCas(uintptr_t entry) {
    delayed.entry=entry;delayed.handler=AddVectoredExceptionHandler(1,&DelayHandler);
    Check(delayed.handler!=nullptr,"front VEH delays a real already raised INT3");
    delayed.worker=CreateThread(nullptr,0,&DelayedWorker,nullptr,0,nullptr);
    Check(delayed.worker!=nullptr && WaitForSingleObject(delayed.trapped,5000)==WAIT_OBJECT_0,"entry exception waits before reaching resident router");
}
void DelayedExceptionAfterRollback() {
    static Fixture<50> f;if(!f.Setup())return;Check(f.Prepare()==Error::None,"delayed fixture prepared");
    delayed.calls=&f;delayed.trapped=CreateEventW(nullptr,TRUE,FALSE,nullptr);delayed.resume=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    Check(delayed.trapped && delayed.resume,"delayed test events created");
    f.router.testAfterCas=&DelayAfterCas;f.router.testFlushFailure=true;
    Check(f.router.Commit()==Error::Flush && f.router.Status()==State::Fault,"commit fails while an actual INT3 is pending");
    Check(f.router.Exposed() && !f.router.Patched() && !f.router.RollbackFailed() && *reinterpret_cast<unsigned char*>(f.Address())==f.expected[0],"byte rolled back before pending exception is released");
    SetEvent(delayed.resume);
    Check(WaitForSingleObject(delayed.worker,10000)==WAIT_OBJECT_0,"delayed real trap finishes after rollback");
    Check(Read(delayed.result)==1 && !f.bad && f.before==1 && f.original==1 && f.after==1,"retained Fault route forwards delayed INT3 through wrapper and original exactly once");
    Check(RemoveVectoredExceptionHandler(delayed.handler)!=0,"remove delay fixture after worker joined");
    CloseHandle(delayed.worker);CloseHandle(delayed.trapped);CloseHandle(delayed.resume);f.CloseAfterJoin();
}
}
int main() {
    Rejection<0>();Rejection<1>();Rejection<2>();Rejection<3>();Rejection<4>();Rejection<5>();Rejection<6>();Rejection<7>();
    Rejection<8>();Rejection<9>();Rejection<10>();Rejection<11>();Rejection<12>();Rejection<13>();Rejection<14>();
    Dispatch();LivePublication();
    PublicationFailure<0>();PublicationFailure<1>();PublicationFailure<2>();PublicationFailure<3>();PublicationFailure<4>();
    PublicationFailure<5>();PublicationFailure<6>();PublicationFailure<7>();PublicationFailure<8>();PublicationFailure<9>();PublicationFailure<10>();PublicationFailure<11>();
    DelayedExceptionAfterRollback();
    printf("MotionBreakpointRouterTests: %u checks, %u failures. Private INT3/VEH, typed wrapper and registered original prefix only.\n",checks,failures);
    return failures?1:0;
}
#endif
