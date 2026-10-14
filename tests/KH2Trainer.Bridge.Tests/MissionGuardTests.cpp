#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define KH2_MISSION_TESTS
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>
#include <wchar.h>
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
void (*onCodeRead)()=nullptr;
void (*onComboConfirm)()=nullptr; bool comboReadSeen=false;
bool Readable(const void* p,SIZE_T n) {
    uintptr_t cursor=reinterpret_cast<uintptr_t>(p);
    if(cursor==g_base+0x2A0F8B0+880 && n==88) comboReadSeen=true;
    if(onComboConfirm && comboReadSeen && cursor==g_base+0x2A0F8B0 && n==1708) {
        auto fn=onComboConfirm; onComboConfirm=nullptr; fn();
    }
    if(onCodeRead && cursor==g_base+0x3FB9A0) { auto fn=onCodeRead; onCodeRead=nullptr; fn(); }
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
#define GetTickCount TestTick
namespace world_features { constexpr unsigned missionFreezeMask=0x20000000u; }
#include "../../src/KH2Trainer.Bridge/MissionFeatures.inl"
unsigned checks=0,failures=0,calls=0; int gotSeconds=0,gotIndex=-1;
bool nativeWrites=true,changeDuringCall=false; char nativeReturn=0;
void Check(bool v,const char* name) { ++checks; if(!v){++failures;printf("FAIL: %s\n",name);} }
constexpr uintptr_t actor=0x100000,status=0x101000,descriptor=0x110000,bar=0x111000,storage=0x2A0F8B0;
TrainerContext Context() { return {g_base,g_base+actor,g_base+status,true}; }
// Test replacement for the single native callout. This follows the recorded
// 3FB9A0 -> 3FA5D0 -> 157140/157170 -> 157190 -> 157110 path.
// No game executable code is mapped or called by this harness.
char __fastcall Native(int seconds,int index) {
    ++calls; gotSeconds=seconds; gotIndex=index;
    if(nativeWrites) {
        At<BYTE>(0xABB868)=seconds>0?1:0;
        const int frames=60*(seconds>0?seconds:At<int>(storage+332));
        At<int>(0xABB85C)=frames; At<int>(0xABB860)=seconds>0?frames:0;
        At<uint32_t>(0xABB858)=At<uint32_t>(0xABB850);
        At<int>(0xABB864)=1; At<unsigned>(0xABB854)&=~2u;
    }
    if(changeDuringCall) ++At<unsigned>(storage);
    return nativeReturn;
}
void Setup(unsigned mode=1) {
    ZeroMemory(reinterpret_cast<void*>(g_base),0x2C00000); ZeroMemory(&shared,sizeof(shared));
    g_gameThread=GetCurrentThreadId(); g_disabled=0; g_shared=&shared; fakeNow=100000;
    shared.hostHeartbeat=fakeNow; unreadable=unwritable=0; onCodeRead=nullptr; onComboConfirm=nullptr; comboReadSeen=false;
    calls=0; gotSeconds=0; gotIndex=-1; nativeWrites=true; changeDuringCall=false; nativeReturn=0;
    mission_features::testRestart=Native; mission_features::freeze={};
    for(const auto& entry:mission_features::code) memcpy(reinterpret_cast<void*>(g_base+entry.rva),entry.bytes,entry.length);
    for(const auto& entry:mission_features::freezeCode) memcpy(reinterpret_cast<void*>(g_base+entry.rva),entry.bytes,entry.length);
    At<BYTE>(0x9BA8D0)=1; At<int>(0x716884)=1;
    At<uintptr_t>(0x9BA920)=g_base+0x130000; At<uintptr_t>(0x716868)=g_base+0x131000; At<uintptr_t>(0x9BA888)=g_base+0x132000;
    At<uintptr_t>(0x2A105D0)=g_base+actor;
    At<uintptr_t>(actor+1472)=g_base+status; At<unsigned>(actor+1736)=0x1000080;
    At<int>(status)=100; At<int>(status+4)=120; At<int>(status+608)=1; At<uint32_t>(status+616)=actor;
    At<uintptr_t>(0x2A0FF68)=g_base+storage; At<uintptr_t>(0x2A0FF70)=g_base+descriptor;
    At<unsigned>(storage)=42; At<unsigned>(storage+4)=1;
    At<uintptr_t>(storage+8)=g_base+descriptor; At<uintptr_t>(storage+96)=g_base+bar;
    At<int>(storage+1072)=1; At<int>(storage+1048)=7;
    At<uintptr_t>(storage+976)=g_base+storage+296;
    At<uintptr_t>(storage+296)=g_base+0x5C4208; At<unsigned>(storage+320)=5;
    At<int>(storage+324)=0; At<int>(storage+328)=120; At<int>(storage+332)=180;
    for(unsigned i=0;i<3;++i) {
        const uintptr_t count=storage+352+80*i,gauge=storage+592+72*i;
        At<uintptr_t>(storage+984+16*i)=g_base+count; At<uintptr_t>(storage+992+16*i)=g_base+gauge;
        At<uintptr_t>(count)=g_base+0x5C4248; At<unsigned>(count+24)=5; At<int>(count+28)=static_cast<int>(i);
        At<int>(count+32)=0; At<int>(count+36)=100+static_cast<int>(i); At<int>(count+56)=10+static_cast<int>(i);
        At<uintptr_t>(gauge)=g_base+0x5C4288; At<unsigned>(gauge+24)=5; At<int>(gauge+28)=static_cast<int>(i);
        At<int>(gauge+32)=0; At<int>(gauge+36)=200+static_cast<int>(i); At<float>(gauge+56)=20.5f+static_cast<float>(i);
    }
    At<uintptr_t>(storage+1088)=g_base+0x5C9E38; At<unsigned>(storage+1112)=5;
    At<int>(storage+1124)=9999; At<int>(storage+1144)=321;
    At<uint32_t>(0xABB850)=1234; At<uint32_t>(0xABB858)=1000;
    At<int>(0xABB85C)=7200; At<int>(0xABB860)=123; At<int>(0xABB864)=2; At<BYTE>(0xABB868)=static_cast<BYTE>(mode);
}
TrainerResult Command(unsigned slot,double value=0,const TrainerContext* alternate=nullptr) {
    double args[8]{value}; TrainerResult r{}; auto c=alternate?*alternate:Context();
    Check(MissionHandle(c,slot,args,r),"known mission command handled"); return r;
}
bool Has(unsigned slot) { return (shared.valid[slot/64]&(uint64_t(1)<<(slot%64)))!=0; }
void Reject(const char* name,unsigned slot=226,double value=90,const TrainerContext* context=nullptr) {
    const int before=At<int>(0xABB860),phase=At<int>(0xABB864); const BYTE mode=At<BYTE>(0xABB868);
    Check(Command(slot,value,context).code!=0 && calls==0,name);
    Check(At<int>(0xABB860)==before && At<int>(0xABB864)==phase && At<BYTE>(0xABB868)==mode,"rejected request leaves clock untouched");
}
void ChangeMission() { ++At<unsigned>(storage); }
void ChangeDescriptor() { At<uintptr_t>(storage+8)=g_base+descriptor+64; At<uintptr_t>(0x2A0FF70)=g_base+descriptor+64; }
void ChangeRoom() { At<BYTE>(0x71700D)^=1; }
void ChangeClock() { ++At<uint32_t>(0xABB858); }
void ChangeMaximum() { ++At<int>(storage+332); }
void Expire() { shared.hostHeartbeat=0; }
void LosePlayer() { At<uintptr_t>(0x2A105D0)+=16; }
void EndMission() { At<unsigned>(storage+4)|=4; }
void SetupCombo() {
    Setup(); At<int>(storage+1048)=8; At<uintptr_t>(storage+976+7*8)=g_base+storage+880;
    const uintptr_t p=storage+880;
    At<uintptr_t>(p)=g_base+0x5C9DF8; At<unsigned>(p+24)=5; At<int>(p+28)=0;
    At<int>(p+36)=100; At<int>(p+56)=12; At<int>(p+80)=30; At<float>(p+84)=45.5f;
}
void CheckComboAbsent(const char* name) {
    MissionSnapshot(Context()); Check(!Has(479)&&!Has(480)&&!Has(481)&&calls==0,name);
}
void ComboTests() {
    Setup(); CheckComboAbsent("unregistered constructor combo has no readout");
    SetupCombo(); MissionSnapshot(Context());
    Check(Has(479)&&Has(480)&&Has(481)&&shared.values[479]==12&&shared.values[480]==30&&shared.values[481]==45.5&&calls==0,
        "combo publishes exact integer current/peak and unscaled native float units without callback");
    for(float allowance:{-1000.f,-0.f,0.f,0.125f,std::numeric_limits<float>::max(),std::numeric_limits<float>::lowest()}) {
        SetupCombo();At<float>(storage+880+84)=allowance;MissionSnapshot(Context());
        Check(Has(481)&&shared.values[481]==static_cast<double>(allowance)&&signbit(shared.values[481])==signbit(allowance),
            "all finite native allowances preserved including negative values and signed zero");
    }
    for(int peak:{0,1,INT32_MAX}) {
        SetupCombo();At<int>(storage+880+80)=peak;MissionSnapshot(Context());
        Check(Has(480)&&shared.values[480]==peak,"peak is independent of current and configured maximum");
    }
    SetupCombo();At<int>(storage+880+36)=INT32_MAX;At<int>(storage+880+56)=INT32_MAX;MissionSnapshot(Context());
    Check(Has(479)&&shared.values[479]==INT32_MAX,"full signed integer current range is read exactly");
    SetupCombo();At<int>(storage+880+36)=0;At<int>(storage+880+56)=0;MissionSnapshot(Context());
    Check(Has(479)&&shared.values[479]==0,"configured zero maximum is valid read-only state");
    SetupCombo();At<int>(0x716884)=2;At<unsigned>(0xABB854)=2;MissionSnapshot(Context());
    Check(Has(479)&&Has(481),"combo readout remains available while native field and timer are paused");
    SetupCombo();At<unsigned>(storage+880+24)=1;unwritable=g_base+storage+880;MissionSnapshot(Context());
    Check(Has(479)&&Has(481)&&calls==0,"registered inactive combo is readable and requires no writable memory");
    for(unsigned field:{36u,56u,80u}) {SetupCombo();At<int>(storage+880+field)=-1;CheckComboAbsent("negative max/current/peak rejected as unsupported counter state");}
    SetupCombo();At<int>(storage+880+56)=101;CheckComboAbsent("current beyond configured bound rejected");
    for(float invalid:{std::numeric_limits<float>::quiet_NaN(),std::numeric_limits<float>::infinity(),-std::numeric_limits<float>::infinity()}) {
        SetupCombo();At<float>(storage+880+84)=invalid;CheckComboAbsent("nonfinite allowance rejects whole combo group");
    }
    SetupCombo();At<uintptr_t>(storage+880)=g_base+0x5C4248;CheckComboAbsent("wrong combo class rejected");
    for(int id:{-1,1,INT32_MAX}){SetupCombo();At<int>(storage+880+28)=id;CheckComboAbsent("only registered combo zero is accepted");}
    SetupCombo();At<unsigned>(storage+880+24)=0;CheckComboAbsent("uninitialized combo rejected");
    SetupCombo();At<uintptr_t>(storage+976+7*8)=g_base+storage+808;CheckComboAbsent("inline combo missing from registry rejected");
    SetupCombo();At<uintptr_t>(storage+976)=g_base+storage+880;CheckComboAbsent("duplicate registration rejected");
    for(int phase:{0,2,3,4}){SetupCombo();At<int>(storage+1072)=phase;CheckComboAbsent("combo readout requires active mission phase");}
    for(unsigned flags:{0u,5u,17u}){SetupCombo();At<unsigned>(storage+4)=flags;CheckComboAbsent("inactive/finishing mission has no combo readout");}
    SetupCombo();g_gameThread=0;CheckComboAbsent("combo readout requires game thread");
    SetupCombo();shared.hostHeartbeat=0;CheckComboAbsent("combo readout requires live host");
    SetupCombo();fakeNow+=5001;CheckComboAbsent("expired host has no combo readout");
    SetupCombo();At<uintptr_t>(storage+8)+=16;CheckComboAbsent("descriptor mirror mismatch suppresses combo");
    SetupCombo();unreadable=g_base+storage+967;CheckComboAbsent("whole combo footprint must be readable");
    for(unsigned drift=0;drift<10;++drift) {
        SetupCombo();
        if(drift==0)onComboConfirm=ChangeMission;
        if(drift==1)onComboConfirm=ChangeDescriptor;
        if(drift==2)onComboConfirm=ChangeRoom;
        if(drift==3)onComboConfirm=Expire;
        if(drift==4)onComboConfirm=EndMission;
        if(drift==5)onComboConfirm=[](){++At<int>(storage+880+56);};
        if(drift==6)onComboConfirm=[](){++At<int>(storage+880+80);};
        if(drift==7)onComboConfirm=[](){++At<int>(storage+880+36);};
        if(drift==8)onComboConfirm=[](){At<unsigned>(storage+880+24)^=4;};
        if(drift==9){At<float>(storage+880+84)=0.f;onComboConfirm=[](){At<float>(storage+880+84)=-0.f;};}
        CheckComboAbsent("fresh combo identity/fields/host validation rejects drift including signed-zero bit change");
        Check(!onComboConfirm,"drift hook executed between first capture and confirmation");
    }
    for(unsigned slot=479;slot<=481;++slot) {SetupCombo();Check(Command(slot,1).code!=0&&calls==0,"combo slot strictly read-only");}
}
constexpr unsigned freezeBit=world_features::missionFreezeMask;
// Native call sites own 1/2/4/8/16; the field pause owns 0x40000000.
constexpr unsigned foreignOwners[]={0u,1u,2u,4u,8u,16u,0x40000000u,0x80000000u,0x4000001Fu};
unsigned& Mask() { return At<unsigned>(0xABB854); }
bool Owned() { return mission_features::freeze.owned; }
TrainerResult Freeze(double value,const TrainerContext* alternate=nullptr) { return Command(233,value,alternate); }
double Published() {
    ZeroMemory(shared.valid,sizeof(shared.valid)); MissionSnapshot(Context());
    return Has(233)?shared.values[233]:-1;
}
bool ClockUntouched() {
    return At<uint32_t>(0xABB850)==1234 && At<uint32_t>(0xABB858)==1000 && At<int>(0xABB85C)==7200 &&
        At<int>(0xABB860)==123 && calls==0;
}
void Held(unsigned owners,const char* name) {
    Check(Freeze(1).code==0 && Owned() && Mask()==(owners|freezeBit) && ClockUntouched() && Published()==1,name);
}
void RefuseFreeze(const char* name,const TrainerContext* context=nullptr,double value=1) {
    const unsigned before=Mask();
    Check(Freeze(value,context).code!=0 && !Owned() && Mask()==before && ClockUntouched(),name);
}
void ChangeHeap() { At<uintptr_t>(0x9BA920)=g_base+0x134000; }
void ChangeFieldScheduler() { At<uintptr_t>(0x716868)=g_base+0x135000; }
void ChangeOuterScheduler() { At<uintptr_t>(0x9BA888)=g_base+0x136000; }
void EndPhase() { At<int>(storage+1072)=2; }
void Disable() { g_disabled=1; }
void LoseMission() { At<uintptr_t>(0x2A0FF68)=0; }
void FreezeTests() {
    for(unsigned mode:{0u,1u}) for(int phase:{1,2}) {
        Setup(mode); At<int>(0xABB864)=phase;
        Held(0,"countdown or count-up freeze owns only the private clock owner bit without a native call");
        Check(At<int>(0xABB864)==phase && At<BYTE>(0xABB868)==mode,"freeze keeps clock phase and direction");
        for(unsigned i=0;i<3;++i) MissionTick(Context());
        Check(Owned() && Mask()==freezeBit && ClockUntouched(),"tick keeps the freeze in the same mission");
        const auto r=Freeze(0);
        Check(r.code==0 && !Owned() && Mask()==0 && ClockUntouched() && Published()==0,"disable clears only the private bit and resumes the held clock");
    }
    for(unsigned owners:foreignOwners) {
        Setup(); Mask()=owners; Held(owners,"freeze is taken alongside native and field pause owners");
        Check(Published()==1,"published freeze state follows the owned bit");
        Check(Freeze(0).code==0 && !Owned() && Mask()==owners,"disable preserves every native and field pause owner");
        Setup(); Mask()=owners; Freeze(1); MissionReset(Context());
        Check(!Owned() && Mask()==owners,"Disable All and failure reset clear only the private bit");
        Setup(); Mask()=owners; Freeze(1); const TrainerContext failure{g_base,0,0,false}; MissionReset(failure);
        Check(!Owned() && Mask()==owners,"failure reset without a scene context still releases the clock");
        for(auto change:{ChangeMission,ChangeDescriptor,ChangeRoom,ChangeHeap,ChangeFieldScheduler,ChangeOuterScheduler,EndPhase,Expire,Disable,LoseMission}) {
            Setup(); Mask()=owners; Freeze(1); change(); MissionTick(Context());
            Check(!Owned() && Mask()==owners,"mission, room, heap, scheduler, phase, host or bridge change releases only the private bit");
            MissionTick(Context()); Check(!Owned() && Mask()==owners,"a released freeze is never re-asserted");
        }
        Setup(); Mask()=owners; Freeze(1); auto unready=Context(); unready.sceneReady=false; MissionTick(unready);
        Check(!Owned() && Mask()==owners,"unready scene releases the freeze");
        Setup(); Mask()=owners; Freeze(1); fakeNow+=5001; MissionTick(Context());
        Check(!Owned() && Mask()==owners,"heartbeat timeout releases the freeze");
        // 157040/157090 zero the whole mask on clock init/reset.
        Setup(); Mask()=owners; Freeze(1); Mask()=0; Check(Published()==0,"vanished bit is not reported as held");
        MissionTick(Context()); Check(!Owned() && Mask()==0,"native mask reset ends ownership without re-asserting");
        Mask()=owners; MissionTick(Context()); MissionReset(Context());
        Check(Mask()==owners && !Owned(),"owners set after a native reset are never cleared by a lost lease");
    }
    for(unsigned byte=0;byte<10;++byte) {
        Setup(); Freeze(1); At<BYTE>(0x717008+byte)^=0x80; MissionTick(Context());
        Check(!Owned() && Mask()==0,"every room byte belongs to the freeze lease");
    }
    for(int phase:{0,2,3,4}) { Setup(); Freeze(1); At<int>(storage+1072)=phase; MissionTick(Context()); Check(!Owned() && Mask()==0,"ended mission phase releases the freeze"); }
    Setup(); Freeze(1); Mask()|=4; MissionTick(Context()); Mask()&=~4u; MissionTick(Context());
    Check(Owned() && Mask()==freezeBit,"native owners may come and go during the freeze");
    Setup(); Freeze(1); At<int>(0x716884)=2; At<int>(storage+1048)=6; At<unsigned>(storage+4)|=4; At<int>(0xABB864)=0; MissionTick(Context());
    Check(Owned() && Mask()==freezeBit,"field state, widget registry, mission flags and clock phase are not part of the lease");
    Setup(); Freeze(1); const auto again=Freeze(1);
    Check(again.code==0 && Owned() && Mask()==freezeBit && wcsstr(again.text,L"already"),"repeated enable keeps one lease");
    Setup(); Freeze(1); ChangeMission(); Check(Freeze(1).code==0 && Owned() && mission_features::freeze.id==43 && Mask()==freezeBit,
        "a new request in a later mission drops the stale lease before taking a new one");
    MissionTick(Context()); Check(Owned() && Mask()==freezeBit,"the replacement lease belongs to the current mission");
    Setup(); const auto idle=Freeze(0); Check(idle.code==0 && !Owned() && Mask()==0,"disable without a lease changes nothing");
    // A set bit that the trainer does not own is never claimed, cleared or reported.
    for(unsigned owners:{freezeBit,freezeBit|2u}) {
        Setup(); Mask()=owners; const auto r=Freeze(1);
        Check(r.code!=0 && !Owned() && Mask()==owners && wcsstr(r.text,L"already set"),"foreign private bit is refused");
        Freeze(0); MissionTick(Context()); MissionReset(Context());
        Check(Mask()==owners && Published()==0,"unowned private bit survives disable, tick and reset");
    }
    Setup(); LoseMission(); RefuseFreeze("absent mission refuses the freeze");
    Check(Published()==0 && !Has(208),"freeze state is published even without a mission");
    for(int phase:{0,2,3,4}) { Setup(); At<int>(storage+1072)=phase; RefuseFreeze("inactive mission phase refuses the freeze"); }
    for(int phase:{-1,0,3}) { Setup(); At<int>(0xABB864)=phase; RefuseFreeze("stopped or invalid clock phase refuses the freeze"); }
    Setup(); At<BYTE>(0xABB868)=2; RefuseFreeze("invalid clock direction refuses the freeze");
    Setup(); At<unsigned>(storage+320)=1; RefuseFreeze("inactive timer refuses the freeze");
    Setup(); At<uintptr_t>(storage+296)=g_base+0x5C4248; RefuseFreeze("wrong timer class refuses the freeze");
    Setup(); At<uintptr_t>(storage+976)=g_base+storage+808; RefuseFreeze("unregistered timer refuses the freeze");
    for(const auto& entry:mission_features::freezeCode) {
        Setup(); At<BYTE>(entry.rva)^=1; RefuseFreeze("changed first byte of a clock mask leaf refuses the freeze");
        Setup(); At<BYTE>(entry.rva+entry.length-1)^=1; RefuseFreeze("changed last byte of a clock mask leaf refuses the freeze");
        Setup(); unreadable=g_base+entry.rva+entry.length-1; RefuseFreeze("unreadable clock mask leaf refuses the freeze");
    }
    Setup(); At<BYTE>(0x3FB9A0)^=1; Held(0,"restart-only code is not a freeze requirement");
    Setup(); unwritable=g_base+0xABB854; RefuseFreeze("read-only clock owner mask refuses the freeze");
    Setup(); g_gameThread=GetCurrentThreadId()+1; RefuseFreeze("worker thread cannot freeze");
    Setup(); g_disabled=1; RefuseFreeze("disabled bridge cannot freeze");
    Setup(); fakeNow+=5001; RefuseFreeze("expired host cannot freeze");
    Setup(); auto context=Context(); context.sceneReady=false; RefuseFreeze("unready scene cannot freeze",&context);
    Setup(); context=Context(); ++context.base; RefuseFreeze("wrong base cannot freeze",&context);
    for(double bad:{-1.0,2.0,0.5,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}) {
        Setup(); RefuseFreeze("invalid freeze value refused",nullptr,bad);
        Setup(); Freeze(1); Check(Freeze(bad).code!=0 && Owned() && Mask()==freezeBit,"invalid value never changes a held freeze");
    }
    // The restart gate refuses every clock owner and names the trainer's own.
    for(unsigned slot:{226u,227u}) {
        Setup(); Freeze(1); const auto r=Command(slot,90);
        Check(r.code!=0 && calls==0 && wcsstr(r.text,L"Release the mission clock freeze first") && Owned() && Mask()==freezeBit,
            "restart is refused with a named reason while the trainer freezes the clock");
        Freeze(0); Check(Command(slot,90).code==0 && calls==1,"restart works again after release");
    }
    Setup(); Mask()=freezeBit; const auto foreign=Command(226,90);
    Check(foreign.code!=0 && calls==0 && !wcsstr(foreign.text,L"Release the mission clock freeze"),"unowned private bit keeps the general restart refusal");
    Setup(); Freeze(1); MissionSnapshot(Context()); Check(shared.values[229]==1,"paused readout includes the trainer's clock owner");
}
}
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,0x2C00000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(!g_base) return 2;
    ComboTests();
    FreezeTests();
    for(unsigned mode:{0u,1u}) for(int phase:{1,2}) for(int seconds:{1,90,3599}) {
        Setup(mode); At<int>(0xABB864)=phase; const auto r=Command(226,seconds);
        Check(r.code==0 && calls==1 && gotSeconds==seconds && gotIndex==0,"countdown restarts or changes direction through exactly one native call");
        Check(At<BYTE>(0xABB868)==1 && At<int>(0xABB864)==1 && At<int>(0xABB85C)==seconds*60 && At<int>(0xABB860)==seconds*60,"native countdown mode/state/display/duration confirmed");
        Check(At<uint32_t>(0xABB858)==1234 && At<unsigned>(storage+4)==1,"restart captures native clock origin without mission flags edit");
    }
    for(unsigned mode:{0u,1u}) for(int phase:{1,2}) for(int limit:{0,1,180,3599,3600,35791394}) {
        Setup(mode); At<int>(0xABB864)=phase; At<int>(storage+332)=limit; nativeReturn=1;
        const auto r=Command(227);
        Check(r.code==0 && calls==1 && gotSeconds==0 && gotIndex==0,"count-up restarts or changes direction with exact native zero argument");
        Check(At<BYTE>(0xABB868)==0 && At<int>(0xABB864)==1 && At<int>(0xABB85C)==limit*60 && At<int>(0xABB860)==0,"count-up preserves configured limit including unlimited zero");
    }
    Setup(); At<int>(status+608)=2; Check(Command(226,60).code==0,"living Roxas/other supported player is not artificially excluded");
    Setup(); At<uint32_t>(0xABB850)=0xfffffff0; Check(Command(226,60).code==0 && At<uint32_t>(0xABB858)==0xfffffff0,"native wrapping tick counter is preserved");
    for(double bad:{0.0,-1.0,3600.0,1.5,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}) { Setup(); Reject("invalid countdown rejected",226,bad); }
    Setup(); double args[8]{}; args[7]=std::numeric_limits<double>::quiet_NaN(); TrainerResult result{};
    Check(MissionHandle(Context(),227,args,result)&&result.code!=0&&calls==0,"nonfinite extra argument rejected");
    for(int bad:{-1,35791395,INT_MAX}) { Setup(); At<int>(storage+332)=bad; Reject("count-up configured limit is bounded before multiply",227); }
    Setup(); At<int>(storage+332)=INT_MAX; Check(Command(226,60).code==0,"countdown does not impose an unrelated configured count-up limit");
    for(unsigned i:{0u,7u}) { Setup(); At<BYTE>(0xABB868)=static_cast<BYTE>(i+2); Reject("invalid native direction rejected"); }
    for(int phase:{-1,0,3}) { Setup(); At<int>(0xABB864)=phase; Reject("stopped or invalid clock cannot be resurrected"); }
    for(unsigned bit:{1u,2u,4u,8u,16u,0x20000000u,0x40000000u,0x80000000u}) { Setup(); At<unsigned>(0xABB854)=bit; Reject("any existing pause owner is preserved"); }
    for(unsigned bit:{4u,16u}) { Setup(); At<unsigned>(storage+4)|=bit; Reject("ending mission rejected"); }
    for(int phase:{0,2,3,4,5,-1}) { Setup(); At<int>(storage+1072)=phase; Reject("unstable mission phase rejected"); }
    Setup(); At<unsigned>(storage+4)=0; Reject("mission controls not activated");
    for(unsigned flags:{0u,1u,4u,0x15u}) { Setup(); At<unsigned>(storage+320)=flags; Reject("timer must be initialized active and not hidden/disabled"); }
    Setup(); At<int>(storage+324)=-1; Reject("unconfigured constructor timer ID rejected");
    Setup(); At<uintptr_t>(storage+296)=g_base+0x5C4248; Reject("wrong timer class rejected");
    for(int count:{-1,0,10}) { Setup(); At<int>(storage+1048)=count; Reject("absent or corrupt widget registry rejected"); }
    Setup(); At<uintptr_t>(storage+976)=g_base+storage+808; Reject("timer must be registered, not merely initialized");
    Setup(); At<uintptr_t>(storage+984)=At<uintptr_t>(storage+976); Reject("duplicate registry rejected");
    Setup(); At<uintptr_t>(storage+984)=g_base+storage+297; Reject("unaligned/foreign registry entry rejected");
    for(uintptr_t rva:std::initializer_list<uintptr_t>{0x2A0FF68u,0x2A0FF70u,storage+8,storage+96,0x9BA920u,0x716868u,0x9BA888u}) { Setup(); At<uintptr_t>(rva)=0; Reject("missing mission/resource/scheduler rejected"); }
    Setup(); At<uintptr_t>(0x2A0FF68)=g_base+storage+8; Reject("foreign mission allocation rejected");
    Setup(); At<uintptr_t>(storage+8)=g_base+descriptor+64; Reject("descriptor mirror mismatch rejected");
    for(uintptr_t rva:std::initializer_list<uintptr_t>{0x9BA8D1u,0x9006B0u,0xABAC58u,0xABAC59u,0xABADE0u}) { Setup(); At<BYTE>(rva)=1; Reject("menu/title/event/capture scene blocked"); }
    for(uintptr_t rva:std::initializer_list<uintptr_t>{0x9BA928u,0xAC0F48u,0x2A11478u,0x2AE8050u,0x2AE9FA8u}) { Setup(); At<uintptr_t>(rva)=1; Reject("pending scene/form/native cinematic/gameover rejected"); }
    Setup(); At<unsigned>(0x2A10504)=2; Reject("native form transition lock rejected");
    for(int phase:{0,2,3}) { Setup(); At<int>(0x716884)=phase; Reject("only stable running field accepts mutation"); }
    Setup(); At<BYTE>(0x9BA8D0)=0; Reject("native scene not ready");
    Setup(); auto context=Context(); context.sceneReady=false; Reject("unready shared context rejected",226,60,&context);
    Setup(); context=Context(); ++context.base; Reject("wrong base rejected",226,60,&context);
    Setup(); context=Context(); context.player=0; Reject("missing current actor rejected",226,60,&context);
    for(uintptr_t rva:std::initializer_list<uintptr_t>{0x2A105D0u,actor+1472}) { Setup(); At<uintptr_t>(rva)=0; Reject("stale actor/status context rejected"); }
    Setup(); At<uint32_t>(status+616)=0; Reject("status backlink rejected");
    for(int hp:{0,121}) { Setup(); At<int>(status)=hp; Reject("dead or corrupt HP rejected"); }
    Setup(); At<int>(status+4)=256; Reject("out-of-range maximum HP rejected");
    for(int id:{0,16}) { Setup(); At<int>(status+608)=id; Reject("invalid player ID rejected"); }
    Setup(); At<unsigned>(actor+1736)=0; Reject("inactive player rejected");
    for(unsigned bit:{0x10000000u,0x80000u,0x100u}) { Setup(); At<unsigned>(actor+288)=bit; Reject("native death/removal state rejected"); }
    Setup(); At<unsigned>(actor+2488)=4; Reject("disabled actor rejected");
    Setup(); g_gameThread=GetCurrentThreadId()+1; Reject("worker thread cannot restart");
    Setup(); g_gameThread=0; Reject("unset game thread cannot restart");
    Setup(); g_disabled=1; Reject("disabled bridge cannot restart");
    Setup(); shared.hostHeartbeat=0; Reject("zero heartbeat cannot restart");
    Setup(); fakeNow+=5001; Reject("expired heartbeat cannot restart");
    Setup(); g_shared=nullptr; Reject("missing host cannot restart");
    Setup(); fakeNow=0x20; shared.hostHeartbeat=0xfffffff0; Check(Command(226,90).code==0,"fresh heartbeat handles tick wrap");
    for(uintptr_t rva:std::initializer_list<uintptr_t>{storage+1707,descriptor+27,bar+15,actor+3607,status+631,0x131047u}) { Setup(); unreadable=g_base+rva; Reject("entire accessed object range must be readable"); }
    for(uintptr_t rva:std::initializer_list<uintptr_t>{0xABB854u,0xABB858u,0xABB85Cu,0xABB860u,0xABB864u,0xABB868u}) { Setup(); unwritable=g_base+rva; Reject("native destination range must be writable"); }
    for(const auto& entry:mission_features::code) {
        Setup(); At<BYTE>(entry.rva+entry.length-1)^=1; Reject("native function tail mutation rejected");
        Setup(); unreadable=g_base+entry.rva+entry.length-1; Reject("native complete function must be readable");
    }
    for(auto fn:{ChangeMission,ChangeDescriptor,ChangeRoom,ChangeClock,ChangeMaximum,Expire,LosePlayer,EndMission}) {
        Setup(); onCodeRead=fn; Check(Command(226,90).code!=0&&calls==0,"identity/timer/host change during preflight cannot dispatch");
    }
    Setup(); nativeWrites=false; Check(Command(226,90).code==2 && calls==1,"unconfirmed native outcome is not reported as success");
    MissionTick(Context()); Check(calls==1,"uncertain result never retries on tick");
    Setup(); changeDuringCall=true; Check(Command(226,90).code==2&&calls==1&&At<int>(0xABB860)==5400,"mission change after call is unconfirmed without rollback/retry");
    Setup(); Command(226,90); MissionReset(Context()); MissionTick(Context());
    Check(At<int>(0xABB860)==5400&&calls==1,"disable-all leaves one-time native restart intact");
    Setup(); MissionCapabilities();
    for(unsigned slot=0;slot<512;++slot) Check(((shared.supported[slot/64]>>(slot%64))&1)==((slot>=208&&slot<=229)||slot==233||(slot>=479&&slot<=481)),"capabilities cover only implemented mission slots");
    Setup(); MissionSnapshot(Context());
    for(unsigned slot=208;slot<=229;++slot) Check(Has(slot)==(slot!=226&&slot!=227),"only valid data has a snapshot value");
    Check(shared.values[208]==42&&shared.values[209]==1&&shared.values[210]==2.05&&shared.values[228]==120&&shared.values[229]==0,"mission and clock readouts use correct offsets/timebase");
    for(unsigned i=0;i<3;++i) {
        Check(shared.values[213+2*i]==10+i&&shared.values[214+2*i]==100+i,"counter readouts use stride80");
        Check(shared.values[219+2*i]==20.5+i&&shared.values[220+2*i]==200+i,"gauge readouts use stride72 and float values");
    }
    Check(shared.values[225]==321,"score uses separate native score object");
    Setup(); At<unsigned>(0xABB854)=2; At<int>(0x716884)=2; MissionSnapshot(Context());
    Check(Has(210)&&shared.values[229]==1,"readouts remain available while field and clock paused");
    Setup(); At<int>(0xABB864)=0; MissionSnapshot(Context()); Check(Has(212)&&shared.values[212]==0,"stopped timer remains a truthful readout");
    Setup(); At<int>(storage+1048)=0; MissionSnapshot(Context()); Check(Has(208)&&!Has(210)&&!Has(213)&&!Has(219),"unused inline widgets never publish stale values");
    Setup(); At<int>(storage+352+28)=-1; MissionSnapshot(Context()); Check(!Has(213)&&Has(215),"invalid counter does not invalidate unrelated valid counter");
    Setup(); At<float>(storage+592+56)=std::numeric_limits<float>::quiet_NaN(); MissionSnapshot(Context()); Check(!Has(219)&&Has(221),"nonfinite gauge suppressed independently");
    Setup(); At<int>(storage+352+56)=101; MissionSnapshot(Context()); Check(!Has(213),"out-of-range counter suppressed");
    Setup(); At<int>(storage+1144)=10000; MissionSnapshot(Context()); Check(!Has(225),"out-of-range score suppressed");
    Setup(); At<uintptr_t>(0x2A0FF68)=0; MissionSnapshot(Context()); Check(!Has(208)&&!Has(210),"absent mission has no fabricated zero values");
    Setup(); g_gameThread=0; MissionSnapshot(Context()); Check(!Has(208),"worker snapshot is rejected");
    for(unsigned slot=208;slot<=229;++slot) if(slot!=226&&slot!=227) { Setup(); Check(Command(slot).code!=0&&calls==0,"read-only slot cannot mutate"); }
    Setup(); double none[8]{};
    for(unsigned slot:{207u,230u,232u,234u,478u,482u}) Check(!MissionHandle(Context(),slot,none,result)&&calls==0,"slots outside the mission handler fall through");
    printf("Mission guard tests: %u checks, %u failures\n",checks,failures);
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE); return failures?1:0;
}
