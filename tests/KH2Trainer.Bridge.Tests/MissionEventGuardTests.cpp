#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define KH2_MISSION_TESTS
#define KH2_MISSIONEVENT_TESTS
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
template<class T>T& At(uintptr_t rva){return *reinterpret_cast<T*>(g_base+rva);}
uintptr_t unreadable=0,unwritable=0; void (*onCodeRead)()=nullptr;
bool afterCall=false; unsigned postCallReads=0; DWORD fakeNow=100000;
bool Readable(const void* p,SIZE_T n) {
    const uintptr_t start=reinterpret_cast<uintptr_t>(p);
    if(afterCall) ++postCallReads;
    if(onCodeRead && start==g_base+0x3FBAE0){auto fn=onCodeRead;onCodeRead=nullptr;fn();}
    if(!start || n>UINTPTR_MAX-start || (unreadable && start<=unreadable && start+n>unreadable))return false;
    const uintptr_t end=start+n; uintptr_t cursor=start;
    while(cursor<end){
        MEMORY_BASIC_INFORMATION m{};
        if(!VirtualQuery(reinterpret_cast<void*>(cursor),&m,sizeof(m)) || m.State!=MEM_COMMIT || (m.Protect&(PAGE_NOACCESS|PAGE_GUARD)))return false;
        const uintptr_t next=reinterpret_cast<uintptr_t>(m.BaseAddress)+m.RegionSize;
        if(next<=cursor)return false; cursor=next;
    }
    return true;
}
bool Writable(const void* p,SIZE_T n){
    const uintptr_t a=reinterpret_cast<uintptr_t>(p);
    if(unwritable && a<=unwritable && a+n>unwritable)return false;
    if(!Readable(p,n))return false;
    MEMORY_BASIC_INFORMATION m{};
    return VirtualQuery(p,&m,sizeof(m)) && (m.Protect&(PAGE_READWRITE|PAGE_WRITECOPY|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY));
}
bool IsInteger(double v,double lo,double hi){return isfinite(v)&&floor(v)==v&&v>=lo&&v<=hi;}
uintptr_t DecodePacked(uint32_t v){return v?g_base+v:0;}
void SnapshotValue(unsigned s,double v){shared.values[s]=v;shared.valid[s/64]|=uint64_t(1)<<(s%64);}
void SupportCapability(unsigned s){shared.supported[s/64]|=uint64_t(1)<<(s%64);}
DWORD TestTick(){return fakeNow;}
#define GetTickCount TestTick
#include "../../src/KH2Trainer.Bridge/MissionFeatures.inl"
#include "../../src/KH2Trainer.Bridge/MissionEventFeatures.inl"
unsigned checks=0,failures=0,calls=0,events=0,completedHud=0,resetHud=0,sounds=0;
int lastEvent=-1,lastIndex=-1,lastInteger=-1; float lastFloat=0; uintptr_t lastScore=0;
bool endMission=false,changeMaximum=false,eventSawOld=false,markAfterCall=true;
char nativeReturn=0;
constexpr uintptr_t actor=0x100000,status=0x101000,descriptor=0x110000,bar=0x111000,storage=0x2A0F8B0;
constexpr uintptr_t outer=0x132000,heap=0x133000,heapVt=0x134000,cache=0x140000;
void Check(bool ok,const char* text){++checks;if(!ok){++failures;printf("FAIL: %s\n",text);}}
TrainerContext Context(){return {g_base,g_base+actor,g_base+status,true};}
uintptr_t FixtureWidget(unsigned slot,unsigned index=0){return storage+(slot==232?1088:slot==231?592+72*index:352+80*index);}
void Dispatch(int event,int index,uintptr_t w,bool gauge){
    ++events;lastEvent=event;lastIndex=index;
    eventSawOld=gauge?At<float>(w+56)==20.5f:At<int>(w+56)==10;
    if(changeMaximum)At<int>(w+36)=50;
    if(endMission){At<uintptr_t>(0x2A0FF68)=0;At<uintptr_t>(0x2A105D0)=0;At<uintptr_t>(0x9BA928)=g_base+0x160000;}
}
void Threshold(uintptr_t w,int value){
    int threshold=At<int>(w+40);if(threshold<=0)return;
    const bool complete=At<int>(w+32)<=threshold?value>=threshold:value<=threshold;
    if(complete && !(At<unsigned>(w+24)&8)){if((At<unsigned>(w+24)&4)&&At<int>(w+52))++sounds;At<unsigned>(w+24)|=8;++completedHud;}
    if(!complete && (At<unsigned>(w+24)&8)){At<unsigned>(w+24)&=~8u;++resetHud;}
}
void SetCounter(uintptr_t w,int value){
    const int maximum=At<int>(w+36),old=At<int>(w+56),id=At<int>(w+28);
    if(value>=maximum){value=maximum;if(old<maximum && id!=-1 && (At<unsigned>(w+24)&4)){Dispatch(123,id,w,false);value=At<int>(w+36);}}
    else if(value<=0){if(old>0 && id!=-1 && (At<unsigned>(w+24)&4))Dispatch(14,id,w,false);value=0;}
    Threshold(w,value);At<int>(w+56)=value;
}
char __fastcall Counter(int value,int index){
    ++calls;lastInteger=value;lastIndex=index;SetCounter(FixtureWidget(230,index),value);afterCall=markAfterCall;return nativeReturn;
}
char __fastcall Gauge(float value,int index){
    ++calls;lastFloat=value;lastIndex=index;const uintptr_t w=FixtureWidget(231,index);
    if(value<=0){if(At<float>(w+56)>0 && At<int>(w+28)!=-1 && (At<unsigned>(w+24)&4))Dispatch(136,index,w,true);value=0;}
    else if(value>=static_cast<float>(At<int>(w+36))){
        if(At<float>(w+56)<static_cast<float>(At<int>(w+36)) && At<int>(w+28)!=-1 && (At<unsigned>(w+24)&4))Dispatch(137,index,w,true);
        value=static_cast<float>(At<int>(w+36));
    }
    Threshold(w,static_cast<int>(value));At<float>(w+56)=value;afterCall=markAfterCall;return nativeReturn;
}
char __fastcall Score(uintptr_t object,int value){
    ++calls;lastScore=object;lastInteger=value;SetCounter(object-g_base,value);afterCall=markAfterCall;return nativeReturn;
}
void Setup(){
    ZeroMemory(reinterpret_cast<void*>(g_base),0x2C00000);ZeroMemory(&shared,sizeof(shared));
    fakeNow=100000;shared.hostHeartbeat=fakeNow;g_shared=&shared;g_gameThread=GetCurrentThreadId();g_disabled=0;
    unreadable=unwritable=0;onCodeRead=nullptr;afterCall=false;postCallReads=0;
    calls=events=completedHud=resetHud=sounds=0;lastEvent=lastIndex=lastInteger=-1;lastFloat=0;lastScore=0;
    endMission=changeMaximum=eventSawOld=false;markAfterCall=true;nativeReturn=0;
    mission_event_features::testCounter=Counter;mission_event_features::testGauge=Gauge;mission_event_features::testScore=Score;
    for(const auto& s:mission_event_features::code)memcpy(reinterpret_cast<void*>(g_base+s.rva),s.bytes,s.size);
    At<BYTE>(0x9BA8D0)=1;At<int>(0x716884)=1;
    At<uintptr_t>(0x9BA920)=g_base+0x130000;At<uintptr_t>(0x716868)=g_base+0x131000;At<uintptr_t>(0x9BA888)=g_base+outer;
    At<uintptr_t>(0x130000)=g_base+0x5B2BB0;At<uintptr_t>(0x130000+64)=g_base+0x130080;At<uintptr_t>(0x130000+72)=g_base+0x131000;
    At<uintptr_t>(0x5B2BB8)=g_base+0x19C2B0;At<uintptr_t>(0x5B2BC0)=g_base+0x19C470;At<uintptr_t>(0xAC0FD8)=1;
    At<uint64_t>(0x9A98B0)=0x0000003A4A32484Bull;
    At<uintptr_t>(outer)=g_base+0x5B13E8;At<uintptr_t>(outer+8)=g_base+heap;
    At<uintptr_t>(0x5B13F0)=g_base+0x14F740;At<uintptr_t>(0x5B13F8)=g_base+0x14FC30;
    At<uintptr_t>(heap)=g_base+heapVt;At<uintptr_t>(heapVt+8)=g_base+0x14F740;At<uintptr_t>(heapVt+16)=g_base+0x14FC30;
    At<uintptr_t>(0x2A250A0)=g_base+0x130000;
    At<uintptr_t>(0x2A105D0)=g_base+actor;At<uintptr_t>(actor+1472)=g_base+status;
    At<unsigned>(actor+1736)=0x1000080;At<int>(status)=100;At<int>(status+4)=120;At<int>(status+608)=1;
    At<uint32_t>(status+616)=actor;At<uint32_t>(actor)=0x120000;
    At<uintptr_t>(0x120000)=g_base+0x121000;At<uintptr_t>(0x121000+96)=g_base+0x3B3030;
    At<uintptr_t>(0x2A171C8)=g_base+actor;At<int>(actor+1464)=1;
    At<uintptr_t>(0x2A0FF68)=g_base+storage;At<uintptr_t>(0x2A0FF70)=g_base+descriptor;
    At<unsigned>(storage)=42;At<unsigned>(storage+4)=1;At<int>(storage+1072)=1;
    At<uintptr_t>(storage+8)=g_base+descriptor;At<uintptr_t>(storage+96)=g_base+bar;At<int>(storage+1048)=6;
    for(unsigned i=0;i<3;++i){
        const uintptr_t c=FixtureWidget(230,i),g=FixtureWidget(231,i);
        At<uintptr_t>(storage+976+16*i)=g_base+c;At<uintptr_t>(storage+984+16*i)=g_base+g;
        At<uintptr_t>(c)=g_base+0x5C4248;At<unsigned>(c+24)=5;At<int>(c+28)=i;At<int>(c+36)=100;At<int>(c+56)=10;
        At<uintptr_t>(g)=g_base+0x5C4288;At<unsigned>(g+24)=5;At<int>(g+28)=i;At<int>(g+36)=200;At<float>(g+56)=20.5f;
    }
    At<uintptr_t>(FixtureWidget(232))=g_base+0x5C9E38;At<unsigned>(FixtureWidget(232)+24)=5;At<int>(FixtureWidget(232)+28)=-1;
    At<int>(FixtureWidget(232)+36)=9999;At<int>(FixtureWidget(232)+56)=321;
    for(uintptr_t v:{0x5C4248u,0x5C9E38u}){At<uintptr_t>(v+32)=g_base+0x3FA4C0;At<uintptr_t>(v+40)=g_base+0x3FA1D0;}
    At<uintptr_t>(0x5C4288+32)=g_base+0x3FA510;At<uintptr_t>(0x5C4288+40)=g_base+0x3FA200;
    At<int>(0x74A8E0)=20;for(int i=0;i<20;++i)At<int>(0x74A890+4*i)=i;
    At<uintptr_t>(0x29F33C8)=g_base+cache;At<uint16_t>(cache+2)=1;At<uintptr_t>(cache+88)=g_base+bar;
    for(unsigned i=0;i<16;++i)At<int>(0x2AE6ED0+96*i)=-1;
}
TrainerResult Execute(unsigned slot=230,double value=100,double index=0,const TrainerContext* custom=nullptr){
    double args[8]{};args[0]=slot==232?value:index;if(slot!=232)args[1]=value;
    TrainerResult r{};const auto c=custom?*custom:Context();
    Check(MissionEventHandle(c,slot,args,r),"owned command handled");return r;
}
void Rejected(const char* why,unsigned slot=230,double value=100,double index=0){
    const auto r=Execute(slot,value,index);Check(r.code!=0 && calls==0,why);
}
void MakeHud(unsigned slot){
    const bool gauge=slot==231;const uintptr_t hud=0x170000;
    At<uintptr_t>(FixtureWidget(slot)+64)=g_base+hud;At<uintptr_t>(hud)=g_base+(gauge?0x5B23A0:0x5B2370);
    for(unsigned sprite:{768u,gauge?2784u:1272u}){
        const uintptr_t context=hud+sprite+32;
        At<uintptr_t>(context+224)=g_base+0x180000;At<uintptr_t>(context+216)=g_base+0x190000;
        for(unsigned index:{0u,4u,6u,10u}){At<uint16_t>(0x180000+36*index)=0;At<uint16_t>(0x180000+36*index+2)=1;}
    }
}
void MakeScript(uintptr_t context=0x1A0000){
    At<uintptr_t>(context)=g_base+0x1B0000;At<uintptr_t>(context+88)=g_base+0x1C0000;At<uintptr_t>(context+96)=g_base+actor;
    At<int>(0x1B0000+16)=16;At<int>(0x1B0000+20)=512;At<int>(0x1B0000+24)=512;
    At<int>(0x1B0000+28)=10;At<int>(0x1B0000+32)=16;At<int>(0x1B0000+40)=0;At<int>(0x1C0000)=1;
}
}
int main(){
    using namespace mission_event_features;
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,0x2C00000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!g_base)return 2;
    for(unsigned slot:{230u,231u})for(unsigned index=0;index<3;++index)for(unsigned mode=0;mode<3;++mode){
        Setup();const double value=mode==0?0:mode==1?50:slot==230?100:200;
        const auto r=Execute(slot,value,index);
        Check(r.code==0 && calls==1 && lastIndex==static_cast<int>(index),"native setter called exactly once for all widget/direction/index combinations");
        Check((slot==230?At<int>(FixtureWidget(slot,index)+56):At<float>(FixtureWidget(slot,index)+56))==value,"fake native setter owns final value");
        Check(events==(mode==1?0u:1u),"normal boundary event retained");
        if(mode!=1)Check(lastEvent==(slot==230?(mode==0?14:123):(mode==0?136:137)) && eventSawOld,"event ID and event-before-value-write match native");
        Check(postCallReads==0,"no old or new game pointer read after native call");
    }
    for(int value:{0,1,5000,9999}){Setup();const auto r=Execute(232,value);Check(r.code==0&&calls==1&&events==0&&lastScore==g_base+FixtureWidget(232),"score uses native class setter without event ID");Check(At<int>(FixtureWidget(232)+56)==value,"score set without reward-history edits");}
    Setup();auto r=Execute(231,12.25,2);Check(r.code==0&&calls==1&&lastFloat==12.25f,"gauge float argument preserved");
    Setup();At<int>(FixtureWidget(230)+36)=0;At<int>(FixtureWidget(230)+56)=0;r=Execute(230,0);Check(r.code==0&&calls==1&&events==0,"configured zero-maximum counter follows native no-crossing behavior");
    Setup();At<int>(FixtureWidget(230)+56)=100;r=Execute(230,100);Check(r.code==0&&calls==1&&events==0,"repeating maximum does not invent a second boundary event");
    Setup();At<float>(FixtureWidget(231)+56)=0;r=Execute(231,0);Check(r.code==0&&calls==1&&events==0,"repeating gauge zero does not invent a second boundary event");
    for(unsigned slot:{230u,231u}){Setup();endMission=true;r=Execute(slot,0);Check(r.code==0&&calls==1&&At<uintptr_t>(0x2A0FF68)==0&&postCallReads==0,"mission teardown and room scheduling do not cause stale trainer reads");}
    Setup();changeMaximum=true;r=Execute();Check(r.code==0&&At<int>(FixtureWidget(230)+56)==50,"native event may change maximum before setter finishes");
    for(char value:{char(0),char(1),char(-1)}){Setup();nativeReturn=value;r=Execute();Check(r.code==0&&calls==1,"native AL is not treated as success flag");}
    for(unsigned slot:{230u,231u,232u}){
        Setup();MakeHud(slot);At<int>(FixtureWidget(slot)+40)=50;r=Execute(slot,60);Check(r.code==0&&completedHud==1,"native threshold completion remains enabled");
        Setup();MakeHud(slot);At<int>(FixtureWidget(slot)+40)=50;At<unsigned>(FixtureWidget(slot)+24)|=8;r=Execute(slot,25);Check(r.code==0&&resetHud==1,"native threshold reset remains enabled");
        Setup();MakeHud(slot);At<int>(FixtureWidget(slot)+32)=100;At<int>(FixtureWidget(slot)+40)=50;r=Execute(slot,25);Check(r.code==0&&completedHud==1,"descending threshold keeps native comparison");
    }
    for(double bad:{-1.0,3.0,0.5,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}){Setup();Rejected("invalid widget index",230,10,bad);}
    for(double bad:{-1.0,101.0,0.5,2147483648.0,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}){Setup();Rejected("invalid counter value",230,bad);}
    for(double bad:{-1.0,201.0,2147483648.0,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}){Setup();Rejected("invalid gauge value",231,bad);}
    for(double bad:{-1.0,10000.0,1.5}){Setup();Rejected("invalid score",232,bad);}
    Setup();double args[8]{};args[1]=50;args[7]=std::numeric_limits<double>::infinity();r={};Check(MissionEventHandle(Context(),230,args,r)&&r.code!=0&&calls==0,"all argument slots must be finite");
    Setup();r={};Check(!MissionEventHandle(Context(),229,args,r),"unowned command falls through");
    Setup();g_disabled=1;Rejected("disabled bridge");
    Setup();g_gameThread=0;Rejected("wrong thread");
    Setup();g_shared=nullptr;Rejected("missing host");
    Setup();shared.hostHeartbeat=0;Rejected("zero heartbeat");
    Setup();fakeNow+=5001;Rejected("expired host");
    Setup();auto c=Context();c.sceneReady=false;r=Execute(230,100,0,&c);Check(r.code!=0&&!calls,"unready context");
    Setup();c=Context();c.base=0;r=Execute(230,100,0,&c);Check(r.code!=0&&!calls,"wrong base");
    for(uintptr_t x:{0x9006B0u,0xABAC58u,0xABAC59u,0xABADE0u,0x9BA8D1u}){Setup();At<BYTE>(x)=1;Rejected("menu/event/title/capture/closing blocks mutation");}
    for(uintptr_t x:{0x9BA928u,0xAC0F48u,0x2A11478u,0x2AE8050u,0x2AE9FA8u}){Setup();At<uintptr_t>(x)=1;Rejected("pending lifecycle blocks mutation");}
    Setup();At<unsigned>(0x2A10504)=2;Rejected("Drive lock");
    Setup();At<unsigned>(0x2A11400)=0x20;Rejected("actor freeze");
    Setup();At<int>(0x716884)=2;Rejected("field pause");
    Setup();At<int>(status)=0;Rejected("dead player");
    Setup();At<uintptr_t>(actor+1472)=0;Rejected("status backlink");
    for(int phase:{0,2,3,4}){Setup();At<int>(storage+1072)=phase;Rejected("nonactive mission phase");}
    for(unsigned flag:{0u,5u,17u}){Setup();At<unsigned>(storage+4)=flag;Rejected("mission inactive or finishing");}
    Setup();At<uintptr_t>(0x2A0FF68)+=16;Rejected("wrong static mission storage");
    Setup();At<uintptr_t>(storage+8)+=16;Rejected("descriptor mirror mismatch");
    Setup();At<int>(storage+1048)=10;Rejected("registry overflow");
    Setup();At<uintptr_t>(storage+984)=At<uintptr_t>(storage+976);Rejected("duplicate registry entry");
    Setup();At<uintptr_t>(storage+976)=g_base+storage+808;Rejected("counter absent from registry");
    for(unsigned slot:{230u,231u,232u}){
        Setup();At<uintptr_t>(FixtureWidget(slot))=0;Rejected("wrong widget class",slot,0);
        Setup();At<unsigned>(FixtureWidget(slot)+24)=0;Rejected("uninitialized widget",slot,0);
        Setup();At<unsigned>(FixtureWidget(slot)+24)=1;At<uintptr_t>(0x2A250A0)=0;r=Execute(slot,0);Check(r.code==0&&calls==1&&events==0,"configured inactive widget follows native setter without boundary dispatch");
        Setup();At<unsigned>(FixtureWidget(slot)+24)=21;r=Execute(slot,0);Check(r.code==0&&calls==1&&events==(slot==232?0u:1u),"suppressed auto-HUD flag does not suppress native setter or enabled events");
        Setup();MakeHud(slot);At<unsigned>(FixtureWidget(slot)+24)=1;At<int>(FixtureWidget(slot)+40)=50;At<int>(FixtureWidget(slot)+52)=123;At<uintptr_t>(0x2A250A0)=0;r=Execute(slot,60);Check(r.code==0&&completedHud==1&&events==0&&sounds==0,"inactive widget keeps HUD threshold change without events or completion sound");
        Setup();MakeHud(slot);At<int>(FixtureWidget(slot)+40)=50;At<int>(FixtureWidget(slot)+52)=123;r=Execute(slot,60);Check(r.code==0&&completedHud==1&&sounds==1,"enabled threshold retains native completion sound");
        Setup();At<int>(FixtureWidget(slot)+36)=-1;Rejected("negative max",slot,0);
        Setup();At<int>(FixtureWidget(slot)+32)=-1;Rejected("negative initial",slot,0);
        Setup();unwritable=g_base+FixtureWidget(slot)+56;Rejected("value not writable",slot,0);
        Setup();MakeHud(slot);At<uintptr_t>(0x170000)=0;Rejected("wrong HUD class",slot,0);
        Setup();MakeHud(slot);unreadable=g_base+0x190000;Rejected("unreadable frame rows",slot,0);
        Setup();MakeHud(slot);At<uintptr_t>(0x170000+768+32+224)=0;At<int>(0x170000+768+32+316)=1;Rejected("enabled animation with null rows",slot,0);
        Setup();MakeHud(slot);At<uintptr_t>(0x170000+768+32+224)=0;r=Execute(slot,0);Check(r.code==0&&calls==1,"native absent disabled animation resource permitted");
    }
    Setup();At<int>(FixtureWidget(230)+28)=1;Rejected("wrong counter ID");
    Setup();At<int>(FixtureWidget(232)+28)=0;Rejected("score event ID must remain -1",232,100);
    Setup();At<int>(FixtureWidget(232)+36)=100;Rejected("score maximum must remain9999",232,10);
    Setup();At<unsigned>(storage+1696)=1;Rejected("native gauge owner preserved",231,10);
    Setup();At<float>(FixtureWidget(231)+56)=std::numeric_limits<float>::quiet_NaN();Rejected("nonfinite old gauge",231,10);
    Setup();At<int>(FixtureWidget(231)+36)=2147483647;Rejected("unsafe float-to-int max",231,10);
    Setup();At<int>(FixtureWidget(231)+36)=16777217;r=Execute(231,16777217);Check(r.code==0&&lastFloat==16777216.0f&&events==1,"gauge uses native float precision and float-converted maximum");
    Setup();DWORD pageOld=0,pageUnused=0;const auto page=reinterpret_cast<void*>((g_base+FixtureWidget(230))&~uintptr_t(4095));
    Check(VirtualProtect(page,4096,PAGE_READONLY,&pageOld)!=FALSE,"real fixture protection changed");
    Rejected("real read-only native widget is rejected");
    Check(VirtualProtect(page,4096,pageOld,&pageUnused)!=FALSE,"real fixture protection restored");
    for(const auto& signature:code){Setup();At<BYTE>(signature.rva)^=1;Rejected("changed native code");}
    for(uintptr_t x:{0x2A250B0u,0x2A25048u}){Setup();At<uintptr_t>(x)=1;Rejected("nested VM execution rejected at boundary");}
    Setup();At<uintptr_t>(0x2A250A0)=0;Rejected("VM allocator not bound");
    Setup();At<uintptr_t>(0x130000)=0;Rejected("changed allocator vtable");
    Setup();At<uintptr_t>(0x2A250A0)=g_base+outer;Rejected("common-script allocator is not current field allocator");
    Setup();At<uintptr_t>(0x130000+72)=At<uintptr_t>(0x130000+64);Rejected("invalid allocator range");
    Setup();At<uintptr_t>(0xAC0FD8)=0;Rejected("allocator mutex absent");
    Setup();At<uint64_t>(0x9A98B0)=0;Rejected("invalid live save header");
    Setup();unwritable=g_base+0x9A98B0;Rejected("native progression save not writable");
    for(int count:{-1,21}){Setup();At<int>(0x74A8E0)=count;Rejected("event pool free count bounded");}
    Setup();At<int>(0x74A890)=20;Rejected("free event index bounded");
    Setup();At<int>(0x74A894)=0;Rejected("duplicate free event index");
    Setup();At<uintptr_t>(0x2A112B8)=g_base+0x74A611;Rejected("unaligned event node");
    Setup();At<int>(0x74A8E0)=19;At<uintptr_t>(0x2A112B8)=At<uintptr_t>(0x2A112C0)=g_base+0x74A610+19*32;r=Execute();Check(r.code==0&&calls==1,"valid queued event list accepted");
    Setup();At<int>(0x74A8E0)=19;At<uintptr_t>(0x2A112B8)=At<uintptr_t>(0x2A112C0)=g_base+0x74A610+19*32;At<uint32_t>(0x74A610+19*32+28)=0x74A610+19*32;Rejected("event cycle rejected");
    Setup();At<uintptr_t>(0x2A112C0)=1;Rejected("event tail consistency");
    Setup();At<uint32_t>(actor+2704)=actor;Rejected("actor cycle rejected");
    Setup();At<uintptr_t>(0x2A171C8)=0;Rejected("player absent from Actor list");
    Setup();At<uintptr_t>(0x121000+96)=0;Rejected("unrecognized Actor event callback");
    Setup();const BYTE thunk[]={0x41,0x8b,0xc0,0x48,0x8b,0xca,0x8b,0xd0,0x45,0x8b,0xc1,0xe9};
    memcpy(reinterpret_cast<void*>(g_base+0x123000),thunk,sizeof(thunk));At<int>(0x12300C)=static_cast<int>(0x3B4C90-0x123010);At<uintptr_t>(0x121000+96)=g_base+0x123000;r=Execute();Check(r.code==0&&calls==1,"exact derived event thunk accepted");
    Setup();At<uintptr_t>(0x29F33C8)=0;Rejected("mission BAR absent from native cache");
    Setup();At<uint16_t>(cache+2)=0;Rejected("BAR cache reference underflow");
    Setup();At<uint32_t>(cache+112)=cache;Rejected("resource cache cycle");
    Setup();At<int>(0x2AE6ED0)=123;At<int>(0x2AE6ED0+24)=4097;Rejected("handler item list count bounded");
    Setup();At<int>(0x2AE6ED0)=123;At<int16_t>(0x2AE6ED0+54)=8;Rejected("handler inline flag list bounded");
    Setup();At<int>(0x2AE6ED0)=123;At<int>(0x2AE6ED0+24)=1;Rejected("missing handler item array");
    Setup();MakeScript();At<uintptr_t>(0x2AE5D88)=g_base+0x1A0000;r=Execute();Check(r.code==0&&calls==1,"loaded global event script preflight accepted");
    Setup();MakeScript();At<uintptr_t>(actor+1456)=g_base+0x1A0000;r=Execute();Check(r.code==0&&calls==1,"loaded Actor event script preflight accepted");
    for(unsigned off:{16u,20u,24u}){Setup();MakeScript();At<uintptr_t>(0x2AE5D88)=g_base+0x1A0000;At<int>(0x1B0000+off)=-1;Rejected("invalid BDX allocation size");}
    Setup();MakeScript();At<uintptr_t>(0x2AE5D88)=g_base+0x1A0000;At<int>(0x1B0000+32)=-1;Rejected("negative BDX PC");
    Setup();MakeScript();At<uintptr_t>(0x2AE5D88)=g_base+0x1A0000;At<int>(0x1C0000)=0;Rejected("invalid work refcount");
    Setup();MakeScript();At<uintptr_t>(0x2AE5D88)=g_base+0x1A0000;At<int>(actor+1464)=INT_MAX;Rejected("Actor script refcount overflow");
    Setup();MakeScript();At<uintptr_t>(0x2AE5D88)=g_base+0x1A0000;At<int>(0x1C0000)=INT_MAX;Rejected("shared BDX work refcount overflow");
    Setup();MakeScript();At<uintptr_t>(0x2AE5D88)=g_base+0x1A0000;memcpy(reinterpret_cast<void*>(g_base+0x1B0000),"B_EX370",8);unwritable=g_base+0x1B0000+20;Rejected("native stack-size adjustment requires writable script header");
    Setup();MakeScript();At<uintptr_t>(0x2A25090)=At<uintptr_t>(0x2A25098)=g_base+0x1A0000;r=Execute();Check(r.code==0&&calls==1,"valid deferred script cleanup list accepted");
    Setup();MakeScript();At<uintptr_t>(0x2A25090)=At<uintptr_t>(0x2A25098)=g_base+0x1A0000;At<uint32_t>(0x1A0000+68)=0x1A0000;Rejected("deferred script cycle rejected");
    Setup();At<uintptr_t>(0x2A25098)=1;Rejected("deferred script tail mismatch");
    Setup();fakeNow=0x20;shared.hostHeartbeat=0xfffffff0;r=Execute();Check(r.code==0&&calls==1,"fresh host interval survives tick wrap");
    for(unsigned mode=0;mode<4;++mode){
        Setup();
        if(mode==0)onCodeRead=[](){++At<unsigned>(storage);};
        if(mode==1)onCodeRead=[](){At<int>(FixtureWidget(230)+36)=101;};
        if(mode==2)onCodeRead=[](){At<int>(FixtureWidget(230)+56)=11;};
        if(mode==3)onCodeRead=[](){shared.hostHeartbeat=0;};
        Rejected("fresh mission/widget/host confirmation rejects drift");
    }
    Setup();MissionEventCapabilities();for(unsigned s=230;s<=232;++s)Check((shared.supported[s/64]&(uint64_t(1)<<(s%64)))!=0,"capabilities published");
    Check(!(shared.supported[229/64]&(uint64_t(1)<<(229%64)))&&!(shared.supported[233/64]&(uint64_t(1)<<(233%64))),"capabilities do not consume adjacent slots");
    printf("MissionEventGuardTests: %u checks, %u failures\n",checks,failures);
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
