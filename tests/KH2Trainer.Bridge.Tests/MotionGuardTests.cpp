#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define KH2_MOTION_TESTS
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>
#include <initializer_list>
#include <limits>
namespace {
uintptr_t g_base=0; DWORD g_gameThread=0; volatile LONG g_disabled=0;
struct TrainerContext { uintptr_t base,player,status; bool sceneReady; };
struct TrainerResult { LONG code; const wchar_t* text; };
struct Shared { DWORD hostHeartbeat; double values[512]; uint64_t valid[8],supported[8]; } shared{};
Shared* g_shared=&shared;
template<class T> T& At(uintptr_t rva) { return *reinterpret_cast<T*>(g_base+rva); }
uintptr_t unreadable=0,unwritable=0;
bool Readable(const void* p,SIZE_T n) {
    uintptr_t cursor=reinterpret_cast<uintptr_t>(p);
    if(!cursor || n>UINTPTR_MAX-cursor || (unreadable && cursor<=unreadable && cursor+n>unreadable)) return false;
    const uintptr_t end=cursor+n;
    while(cursor<end) {
        MEMORY_BASIC_INFORMATION m{};
        if(!VirtualQuery(reinterpret_cast<const void*>(cursor),&m,sizeof(m)) || m.State!=MEM_COMMIT || (m.Protect&(PAGE_NOACCESS|PAGE_GUARD))) return false;
        const uintptr_t next=reinterpret_cast<uintptr_t>(m.BaseAddress)+m.RegionSize;
        if(next<=cursor) return false; cursor=next;
    }
    return true;
}
bool Writable(const void* p,SIZE_T n) {
    const uintptr_t start=reinterpret_cast<uintptr_t>(p);
    return Readable(p,n)&&(!unwritable || unwritable<start || unwritable>=start+n);
}
bool IsInteger(double v,double lo,double hi) { return isfinite(v)&&floor(v)==v&&v>=lo&&v<=hi; }
uintptr_t DecodePacked(uint32_t v) { return v?g_base+v:0; }
void SnapshotValue(unsigned s,double v) { shared.values[s]=v; shared.valid[s/64]|=uint64_t(1)<<(s%64); }
void SupportCapability(unsigned s) { shared.supported[s/64]|=uint64_t(1)<<(s%64); }
DWORD fakeNow=100000;
DWORD TestTick() { return fakeNow; }
unsigned protectCalls=0,failProtectCall=0;
bool replaceOnRestore=false;
BOOL TestProtect(void* p,SIZE_T n,DWORD protection,DWORD* old) {
    ++protectCalls;
    if(protectCalls==failProtectCall) {
        if(replaceOnRestore) At<uintptr_t>(0x755A20)=g_base+0x123456;
        return FALSE;
    }
    return VirtualProtect(p,n,protection,old);
}
#define GetTickCount TestTick
#define VirtualProtect TestProtect
#include "../../src/KH2Trainer.Bridge/MotionFeatures.inl"
#undef VirtualProtect
unsigned checks=0,failures=0,calls=0;
bool nativeWrites=true,sawSuperseded=false,raiseNative=false;
uint32_t* seenArgs=nullptr;
HANDLE originalEntered=nullptr,originalContinue=nullptr,stopEntered=nullptr;
void Check(bool v,const char* name) { ++checks; if(!v){++failures;printf("FAIL: %s\n",name);} }
constexpr uintptr_t actorRva=0x100000,statusRva=0x101000,modelRva=0x120000,modelResourceRva=0x121000,motionRva=0x130000,resourceRva=0x131000;
TrainerContext Context() { return {g_base,At<uintptr_t>(0x2A105D0),g_base+statusRva,true}; }
void __fastcall Original(uint32_t* args) {
    ++calls; seenArgs=args; sawSuperseded=InterlockedCompareExchange(&motion_features::scriptChanged,0,0)!=0;
    if(originalEntered) { SetEvent(originalEntered); WaitForSingleObject(originalContinue,5000); }
    if(raiseNative) RaiseException(0xe0000123,0,0,nullptr);
    if(nativeWrites && args && Readable(args,12)) {
        const uintptr_t handle=DecodePacked(args[0]);
        if(Readable(reinterpret_cast<void*>(handle),8)) {
            const uintptr_t actor=DecodePacked(*reinterpret_cast<uint32_t*>(handle+4));
            if(Writable(reinterpret_cast<void*>(actor+680),4)) *reinterpret_cast<uint32_t*>(actor+680)=args[2];
        }
    }
}
void Setup(unsigned format=0) {
    ZeroMemory(reinterpret_cast<void*>(g_base),0x2C00000); ZeroMemory(&shared,sizeof(shared));
    motion_features::lease={}; motion_features::desired=1; motion_features::state=motion_features::Off;
    motion_features::observedActor=nullptr; motion_features::scriptChanged=0; motion_features::hooked=false;
    motion_features::originalWriter=nullptr; motion_features::testWriter=Original; motion_features::testPin=true;
    unreadable=unwritable=0; protectCalls=failProtectCall=0; replaceOnRestore=false;
    fakeNow=100000; g_gameThread=GetCurrentThreadId(); g_disabled=0; g_shared=&shared; shared.hostHeartbeat=fakeNow;
    calls=0; nativeWrites=true; sawSuperseded=false; seenArgs=nullptr; raiseNative=false; originalEntered=originalContinue=stopEntered=nullptr;
    At<uintptr_t>(0x2A105D0)=g_base+actorRva; At<uintptr_t>(0x2A171C8)=g_base+actorRva;
    At<uint32_t>(actorRva)=0x750300; At<uint32_t>(actorRva+4)=actorRva;
    At<uintptr_t>(actorRva+1472)=g_base+statusRva; At<unsigned>(actorRva+1736)=0x1000080;
    At<uintptr_t>(actorRva+360)=g_base+actorRva; At<int>(actorRva+384)=12; At<int>(actorRva+388)=24;
    At<float>(actorRva+408)=60; At<float>(actorRva+412)=15.5f; At<float>(actorRva+416)=0; At<float>(actorRva+420)=2;
    At<float>(actorRva+680)=1.25f; At<uintptr_t>(actorRva+1968)=g_base+modelRva;
    At<int>(statusRva)=100; At<int>(statusRva+4)=120; At<int>(statusRva+608)=1; At<uint32_t>(statusRva+616)=actorRva;
    At<uintptr_t>(modelRva+32)=g_base+modelResourceRva; At<uintptr_t>(modelResourceRva)=g_base+0x122000;
    At<uintptr_t>(actorRva+368)=g_base+motionRva; At<uintptr_t>(motionRva)=g_base+(format?0x5B4A38:0x5B4958);
    At<uintptr_t>(motionRva+8)=g_base+resourceRva; At<unsigned>(resourceRva)=format;
    if(!format) { At<uint16_t>(resourceRva+16)=2; At<uint16_t>(resourceRva+18)=2; At<unsigned>(resourceRva+20)=60; At<float>(resourceRva+152)=60; }
    else { At<unsigned>(resourceRva+16)=2; At<unsigned>(resourceRva+32)=60; At<unsigned>(resourceRva+36)=61; At<float>(resourceRva+88)=60; }
    At<BYTE>(0x9BA8D0)=1; At<int>(0x716884)=1;
    At<uintptr_t>(0x9BA920)=g_base+0x140000; At<uintptr_t>(0x716868)=g_base+0x141000; At<uintptr_t>(0x2A17180)=g_base+0x142000;
    At<uintptr_t>(0x2A25370)=g_base+0x143000;
    At<uintptr_t>(motion_features::kBankRoot)=g_base+motion_features::kBank;
    At<uintptr_t>(motion_features::kSlot)=g_base+motion_features::kWriter; At<unsigned>(motion_features::kSlot+8)=2;
    memcpy(reinterpret_cast<void*>(g_base+motion_features::kWriter),motion_features::kWriterBytes,sizeof(motion_features::kWriterBytes));
}
TrainerResult Command(unsigned slot,double value,const TrainerContext* alternate=nullptr) {
    const auto c=alternate?*alternate:Context(); double args[8]{value}; TrainerResult result{};
    Check(MotionHandle(c,slot,args,result),"known motion command handled"); return result;
}
void Enable(double speed=2) {
    Check(Command(160,speed).code==0,"desired speed accepted"); Check(Command(161,1).code==0,"override enabled");
}
void Tick() { MotionTick(Context()); }
bool IsActive() { return motion_features::lease.enabled; }
void Reject(const char* text) {
    const uint32_t before=At<uint32_t>(actorRva+680); const uintptr_t slot=At<uintptr_t>(motion_features::kSlot);
    const auto r=Command(161,1);
    Check(r.code!=0&&!IsActive()&&At<uint32_t>(actorRva+680)==before&&At<uintptr_t>(motion_features::kSlot)==slot,text);
}
void Script(float value,uintptr_t handle=actorRva) {
    uint32_t args[4]{static_cast<uint32_t>(handle),0x12345678,motion_features::Bits(value),0xabcdef01};
    motion_features::WriterHook(args);
    Check(seenArgs==args&&args[1]==0x12345678&&args[3]==0xabcdef01,"wrapper preserves full two-operand array ABI");
}
DWORD WINAPI WriterThread(void*) { Script(2); return 0; }
DWORD WINAPI StopThread(void*) {
    g_gameThread=GetCurrentThreadId(); SetEvent(stopEntered); MotionReset(Context()); return 0;
}
void TestConcurrent() {
    Setup(); Enable();
    originalEntered=CreateEventW(nullptr,TRUE,FALSE,nullptr); originalContinue=CreateEventW(nullptr,TRUE,FALSE,nullptr); stopEntered=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    HANDLE writer=CreateThread(nullptr,0,WriterThread,nullptr,0,nullptr);
    Check(WaitForSingleObject(originalEntered,5000)==WAIT_OBJECT_0,"writer reached native callback while mutation lock held");
    HANDLE stopper=CreateThread(nullptr,0,StopThread,nullptr,0,nullptr);
    Check(WaitForSingleObject(stopEntered,5000)==WAIT_OBJECT_0,"concurrent reset attempted");
    Check(WaitForSingleObject(stopper,30)==WAIT_TIMEOUT,"reset waits for synchronous native writer");
    SetEvent(originalContinue);
    Check(WaitForSingleObject(writer,5000)==WAIT_OBJECT_0&&WaitForSingleObject(stopper,5000)==WAIT_OBJECT_0,"writer and reset finish without deadlock");
    Check(!IsActive()&&At<float>(actorRva+680)==2&&calls==1,"same-float concurrent script ownership wins over baseline restoration");
    CloseHandle(writer); CloseHandle(stopper); CloseHandle(originalEntered); CloseHandle(originalContinue); CloseHandle(stopEntered);
    originalEntered=originalContinue=stopEntered=nullptr; g_gameThread=GetCurrentThreadId();
}
}
int main() {
    using namespace motion_features;
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,0x2C00000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE)); if(!g_base)return 2;
    for(unsigned format=0;format<=1;++format) {
        Setup(format); View view{}; Check(ReadView(Context(),view)&&view.format==format,"Prototype/RAW supported header produces a view");
        MotionSnapshot(Context()); Check(shared.values[162]==1.25&&shared.values[163]==15.5&&shared.values[164]==60&&shared.values[165]==12&&shared.values[166]==24&&shared.values[169]==format,"readouts match real controller/header fields");
        Enable(); Check(At<float>(actorRva+680)==2&&OwnSlot()&&state==Active,"one initial Actor speed write and own narrow callback installed");
        Check(At<unsigned>(kSlot+8)==2&&At<unsigned>(kSlot+12)==0,"VM arity and metadata remain intact");
        Check(Command(160,0.5).code==0&&At<float>(actorRva+680)==0.5f&&lease.baseline==Bits(1.25f),"rate updates preserve original baseline");
        const uint32_t baseline=lease.baseline; Command(161,1); Check(lease.baseline==baseline,"repeated enable does not capture own override as baseline");
        // Ordinary motion switch on the same Actor/model must retain the override.
        memcpy(reinterpret_cast<void*>(g_base+0x132000),reinterpret_cast<void*>(g_base+motionRva),48);
        memcpy(reinterpret_cast<void*>(g_base+0x133000),reinterpret_cast<void*>(g_base+resourceRva),160);
        At<uintptr_t>(actorRva+368)=g_base+0x132000; At<uintptr_t>(0x132008)=g_base+0x133000;
        At<int>(actorRva+384)=25; At<int>(actorRva+388)=-1; At<float>(actorRva+412)=0;
        Tick(); Check(IsActive()&&At<float>(actorRva+680)==0.5f,"normal motion/resource/ID change preserves actor-wide lease");
        At<int>(0x716884)=2; Tick(); Check(IsActive(),"field pause can retain an actor-bound animation setting");
        Command(161,0); Check(!IsActive()&&At<float>(actorRva+680)==1.25f&&At<uintptr_t>(kSlot)==g_base+kWriter,"disable restores exact baseline and only owned slot");
    }
    Setup(); auto c=Context(); c.sceneReady=false; Check(Command(160,3,&c).code==0&&At<float>(actorRva+680)==1.25f,"desired rate may be stored with no scene and performs no game write");
    for(double bad : {0.,-1.,3.01,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}) { Setup(); Check(Command(160,bad).code!=0&&desired==1,"invalid rate is rejected"); }
    Setup(); Check(Command(161,0.5).code!=0,"fractional toggle rejected");
    Setup(); double args[8]{}; TrainerResult r{}; Check(!MotionHandle(Context(),159,args,r),"unowned slot ignored");
    for(unsigned slot=162;slot<=170;++slot) { Setup(); Check(Command(slot,1).code!=0,"readouts are not writable"); }
    Setup(); Enable(); At<float>(actorRva+680)=0.75f; Tick(); Check(!IsActive()&&state==ValueChanged&&At<float>(actorRva+680)==0.75f,"external distinct speed is preserved instead of constantly overwritten");
    Setup(); Enable(); Script(0.5f); Check(calls==1&&sawSuperseded,"script ownership is revoked before original exactly once"); Tick(); Check(!IsActive()&&state==ScriptChanged&&At<float>(actorRva+680)==0.5f,"script new speed is preserved");
    Setup(); Enable(); Script(2); MotionReset(Context()); Check(!IsActive()&&At<float>(actorRva+680)==2,"same-float native script prevents baseline restore on reset");
    Setup(); Enable(); Script(2); shared.hostHeartbeat=0; MotionReset(Context()); Check(At<float>(actorRva+680)==2,"expired host reset respects prior same-float script ownership before tick");
    Setup(); Enable(); Script(2); Command(161,0); Check(At<float>(actorRva+680)==2,"explicit disable after same-float script preserves native write");
    Setup(); Enable(); Script(2); Command(160,0.5); Check(!IsActive()&&At<float>(actorRva+680)==2&&desired==0.5f,"slider after script stores desired rate without reacquiring ownership");
    Setup(); Enable(); At<uint32_t>(0x110004)=0x110000; Script(0.75f,0x110000); Tick(); Check(IsActive()&&calls==1&&At<float>(0x110000+680)==0.75f&&At<float>(actorRva+680)==2,"unrelated Actor script forwards unchanged without dropping player lease");
    Setup(); Enable(); nativeWrites=false; WriterHook(nullptr); Check(calls==1,"invalid observation still forwards original once");
    Setup(); Enable(); Command(161,0); Script(0.7f); Check(calls==1&&At<float>(actorRva+680)==0.7f,"already-dispatched wrapper forwards after unhook");
    Setup(); Enable(); raiseNative=true; bool propagated=false;
    __try { Script(2); } __except(GetExceptionCode()==0xe0000123?EXCEPTION_EXECUTE_HANDLER:EXCEPTION_CONTINUE_SEARCH) { propagated=true; }
    Check(propagated&&calls==1,"native callback exception propagates exactly once"); raiseNative=false; MotionReset(Context()); Check(!IsActive(),"exception path releases SRW lock");
    TestConcurrent();
    for(uintptr_t address : {kBankRoot,kSlot}) {
        Setup(); Enable(); At<uintptr_t>(address)=g_base+0x123456; Tick(); Check(!IsActive()&&state==HookChanged&&At<float>(actorRva+680)==2,"bank/slot replacement abandons ownership without clobbering unobserved native writes");
        if(address==kSlot) Check(At<uintptr_t>(kSlot)==g_base+0x123456,"foreign callback replacement is preserved");
    }
    for(uintptr_t address : {kBankRoot,kSlot}) {
        Setup(); Enable(); At<uintptr_t>(address)=g_base+0x123456; MotionReset(Context());
        Check(!IsActive()&&At<float>(actorRva+680)==2,"direct reset after lost callback observation never restores an unobserved value");
        Setup(); Enable(); At<uintptr_t>(address)=g_base+0x123456; shared.hostHeartbeat=0; Tick();
        Check(!IsActive()&&state==HostExpired&&At<float>(actorRva+680)==2,"host expiry plus lost callback observation never restores an unobserved value");
    }
    for(uintptr_t address : {kSlot+8,kSlot+12,kWriter}) { Setup(); Enable(); At<BYTE>(address)^=1; Tick(); Check(!IsActive()&&At<float>(actorRva+680)==2,"changed VM metadata or writer bytes ends lease without unobserved ownership restore"); }
    Setup(); At<uintptr_t>(kSlot)=g_base+0x123456; Reject("foreign callback prevents install");
    Setup(); At<uintptr_t>(kBankRoot)=g_base+0x123456; Reject("foreign bank prevents install");
    Setup(); At<unsigned>(kSlot+8)=3; Reject("wrong arity prevents install");
    Setup(); At<unsigned>(kSlot+12)=1; Reject("wrong VM flags prevent install");
    Setup(); At<BYTE>(kWriter)=0x90; Reject("changed writer bytes prevent install");
    Setup(); testPin=false; Reject("cannot install a callback whose module is not pinned");
    Setup(); failProtectCall=1; Reject("protection failure prevents install without speed write");
    Setup(); failProtectCall=2; Reject("failed protection restoration rolls back only own CAS");
    Setup(); failProtectCall=2; replaceOnRestore=true; r=Command(161,1); Check(r.code!=0&&!IsActive()&&At<uintptr_t>(kSlot)==g_base+0x123456&&At<float>(actorRva+680)==1.25f,"protection failure never overwrites a concurrent foreign callback");
    Setup(); Enable(); failProtectCall=protectCalls+1; Command(161,0); Check(!IsActive()&&OwnSlot()&&At<float>(actorRva+680)==1.25f,"failed unhook leaves resident forwarding wrapper with no lease");
    failProtectCall=0; Tick(); Check(!OwnSlot(),"inactive tick retries removal of own callback");
    Setup(); Enable(); shared.hostHeartbeat=0; Tick(); Check(!IsActive()&&state==HostExpired&&At<float>(actorRva+680)==1.25f,"host expiry restores in a still-valid scene");
    Setup(); Enable(); fakeNow+=5001; Tick(); Check(!IsActive()&&At<float>(actorRva+680)==1.25f,"absolute heartbeat age is checked");
    Setup(); Enable(); fakeNow=0x20; shared.hostHeartbeat=0xfffffff0; Tick(); Check(IsActive(),"fresh heartbeat subtraction handles tick wrap");
    Setup(); Enable(); g_disabled=1; MotionReset(Context()); Check(!IsActive()&&At<float>(actorRva+680)==1.25f,"failure reset can restore when fresh scene context is supplied");
    Setup(); Enable(); c=Context(); c.sceneReady=false; MotionReset(c); Check(!IsActive()&&At<float>(actorRva+680)==2,"unready reset does not follow or restore retained game fields");
    for(uintptr_t address : {0x9BA920u,0x716868u,0x2A17180u}) { Setup(); Enable(); At<uintptr_t>(address)+=8; Tick(); Check(!IsActive()&&At<float>(actorRva+680)==2,"heap/scheduler identity loss never writes old Actor speed"); }
    for(unsigned i=0;i<10;++i) { Setup(); Enable(); At<BYTE>(0x717008+i)^=1; Tick(); Check(!IsActive()&&At<float>(actorRva+680)==2,"every room byte binds ownership"); }
    for(uintptr_t address : {0x9BA8D1u,0xABAC58u,0xABAC59u,0x9006B0u}) { Setup(); Enable(); At<BYTE>(address)=1; Tick(); Check(!IsActive()&&At<float>(actorRva+680)==2,"event/title/menu teardown never restores old speed"); }
    for(uintptr_t address : {0x9BA928u,0xAC0F48u,0x2AE9FA8u}) { Setup(); Enable(); At<uintptr_t>(address)=1; Tick(); Check(!IsActive()&&At<float>(actorRva+680)==2,"pending scene/form transition ends lease without old-Actor write"); }
    Setup(); Enable(); At<unsigned>(0x2A10504)=2; Tick(); Check(!IsActive()&&At<float>(actorRva+680)==2,"native form lock blocks restoration");
    Setup(); Enable(); At<int>(actorRva+3552)=1; At<BYTE>(0x9ACDD4)=1; Tick(); Check(!IsActive()&&At<float>(actorRva+680)==2,"in-place form identity change is not a renewed lease");
    Setup(); Enable(); At<uintptr_t>(0x2A105D0)=g_base+0x110000; Tick(); Check(!IsActive()&&At<float>(actorRva+680)==2&&At<float>(0x110000+680)==0,"replacement player gets no override and old actor is not followed");
    Setup(); Enable(); At<uintptr_t>(actorRva+1472)=g_base+0x102000; Tick(); Check(!IsActive()&&At<float>(actorRva+680)==2,"status replacement prevents old-field restore");
    Setup(); Enable(); At<uintptr_t>(actorRva+360)=0; Tick(); Check(!IsActive()&&At<float>(actorRva+680)==2,"controller owner mismatch prevents restore");
    Setup(); Enable(); memcpy(reinterpret_cast<void*>(g_base+0x124000),reinterpret_cast<void*>(g_base+modelRva),856); At<uintptr_t>(actorRva+1968)=g_base+0x124000; Tick(); Check(!IsActive()&&At<float>(actorRva+680)==1.25f,"model replacement restores still-owned Actor field without touching old model");
    Setup(); Enable(); At<uintptr_t>(modelRva+32)=g_base+0x125000; Tick(); Check(!IsActive()&&At<float>(actorRva+680)==1.25f,"invalid new model resource restores Actor speed only");
    Setup(); Enable(); At<uintptr_t>(modelResourceRva)=g_base+0x126000; Tick(); Check(!IsActive()&&At<float>(actorRva+680)==1.25f,"model-resource vtable replacement ends lease and restores only current Actor field");
    Setup(); Enable(); At<uintptr_t>(actorRva+368)=0; Tick(); Check(!IsActive()&&At<float>(actorRva+680)==1.25f,"missing motion restores persistent Actor speed");
    Setup(); Enable(); unwritable=g_base+actorRva+680; Command(161,0); Check(!IsActive()&&At<float>(actorRva+680)==2,"unwritable speed is not restored");
    Setup(); g_gameThread=0; Reject("foreign thread cannot enable");
    Setup(); shared.hostHeartbeat=0; Reject("zero host heartbeat cannot enable");
    Setup(); g_disabled=1; Reject("disabled bridge cannot enable");
    Setup(); At<BYTE>(0x9BA8D0)=0; Reject("not-ready native scene rejected");
    Setup(); At<int>(statusRva)=0; Reject("dead Sora rejected");
    Setup(); At<int>(statusRva+608)=14; Reject("unsupported character rejected");
    Setup(); At<uint32_t>(actorRva+1696)=1; Reject("attached Actor cannot start override");
    Setup(); At<uint32_t>(actorRva+2704)=actorRva; Reject("cyclic Actor list rejected");
    Setup(); At<uintptr_t>(0x2A171C8)=0; Reject("unlisted Actor rejected");
    Setup(); At<uintptr_t>(actorRva+360)=0; Reject("wrong controller owner rejected");
    Setup(); At<uint32_t>(statusRva+616)=0; Reject("wrong status backlink rejected");
    Setup(); At<uintptr_t>(actorRva+1968)=0; Reject("missing model rejected");
    Setup(); At<uintptr_t>(modelRva+32)=0; Reject("missing model resource rejected");
    Setup(); At<uintptr_t>(motionRva)=g_base; Reject("unknown motion vtable rejected");
    Setup(); At<unsigned>(resourceRva)=1; Reject("wrapper/header format mismatch rejected");
    Setup(); At<unsigned>(resourceRva+20)=0; Reject("zero motion duration rejected");
    Setup(); At<unsigned>(resourceRva+20)=61; Reject("inconsistent controller/header duration rejected");
    Setup(); At<uint16_t>(resourceRva+16)=0; Reject("empty skeleton rejected");
    Setup(); At<uint16_t>(resourceRva+18)=1; Reject("prototype total joints smaller than base count rejected");
    Setup(1); At<unsigned>(resourceRva+36)=0; Reject("RAW zero sample count rejected");
    Setup(); At<float>(resourceRva+152)=0; Reject("zero sample rate rejected");
    Setup(); At<float>(actorRva+412)=std::numeric_limits<float>::quiet_NaN(); Reject("nonfinite frame rejected");
    Setup(); At<float>(actorRva+680)=std::numeric_limits<float>::infinity(); Reject("nonfinite native speed rejected");
    Setup(); At<float>(actorRva+680)=-1; Reject("reverse native playback is not commandeered");
    Setup(); At<float>(actorRva+680)=0; Enable(); Command(161,0); Check(At<float>(actorRva+680)==0,"explicit override can restore an exact native zero baseline");
    Setup(); unreadable=g_base+resourceRva+159; Reject("full Prototype header must be readable");
    Setup(1); unreadable=g_base+resourceRva+95; Reject("full RAW header must be readable");
    Setup(); MotionCapabilities(); for(unsigned i=160;i<=170;++i) Check((shared.supported[i/64]&(uint64_t(1)<<(i%64)))!=0,"only implemented motion capability published");
    Setup(); At<uintptr_t>(actorRva+368)=0; MotionSnapshot(Context()); Check(shared.valid[2]==((uint64_t(1)<<32)|(uint64_t(1)<<33)|(uint64_t(1)<<42)),"invalid motion publishes controls and status only, never fabricated readouts");
    printf("Motion guard tests: %u checks, %u failures\n",checks,failures);
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE); return failures?1:0;
}
