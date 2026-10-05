#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define KH2_WORLD_TESTS
#include <windows.h>
#include <stdint.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits>
#include <initializer_list>

// Synthetic memory only. No process discovery, injection, game file access or
// native game function invocation is used by this harness.
namespace {
uintptr_t g_base=0;
volatile LONG g_disabled=0;
DWORD g_gameThread=0;
struct TestShared { DWORD hostHeartbeat; double values[128]; uint64_t valid[2], supported[2]; } shared{};
TestShared* g_shared=&shared;
struct TrainerContext { uintptr_t base,player,status; bool sceneReady; };
struct TrainerResult { LONG code; const wchar_t* text; };
template<class T> T& At(uintptr_t rva) { return *reinterpret_cast<T*>(g_base+rva); }
bool Readable(const void* p,SIZE_T size) {
    if (!p || reinterpret_cast<uintptr_t>(p)>UINTPTR_MAX-size) return false;
    MEMORY_BASIC_INFORMATION m{};
    if (!VirtualQuery(p,&m,sizeof(m)) || m.State!=MEM_COMMIT || (m.Protect&(PAGE_GUARD|PAGE_NOACCESS))) return false;
    return reinterpret_cast<uintptr_t>(p)+size<=reinterpret_cast<uintptr_t>(m.BaseAddress)+m.RegionSize;
}
bool Writable(const void* p,SIZE_T size) { return Readable(p,size); }
bool IsInteger(double n,double low,double high) { return isfinite(n) && n>=low && n<=high && floor(n)==n; }
void SnapshotValue(unsigned s,double v) { shared.values[s]=v; shared.valid[s/64]|=uint64_t(1)<<(s%64); }
void SupportCapability(unsigned s) { shared.supported[s/64]|=uint64_t(1)<<(s%64); }
#include "../../src/KH2Trainer.Bridge/WorldFeatures.inl"
unsigned retryCalls=0;
world_features::MapTarget retryTarget{};
unsigned retryFlags=0,retryDelay=0,retryRestore=0,retrySignal=0;
intptr_t __fastcall FakeRetry(const world_features::MapTarget* destination,unsigned flags,int delay,BYTE restore,unsigned signal) {
    ++retryCalls; retryTarget=*destination; retryFlags=flags; retryDelay=static_cast<unsigned>(delay); retryRestore=restore; retrySignal=signal;
    return 0;
}
unsigned captures=0;
alignas(8) unsigned char fakeTexture[32]{};
void FakeCapture() { ++captures; At<uintptr_t>(0x9BAA08)=reinterpret_cast<uintptr_t>(fakeTexture); }
void FailedCapture() { ++captures; At<uintptr_t>(0x9BAA08)=0; }
unsigned cameraWrites=0,rollWrites=0,fovWrites=0,cameraFrames=0;
bool cameraArgsValid=true;
void __fastcall FakeSetCamera(void* camera,const world_features::Vec4* eye,const world_features::Vec4* target,const world_features::Vec4* up) {
    ++cameraWrites; cameraArgsValid &= camera==reinterpret_cast<void*>(g_base+0xAC1020);
    At<world_features::Vec4>(0xAC1020+72)=*eye; At<world_features::Vec4>(0xAC1020+88)=*target; At<world_features::Vec4>(0xAC1020+104)=*up;
}
void __fastcall FakeSetRoll(void* camera,const world_features::Vec4* eye,const world_features::Vec4* target,float roll) {
    ++rollWrites; cameraArgsValid &= camera==reinterpret_cast<void*>(g_base+0xAC1020) && eye->w==1 && target->w==1;
    At<float>(0xAC1020+120)=roll;
}
void __fastcall FakeSetFov(void* projection,float radians,int vertical) {
    ++fovWrites; cameraArgsValid &= projection==reinterpret_cast<void*>(g_base+0xAC1840) && vertical==0 && fabsf(radians-85*0.017453292519943295f)<0.000001f;
}
void __fastcall FakeCameraFrame(void*) { ++cameraFrames; }
void __fastcall FaultSetCamera(void*,const world_features::Vec4*,const world_features::Vec4*,const world_features::Vec4*) {
    RaiseException(0xE0123456,0,0,nullptr);
}

unsigned checks=0,failures=0;
void Check(bool condition,const char* name) { ++checks; if(!condition) { ++failures; printf("FAIL: %s\n",name); } }
struct alignas(8) Buffer { unsigned char bytes[152]; };
void Word(void* p,unsigned offset,uintptr_t n) { *reinterpret_cast<uintptr_t*>(static_cast<unsigned char*>(p)+offset)=n; }
void Dword(void* p,unsigned offset,unsigned n) { *reinterpret_cast<unsigned*>(static_cast<unsigned char*>(p)+offset)=n; }
void Task(Buffer& b,void* manager,uintptr_t callback,unsigned group,unsigned priority) {
    ZeroMemory(&b,sizeof(b)); Word(&b,0,callback); Word(&b,88,reinterpret_cast<uintptr_t>(manager)); Dword(&b,96,group); Dword(&b,100,priority);
}
uintptr_t Pointer(const Buffer& b) { return *reinterpret_cast<const uintptr_t*>(&b); }
bool Command(unsigned slot,double value,TrainerResult& result) {
    TrainerContext c{g_base,0,0,true}; double args[8]{}; args[0]=value; return WorldHandle(c,slot,args,result);
}
}
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,0x2C00000,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    if(!g_base) return 2;
    g_gameThread=GetCurrentThreadId(); shared.hostHeartbeat=GetTickCount();
    alignas(8) unsigned char outer[72]{},inner[72]{};
    Buffer timing{},camera{};
    Task(timing,outer,g_base+0x1548E0,0,800000);
    Task(camera,inner,g_base+0x19CBA0,3,30000);
    Word(outer,16,reinterpret_cast<uintptr_t>(&timing)); Word(outer,24,reinterpret_cast<uintptr_t>(&timing));
    Word(inner,16,reinterpret_cast<uintptr_t>(&camera)); Word(inner,24,reinterpret_cast<uintptr_t>(&camera));
    At<uintptr_t>(0x9BA888)=reinterpret_cast<uintptr_t>(outer);
    At<uintptr_t>(0x716868)=reinterpret_cast<uintptr_t>(inner);
    At<uintptr_t>(0x9BA920)=g_base+0x1000;
    At<BYTE>(0x9BA8D0)=1; At<int>(0x716884)=1;
    At<float>(0xAC1840+76)=1; At<float>(0xAC1840+80)=1;
    At<world_features::Vec4>(0xAC1020+72)={10,20,30,1};
    At<world_features::Vec4>(0xAC1020+88)={10,20,40,1};
    At<world_features::Vec4>(0xAC1020+104)={0,-1,0,0};
    TrainerContext context{g_base,0,0,true}; TrainerResult result{};
    Check(world_features::CallbackWritesAllowed(),"normal callback writes permitted");
    g_disabled=1; Check(!world_features::CallbackWritesAllowed(),"failed bridge blocks callback writes"); g_disabled=0;
    const DWORD thread=g_gameThread; g_gameThread=0; Check(!world_features::CallbackWritesAllowed(),"wrong thread blocks writes"); g_gameThread=thread;
    shared.hostHeartbeat=GetTickCount()-6000; Check(!world_features::CallbackWritesAllowed(),"expired host blocks callback writes"); shared.hostHeartbeat=GetTickCount();
    shared.hostHeartbeat=0; Check(!world_features::CallbackWritesAllowed(),"zero heartbeat is never valid"); shared.hostHeartbeat=GetTickCount();
    Check(Command(48,2,result)&&result.code==0,"valid speed accepted");
    Check(Pointer(timing)==reinterpret_cast<uintptr_t>(world_features::TimingFrame),"native timing node wrapped");
    Command(48,0,result); Check(result.code!=0&&world_features::speed==2,"zero speed rejected without mutation");
    Command(48,std::numeric_limits<double>::quiet_NaN(),result); Check(result.code!=0&&world_features::speed==2,"NaN speed rejected");
    WorldReset(context); Check(Pointer(timing)==g_base+0x1548E0&&world_features::speed==1,"reset restores owned timing callback");
    Word(&timing,112,1); Command(48,2,result); Check(result.code!=0&&Pointer(timing)==g_base+0x1548E0,"fiber task rejected"); Word(&timing,112,0);
    Word(&timing,128,reinterpret_cast<uintptr_t>(&timing)); Command(48,2,result); Check(result.code!=0&&Pointer(timing)==g_base+0x1548E0,"invalid list rejected before write"); Word(&timing,128,0);
    Command(48,2,result); Word(&timing,0,g_base+0x123456); WorldReset(context); Check(Pointer(timing)==g_base+0x123456,"reset preserves foreign callback"); Word(&timing,0,g_base+0x1548E0);
    const unsigned otherBits=0x01012345; At<unsigned>(0x749804)=otherBits;
    Command(57,1,result); Check(result.code==0&&At<unsigned>(0x749804)==(otherBits|0x04000000),"caption bit preserves unrelated bits");
    At<unsigned>(0x749804)|=0x20000000; WorldReset(context); Check(At<unsigned>(0x749804)==(otherBits|0x20000000),"restore preserves later unrelated bit");
    Command(57,1,result); At<unsigned>(0x749804)&=~0x04000000; WorldReset(context); Check(!(At<unsigned>(0x749804)&0x04000000),"restore respects later same-bit writer");
    Command(51,1,result); Check(result.code==0&&world_features::freeCamera,"camera captured");
    Check(Pointer(camera)==reinterpret_cast<uintptr_t>(world_features::CameraFrame),"camera task wrapped");
    Command(52,45,result); Check(result.code==0&&world_features::eye.x==45&&world_features::target.x==45,"camera translation preserves relative target");
    Command(56,90,result); Check(result.code!=0,"camera pitch outside safe range rejected");
    Command(55,90,result); Check(result.code==0&&fabs(world_features::Yaw()-90)<0.01,"camera yaw updates target around eye");
    At<BYTE>(0x9BA8D0)=0; WorldTick(context); Check(!world_features::freeCamera,"transition cancels held camera"); At<BYTE>(0x9BA8D0)=1;
    Command(49,0,result); Check(result.code!=0&&!world_features::fovEnabled,"invalid FOV rejected");
    Command(49,85,result); Check(result.code==0&&world_features::fovEnabled&&world_features::fovDegrees==85,"valid FOV enables override");
    At<BYTE>(0xAC183C)=1; Command(51,1,result); Check(result.code!=0,"dual-bank camera capture rejected"); At<BYTE>(0xAC183C)=0;
    WorldReset(context); Check(Pointer(camera)==g_base+0x19CBA0&&!world_features::fovEnabled,"reset restores camera task");
    world_features::testSetCamera=FakeSetCamera; world_features::testSetRoll=FakeSetRoll;
    world_features::testSetFov=FakeSetFov; world_features::testCameraFrame=FakeCameraFrame;
    At<float>(0xAC1020+120)=0.4f;
    Command(51,1,result); Command(49,85,result);
    Check(WorldCameraExtraIsHeld()&&world_features::heldRoll==0.4f,"freecam captures native roll without changing up");
    Check(WorldCameraExtraSetRoll(1.2f)&&WorldCameraExtraRoll()==1.2f&&At<float>(0xAC1020+120)==0.4f,"roll changes held setting before renderer phase");
    world_features::CameraFrame(&camera);
    Check(cameraWrites==1&&rollWrites==1&&fovWrites==1&&cameraFrames==1&&cameraArgsValid,"camera callback uses checked ABI and invokes original exactly once");
    Check(At<float>(0xAC1020+120)==1.2f&&At<world_features::Vec4>(0xAC1020+104).y==-1,"roll reaches native channel once and leaves captured up unchanged");
    for (float bad : {std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN(),1e20f,-3.2f,3.2f})
        Check(!WorldCameraExtraSetRoll(bad)&&WorldCameraExtraRoll()==1.2f,"unsafe roll never reaches native iterative normalizer");
    At<int>(0xAC1528)=1; world_features::CameraFrame(&camera);
    Check(cameraFrames==2&&cameraWrites==1&&fovWrites==1&&!world_features::freeCamera&&!world_features::fovEnabled,"script owner takeover clears camera and FOV before native callback");
    At<int>(0xAC1528)=0; world_features::CameraFrame(&camera);
    Check(cameraFrames==3&&cameraWrites==1&&!WorldCameraExtraIsHeld(),"return to follow owner does not reactivate old override");
    for(int owner : {1,2,3,-1}) {
        At<int>(0xAC1528)=owner; Command(51,1,result); Check(result.code!=0&&!world_features::freeCamera,"non-follow owner cannot capture freecam");
        Command(49,85,result); Check(result.code!=0&&!world_features::fovEnabled,"non-follow owner cannot enable FOV");
    }
    At<int>(0xAC1528)=0;
    At<int>(0x718C60+72)=1; Command(51,1,result); Check(result.code!=0,"non-normal controller submode rejected"); At<int>(0x718C60+72)=0;
    for (float bad : {std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN(),1e20f,-3.2f}) {
        At<float>(0xAC1020+120)=bad; Command(51,1,result); Check(result.code!=0&&!world_features::freeCamera,"capture rejects unsafe native roll");
    }
    At<float>(0xAC1020+120)=0;
    for(unsigned byte=0;byte<sizeof(world_features::MapTarget);++byte) {
        Command(51,1,result); Command(49,85,result); auto& value=At<BYTE>(0x717008+byte); value^=1;
        const unsigned before=cameraWrites; world_features::CameraFrame(&camera);
        Check(!world_features::freeCamera&&!world_features::fovEnabled&&cameraWrites==before,"full map target change cancels render lease before writing"); value^=1;
    }
    Command(51,1,result); Command(49,85,result); At<uintptr_t>(0x9BA920)=g_base+0x2000;
    world_features::CameraFrame(&camera); Check(!world_features::freeCamera&&!world_features::fovEnabled,"same-room heap replacement releases both overrides"); At<uintptr_t>(0x9BA920)=g_base+0x1000;
    Command(51,1,result); Command(49,85,result); At<uintptr_t>(0x716868)=reinterpret_cast<uintptr_t>(outer);
    world_features::CameraFrame(&camera); Check(!world_features::freeCamera&&!world_features::fovEnabled,"scheduler replacement releases both overrides"); At<uintptr_t>(0x716868)=reinterpret_cast<uintptr_t>(inner);
    Command(51,1,result); Command(49,85,result); At<int>(0x718C60+72)=2;
    world_features::CameraFrame(&camera); Check(!world_features::freeCamera&&!world_features::fovEnabled,"controller mode takeover releases both overrides"); At<int>(0x718C60+72)=0;
    Command(51,1,result); Command(49,85,result); shared.hostHeartbeat=GetTickCount()-6000;
    world_features::CameraFrame(&camera); Check(!world_features::freeCamera&&!world_features::fovEnabled,"expired host releases camera before renderer writes"); shared.hostHeartbeat=GetTickCount();
    Command(51,1,result); Command(49,85,result); g_gameThread=0;
    unsigned beforeCamera=cameraWrites,beforeFrames=cameraFrames;
    world_features::CameraFrame(&camera); Check(cameraWrites==beforeCamera&&cameraFrames==beforeFrames+1,"wrong-thread callback still calls original once without trainer writes"); g_gameThread=thread;
    At<int>(0xAC1838)=1; world_features::CameraFrame(&camera);
    Check(cameraWrites==beforeCamera&&cameraFrames==beforeFrames+2,"secondary bank skips trainer writes but preserves original update"); At<int>(0xAC1838)=0;
    world_features::testSetCamera=FaultSetCamera; beforeFrames=cameraFrames;
    world_features::CameraFrame(&camera); Check(cameraFrames==beforeFrames+1&&!world_features::freeCamera&&!world_features::fovEnabled,"native setter fault clears ownership and still calls original once"); world_features::testSetCamera=FakeSetCamera;
    WorldReset(context);
    double travel[8]{19,0,0,-1,-1,-1,0,0}; WorldHandle(context,61,travel,result); Check(result.code!=0,"invalid world rejected before native call");
    alignas(8) unsigned char table[1024]{}; *reinterpret_cast<unsigned*>(table+4)=1;
    *reinterpret_cast<unsigned short*>(table+8)=2; *reinterpret_cast<unsigned short*>(table+10)=32; At<uintptr_t>(0x2A10558)=reinterpret_cast<uintptr_t>(table);
    world_features::MapTarget destination{0,1,0,0,-1,-1,-1};
    Check(world_features::ValidDestination(destination),"live table room accepted"); destination.area=2;
    Check(!world_features::ValidDestination(destination),"live table room bound enforced"); destination.area=0; destination.world=1;
    Check(!world_features::ValidDestination(destination),"live table world bound enforced");
    At<unsigned>(0x2A11400)=0x8000;
    Command(79,1,result); Check(result.code==0&&At<unsigned>(0x2A11400)==0x8020,"actor freeze owns only its bit");
    Check(world_features::actorFreezeOwned,"actor freeze ownership tracked");
    Command(79,2,result); Check(result.code!=0&&At<unsigned>(0x2A11400)==0x8020,"invalid freeze setting preserves state");
    At<unsigned>(0x2A11400)|=0x10000;
    Command(79,0,result); Check(result.code==0&&At<unsigned>(0x2A11400)==0x18000,"freeze release preserves other flags");
    At<unsigned>(0x2A11400)|=0x20; Command(79,1,result);
    Check(result.code!=0&&!world_features::actorFreezeOwned,"pre-existing native freeze rejected");
    WorldReset(context); Check(At<unsigned>(0x2A11400)&0x20,"reset preserves unowned native freeze");
    At<unsigned>(0x2A11400)&=~0x20u; Command(79,1,result);
    At<unsigned>(0x2A11400)&=~0x20u; WorldTick(context);
    Check(!world_features::actorFreezeOwned&&!(At<unsigned>(0x2A11400)&0x20),"native clear releases ownership without reassertion");
    Command(79,1,result); At<uintptr_t>(0x9BA928)=1; WorldTick(context);
    Check(!world_features::actorFreezeOwned&&!(At<unsigned>(0x2A11400)&0x20),"pending transition restores owned freeze"); At<uintptr_t>(0x9BA928)=0;
    Command(79,1,result); At<BYTE>(0x717008)=1; WorldTick(context);
    Check(!world_features::actorFreezeOwned&&(At<unsigned>(0x2A11400)&0x20),"new scene freeze is preserved");
    At<BYTE>(0x717008)=0; At<unsigned>(0x2A11400)&=~0x20u;
    Command(79,1,result); WorldReset(context);
    Check(!world_features::actorFreezeOwned&&!(At<unsigned>(0x2A11400)&0x20),"disable-all releases same-scene freeze");
    WorldCapabilities(); Check((shared.supported[0]&(uint64_t(1)<<48)) && (shared.supported[1]&(uint64_t(1)<<15)),"declared range publishes capabilities");
    WorldSnapshot(context); Check((shared.valid[0]&(uint64_t(1)<<48))&&shared.values[48]==1,"snapshot shows restored speed");
    world_features::testRetryCall=FakeRetry;
    At<uint64_t>(0x9A98B0)=At<uint64_t>(0x29FB580)=0x0000003A4A32484Bull;
    At<world_features::MapTarget>(0x2A0C540)={0,1,7,0,91,-1,300};
    At<BYTE>(0x29FB580+12)=0; At<BYTE>(0x29FB580+13)=1; At<BYTE>(0x29FB580+14)=7;
    // The deliberately stale CRC must not reject a valid in-memory snapshot.
    At<unsigned>(0x29FB580+8)=0x12345678;
    Check(Command(115,0,result)&&result.code==0&&retryCalls==1,"native checkpoint accepted without stale CRC validation");
    Check(retryFlags==1&&retryDelay==0&&retryRestore==1&&retrySignal==0,"retry uses exact native menu transition parameters");
    Check(retryTarget.world==0&&retryTarget.area==1&&retryTarget.entrance==7&&retryTarget.map==91&&retryTarget.event==300,"retry preserves native target including mission spawn sets");
    At<uint64_t>(0x29FB580)=0; Command(115,0,result); Check(result.code!=0&&retryCalls==1,"invalid checkpoint header rejects before call");
    At<uint64_t>(0x29FB580)=0x0000003A4A32484Bull;
    At<uint64_t>(0x9A98B0)=0; Command(115,0,result); Check(result.code!=0&&retryCalls==1,"invalid live save header rejects before call");
    At<uint64_t>(0x9A98B0)=0x0000003A4A32484Bull;
    At<BYTE>(0x2A0C540)=255; Command(115,0,result); Check(result.code!=0&&retryCalls==1,"startup checkpoint sentinel rejected"); At<BYTE>(0x2A0C540)=0;
    At<BYTE>(0x29FB580+14)=6; Command(115,0,result); Check(result.code!=0&&retryCalls==1,"mismatched snapshot entrance rejected"); At<BYTE>(0x29FB580+14)=7;
    At<BYTE>(0x29FB580+13)=0; Command(115,0,result); Check(result.code!=0&&retryCalls==1,"mismatched snapshot room rejected"); At<BYTE>(0x29FB580+13)=1;
    At<uintptr_t>(0x9BA928)=1; Command(115,0,result); Check(result.code!=0&&retryCalls==1,"retry during pending transition rejected"); At<uintptr_t>(0x9BA928)=0;
    At<BYTE>(0x9006B0)=1; Command(115,0,result); Check(result.code!=0&&retryCalls==1,"retry during menu rejected"); At<BYTE>(0x9006B0)=0;
    At<BYTE>(0x9BA8D1)=1; Command(115,0,result); Check(result.code!=0&&retryCalls==1,"retry during event-only phase rejected"); At<BYTE>(0x9BA8D1)=0;
    Check(shared.supported[1]&(uint64_t(1)<<(115-64)),"retry capability published");
    world_features::testCaptureCall=FakeCapture;
    At<BYTE>(0x9BAA50)=1;
    Command(116,1,result); Check(result.code!=0,"pause rejects absent native draw and field fiber tasks");
    Buffer draw{},field{}; alignas(8) unsigned char continuation[48]{};
    Task(draw,outer,g_base+0x1567A0,0,100000); Task(field,outer,g_base+0x150310,0x80001,130000);
    Word(&field,24,g_base+0x716860); Word(&field,112,reinterpret_cast<uintptr_t>(continuation)); continuation[24]=1;
    Word(&draw,120,reinterpret_cast<uintptr_t>(&field)); Word(&field,128,reinterpret_cast<uintptr_t>(&draw));
    Word(&field,120,reinterpret_cast<uintptr_t>(&timing)); Word(&timing,128,reinterpret_cast<uintptr_t>(&field));
    Word(outer,16,reinterpret_cast<uintptr_t>(&draw));
    Command(116,2,result); Check(result.code!=0,"invalid pause value rejected");
    At<unsigned>(0xABB854)=1; Command(116,1,result); Check(result.code!=0,"native timer pause ownership rejected"); At<unsigned>(0xABB854)=0;
    At<BYTE>(0xABADE0)=1; Command(116,1,result); Check(result.code!=0,"native screen capture ownership rejected"); At<BYTE>(0xABADE0)=0;
    Dword(continuation,28,1); Command(116,1,result); Check(result.code!=0,"sleeping field fiber rejected"); Dword(continuation,28,0);
    Command(116,1,result); Check(result.code==0&&world_features::pausePhase==world_features::PausePhase::Requested&&At<int>(0x716884)==1&&captures==0,"pause queues without out-of-phase capture");
    world_features::PauseBeforeTiming();
    Check(captures==1&&At<int>(0x716884)==2&&At<BYTE>(0xABADE0)==1&&At<unsigned>(0xABB854)==world_features::pauseTimerMask,"pause captures before timing and owns field/timer gates");
    world_features::PauseBeforeTiming(); Check(captures==1&&world_features::pausePhase==world_features::PausePhase::Held,"paused frames reuse capture without simulation or recapture");
    g_gameThread=0; world_features::PauseBeforeTiming();
    Check(At<int>(0x716884)==2&&At<unsigned>(0xABB854)==world_features::pauseTimerMask,"wrong-thread callback does not restore or write game state"); g_gameThread=thread;
    Command(117,0,result); Check(result.code==0&&At<int>(0x716884)==1&&At<BYTE>(0xABADE0)==0&&At<unsigned>(0xABB854)==0,"step releases field and clock for one update");
    Command(117,0,result); Check(result.code!=0,"duplicate step rejected while update pending");
    world_features::PauseBeforeTiming();
    Check(captures==2&&At<int>(0x716884)==2&&At<BYTE>(0xABADE0)==1&&At<unsigned>(0xABB854)==0,"step recaptures and suspends field before timing");
    world_features::PauseAfterTiming();
    Check(At<unsigned>(0xABB854)==world_features::pauseTimerMask&&world_features::pausePhase==world_features::PausePhase::Held,"step allows one timing call then freezes clock again");
    WorldSnapshot(context); Check(shared.values[116]==1,"pause snapshot indicates ownership");
    Command(116,0,result); Check(result.code==0&&At<int>(0x716884)==1&&At<BYTE>(0xABADE0)==0&&At<unsigned>(0xABB854)==0,"pause disable restores acquired gates");
    Command(117,0,result); Check(result.code!=0,"step rejected while not paused");
    Command(116,1,result); Command(116,0,result); world_features::PauseBeforeTiming(); Check(captures==2&&At<int>(0x716884)==1,"queued pause can be canceled before any capture");
    Command(116,1,result); At<unsigned>(0xABB854)=4; world_features::PauseBeforeTiming();
    Check(world_features::pausePhase==world_features::PausePhase::Off&&At<unsigned>(0xABB854)==4&&captures==2,"native owner arriving before capture wins"); At<unsigned>(0xABB854)=0;
    Command(116,1,result); world_features::PauseBeforeTiming(); At<unsigned>(0xABB854)|=1; At<BYTE>(0x9006B0)=1; WorldTick(context);
    Check(world_features::pausePhase==world_features::PausePhase::Off&&At<unsigned>(0xABB854)==1&&At<int>(0x716884)==2&&At<BYTE>(0xABADE0)==1,"native menu takeover preserves its state and bit");
    At<BYTE>(0x9006B0)=0; At<BYTE>(0xABADE0)=0; At<int>(0x716884)=1; At<unsigned>(0xABB854)=0;
    Command(116,1,result); world_features::PauseBeforeTiming(); At<uintptr_t>(0x9BA928)=1; WorldTick(context);
    Check(world_features::pausePhase==world_features::PausePhase::Off&&At<int>(0x716884)==1&&At<unsigned>(0xABB854)==0,"pending transition releases same-scene pause"); At<uintptr_t>(0x9BA928)=0;
    Command(116,1,result); world_features::PauseBeforeTiming(); At<BYTE>(0x717008)=1; WorldTick(context);
    Check(world_features::pausePhase==world_features::PausePhase::Off&&At<int>(0x716884)==2&&At<BYTE>(0xABADE0)==1&&At<unsigned>(0xABB854)==0,"new scene field and capture state preserved");
    At<BYTE>(0x717008)=0; At<int>(0x716884)=1; At<BYTE>(0xABADE0)=0;
    Command(116,1,result); world_features::PauseBeforeTiming(); shared.hostHeartbeat=GetTickCount()-6000; world_features::PauseBeforeTiming();
    Check(world_features::pausePhase==world_features::PausePhase::Off&&At<int>(0x716884)==1&&At<unsigned>(0xABB854)==0,"lost host releases field pause"); shared.hostHeartbeat=GetTickCount();
    Command(116,1,result); world_features::testCaptureCall=FailedCapture; world_features::PauseBeforeTiming();
    Check(world_features::pausePhase==world_features::PausePhase::Off&&At<int>(0x716884)==1&&At<unsigned>(0xABB854)==0,"failed capture never freezes module"); world_features::testCaptureCall=FakeCapture;
    At<BYTE>(0x9BAA50)=0; const unsigned beforeBadCapture=captures; Command(116,1,result); world_features::PauseBeforeTiming();
    Check(world_features::pausePhase==world_features::PausePhase::Off&&captures==beforeBadCapture,"missing texture without recreate flag never calls native capture"); At<BYTE>(0x9BAA50)=1;
    Command(116,1,result); world_features::PauseBeforeTiming(); WorldReset(context);
    Check(At<int>(0x716884)==1&&At<BYTE>(0xABADE0)==0&&At<unsigned>(0xABB854)==0&&Pointer(timing)==g_base+0x1548E0,"disable-all restores pause and timing callback");
    Check((shared.supported[1]&(uint64_t(1)<<(116-64)))&&(shared.supported[1]&(uint64_t(1)<<(117-64))),"field pause and step capabilities published");
    printf("World guard tests: %u checks, %u failures; synthetic memory only.\n",checks,failures);
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);
    return failures?1:0;
}
