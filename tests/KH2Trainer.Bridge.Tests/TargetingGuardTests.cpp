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
#include <limits.h>
#include <intrin.h>
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
#include "../../src/KH2Trainer.Bridge/PlayerRoleSupport.inl"
#include "../../src/KH2Trainer.Bridge/ActorLifetimeSupport.inl"
// This isolated target/movement/loot fixture never admits damage protection.
// CombatGuardTests exercises its actual controller, lifetime and native dispatch.
bool PlayerHealthControlReady(const TrainerContext&) { return false; }
#include "../../src/KH2Trainer.Bridge/CombatFeatures.inl"
#include "../../src/KH2Trainer.Bridge/DamageTuningFeatures.inl"
#include "../../src/KH2Trainer.Bridge/ActorMovementFeatures.inl"
#include "../../src/KH2Trainer.Bridge/TargetingFeatures.inl"
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

constexpr uintptr_t Bar=0x110010,Pref=0x110210,Sstm=0x110310,Params=Sstm+8;
void Resource() {
    At<uintptr_t>(0x2AE5E50)=g_base+Bar;At<unsigned>(Bar-16)=4096;
    At<unsigned>(Bar-12)=0x23234141;At<unsigned>(Bar-8)=1;
    memcpy(reinterpret_cast<void*>(g_base+Bar),"BAR\1",4);
    At<int>(Bar+4)=1;At<uint32_t>(Bar+8)=Bar;
    At<uint16_t>(Bar+16)=2;memcpy(reinterpret_cast<void*>(g_base+Bar+20),"pref",4);
    At<uint32_t>(Bar+24)=Pref;At<unsigned>(Bar+28)=512;
    memcpy(reinterpret_cast<void*>(g_base+Pref),"BAR\1",4);
    At<int>(Pref+4)=1;At<uint32_t>(Pref+8)=Pref;
    At<uint16_t>(Pref+16)=2;memcpy(reinterpret_cast<void*>(g_base+Pref+20),"sstm",4);
    At<uint32_t>(Pref+24)=Sstm;At<unsigned>(Pref+28)=128;
    At<int>(Sstm+4)=8;At<float>(Params+76)=1500.25f;At<float>(Params+80)=2000.5f;
    At<uintptr_t>(0x2AE5768)=g_base+Pref;At<uintptr_t>(0x2AE5760)=g_base+Params;
    At<float>(targeting::Factor)=1;At<float>(targeting::BreakDistance)=2000.5f;
    const BYTE scale[]={0x48,0x8B,0x05,0xF9,0x99,0x73,0x02,0xF3,0x0F,0x11,0x05,0xAD,0x56,0x66,0x02,0xF3,0x0F,0x59,0x40,0x50,0xF3,0x0F,0x11,0x05,0xA4,0x56,0x66,0x02,0xC3};
    const BYTE distance[]={0xF3,0x0F,0x11,0x05,0x98,0x56,0x66,0x02,0xC3};
    memcpy(reinterpret_cast<void*>(g_base+0x3ABD60),scale,sizeof(scale));
    memcpy(reinterpret_cast<void*>(g_base+0x3ABD80),distance,sizeof(distance));
}
void Init(int form=0){Setup(form);Resource();}
TrainerResult Run(unsigned slot,double value=0) {
    const double args[8]={value};TrainerResult r{};Check(TargetingHandle(context,slot,args,r),"write slot handled");return r;
}
TrainerResult Pair(bool restore,float expectedScale,float expectedBreak,float desiredScale,float desiredBreak,float retain=2000.5f) {
    double args[8]={restore?1.0:0.0,double(targeting::Bits(expectedScale)),double(targeting::Bits(expectedBreak)),
        double(targeting::Bits(desiredScale)),double(targeting::Bits(desiredBreak)),double(targeting::Bits(retain))};
    TrainerResult r{};Check(TargetingHandle(context,475,args,r),"paired command handled");return r;
}
void Reject(const char* why) {
    BYTE before[32];memcpy(before,reinterpret_cast<void*>(g_base+targeting::Factor-12),32);
    for(unsigned slot:{368u,369u,372u})Check(Run(slot,5).code!=0,why);
    Check(Pair(false,1,2000.5f,4,8002).code!=0,why);
    Check(!memcmp(before,reinterpret_cast<void*>(g_base+targeting::Factor-12),32),"rejection preserves both globals and surrounding bytes");
}
}
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,0x2C00000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!g_base)return 2;
    for(int form=0;form<=6;++form)for(double factor:{0.05,1.0,1.23456789,10.0}) {
        Init(form);BYTE actor[3608],resource[4096];memcpy(actor,reinterpret_cast<void*>(g_base+Player),sizeof(actor));memcpy(resource,reinterpret_cast<void*>(g_base+Bar),sizeof(resource));
        Check(Run(368,factor).code==0,"bounded scale for each supported Sora form");
        float native=static_cast<float>(factor),expected=native*2000.5f;
        Check(At<float>(targeting::Factor)==native&&At<float>(targeting::BreakDistance)==expected,"scale updates both globals with float32 product");
        TargetingSnapshot(context);Check(Valid(368)&&Valid(369)&&Valid(370)&&Valid(371)&&Valid(373)&&!Valid(372),"exact readout slots");
        Check(shared.values[370]==native*1500.25f&&shared.values[371]==1500.25&&shared.values[373]==2000.5,"derived acquisition and actual defaults are distinct");
        Check(Run(369,777.25).code==0&&At<float>(targeting::Factor)==native&&At<float>(targeting::BreakDistance)==777.25f,"break override preserves factor");
        Check(Run(372).code==0&&At<float>(targeting::Factor)==1&&At<float>(targeting::BreakDistance)==2000.5f,"reset uses loaded defaults");
        Check(!memcmp(actor,reinterpret_cast<void*>(g_base+Player),sizeof(actor))&&!memcmp(resource,reinterpret_cast<void*>(g_base+Bar),sizeof(resource)),"no actor, target or resource mutation");
    }
    for(unsigned slot:{368u,369u})for(double value:{-1.0,0.0,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity(),100001.0}) {
        Init();Check(Run(slot,value).code!=0&&At<float>(targeting::Factor)==1&&At<float>(targeting::BreakDistance)==2000.5f,"invalid policy input leaves both values unchanged");
    }
    Init();Check(Run(368,.049).code!=0&&Run(368,10.001).code!=0,"scale boundary");
    Init();Check(Run(369,1).code==0&&Run(369,100000).code==0,"break inclusive boundaries");
    Init();At<int>(0x716884)=2;TargetingSnapshot(context);Check(Valid(370),"read-only snapshot while field paused");Reject("paused edit");
    Init();++g_gameThread;Reject("wrong game thread");
    Init();g_shared=nullptr;Reject("no mapping");
    Init();shared.hostHeartbeat=GetTickCount()-5001;Reject("stale heartbeat");
    Init();g_disabled=1;Reject("disabled bridge");
    Init();context.base+=16;Reject("foreign base");
    Init();At<uintptr_t>(0x2AE9FA8)=1;Reject("Drive rebuilding actor");
    Init();At<BYTE>(0x9BA8D0)=0;Reject("scene unloaded");
    Init();At<uintptr_t>(0x9BA928)=1;Reject("scene queued");
    Init();At<BYTE>(0xABAC58)=1;Reject("scripted event");
    Init();At<uintptr_t>(0x2A171C8)=g_base+Other;Reject("actor removed from live list");
    Init();At<int>(Status)=0;Reject("dead Sora");
    Init();At<uintptr_t>(0x2AE5E50)=0;Reject("missing outer BAR");
    Init();At<unsigned>(Bar-12)=0;Reject("stale allocation magic");
    Init();At<unsigned>(Bar-8)=2;Reject("wrong allocation kind");
    Init();At<unsigned>(Bar-16)=4095;Reject("nonrounded allocation");
    Init();At<int>(Bar+4)=-1;Reject("negative BAR count");
    Init();At<int>(Bar+4)=0x7fffffff;Reject("BAR table extends beyond allocation");
    Init();At<uint32_t>(Bar+8)=Pref;Reject("outer BAR self mismatch");
    Init();At<uint16_t>(Bar+16)=3;Reject("wrong pref entry type");
    Init();At<unsigned>(Bar+20)=0;Reject("missing pref tag");
    Init();At<uint32_t>(Bar+24)=Bar+16;Reject("pref aliases index table");
    Init();At<unsigned>(Bar+28)=4096;Reject("pref exceeds outer allocation");
    Init();At<uintptr_t>(0x2AE5768)=g_base+Pref+16;Reject("installed pref mismatch");
    Init();At<uint32_t>(Pref+8)=Bar;Reject("nested BAR self mismatch");
    Init();At<int>(Pref+4)=33;Reject("nested index exceeds pref entry");
    Init();At<uint32_t>(Pref+24)=Bar+1000;Reject("sstm lies outside pref");
    Init();At<unsigned>(Pref+28)=7;Reject("sstm too short for relative pointer");
    Init();At<unsigned>(Pref+28)=91;Reject("parameter final byte outside sstm");
    Init();At<unsigned>(Pref+28)=92;Check(Run(368,2).code==0,"exact last-byte parameter bound");
    Init();At<int>(Sstm+4)=-1;Reject("negative relative pointer");
    Init();At<int>(Sstm+4)=0;Reject("null relative pointer");
    Init();At<int>(Sstm+4)=0x7fffffff;Reject("relative offset overflow");
    Init();At<uintptr_t>(0x2AE5760)=g_base+Params+4;Reject("installed parameters mismatch");
    Init();At<float>(Params+76)=0;Reject("degenerate acquisition default");
    Init();At<float>(Params+80)=std::numeric_limits<float>::infinity();Reject("nonfinite native default");
    Init();At<float>(Params+80)=-1;Reject("negative native default");
    Init();At<BYTE>(0x3ABD60)^=1;Reject("scale setter hook");
    Init();At<BYTE>(0x3ABD88)^=1;Reject("distance setter tail modified");
    Init();At<int>(Bar+4)=2;memcpy(reinterpret_cast<void*>(g_base+Bar+32),reinterpret_cast<void*>(g_base+Bar+16),16);At<uint32_t>(Bar+24)=0;Reject("broken first duplicate cannot be rescued by later valid tag");
    Init();At<int>(Pref+4)=2;memcpy(reinterpret_cast<void*>(g_base+Pref+32),reinterpret_cast<void*>(g_base+Pref+16),16);At<unsigned>(Pref+28)=0;Reject("nested first-match precedence");
    Init();At<uint16_t>(Bar+18)=1;Check(Run(368,2).code==0,"link word does not alter first-match semantics");
    Init();At<float>(targeting::Factor)=std::numeric_limits<float>::quiet_NaN();TargetingSnapshot(context);Check(!Valid(368)&&!Valid(370)&&Valid(369)&&Valid(371),"invalid live scalar suppresses only dependent diagnostics");Check(Run(372).code==0,"explicit reset repairs invalid live scalars");
    Init();DWORD old=0,unused=0;void* page=reinterpret_cast<void*>((g_base+targeting::Factor)&~uintptr_t(4095));Check(VirtualProtect(page,4096,PAGE_READONLY,&old)!=FALSE,"real read-only globals");Reject("unwritable globals");VirtualProtect(page,4096,old,&unused);
    Init();TargetingCapabilities();Check(shared.supported[5]==(uint64_t(63)<<48),"exact capability mask");
    Check(shared.supported[7]==((uint64_t(1)<<27)|(uint64_t(1)<<28)),"pair capabilities only 475 and 476");
    for(int form=0;form<=6;++form)for(float scale:{.15f,4.0f}) {
        Init(form);At<float>(targeting::Factor)=1.25f;At<float>(targeting::BreakDistance)=777.25f;
        Check(Pair(false,1.25f,777.25f,scale,scale*2000.5f).code==0,"pair applies both reward scales in each Sora form");
        TargetingSnapshot(context);Check(Valid(475)&&Valid(476)&&shared.values[475]==targeting::Bits(scale)&&shared.values[476]==targeting::Bits(scale*2000.5f),"snapshot pair is exact raw Float32 bits");
        At<float>(Params+80)=3000.25f;
        Check(Pair(true,scale,scale*2000.5f,1.25f,777.25f).code==0,"restore ignores changed retain parameter and exact original distance need not be scale times retain");
        Check(At<uint32_t>(targeting::Factor)==targeting::Bits(1.25f)&&At<uint32_t>(targeting::BreakDistance)==targeting::Bits(777.25f),"nondefault original restored bit-exactly");
    }
    for(int which=0;which<2;++which) {
        Init();Check(Pair(false,1,2000.5f,4,8002).code==0,"prepare pair conflict");
        At<uint32_t>(which?targeting::BreakDistance:targeting::Factor)++;
        const uint32_t s=At<uint32_t>(targeting::Factor),d=At<uint32_t>(targeting::BreakDistance);
        Check(Pair(true,4,8002,1,2000.5f).code==0,"one-ULP foreign edit is successful restore no-op");
        Check(At<uint32_t>(targeting::Factor)==s&&At<uint32_t>(targeting::BreakDistance)==d,"whole foreign pair preserved after either field changes");
        Check(Pair(false,4,8002,.15f,.15f*2000.5f).code!=0,"apply conflict rejects without takeover");
    }
    Init();Check(Pair(false,1,2000.5f,4,8002,2000).code!=0,"stale native retain bits reject apply");
    Check(Pair(false,1,2000.5f,4,8003).code!=0,"forged product rejected");
    for(float f:{.049f,10.01f,0.0f,-0.0f,-1.0f,std::numeric_limits<float>::quiet_NaN(),std::numeric_limits<float>::infinity()}) {
        Init();Check(Pair(true,1,2000.5f,f,777.25f).code!=0,"invalid desired scale cannot restore");
        Check(Pair(true,1,2000.5f,1,f).code!=0 || (isfinite(f)&&f>0),"invalid desired break cannot restore");
        At<float>(targeting::Factor)=f;TargetingSnapshot(context);Check(!Valid(475)&&!Valid(476),"invalid pair suppresses both exact slots");
    }
    Init();Check(Pair(true,1,2000.5f,.05f,10000000).code==0,"inclusive restorable pair boundaries");
    Check(Pair(true,.05f,10000000,10,10000002).code!=0,"break above largest supported native default product rejected");
    Init();double pairArgs[8]={0,double(targeting::Bits(1)),double(targeting::Bits(2000.5f)),double(targeting::Bits(4)),double(targeting::Bits(8002)),double(targeting::Bits(2000.5f))};TrainerResult pairResult{};
    Check(TargetingHandle(context,475,nullptr,pairResult)&&pairResult.code!=0,"null pair arguments rejected");
    for(unsigned i=0;i<6;++i)for(double invalid:{-1.0,.5,4294967296.0,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}) {
        const double oldArg=pairArgs[i];pairArgs[i]=invalid;Check(TargetingHandle(context,475,pairArgs,pairResult)&&pairResult.code!=0,"every raw-bit argument requires uint32 and operation0/1");pairArgs[i]=oldArg;
    }
    for(int character:{4,14}) {Init();At<int>(Status+608)=character;Check(Pair(false,1,2000.5f,4,8002).code!=0,"pair does not widen Sora-only compatibility");}
    const double args[8]{};TrainerResult r{};for(unsigned slot:{367u,370u,371u,373u,374u,375u,376u,474u,476u,477u})Check(!TargetingHandle(context,slot,args,r),"read-only and neighboring slots cannot mutate");
    printf("TargetingGuardTests: %u checks, %u failures\n",checks,failures);VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
