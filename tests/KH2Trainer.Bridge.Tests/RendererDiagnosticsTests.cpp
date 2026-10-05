#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdint.h>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <initializer_list>
#include <limits>
namespace {
struct TrainerContext { uintptr_t base,player,status; bool sceneReady; };
struct TrainerResult { LONG code; const wchar_t* text; };
struct Shared { DWORD hostHeartbeat; double values[512]; uint64_t valid[8],supported[8]; } shared{};
uintptr_t g_base=0,g_selectedVtable=0; DWORD g_gameThread=0; LONG g_disabled=0;
Shared* g_shared=&shared;
bool IsInteger(double v,double lo,double hi) { return std::isfinite(v)&&v>=lo&&v<=hi&&floor(v)==v; }
#ifdef RENDERER_PRODUCTION_COMPILE
bool Readable(const void*,SIZE_T) { return false; }
bool Writable(const void*,SIZE_T) { return false; }
void SnapshotValue(unsigned,double) {}
void SupportCapability(unsigned) {}
#include "../../src/KH2Trainer.Bridge/DisplayFeatures.inl"
#include "../../src/KH2Trainer.Bridge/RendererDiagnostics.inl"
#else
#define KH2_DISPLAY_TESTS
constexpr SIZE_T ImageSize=0x900000;
constexpr uintptr_t ObjectRva=0x8A0970, AppAddress=0x220000;
DWORD fakeNow=100000,appId=0,timingId=0,timingProcess=0,fakeTimingExit=STILL_ACTIVE;
HANDLE appHandle=reinterpret_cast<HANDLE>(uintptr_t(0x1234));
HANDLE timingHandle=reinterpret_cast<HANDLE>(uintptr_t(0x5678));
bool throwUnlock=false;
bool exitQueryWorks=true,outerHeld=false,innerHeld=false,tryBusy=false,frequencyWorks=true,qpcWorks=true;
DWORD Now() { return fakeNow; }
DWORD ThreadId(HANDLE h) { return h==appHandle?appId:(h==timingHandle?timingId:0); }
DWORD ProcessIdOfThread(HANDLE h) { return h==timingHandle?timingProcess:0; }
BOOL ExitCodeThread(HANDLE h,DWORD* result) { if(h!=timingHandle||!exitQueryWorks)return FALSE; *result=fakeTimingExit;return TRUE; }
int64_t fakeFrequency=1000000,fakeQpc=20000000;
uintptr_t denied=0,deniedWrite=0,throwRead=0; SIZE_T deniedSize=0,deniedWriteSize=0;
unsigned checks=0,failures=0,locks=0,unlocks=0,tries=0,leaves=0,published=0,qpcCalls=0;
int fakeLockResult=0,fakeUnlockResult=0;
using Mutation=void(*)(); Mutation onLock=nullptr,onInner=nullptr,onQpc=nullptr;
void Check(bool b,const char* label) { ++checks;if(!b){++failures;printf("FAIL %s\n",label);} }
bool Inside(const void* p,SIZE_T n) {
    const auto a=reinterpret_cast<uintptr_t>(p);
    return a>=g_base && n<=ImageSize && a-g_base<=ImageSize-n;
}
bool Overlap(uintptr_t a,SIZE_T n,uintptr_t b,SIZE_T size) { return b && a<b+size && b<a+n; }
bool Readable(const void* p,SIZE_T n) {
    if(throwRead && reinterpret_cast<uintptr_t>(p)==throwRead && outerHeld)
        RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    return Inside(p,n) && !Overlap(reinterpret_cast<uintptr_t>(p),n,denied,deniedSize);
}
bool Writable(const void* p,SIZE_T n) { return Readable(p,n) && !Overlap(reinterpret_cast<uintptr_t>(p),n,deniedWrite,deniedWriteSize); }
BOOL ClockFrequency(LARGE_INTEGER* v) { v->QuadPart=fakeFrequency;return frequencyWorks; }
BOOL ClockNow(LARGE_INTEGER* v) {
    ++qpcCalls;Check(outerHeld&&innerHeld,"QPC comparison is sampled under locks after record capture");
    if(onQpc)onQpc();v->QuadPart=fakeQpc;return qpcWorks;
}
BOOL TryHistory(LPCRITICAL_SECTION cs) {
    ++tries;Check(outerHeld&&!innerHeld && reinterpret_cast<uintptr_t>(cs)==g_base+ObjectRva+31392,"native outer-before-inner lock order");
    if(tryBusy)return FALSE;
    innerHeld=true;if(onInner)onInner();return TRUE;
}
void LeaveHistory(LPCRITICAL_SECTION cs) {
    ++leaves;Check(outerHeld&&innerHeld && reinterpret_cast<uintptr_t>(cs)==g_base+ObjectRva+31392,"history lock released once before outer");innerHeld=false;
}
void SnapshotValue(unsigned slot,double value) {
    Check(!outerHeld&&!innerHeld,"publish only after both releases");++published;
    shared.values[slot]=value;shared.valid[slot/64]|=uint64_t(1)<<(slot%64);
}
void SupportCapability(unsigned slot) { shared.supported[slot/64]|=uint64_t(1)<<(slot%64); }
#define GetTickCount Now
#define GetThreadId ThreadId
#define GetProcessIdOfThread ProcessIdOfThread
#define GetExitCodeThread ExitCodeThread
#define QueryPerformanceFrequency ClockFrequency
#define QueryPerformanceCounter ClockNow
#define TryEnterCriticalSection TryHistory
#define LeaveCriticalSection LeaveHistory
#include "../../src/KH2Trainer.Bridge/DisplayFeatures.inl"
#include "../../src/KH2Trainer.Bridge/RendererDiagnostics.inl"
template<class T>T& At(uintptr_t rva) { return *reinterpret_cast<T*>(g_base+rva); }
template<class T>T& GX(SIZE_T offset) { return At<T>(ObjectRva+offset); }
template<SIZE_T N>void Seed(uintptr_t rva,const BYTE(&bytes)[N]) { memcpy(reinterpret_cast<void*>(g_base+rva),bytes,N); }
int __cdecl MockLock(void* p) {
    ++locks;Check(p==reinterpret_cast<void*>(g_base+ObjectRva+30848),"opaque presentation mutex address");
    if(fakeLockResult)return fakeLockResult;
    Check(!outerHeld&&!innerHeld,"outer mutex acquired exactly once");outerHeld=true;if(onLock)onLock();return 0;
}
int __cdecl MockUnlock(void* p) {
    ++unlocks;Check(outerHeld&&!innerHeld&&p==reinterpret_cast<void*>(g_base+ObjectRva+30848),"captured outer unlock called exactly once");outerHeld=false;
    if(throwUnlock)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    return fakeUnlockResult;
}
constexpr uintptr_t NodeBase=0x300000, SentinelBase=0x280000;
uintptr_t Node(unsigned which,unsigned n=0) { return NodeBase+which*0x10000+n*80; }
uintptr_t Sentinel(unsigned which) { return SentinelBase+which*80; }
void MakeList(unsigned which,unsigned count) {
    const auto& spec=renderer_diagnostics::Lists[which];
    GX<uintptr_t>(spec.offset)=g_base+Sentinel(which);GX<uint64_t>(spec.offset+8)=count;
    At<uintptr_t>(Sentinel(which))=g_base+(count?Node(which):Sentinel(which));
    At<uintptr_t>(Sentinel(which)+8)=g_base+(count?Node(which,count-1):Sentinel(which));
    for(unsigned i=0;i<count;++i) {
        const auto node=Node(which,i);
        At<uintptr_t>(node)=g_base+(i+1<count?Node(which,i+1):Sentinel(which));
        At<uintptr_t>(node+8)=g_base+(i?Node(which,i-1):Sentinel(which));
        At<int64_t>(node+spec.beginOffset)=fakeQpc-2500-static_cast<int64_t>(i)*100;
        At<int64_t>(node+spec.endOffset)=fakeQpc-500;
        if(which==1) { At<uint32_t>(node+32)=1;At<uint32_t>(node+36)=2;At<uint32_t>(node+40)=1; }
        else if(which==3)At<uint32_t>(node+48)=0;
        else At<uint32_t>(node+32)=1;
    }
}
void Reset() {
    memset(reinterpret_cast<void*>(g_base),0,ImageSize);
    shared={};g_shared=&shared;shared.hostHeartbeat=fakeNow=100000;
    fakeFrequency=1000000;fakeQpc=20000000;
    g_disabled=0;renderer_diagnostics::faulted=display_preview::faulted=false;
    g_gameThread=appId=GetCurrentThreadId();timingId=appId+1;timingProcess=GetCurrentProcessId();
    fakeTimingExit=STILL_ACTIVE;exitQueryWorks=true;g_selectedVtable=g_base+0x100000;
    denied=deniedWrite=throwRead=0;deniedSize=deniedWriteSize=0;
    throwUnlock=outerHeld=innerHeld=tryBusy=false;frequencyWorks=qpcWorks=true;
    locks=unlocks=tries=leaves=published=qpcCalls=0;fakeLockResult=fakeUnlockResult=0;
    onLock=onInner=onQpc=nullptr;
    GX<uintptr_t>(0)=g_base+display_preview::VtableRva;
    GX<uintptr_t>(736)=g_base+0x200000;GX<uintptr_t>(1144)=g_base+0x210000;
    GX<HANDLE>(784)=appHandle;GX<HANDLE>(792)=timingHandle;GX<int>(808)=0;GX<uintptr_t>(1000)=g_base+AppAddress;
    At<uintptr_t>(display_preview::AppRva)=g_base+AppAddress;At<uintptr_t>(AppAddress)=g_selectedVtable;At<int>(AppAddress+4752)=-1;
    At<int>(display_preview::EpochRva)=-100;
    display_preview::testLock=MockLock;display_preview::testUnlock=MockUnlock;display_preview::testRuntimeAvailable=true;
    // Preview setters remain null. Executing any game-code pointer in this
    // PAGE_READWRITE fixture would fault, while legitimate snapshots must pass.
    display_preview::testBrightness=nullptr;display_preview::testColor=nullptr;
    At<uintptr_t>(0x57B458)=reinterpret_cast<uintptr_t>(MockLock);At<uintptr_t>(0x57B450)=reinterpret_cast<uintptr_t>(MockUnlock);
    Seed(0x5061A0,display_preview::BrightnessCode);Seed(0x5061F0,display_preview::ColorCode);
    Seed(0x1268C0,display_preview::GammaCode);Seed(0x125D00,display_preview::ColorSetterCode);
    Seed(0x11C150,display_preview::GetterCode);Seed(0x43AD04,display_preview::LockCode);Seed(0x43AD0A,display_preview::UnlockCode);
    At<float>(0x5B532C)=50;At<float>(0x5A9CB4)=2.2f;
    GX<uintptr_t>(1344)=g_base+0x5A8DA8;
    GX<unsigned>(1504)=4;GX<unsigned>(1108)=8;GX<int>(30556)=2;
    GX<int>(1352)=1280;GX<int>(1356)=720;GX<int>(8)=1920;GX<int>(12)=1080;
    GX<uintptr_t>(1296)=g_base+0x230000;GX<uint64_t>(1312)=256ull<<20;GX<uint64_t>(1320)=512ull<<20;
    for(unsigned i=0;i<3;++i) {
        GX<uintptr_t>(1608+8*i)=g_base+renderer_diagnostics::PoolRvas[i];
        At<uintptr_t>(renderer_diagnostics::PoolRvas[i])=g_base+renderer_diagnostics::PoolVtables[i];
        for(unsigned j=0;j<=i;++j)At<uintptr_t>(renderer_diagnostics::PoolRvas[i]+8+72*j)=0xDEADBEEF;
    }
    At<int64_t>(renderer_diagnostics::FrequencyRva)=fakeFrequency;
    for(unsigned i=0;i<4;++i)MakeList(i,3);
}
TrainerContext Context() { return {g_base,0,0,false}; }
bool Has(unsigned slot) { return (shared.valid[slot/64]&(uint64_t(1)<<(slot%64)))!=0; }
void Run() { RendererDiagnosticsSnapshot(Context()); }
void Rejected(const char* label,bool locked=false) {
    Run();Check(published==0&&locks==(locked?1u:0u)&&unlocks==locks&&!outerHeld&&!innerHeld,label);
}
void RejectMutation(Mutation m,const char* label) { Reset();onLock=m;Rejected(label,true); }
bool CatchSnapshot() { __try { Run(); } __except(EXCEPTION_EXECUTE_HANDLER){return true;}return false; }
uint64_t HashFixture() { uint64_t v=1469598103934665603ull;const auto* p=reinterpret_cast<BYTE*>(g_base);for(SIZE_T i=0;i<ImageSize;++i)v=(v^p[i])*1099511628211ull;return v; }

void TestNormal() {
    Reset();const uint64_t before=HashFixture();Run();
    Check(published==16&&locks==1&&unlocks==1&&tries==1&&leaves==1,"all sixteen values published with paired locks");
    for(unsigned slot=392;slot<=395;++slot)Check(Has(slot)&&shared.values[slot]==2,"native timestamp offsets and milliseconds");
    const double expected[]={4,8,1280,720,1920,1080,256,512,2,1,2,3};
    for(unsigned i=0;i<12;++i)Check(Has(396+i)&&shared.values[396+i]==expected[i],"distinct raw units and pool count");
    Check(before==HashFixture(),"entire fake game image unchanged; no COM or renderer call");
    Reset();RendererDiagnosticsCapabilities();for(unsigned i=0;i<512;++i)
        Check(bool(shared.supported[i/64]&(uint64_t(1)<<(i%64)))==(i>=392&&i<=407),"exact sixteen capability bits");
    Reset();RendererDiagnosticsReset(Context());Check(!locks&&!published&&!renderer_diagnostics::faulted,"normal reset has no effect or game access");
    RendererDiagnosticsFailureReset(Context());Rejected("failure reset prevents future snapshots");
    RendererDiagnosticsReset(Context());Check(renderer_diagnostics::faulted,"normal reset cannot clear fault latch");
}
void TestLifetimes() {
    const Mutation mutations[]={
        []{g_disabled=1;},[]{g_gameThread=0;},[]{++g_gameThread;},[]{g_shared=nullptr;},
        []{shared.hostHeartbeat=0;},[]{fakeNow+=5001;},[]{display_preview::faulted=true;},
        []{At<int>(display_preview::EpochRva)=0;},[]{At<int>(display_preview::EpochRva)=-1;},
        []{GX<uintptr_t>(0)+=8;},[]{GX<uintptr_t>(736)=0;},[]{GX<uintptr_t>(1144)=0;},
        []{GX<HANDLE>(784)=nullptr;},[]{GX<HANDLE>(792)=nullptr;},[]{GX<HANDLE>(792)=appHandle;},
        []{++appId;},[]{timingId=appId;},[]{timingId=0;},[]{++timingProcess;},[]{fakeTimingExit=0;},
        []{exitQueryWorks=false;},[]{GX<int>(808)=1;},[]{At<int>(AppAddress+4752)=0;},
        []{GX<uintptr_t>(1000)+=8;},[]{At<uintptr_t>(AppAddress)+=8;},[]{g_selectedVtable=0;},
        []{display_preview::testRuntimeAvailable=false;},[]{At<uintptr_t>(0x57B458)+=1;},[]{At<uintptr_t>(0x57B450)+=1;},
        []{At<BYTE>(0x43AD04)^=1;},[]{At<BYTE>(0x43AD0A)^=1;},[]{At<BYTE>(0x11C150)^=1;}
    };
    for(auto m:mutations){Reset();m();Rejected("invalid lifetime/code rejected before acquisition");}
    for(auto m:mutations)RejectMutation(m,"lifetime/code lost while waiting still releases captured mutex");
    RejectMutation([]{GX<uintptr_t>(736)+=8;},"replacement device rejected after wait");
    RejectMutation([]{GX<uintptr_t>(1144)+=8;},"replacement root rejected after wait");
    Reset();auto c=Context();++c.base;RendererDiagnosticsSnapshot(c);Check(!published&&!locks,"foreign context rejected");
    Reset();shared.hostHeartbeat=0xfffffff0;fakeNow=15;Run();Check(published==16,"heartbeat wrap accepted");
    for(uintptr_t rva:{uintptr_t(display_preview::EpochRva),uintptr_t(display_preview::AppRva),uintptr_t(AppAddress+4755),uintptr_t(ObjectRva+31392+39)}) {
        Reset();denied=g_base+rva;deniedSize=1;Run();Check(!published&&unlocks==locks,"unreadable last lifetime or history byte rejected");
    }
    for(uintptr_t rva:{uintptr_t(ObjectRva+30848+79),uintptr_t(ObjectRva+31392+39)}) {
        Reset();deniedWrite=g_base+rva;deniedWriteSize=1;Run();Check(!published&&unlocks==locks,"unwritable synchronization storage rejected");
    }
    Reset();GX<uintptr_t>(1344)+=8;Rejected("foreign framebuffer rejected",true);
    for(unsigned i=0;i<3;++i) {
        Reset();GX<uintptr_t>(1608+8*i)+=8;Rejected("foreign pool binding rejected",true);
        Reset();At<uintptr_t>(renderer_diagnostics::PoolRvas[i])+=8;Rejected("foreign pool vtable rejected",true);
        Reset();denied=g_base+renderer_diagnostics::PoolRvas[i]+4711;deniedSize=1;Rejected("unreadable last pool byte rejected",true);
    }
}
void TestLocksAndFaults() {
    Reset();fakeLockResult=1;Run();Check(!published&&locks==1&&!unlocks&&!tries,"failed outer acquisition is never unlocked");
    Reset();tryBusy=true;Run();Check(published==12&&tries==1&&!leaves&&unlocks==1,"busy history lock skips only four times");
    Reset();fakeUnlockResult=1;Run();Check(!published&&renderer_diagnostics::faulted&&unlocks==1,"unlock failure discards every copied value");
    Run();Check(locks==1,"faulted snapshot never retries uncertain mutex");
    Check(display_preview::faulted,"uncertain unlock also latches Display's shared mutex guard");
    DisplaySnapshot(Context());TrainerResult result{};double args[8]{};
    Check(DisplayHandle(Context(),304,args,result)&&locks==1&&!published,"Display snapshot and command cannot retry Renderer-failed mutex");
    RendererDiagnosticsReset(Context());Check(display_preview::faulted&&renderer_diagnostics::faulted,"normal reset preserves both mutex fault latches");
    Reset();throwUnlock=true;Check(CatchSnapshot()&&!published&&unlocks==1&&renderer_diagnostics::faulted&&display_preview::faulted,"unlock exception latches both users and publishes nothing");
    DisplaySnapshot(Context());Check(locks==1,"Display snapshot cannot retry after unlock exception");
    Reset();throwRead=g_base+renderer_diagnostics::PoolRvas[0];Check(CatchSnapshot()&&unlocks==1&&!tries&&!published,"pre-inner SEH releases outer mutex");
    Reset();throwRead=g_base+Node(0);Check(CatchSnapshot()&&leaves==1&&unlocks==1&&!published,"inner read fault releases both locks");
    Check(renderer_diagnostics::faulted&&!outerHeld&&!innerHeld,"read exception latches module unavailable");
    Reset();onLock=[]{fakeQpc+=2000000;for(unsigned i=0;i<4;++i)MakeList(i,3);};Run();
    Check(published==16&&qpcCalls==1,"post-lock QPC avoids false future timestamps after waiting");
    Reset();onQpc=[]{At<int64_t>(Node(0)+24)=INT64_MAX;};Run();
    Check(Has(392)&&shared.values[392]==2,"duration is computed from immutable copied record");
}
void TestLists() {
    for(unsigned which=0;which<4;++which) {
        const auto spec=renderer_diagnostics::Lists[which];
        for(unsigned count=0;count<=spec.capacity;++count) {
            Reset();MakeList(which,count);Run();
            Check(Has(392+which)==bool(count)&&published==(count?16u:15u),"every bounded list size including maximum");
            if(count)Check(shared.values[392+which]==2,"head is newest rather than oldest");
        }
        Reset();GX<uint64_t>(spec.offset+8)=spec.capacity+1ull;Run();Check(!Has(392+which)&&published==15,"over-capacity count rejected");
        Reset();GX<uint64_t>(spec.offset+8)=UINT64_MAX;Run();Check(!Has(392+which),"huge count never loops");
        Reset();GX<uintptr_t>(spec.offset)=0;Run();Check(!Has(392+which),"null sentinel rejected");
        Reset();denied=g_base+Sentinel(which)+15;deniedSize=1;Run();Check(!Has(392+which),"sentinel full span required");
        Reset();denied=g_base+Node(which,2)+spec.nodeBytes-1;deniedSize=1;Run();Check(!Has(392+which),"oldest node full span required");
        Reset();At<uintptr_t>(Node(which,1))=g_base+Node(which,0);Run();Check(!Has(392+which),"interior repeated-node cycle rejected");
        Reset();At<uintptr_t>(Node(which,1))=g_base+Sentinel(which);Run();Check(!Has(392+which),"short chain rejected");
        Reset();GX<uint64_t>(spec.offset+8)=2;Run();Check(!Has(392+which),"long chain rejected");
        Reset();At<uintptr_t>(Node(which,1)+8)=g_base+Sentinel(which);Run();Check(!Has(392+which),"middle backlink rejected");
        Reset();At<uintptr_t>(Sentinel(which)+8)=g_base+Node(which,0);Run();Check(!Has(392+which),"sentinel tail mismatch rejected");
        Reset();At<uintptr_t>(Node(which,2))=g_base+Sentinel((which+1)%4);Run();Check(!Has(392+which),"foreign sentinel rejected");
        Reset();MakeList(which,0);At<uintptr_t>(Sentinel(which))=g_base+Node(which);Run();Check(!Has(392+which),"empty count with live links is not accepted");
        Reset();At<uint32_t>(Node(which)+(which==3?48:32))=UINT32_MAX;Run();Check(!Has(392+which),"invalid newest tag rejected");
        Reset();At<uintptr_t>(Node(which,1))=UINTPTR_MAX-1;Run();Check(!Has(392+which),"unreadable overflow-adjacent pointer rejected");
    }
    for(unsigned offset:{36u,40u}) {Reset();At<uint32_t>(Node(1)+offset)=3;Run();Check(!Has(393),"Present index outside three buffers rejected");}
    Reset();At<uint32_t>(Node(1)+44)=0xFFFFFFFF;Run();Check(Has(393),"uninitialized Present padding ignored");
    Reset();At<uint32_t>(Node(2)+36)=0xFFFFFFFF;Run();Check(Has(394),"wait padding ignored");
    Reset();At<int64_t>(Node(3)+16)=INT64_MIN;At<int64_t>(Node(3)+24)=INT64_MAX;Run();Check(Has(395)&&shared.values[395]==2,"CPU render interval does not use wait timestamp pair");
}
void TestClocks() {
    using renderer_diagnostics::Record;using renderer_diagnostics::Milliseconds;
    double ms=0;
    Check(Milliseconds({1000000000000000ll,1000000000000003ll,true},0,1000000,1000000000000004ll,ms)&&ms==0.003,"large absolute ticks retain small delta precision");
    Check(Milliseconds({1,10000001,true},0,1000000,10000001,ms)&&ms==10000,"inclusive ten-second duration");
    Check(!Milliseconds({1,10000002,true},0,1000000,10000002,ms),"duration beyond limit rejected");
    Check(Milliseconds({15000000,15000000,true},0,1000000,25000000,ms)&&ms==0,"zero interval and inclusive age limit");
    Check(!Milliseconds({15000000,15000000,true},0,1000000,25000001,ms),"stale age rejected");
    Check(Milliseconds({15000000,21000000,true},0,1000000,20000000,ms),"inclusive one-second GPU calibration skew");
    Check(!Milliseconds({15000000,21000001,true},0,1000000,20000000,ms),"larger GPU future skew rejected");
    for(unsigned kind=1;kind<4;++kind)Check(!Milliseconds({15000000,20000001,true},kind,1000000,20000000,ms),"CPU records cannot be in future");
    for(const Record r: {Record{0,5,true},Record{-1,5,true},Record{6,5,true},Record{INT64_MIN,INT64_MAX,true},Record{1,INT64_MAX,true},Record{1,1,false}})
        Check(!Milliseconds(r,0,1000000,20000000,ms),"invalid signed timestamp cannot overflow or publish");
    for(int64_t freq:{int64_t(0),int64_t(-1),INT64_MAX})Check(!Milliseconds({1,2,true},0,freq,2,ms),"invalid or multiplicatively unsafe frequency rejected");
    Reset();++fakeFrequency;Run();Check(published==12,"native and Windows QPC frequency mismatch hides only time values");
    Reset();frequencyWorks=false;Run();Check(published==12&&!qpcCalls,"frequency API failure skips QPC");
    Reset();qpcWorks=false;Run();Check(published==12,"QPC API failure hides times");
    Reset();fakeFrequency=At<int64_t>(renderer_diagnostics::FrequencyRva)=0;Run();Check(published==12,"zero shared frequency rejected");
    Reset();denied=g_base+renderer_diagnostics::FrequencyRva;deniedSize=8;Run();Check(published==12,"unreadable frequency suppresses time fields");
    Reset();At<int64_t>(Node(0)+16)=fakeQpc-12345;At<int64_t>(Node(0)+24)=fakeQpc;Run();
    Check(Has(392)&&fabs(shared.values[392]-12.345)<1e-12,"calibrated GPU values use QPC milliseconds once");
}
void TestResources() {
    for(unsigned samples:{1u,2u,4u,8u})for(unsigned capability:{1u,2u,4u,8u}) {
        Reset();GX<unsigned>(1504)=samples;GX<unsigned>(1108)=capability;GX<int>(30556)=3;Run();
        Check(Has(396)&&Has(397)&&Has(404)&&shared.values[396]==samples&&shared.values[397]==capability,"independent actual sample count/capability/replayed AA level");
    }
    for(unsigned samples:{0u,3u,16u,UINT32_MAX})for(unsigned offset:{1504u,1108u}) {
        Reset();GX<unsigned>(offset)=samples;Run();Check(published==15&&!Has(offset==1504?396:397),"bad individual MSAA value suppressed");
    }
    const unsigned dimensions[]={1352,1356,8,12};
    for(unsigned i=0;i<4;++i)for(int v:{-1,0,1,16384,16385,INT32_MAX}) {
        Reset();GX<int>(dimensions[i])=v;Run();Check(Has(398+i)==(v>=1&&v<=16384),"dimension bounds are independent");
    }
    for(int level:{-1,0,1,2,3,4,INT32_MAX}){Reset();GX<int>(30556)=level;Run();Check(Has(404)==(level>=0&&level<=3),"AA exponent range");}
    for(unsigned i=0;i<2;++i)for(uint64_t v:{0ull,1ull,(1ull<<22)-1,1ull<<22,1ull<<40,(1ull<<40)+(1ull<<22),UINT64_MAX}) {
        Reset();GX<uint64_t>(1312+8*i)=v;Run();const bool ok=v==(1ull<<22)||v==(1ull<<40);
        Check(Has(402+i)==ok&&Has(402+(1-i)),"individual heap bound/alignment and MiB conversion");
        if(ok)Check(shared.values[402+i]==double(v)/1048576,"binary MiB scale");
    }
    Reset();GX<uintptr_t>(1296)=0;Run();Check(!Has(402)&&!Has(403)&&published==14,"allocation and cached budget require a live heap");
    for(unsigned pool=0;pool<3;++pool)for(unsigned n=0;n<=64;++n) {
        Reset();for(unsigned j=0;j<64;++j)At<uintptr_t>(renderer_diagnostics::PoolRvas[pool]+8+72*j)=j<n?UINTPTR_MAX:0;
        Run();Check(Has(405+pool)&&shared.values[405+pool]==n,"every occupancy0..64 counted without dereferencing COM pointers");
    }
}
#endif
}
#ifndef RENDERER_PRODUCTION_COMPILE
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,ImageSize,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(!g_base)return 2;
    TestNormal();TestLifetimes();TestLocksAndFaults();TestLists();TestClocks();TestResources();
    printf("RendererDiagnosticsTests: %u checks, %u failures\n",checks,failures);
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
#endif
