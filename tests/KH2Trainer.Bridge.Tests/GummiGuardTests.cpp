#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define KH2_GUMMI_TESTS
#include <windows.h>
#include <stdint.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits>
#include <initializer_list>
namespace {
uintptr_t g_base=0; DWORD g_gameThread=0; volatile LONG g_disabled=0;
struct TrainerContext { uintptr_t base,player,status; bool sceneReady; };
struct TrainerResult { LONG code; const wchar_t* text; };
struct Shared { DWORD hostHeartbeat; double values[512]; uint64_t valid[8],supported[8]; } shared{};
Shared* g_shared=&shared;
bool switchPlayerOnSecondRead=false; unsigned playerReads=0;
template<class T>T& At(uintptr_t rva){return *reinterpret_cast<T*>(g_base+rva);}
bool Readable(const void* p,size_t count) {
    const uintptr_t start=reinterpret_cast<uintptr_t>(p);
    if(!start || count>UINTPTR_MAX-start)return false;
    if(switchPlayerOnSecondRead && start==g_base+0xAF0540 && ++playerReads==2) At<uintptr_t>(0xAF0540)=g_base+0x52000;
    uintptr_t cursor=start;
    while(cursor<start+count) {
        MEMORY_BASIC_INFORMATION m{};
        if(!VirtualQuery(reinterpret_cast<const void*>(cursor),&m,sizeof(m))||m.State!=MEM_COMMIT||
           (m.Protect&(PAGE_GUARD|PAGE_NOACCESS)))return false;
        const DWORD protection=m.Protect&0xff;
        if(protection!=PAGE_READONLY && protection!=PAGE_READWRITE && protection!=PAGE_WRITECOPY &&
           protection!=PAGE_EXECUTE_READ && protection!=PAGE_EXECUTE_READWRITE && protection!=PAGE_EXECUTE_WRITECOPY)return false;
        const uintptr_t next=reinterpret_cast<uintptr_t>(m.BaseAddress)+m.RegionSize;
        if(next<=cursor)return false;cursor=next;
    }
    return true;
}
bool Writable(const void* p,size_t count) {
    if(!Readable(p,count))return false;
    uintptr_t cursor=reinterpret_cast<uintptr_t>(p),end=cursor+count;
    while(cursor<end) {
        MEMORY_BASIC_INFORMATION m{};
        if(!VirtualQuery(reinterpret_cast<const void*>(cursor),&m,sizeof(m)))return false;
        const DWORD protection=m.Protect&0xff;
        if(protection!=PAGE_READWRITE && protection!=PAGE_WRITECOPY && protection!=PAGE_EXECUTE_READWRITE && protection!=PAGE_EXECUTE_WRITECOPY)return false;
        cursor=reinterpret_cast<uintptr_t>(m.BaseAddress)+m.RegionSize;
    }
    return true;
}
// Packed-pointer decoding itself is covered by the shared bridge's tests. This
// fixture maps synthetic RVAs, allowing invalid descriptors and list edges.
uintptr_t DecodePacked(uint32_t value){return value?g_base+value:0;}
bool IsInteger(double n,double lo,double hi){return isfinite(n)&&floor(n)==n&&n>=lo&&n<=hi;}
void SnapshotValue(unsigned s,double n){shared.values[s]=n;shared.valid[s/64]|=uint64_t(1)<<(s%64);}
void SupportCapability(unsigned s){shared.supported[s/64]|=uint64_t(1)<<(s%64);}
#include "../../src/KH2Trainer.Bridge/GummiFeatures.inl"
unsigned checks=0,failures=0,healCalls=0,scoreCalls=0;uintptr_t lastState=0;float lastAmount=0;int lastPoints=0;
TrainerContext host{};
void Check(bool ok,const char* name){++checks;if(!ok){++failures;printf("FAIL %s\n",name);}}
void __fastcall MockHeal(void* state,float amount){++healCalls;lastState=reinterpret_cast<uintptr_t>(state);lastAmount=amount;}
void __fastcall MockScore(int points){++scoreCalls;lastPoints=points;}
TrainerResult Command(unsigned slot,double value=0){double args[8]={value};TrainerResult r{};Check(GummiHandle(host,slot,args,r),"Gummi command is handled");return r;}
void ClearSnapshot(){memset(shared.valid,0,sizeof(shared.valid));memset(shared.values,0,sizeof(shared.values));}
bool Valid(unsigned slot){return (shared.valid[slot/64]&(uint64_t(1)<<(slot%64)))!=0;}
void Player(uintptr_t rva){
    At<uint32_t>(rva)=DWORD(gummi::DescriptorRva);
    At<uintptr_t>(rva+0x550)=g_base+rva+0x570;
    At<uintptr_t>(rva+0x570)=g_base+gummi::StateVtableRva;
    At<float>(rva+0x578)=42.25f;At<int>(rva+0x57C)=120;
    At<int>(rva+0x5D8)=2;At<uint32_t>(rva+0x140C)=0;
}
void Ready(){
    g_shared=&shared;g_disabled=0;g_gameThread=GetCurrentThreadId();shared.hostHeartbeat=GetTickCount();
    host={g_base,0,0,false};switchPlayerOnSecondRead=false;playerReads=0;
    At<uintptr_t>(gummi::ModuleRva)=g_base+gummi::ModuleVtableRva;
    At<uintptr_t>(gummi::ModuleRva+8)=g_base+0x90000;
    At<int>(gummi::ModuleRva+36)=1;At<uint32_t>(gummi::ModuleRva+20)=0;
    At<uintptr_t>(gummi::ModeListRva)=g_base+gummi::ModuleRva;
    At<uintptr_t>(gummi::HeapRva)=g_base+0xA0000;At<uintptr_t>(gummi::ModuleHeapRva)=g_base+0xA0000;
    At<uintptr_t>(gummi::SchedulerRva)=g_base+0x90000;
    At<int>(gummi::MissionPhaseRva)=8;At<uintptr_t>(gummi::PlayerRva)=g_base+0x50000;
    At<uintptr_t>(gummi::DescriptorRva)=g_base+gummi::DescriptorVtableRva;Player(0x50000);Player(0x52000);
    At<uint32_t>(0x9A8788)=3;At<uint32_t>(0x716C04)=2;
    At<uint32_t>(gummi::ScoreRva)=1209;At<BYTE>(gummi::ScoreLockRva)=0;
    At<int>(0x72B2C4)=12;At<int>(0x72B2C0)=7;At<int>(0x72B2C8)=15;
    At<uintptr_t>(0xAF4258)=g_base+0xB0000;At<BYTE>(0xB0000)=3;At<BYTE>(0xB0001)=2;
    At<int>(0xAF4204)=4;At<int>(0xAF4260)=1;
    memcpy(reinterpret_cast<void*>(g_base+gummi::HealRva),gummi::HealCode,sizeof(gummi::HealCode));
    memcpy(reinterpret_cast<void*>(g_base+gummi::AddScoreRva),gummi::ScoreCode,sizeof(gummi::ScoreCode));
}
void Rejected(const char* name){const unsigned a=healCalls,b=scoreCalls;Check(Command(130,5).code!=0&&healCalls==a&&scoreCalls==b,name);}
}
int main(){
    constexpr size_t AllocationSize=0xC00000;
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,AllocationSize,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!g_base)return 2;
    Ready();gummi::testHeal=MockHeal;gummi::testAddScore=MockScore;
    Check(Command(130,12.5).code==0&&healCalls==1&&lastState==g_base+0x50570&&lastAmount==12.5f,"native heal ABI receives embedded state and float amount with Sora scene false");
    Check(Command(131).code==0&&lastAmount==77.75f,"refill computes missing fractional HP");
    At<float>(0x50578)=120;const unsigned fullCalls=healCalls;
    Check(Command(131).code==0&&healCalls==fullCalls,"full HP skips native zero-means-one helper");Ready();
    for(double n:{0.0,-1.0,121.0,std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN(),1e-300})
        Check(Command(130,n).code!=0,"invalid healing amount rejected before float cast or call");
    const unsigned beforeScore=scoreCalls;
    Check(Command(133,1000).code==0&&scoreCalls==beforeScore+1&&lastPoints==1000&&At<uint32_t>(gummi::ScoreRva)==1209,"score helper called once with points, trainer does not directly alter count digit");
    for(double n:{-10.0,0.0,1.0,11.0,10.5,100000000.0,2147483647.0,4294967295.0,std::numeric_limits<double>::quiet_NaN()})
        Check(Command(133,n).code!=0,"invalid points rejected without signed or unsigned overflow");
    At<uint32_t>(gummi::ScoreRva)=99999999;Check(Command(133,99999990).code==0&&lastPoints==99999990,"maximum valid input remains within unsigned sum range");
    At<uint32_t>(gummi::ScoreRva)=100000000;Check(Command(133,10).code!=0,"out of range existing score rejected");Ready();
    At<BYTE>(gummi::ScoreLockRva)=1;Check(Command(133,10).code!=0,"native additions lock respected");Ready();
    At<BYTE>(gummi::AddScoreRva+58)^=1;Check(Command(133,10).code!=0,"whole score function signature checked including final instruction");Ready();
    At<BYTE>(gummi::HealRva+45)^=1;Rejected("whole heal signature checked including return");Ready();
    At<uintptr_t>(gummi::HeapRva)=0;Rejected("null subsystem heap rejected");Ready();
    At<uintptr_t>(gummi::ModuleHeapRva)=g_base+0xA0100;Rejected("heap ownership mismatch rejected");Ready();
    At<uintptr_t>(gummi::HeapRva)=g_base+AllocationSize;At<uintptr_t>(gummi::ModuleHeapRva)=g_base+AllocationSize;Rejected("unreadable heap rejected");Ready();
    At<uintptr_t>(gummi::SchedulerRva)=0;Rejected("null scheduler rejected");Ready();
    At<uintptr_t>(gummi::ModuleRva+8)=g_base+0x90100;Rejected("module scheduler mismatch rejected");Ready();
    At<uintptr_t>(gummi::ModuleRva)=g_base+gummi::ModuleVtableRva+8;Rejected("foreign module descriptor rejected");Ready();
    At<uintptr_t>(gummi::ModeListRva)=0;Rejected("unlisted module rejected");Ready();
    At<uint32_t>(gummi::ModuleRva+20)=DWORD(gummi::ModuleRva);Rejected("cyclic module list rejected");Ready();
    At<uint32_t>(gummi::ModuleRva+20)=DWORD(AllocationSize+0x1000);Rejected("invalid module tail rejected after target found");Ready();
    At<uintptr_t>(gummi::ModeListRva)=g_base+0xC0000;At<uint32_t>(0xC0014)=DWORD(gummi::ModuleRva);
    Check(Command(130,1).code==0,"module can be after another active mode");Ready();
    At<uint32_t>(gummi::ModuleRva+20)=0xC0000;
    for(unsigned i=0;i<64;++i)At<uint32_t>(0xC0000+i*64+20)=i==63?0:0xC0000+(i+1)*64;
    Rejected("overlong module list bounded");Ready();
    for(int n:{0,2,3,4,-1}){At<int>(gummi::ModuleRva+36)=n;Rejected("nonrunning module rejects actions");}Ready();
    for(int n=0;n<=19;++n)if(n!=8){At<int>(gummi::MissionPhaseRva)=n;Rejected("non-gameplay mission phase rejects action");}Ready();
    for(int n:{0,1,3,4,5,6,-1}){At<int>(0x505D8)=n;Rejected("nonactive player phase rejects action");}Ready();
    At<uintptr_t>(gummi::PlayerRva)=0;Rejected("missing player rejected");Ready();
    At<uintptr_t>(gummi::PlayerRva)=g_base+AllocationSize-0x1000;Rejected("short readable player rejected");Ready();
    At<uint32_t>(0x50000)=DWORD(gummi::DescriptorRva+8);Rejected("packed descriptor mismatch rejected");Ready();
    At<uintptr_t>(gummi::DescriptorRva)=g_base+gummi::DescriptorVtableRva+8;Rejected("descriptor vtable mismatch rejected");Ready();
    At<uintptr_t>(0x50570)=g_base+gummi::StateVtableRva+8;Rejected("embedded state type mismatch rejected");Ready();
    At<uintptr_t>(0x50550)=g_base+0x52570;Rejected("ship-state backlink mismatch rejected");Ready();
    for(float f:{0.f,-1.f,121.f,std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN()}){At<float>(0x50578)=f;Rejected("dead or invalid HP cannot be healed");}Ready();
    for(int n:{0,-1}){At<int>(0x5057C)=n;Rejected("invalid max HP rejected");}Ready();
    At<uint32_t>(0x5140C)=0x10;Rejected("death flag rejected with positive HP");Ready();
    At<uint32_t>(0x5140C)=0x40000;Rejected("rebirth flag rejected");Ready();
    shared.hostHeartbeat=GetTickCount()-5001;Rejected("expired host rejected");Ready();
    shared.hostHeartbeat=0;Rejected("zero heartbeat rejected");Ready();
    shared.hostHeartbeat=GetTickCount()+1000;Rejected("future heartbeat rejected");Ready();
    g_shared=nullptr;Rejected("missing host rejected");Ready();g_disabled=1;Rejected("disabled bridge rejected");Ready();
    ++g_gameThread;Rejected("worker or foreign thread rejected");Ready();host.base=0;Rejected("foreign bridge context rejected");Ready();
    switchPlayerOnSecondRead=true;Rejected("player replacement between initial and immediate pre-call check rejected");Ready();
    DWORD old=0;VirtualProtect(reinterpret_cast<void*>(g_base+0x50000),0x2000,PAGE_READONLY,&old);
    Rejected("read-only health memory rejects healing");VirtualProtect(reinterpret_cast<void*>(g_base+0x50000),0x2000,old,&old);Ready();
    VirtualProtect(reinterpret_cast<void*>(g_base+0x72B000),0x1000,PAGE_READONLY,&old);
    Check(Command(133,10).code!=0,"read-only score memory rejects adding points");VirtualProtect(reinterpret_cast<void*>(g_base+0x72B000),0x1000,old,&old);Ready();
    ClearSnapshot();GummiSnapshot(host);
    Check(Valid(128)&&shared.values[128]==42.25&&shared.values[129]==120,"HP snapshot preserves fractions");
    Check(shared.values[132]==1209&&shared.values[134]==9&&shared.values[135]==12&&shared.values[136]==7&&shared.values[137]==15,"score and medal snapshots decoded");
    Check(shared.values[138]==8&&shared.values[139]==2&&shared.values[140]==3&&shared.values[141]==2&&shared.values[142]==4,"mission context snapshot correct");
    At<int>(gummi::ModuleRva+36)=2;ClearSnapshot();GummiSnapshot(host);Check(Valid(128)&&Valid(132),"paused Gummi readouts remain valid");Ready();
    At<uint32_t>(0x716C04)=0;At<BYTE>(0xB0001)=1;ClearSnapshot();GummiSnapshot(host);Check(shared.values[141]==1&&At<uint32_t>(0x716C04)==0,"zero mission variant normalized without engine side effect");Ready();
    At<int>(0x72B2C4)=31;At<int>(0x72B2C0)=10;At<int>(0x72B2C8)=-1;ClearSnapshot();GummiSnapshot(host);Check(!Valid(135)&&!Valid(136)&&!Valid(137)&&Valid(128),"invalid medal fields omitted individually");Ready();
    At<BYTE>(0xB0001)=3;ClearSnapshot();GummiSnapshot(host);Check(!Valid(142),"rank row for another mission omitted");Ready();
    At<int>(0xAF4204)=17;ClearSnapshot();GummiSnapshot(host);Check(!Valid(142),"rank above observed limit omitted");Ready();
    At<uintptr_t>(gummi::HeapRva)=0;ClearSnapshot();GummiSnapshot(host);Check(!Valid(128)&&!Valid(132)&&!Valid(138),"module loss yields no stale data");
    GummiCapabilities();bool every=true;for(unsigned s=128;s<=143;++s)every&=(shared.supported[s/64]&(uint64_t(1)<<(s%64)))!=0;
    Check(every,"implemented capabilities remain static without scene");
    Ready();const unsigned oldHeal=healCalls,oldScore=scoreCalls;GummiReset(host);GummiTick(host);Check(healCalls==oldHeal&&scoreCalls==oldScore,"reset and tick do not mutate one-shot results");
    double args[8]{};TrainerResult r{};Check(!GummiHandle(host,128,args,r)&&!GummiHandle(host,144,args,r),"read-only and reserved slots do not accept writes");
    Check(GummiHandle(host,130,nullptr,r)&&r.code!=0,"missing arguments safely rejected");
    printf("GummiGuardTests: %u checks, %u failures\n",checks,failures);VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
