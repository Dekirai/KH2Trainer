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
constexpr uintptr_t Player=0x50000,Other=0x70000,Status=0x2A17290;
unsigned checks=0,failures=0;
void Check(bool yes,const char* name){++checks;if(!yes){++failures;printf("FAIL %s\n",name);}}
bool Valid(unsigned s){return (shared.valid[s/64]&(uint64_t(1)<<(s%64)))!=0;}
void Setup(int form=0) {
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
TrainerResult Run(unsigned slot,double value) {
    const double args[8]={value};TrainerResult r{};Check(ActorMovementHandle(context,slot,args,r),"allocated slot handled");return r;
}
void Reject(const char* why) {
    BYTE actorBefore[3608],statusBefore[632];memcpy(actorBefore,reinterpret_cast<void*>(g_base+Player),sizeof(actorBefore));
    memcpy(statusBefore,reinterpret_cast<void*>(g_base+Status),sizeof(statusBefore));
    for(unsigned slot=344;slot<=347;++slot)Check(Run(slot,4).code!=0,why);
    Check(!memcmp(actorBefore,reinterpret_cast<void*>(g_base+Player),sizeof(actorBefore)),"rejected command preserves whole actor");
    Check(!memcmp(statusBefore,reinterpret_cast<void*>(g_base+Status),sizeof(statusBefore)),"rejected command preserves whole status");
}
}
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,0x2C00000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!g_base)return 2;
    const unsigned offsets[]={296,300,312,304};const double minima[]={0,0,.1,0},maxima[]={32,64,100,1000};
    for(int form=0;form<=6;++form)for(unsigned i=0;i<4;++i)for(double value:{minima[i],4.125,maxima[i]}) {
        Setup(form);BYTE expected[3608];memcpy(expected,reinterpret_cast<void*>(g_base+Player),sizeof(expected));
        const float native=static_cast<float>(value);memcpy(expected+offsets[i],&native,4);
        Check(Run(344+i,value).code==0,"all seven stable Sora forms accept bounded scalar");
        Check(!memcmp(expected,reinterpret_cast<void*>(g_base+Player),sizeof(expected)),"only requested four bytes change; motion/turn/physics untouched");
        Check(At<float>(Other+296)==5&&At<int>(Status)==50,"other actor and player HP untouched");
        ActorMovementSnapshot(context);Check(Valid(344+i)&&shared.values[344+i]==native,"readout reports actual float32 value");
    }
    for(unsigned i=0;i<4;++i)for(double value:{minima[i]-.001,maxima[i]+.001,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity()}) {
        Setup();BYTE before[3608];memcpy(before,reinterpret_cast<void*>(g_base+Player),sizeof(before));
        Check(Run(344+i,value).code!=0&&!memcmp(before,reinterpret_cast<void*>(g_base+Player),sizeof(before)),"NaN infinity or policy violation preserves actor");
    }
    Setup();ActorMovementSnapshot(context);Check(shared.values[344]==2&&shared.values[345]==8&&shared.values[346]==20&&shared.values[347]==160,"offset ordering is walk run fall jump");
    Setup();At<float>(Player+296)=100;ActorMovementSnapshot(context);Check(Valid(344)&&shared.values[344]==100,"finite native values outside edit policy remain visible");
    Setup();At<float>(Player+300)=std::numeric_limits<float>::quiet_NaN();ActorMovementSnapshot(context);Check(!Valid(345)&&Valid(344)&&Valid(346)&&Valid(347),"one invalid float suppresses only its readout");
    Check(Run(345,8).code==0&&At<float>(Player+300)==8,"explicit bounded write repairs invalid scalar");
    Setup();At<int>(0x716884)=2;ActorMovementSnapshot(context);Check(Valid(344)&&Valid(347),"paused field allows observation");Reject("paused field blocks mutation");
    Setup();++g_gameThread;Reject("wrong game thread");
    Setup();shared.hostHeartbeat=GetTickCount()-5001;Reject("expired trainer heartbeat");
    Setup();shared.hostHeartbeat=0;Reject("no initial heartbeat");
    Setup();g_shared=nullptr;Reject("disconnected mapping");
    Setup();g_disabled=1;Reject("disabled bridge");
    Setup();context.base+=16;Reject("foreign context base");
    Setup();context.sceneReady=false;Reject("stale unready context");
    Setup();At<BYTE>(0x9BA8D0)=0;Reject("scene teardown");
    Setup();At<BYTE>(0x9BA8D1)=1;Reject("event-only scene");
    Setup();At<uintptr_t>(0x9BA928)=1;Reject("queued scene transition");
    Setup();At<BYTE>(0x9006B0)=1;Reject("menu");
    Setup();At<uintptr_t>(0xAC0F48)=1;Reject("native transition context");
    Setup();At<uintptr_t>(0x716868)=0;Reject("missing gameplay scheduler");
    Setup();At<uintptr_t>(0x9BA920)=0;Reject("missing scene heap");
    Setup();At<BYTE>(0xABAC58)=1;Reject("scripted event state");
    Setup();At<BYTE>(0xABAC59)=1;Reject("scripted event state second flag");
    Setup();At<uintptr_t>(0x2AE9FA8)=1;Reject("Drive transition context");
    Setup();At<unsigned>(0x2A10504)=2;Reject("Drive native transition lock");
    Setup();At<uintptr_t>(0x2A105D0)=g_base+Other;Reject("current actor replaced");
    Setup();At<uintptr_t>(Player+1472)=g_base+Status+632;Reject("status replaced");
    Setup();At<uint32_t>(Status+616)=Other;Reject("status backlink mismatch");
    Setup();At<int>(Status+612)=0;Reject("unallocated status refcount");
    Setup();At<int>(0x2A23810)=0;Reject("status on free list");
    Setup();At<int>(0x2A23950)=81;Reject("malformed status pool count");
    Setup();At<int>(Status+608)=14;Reject("Roxas is not claimed as Sora");
    Setup();At<int>(Status)=0;Reject("dead player");
    Setup();At<int>(Status)=101;Reject("invalid HP");
    Setup();At<uint32_t>(Player)=0x74A518;Reject("different player descriptor");
    Setup();At<uintptr_t>(0x750300)=0;Reject("descriptor vtable modified");
    Setup();At<uintptr_t>(0x5CBA28+296)=0;Reject("input callback replaced");
    Setup();At<unsigned>(Player+1736)=0x80;Reject("not a Sora-category actor");
    Setup();At<unsigned>(Player+288)=0x10000000;Reject("deleting actor");
    Setup();At<unsigned>(Player+288)=0x100;Reject("incompatible actor state");
    Setup();At<unsigned>(Player+2488)=4;Reject("inactive actor");
    Setup();At<uint32_t>(Player+1696)=Other;Reject("attached actor");
    Setup();At<uintptr_t>(Player+360)=g_base+Other;Reject("motion owner backlink mismatch");
    Setup();At<int>(Player+3552)=7;Reject("special form outside supported Drive set");
    Setup();At<int>(Player+3552)=-1;Reject("invalid negative form");
    Setup();At<BYTE>(0x9ACDD4)=1;Reject("Actor and current form disagree");
    Setup();At<uintptr_t>(0x2A171C8)=g_base+Other;Reject("actor no longer listed");
    Setup();At<uint32_t>(Other+2704)=Player;Reject("cyclic live list");
    Setup();DWORD old=0,unused=0;void* page=reinterpret_cast<void*>(g_base+Player);
    Check(VirtualProtect(page,4096,PAGE_READONLY,&old)!=FALSE,"real read-only actor page");Reject("non-writable scalar");VirtualProtect(page,4096,old,&unused);
    Setup();context.player=1;At<uintptr_t>(0x2A105D0)=1;Reject("unreadable current actor pointer");
    Setup();ActorMovementCapabilities();Check(shared.supported[5]==(uint64_t(15)<<24),"exact capabilities344..347 only");
    const double args[8]{};TrainerResult result{};
    for(unsigned slot:{343u,348u,349u,350u,351u,352u})Check(!ActorMovementHandle(context,slot,args,result),"reserved and neighboring slots unclaimed");
    printf("ActorMovementGuardTests: %u checks, %u failures\n",checks,failures);
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
