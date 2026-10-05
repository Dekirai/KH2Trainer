#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define KH2_DRIVE_TESTS
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <math.h>
#include <limits.h>
#include <string.h>
#include <initializer_list>
#include <limits>
// Fake memory and callbacks only: never opens the game or calls game code.
namespace {
uintptr_t g_base=0;
volatile LONG g_disabled=0;
DWORD g_gameThread=0;
struct Shared { DWORD hostHeartbeat; uint64_t supported[8]; double values[512]; } shared{};
Shared* g_shared=&shared;
struct TrainerContext { uintptr_t base,player,status; bool sceneReady; };
struct TrainerResult { LONG code; const wchar_t* text; };
template<class T> T& At(uintptr_t rva) { return *reinterpret_cast<T*>(g_base+rva); }
bool Readable(const void* address,SIZE_T size) {
    uintptr_t cursor=reinterpret_cast<uintptr_t>(address);
    if (!cursor || size>UINTPTR_MAX-cursor) return false;
    const uintptr_t end=cursor+size;
    while(cursor<end) {
        MEMORY_BASIC_INFORMATION m{};
        if(!VirtualQuery(reinterpret_cast<const void*>(cursor),&m,sizeof(m)) || m.State!=MEM_COMMIT || (m.Protect&(PAGE_NOACCESS|PAGE_GUARD))) return false;
        const uintptr_t next=reinterpret_cast<uintptr_t>(m.BaseAddress)+m.RegionSize;
        if(next<=cursor) return false;
        cursor=next;
    }
    return true;
}
bool Writable(const void* p,SIZE_T n) {
    uintptr_t cursor=reinterpret_cast<uintptr_t>(p);
    if(!cursor || n>UINTPTR_MAX-cursor) return false;
    const uintptr_t end=cursor+n;
    while(cursor<end) {
        MEMORY_BASIC_INFORMATION m{};
        if(!VirtualQuery(reinterpret_cast<const void*>(cursor),&m,sizeof(m)) || m.State!=MEM_COMMIT ||
            (m.Protect&(PAGE_NOACCESS|PAGE_GUARD))) return false;
        const DWORD protection=m.Protect&0xff;
        if(protection!=PAGE_READWRITE && protection!=PAGE_WRITECOPY &&
            protection!=PAGE_EXECUTE_READWRITE && protection!=PAGE_EXECUTE_WRITECOPY) return false;
        const uintptr_t next=reinterpret_cast<uintptr_t>(m.BaseAddress)+m.RegionSize;
        if(next<=cursor) return false;
        cursor=next;
    }
    return true;
}
bool IsInteger(double v,double lo,double hi) { return isfinite(v)&&floor(v)==v&&v>=lo&&v<=hi; }
uintptr_t DecodePacked(uint32_t v) { return v ? g_base+v : 0; }
void SupportCapability(unsigned slot) { shared.supported[slot/64]|=uint64_t(1)<<(slot%64); }
void SnapshotValue(unsigned slot,double value) { shared.values[slot]=value; }
DWORD fakeNow=100000;
DWORD TestTickCount() { return fakeNow; }
#define GetTickCount TestTickCount
#include "../../../trainer/Native/ProgressionFeatures.inl"
#include "../../../trainer/Native/DriveFeatures.inl"
unsigned checks=0,failures=0,begins=0;
bool queueWorks=true;
struct Call { uintptr_t actor; int form; } calls[8]{};
constexpr uint16_t formItems[]={0,26,27,563,31,29,30};
void Check(bool value,const char* label) { ++checks; if(!value) { ++failures; printf("FAIL: %s\n",label); } }
void __fastcall Begin(uintptr_t actor,int form) {
    calls[begins++]={actor,form};
    if(!queueWorks) return;
    const uintptr_t ctx=g_base+0x110000;
    At<uintptr_t>(0x2AE9FA8)=ctx;
    *reinterpret_cast<uintptr_t*>(ctx)=actor;
    *reinterpret_cast<int*>(ctx+8)=form;
    *reinterpret_cast<uintptr_t*>(ctx+40)=g_base+0x111000;
    At<unsigned>(0x2A10504)|=2;
    // These are writes by the fake native callback, never by the trainer.
    At<BYTE>(0x9ACDD4)=static_cast<BYTE>(form);
}
constexpr uintptr_t actorRva=0x100000,statusRva=0x2A17290,commandsRva=0x103000,itemsRva=0x104000,objectsRva=0x105000,levelsRva=0x106000;
template<class T> void Put(uintptr_t p,SIZE_T offset,T value) { *reinterpret_cast<T*>(p+offset)=value; }
uintptr_t Row(uintptr_t rva,unsigned index,unsigned stride) { return g_base+rva+8+static_cast<uintptr_t>(index)*stride; }
TrainerContext Context() { return {g_base,At<uintptr_t>(0x2A105D0),g_base+statusRva,true}; }
void Setup() {
    ZeroMemory(reinterpret_cast<void*>(g_base),0x2C00000);
    ZeroMemory(&shared,sizeof(shared));
    begins=0; queueWorks=true; ZeroMemory(calls,sizeof(calls)); fakeNow=100000; drive_features::queue={};
    g_disabled=0; g_gameThread=GetCurrentThreadId();
    shared.hostHeartbeat=GetTickCount();
    memcpy(reinterpret_cast<void*>(g_base+0x40CE60),drive_features::kBeginBytes,sizeof(drive_features::kBeginBytes));
    At<BYTE>(0x9BA8D0)=1; At<int>(0x716884)=1;
    At<uintptr_t>(0x2A105D0)=g_base+actorRva;
    At<uintptr_t>(0x2A171C8)=g_base+actorRva;
    Put<uint32_t>(g_base+actorRva,0,0x750300);
    Put<uint32_t>(g_base+actorRva,8,0x108000); Put<uint32_t>(g_base+actorRva,12,0x109000);
    Put<uintptr_t>(g_base+actorRva,344,g_base+0x10A000);
    Put<uintptr_t>(g_base+actorRva,1472,g_base+statusRva);
    Put<unsigned>(g_base+actorRva,1736,0x1000080);
    Put<uintptr_t>(g_base+actorRva,3536,g_base+0x10B000);
    Put<int>(g_base+statusRva,0,100); Put<int>(g_base+statusRva,4,120);
    Put<int>(g_base+statusRva,608,1); Put<uint32_t>(g_base+statusRva,616,actorRva);
    Put<int>(g_base+statusRva,612,1); Put<uint32_t>(g_base+statusRva,592,0x9ABDA0); Put<uint32_t>(g_base+statusRva,620,0x9ABDA0);
    Put<BYTE>(g_base+statusRva,431,1); Put<BYTE>(g_base+statusRva,433,9); Put<BYTE>(g_base+statusRva,434,9);
    At<uintptr_t>(0x9BA920)=g_base+0x10C000; At<uintptr_t>(0x10C000)=g_base+0x10C100;
    At<uintptr_t>(0x716868)=g_base+0x10D000; At<uintptr_t>(0x2A17180)=g_base+0x10E000;
    At<uint64_t>(0x9A98B0)=0x0000003A4A32484Bull;
    At<BYTE>(0x9ABDA0+15)=1;
    At<uintptr_t>(0x2AEA8A0)=g_base+0x130000; At<int>(0x130004)=1;
    At<uintptr_t>(0x2AE58A8)=g_base+0x131000; At<int>(0x131004)=2; At<int>(0x13100c)=4; At<int>(0x131010)=1;
    At<uintptr_t>(0x2A25370)=g_base+itemsRva; At<int>(itemsRva+4)=6;
    for(unsigned form=1;form<=6;++form) {
        const uintptr_t row=Row(itemsRva,form-1,24);
        Put<uint16_t>(row,0,formItems[form]); Put<BYTE>(row,2,21); Put<BYTE>(row,3,1);
        Put<uint16_t>(row,16,static_cast<uint16_t>(form+9)); Put<uint16_t>(row,18,static_cast<uint16_t>(form));
        At<BYTE>(0x9ABDA0+3588+56*(form-1)+2)=1;
        At<uint16_t>(0x2A252F0+2*(form+11))=static_cast<uint16_t>(100+form);
    }
    At<uint16_t>(0x2A252F0+16)=100;
    At<uintptr_t>(0x2A25030)=g_base+objectsRva; At<int>(objectsRva+4)=7;
    for(unsigned i=0;i<7;++i) {
        const uintptr_t row=Row(objectsRva,i,96); Put<unsigned>(row,0,100+i);
        memcpy(reinterpret_cast<void*>(row+8),"P_EX100",8);
    }
    At<uintptr_t>(0x2AE5760)=g_base+0x107000;
    At<float>(0x107000+104)=100; At<float>(0x107000+152)=1; At<float>(0x107000+156)=1; At<float>(0x107000+160)=100;
    At<uintptr_t>(0x2AE5708)=g_base+levelsRva; At<int>(levelsRva+4)=2;
    Put<BYTE>(Row(levelsRva,0,8),0,0x61); Put<int>(Row(levelsRva,0,8),4,10);
    Put<BYTE>(Row(levelsRva,1,8),0,0x62); Put<int>(Row(levelsRva,1,8),4,0);
    At<uintptr_t>(0x2A11498)=g_base+0x150000; At<int>(0x150004)=1;
    At<uint16_t>(0x150008)=29; At<BYTE>(0x150008+36)=0;
    At<uintptr_t>(0x2A11668)=g_base+0x151000; At<int>(0x151004)=1;
    At<uint16_t>(0x151008)=50255&0x7fff; At<unsigned>(0x15100c)=16;
    memcpy(reinterpret_cast<void*>(g_base+0x151010),"Antiform",9);
    // A normal Sora fixture has a real equipped Keyblade and native weapon
    // model/motion mappings. Form offhand slots remain empty until prepared.
    At<uint16_t>(0x9ABDA0)=600;
    At<int>(itemsRva+4)=8;
    for(unsigned i=0;i<2;++i) {
        const uintptr_t row=Row(itemsRva,6+i,24);
        Put<uint16_t>(row,0,static_cast<uint16_t>(600+i)); Put<BYTE>(row,2,2);
        Put<uint16_t>(row,4,static_cast<uint16_t>(1+i));
    }
    At<int>(objectsRva+4)=9;
    for(unsigned i=0;i<7;++i) {
        const uintptr_t row=Row(objectsRva,i,96);
        Put<uint16_t>(row,76,1); Put<uint16_t>(row,78,1); Put<BYTE>(row,87,static_cast<BYTE>(i));
    }
    for(unsigned i=0;i<2;++i) {
        const uintptr_t row=Row(objectsRva,7+i,96); Put<unsigned>(row,0,200+i);
        memcpy(reinterpret_cast<void*>(row+8),"W_EX010",8);
    }
    At<uintptr_t>(0x2AE5A38)=g_base+0x170000; At<unsigned>(0x170004)=16;
    At<unsigned>(0x170000+4*17)=200; At<unsigned>(0x170000+4*18)=201;
    At<uintptr_t>(0x2AE5A40)=g_base+0x171000;
    At<uintptr_t>(0x2AE5E50)=g_base+0x16F000;
    At<unsigned>(0x16EFF0)=0x3000; At<unsigned>(0x16EFF4)=0x23234141; At<unsigned>(0x16EFF8)=1;
    At<unsigned>(0x16F000)=0x01524142; At<int>(0x16F004)=2; At<uint32_t>(0x16F008)=0x16F000;
    At<uint16_t>(0x16F010)=2; At<unsigned>(0x16F014)=0x746e6577;
    At<uint32_t>(0x16F018)=0x170000; At<unsigned>(0x16F01C)=256;
    At<uint16_t>(0x16F020)=2; At<unsigned>(0x16F024)=0x74736d77;
    At<uint32_t>(0x16F028)=0x171000; At<unsigned>(0x16F02C)=128;
    memcpy(reinterpret_cast<void*>(g_base+0x171000+32*2),"W_EX010",8);
    memcpy(reinterpret_cast<void*>(g_base+0x171000+32*3),"W_EX010",8);
    drive_features::testBegin=Begin;
}
TrainerResult Execute(unsigned slot=122,double form=1,const TrainerContext* given=nullptr) {
    const TrainerContext c=given?*given:Context(); TrainerResult result{}; double args[8]{form};
    Check(DriveHandle(c,slot,args,result),"domain claims its command"); return result;
}
void Rejected(const char* label,unsigned slot=122,double form=1) {
    const auto result=Execute(slot,form); Check(result.code!=0&&begins==0,label);
}
void SetForm(unsigned form) {
    const auto c=Context(); Put<int>(c.player,3552,static_cast<int>(form)); At<BYTE>(0x9ACDD4)=static_cast<BYTE>(form);
    Put<BYTE>(c.status,431,form?2:1);
    Put<uint32_t>(c.status,596,form?0x9ABDA0+3588+56*(form-1):0);
    Put<float>(c.status,436,form?400.0f:0.0f); Put<float>(c.status,440,form?400.0f:0.0f);
}
void CompleteNative(unsigned form) {
    const auto old=Context(); const uintptr_t next=old.player==g_base+actorRva?g_base+0x102000:g_base+actorRva;
    memcpy(reinterpret_cast<void*>(next),reinterpret_cast<void*>(old.player),3608);
    At<uintptr_t>(0x2A105D0)=next; At<uintptr_t>(0x2A171C8)=next;
    Put<uint32_t>(old.status,616,static_cast<uint32_t>(next-g_base));
    At<uintptr_t>(0x2AE9FA8)=0; At<unsigned>(0x2A10504)&=~2u; At<int>(0x2AE9790)=0;
    SetForm(form);
}
void Tick() { DriveTick(Context()); }
void QueueFrom(unsigned current,unsigned target) { Setup(); SetForm(current); const auto r=Execute(target?122:123,target); Check(r.code==0,"queue setup accepted"); }
void AssertStopped(drive_features::Outcome outcome,unsigned expectedCalls,const char* label) {
    Check(drive_features::queue.phase==drive_features::Idle && drive_features::queue.outcome==outcome && begins==expectedCalls,label);
    CompleteNative(0); Tick(); Check(begins==expectedCalls,"stopped trainer queue never restarts after native completion");
}
}
#include "DriveWeaponTests.cpp"
int main() {
    using namespace drive_features;
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,0x2C00000,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    if(!g_base) return 2;
    Setup(); Check(LiveScene(Context())&&CanStart(Context(),1)&&CanStart(Context(),6),"valid fake scene and Anti resources pass structural gates");
    // All 49 current/requested combinations, including all six same-form restarts.
    for(unsigned current=0;current<=6;++current) for(unsigned target=0;target<=6;++target) {
        Setup(); SetForm(current); const uintptr_t initial=Context().player;
        const auto r=Execute(target?122:123,target); Check(r.code==0,"7x7 requested transition accepted");
        if(!current&&!target) { Check(begins==0&&queue.outcome==Completed,"base Revert is a successful no-op"); continue; }
        Check(begins==1&&calls[0].actor==initial&&calls[0].form==static_cast<int>(current?0:target),"7x7 correct native first step and actor");
        Tick(); Check(begins==1&&queue.phase!=Idle,"pending native context never advances second step");
        CompleteNative(current?0:target); Tick();
        if(current&&target) {
            Check(begins==2&&calls[1].actor!=initial&&calls[1].form==static_cast<int>(target)&&queue.phase==WaitingForForm,"7x7 fresh base actor starts exactly one selected form");
            CompleteNative(target); Tick();
        }
        Check(queue.phase==Idle&&queue.outcome==Completed&&Field<int>(Context().player,3552)==static_cast<int>(target),"7x7 completion matches actual actor and selected form");
        const unsigned before=begins; Tick(); Tick(); Check(begins==before,"completed queue never retries");
    }
    for(unsigned form=1;form<=6;++form) {
        Setup(); At<BYTE>(statusRva+433)=0; At<BYTE>(statusRva+434)=0; At<BYTE>(statusRva+431)=0;
        At<unsigned>(0x2A10504)=1; At<unsigned>(0x2A10508)=0xffffffff; At<unsigned>(0x2A11400)=0x40002;
        const auto r=Execute(122,form);
        Check(r.code==0&&begins==1&&calls[0].form==static_cast<int>(form),"zero gauge, locked form, no allies and normal Drive restrictions are bypassed");
        Check(At<unsigned>(0x9A98B0+14016)==0&&At<BYTE>(statusRva+433)==0,"trainer neither grants unlocks nor fills or charges gauge");
    }
    Setup(); queueWorks=false; auto r=Execute(); Tick(); Check(r.code==2&&begins==1&&queue.outcome==NativeQueueFailed,"missing native queue reports once without retry");
    for(double invalid : {0.0,7.0,1.5,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}) {
        Setup(); Rejected("bad form input rejected before native calls",122,invalid);
    }
    Setup(); double args[8]{}; r={}; Check(!DriveHandle(Context(),121,args,r),"unowned command remains unhandled");
    QueueFrom(1,6); r=Execute(122,2); Check(r.code!=0&&begins==1&&queue.target==6,"busy queue cannot be retargeted");
    for(unsigned phase=1;phase<=3;++phase) {
        if(phase==1) QueueFrom(1,6); else if(phase==2) QueueFrom(0,6); else QueueFrom(1,0);
        const uintptr_t native=At<uintptr_t>(0x2AE9FA8); r=Execute(126);
        Check(r.code==0&&At<uintptr_t>(0x2AE9FA8)==native,"cancel leaves active native fiber untouched"); AssertStopped(Cancelled,1,"cancel terminates each queue phase");
    }
    QueueFrom(1,6); auto unready=Context(); unready.sceneReady=false; r=Execute(126,0,&unready); Check(r.code==0,"cancel does not require a playable scene");
    QueueFrom(1,6); DriveReset(Context()); AssertStopped(Cancelled,1,"disable-all drops queued second step only");
    QueueFrom(1,6); shared.hostHeartbeat=0; Tick(); AssertStopped(HostExpired,1,"zero heartbeat drops queued second step");
    QueueFrom(1,6); fakeNow+=5001; Tick(); AssertStopped(HostExpired,1,"expired heartbeat drops queued second step");
    QueueFrom(1,6); g_disabled=1; Tick(); AssertStopped(HostExpired,1,"disabled bridge drops queue without native calls");
    QueueFrom(1,6); g_gameThread=0; Tick(); AssertStopped(HostExpired,1,"foreign thread cannot progress queue");
    QueueFrom(1,6); fakeNow+=kTimeout; shared.hostHeartbeat=fakeNow; Tick(); AssertStopped(TimedOut,1,"overall timeout includes native first step");
    QueueFrom(1,6); fakeNow=0x20; shared.hostHeartbeat=fakeNow; queue.started=0xffff0000; Tick(); AssertStopped(TimedOut,1,"timeout subtraction handles tick wrap");
    QueueFrom(1,6); fakeNow=0x20; shared.hostHeartbeat=fakeNow; queue.started=0xffffff00; Tick(); Check(queue.phase==WaitingForBase,"short wrapped interval remains active");
    for(uintptr_t rva : {0x9BA920u,0x716868u,0x2A17180u}) {
        QueueFrom(1,6); At<uintptr_t>(rva)+=16; Tick(); AssertStopped(SceneChanged,1,"heap or scheduler replacement cancels queued step");
    }
    for(unsigned i=0;i<10;++i) { QueueFrom(1,6); ++At<BYTE>(0x717008+i); Tick(); AssertStopped(SceneChanged,1,"every room-identity byte binds queue"); }
    QueueFrom(1,6); At<uintptr_t>(0x9BA928)=1; Tick(); At<uintptr_t>(0x9BA928)=0; AssertStopped(SceneChanged,1,"observed transient room transition irrevocably cancels queued step");
    for(uintptr_t rva : {0x9BA8D1u,0xABAC58u,0xABAC59u}) { QueueFrom(1,6); At<BYTE>(rva)=1; Tick(); AssertStopped(SceneChanged,1,"observed event/title entry cancels queued step"); }
    QueueFrom(1,6); auto c=Context(); c.sceneReady=false; DriveTick(c); AssertStopped(SceneChanged,1,"unready scene cancels queue");
    // Engine-owned context replacement, including in-place field/task changes.
    QueueFrom(1,6); At<uintptr_t>(0x2AE9FA8)=g_base+0x112000; Tick(); AssertStopped(SafetyRejected,1,"foreign context pointer aborts follow-up");
    for(unsigned offset : {0u,8u,40u}) {
        QueueFrom(1,6); At<unsigned>(0x110000+offset)^=1; Tick(); AssertStopped(SafetyRejected,1,"context source/form/task change aborts follow-up");
    }
    QueueFrom(1,6); At<uintptr_t>(0x2AE9FA8)=0; At<unsigned>(0x2A10504)=0; SetForm(0); Tick();
    Check(begins==1&&queue.phase==WaitingForBase,"same old actor plus updated save byte is insufficient completion");
    QueueFrom(1,6); CompleteNative(0); At<unsigned>(0x2A10504)|=2; Tick(); AssertStopped(SafetyRejected,1,"native transition lock must be released before second step");
    QueueFrom(1,6); CompleteNative(0); At<int>(0x2AE9790)=1; Tick(); AssertStopped(SafetyRejected,1,"saved partner array must be empty after Revert cleanup");
    QueueFrom(1,6); CompleteNative(0); At<uint16_t>(0x2A252F0+34)=999; Tick(); AssertStopped(SafetyRejected,1,"fresh second-step model validation blocks changed resources");
    QueueFrom(0,6); CompleteNative(6); At<float>(statusRva+436)=0; Tick(); Check(queue.outcome==SafetyRejected,"zero completed native timer is not reported as success");
    Setup(); g_disabled=1; Rejected("disabled bridge rejected");
    Setup(); g_gameThread=0; Rejected("foreign thread rejected");
    Setup(); shared.hostHeartbeat=0; Rejected("zero heartbeat rejected");
    Setup(); shared.hostHeartbeat=fakeNow-5001; Rejected("expired heartbeat rejected");
    Setup(); c=Context(); c.sceneReady=false; r=Execute(122,1,&c); Check(r.code!=0&&!begins,"unready context rejected");
    Setup(); c=Context(); c.base=0; r=Execute(122,1,&c); Check(r.code!=0&&!begins,"wrong base rejected");
    for(uintptr_t rva : {0x9BA8D1u,0xABAC58u,0xABAC59u,0x9006B0u,0xABADE0u}) { Setup(); At<BYTE>(rva)=1; Rejected("event/menu/title/capture blocks request"); }
    for(uintptr_t rva : {0x9BA928u,0xAC0F48u,0x2AE9FA8u}) { Setup(); At<uintptr_t>(rva)=1; Rejected("transition or native menu blocks request"); }
    Setup(); At<unsigned>(0x2A10504)=2; Rejected("native form transition lock blocks request");
    Setup(); At<unsigned>(0x2A24EDC)=1; Rejected("active summon blocks request");
    Setup(); At<int>(0x716884)=2; Rejected("field pause blocks request");
    Setup(); At<unsigned>(0x2A11400)=0x20; Rejected("actor freeze blocks request");
    Setup(); At<uintptr_t>(0x2A105D0)=0; Rejected("stale player rejected");
    Setup(); At<uintptr_t>(actorRva+1472)=0; Rejected("status identity rejected");
    Setup(); At<uint32_t>(statusRva+616)=actorRva+16; Rejected("status backlink rejected");
    Setup(); At<int>(statusRva+608)=14; Rejected("Roxas rejected");
    Setup(); At<uint32_t>(actorRva)=0x74A518; Rejected("non-playable Sora controller rejected");
    Setup(); At<int>(statusRva)=0; Rejected("dead Sora rejected");
    Setup(); At<uint32_t>(actorRva+1696)=1; Rejected("attached Sora rejected");
    Setup(); At<uintptr_t>(actorRva+3400)=1; Rejected("special action ownership rejected");
    Setup(); At<unsigned>(actorRva+288)=0x100; Rejected("actor already transitioning rejected");
    Setup(); At<BYTE>(0x9ACDD4)=1; Rejected("save and actor form mismatch rejected");
    Setup(); At<uintptr_t>(0x2A17180)=0; Rejected("missing actor scheduler rejected");
    Setup(); At<uintptr_t>(0x9BA920)=0; Rejected("missing native heap rejected");
    Setup(); At<int>(0x2AE9790)=3; Rejected("invalid saved party count rejected");
    Setup(); At<int>(0x2AE9790)=1; Rejected("base form requires empty two-entry suspended-partner list");
    Setup(); SetForm(1); At<int>(0x2AE9790)=1; At<int>(0x2AE9788)=18; Rejected("saved party sentinel cannot index model table",123,0);
    Setup(); SetForm(1); At<int>(0x2AE9790)=1; At<int>(0x2AE9788)=1; At<uint16_t>(0x2A25302)=999; Rejected("missing saved party model rejected",123,0);
    Setup(); At<uintptr_t>(0x2A239B0)=1; Rejected("bad party actor rejected");
    Setup(); At<uintptr_t>(0x2A171C8)=0; Rejected("player absent from native list rejected");
    Setup(); At<uint32_t>(actorRva+2704)=actorRva; Rejected("cyclic actor list rejected before native traversal");
    Setup(); At<uint32_t>(actorRva+2704)=0x2c00000; Rejected("unreadable actor list link rejected");
    Setup(); At<uintptr_t>(0x2A0FF68)=g_base+0x120000; At<uintptr_t>(0x120008)=g_base+0x121000; At<float>(0x120000+1704)=std::numeric_limits<float>::quiet_NaN(); Rejected("nonfinite area multiplier rejected");
    Setup(); At<BYTE>(0x9ACDE4+1)=19; Rejected("invalid world costume rejected");
    Setup(); At<BYTE>(0x9ACDE4+1)=18; r=Execute(); Check(r.code==0&&begins==1,"no-character costume sentinel accepted for absent party");
    Setup(); At<BYTE>(0x9ACDE4+1)=1; At<uint16_t>(0x2A25302)=999; Rejected("world costume missing object rejected");
    Setup(); At<int>(0x2A23950)=81; Rejected("out-of-range status free count rejected");
    Setup(); At<int>(0x2A23950)=1; At<int>(0x2A23810)=80; Rejected("out-of-range free status index rejected");
    Setup(); At<int>(0x2A23950)=2; At<int>(0x2A23810)=1; At<int>(0x2A23814)=1; Rejected("duplicate free status index rejected");
    Setup(); At<int>(0x2A23950)=1; At<int>(0x2A23810)=0; Rejected("player status cannot be in free list");
    Setup(); At<int>(statusRva+612)=0; Rejected("unowned status refcount rejected");
    Setup(); At<int>(statusRva+612)=INT_MAX; Rejected("native refcount overflow rejected");
    Setup(); At<uint32_t>(statusRva+592)=0x9ABDA0+276; Rejected("foreign character save rejected");
    Setup(); At<uint32_t>(statusRva+620)=0; Rejected("missing Drive save rejected");
    Setup(); At<uint32_t>(statusRva+596)=0x9ABDA0+3588; Rejected("base Sora cannot retain unrelated form save pointer");
    Setup(); At<uintptr_t>(0x2AEA8A0)=0; Rejected("missing equipment stat table rejected");
    Setup(); At<BYTE>(0x9ABDA0+15)=0; Rejected("invalid saved level rejected");
    Setup(); At<BYTE>(0x9ABDA0+16)=9; Rejected("armor count past slot array rejected");
    Setup(); At<uint16_t>(0x9ABDA0)=999; Rejected("missing equipped weapon rejected");
    Setup(); At<uint16_t>(0x9ABDA0+84)=0x8000|26; Rejected("equipped non-ability item rejected");
    Setup(); At<uint16_t>(0x9ABDA0+3588)=999; r=Execute();
    Check(r.code==0 && At<uint16_t>(0x9ABDA0+3588)==600,"missing target form weapon uses validated main Keyblade");
    Setup(); At<uint16_t>(0x9ABDA0+3588+8)=0x8000|26; Rejected("invalid target form ability rejected");
    Setup(); At<BYTE>(0x9ABDA0+3588+2)=8; Rejected("invalid form level rejected");
    Setup(); At<BYTE>(0x40CE60)=0x90; Rejected("changed native form entry rejected");
    Setup(); At<uint64_t>(0x9A98B0)=0; Rejected("invalid save header rejected");
    Setup(); At<uint16_t>(0x2A252F0+24)=999; Rejected("missing selected model rejected");
    Setup(); At<uint16_t>(0x2A252F0+24)=566; Rejected("context-dependent object alias rejected");
    Setup(); Put<BYTE>(Row(objectsRva,1,96),8,0); At<uintptr_t>(0x2A25038)=g_base+0x140000; At<int>(0x140004)=1; At<unsigned>(0x140008)=101; memcpy(reinterpret_cast<void*>(g_base+0x140010),"P_EX100",8); Rejected("invalid first object match cannot be hidden by later table");
    Setup(); At<float>(0x107000+104)=std::numeric_limits<float>::quiet_NaN(); Rejected("invalid form timer factor rejected");
    Setup(); At<float>(0x107000+104)=std::numeric_limits<float>::max(); Rejected("native timer multiplication overflow rejected");
    Setup(); At<int>(0x107000+140)=INT_MAX; Rejected("Anti timer gauge overflow rejected",122,6);
    Setup(); At<float>(0x107000+104)=0; Rejected("zero timer factor rejected");
    Setup(); SetForm(6); At<uint16_t>(0x9ABDA0+3588+56*5+8)=0x8000|26; Rejected("Anti Revert validates current form abilities",123,0);
    Setup(); At<uintptr_t>(0x2A11498)=0; Rejected("missing form message table rejected even for non-Anti");
    Setup(); At<BYTE>(0x150008+36)=6; Rejected("override index is bounded to exactly six slots");
    Setup(); At<uint16_t>(0x150008)=28; Rejected("missing message29 rejected");
    Setup(); At<int>(0x150004)=2; At<uint16_t>(0x150048)=29; Rejected("duplicate message29 rejected");
    Setup(); At<uintptr_t>(0x2A11668)=0; Rejected("missing Anti text and fallback rejected",122,6);
    Setup(); At<unsigned>(0x15100c)=8; Rejected("Anti text offset inside row table rejected",122,6);
    Setup(); memset(reinterpret_cast<void*>(g_base+0x151010),'X',4096); Rejected("unbounded Anti string rejected",122,6);
    Setup(); At<uintptr_t>(0x2A11668)=0; At<uintptr_t>(0x2A11678)=g_base+0x151000; At<uint16_t>(0x151008)=0xADC; r=Execute(122,6); Check(r.code==0&&begins==1,"native system fallback text is supported");
    Setup(); DriveCapabilities(); for(unsigned slot=122;slot<=127;++slot) Check((shared.supported[slot/64]&(uint64_t(1)<<(slot%64)))!=0,"implemented Drive capability published");
    QueueFrom(2,6); DriveSnapshot(Context()); Check(shared.values[124]==6&&shared.values[125]==WaitingForBase&&shared.values[127]==Queued,"queue snapshot publishes target phase and last switch result");
    RunWeaponTests();
    printf("Drive guard tests: %u checks, %u failures\n",checks,failures);
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE); return failures?1:0;
}
