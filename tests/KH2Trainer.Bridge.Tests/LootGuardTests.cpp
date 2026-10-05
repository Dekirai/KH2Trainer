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
#include "../../src/KH2Trainer.Bridge/CombatFeatures.inl"
#include "../../src/KH2Trainer.Bridge/DamageTuningFeatures.inl"
#include "../../src/KH2Trainer.Bridge/LootFeatures.inl"
constexpr uintptr_t Player=0x50000,Ally=0x70000,Status=0x2A17290,AllyStatus=Status+632;
constexpr uintptr_t SecondAlly=0x80000,SecondAllyStatus=Status+2*632;
unsigned checks=0,failures=0;
void Check(bool yes,const char* name){++checks;if(!yes){++failures;printf("FAIL %s\n",name);}}
bool Valid(unsigned s){return (shared.valid[s/64]&(uint64_t(1)<<(s%64)))!=0;}
void Setup() {
    memset(reinterpret_cast<void*>(g_base),0,0x2C00000);shared={};g_shared=&shared;g_disabled=0;
    g_gameThread=GetCurrentThreadId();shared.hostHeartbeat=GetTickCount();
    context={g_base,g_base+Player,g_base+Status,true};
    At<BYTE>(0x9BA8D0)=1;At<int>(0x716884)=1;At<uintptr_t>(0x716868)=g_base+0x90000;
    At<uintptr_t>(0x2A105D0)=context.player;At<uintptr_t>(0x2A171C8)=context.player;
    At<uint32_t>(Player+2704)=Ally;At<uintptr_t>(0x2A239B0)=g_base+Ally;
    for(unsigned i=0;i<2;++i) {
        const uintptr_t actor=i?Ally:Player,s=i?AllyStatus:Status;
        At<uintptr_t>(actor+1472)=g_base+s;At<unsigned>(actor+1736)=i?0x8:0x84;
        At<int>(s)=50;At<int>(s+4)=100;At<int>(s+612)=1;At<uint32_t>(s+616)=static_cast<uint32_t>(actor);
        At<uintptr_t>(s+504)=g_base+s;At<float>(s+520)=i?60.f:40.f;
        At<float>(s+568)=i?.5f:.25f;At<float>(s+572)=i?.25f:.5f;At<float>(s+580)=i?.5f:.75f;
    }
    At<float>(Status+452)=10;At<float>(0x2A11418)=1;
    At<int>(0x2A23950)=78;for(int i=0;i<78;++i)At<int>(0x2A23810+4*i)=i+2;
}
TrainerResult Run(unsigned slot,double value) {
    const double args[8]={value};TrainerResult r{};Check(LootHandle(context,slot,args,r),"allocated slot handled");return r;
}
void AddSecondAlly() {
    // Copy the validated fixture, then give the third native party slot its
    // own allocated status and owner identities. The free list must change.
    memcpy(reinterpret_cast<void*>(g_base+SecondAlly),reinterpret_cast<void*>(g_base+Ally),2708);
    memcpy(reinterpret_cast<void*>(g_base+SecondAllyStatus),reinterpret_cast<void*>(g_base+AllyStatus),632);
    At<uintptr_t>(0x2A239B8)=g_base+SecondAlly;
    At<uint32_t>(Ally+2704)=static_cast<uint32_t>(SecondAlly);At<uint32_t>(SecondAlly+2704)=0;
    At<uintptr_t>(SecondAlly+1472)=g_base+SecondAllyStatus;
    At<uint32_t>(SecondAllyStatus+616)=static_cast<uint32_t>(SecondAlly);
    At<uintptr_t>(SecondAllyStatus+504)=g_base+SecondAllyStatus;
    At<int>(0x2A23950)=77;for(int i=0;i<77;++i)At<int>(0x2A23810+4*i)=i+3;
}
void Reject(const char* why) {
    BYTE before[1264];memcpy(before,reinterpret_cast<void*>(g_base+Status),sizeof(before));
    for(unsigned s=352;s<=355;++s)Check(Run(s,1).code!=0,why);
    Check(!memcmp(before,reinterpret_cast<void*>(g_base+Status),sizeof(before)),"rejected edit preserves both complete statuses");
}
}
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,0x2C00000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!g_base)return 2;
    const unsigned offsets[]={520,568,572,580};const double maxima[]={5000,9,99,100};
    for(unsigned i=0;i<4;++i)for(double v:{0.,.125,maxima[i]}) {
        Setup();BYTE expected[1264];memcpy(expected,reinterpret_cast<void*>(g_base+Status),sizeof(expected));
        const float native=static_cast<float>(i==3?v/100:v);memcpy(expected+offsets[i],&native,4);
        Check(Run(352+i,v).code==0,"bounded scalar including fractional/endpoints accepted");
        Check(!memcmp(expected,reinterpret_cast<void*>(g_base+Status),sizeof(expected)),"only exact four-byte field changes; abilities, adjacent stats and ally untouched");
    }
    for(unsigned i=0;i<4;++i)for(double v:{-1.,maxima[i]+.01,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}) {
        Setup();const float before=At<float>(Status+offsets[i]);
        Check(Run(352+i,v).code!=0&&At<float>(Status+offsets[i])==before,"non-finite/out-of-range value never writes");
    }
    Setup();LootSnapshot(context);
    Check(shared.values[352]==40&&shared.values[353]==.25&&shared.values[354]==.5&&shared.values[355]==75,"player floats and percentage read correctly");
    Check(shared.values[356]==170&&shared.values[357]==1.75&&shared.values[358]==1.75&&shared.values[359]==37.5,"native additive party quantities/luck, multiplicative conversion and radius");
    Setup();At<float>(Status+568)=.1f;At<float>(AllyStatus+568)=.2f;
    At<float>(Status+572)=.1f;At<float>(AllyStatus+572)=.2f;LootSnapshot(context);
    Check(shared.values[357]==1.3000000715255737&&shared.values[358]==1.3000000715255737,"native rounds each scalar addition to float32 before the next party member");
    Check(shared.values[357]!=1.2999999523162842,"readout cannot silently use double accumulation rounded only at the end");
    Setup();AddSecondAlly();At<float>(Status+568)=.1f;At<float>(AllyStatus+568)=.2f;At<float>(SecondAllyStatus+568)=.3f;
    At<float>(Status+572)=.1f;At<float>(AllyStatus+572)=.2f;At<float>(SecondAllyStatus+572)=.3f;
    At<float>(Status+580)=.7f;At<float>(AllyStatus+580)=.9f;At<float>(SecondAllyStatus+580)=.3f;
    LootSnapshot(context);
    Check(shared.values[357]==1.6000001430511475&&shared.values[358]==1.6000001430511475,"third native party slot contributes after player and first ally in float32 order");
    Check(shared.values[359]==0.18900001049041748*100.0,"retention rounds after each multiplication before final double percent display");
    Check(shared.values[359]!=0.1889999955892563*100.0,"retention rejects a double product rounded only after all three actors");
    Setup();AddSecondAlly();At<int>(SecondAllyStatus)=0;LootSnapshot(context);
    Check(shared.values[357]==2.25&&shared.values[358]==2.0&&shared.values[359]==18.75,"dead but allocated third actor retains native party contributions");
    Setup();AddSecondAlly();At<uint32_t>(SecondAllyStatus+616)=Ally;LootSnapshot(context);
    Check(!Valid(357)&&!Valid(358)&&!Valid(359)&&Valid(352),"third member's mismatched status backlink suppresses aggregate only");
    Setup();At<int>(AllyStatus)=0;LootSnapshot(context);Check(shared.values[357]==1.75,"native valid party contribution does not impose a new living-HP gate");
    Setup();At<unsigned>(Ally+288)=0x10000000;LootSnapshot(context);Check(shared.values[357]==1.25&&shared.values[359]==75,"deleting party actor contributes nothing");
    Setup();At<uintptr_t>(0x2A239B0)=g_base+0x80000;LootSnapshot(context);Check(shared.values[357]==1.25,"unlisted party pointer is ignored without dereferencing it");
    Setup();At<uintptr_t>(Ally+1472)=0;LootSnapshot(context);Check(shared.values[358]==1.5,"party member without status contributes nothing");
    Setup();At<uintptr_t>(AllyStatus+504)=0;LootSnapshot(context);Check(!Valid(357)&&Valid(352),"invalid ally status owner suppresses aggregate only");
    Setup();At<int>(0x2A23810)=1;LootSnapshot(context);Check(!Valid(357)&&Valid(352),"released ally status suppresses aggregate");
    Setup();At<uint32_t>(AllyStatus+616)=Player;LootSnapshot(context);Check(!Valid(358),"reused ally status rejected");
    Setup();At<unsigned>(Player+1736)=0x80;LootSnapshot(context);Check(shared.values[356]==130,"draw bonus omitted when native actor category does not consume it");
    Setup();At<float>(Status+520)=std::numeric_limits<float>::quiet_NaN();LootSnapshot(context);Check(!Valid(352)&&!Valid(356)&&Valid(357),"NaN radius cannot leak into UI");
    Check(Run(352,300).code==0,"finite explicit request can replace invalid current scalar");
    Setup();At<float>(AllyStatus+572)=std::numeric_limits<float>::infinity();LootSnapshot(context);Check(!Valid(357)&&!Valid(358)&&!Valid(359),"non-finite party aggregate unavailable");
    Setup();At<float>(0x2A11418)=2;LootSnapshot(context);Check(shared.values[357]==2.75,"script-selected base quantity retained");
    Setup();At<int>(0x716884)=2;LootSnapshot(context);Check(Valid(352)&&Valid(359),"field pause supports readouts");Reject("field pause blocks edits");
    Setup();At<uintptr_t>(Status+504)=0;Reject("ability status backlink mismatch");
    Setup();At<uint32_t>(Status+616)=Ally;Reject("actor status backlink mismatch");
    Setup();At<int>(0x2A23810)=0;Reject("current status on free list");
    Setup();At<uint32_t>(Ally+2704)=Player;Reject("cyclic live list");
    Setup();At<uintptr_t>(0x2AE9FA8)=1;Reject("Drive replacement in progress");
    Setup();At<BYTE>(0x9006B0)=1;Reject("menu in progress");
    Setup();At<int>(Status)=0;Reject("dead player");
    Setup();context.sceneReady=false;Reject("unready scene");
    Setup();++g_gameThread;Reject("wrong thread");
    Setup();shared.hostHeartbeat=GetTickCount()-5001;Reject("expired host");
    Setup();g_disabled=1;Reject("disabled bridge");
    Setup();DWORD old=0,unused=0;void* page=reinterpret_cast<void*>((g_base+Status)&~uintptr_t(4095));
    Check(VirtualProtect(page,4096,PAGE_READONLY,&old)!=FALSE,"real read-only page set");Reject("read-only field");VirtualProtect(page,4096,old,&unused);
    Setup();for(unsigned s=356;s<=359;++s)Check(Run(s,100).code!=0,"readout command cannot mutate");
    LootCapabilities();Check(shared.supported[5]==(uint64_t(255)<<32),"exact loot capability mask");
    Check(shared.supported[0]==0&&shared.supported[4]==0&&shared.supported[6]==0,"neighboring capability banks preserved");
    const double args[8]{};TrainerResult r{};Check(!LootHandle(context,351,args,r)&&!LootHandle(context,360,args,r),"neighboring commands unclaimed");
    printf("LootGuardTests: %u checks, %u failures\n",checks,failures);VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
