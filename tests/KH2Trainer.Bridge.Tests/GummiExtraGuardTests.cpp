#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define KH2_GUMMI_TESTS
#define KH2_GUMMI_EXTRA_TESTS
#include <windows.h>
#include <stdint.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits>
#include <initializer_list>
#include <utility>
#include <wchar.h>
namespace {
uintptr_t g_base=0; DWORD g_gameThread=0; volatile LONG g_disabled=0;
struct TrainerContext { uintptr_t base,player,status; bool sceneReady; };
struct TrainerResult { LONG code; const wchar_t* text; };
struct Shared { DWORD hostHeartbeat; double values[512]; uint64_t valid[8],supported[8]; } shared{};
Shared* g_shared=&shared;
void(*onCodeRead)()=nullptr;
void(*onRequestCodeRead)()=nullptr;
unsigned requestCodeReads=0,mutateOnRequestCodeRead=1;
uintptr_t deniedRead=0,deniedWrite=0;size_t deniedReadSize=0;
BYTE requestMutationExpected[0x1410]{};bool capturedRequestMutation=false;
bool afterCall=false;unsigned postCallReads=0;
bool switchPlayerOnSecondRead=false; unsigned playerReads=0;
template<class T>T& At(uintptr_t rva){return *reinterpret_cast<T*>(g_base+rva);}
bool Readable(const void* p,size_t count) {
    if(afterCall)++postCallReads;
    const uintptr_t start=reinterpret_cast<uintptr_t>(p);
    if(start==g_base+0x2312B0 && ++requestCodeReads==mutateOnRequestCodeRead && onRequestCodeRead){
        auto f=onRequestCodeRead;onRequestCodeRead=nullptr;f();
        memcpy(requestMutationExpected,reinterpret_cast<void*>(g_base+0x50000),sizeof(requestMutationExpected));capturedRequestMutation=true;
    }
    if(deniedRead && start==deniedRead && count==deniedReadSize)return false;
    if(onCodeRead && start==g_base+0x225CD0){auto f=onCodeRead;onCodeRead=nullptr;f();}
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
    if(deniedWrite && reinterpret_cast<uintptr_t>(p)==deniedWrite)return false;
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
#include "../../src/KH2Trainer.Bridge/GummiExtraFeatures.inl"
unsigned checks=0,failures=0,calls=0,lastKind=0;uintptr_t lastObject=0;int lastArg=0;
TrainerContext host{};
void Check(bool ok,const char* name){++checks;if(!ok){++failures;printf("FAIL %s\n",name);}}
void NativeStat(uintptr_t state,int delta,unsigned off,unsigned kind){++calls;lastKind=kind;lastObject=state;lastArg=delta;gummi_extra::Field<int>(state,off)+=delta;afterCall=true;}
void __fastcall Mobility(uintptr_t s,int n){NativeStat(s,n,36,320);}
void __fastcall Roll(uintptr_t s,int n){NativeStat(s,n,40,321);}
void __fastcall Lockon(uintptr_t s,int n){NativeStat(s,n,44,322);}
void __fastcall Charge(uintptr_t q,int n){
    ++calls;lastKind=323;lastObject=q;lastArg=n;
    const auto ship=gummi_extra::Field<uintptr_t>(q,8),state=gummi_extra::Field<uintptr_t>(ship,200);
    const float multiplier=float(gummi_extra::Field<int>(state,52))/100.0f+1.0f;
    auto& progress=gummi_extra::Field<int>(q,56);auto& stock=gummi_extra::Field<int>(q,60);
    progress+=int(multiplier*float(n));
    if(progress>=100){while(stock<9){progress-=100;++stock;if(stock>=9)break;if(progress<100){afterCall=true;return;}}progress=100;gummi_extra::Field<unsigned>(q,68)|=4;}
    afterCall=true;
}
void __fastcall Request(uintptr_t q){
    ++calls;lastKind=485;lastObject=q;lastArg=0;
    gummi_extra::Field<unsigned>(q,68)|=2;afterCall=true;
}
TrainerResult Command(unsigned slot,double value=0){double args[8]={value};TrainerResult r{};Check(GummiExtraHandle(host,slot,args,r),"command handled");return r;}
void ClearSnapshot(){memset(shared.valid,0,sizeof(shared.valid));memset(shared.values,0,sizeof(shared.values));}
bool Valid(unsigned s){return(shared.valid[s/64]&(uint64_t(1)<<(s%64)))!=0;}
void Player(uintptr_t rva){
    At<uint32_t>(rva)=DWORD(gummi::DescriptorRva);
    At<uintptr_t>(rva+0x550)=g_base+rva+0x570;
    At<uintptr_t>(rva+0x570)=g_base+gummi::StateVtableRva;
    At<float>(rva+0x578)=42.25f;At<int>(rva+0x57C)=120;
    At<int>(rva+0x5D8)=2;At<uint32_t>(rva+0x140C)=0;
}
void Ready(){
    g_shared=&shared;g_disabled=0;g_gameThread=GetCurrentThreadId();shared.hostHeartbeat=GetTickCount();
    host={g_base,0,0,false};afterCall=false;postCallReads=0;onCodeRead=nullptr;calls=0;switchPlayerOnSecondRead=false;playerReads=0;
    onRequestCodeRead=nullptr;requestCodeReads=0;mutateOnRequestCodeRead=1;deniedRead=deniedWrite=0;deniedReadSize=0;
    capturedRequestMutation=false;
    At<uintptr_t>(gummi::ModuleRva)=g_base+gummi::ModuleVtableRva;
    At<uintptr_t>(gummi::ModuleRva+8)=g_base+0x90000;
    At<int>(gummi::ModuleRva+36)=1;At<uint32_t>(gummi::ModuleRva+20)=0;
    At<uintptr_t>(gummi::ModeListRva)=g_base+gummi::ModuleRva;
    At<uintptr_t>(gummi::HeapRva)=g_base+0xA0000;At<uintptr_t>(gummi::ModuleHeapRva)=g_base+0xA0000;
    At<uintptr_t>(gummi::SchedulerRva)=g_base+0x90000;
    At<int>(gummi::MissionPhaseRva)=8;At<uintptr_t>(gummi::PlayerRva)=g_base+0x50000;
    At<uintptr_t>(gummi::DescriptorRva)=g_base+gummi::DescriptorVtableRva;Player(0x50000);Player(0x52000);
    At<uintptr_t>(0x50560)=g_base+0xC1008;
    At<uintptr_t>(0xAEF508)=g_base+0xC1000;At<int>(0xC1004)=1;At<int>(0xC1008)=0;
    for(unsigned o:{4u,8u,12u,16u,20u,24u,64u,68u,72u})At<float>(0xC1008+o)=1.0f;
    At<uintptr_t>(0xAF0780)=g_base+0xC2000;At<int>(0xC2004)=1;At<int>(0xC2008)=0;At<float>(0xC2018)=0.5f;
    At<int>(0x50570+36)=25;At<int>(0x50570+40)=50;At<int>(0x50570+44)=10;At<int>(0x50570+52)=0;
    At<uintptr_t>(0x50000+2960)=g_base+0x5B5320;
    At<uintptr_t>(0xAEF408)=g_base+0xC3000;At<int>(0xC3004)=4;
    for(unsigned i=0;i<4;++i){
        At<int>(0x5B51B8+4*i)=100+int(i);At<int>(0xC3008+128*i)=100+int(i);
        At<uintptr_t>(0x50000+2960+1848+16*i)=g_base+0xC3008+128*i;
        At<float>(0xC3008+128*i+4)=30;At<float>(0xC3008+128*i+8)=20;
        At<float>(0xC3008+128*i+12)=0.1f;At<float>(0xC3008+128*i+16)=2;
    }
    At<uintptr_t>(0x50000+1160)=g_base+0x5B5238;
    At<int>(0x50000+4872)=0;At<uintptr_t>(0x50000+4872+8)=g_base+0x50000+1160;
    At<uintptr_t>(0x50000+4872+16)=At<uintptr_t>(0x50000+4872+24)=0;
    for(unsigned i=0;i<5;++i)At<int>(0x50000+4872+32+4*i)=i?0:1;
    At<int>(0x50000+4872+52)=0;At<int>(0x50000+4872+56)=40;
    At<int>(0x50000+4872+60)=2;At<float>(0x50000+4872+64)=0;At<unsigned>(0x50000+4872+68)=1;
    At<float>(0x50000+1512)=12.5f;
    for(const auto& sig:gummi_extra::code)memcpy(reinterpret_cast<void*>(g_base+sig.rva),sig.data,sig.size);
    for(const auto& sig:gummi_extra::requestCode)memcpy(reinterpret_cast<void*>(g_base+sig.rva),sig.data,sig.size);
    At<float>(gummi_extra::RequestStepRva)=1.0f;
    At<uint32_t>(0x9A8788)=3;At<uint32_t>(0x716C04)=2;
    At<uint32_t>(gummi::ScoreRva)=1209;At<BYTE>(gummi::ScoreLockRva)=0;
    At<int>(0x72B2C4)=12;At<int>(0x72B2C0)=7;At<int>(0x72B2C8)=15;
    At<uintptr_t>(0xAF4258)=g_base+0xB0000;At<BYTE>(0xB0000)=3;At<BYTE>(0xB0001)=2;
    At<int>(0xAF4204)=4;At<int>(0xAF4260)=1;
    memcpy(reinterpret_cast<void*>(g_base+gummi::HealRva),gummi::HealCode,sizeof(gummi::HealCode));
    memcpy(reinterpret_cast<void*>(g_base+gummi::AddScoreRva),gummi::ScoreCode,sizeof(gummi::ScoreCode));
}
void Rejected(unsigned slot,const char* why,double value=100){const unsigned oldCalls=calls;const auto r=Command(slot,value);Check(r.code!=0&&calls==oldCalls,why);}
constexpr uintptr_t RequestCombo=0x50000+4872;
void RequestReady(){Ready();At<unsigned>(RequestCombo+68)=9;}
void Continuation(float time=20){RequestReady();At<int>(RequestCombo)=3;At<int>(RequestCombo+52)=2;At<int>(RequestCombo+32+8)=1;At<int>(RequestCombo+60)=0;At<float>(RequestCombo+64)=time;}
void RequestRejected(const char* why) {
    BYTE before[0x1410];memcpy(before,reinterpret_cast<void*>(g_base+0x50000),sizeof(before));
    const unsigned oldCalls=calls;auto r=Command(485);
    Check(r.code!=0&&calls==oldCalls,why);
    Check(memcmp(before,reinterpret_cast<void*>(g_base+0x50000),sizeof(before))==0,"request refusal writes no player bytes");
}
void RequestAccepted(const char* why) {
    BYTE before[0x1410];memcpy(before,reinterpret_cast<void*>(g_base+0x50000),sizeof(before));
    *reinterpret_cast<unsigned*>(before+4872+68)|=2;
    auto r=Command(485);
    Check(r.code==0&&calls==1&&lastKind==485&&lastObject==g_base+RequestCombo,why);
    Check(memcmp(before,reinterpret_cast<void*>(g_base+0x50000),sizeof(before))==0,"request mutates only flag mask2, all other ship bytes unchanged");
    Check(postCallReads==0,"request discards pointers after dispatch");
    Check(wcsstr(r.text,L"request queued once")!=nullptr,"request acknowledgement makes no attack guarantee");
}
void RequestTests() {
    for(int stock:{1,9}){RequestReady();At<int>(RequestCombo+60)=stock;RequestAccepted("start stock boundary accepted once");}
    RequestReady();At<unsigned>(RequestCombo+68)=13;At<int>(RequestCombo+60)=9;At<int>(RequestCombo+56)=100;RequestAccepted("full-latched start leaves stock/progress/latch for native update");
    for(int first=0;first<5;++first){RequestReady();for(int i=0;i<5;++i)At<int>(RequestCombo+32+4*i)=i==first?1:0;At<int>(RequestCombo+52)=first;RequestAccepted("each native first stage accepted");}
    for(unsigned companions=1;companions<=3;++companions){
        RequestReady();for(int i=0;i<5;++i)At<int>(RequestCombo+32+4*i)=0;
        At<unsigned>(RequestCombo+68)=1;At<int>(RequestCombo+52)=5;
        // Deliberately unreadable pointers: this is a scalar request, not graph validation.
        At<uintptr_t>(RequestCombo+16)=(companions&1)?1:0;At<uintptr_t>(RequestCombo+24)=(companions&2)?2:0;
        RequestAccepted("companion-only input request does not dereference deferred objects");
    }
    for(float time:{10.0f,20.0f,50.0f}){Continuation(time);RequestAccepted("inclusive continuation window with zero stock accepted");}
    for(int stage=1;stage<5;++stage){Continuation();At<int>(RequestCombo+52)=stage;At<int>(RequestCombo+32+4*stage)=1;RequestAccepted("each continuation stage accepted");}
    RequestReady();At<float>(gummi_extra::RequestStepRva)=0;RequestAccepted("zero native step is finite and allowed");
    for(int phase:{1,2,4,5,-1,6}){RequestReady();At<int>(RequestCombo)=phase;RequestRejected("non-admissible phase rejected");}
    RequestReady();At<int>(RequestCombo+60)=0;RequestRejected("empty stock cannot start");
    for(float time:{nextafterf(10.0f,0.0f),nextafterf(50.0f,100.0f)}){Continuation(time);RequestRejected("adjacent float outside continuation window rejected");}
    for(unsigned flag:{0u,8u,11u,0x19u,0xffffffffu}){RequestReady();At<unsigned>(RequestCombo+68)=flag;RequestRejected("absent installed, pending and unknown flags rejected");}
    RequestReady();At<unsigned>(RequestCombo+68)=1;RequestRejected("main-count flag missing");
    RequestReady();for(int i=0;i<5;++i)At<int>(RequestCombo+32+4*i)=0;At<int>(RequestCombo+52)=5;RequestRejected("main flag without any main count");
    RequestReady();for(int i=0;i<5;++i)At<int>(RequestCombo+32+4*i)=0;At<unsigned>(RequestCombo+68)=1;At<int>(RequestCombo+52)=5;RequestRejected("no main count or companion cannot represent installation");
    RequestReady();At<unsigned>(RequestCombo+68)=13;RequestRejected("saturated start requires full stock and progress");
    RequestReady();At<unsigned>(RequestCombo+68)=13;At<int>(RequestCombo+60)=9;RequestRejected("saturated start requires progress100");
    for(int index:{-1,1,5,6}){RequestReady();At<int>(RequestCombo+52)=index;RequestRejected("start requires first positive count index");}
    for(int index:{-1,0,5,6}){Continuation();At<int>(RequestCombo+52)=index;RequestRejected("continuation index must be1..4");}
    Continuation();At<int>(RequestCombo+40)=0;RequestRejected("continuation count must be positive");
    for(int stock:{-1,10}){RequestReady();At<int>(RequestCombo+60)=stock;RequestRejected("stock range");}
    for(int progress:{-1,101}){RequestReady();At<int>(RequestCombo+56)=progress;RequestRejected("progress range");}
    for(unsigned i=0;i<5;++i)for(int count:{-1,1001}){RequestReady();At<int>(RequestCombo+32+4*i)=count;RequestRejected("every stage count range");}
    for(float value:{-1.0f,std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN()}){
        RequestReady();At<float>(RequestCombo+64)=value;RequestRejected("invalid elapsed time");
        RequestReady();At<float>(gummi_extra::RequestStepRva)=value;RequestRejected("invalid native step");
    }
    RequestReady();At<float>(RequestCombo+64)=std::numeric_limits<float>::max();At<float>(gummi_extra::RequestStepRva)=std::numeric_limits<float>::max();RequestRejected("native time addition overflow rejected");
    RequestReady();At<uintptr_t>(RequestCombo+8)=0;RequestRejected("main owner missing");
    RequestReady();At<uintptr_t>(0x50000+1160)=0;RequestRejected("main vtable mismatch");
    RequestReady();At<uintptr_t>(0x50000+1160+200)=0;RequestRejected("main state backlink mismatch");
    RequestReady();deniedWrite=g_base+RequestCombo+68;RequestRejected("flag DWORD not writable");
    for(auto span:{std::pair<unsigned,size_t>{0,4},{8,8},{16,8},{24,8},{32,4},{36,4},{40,4},{44,4},{48,4},{52,4},{56,4},{60,4},{64,4},{68,4}}){
        RequestReady();deniedRead=g_base+RequestCombo+span.first;deniedReadSize=span.second;RequestRejected("each individual request span read checked");
    }
    for(auto span:{std::pair<uintptr_t,size_t>{0x50000+1160,8},{0x50000+1160+200,8},{gummi_extra::RequestStepRva,4}}){
        RequestReady();deniedRead=g_base+span.first;deniedReadSize=span.second;RequestRejected("main identity and global step reads checked");
    }
    for(const auto& sig:gummi_extra::requestCode){
        RequestReady();At<BYTE>(sig.rva+sig.size-1)^=1;RequestRejected("each complete request code/constant signature checked");
        RequestReady();deniedRead=g_base+sig.rva;deniedReadSize=sig.size;RequestRejected("each signature span checked readable");
    }
    for(unsigned i=0;i<8;++i)for(double value:{1.,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}){
        RequestReady();double args[8]{};args[i]=value;TrainerResult r{};Check(GummiExtraHandle(host,485,args,r)&&r.code!=0&&calls==0,"all eight unused arguments must be finite zero");
    }
    RequestReady();TrainerResult result{};Check(GummiExtraHandle(host,485,nullptr,result)&&result.code!=0&&calls==0,"request null args rejected");
    // Shared host/module/player gates apply to this action independently of charge tests.
    void(*gates[])()={
        [](){host.base=0;},[](){g_disabled=1;},[](){g_shared=nullptr;},[](){g_gameThread=0;},[](){g_gameThread++;},
        [](){shared.hostHeartbeat=0;},[](){shared.hostHeartbeat=GetTickCount()-5001;},[](){shared.hostHeartbeat=GetTickCount()+1000;},
        [](){At<uintptr_t>(gummi::ModuleRva)=0;},[](){At<int>(gummi::ModuleRva+36)=2;},[](){At<uintptr_t>(gummi::ModeListRva)=0;},
        [](){At<uint32_t>(gummi::ModuleRva+20)=DWORD(gummi::ModuleRva);},[](){At<uintptr_t>(gummi::HeapRva)=0;},
        [](){At<uintptr_t>(gummi::ModuleHeapRva)=0;},[](){At<uintptr_t>(gummi::SchedulerRva)=0;},[](){At<uintptr_t>(gummi::ModuleRva+8)=1;},
        [](){At<int>(gummi::MissionPhaseRva)=7;},[](){At<uintptr_t>(gummi::PlayerRva)=0;},[](){At<uint32_t>(0x50000)=0;},
        [](){At<uintptr_t>(gummi::DescriptorRva)=0;},[](){At<uintptr_t>(0x50570)=0;},[](){At<uintptr_t>(0x50550)=0;},
        [](){At<int>(0x505D8)=3;},[](){At<float>(0x50578)=0;},[](){At<float>(0x50578)=std::numeric_limits<float>::quiet_NaN();},
        [](){At<int>(0x5057C)=0;},[](){At<unsigned>(0x5140C)=0x10;},[](){At<unsigned>(0x5140C)=0x40000;}
    };
    for(auto gate:gates){RequestReady();gate();RequestRejected("independent request context gate");}
    // Every second-sample mismatch is rejected; the fixture's deliberate writes
    // are not attributed to the command. Counter snapshots start after mutation.
    void(*changes[])()={
        [](){At<int>(RequestCombo+56)++;},[](){At<int>(RequestCombo+60)++;},[](){At<float>(RequestCombo+64)=1;},
        [](){At<float>(gummi_extra::RequestStepRva)=.5f;},[](){At<int>(RequestCombo+32)++;},
        [](){At<int>(RequestCombo+36)++;},[](){At<int>(RequestCombo+40)++;},[](){At<int>(RequestCombo+44)++;},[](){At<int>(RequestCombo+48)++;},
        [](){At<uintptr_t>(RequestCombo+16)=1;},[](){At<uintptr_t>(RequestCombo+24)=2;},[](){At<unsigned>(RequestCombo+68)|=2;},
        [](){At<int>(RequestCombo)=2;},[](){At<int>(RequestCombo+52)=1;},[](){At<uintptr_t>(gummi::PlayerRva)=g_base+0x52000;},
        [](){At<uint32_t>(0x9A8788)++;},[](){At<uint32_t>(0x716C04)++;},[](){At<uintptr_t>(gummi::HeapRva)=g_base+0xA1000;At<uintptr_t>(gummi::ModuleHeapRva)=g_base+0xA1000;}
    };
    for(auto change:changes){
        RequestReady();onRequestCodeRead=change;const auto r=Command(485);Check(r.code!=0&&calls==0,"every captured scalar/lifetime revalidated after first sample");
        Check(capturedRequestMutation&&!memcmp(requestMutationExpected,reinterpret_cast<void*>(g_base+0x50000),sizeof(requestMutationExpected)),"changed sample rejection adds no player writes");
    }
    for(auto change:{+[](){host.base=0;},+[](){shared.hostHeartbeat=0;},+[](){g_gameThread=0;},+[](){g_disabled=1;},+[](){g_shared=nullptr;}}){
        RequestReady();onRequestCodeRead=change;mutateOnRequestCodeRead=2;const auto r=Command(485);Check(r.code!=0&&calls==0,"host/base/thread/disable rechecked after second sample");
        Check(capturedRequestMutation&&!memcmp(requestMutationExpected,reinterpret_cast<void*>(g_base+0x50000),sizeof(requestMutationExpected)),"final host rejection adds no player writes");
    }
    RequestReady();onRequestCodeRead=[](){deniedWrite=g_base+RequestCombo+68;};auto r=Command(485);Check(r.code!=0&&calls==0,"flag writeability freshly rechecked");
    RequestReady();onRequestCodeRead=[](){At<BYTE>(gummi_extra::RequestSetterRva+4)^=1;};r=Command(485);Check(r.code!=0&&calls==0,"setter mutation before first signature completion rejected");
    RequestReady();onRequestCodeRead=[](){At<BYTE>(gummi_extra::RequestSetterRva+4)^=1;};mutateOnRequestCodeRead=2;r=Command(485);Check(r.code!=0&&calls==0,"setter signature rechecked after second sample");
    RequestReady();RequestAccepted("first explicit request");afterCall=false;calls=0;RequestRejected("pending request cannot replay before native consumer clears it");
    RequestReady();GummiExtraCapabilities();Check((shared.supported[485/64]&(uint64_t(1)<<(485%64)))!=0,"request capability485 exposed");
    double args[8]{};Check(!GummiExtraHandle(host,484,args,result)&&!GummiExtraHandle(host,486,args,result),"adjacent485 commands remain outside handler");
}
}
int main(){
    constexpr size_t allocation=0xC00000;
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,allocation,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!g_base)return 2;
    gummi_extra::testMobility=Mobility;gummi_extra::testRoll=Roll;gummi_extra::testLockon=Lockon;gummi_extra::testCharge=Charge;gummi_extra::testRequest=Request;
    for(unsigned slot=320;slot<=322;++slot)for(int value:{-100,0,50,200,1000}){
        if((slot==322&&value<0)||(slot<322&&value>200))continue;
        Ready();const unsigned off=36+4*(slot-320);const int old=At<int>(0x50570+off);
        BYTE before[0x1410];memcpy(before,reinterpret_cast<void*>(g_base+0x50000),sizeof(before));
        auto r=Command(slot,value);
        Check(r.code==0&&calls==1&&lastKind==slot&&lastObject==g_base+0x50570&&lastArg==value-old,"native stat delta ABI and exactly one call");
        *reinterpret_cast<int*>(before+0x570+off)=value;
        Check(memcmp(before,reinterpret_cast<void*>(g_base+0x50000),sizeof(before))==0,"only the intended runtime stat changes");
        Check(postCallReads==0,"accepted stat call discards old pointers");
    }
    for(unsigned slot=320;slot<=323;++slot){
        for(double n:{-101.0,1001.0,1.5,std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()}){Ready();Rejected(slot,"invalid input causes zero native calls",n);}
        Ready();shared.hostHeartbeat=0;Rejected(slot,"missing host");
        Ready();shared.hostHeartbeat=GetTickCount()-5001;Rejected(slot,"expired host");
        Ready();shared.hostHeartbeat=GetTickCount()+1000;Rejected(slot,"future heartbeat");
        Ready();g_gameThread++;Rejected(slot,"wrong engine thread");
        Ready();g_disabled=1;Rejected(slot,"disabled bridge");
        Ready();host.base=0;Rejected(slot,"wrong build context");
        Ready();g_shared=nullptr;Rejected(slot,"missing IPC");
        Ready();At<int>(gummi::ModuleRva+36)=2;Rejected(slot,"paused Gummi module");
        Ready();At<int>(gummi::MissionPhaseRva)=14;Rejected(slot,"goal/results phase");
        Ready();At<int>(0x505D8)=5;Rejected(slot,"rebirth player phase");
        Ready();At<float>(0x50578)=0;Rejected(slot,"dead ship");
        Ready();At<unsigned>(0x5140C)=0x40000;Rejected(slot,"pending rebirth flag");
        Ready();At<uintptr_t>(gummi::PlayerRva)=0;Rejected(slot,"missing player");
        Ready();At<uintptr_t>(gummi::HeapRva)=0;Rejected(slot,"module heap released");
        Ready();At<uintptr_t>(gummi::ModuleRva+8)=1;Rejected(slot,"foreign scheduler");
        Ready();At<uint32_t>(gummi::ModuleRva+20)=static_cast<uint32_t>(gummi::ModuleRva);Rejected(slot,"cyclic module list");
        Ready();switchPlayerOnSecondRead=true;Rejected(slot,"ship replaced before dispatch");
        Ready();DWORD old=0,tmp=0;Check(VirtualProtect(reinterpret_cast<void*>(g_base+0x50000),0x2000,PAGE_READONLY,&old)!=0,"make fixture read-only");
        Rejected(slot,"read-only native payload");Check(VirtualProtect(reinterpret_cast<void*>(g_base+0x50000),0x2000,old,&tmp)!=0,"restore fixture page");
        for(const auto& sig:gummi_extra::code){Ready();At<BYTE>(sig.rva+sig.size-1)^=1;Rejected(slot,"full code signature covers final instruction");}
        Ready();double args[8]={100};TrainerResult result{};args[7]=std::numeric_limits<double>::quiet_NaN();Check(GummiExtraHandle(host,slot,args,result)&&result.code!=0&&calls==0,"unused nonfinite args rejected");
        Ready();Check(GummiExtraHandle(host,slot,nullptr,result)&&result.code!=0&&!calls,"null args rejected");
    }
    for(unsigned slot=320;slot<=322;++slot){
        Ready();At<int>(0x50570+36+4*(slot-320))=INT32_MIN;Rejected(slot,"native signed delta overflow rejected",200);
        Ready();onCodeRead=[](){At<int>(0x50570+36)++;At<int>(0x50570+40)++;At<int>(0x50570+44)++;};Rejected(slot,"runtime stat changed during preflight");
    }
    Ready();At<uintptr_t>(0xAF0780)=0;Rejected(320,"negative mobility requires native system row",-50);
    Ready();At<float>(0xC2018)=-1;Rejected(320,"invalid negative-mobility scaling",-50);
    Ready();At<float>(0xC2018)=std::numeric_limits<float>::infinity();Rejected(320,"nonfinite system coefficient",-50);
    Ready();At<int>(0xC2004)=4097;Rejected(320,"system row traversal bounded",-50);
    Ready();At<int>(0xC2008)=1;Rejected(320,"missing system row zero",-50);
    Ready();At<uintptr_t>(0x50560)=g_base+0xC1088;Rejected(320,"tuning pointer belongs to another row");
    Ready();At<float>(0xC1008+64)=0;Rejected(321,"zero roll duration rejected");
    Ready();At<float>(0xC1008+12)=std::numeric_limits<float>::quiet_NaN();Rejected(320,"nonfinite deceleration");
    Ready();At<float>(0xC1008+4)=std::numeric_limits<float>::max();Rejected(320,"native speed multiplication would overflow");
    Ready();At<float>(0x50000+1108)=std::numeric_limits<float>::max();Rejected(321,"native roll impulse multiplication would overflow");At<float>(0x50000+1108)=0;
    Ready();At<int>(0xC1004)=4097;Rejected(321,"tuning table bounded");
    Ready();onCodeRead=[](){At<float>(0xC2018)=2;};Rejected(320,"negative-mobility coefficient drift",-50);
    Ready();onCodeRead=[](){shared.hostHeartbeat=0;};Rejected(320,"host loss during preflight");
    Ready();At<uintptr_t>(0x50000+2960)=0;Rejected(322,"lock-on subsystem class");
    Ready();At<int>(0xC3004)=0;Rejected(322,"lock-on resource empty");
    Ready();At<uintptr_t>(0x50000+2960+1848)=g_base+0xC3009;Rejected(322,"unaligned lock-on row");
    Ready();At<int>(0xC3008)=999;Rejected(322,"lock-on row ID mismatch");
    Ready();At<float>(0xC3008+16)=-1;Rejected(322,"negative native minimum delay");
    Ready();At<float>(0xC3008+12)=std::numeric_limits<float>::max();Rejected(322,"charge delay multiplication overflow",1000);
    for(int bonus:{0,50,100})for(int points:{1,60,100,900}){
        Ready();At<int>(0x50570+52)=bonus;
        const int gain=int((float(bonus)/100.0f+1)*float(points));int expected=40+gain,stock=2;bool full=false;
        while(expected>=100&&stock<9){expected-=100;++stock;}if(stock==9&&40+gain>=100){expected=100;full=true;}
        const auto r=Command(323,points);
        Check(r.code==0&&calls==1&&lastKind==323&&lastObject==g_base+0x50000+4872&&lastArg==points,"native combo charge ABI exactly once");
        Check(At<int>(0x50000+4872+56)==expected&&At<int>(0x50000+4872+60)==stock&&((At<unsigned>(0x50000+4872+68)&4)!=0)==full,"normal charge-to-stock and cap latch retained");
        Check(postCallReads==0,"charge dispatch discards old pointers");
    }
    Ready();At<int>(0x50000+4872+60)=9;auto r=Command(323,1);Check(r.code==0&&At<int>(0x50000+4872+60)==9&&At<int>(0x50000+4872+56)==41,"stock9 below-threshold does not fabricate full latch");
    Ready();At<int>(0x50000+4872+56)=100;At<int>(0x50000+4872+60)=9;r=Command(323,1);Check(r.code==0&&At<int>(0x50000+4872+56)==100&&(At<unsigned>(0x50000+4872+68)&4),"native full-stock saturation");
    for(int phase=0;phase<=5;++phase){Ready();At<int>(0x50000+4872)=phase;r=Command(323,10);Check(r.code==0&&At<int>(0x50000+4872)==phase,"charge preserves each valid combo phase");}
    for(int phase:{4,5}) {
        Ready();const uintptr_t combo=0x50000+4872;
        for(unsigned i=0;i<5;++i)At<int>(combo+32+4*i)=0;
        At<uintptr_t>(combo+16)=g_base+0xD0000;
        At<int>(combo)=phase;At<int>(combo+52)=6;
        ClearSnapshot();GummiExtraSnapshot(host);
        Check(Valid(324)&&Valid(325)&&Valid(326)&&shared.values[326]==phase,"companion-only index6 finish and recovery keep native readouts");
        r=Command(323,10);
        Check(r.code==0&&calls==1&&At<int>(combo)==phase&&At<int>(combo+52)==6,"companion-only index6 finish and recovery accept charge without changing phase");
        Check(postCallReads==0,"companion-only charge still discards native pointer");
    }
    for(int phase:{0,1,2,3}) {
        Ready();At<int>(0x50000+4872)=phase;At<int>(0x50000+4872+52)=6;
        Rejected(323,"index6 cannot index a stage before the native finish phase");
    }
    Ready();At<int>(0x50000+4872)=4;At<int>(0x50000+4872+52)=7;
    Rejected(323,"index beyond native companion completion sentinel is invalid");
    Ready();At<unsigned>(0x50000+4872+68)=0;Rejected(323,"no installed combo");
    Ready();At<uintptr_t>(0x50000+4872+8)=0;Rejected(323,"combo owner missing");
    Ready();At<uintptr_t>(0x50550)=0;Rejected(323,"combo state backlink missing");
    Ready();At<int>(0x50000+4872+60)=10;Rejected(323,"invalid stock");
    Ready();At<int>(0x50000+4872+56)=101;Rejected(323,"invalid progress");
    Ready();At<int>(0x50000+4872)=1;At<int>(0x50000+4872+52)=5;Rejected(323,"wait phase requires real combo index");
    Ready();At<int>(0x50570+52)=-100;Rejected(323,"zero native charge multiplier");
    Ready();At<int>(0x50570+52)=-99;Rejected(323,"truncated zero charge gain",1);
    Ready();At<int>(0x50570+52)=INT32_MAX;Rejected(323,"native float conversion overflow",900);
    Ready();onCodeRead=[](){At<int>(0x50000+4872+60)++;};Rejected(323,"stock changed before dispatch");
    Ready();ClearSnapshot();GummiExtraSnapshot(host);
    Check(Valid(320)&&shared.values[320]==25&&shared.values[321]==50&&shared.values[322]==10,"runtime stat readouts");
    Check(shared.values[324]==2&&shared.values[325]==40&&shared.values[326]==0,"combo readouts");
    Check(shared.values[327]==12.5&&shared.values[328]==1.25&&shared.values[329]==1.5,"native effective mobility/roll and remaining engine ticks");
    Ready();At<int>(0x50570+36)=-100;At<int>(0x50570+40)=-100;ClearSnapshot();GummiExtraSnapshot(host);Check(shared.values[328]==0.5&&shared.values[329]==0,"negative mobility uses native resource scaling");
    Ready();At<int>(0x50570+36)=-100;At<float>(0xC2018)=2;At<int>(0x50570+40)=500;ClearSnapshot();GummiExtraSnapshot(host);Check(fabs(shared.values[328]-0.1)<0.00001&&shared.values[329]==3,"native effective clamps");
    Ready();At<int>(gummi::ModuleRva+36)=2;ClearSnapshot();GummiExtraSnapshot(host);Check(Valid(320)&&Valid(324),"paused readouts remain available");
    Ready();At<uintptr_t>(gummi::HeapRva)=0;ClearSnapshot();GummiExtraSnapshot(host);Check(!Valid(320)&&!Valid(324),"module teardown omits all stale values");
    Ready();At<unsigned>(0x50000+4872+68)=0;ClearSnapshot();GummiExtraSnapshot(host);Check(Valid(320)&&!Valid(324),"uninstalled combo omitted independently");
    Ready();GummiExtraCapabilities();for(unsigned s=320;s<=329;++s)Check((shared.supported[s/64]&(uint64_t(1)<<(s%64)))!=0,"exact capability range");
    Check(!(shared.supported[319/64]&(uint64_t(1)<<(319%64)))&&!(shared.supported[330/64]&(uint64_t(1)<<(330%64))),"adjacent slots remain free");
    double args[8]{};TrainerResult result{};Check(!GummiExtraHandle(host,319,args,result)&&!GummiExtraHandle(host,324,args,result),"read-only/reserved slot writes rejected");
    RequestTests();
    printf("GummiExtraGuardTests: %u checks, %u failures\n",checks,failures);VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
