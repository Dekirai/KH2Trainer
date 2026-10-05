#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define KH2_MISSION_TESTS
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
void (*onCodeRead)()=nullptr;
bool Readable(const void* p,SIZE_T n) {
    uintptr_t cursor=reinterpret_cast<uintptr_t>(p);
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
#include "../../../trainer/Native/MissionFeatures.inl"
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
    shared.hostHeartbeat=fakeNow; unreadable=unwritable=0; onCodeRead=nullptr;
    calls=0; gotSeconds=0; gotIndex=-1; nativeWrites=true; changeDuringCall=false; nativeReturn=0;
    mission_features::testRestart=Native;
    for(const auto& entry:mission_features::code) memcpy(reinterpret_cast<void*>(g_base+entry.rva),entry.bytes,entry.length);
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
}
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,0x2C00000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(!g_base) return 2;
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
    for(unsigned bit:{1u,2u,4u,8u,16u,0x40000000u,0x80000000u}) { Setup(); At<unsigned>(0xABB854)=bit; Reject("any existing pause owner is preserved"); }
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
    for(unsigned slot=0;slot<512;++slot) Check(((shared.supported[slot/64]>>(slot%64))&1)==(slot>=208&&slot<=229),"capabilities cover only implemented mission slots");
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
    Setup(); double none[8]{}; Check(!MissionHandle(Context(),230,none,result)&&calls==0,"reserved slot falls through");
    printf("Mission guard tests: %u checks, %u failures\n",checks,failures);
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE); return failures?1:0;
}
