#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#ifndef MOTION_RUNTIME_PRODUCTION_COMPILE
#define KH2_MOTION_RUNTIME_TESTS
#define KH2_MOTION_BREAKPOINT_TESTS
#define KH2_MOTION_ORIGINAL_TESTS
#endif
#include "../../src/KH2Trainer.Bridge/MotionObservationRuntime.h"
#include <stdio.h>
#include <string.h>

#ifdef MOTION_RUNTIME_PRODUCTION_COMPILE
struct ProductionMotionRuntime;
bool CompileMotionObservation(uintptr_t fixtureModule,DWORD owner,motion_observer::BeforeFn before,
                              motion_observer::AfterFn after,void* context) noexcept {
    using Runtime=motion_observation::Runtime<ProductionMotionRuntime>;
    if(!Runtime::Start(fixtureModule,owner,before,after,context))return false;
    return Runtime::Tick().phase==motion_observation::Phase::Installed;
}
#else
namespace motion_observation {
struct RuntimeTestAccess {
    template<class T> static auto& Original(){return T::original;}
    template<class T> static auto& Router(){return T::router;}
};
}
namespace {
using namespace motion_observation;
volatile LONG checks=0,failures=0;
void Check(bool okay,const char* label){InterlockedIncrement(&checks);if(!okay){InterlockedIncrement(&failures);printf("FAIL %s\n",label);}}
constexpr size_t ModuleSize=8*1024*1024;
constexpr DWORD InputError=0x21554321,OutputError=0x46213557,NativeException=0xe0424d72;
constexpr uintptr_t ModelBase=0x1234567800ULL;
const auto& Def(){return *motion_entry_plan::Get(motion_entry_plan::Kind::NormalBind);}
uint32_t Bits(float value){uint32_t bits;memcpy(&bits,&value,4);return bits;}
float Float(uint32_t bits){float value;memcpy(&value,&bits,4);return value;}
template<class T> T& Field(unsigned char* p,size_t offset){return *reinterpret_cast<T*>(p+offset);}
struct Call {
    alignas(16) unsigned char controller[512]{};
    uint32_t blend=0x80000000,frame=0x7fc12345;
    bool succeed=false,zeroBlend=false,raise=false,routed=true;
    unsigned before=0,group=0,bind=0,after=0,successHelper=0;
};
thread_local Call* active=nullptr;
unsigned char* fixtureModule=nullptr;
motion_observer::OriginalFn nativeEntry=nullptr;
struct RuntimeIdentity;
using ActiveRuntime=Runtime<RuntimeIdentity>;
unsigned contextMarker=0;

uint64_t __fastcall Before(void* context,uintptr_t controller) {
    auto& c=*active;
    Check(context==&contextMarker && controller==reinterpret_cast<uintptr_t>(c.controller),"Before receives immutable context and native controller");
    Check(!c.group && !c.bind && !c.after && Field<uintptr_t>(c.controller,328)==0xcccccccc,"Before precedes actual native context stores");
    Check(GetLastError()==InputError,"INT3 and Before preserve incoming LastError");
    ++c.before;SetLastError(1);return reinterpret_cast<uintptr_t>(&c);
}
uint8_t __fastcall GroupFixture(uintptr_t group) {
    auto& c=*active;
    Check(group==0 && c.before==unsigned(c.routed) && !c.group && !c.bind && !c.after,"first declared native callee follows Before");
    Check(GetLastError()==InputError,"Original starts with incoming LastError");
    ++c.group;return c.zeroBlend?1:0;
}
uint8_t __fastcall BindFixture(uintptr_t controller,uintptr_t resource,float blend,float frame) {
    auto& c=*active;
    Check(controller==reinterpret_cast<uintptr_t>(c.controller) && !resource,"real body selects null resource for negative selection");
    Check(c.group==1 && !c.bind && !c.after,"real body reaches declared bind callee once");
    Check(Bits(blend)==(c.zeroBlend?0:c.blend) && Bits(frame)==c.frame,"native body preserves frame and applies its actual blend branch");
    Check(Field<uintptr_t>(c.controller,328)==ModelBase+128 && !Field<uintptr_t>(c.controller,344) && !Field<uintptr_t>(c.controller,352),"real context stores execute before bind callee");
    ++c.bind;SetLastError(OutputError);
    if(c.raise)RaiseException(NativeException,0,0,nullptr);
    return c.succeed?1:0;
}
uint8_t __fastcall SuccessFixture(uintptr_t group) {
    auto& c=*active;
    Check(!group && c.succeed && c.bind==1 && !c.after,"third declared native callee is reached only on success");
    ++c.successHelper;return 0;
}
void __fastcall After(void* context,uintptr_t controller,uint64_t ticket,bool entered,bool normal) {
    auto& c=*active;
    Check(context==&contextMarker && controller==reinterpret_cast<uintptr_t>(c.controller) && ticket==reinterpret_cast<uintptr_t>(&c),"After receives invocation-local ticket");
    Check(entered && normal!=c.raise && c.before==1 && c.group==1 && c.bind==1 && !c.after,"After sees exact original completion path");
    Check(c.successHelper==unsigned(c.succeed && !c.raise),"success helper count reflects native branch");
    if(c.succeed && !c.raise)Check(Field<int32_t>(c.controller,44)==-1 && Field<int32_t>(c.controller,48)==-1,"native success stores signed selection and resolved value");
    Check(GetLastError()==OutputError,"After observes original outgoing LastError");
    ++c.after;SetLastError(2);
}
void Reset(Call& c) {
    memset(c.controller,0,sizeof(c.controller));
    Field<uintptr_t>(c.controller,16)=ModelBase;
    Field<uintptr_t>(c.controller,328)=0xcccccccc;
    Field<uintptr_t>(c.controller,344)=1;Field<uintptr_t>(c.controller,352)=2;
    Field<int32_t>(c.controller,44)=11;Field<int32_t>(c.controller,48)=12;
}
DWORD Invoke(Call& c) {
    Reset(c);Call* prior=active;active=&c;SetLastError(InputError);DWORD caught=0;
    __try {
        __try {
            const auto result=nativeEntry(reinterpret_cast<uintptr_t>(c.controller),-1,Float(c.blend),Float(c.frame));
            Check(result==uint8_t(c.succeed),"actual native AL0/AL1 survives full route");
        } __except(EXCEPTION_EXECUTE_HANDLER) {caught=GetExceptionCode();}
        Check(GetLastError()==OutputError,"full route preserves outgoing LastError through return or SEH");
    } __finally {active=prior;}
    Check(c.before==unsigned(c.routed) && c.after==unsigned(c.routed) && c.bind==1,"one callback pair and bind callee per invocation");
    return caught;
}
void Jump(unsigned char* destination,uintptr_t target) {
    unsigned char bytes[]={0x48,0xb8,0,0,0,0,0,0,0,0,0xff,0xe0};
    memcpy(bytes+2,&target,8);memcpy(destination,bytes,sizeof(bytes));
}
bool CreateSource() {
    fixtureModule=static_cast<unsigned char*>(VirtualAlloc(nullptr,ModuleSize,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(!fixtureModule)return false;
    memcpy(fixtureModule+Def().rva,Def().original,Def().originalSize);
    // The complete real Motion body stays byte-identical. Only its three
    // callees are declared fixture functions in this private source allocation.
    Jump(fixtureModule+0x40d7f0,reinterpret_cast<uintptr_t>(&GroupFixture));
    Jump(fixtureModule+0x3c8a40,reinterpret_cast<uintptr_t>(&BindFixture));
    Jump(fixtureModule+0x40d7d0,reinterpret_cast<uintptr_t>(&SuccessFixture));
    // Original PE unwind bytes from the independently verified 6E6434 record.
    const unsigned char unwind[]={1,0x22,0x0a,0,0x22,0x78,2,0,0x14,0x68,3,0,0x0f,0x64,0x0b,0,0x0f,0x34,0x0a,0,0x0f,0x72,0x0b,0x70};
    memcpy(fixtureModule+0x1000,unwind,sizeof(unwind));
    auto* table=reinterpret_cast<RUNTIME_FUNCTION*>(fixtureModule+0x1100);
    *table={static_cast<DWORD>(Def().rva),static_cast<DWORD>(Def().rva+Def().originalSize),0x1000};
    DWORD old=0;
    if(!VirtualProtect(fixtureModule,ModuleSize,PAGE_EXECUTE_READ,&old) || !FlushInstructionCache(GetCurrentProcess(),fixtureModule,ModuleSize) ||
       !RtlAddFunctionTable(table,1,reinterpret_cast<DWORD64>(fixtureModule)))return false;
    nativeEntry=reinterpret_cast<motion_observer::OriginalFn>(fixtureModule+Def().rva);
    return true;
}
void EarlyFailures() {
    struct BadSource;using Bad=Runtime<BadSource>;
    Check(!Bad::Start(1,GetCurrentThreadId(),Before,After,&contextMarker),"invalid fixtureModule cannot prepare an original image");
    Check(Bad::InspectOnOwner().phase==Phase::Fault && Bad::InspectOnOwner().error==Error::SourcePin,"source failure is permanent and classified");
    struct BadCallback;using Callback=Runtime<BadCallback>;
    Check(!Callback::Start(reinterpret_cast<uintptr_t>(fixtureModule),GetCurrentThreadId(),reinterpret_cast<motion_observer::BeforeFn>(1),After,&contextMarker),"unloaded callback cannot be pinned");
    Check(Callback::InspectOnOwner().error==Error::CallbackPin,"callback pin failure is distinct");
    struct FailedOriginal;using Original=Runtime<FailedOriginal>;
    auto& image=RuntimeTestAccess::Original<Original>();image.testFailAdd=true;image.testFailFree=true;
    Check(!Original::Start(reinterpret_cast<uintptr_t>(fixtureModule),GetCurrentThreadId(),Before,After,&contextMarker),"failed original registration cannot publish a route");
    Check(Original::InspectOnOwner().unpublishedCleanupPending && image.Entry()!=0,"failed prepublication free retains address for retry");
    image.testFailFree=false;
    Check(!Original::Tick().unpublishedCleanupPending && !image.Entry(),"owner tick retries unpublished cleanup");
    Check(fixtureModule[Def().rva]==Def().original[0],"early failures leave native entry untouched");
}
DWORD WINAPI Foreign(void*) {
    Check(ActiveRuntime::Tick().phase==Phase::Invalid && ActiveRuntime::InspectOnOwner().phase==Phase::Invalid,"foreign thread cannot access management state");
    Check(!ActiveRuntime::Start(reinterpret_cast<uintptr_t>(fixtureModule),GetCurrentThreadId(),Before,After,&contextMarker),"foreign thread cannot rebind singleton");
    Call c{};c.succeed=true;c.zeroBlend=true;c.blend=0xffc12345;
    Check(!Invoke(c),"native call on another thread still forwards through immutable route");
    return 0;
}
void InstalledRoute() {
    const auto base=reinterpret_cast<uintptr_t>(fixtureModule);
    Check(!ActiveRuntime::Start(base,0,Before,After,&contextMarker),"zero owner rejected before singleton claim");
    Check(!ActiveRuntime::Start(base,GetCurrentThreadId(),nullptr,After,&contextMarker),"missing callback rejected before singleton claim");
    Call unobserved{};unobserved.routed=false;
    Check(!Invoke(unobserved),"original call before publication is explicitly unobserved");
    Check(ActiveRuntime::Start(base,GetCurrentThreadId(),Before,After,&contextMarker),"real image, observer and one-byte route install together");
    auto state=ActiveRuntime::Tick();
    Check(state.phase==Phase::Installed && state.exposed && state.patched && !state.rollbackFailed && !state.observerFault,"installed state reports actual route without claiming drained history");
    Check(fixtureModule[Def().rva]==0xcc && !memcmp(fixtureModule+Def().rva+1,Def().original+1,Def().originalSize-1),"only original byte zero changes; entire native continuation is intact");
    Check(!ActiveRuntime::Start(base,GetCurrentThreadId(),Before,After,&contextMarker),"owner cannot replace immutable binding");
    const uint32_t patterns[]={0,0x80000000,1,0x7f800000,0xff800000,0x7fc12345,0x7f812345,0x3f123456};
    for(unsigned i=0;i<8;++i)for(unsigned branch=0;branch<4;++branch) {
        Call c{};c.blend=patterns[i];c.frame=patterns[7-i];c.succeed=(branch&1)!=0;c.zeroBlend=(branch&2)!=0;
        Check(!Invoke(c),"full native failure/success and blend branches return normally");
    }
    HANDLE worker=CreateThread(nullptr,0,Foreign,nullptr,0,nullptr);
    Check(worker!=nullptr,"foreign caller created");
    if(worker){Check(WaitForSingleObject(worker,10000)==WAIT_OBJECT_0,"foreign caller joined");CloseHandle(worker);}
    Call failed{};failed.raise=true;
    Check(Invoke(failed)==NativeException,"exception from fixture callee unwinds actual original body and typed wrapper");
    state=ActiveRuntime::Tick();
    Check(state.phase==Phase::Fault && state.error==Error::ObserverFault && state.observerFault && state.patched,"native exception leaves permanent observation fault and resident forwarding");
    Call later{};later.succeed=true;
    Check(!Invoke(later) && ActiveRuntime::Tick().phase==Phase::Fault,"fault does not silently suppress a later original invocation");
}
}
int main() {
    Check(CreateSource(),"private exact native body, declared callees and original unwind initialized");
    if(!fixtureModule || !nativeEntry)return 1;
    EarlyFailures();InstalledRoute();
    // All published storage stays resident until this private process exits.
    printf("MotionObservationRuntimeTests: %ld checks, %ld failures. Exact original body with three declared fixture callees; no game state.\n",checks,failures);
    return failures?1:0;
}
#endif
