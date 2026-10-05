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
    if(!p || reinterpret_cast<uintptr_t>(p)>UINTPTR_MAX-size || !VirtualQuery(p,&m,sizeof(m)) ||
       m.State!=MEM_COMMIT || (m.Protect&(PAGE_GUARD|PAGE_NOACCESS))) return false;
    return reinterpret_cast<uintptr_t>(p)+size<=reinterpret_cast<uintptr_t>(m.BaseAddress)+m.RegionSize;
}
bool Writable(const void* p,size_t size) { MEMORY_BASIC_INFORMATION m{}; return Readable(p,size)&&VirtualQuery(p,&m,sizeof(m))&&m.Protect==PAGE_READWRITE; }
uintptr_t DecodePacked(uint32_t p){return p?g_base+p:0;}
bool IsInteger(double v,double lo,double hi){return isfinite(v)&&floor(v)==v&&v>=lo&&v<=hi;}
void SnapshotValue(unsigned s,double v){shared.values[s]=v;shared.valid[s/64]|=uint64_t(1)<<(s%64);}
void SupportCapability(unsigned s){shared.supported[s/64]|=uint64_t(1)<<(s%64);}
#include "../../../trainer/Native/CombatFeatures.inl"
#include "../../../trainer/Native/DamageTuningFeatures.inl"
unsigned checks=0,failures=0;
constexpr uintptr_t Player=0x50000,Enemy=0x70000,PlayerStatus=0x2A17290,EnemyStatus=0x2A17290+632;
void Check(bool yes,const char* name){++checks;if(!yes){++failures;printf("FAIL %s\n",name);}}
void Setup() {
    memset(reinterpret_cast<void*>(g_base),0,0x2C00000); shared={}; g_shared=&shared;
    g_disabled=0;g_gameThread=GetCurrentThreadId();shared.hostHeartbeat=GetTickCount();
    context={g_base,g_base+Player,g_base+PlayerStatus,true};
    At<BYTE>(0x9BA8D0)=1;At<int>(0x716884)=1;At<uintptr_t>(0x716868)=g_base+0x90000;
    At<uintptr_t>(0x2A105D0)=context.player;At<uintptr_t>(0x2A171C8)=context.player;
    At<uint32_t>(Player+2704)=static_cast<uint32_t>(Enemy);
    At<uintptr_t>(Player+1472)=g_base+PlayerStatus;At<uint32_t>(Player+1736)=0x80;
    At<uintptr_t>(Enemy+1472)=g_base+EnemyStatus;At<uint32_t>(Enemy+1736)=0x12;
    At<uintptr_t>(Player+3528)=g_base+0x2A11208;At<uintptr_t>(0x2A11208+56)=context.player;
    At<int>(0x2A11208)=2;At<uint32_t>(0x2A11208+4)=static_cast<uint32_t>(Enemy);
    for(unsigned i=0;i<2;++i) {
        const uintptr_t s=i?EnemyStatus:PlayerStatus;
        At<int>(s)=50;At<int>(s+4)=100;At<int>(s+612)=1;
        At<uint32_t>(s+616)=static_cast<uint32_t>(i?Enemy:Player);
        for(unsigned j=0;j<7;++j)At<BYTE>(s+424+j)=static_cast<BYTE>(70+10*i+j);
        for(unsigned j=0;j<4;++j)At<int>(s+408+4*j)=static_cast<int>(10+i*4+j);
    }
    At<int>(0x2A23950)=78;
    for(int i=0;i<78;++i)At<int>(0x2A23810+4*i)=i+2;
}
TrainerResult Run(unsigned slot,double value=100) {
    double args[8]={value};TrainerResult r{};
    Check(DamageTuningHandle(context,slot,args,r),"owned slot handled");return r;
}
void RejectBoth(const char* why) {
    BYTE before[1264]{};memcpy(before,reinterpret_cast<void*>(g_base+PlayerStatus),sizeof(before));
    Check(Run(272,17).code!=0&&Run(279,17).code!=0,why);
    Check(!memcmp(before,reinterpret_cast<void*>(g_base+PlayerStatus),sizeof(before)),"rejected request leaves both status records unchanged");
}
}
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,0x2C00000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!g_base)return 2;
    for(unsigned slot=272;slot<=285;++slot) for(unsigned value:{0u,1u,100u,255u}) {
        Setup();BYTE expected[1264]{};memcpy(expected,reinterpret_cast<void*>(g_base+PlayerStatus),sizeof(expected));
        expected[(slot>=279?632:0)+424+(slot>=279?slot-279:slot-272)]=static_cast<BYTE>(value);
        Check(Run(slot,value).code==0,"every player/target coefficient accepts native byte endpoints");
        Check(!memcmp(expected,reinterpret_cast<void*>(g_base+PlayerStatus),sizeof(expected)),"exactly the requested byte changes; adjacent stats and other actor are preserved");
    }
    for(double value:{-1.0,256.0,0.5,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}) {
        Setup();BYTE before[1264]{};memcpy(before,reinterpret_cast<void*>(g_base+PlayerStatus),sizeof(before));
        Check(Run(272,value).code!=0&&Run(285,value).code!=0,"invalid coefficient rejected");
        Check(!memcmp(before,reinterpret_cast<void*>(g_base+PlayerStatus),sizeof(before)),"invalid number never changes status");
    }
    Setup();DamageTuningSnapshot(context);
    for(unsigned i=0;i<14;++i)Check(shared.values[272+i]==70+(i/7)*10+i%7,"coefficient readout uses the matching actor and field");
    for(unsigned i=0;i<8;++i)Check(shared.values[286+i]==10+i,"base caps/floors preserve native order");
    for(unsigned slot=286;slot<=293;++slot)Check(Run(slot,7).code!=0,"diagnostics cannot become writes");
    Setup();At<int>(0x716884)=2;DamageTuningSnapshot(context);Check(shared.valid[4]!=0,"field pause permits inspection");RejectBoth("field pause blocks mutations");
    Setup();g_disabled=1;RejectBoth("disabled bridge");
    Setup();g_shared=nullptr;RejectBoth("missing host");
    Setup();shared.hostHeartbeat=0;RejectBoth("zero heartbeat");
    Setup();shared.hostHeartbeat=GetTickCount()-5001;RejectBoth("expired heartbeat");
    Setup();++g_gameThread;RejectBoth("foreign thread");
    Setup();g_gameThread=0;RejectBoth("uninitialized thread");
    Setup();context.base=0;RejectBoth("foreign base");
    Setup();context.sceneReady=false;RejectBoth("unready scene");
    Setup();At<uintptr_t>(0x2AE9FA8)=1;RejectBoth("queued Drive actor replacement");
    Setup();At<unsigned>(0x2A10504)=2;RejectBoth("native Drive lock");
    Setup();At<BYTE>(0x9BA8D1)=1;RejectBoth("scene unloading");
    Setup();At<uintptr_t>(0x9BA928)=1;RejectBoth("pending room transition");
    Setup();At<BYTE>(0x9006B0)=1;RejectBoth("native menu");
    Setup();At<uintptr_t>(0x2A105D0)=g_base+Enemy;RejectBoth("stale player context");
    Setup();At<uint32_t>(PlayerStatus+616)=static_cast<uint32_t>(Enemy);RejectBoth("wrong status backlink");
    Setup();At<int>(PlayerStatus)=0;RejectBoth("dead player");
    Setup();At<uintptr_t>(0x2A171C8)=g_base+Enemy;RejectBoth("player missing from live list");
    Setup();At<uint32_t>(Enemy+2704)=static_cast<uint32_t>(Player);RejectBoth("cyclic live list");
    Setup();At<int>(PlayerStatus+612)=0;RejectBoth("released status");
    Setup();At<int>(0x2A23950)=-1;RejectBoth("negative free count");
    Setup();At<int>(0x2A23950)=81;RejectBoth("overflowed free count");
    Setup();At<int>(0x2A23810)=80;RejectBoth("out of bounds free entry");
    Setup();At<int>(0x2A23810)=3;RejectBoth("duplicate free entry");
    Setup();At<int>(0x2A23810)=0;RejectBoth("current player status marked free");
    Setup();At<int>(0x2A23810)=1;Check(Run(279).code!=0&&Run(272).code==0,"free enemy status rejected independently");
    Setup();At<int>(0x2A11208)=1;DamageTuningSnapshot(context);Check((shared.valid[4]&(uint64_t(1)<<23))==0,"automatic target has no manual-target readout");Check(Run(279).code!=0&&Run(272).code==0,"automatic lock-on is not an edit target");
    Setup();At<uint32_t>(EnemyStatus+620)=1;Check(Run(279).code!=0,"save-backed enemy status excluded");
    Setup();At<uint32_t>(EnemyStatus+616)=static_cast<uint32_t>(Player);Check(Run(279).code!=0,"target status reuse rejected");
    Setup();At<uint32_t>(0x2A11208+4)=static_cast<uint32_t>(Player);Check(Run(279).code!=0,"player cannot be selected as enemy");
    Setup();At<int>(EnemyStatus)=0;Check(Run(279).code!=0,"dead target excluded");
    Setup();context.status++;At<uintptr_t>(Player+1472)=context.status;RejectBoth("unaligned status record");
    Setup();memcpy(reinterpret_cast<void*>(g_base+0xA0000),reinterpret_cast<void*>(g_base+PlayerStatus),632);
    context.status=g_base+0xA0000;At<uintptr_t>(Player+1472)=context.status;RejectBoth("readable foreign status outside pool");
    Setup();DWORD old=0,unused=0;auto page=reinterpret_cast<void*>((g_base+PlayerStatus)&~uintptr_t(4095));
    Check(VirtualProtect(page,4096,PAGE_READONLY,&old)!=FALSE,"real read-only fixture protection applied");
    RejectBoth("actual read-only coefficient pages rejected");VirtualProtect(page,4096,old,&unused);
    Setup();DamageTuningCapabilities();
    for(unsigned slot=0;slot<512;++slot)Check(!!(shared.supported[slot/64]&(uint64_t(1)<<(slot%64)))==(slot>=272&&slot<=293),"only assigned capabilities are published");
    double args[8]{};TrainerResult r{};Check(!DamageTuningHandle(context,271,args,r)&&!DamageTuningHandle(context,294,args,r),"neighboring domains unclaimed");
    printf("DamageTuningTests: %u checks, %u failures\n",checks,failures);VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
