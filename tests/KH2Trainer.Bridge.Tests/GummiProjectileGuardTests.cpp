#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define KH2_GUMMI_TESTS
#define KH2_GUMMI_PROJECTILE_TESTS
#include <windows.h>
#include <stdint.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <limits>
#include <vector>
#include <initializer_list>
namespace {
uintptr_t g_base=0; DWORD g_gameThread=0; volatile LONG g_disabled=0;
struct TrainerContext { uintptr_t base,player,status; bool sceneReady; };
struct TrainerResult { LONG code; const wchar_t* text; };
struct Shared { DWORD hostHeartbeat; double values[512]; uint64_t valid[8],supported[8]; } shared{};
Shared* g_shared=&shared;
template<class T>T& At(uintptr_t rva){return *reinterpret_cast<T*>(g_base+rva);}
bool afterCall=false, destroyAfterCall=false; unsigned postCallReads=0,calls=0;
uintptr_t watchRead=0; unsigned watchOrdinal=0,watchSeen=0; void(*onRead)()=nullptr;
bool Readable(const void* p,size_t count) {
    if(afterCall)++postCallReads;
    const uintptr_t start=reinterpret_cast<uintptr_t>(p);
    if(onRead && start==watchRead && ++watchSeen==watchOrdinal){auto f=onRead;onRead=nullptr;f();}
    if(!start || count>UINTPTR_MAX-start)return false;
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
uintptr_t DecodePacked(uint32_t value){return value?g_base+value:0;}
bool IsInteger(double n,double lo,double hi){return isfinite(n)&&floor(n)==n&&n>=lo&&n<=hi;}
void SnapshotValue(unsigned s,double n){shared.values[s]=n;shared.valid[s/64]|=uint64_t(1)<<(s%64);}
void SupportCapability(unsigned s){shared.supported[s/64]|=uint64_t(1)<<(s%64);}
#include "../../src/KH2Trainer.Bridge/GummiFeatures.inl"
#include "../../src/KH2Trainer.Bridge/GummiProjectileFeatures.inl"
constexpr uintptr_t Pool=0x100008, Sprites=0x150000, Manager=0x90000, Task=0x91000;
constexpr size_t Allocation=0xC00000;
unsigned checks=0,failures=0;
TrainerContext host{};
void Check(bool ok,const char* name){++checks;if(!ok){++failures;printf("FAIL %s\n",name);}}
void __fastcall NativeClear() {
    ++calls;
    const uintptr_t pool=At<uintptr_t>(gummi_projectile::PoolRva),sprites=At<uintptr_t>(gummi_projectile::SpriteRva);
    for(unsigned i=0;i<768;++i) {
        const uintptr_t p=pool+176*i;
        auto& flags=*reinterpret_cast<unsigned*>(p+128);
        if(flags&0x100){flags&=~0x100u;*reinterpret_cast<uint32_t*>(sprites+16*(*reinterpret_cast<int*>(p+152))+12)=0;}
    }
    if(destroyAfterCall) {
        At<uintptr_t>(gummi_projectile::PoolRva)=0;At<uintptr_t>(gummi_projectile::SpriteRva)=0;
        At<uintptr_t>(gummi::PlayerRva)=0;At<uintptr_t>(gummi::SchedulerRva)=0;
    }
    afterCall=true;
}
void Player(uintptr_t rva) {
    At<uint32_t>(rva)=DWORD(gummi::DescriptorRva);At<uintptr_t>(rva+0x550)=g_base+rva+0x570;
    At<uintptr_t>(rva+0x570)=g_base+gummi::StateVtableRva;At<float>(rva+0x578)=42.25f;At<int>(rva+0x57C)=120;
    At<int>(rva+0x5D8)=2;At<unsigned>(rva+0x140C)=0;
}
void Node(uintptr_t rva,uintptr_t previous,uintptr_t next,int priority,uintptr_t fn) {
    At<uintptr_t>(rva)=g_base+fn;At<uintptr_t>(rva+88)=g_base+Manager;
    At<unsigned>(rva+96)=1;At<int>(rva+100)=priority;At<uintptr_t>(rva+104)=g_base+0x1F60D0;
    At<uintptr_t>(rva+112)=0;At<uintptr_t>(rva+120)=next?g_base+next:0;At<uintptr_t>(rva+128)=previous?g_base+previous:0;
}
void Ready(unsigned active=5) {
    memset(reinterpret_cast<void*>(g_base),0,Allocation);memset(&shared,0,sizeof(shared));
    g_shared=&shared;g_disabled=0;g_gameThread=GetCurrentThreadId();shared.hostHeartbeat=GetTickCount();
    host={g_base,0,0,false};afterCall=false;destroyAfterCall=false;postCallReads=0;calls=0;onRead=nullptr;watchSeen=0;
    At<uintptr_t>(gummi::ModuleRva)=g_base+gummi::ModuleVtableRva;At<uintptr_t>(gummi::ModuleRva+8)=g_base+Manager;
    At<int>(gummi::ModuleRva+36)=1;At<uintptr_t>(gummi::ModeListRva)=g_base+gummi::ModuleRva;
    At<uintptr_t>(gummi::HeapRva)=At<uintptr_t>(gummi::ModuleHeapRva)=g_base+0xA0000;
    At<uintptr_t>(gummi::SchedulerRva)=g_base+Manager;At<int>(gummi::MissionPhaseRva)=8;
    At<uintptr_t>(gummi::PlayerRva)=g_base+0x50000;At<uintptr_t>(gummi::DescriptorRva)=g_base+gummi::DescriptorVtableRva;
    Player(0x50000);Player(0x52000);At<uint32_t>(0x9A8788)=3;At<uint32_t>(0x716C04)=2;
    At<uintptr_t>(Manager+16)=At<uintptr_t>(Manager+24)=g_base+Task;Node(Task,0,0,22000,0x1F6080);
    At<uintptr_t>(gummi_projectile::PoolRva)=g_base+Pool;At<uintptr_t>(gummi_projectile::SpriteRva)=g_base+Sprites;
    At<uintptr_t>(gummi_projectile::VtableRva+48)=g_base+gummi_projectile::CleanupRva;At<uint64_t>(Pool-8)=768;
    for(unsigned i=0;i<768;++i) {
        At<uintptr_t>(Pool+176*i)=g_base+gummi_projectile::VtableRva;At<int>(Pool+176*i+152)=i;
        At<unsigned>(Pool+176*i+128)=0x28|(i<active?0x100:0);At<unsigned>(Sprites+16*i+12)=0x05000080;
    }
    for(const auto& sig:gummi_projectile::signatures)memcpy(reinterpret_cast<void*>(g_base+sig.rva),sig.bytes,sig.size);
}
TrainerResult Command(){double args[8]{};TrainerResult r{};Check(GummiProjectileHandle(host,360,args,r),"action is routed");return r;}
void Rejected(const char* why){const auto oldCalls=calls;const auto r=Command();Check(r.code!=0&&calls==oldCalls,why);}
bool Valid(unsigned s){return(shared.valid[s/64]&(uint64_t(1)<<(s%64)))!=0;}
void Observe(){memset(shared.valid,0,sizeof(shared.valid));GummiProjectileSnapshot(host);}
void ProtectReject(uintptr_t rva,DWORD protection,const char* why) {
    DWORD old=0,temp=0;Check(VirtualProtect(reinterpret_cast<void*>(g_base+rva),0x1000,protection,&old)!=0,"fixture protection set");
    Rejected(why);Check(VirtualProtect(reinterpret_cast<void*>(g_base+rva),0x1000,old,&temp)!=0,"fixture protection restored");
}
void Drift(void(*change)()){watchRead=g_base+gummi_projectile::ClearRva;watchOrdinal=1;watchSeen=0;onRead=change;}
}
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,Allocation,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!g_base)return 2;
    gummi_projectile::testClear=NativeClear;
    for(unsigned count:{0u,1u,5u,767u,768u}) {
        Ready(count);Observe();Check(Valid(361)&&shared.values[361]==count,"fresh count includes zero and full pools");
        std::vector<BYTE> pool(gummi_projectile::PoolBytes),sprites(gummi_projectile::SpriteBytes);
        memcpy(pool.data(),reinterpret_cast<void*>(g_base+Pool),pool.size());memcpy(sprites.data(),reinterpret_cast<void*>(g_base+Sprites),sprites.size());
        for(unsigned i=0;i<count;++i){*reinterpret_cast<unsigned*>(pool.data()+176*i+128)&=~0x100u;*reinterpret_cast<unsigned*>(sprites.data()+16*i+12)=0;}
        const auto r=Command();Check(r.code==0&&calls==1,"accepted clear calls native exactly once including empty pool");
        Check(memcmp(pool.data(),reinterpret_cast<void*>(g_base+Pool),pool.size())==0,"only active bits change in record pool");
        Check(memcmp(sprites.data(),reinterpret_cast<void*>(g_base+Sprites),sprites.size())==0,"only active main sprite controls change");
        Check(postCallReads==0,"native return never dereferences prior state");
    }
    Ready(0);for(unsigned i:{3u,200u,767u})At<unsigned>(Pool+176*i+128)|=0x100;Observe();Check(Valid(361)&&shared.values[361]==3,"sparse active pool count");
    auto r=Command();Check(!r.code&&calls==1&&!(At<unsigned>(Pool+176*767+128)&0x100),"last sparse record cleared");
    Ready();destroyAfterCall=true;r=Command();Check(!r.code&&calls==1&&!postCallReads,"teardown inside callout causes no stale post-call reads");
    Ready();shared.hostHeartbeat=0;Rejected("zero heartbeat");
    Ready();shared.hostHeartbeat=GetTickCount()-5001;Rejected("expired heartbeat");
    Ready();shared.hostHeartbeat=GetTickCount()+1000;Rejected("future heartbeat");
    Ready();g_gameThread++;Rejected("foreign thread");
    Ready();g_gameThread=0;Rejected("missing engine thread");
    Ready();g_disabled=1;Rejected("disabled bridge");
    Ready();g_shared=nullptr;Rejected("missing shared context");
    Ready();host.base=0;Rejected("wrong module base");
    Ready();At<int>(gummi::ModuleRva+36)=2;Observe();Check(Valid(361),"paused module allows fresh readout");Rejected("paused module blocks action");
    Ready();At<int>(gummi::MissionPhaseRva)=14;Rejected("result phase blocks action");
    Ready();At<int>(0x505D8)=5;Rejected("rebirth phase");
    Ready();At<float>(0x50578)=0;Rejected("dead ship");
    Ready();At<unsigned>(0x5140C)=0x40000;Rejected("ship transition flag");
    Ready();At<uintptr_t>(gummi::PlayerRva)=0;Rejected("missing player");
    Ready();At<uintptr_t>(gummi::HeapRva)=0;Rejected("released heap");Observe();Check(!Valid(361),"released heap omits snapshot");
    Ready();At<uintptr_t>(gummi::ModuleRva+8)=1;Rejected("foreign scheduler");
    Ready();At<uint32_t>(gummi::ModuleRva+20)=DWORD(gummi::ModuleRva);Rejected("cyclic mode list");
    Ready();At<uintptr_t>(Manager+16)=At<uintptr_t>(Manager+24)=0;Rejected("no projectile task");Observe();Check(!Valid(361),"stale nonnull pool without owner is invalid");
    Ready();At<uintptr_t>(Manager+32)=g_base+Task;Rejected("scheduler is dispatching");
    Ready();At<uintptr_t>(Task+88)=0;Rejected("task manager backlink");
    Ready();At<uintptr_t>(Task+128)=g_base+Task;Rejected("head previous link");
    Ready();At<uintptr_t>(Task+120)=g_base+Task;Rejected("task self cycle");
    Ready();At<uintptr_t>(Manager+24)=0;Rejected("tail mismatch");
    Ready();At<uintptr_t>(Task+104)=0;Rejected("task cleanup ownership");
    Ready();At<uintptr_t>(Task+112)=g_base+0x92000;Rejected("fiber replacing direct task");
    Ready();At<unsigned>(Task+96)=3;Rejected("wrong task group");
    Ready();At<int>(Task+100)=22001;Rejected("wrong task priority");
    Ready();At<uintptr_t>(Task)=g_base+0x1F60D0;Rejected("wrong task callback");
    Ready();Node(Task,0,0x91200,22000,0x1F6080);Node(0x91200,Task,0,22000,0x1F6080);At<uintptr_t>(Manager+24)=g_base+0x91200;Rejected("duplicate pool tasks");
    Ready();Node(Task,0,0x91200,22000,0x1F6080);Node(0x91200,Task,0,21999,0x111111);At<uintptr_t>(Manager+24)=g_base+0x91200;Rejected("unsorted task priorities");
    Ready();Node(Task,0,0x91200,22000,0x1F6080);Node(0x91200,Task,0,22001,0x111111);At<uintptr_t>(Manager+24)=g_base+0x91200;r=Command();Check(!r.code&&calls==1,"unrelated valid tasks coexist");
    Ready();for(unsigned i=0;i<2049;++i)Node(0x300000+160*i,i?0x300000+160*(i-1):0,i<2048?0x300000+160*(i+1):0,22000,i?0x111111:0x1F6080);
    At<uintptr_t>(Manager+16)=g_base+0x300000;At<uintptr_t>(Manager+24)=g_base+0x300000+160*2048;Rejected("task traversal is bounded");
    for(unsigned i:{0u,384u,767u}) {
        Ready();At<unsigned>(Pool+176*i+128)|=1;Rejected("individually allocated flag blocks every record");
        Ready();At<uintptr_t>(Pool+176*i)=0;Rejected("wrong subtype in pool");
        for(int bad:{-1,768,static_cast<int>((i+1)%768)}){Ready();At<int>(Pool+176*i+152)=bad;Rejected("sprite index and fixed slot identity");}
    }
    Ready();At<uint64_t>(Pool-8)=767;Rejected("count header mismatch");
    Ready();At<uintptr_t>(gummi_projectile::PoolRva)=0;Rejected("null pool");
    Ready();At<uintptr_t>(gummi_projectile::PoolRva)=4;Rejected("pool header underflow");
    Ready();At<uintptr_t>(gummi_projectile::PoolRva)=UINTPTR_MAX-7;Rejected("pool span overflow");
    Ready();At<uintptr_t>(gummi_projectile::PoolRva)++;Rejected("pool alignment");
    Ready();At<uintptr_t>(gummi_projectile::SpriteRva)=0;Rejected("null sprite buffer");
    Ready();At<uintptr_t>(gummi_projectile::SpriteRva)=UINTPTR_MAX-3;Rejected("sprite span overflow");
    Ready();At<uintptr_t>(gummi_projectile::SpriteRva)++;Rejected("sprite alignment");
    Ready();At<uintptr_t>(gummi_projectile::SpriteRva)=g_base+Pool+128;Rejected("record and sprite buffers overlap");
    Ready();At<uintptr_t>(gummi_projectile::VtableRva+48)=g_base+0x23D850;Rejected("foreign cleanup callback");
    Ready();ProtectReject(0x100000,PAGE_READONLY,"read-only pool flags");
    Ready();ProtectReject(0x121000,PAGE_NOACCESS,"truncated pool span");
    Ready();ProtectReject(0x152000,PAGE_NOACCESS,"truncated sprite buffer");
    Ready();ProtectReject(0x150000,PAGE_READONLY,"read-only sprite writes");
    Ready();ProtectReject(0x91000,PAGE_NOACCESS,"unreadable owner node");
    for(const auto& sig:gummi_projectile::signatures){Ready();At<BYTE>(sig.rva+sig.size-1)^=1;Rejected("full code pin includes final byte");}
    Ready();Drift([](){At<uintptr_t>(gummi::PlayerRva)=g_base+0x52000;});Rejected("fresh ship identity");
    Ready();Drift([](){At<uint32_t>(0x9A8788)++;});Rejected("fresh route identity");
    Ready();Drift([](){At<uint32_t>(0x716C04)++;});Rejected("fresh variant identity");
    Ready();Drift([](){shared.hostHeartbeat=0;});Rejected("host expires during preflight");
    Ready();Drift([](){shared.hostHeartbeat=0;});watchOrdinal=2;Rejected("host expires during final code verification");
    Ready();Drift([](){At<int>(gummi::ModuleRva+36)=2;});Rejected("module pauses during preflight");
    Ready();Drift([](){At<unsigned>(Pool+176*767+128)|=1;});Rejected("last record ownership changes during preflight");
    Ready();Drift([](){memcpy(reinterpret_cast<void*>(g_base+0x180000),reinterpret_cast<void*>(g_base+Pool-8),gummi_projectile::PoolBytes+8);At<uintptr_t>(gummi_projectile::PoolRva)=g_base+0x180008;});Rejected("equally shaped replacement pool is rejected");
    Ready();Drift([](){memcpy(reinterpret_cast<void*>(g_base+0x160000),reinterpret_cast<void*>(g_base+Sprites),gummi_projectile::SpriteBytes);At<uintptr_t>(gummi_projectile::SpriteRva)=g_base+0x160000;});Rejected("replacement sprite buffer is rejected");
    Ready();Drift([](){memcpy(reinterpret_cast<void*>(g_base+0x91200),reinterpret_cast<void*>(g_base+Task),152);At<uintptr_t>(Manager+16)=At<uintptr_t>(Manager+24)=g_base+0x91200;});Rejected("replacement native task is rejected");
    Ready();DWORD old=0,temp=0;Check(VirtualProtect(reinterpret_cast<void*>(g_base+0x100000),0x1000,PAGE_READONLY,&old)!=0,"read-only snapshot fixture");
    Observe();Check(Valid(361)&&shared.values[361]==5,"read-only pool remains observable");Check(VirtualProtect(reinterpret_cast<void*>(g_base+0x100000),0x1000,old,&temp)!=0,"restore snapshot fixture");
    Ready();At<int>(Pool+176*767+152)=-1;Observe();Check(!Valid(361),"snapshot rejects invalid final sprite index");
    Ready();double args[8]{};TrainerResult result{};args[7]=std::numeric_limits<double>::quiet_NaN();Check(GummiProjectileHandle(host,360,args,result)&&result.code!=0&&!calls,"nonfinite argument rejected");
    Ready();Check(GummiProjectileHandle(host,360,nullptr,result)&&result.code!=0&&!calls,"missing args rejected");
    Ready();Check(!GummiProjectileHandle(host,361,args,result)&&!GummiProjectileHandle(host,359,args,result)&&!GummiProjectileHandle(host,362,args,result)&&!calls,"read-only and unrelated slots are not commands");
    Ready();GummiProjectileCapabilities();uint64_t expectedCapabilities[8]{};expectedCapabilities[360/64]=(uint64_t(1)<<(360%64))|(uint64_t(1)<<(361%64));
    Check(memcmp(shared.supported,expectedCapabilities,sizeof(expectedCapabilities))==0,"exact capability ownership");
    printf("GummiProjectileGuardTests: %u checks, %u failures\n",checks,failures);
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
