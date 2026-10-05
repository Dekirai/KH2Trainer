#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define KH2_CAMERA_EXTRA_TESTS
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <math.h>
#include <string.h>
#include <limits>
#include <initializer_list>
namespace {
uintptr_t g_base=0; DWORD g_gameThread=0; volatile LONG g_disabled=0;
struct TrainerContext { uintptr_t base,player,status; bool sceneReady; };
struct TrainerResult { LONG code; const wchar_t* text; };
struct Shared { DWORD hostHeartbeat; double values[512]; uint64_t valid[8],supported[8]; } shared{};
Shared* g_shared=&shared;
template<class T>T& At(uintptr_t rva) { return *reinterpret_cast<T*>(g_base+rva); }
template<class T>T& Field(uintptr_t object,size_t offset) { return *reinterpret_cast<T*>(object+offset); }
bool Readable(const void* p,size_t size) {
    uintptr_t pos=reinterpret_cast<uintptr_t>(p);
    if (!pos || size>UINTPTR_MAX-pos) return false;
    const uintptr_t end=pos+size;
    while(pos<end) {
        MEMORY_BASIC_INFORMATION info{};
        if(!VirtualQuery(reinterpret_cast<const void*>(pos),&info,sizeof(info)) || info.State!=MEM_COMMIT ||
            (info.Protect&(PAGE_GUARD|PAGE_NOACCESS))) return false;
        const DWORD prot=info.Protect&0xff;
        if(prot!=PAGE_READONLY && prot!=PAGE_READWRITE && prot!=PAGE_WRITECOPY &&
            prot!=PAGE_EXECUTE_READ && prot!=PAGE_EXECUTE_READWRITE && prot!=PAGE_EXECUTE_WRITECOPY) return false;
        const uintptr_t next=reinterpret_cast<uintptr_t>(info.BaseAddress)+info.RegionSize;
        if(next<=pos) return false;
        pos=next;
    }
    return true;
}
bool Writable(const void* p,size_t size) {
    if(!Readable(p,size)) return false;
    uintptr_t pos=reinterpret_cast<uintptr_t>(p),end=pos+size;
    while(pos<end) {
        MEMORY_BASIC_INFORMATION info{};
        if(!VirtualQuery(reinterpret_cast<const void*>(pos),&info,sizeof(info))) return false;
        const DWORD prot=info.Protect&0xff;
        if(prot!=PAGE_READWRITE && prot!=PAGE_WRITECOPY && prot!=PAGE_EXECUTE_READWRITE && prot!=PAGE_EXECUTE_WRITECOPY) return false;
        pos=reinterpret_cast<uintptr_t>(info.BaseAddress)+info.RegionSize;
    }
    return true;
}
uintptr_t DecodePacked(uint32_t v) { return v?g_base+v:0; }
bool badContext=false,held=false,consume=true,changeActorDuringFollow=false;
float heldRoll=0;unsigned rollCalls=0;
TrainerContext MakeTrainerContext() {
    const uintptr_t actor=At<uintptr_t>(0x2A105D0);
    if(badContext || !At<BYTE>(0x9BA8D0) || !Readable(reinterpret_cast<void*>(actor),0xDE4)) return {g_base,0,0,false};
    return {g_base,actor,Field<uintptr_t>(actor,1472),true};
}
bool WorldCameraExtraIsHeld() { return held; }
bool WorldCameraExtraSetRoll(float r) { ++rollCalls; if(!held || !isfinite(r) || fabsf(r)>3.141592654f) return false; heldRoll=r; return true; }
float WorldCameraExtraRoll() { return heldRoll; }
void SnapshotValue(unsigned s,double v) { shared.values[s]=v; shared.valid[s/64]|=uint64_t(1)<<(s%64); }
void SupportCapability(unsigned s) { shared.supported[s/64]|=uint64_t(1)<<(s%64); }
#include "../../src/KH2Trainer.Bridge/CameraExtraFeatures.inl"
constexpr uintptr_t Actor=0x10000,Status=0x15000,ActorController=0x18000,ControllerVt=0x1A000,
    Scheduler=0x20000,Heap=0x24000,Node=0x30000,Node2=0x31000;
unsigned checks=0,failures=0,followCalls=0,recenterCalls=0,snapCalls=0;
void Check(bool good,const char* label) { ++checks; if(!good) { ++failures; printf("FAIL: %s\n",label); } }
void __fastcall NativeRecenter() { ++recenterCalls; At<BYTE>(camera_extra::Controller+65)=1; }
void __fastcall NativeSnap() { ++snapCalls; At<BYTE>(camera_extra::Controller+64)=1; }
void __fastcall NativeFollow(void*) {
    ++followCalls;
    if(changeActorDuringFollow) At<uintptr_t>(0x2A105D0)=g_base+Actor+0x1000;
    if(consume && At<int>(0xAC1528)==0 && At<int>(0x718CA8)==0) {
        At<BYTE>(camera_extra::Controller+64)=0;
        At<BYTE>(camera_extra::Controller+65)=0;
    }
}
void Ready() {
    memset(reinterpret_cast<void*>(g_base),0,0x2C00000); memset(&shared,0,sizeof(shared));
    badContext=held=changeActorDuringFollow=false; consume=true; heldRoll=0;rollCalls=0;
    followCalls=recenterCalls=snapCalls=0; camera_extra::pending={};
    camera_extra::testNow=100000; shared.hostHeartbeat=camera_extra::testNow;
    g_shared=&shared;g_gameThread=GetCurrentThreadId();g_disabled=0;
    camera_extra::testFollow=NativeFollow;camera_extra::testRecenter=NativeRecenter;camera_extra::testSnap=NativeSnap;
    camera_extra::testBeforeSwap=nullptr;
    memcpy(reinterpret_cast<void*>(g_base+0x164860),camera_extra::FollowBytes,sizeof(camera_extra::FollowBytes));
    memcpy(reinterpret_cast<void*>(g_base+0x430B60),camera_extra::RecenterBytes,sizeof(camera_extra::RecenterBytes));
    memcpy(reinterpret_cast<void*>(g_base+0x430B40),camera_extra::SnapBytes,sizeof(camera_extra::SnapBytes));
    memcpy(reinterpret_cast<void*>(g_base+0x165A40),camera_extra::RecenterSetter,sizeof(camera_extra::RecenterSetter));
    memcpy(reinterpret_cast<void*>(g_base+0x165BC0),camera_extra::SnapSetter,sizeof(camera_extra::SnapSetter));
    memcpy(reinterpret_cast<void*>(g_base+0x164E70),camera_extra::ControllerGetter,sizeof(camera_extra::ControllerGetter));
    At<BYTE>(0x9BA8D0)=1;At<int>(0x716884)=1;
    At<uintptr_t>(0x2A105D0)=g_base+Actor;At<uintptr_t>(0x718CB0)=g_base+Actor;
    At<uintptr_t>(Actor+1472)=g_base+Status;At<uint32_t>(Status+616)=Actor;
    At<unsigned>(Actor+0x6C8)=0x80;At<int>(Status)=100;At<uint32_t>(Actor)=ActorController;
    At<uintptr_t>(ActorController)=g_base+ControllerVt;
    At<uintptr_t>(0x716868)=g_base+Scheduler;At<uintptr_t>(0x9BA920)=g_base+Heap;
    At<BYTE>(0x717008)=2;At<BYTE>(0x717009)=3;At<short>(0x71700C)=1;
    At<uintptr_t>(Scheduler+16)=g_base+Node;At<uintptr_t>(Scheduler+24)=g_base+Node;
    At<uintptr_t>(Node)=g_base+0x164860;At<uintptr_t>(Node+88)=g_base+Scheduler;
    At<unsigned>(Node+96)=1;At<int>(Node+100)=26000;
    At<float>(camera_extra::Controller+88)=420;
    At<float>(camera_extra::Camera+72)=10;At<float>(camera_extra::Camera+88)=10;
    At<float>(camera_extra::Camera+80)=5;At<float>(camera_extra::Camera+96)=105;
}
TrainerResult Command(unsigned s,double n=0) {
    double args[8]={n};TrainerResult r{};
    Check(CameraExtraHandle(MakeTrainerContext(),s,args,r),"owned command dispatched");return r;
}
void Frame() {
    At<uintptr_t>(Scheduler+32)=g_base+Node;
    camera_extra::FollowFrame(reinterpret_cast<void*>(g_base+Node));
    At<uintptr_t>(Scheduler+32)=0;
}
bool FlagsClear() { return !At<BYTE>(camera_extra::Controller+64) && !At<BYTE>(camera_extra::Controller+65); }
void ClearSnapshot() { memset(shared.valid,0,sizeof(shared.valid));memset(shared.values,0,sizeof(shared.values)); }
bool Valid(unsigned s) { return (shared.valid[s/64]&(uint64_t(1)<<(s%64)))!=0; }
void NoRequests(const char* label) { Check(!recenterCalls&&!snapCalls&&FlagsClear(),label); }
void Mutation(unsigned kind) {
    switch(kind) {
    case 0: At<BYTE>(0x9BA8D0)=0;break;
    case 1: At<BYTE>(0x9BA8D1)=1;break;
    case 2: At<int>(0x716884)=2;break;
    case 3: At<uintptr_t>(0x9BA928)=g_base+0x40000;break;
    case 4: At<BYTE>(0x9006B0)=1;break;
    case 5: At<uintptr_t>(0xAC0F48)=g_base+0x40000;break;
    case 6: At<int>(0xAC1528)=1;break;
    case 7: At<int>(0x718CA8)=3;break;
    case 8: At<int>(0xAC1838)=1;break;
    case 9: At<BYTE>(0xAC183C)=1;break;
    case 10: At<uintptr_t>(0x718CB0)=g_base+Actor+0x1000;break;
    case 11: At<uintptr_t>(0x2A105D0)=g_base+Actor+0x1000;break;
    case 12: At<uint32_t>(Status+616)=Actor+0x1000;break;
    case 13: At<unsigned>(Actor+0x6C8)=0;break;
    case 14: At<int>(Status)=0;break;
    case 15: At<uint32_t>(Actor)=0;break;
    case 16: At<uintptr_t>(ActorController)=0;break;
    case 17: At<uintptr_t>(0x716868)=0;break;
    case 18: At<uintptr_t>(0x9BA920)=0;break;
    case 19: badContext=true;break;
    case 20: held=true;break;
    case 21: shared.hostHeartbeat=0;break;
    case 22: shared.hostHeartbeat=camera_extra::testNow-5001;break;
    case 23: g_disabled=1;break;
    }
}
void CasRace() { At<uintptr_t>(Node)=g_base+0x445566; }
}
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,0x2C00000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!g_base)return 2;
    for(unsigned slot:{243u,244u}) {
        Ready();Check(Command(slot).code==0,"action queued in valid normal follow");
        Check(camera_extra::pending.action==(slot==243?1u:2u),"exact action remembered");
        NoRequests("enqueue writes no native request flag");
        Check(At<uintptr_t>(Node)==reinterpret_cast<uintptr_t>(camera_extra::FollowFrame),"only selected callback replaced");
        Check(Command(slot).code!=0,"second queued action rejected");Frame();
        Check(followCalls==1 && recenterCalls==(slot==243?1u:0u) && snapCalls==(slot==244?1u:0u),"exact native request and one ordinary update");
        Check(!camera_extra::pending.action&&FlagsClear(),"native flags consumed in same update");
        Frame();Check(followCalls==2&&recenterCalls+snapCalls==1,"no repeat next frame");
        CameraExtraReset(MakeTrainerContext());Check(At<uintptr_t>(Node)==g_base+0x164860,"reset restores current own callback");
        for(unsigned mutation=0;mutation<24;++mutation) {
            Ready();Mutation(mutation);Check(Command(slot).code!=0,"invalid initial scene/context/host rejected");NoRequests("rejection makes no native calls");
            Ready();Check(Command(slot).code==0,"queue before gate loss");Mutation(mutation);Frame();
            Check(followCalls==1&&!camera_extra::pending.action,"gate loss cancels without suppressing native update");NoRequests("gate loss cannot dispatch old request");
        }
        // Identity changes that remain individually valid must also cancel.
        for(unsigned identity=0;identity<7;++identity) {
            Ready();Check(Command(slot).code==0,"queue before valid replacement");
            if(identity==0)At<uintptr_t>(0x9BA920)=g_base+Heap+0x1000;
            if(identity==1)At<BYTE>(0x71700A)=9;
            if(identity==2)At<short>(0x71700C)=8;
            if(identity==3)At<short>(0x71700E)=7;
            if(identity==4)At<short>(0x717010)=6;
            if(identity==5){memcpy(reinterpret_cast<void*>(g_base+Status+0x1000),reinterpret_cast<void*>(g_base+Status),632);At<uintptr_t>(Actor+1472)=g_base+Status+0x1000;}
            if(identity==6){At<uintptr_t>(ActorController+0x1000)=g_base+ControllerVt;At<uint32_t>(Actor)=ActorController+0x1000;}
            Frame();Check(followCalls==1&&!camera_extra::pending.action,"full scene/actor lease rejects valid-looking replacement");NoRequests("replacement never receives old request");
        }
        Ready();Command(slot);CameraExtraReset(MakeTrainerContext());Frame();NoRequests("explicit cancel never fires later");
        Ready();Command(slot);camera_extra::testNow+=1501;shared.hostHeartbeat=camera_extra::testNow;Frame();NoRequests("elapsed timeout cancels request");
        Ready();camera_extra::testNow=0xfffffff0u;shared.hostHeartbeat=camera_extra::testNow;Command(slot);
        camera_extra::testNow=20;shared.hostHeartbeat=20;Frame();Check(recenterCalls+snapCalls==1,"tick wrap preserves short request age");
        Ready();camera_extra::testNow=0xffffff00u;shared.hostHeartbeat=camera_extra::testNow;Command(slot);
        camera_extra::testNow=1600;shared.hostHeartbeat=1600;Frame();NoRequests("tick wrap preserves expired request age");
        Ready();Command(slot);consume=false;Frame();Check(At<BYTE>(camera_extra::Controller+(slot==243?65:64))==1,"post-update native request is not cleared by value equality");
        Ready();Command(slot);consume=false;changeActorDuringFollow=true;Frame();
        Check(At<BYTE>(camera_extra::Controller+(slot==243?65:64))==1,"no cleanup write against changed actor lease");
        Ready();Command(slot);At<BYTE>(camera_extra::Controller+64)=1;Frame();
        Check(!recenterCalls&&!snapCalls,"existing native flag prevents dispatch");
        Ready();Command(slot);++g_gameThread;Frame();Check(followCalls==1&&!recenterCalls&&!snapCalls,"wrong thread calls original only");
        g_gameThread=GetCurrentThreadId();CameraExtraReset(MakeTrainerContext());
        Ready();Command(slot);Mutation(6);CameraExtraTick(MakeTrainerContext());At<int>(0xAC1528)=0;Frame();NoRequests("observed transient ownership loss permanently cancels");
        Ready();Command(slot);Mutation(3);CameraExtraTick(MakeTrainerContext());At<uintptr_t>(0x9BA928)=0;Frame();NoRequests("observed transient transition cannot reopen request");
        Ready();At<BYTE>(camera_extra::Controller+65)=1;Check(Command(slot).code!=0,"preexisting recenter not overwritten");
        Check(At<BYTE>(camera_extra::Controller+65)==1,"preexisting request preserved at command rejection");
    }
    // Entire task list must be valid before any callback can be changed.
    for(unsigned fault=0;fault<12;++fault) {
        Ready();
        if(fault==0){At<uintptr_t>(Scheduler+16)=0;At<uintptr_t>(Scheduler+24)=0;}
        if(fault==1)At<uintptr_t>(Scheduler+32)=g_base+Node;
        if(fault==2)At<uintptr_t>(Node+88)=g_base+Scheduler+0x1000;
        if(fault==3)At<uintptr_t>(Node+128)=g_base+Node;
        if(fault==4)At<uintptr_t>(Node+112)=g_base+0x50000;
        if(fault==5)At<int>(Node+100)=26001;
        if(fault==6)At<unsigned>(Node+96)=3;
        if(fault==7)At<uintptr_t>(Node)=g_base+0x123456;
        if(fault==8)At<uintptr_t>(Scheduler+24)=g_base+Node2;
        if(fault>=9){memcpy(reinterpret_cast<void*>(g_base+Node2),reinterpret_cast<void*>(g_base+Node),152);At<uintptr_t>(Node+120)=g_base+Node2;At<uintptr_t>(Node2+128)=g_base+Node;At<uintptr_t>(Scheduler+24)=g_base+Node2;}
        if(fault==10)At<int>(Node2+100)=25999;
        if(fault==11)At<uintptr_t>(Node2+120)=g_base+Node;
        const uintptr_t before=At<uintptr_t>(Node);Check(Command(243).code!=0,"invalid or ambiguous task list rejected");
        Check(At<uintptr_t>(Node)==before,"bad list never partially patched");NoRequests("bad list performs no native action");
    }
    Ready();camera_extra::testBeforeSwap=CasRace;Check(Command(243).code!=0,"CAS race rejected");
    Check(At<uintptr_t>(Node)==g_base+0x445566&&!camera_extra::pending.action,"concurrent foreign callback retained");
    for(uintptr_t rva:{uintptr_t(0x164860),uintptr_t(0x430B60),uintptr_t(0x430B40),uintptr_t(0x165A40),uintptr_t(0x165BC0),uintptr_t(0x164E70)}) {
        Ready();At<BYTE>(rva)^=1;Check(Command(243).code!=0,"each native function signature required");NoRequests("modified code never dispatched");
    }
    Ready();Command(243);At<uintptr_t>(Node)=g_base+0x777777;CameraExtraReset(MakeTrainerContext());
    Check(At<uintptr_t>(Node)==g_base+0x777777,"reset does not replace foreign callback");
    Ready();Command(243);At<uintptr_t>(Scheduler+32)=g_base+Node;CameraExtraReset(MakeTrainerContext());
    Check(At<uintptr_t>(Node)==reinterpret_cast<uintptr_t>(camera_extra::FollowFrame)&&!camera_extra::pending.action,"reset during iteration disarms without list mutation");
    Ready();DWORD old=0;VirtualProtect(reinterpret_cast<void*>(g_base+Status),4096,PAGE_NOACCESS,&old);
    Check(Command(243).code!=0,"unreadable status rejected");VirtualProtect(reinterpret_cast<void*>(g_base+Status),4096,old,&old);
    Ready();VirtualProtect(reinterpret_cast<void*>(g_base+Node),4096,PAGE_READONLY,&old);
    Check(Command(243).code!=0,"read-only task callback rejected");VirtualProtect(reinterpret_cast<void*>(g_base+Node),4096,old,&old);
    Ready();VirtualProtect(reinterpret_cast<void*>((g_base+camera_extra::Controller)&~uintptr_t(4095)),4096,PAGE_READONLY,&old);
    Check(Command(243).code!=0,"read-only native request flags rejected");VirtualProtect(reinterpret_cast<void*>((g_base+camera_extra::Controller)&~uintptr_t(4095)),4096,old,&old);
    Ready();Check(Command(240,30).code!=0&&!rollCalls,"roll requires held free camera");
    for(double angle:{-180.0,-90.0,0.0,90.0,180.0}) {
        Ready();held=true;Check(Command(240,angle).code==0,"bounded roll accepted");
        Check(rollCalls==1&&fabs(heldRoll-angle*camera_extra::Pi/180)<0.00001,"roll converted once to radians");
        CameraExtraSnapshot(MakeTrainerContext());Check(Valid(240)&&fabs(shared.values[240]-angle)<0.0001,"held roll snapshot immediate");
    }
    for(double angle:{-180.01,180.01,1e30,std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()}) {
        Ready();held=true;Check(Command(240,angle).code!=0&&!rollCalls,"unsafe angle never reaches iterative native normalization");
    }
    Ready();CameraExtraSnapshot(MakeTrainerContext());
    for(unsigned slot:{240u,241u,242u,245u,246u,247u,248u})Check(Valid(slot),"valid camera readout populated");
    Check(shared.values[246]==1&&shared.values[247]==420&&shared.values[248]==100,"follow and pivot distances remain distinct");
    At<int>(0xAC1528)=1;ClearSnapshot();CameraExtraSnapshot(MakeTrainerContext());Check(Valid(241)&&shared.values[241]==1,"script ownership remains readable");
    At<int>(0x718CA8)=99;ClearSnapshot();CameraExtraSnapshot(MakeTrainerContext());Check(!Valid(242)&&Valid(241),"unknown controller submode omitted individually");
    for(float f:{std::numeric_limits<float>::quiet_NaN(),std::numeric_limits<float>::infinity(),100.f}) {
        Ready();At<float>(camera_extra::Camera+120)=f;CameraExtraSnapshot(MakeTrainerContext());Check(!Valid(240)&&Valid(241),"invalid native roll omitted without losing owner");
    }
    Ready();At<float>(camera_extra::Controller+88)=-1;CameraExtraSnapshot(MakeTrainerContext());Check(!Valid(247)&&Valid(248),"negative native follow distance omitted");
    Ready();At<float>(camera_extra::Camera+72)=std::numeric_limits<float>::quiet_NaN();CameraExtraSnapshot(MakeTrainerContext());Check(!Valid(248)&&Valid(240),"invalid vector omits pivot distance");
    Ready();At<BYTE>(0x9BA8D0)=0;CameraExtraSnapshot(MakeTrainerContext());bool none=true;for(unsigned s=240;s<=248;++s)none&=!Valid(s);Check(none,"scene teardown clears fresh snapshot availability");
    CameraExtraCapabilities();bool all=true;for(unsigned s=240;s<=248;++s)all&=(shared.supported[s/64]&(uint64_t(1)<<(s%64)))!=0;
    Check(all,"static capabilities remain implemented when scene absent");
    Check(!(shared.supported[239/64]&(uint64_t(1)<<(239%64)))&&!(shared.supported[249/64]&(uint64_t(1)<<(249%64))),"unowned neighboring slots untouched");
    Ready();for(unsigned s:{241u,242u,245u,246u,247u,248u})Check(Command(s).code==2,"readout slot cannot become write command");
    TrainerResult ignored{};double args[8]{};Check(!CameraExtraHandle(MakeTrainerContext(),249,args,ignored),"unowned command forwarded");
    printf("CameraExtraGuardTests: %u checks, %u failures\n",checks,failures);
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
