#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdint.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits>
namespace {
uintptr_t g_base=0; DWORD g_gameThread=0; volatile LONG g_disabled=0;
struct TrainerContext { uintptr_t base,player,status; bool sceneReady; };
struct TrainerResult { LONG code; const wchar_t* text; };
struct Shared { DWORD hostHeartbeat; double values[128]; uint64_t valid[2],supported[2]; } shared{};
Shared* g_shared=&shared;
template<class T>T& At(uintptr_t rva){return *reinterpret_cast<T*>(g_base+rva);}
bool Readable(const void* p,size_t size) {
    MEMORY_BASIC_INFORMATION m{};if(!p||reinterpret_cast<uintptr_t>(p)>UINTPTR_MAX-size||
       !VirtualQuery(p,&m,sizeof(m))||m.State!=MEM_COMMIT||(m.Protect&(PAGE_GUARD|PAGE_NOACCESS)))return false;
    return reinterpret_cast<uintptr_t>(p)+size<=reinterpret_cast<uintptr_t>(m.BaseAddress)+m.RegionSize;
}
bool Writable(const void* p,size_t size){MEMORY_BASIC_INFORMATION m{};return Readable(p,size)&&VirtualQuery(p,&m,sizeof(m))&&m.Protect==PAGE_READWRITE;}
uintptr_t DecodePacked(uint32_t v){return v?g_base+v:0;}
bool IsInteger(double n,double lo,double hi){return isfinite(n)&&floor(n)==n&&n>=lo&&n<=hi;}
void SnapshotValue(unsigned s,double n){shared.values[s]=n;shared.valid[s/64]|=uint64_t(1)<<(s%64);}
void SupportCapability(unsigned s){shared.supported[s/64]|=uint64_t(1)<<(s%64);}
#include "../../../trainer/Native/CombatFeatures.inl"
unsigned checks=0,failures=0,calls=0;int passedDelta=0;unsigned passedBar=0;BYTE passedEffects=0;
TrainerContext context{};
void Check(bool ok,const char* name){++checks;if(!ok){++failures;printf("FAIL %s\n",name);}}
intptr_t __fastcall Original(uintptr_t,uintptr_t,int delta,unsigned bar,BYTE effects){++calls;passedDelta=delta;passedBar=bar;passedEffects=effects;return 1234;}
void Stub(uintptr_t rva,uintptr_t dest){BYTE bytes[12]={0x48,0xb8};memcpy(bytes+2,&dest,8);bytes[10]=0xff;bytes[11]=0xe0;DWORD old=0;VirtualProtect(reinterpret_cast<void*>(g_base+rva),12,PAGE_EXECUTE_READWRITE,&old);memcpy(reinterpret_cast<void*>(g_base+rva),bytes,12);FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(g_base+rva),12);}
TrainerResult Command(unsigned slot,double value=0){double args[8]={value};TrainerResult r{};Check(CombatHandle(context,slot,args,r),"known combat command handled");return r;}
intptr_t Hit(int delta=-10,unsigned bar=0,BYTE effects=1){return combat::DamageHook(g_base+combat::ControllerRva,context.player,delta,bar,effects);}
void Ready(){g_shared=&shared;g_disabled=0;g_gameThread=GetCurrentThreadId();shared.hostHeartbeat=GetTickCount();context.sceneReady=true;At<BYTE>(0x9BA8D0)=1;At<BYTE>(0x9BA8D1)=0;At<int>(0x716884)=1;At<uintptr_t>(0x9BA928)=0;At<uintptr_t>(0x716868)=g_base+0x90000;At<uintptr_t>(0x9BA920)=g_base+0xA0000;At<uintptr_t>(0x2A105D0)=context.player;At<uintptr_t>(0x50000+1472)=context.status;At<uint32_t>(0x60000+616)=0x50000;At<int>(0x60000)=50;At<int>(0x60004)=100;At<uint32_t>(0x50000+1736)=0x80;At<uint32_t>(0x50000+2488)=0;At<uint32_t>(0x50000+288)=0;At<uint32_t>(0x50000)=DWORD(combat::ControllerRva);At<uintptr_t>(combat::ControllerRva)=g_base+combat::VtableRva;At<uintptr_t>(combat::DamageSlotRva)=g_base+combat::DamageRva;}
void Enemy(){At<uintptr_t>(0x50000+3528)=g_base+combat::LockRva;At<uintptr_t>(combat::LockRva+56)=context.player;At<int>(combat::LockRva)=2;At<uint32_t>(combat::LockRva+4)=0x70000;At<uint32_t>(combat::LockRva+12)=0;At<uintptr_t>(0x2A171C8)=g_base+0x70000;At<uint32_t>(0x70000+2704)=0;At<uint32_t>(0x70000+1736)=0x12;At<uint32_t>(0x70000+288)=0;At<uint32_t>(0x70000+2488)=0;At<uintptr_t>(0x70000+1472)=g_base+0x80000;At<uint32_t>(0x80000+616)=0x70000;At<int>(0x80000)=80;At<int>(0x80004)=500;At<float>(0x70000+3400)=17;At<float>(0x70000+3404)=100;}
}
int main(){
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,0x2C00000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!g_base)return 2;
    context={g_base,g_base+0x50000,g_base+0x60000,true};Ready();Enemy();Stub(combat::DamageRva,reinterpret_cast<uintptr_t>(&Original));
    Check(Command(106,1).code==0,"guard installs only original slot");
    Check(Hit()==50&&calls==0&&At<int>(0x60000)==50,"negative HP callback blocked before original and without HP writes");
    Check(combat::blockedHits==1&&combat::lastBlockedDamage==10,"blocked metrics exact");
    Check(Hit(10,0,7)==1234&&calls==1&&passedDelta==10&&passedEffects==7,"healing forwards full ABI");
    Check(Hit(-10,1,9)==1234&&passedBar==1&&passedEffects==9,"secondary bars forward");
    Check(Hit(0)==1234&&passedDelta==0,"zero delta forwards");
    Check(Hit(INT_MIN)==50&&combat::lastBlockedDamage==2147483648u,"INT_MIN magnitude does not overflow");
    unsigned before=calls;
    combat::DamageHook(g_base+combat::ControllerRva,g_base+0x70000,-10,0,1);Check(calls==before+1,"other actors pass through");
    shared.hostHeartbeat=GetTickCount()-5001;Check(Hit()==1234,"expired heartbeat cannot block");
    shared.hostHeartbeat=GetTickCount()+1;Check(Hit()==1234,"future heartbeat fails unsigned age check");
    shared.hostHeartbeat=0;Check(Hit()==1234,"zero heartbeat rejected");shared.hostHeartbeat=GetTickCount();
    g_shared=nullptr;Check(Hit()==1234,"missing host forwards");g_shared=&shared;
    g_disabled=1;Check(Hit()==1234,"disabled bridge forwards");g_disabled=0;
    ++g_gameThread;Check(Hit()==1234,"other thread forwards");g_gameThread=GetCurrentThreadId();
    At<BYTE>(0x9BA8D1)=1;Check(Hit()==1234,"scene transition forwards before next tick");At<BYTE>(0x9BA8D1)=0;
    At<uint32_t>(0x60000+616)=0x70000;Check(Hit()==1234,"status backlink mismatch forwards");At<uint32_t>(0x60000+616)=0x50000;
    At<uintptr_t>(0x50000+1472)=g_base+0x81000;Check(Hit()==1234,"status replacement forwards");At<uintptr_t>(0x50000+1472)=context.status;
    At<uintptr_t>(0x2A105D0)=g_base+0x51000;Check(Hit()==1234,"player replacement forwards");At<uintptr_t>(0x2A105D0)=context.player;
    At<BYTE>(0x717011)^=1;Check(Hit()==1234,"full ten-byte room identity checked");At<BYTE>(0x717011)^=1;
    At<uintptr_t>(0x9BA920)+=8;Check(Hit()==1234,"scene heap replacement forwards");At<uintptr_t>(0x9BA920)-=8;
    At<int>(0x60000)=0;Check(Hit()==1234,"dead player not resurrected");At<int>(0x60000)=50;
    Check(Command(106,0).code==0&&At<uintptr_t>(combat::DamageSlotRva)==g_base+combat::DamageRva,"disable restores owned callback");
    Check(At<int>(0x60008)==0&&At<int>(0x2A23960)==0,"no HP floor or save mirror mutation");
    At<uintptr_t>(combat::DamageSlotRva)=g_base+0x123;Check(Command(106,1).code!=0&&At<uintptr_t>(combat::DamageSlotRva)==g_base+0x123,"foreign callback preserved on install");Ready();
    Check(Command(106,1).code==0,"reinstall guard");At<uintptr_t>(combat::DamageSlotRva)=g_base+0x456;CombatReset({g_base,0,0,false});Check(At<uintptr_t>(combat::DamageSlotRva)==g_base+0x456&&!combat::guard.enabled,"foreign replacement preserved on reset");Ready();
    Check(Command(106,1).code==0,"install for expiry test");shared.hostHeartbeat=GetTickCount()-5001;CombatTick(context);Check(!combat::guard.enabled&&At<uintptr_t>(combat::DamageSlotRva)==g_base+combat::DamageRva,"tick expiry restores hook");Ready();
    Check(Command(106,1).code==0,"install for transition test");context.sceneReady=false;CombatTick(context);Check(!combat::guard.enabled,"scene loss disables guard");Ready();
    Check(Command(106,1).code==0,"install for field-pause interaction");At<int>(0x716884)=2;CombatTick(context);Check(combat::guard.enabled&&Hit()==1234,"field pause retains policy but suppresses no callback");At<int>(0x716884)=1;Check(Hit()==50,"single resumed field step regains protection");At<BYTE>(0x9006B0)=1;CombatTick(context);Check(!combat::guard.enabled,"native menu takeover disables policy");At<BYTE>(0x9006B0)=0;Ready();
    Check(Command(106,0.5).code!=0&&Command(106,std::numeric_limits<double>::quiet_NaN()).code!=0,"invalid toggle values rejected");
    CombatSnapshot(context);Check(shared.values[98]==80&&shared.values[99]==500&&shared.values[100]==17&&shared.values[101]==100,"target snapshot follows validated enemy");
    At<int>(0x716884)=2;shared.valid[0]=shared.valid[1]=0;CombatSnapshot(context);Check((shared.valid[1]&(uint64_t(1)<<(98-64)))&&shared.values[98]==80,"target display remains available during field pause");Check(Command(102).code!=0,"target mutation still requires gameplay state1");At<int>(0x716884)=1;
    Check(Command(102).code==0&&At<int>(0x80000)==500,"refill living target HP");
    Check(Command(110,1).code==0&&At<int>(0x80000)==1,"HP setter remains nonlethal");
    Check(Command(110,0).code!=0&&Command(110,501).code!=0&&Command(110,1.5).code!=0,"HP setter bounds and integer validated");
    At<int>(0x80008)=100;Check(Command(110,99).code!=0&&Command(110,100).code==0,"native boss HP floor respected");At<int>(0x80008)=501;Check(Command(102).code!=0,"corrupt HP floor rejected");At<int>(0x80008)=0;
    Check(Command(103).code==0&&At<float>(0x70000+3400)==0&&At<float>(0x70000+3404)==100,"revenge reset preserves threshold");
    Check(Command(104,99.5).code==0&&At<float>(0x70000+3400)==99.5f,"fractional RV allowed");
    Check(Command(104,-1).code!=0&&Command(104,1000001).code!=0&&Command(104,std::numeric_limits<double>::infinity()).code!=0,"RV invalid values rejected");
    At<int>(combat::LockRva)=1;Check(Command(102).code!=0,"automatic targets read-only");Enemy();
    At<uintptr_t>(0x2A171C8)=0;Check(Command(102).code!=0,"unlisted stale pointer rejected");Enemy();
    At<uint32_t>(0x70000+2704)=0x70000;Check(Command(102).code!=0,"cyclic live list rejected");Enemy();
    At<uint32_t>(0x70000+2704)=0x2C10000;Check(Command(102).code!=0,"corrupt list tail rejected even after target found");Enemy();
    At<uint32_t>(0x70000+1736)=2;Check(Command(103).code!=0,"non-enemy actor tail not interpreted as RV");Enemy();
    At<uint32_t>(0x70000+2488)=4;Check(Command(102).code!=0,"defeated target not resurrected");Enemy();
    At<int>(0x80000)=0;Check(Command(102).code!=0,"zero HP target rejected");Enemy();
    At<uint32_t>(0x80000+616)=0x50000;Check(Command(102).code!=0,"reused status with wrong backlink rejected");Enemy();
    At<uint32_t>(0x80000+620)=1;Check(Command(102).code!=0,"save-backed status excluded");At<uint32_t>(0x80000+620)=0;
    At<float>(0x70000+3400)=std::numeric_limits<float>::quiet_NaN();Check(Command(103).code!=0,"invalid RV rejected");Enemy();
    At<uintptr_t>(combat::LockRva+56)=0;Check(Command(102).code!=0,"wrong lock owner rejected");Enemy();
    At<uint32_t>(combat::LockRva+12)=0x123;Check(Command(102).code!=0,"alternate target reference excluded");Enemy();
    At<uint32_t>(0x70000+288)=0x80000;Check(Command(102).code!=0,"queued-destruction target excluded");Enemy();
    CombatCapabilities();Check((shared.supported[1]&(uint64_t(1)<<(106-64)))!=0,"guard capability published");
    double args[8]{};TrainerResult r{};Check(!CombatHandle(context,109,args,r)&&!CombatHandle(context,111,args,r),"unused slots are not claimed");
    printf("CombatGuardTests: %u checks, %u failures\n",checks,failures);VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
