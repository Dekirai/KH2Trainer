#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdint.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <initializer_list>
#include <limits>
namespace {
uintptr_t g_base=0; DWORD g_gameThread=0; volatile LONG g_disabled=0;
struct TrainerContext { uintptr_t base,player,status; bool sceneReady; } context{};
struct TrainerResult { LONG code; const wchar_t* text; };
struct Shared { DWORD hostHeartbeat; double values[512]; uint64_t valid[8],supported[8]; } shared{};
Shared* g_shared=&shared;
template<class T>T& At(uintptr_t rva){return *reinterpret_cast<T*>(g_base+rva);}
bool Readable(const void* p,size_t size) {
    MEMORY_BASIC_INFORMATION m{};
    return p && reinterpret_cast<uintptr_t>(p)<=UINTPTR_MAX-size && VirtualQuery(p,&m,sizeof(m)) &&
        m.State==MEM_COMMIT && !(m.Protect&(PAGE_GUARD|PAGE_NOACCESS)) &&
        reinterpret_cast<uintptr_t>(p)+size<=reinterpret_cast<uintptr_t>(m.BaseAddress)+m.RegionSize;
}
bool Writable(const void* p,size_t size) { MEMORY_BASIC_INFORMATION m{};return Readable(p,size)&&VirtualQuery(p,&m,sizeof(m))&&m.Protect==PAGE_READWRITE; }
uintptr_t DecodePacked(uint32_t p){return p?g_base+p:0;}
bool IsInteger(double v,double lo,double hi){return isfinite(v)&&floor(v)==v&&v>=lo&&v<=hi;}
void SnapshotValue(unsigned s,double v){shared.values[s]=v;shared.valid[s/64]|=uint64_t(1)<<(s%64);}
void SupportCapability(unsigned s){shared.supported[s/64]|=uint64_t(1)<<(s%64);}
#include "../../../trainer/Native/CombatFeatures.inl"
#include "../../../trainer/Native/DamageTuningFeatures.inl"
#include "../../../trainer/Native/ActorMovementFeatures.inl"
bool injectCasRace=false;
LONG CollisionTestCas(volatile LONG* p,LONG replacement,LONG expected) {
    if(injectCasRace){*p^=0x4000;injectCasRace=false;}
    return InterlockedCompareExchange(p,replacement,expected);
}
#pragma push_macro("InterlockedCompareExchange")
#undef InterlockedCompareExchange
#define InterlockedCompareExchange CollisionTestCas
#include "../../../trainer/Native/CollisionFeatures.inl"
#pragma pop_macro("InterlockedCompareExchange")
constexpr uintptr_t Player=0x50000,Other=0x70000,Status=0x2A17290;
unsigned checks=0,failures=0;
void Check(bool yes,const char* name){++checks;if(!yes){++failures;printf("FAIL %s\n",name);}}
bool Valid(unsigned s){return (shared.valid[s/64]&(uint64_t(1)<<(s%64)))!=0;}
void BaseSetup(int form=0) {
    memset(reinterpret_cast<void*>(g_base),0,0x2C00000);shared={};g_shared=&shared;g_disabled=0;
    g_gameThread=GetCurrentThreadId();shared.hostHeartbeat=GetTickCount();
    context={g_base,g_base+Player,g_base+Status,true};
    At<BYTE>(0x9BA8D0)=1;At<int>(0x716884)=1;At<uintptr_t>(0x716868)=g_base+0x90000;
    At<uintptr_t>(0x9BA920)=g_base+0xA0000;At<uintptr_t>(0x2A105D0)=context.player;
    At<uintptr_t>(0x2A171C8)=context.player;At<uint32_t>(Player+2704)=Other;
    At<uintptr_t>(Player+1472)=context.status;At<unsigned>(Player+1736)=0x1000084;
    At<uint32_t>(Player)=0x750300;At<uintptr_t>(0x750300)=g_base+0x5CBA28;
    At<uintptr_t>(0x5CBA28+296)=g_base+0x404FB0;At<uintptr_t>(Player+360)=context.player;
    At<int>(Player+3552)=form;At<BYTE>(0x9ACDD4)=static_cast<BYTE>(form);
    At<int>(Status)=50;At<int>(Status+4)=100;At<int>(Status+608)=1;At<int>(Status+612)=1;
    At<uint32_t>(Status+616)=static_cast<uint32_t>(Player);
    At<int>(0x2A23950)=79;for(int i=0;i<79;++i)At<int>(0x2A23810+4*i)=i+1;
    At<float>(Player+296)=2;At<float>(Player+300)=8;At<float>(Player+304)=160;
    At<float>(Player+308)=.2f;At<float>(Player+312)=20;At<float>(Player+316)=3;
    At<float>(Player+680)=1;At<float>(Other+296)=5;
}

constexpr uintptr_t Buffer=0xB0000,Resource=0xC0000,MapCollider=0xD0000;
void Setup(int form=0) {
    BaseSetup(form);collision_features::lease={};injectCasRace=false;
    At<uintptr_t>(Player+2560)=g_base+Buffer;At<int>(Buffer)=1;
    At<uintptr_t>(Buffer+8)=context.player;At<unsigned>(Buffer+16)=1;
    At<uintptr_t>(Player+2744)=g_base+Resource;At<int>(Resource)=2;
    At<BYTE>(Resource+64+4)=1;At<BYTE>(Resource+84+4)=2;
    At<uintptr_t>(0xABD448)=g_base+MapCollider;
    At<unsigned>(Player+2488)=1;At<float>(Player+1776)=20;
    At<float>(Player+1780)=30;At<float>(Player+1852)=4;
    At<uint16_t>(Player+1840)=7;At<float>(Player+1848)=123.25f;
    At<float>(Player+1880)=0;At<float>(Player+1884)=-1;At<float>(Player+1888)=0;
    At<unsigned>(Player+1856)=0x34;
}
TrainerResult Run(unsigned slot,double value) {
    double args[8]={value};TrainerResult r{};Check(CollisionHandle(context,slot,args,r),"owned slot handled");return r;
}
void Reject(const char* why) {
    BYTE before[3608],status[632];memcpy(before,reinterpret_cast<void*>(g_base+Player),sizeof(before));
    memcpy(status,reinterpret_cast<void*>(g_base+Status),sizeof(status));
    Check(Run(376,1).code!=0,why);
    Check(!memcmp(before,reinterpret_cast<void*>(g_base+Player),sizeof(before)),"rejection preserves whole actor");
    Check(!memcmp(status,reinterpret_cast<void*>(g_base+Status),sizeof(status)),"rejection preserves whole status");
    Check(!collision_features::lease.active,"rejection acquires no lease");
}
void Enabled() { Check(Run(376,1).code==0&&collision_features::lease.active,"enable acquires lease"); }
void ExpectAbandoned(const char* why) {
    const unsigned old=At<unsigned>(Player+288);CollisionTick(context);
    Check(!collision_features::lease.active,why);
    Check(At<unsigned>(Player+288)==old,"lost identity leaves old actor unchanged");
    Check(!(At<unsigned>(Other+288)&2),"lost identity does not change another actor");
}
void CacheSuppressed(const char* why) {
    CollisionSnapshot(context);
    for(unsigned slot:{380u,381u,382u,383u,387u,388u,389u,390u})Check(!Valid(slot),why);
    Check(Valid(379)&&Valid(384)&&Valid(391),"raw data remains labelled as native state");
}
}
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,0x2C00000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!g_base)return 2;
    for(int form=0;form<=6;++form) {
        Setup(form);At<unsigned>(Player+288)=0x2000;BYTE expected[3608];
        memcpy(expected,reinterpret_cast<void*>(g_base+Player),sizeof(expected));
        *reinterpret_cast<unsigned*>(expected+288)|=2;
        Enabled();Check(!memcmp(expected,reinterpret_cast<void*>(g_base+Player),sizeof(expected)),"enable changes only one flags bit");
        CollisionSnapshot(context);Check(Valid(376)&&shared.values[376]==1&&shared.values[377]==1&&shared.values[378]==0,"selective bypass preserves world gate and disables only body gate");
        Check(Run(376,1).code==0,"idempotent enable");
        At<unsigned>(Player+288)|=0x8000;Check(Run(376,0).code==0,"explicit off");
        Check(At<unsigned>(Player+288)==0xA000&&!collision_features::lease.active,"restore preserves concurrently changed unrelated flags");
        Check(At<unsigned>(Player+292)==0&&At<unsigned>(Player+2248)==0,"world-bypass and render-partition flags untouched");
        Check(At<int>(Status)==50&&At<int>(Status+4)==100,"HP and status untouched");
    }
    for(double v:{-1.,.5,2.,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}) {
        Setup();Check(Run(376,v).code!=0&&!At<unsigned>(Player+288),"invalid toggle values rejected");
    }
    Setup();At<unsigned>(Player+288)=2;Reject("preexisting native separation bit is never acquired");
    Check(Run(376,0).code==0&&At<unsigned>(Player+288)==2,"off without ownership preserves native bit");
    Setup();At<unsigned>(Player+2488)|=0x1000;Reject("native alternate separation gate");
    Setup();At<uintptr_t>(Player+2560)=0;Reject("missing body buffer");
    Setup();At<uintptr_t>(Buffer+8)=g_base+Other;Reject("wrong buffer owner");
    Setup();At<unsigned>(Buffer+16)=2;Reject("hurt-shape buffer is not a body buffer");
    Setup();At<int>(Buffer)=0;Reject("empty body buffer");
    Setup();At<int>(Buffer)=-1;Reject("negative body count");
    Setup();At<int>(Buffer)=2;Reject("body count beyond source type1 capacity");
    Setup();At<int>(Resource)=-1;Reject("negative source count");
    Setup();At<int>(Resource)=4097;Reject("source count beyond diagnostic policy bound");
    Setup();At<uintptr_t>(Player+2744)=1;Reject("unreadable source");
    Setup();At<uintptr_t>(Player+2560)=1;Reject("unreadable buffer");
    Setup();At<BYTE>(Resource+68)=2;Reject("source has no body records");
    Setup();injectCasRace=true;Check(Run(376,1).code!=0&&!collision_features::lease.active&&At<unsigned>(Player+288)==0x4000,"acquire CAS race does not add owned flag");
    Setup();Enabled();injectCasRace=true;CollisionReset(context);Check(!collision_features::lease.active&&At<unsigned>(Player+288)==0x4002,"release CAS race abandons without forcing stale value");
    Setup();++g_gameThread;Reject("wrong game thread");
    Setup();shared.hostHeartbeat=GetTickCount()-5001;Reject("expired heartbeat");
    Setup();g_shared=nullptr;Reject("missing IPC mapping");
    Setup();g_disabled=1;Reject("disabled bridge");
    Setup();context.sceneReady=false;Reject("unready context");
    Setup();At<int>(0x716884)=2;Reject("paused field rejects enable");
    Setup();At<BYTE>(0x9BA8D0)=0;Reject("scene teardown");
    Setup();At<BYTE>(0x9BA8D1)=1;Reject("event-only scene");
    Setup();At<uintptr_t>(0x9BA928)=1;Reject("pending transition");
    Setup();At<uintptr_t>(0x2AE9FA8)=1;Reject("native form transition");
    Setup();At<unsigned>(0x2A10504)=2;Reject("form transition lock");
    Setup();At<uintptr_t>(Player+1472)=g_base+Status+632;Reject("status changed");
    Setup();At<uint32_t>(Status+616)=Other;Reject("status backlink mismatch");
    Setup();At<int>(Status+612)=0;Reject("freed status");
    Setup();At<int>(0x2A23810)=0;Reject("status pool free-list member");
    Setup();At<uint32_t>(Other+2704)=Player;Reject("cyclic actor list");
    Setup();At<uint32_t>(Player)=0x74A518;Reject("foreign actor descriptor");
    Setup();At<int>(Status+608)=14;Reject("non-Sora character");
    Setup();At<int>(Player+3552)=7;Reject("unknown form");
    Setup();At<uintptr_t>(Player+360)=g_base+Other;Reject("motion owner mismatch");
    Setup();At<uint32_t>(Player+1696)=Other;Reject("attached actor");
    Setup();DWORD old=0,unused=0;void* page=reinterpret_cast<void*>(g_base+Player);
    Check(VirtualProtect(page,4096,PAGE_READONLY,&old)!=FALSE,"real read-only actor page");Reject("read-only flag field");VirtualProtect(page,4096,old,&unused);
    Setup();Enabled();shared.hostHeartbeat=GetTickCount()-5001;CollisionTick(context);Check(!collision_features::lease.active&&!(At<unsigned>(Player+288)&2),"heartbeat expiry restores current owned bit");
    Setup();Enabled();g_disabled=1;CollisionReset(context);Check(!collision_features::lease.active&&!(At<unsigned>(Player+288)&2),"fatal disable can restore current actor independently of bridge enabled gate");
    Setup();Enabled();At<int>(Status)=0;CollisionTick(context);Check(!collision_features::lease.active&&!(At<unsigned>(Player+288)&2),"death restores bit while identity still valid");
    Setup();Enabled();At<int>(0x716884)=2;CollisionTick(context);Check(collision_features::lease.active,"field pause retains ownership");CollisionReset(context);Check(!(At<unsigned>(Player+288)&2),"explicit pause reset restores bit");
    Setup();Enabled();At<unsigned>(Player+288)&=~2u;CollisionTick(context);Check(!collision_features::lease.active&&!At<unsigned>(Player+288),"native clear relinquishes lease with no forced reapply");
    Setup();Enabled();At<uintptr_t>(0x2A105D0)=g_base+Other;ExpectAbandoned("actor replacement abandons");
    Setup();Enabled();At<uintptr_t>(0x716868)=g_base+0x91000;ExpectAbandoned("scheduler replacement abandons");
    Setup();Enabled();At<uintptr_t>(0x9BA920)=g_base+0xA1000;ExpectAbandoned("scene heap replacement abandons");
    for(unsigned i=0;i<10;++i){Setup();Enabled();At<BYTE>(0x717008+i)=1;ExpectAbandoned("each map-target byte binds scene lease");}
    Setup();Enabled();At<int>(Player+3552)=1;At<BYTE>(0x9ACDD4)=1;ExpectAbandoned("same actor with changed form abandons");
    Setup();Enabled();At<uint32_t>(Status+616)=Other;ExpectAbandoned("changed status backlink abandons");
    Setup();Enabled();At<int>(Status+612)=0;ExpectAbandoned("status deallocation abandons");
    Setup();Enabled();At<int>(0x2A23810)=0;ExpectAbandoned("freed status pool slot abandons");
    Setup();Enabled();At<BYTE>(0x9BA8D0)=0;ExpectAbandoned("scene teardown never writes old actor");
    Setup();Enabled();At<uintptr_t>(0x9BA928)=1;ExpectAbandoned("pending transition never writes old actor");
    Setup();Enabled();At<uintptr_t>(0x2AE9FA8)=1;ExpectAbandoned("form transition never writes old actor");
    Setup();Enabled();At<uintptr_t>(0x2A171C8)=g_base+Other;ExpectAbandoned("unlisted actor abandons");
    Setup();Enabled();At<unsigned>(Player+288)|=0x10000000;ExpectAbandoned("deleting actor abandons");
    Setup();CollisionSnapshot(context);
    for(unsigned slot=376;slot<=391;++slot)Check(Valid(slot),"valid scene publishes all sixteen fields");
    Check(shared.values[377]==1&&shared.values[378]==1&&shared.values[379]==0&&shared.values[380]==7&&shared.values[381]==123.25&&shared.values[382]==1,"native contact field mapping");
    Check(shared.values[383]==0&&shared.values[384]==20&&shared.values[385]==30&&shared.values[386]==4&&shared.values[387]==0&&shared.values[388]==-1&&shared.values[389]==0&&shared.values[390]==0&&shared.values[391]==6,"geometry normal and category mapping");
    Setup();At<unsigned>(Player+1860)=5;At<uintptr_t>(Player+1864)=1;CollisionSnapshot(context);
    Check(shared.values[382]==0&&shared.values[383]==1&&shared.values[390]==1,"airborne and lateral flags independent; dynamic pointer is never dereferenced");
    Setup();At<unsigned>(Player+1860)=2;At<uint16_t>(Player+1840)=0xFFFF;CollisionSnapshot(context);
    for(unsigned slot:{380u,381u,382u,387u,388u,389u,390u})Check(!Valid(slot),"constructor sentinel is not mistaken for grounded contact");
    Check(Valid(379)&&shared.values[379]==2,"raw invalid-cache flag remains visible");
    Setup();At<uint16_t>(Player+1840)=0xFFFF;CollisionSnapshot(context);Check(Valid(381)&&!Valid(380)&&!Valid(382)&&!Valid(387),"floor height can be valid without a selected support polygon");
    for(unsigned offset:{1776u,1780u,1852u,1848u,1880u,1884u,1888u}) {
        Setup();At<float>(Player+offset)=std::numeric_limits<float>::quiet_NaN();CollisionSnapshot(context);
        if(offset==1776)Check(!Valid(384)&&Valid(385),"NaN radius isolated");
        if(offset==1780)Check(!Valid(385)&&Valid(384),"NaN extent isolated");
        if(offset==1852)Check(!Valid(386)&&Valid(384),"NaN offset isolated");
        if(offset==1848)Check(!Valid(381)&&!Valid(382)&&!Valid(387),"NaN floor height suppresses interpreted contact");
        if(offset>=1880)Check(!Valid(387)&&!Valid(388)&&!Valid(389),"invalid normal suppresses vector as a unit");
    }
    Setup();At<float>(Player+1884)=0;CollisionSnapshot(context);Check(!Valid(387)&&!Valid(388)&&!Valid(389),"zero normal is not a measured plane");
    Setup();At<float>(Player+1884)=100;CollisionSnapshot(context);Check(!Valid(387),"non-normalized corrupt cache rejected");
    Setup();At<float>(Player+1776)=-1;CollisionSnapshot(context);Check(Valid(384)&&shared.values[384]==-1,"diagnostic does not hide finite malformed geometry");
    Setup();At<unsigned>(Player+292)|=0x40;CacheSuppressed("full movement collision bypass suppresses contact interpretation");
    Setup();At<unsigned>(0x2A11400)|=0x20;CacheSuppressed("global actor freeze suppresses contact interpretation");
    Setup();At<unsigned>(Player+288)|=0x400;CacheSuppressed("native actor stop suppresses contact interpretation");
    Setup();At<BYTE>(Player+1612)=1;CacheSuppressed("timed stop suppresses contact interpretation");
    for(unsigned i=0;i<4;++i){Setup();At<uintptr_t>(0xBF2AC8)=g_base+0xE0000;At<uintptr_t>(0xE0000+80+i*8)=1;CacheSuppressed("each native global stop lane suppresses contact interpretation");}
    Setup();At<uintptr_t>(0xBF2AC8)=1;CacheSuppressed("unreadable native global stop context suppresses contact interpretation");
    Setup();At<unsigned>(Player+1736)&=~0x44u;CacheSuppressed("unresolved actor-category stop branch suppresses contact interpretation");
    Setup();At<int>(0x716884)=2;CacheSuppressed("paused field suppresses contact interpretation");
    Setup();At<unsigned>(Player+288)|=1;CacheSuppressed("native world collision mask suppresses contact interpretation");
    Setup();At<unsigned>(Player+2488)&=~1u;CacheSuppressed("world collision not initialized suppresses contact interpretation");
    Setup();At<uintptr_t>(0xABD448)=0;CacheSuppressed("torn-down map collider suppresses contact interpretation");
    Setup();At<uintptr_t>(Player+2560)=1;CollisionSnapshot(context);Check(!Valid(378)&&Valid(377)&&Valid(379),"invalid body buffer does not erase independent diagnostics");
    Setup();++g_gameThread;CollisionSnapshot(context);Check(!shared.valid[5]&&!shared.valid[6],"wrong-thread snapshot publishes nothing");
    Setup();CollisionCapabilities();Check(shared.supported[5]==(uint64_t(255)<<56)&&shared.supported[6]==255,"exact capability slots376..391");
    for(unsigned slot=377;slot<=391;++slot){Setup();BYTE before[3608];memcpy(before,reinterpret_cast<void*>(g_base+Player),sizeof(before));Check(Run(slot,123).code==1&&!memcmp(before,reinterpret_cast<void*>(g_base+Player),sizeof(before)),"diagnostic command performs no writes");}
    const double args[8]{};TrainerResult result{};for(unsigned slot:{375u,392u})Check(!CollisionHandle(context,slot,args,result),"neighbor slots unclaimed");
    printf("CollisionGuardTests: %u checks, %u failures\n",checks,failures);
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
