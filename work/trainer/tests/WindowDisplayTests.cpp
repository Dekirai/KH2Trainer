#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdint.h>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <initializer_list>
#include <limits>
#include <utility>
namespace {
struct TrainerContext { uintptr_t base,player,status;bool sceneReady; };
struct TrainerResult { LONG code;const wchar_t* text; };
struct Shared { DWORD hostHeartbeat;double values[512];uint64_t valid[8],supported[8]; } shared{};
uintptr_t g_base=0,g_selectedVtable=0;DWORD g_gameThread=0;LONG g_disabled=0;
Shared* g_shared=&shared;
bool IsInteger(double v,double lo,double hi) { return std::isfinite(v)&&v>=lo&&v<=hi&&floor(v)==v; }
#ifdef WINDOW_DISPLAY_PRODUCTION_COMPILE
bool Readable(const void*,SIZE_T) { return false; }
bool Writable(const void*,SIZE_T) { return false; }
void SnapshotValue(unsigned,double) {}
void SupportCapability(unsigned) {}
#include "../../../trainer/Native/DisplayFeatures.inl"
#include "../../../trainer/Native/RendererDiagnostics.inl"
#include "../../../trainer/Native/WindowDisplayFeatures.inl"
#else
#define KH2_DISPLAY_TESTS
#define KH2_WINDOW_DISPLAY_TESTS
constexpr SIZE_T ImageSize=0x900000;
constexpr uintptr_t ObjectRva=0x8A0970,AppAddress=0x220000;
DWORD fakeNow=100000,appId=0,timingId=0,timingProcess=0,windowThread=0,windowProcess=0;
HANDLE appHandle=reinterpret_cast<HANDLE>(uintptr_t(0x1234)),timingHandle=reinterpret_cast<HANDLE>(uintptr_t(0x5678));
HWND windowHandle=reinterpret_cast<HWND>(uintptr_t(0x9876));
bool outerHeld=false,tryBusy=false,windowValid=true,threadAlive=true,throwUnlock=false,throwLeave=false,throwTry=false,throwLock=false;
int depth=0,setterFault=0,lockResult=0,fakeUnlockResult=0;
uintptr_t denied=0,deniedWrite=0;SIZE_T deniedSize=0,deniedWriteSize=0;
unsigned checks=0,failures=0,locks=0,unlocks=0,tries=0,leaves=0,nativeEnters=0,nativeLeaves=0,setters=0,published=0;
int lastMode=-1;float lastDimensions[2]{};
using Mutation=void(*)();Mutation onLock=nullptr,onInner=nullptr;
void Check(bool b,const char* label) { ++checks;if(!b){++failures;printf("FAIL %s\n",label);} }
bool Overlap(uintptr_t a,SIZE_T n,uintptr_t b,SIZE_T size) { return b && a<b+size && b<a+n; }
bool Readable(const void* p,SIZE_T n) {
    const auto a=reinterpret_cast<uintptr_t>(p);
    return a>=g_base && n<=ImageSize && a-g_base<=ImageSize-n && !Overlap(a,n,denied,deniedSize);
}
bool Writable(const void* p,SIZE_T n) { return Readable(p,n)&&!Overlap(reinterpret_cast<uintptr_t>(p),n,deniedWrite,deniedWriteSize); }
DWORD Now() { return fakeNow; }
DWORD ThreadId(HANDLE h) { return h==appHandle?appId:(h==timingHandle?timingId:0); }
DWORD ProcessIdOfThread(HANDLE h) { return h==timingHandle?timingProcess:0; }
BOOL ExitCodeThread(HANDLE h,DWORD* out) { if(h!=timingHandle)return FALSE;*out=threadAlive?STILL_ACTIVE:0;return TRUE; }
DWORD WindowThread(HWND h,DWORD* out) { *out=windowProcess;return h==windowHandle?windowThread:0; }
BOOL WindowValid(HWND h) { return h==windowHandle && windowValid; }
BOOL TryResize(LPCRITICAL_SECTION cs) {
    ++tries;Check(outerHeld&&depth==0&&reinterpret_cast<uintptr_t>(cs)==g_base+ObjectRva+31432,"outer then resize lock");
    if(throwTry)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    if(tryBusy)return FALSE;
    ++depth;if(onInner)onInner();return TRUE;
}
void WINAPI NativeEnter(LPCRITICAL_SECTION cs) {
    ++nativeEnters;Check(outerHeld&&depth==1&&reinterpret_cast<uintptr_t>(cs)==g_base+ObjectRva+31432,"original setter recurses into already-held resize CS");++depth;
}
void WINAPI NativeLeave(LPCRITICAL_SECTION cs) {
    Check(outerHeld&&depth>0&&reinterpret_cast<uintptr_t>(cs)==g_base+ObjectRva+31432,"captured resize leave with acquired ownership");
    if(depth==2)++nativeLeaves;else ++leaves;
    if(throwLeave && depth==1)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    --depth;
}
void SnapshotValue(unsigned slot,double value) {
    Check(!outerHeld&&depth==0,"publish copied snapshot only after both unlocks");
    ++published;shared.values[slot]=value;shared.valid[slot/64]|=uint64_t(1)<<(slot%64);
}
void SupportCapability(unsigned slot) { shared.supported[slot/64]|=uint64_t(1)<<(slot%64); }
#define GetTickCount Now
#define GetThreadId ThreadId
#define GetProcessIdOfThread ProcessIdOfThread
#define GetExitCodeThread ExitCodeThread
#define GetWindowThreadProcessId WindowThread
#define IsWindow WindowValid
#define TryEnterCriticalSection TryResize
#include "../../../trainer/Native/DisplayFeatures.inl"
#include "../../../trainer/Native/RendererDiagnostics.inl"
#include "../../../trainer/Native/WindowDisplayFeatures.inl"
template<class T>T& At(uintptr_t rva) { return *reinterpret_cast<T*>(g_base+rva); }
template<class T>T& GX(SIZE_T offset) { return At<T>(ObjectRva+offset); }
template<SIZE_T N>void Seed(uintptr_t rva,const BYTE(&bytes)[N]) { memcpy(reinterpret_cast<void*>(g_base+rva),bytes,N); }
void CodeAccess(DWORD protection) {
    DWORD old=0;
    Check(VirtualProtect(reinterpret_cast<void*>(g_base+0x124000),0x2000,protection,&old)!=0,"isolated setter code page protection");
    Check(VirtualProtect(reinterpret_cast<void*>(g_base+0x439000),0x1000,protection,&old)!=0,"isolated cookie-check page protection");
}
void Corrupt(uintptr_t rva) { CodeAccess(PAGE_READWRITE);At<BYTE>(rva)^=1;CodeAccess(PAGE_EXECUTE_READ); }
int __cdecl MockLock(void* p) {
    ++locks;Check(p==reinterpret_cast<void*>(g_base+ObjectRva+30848),"presentation mutex address");
    if(throwLock)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    if(lockResult)return lockResult;
    Check(!outerHeld&&depth==0,"presentation acquired once");outerHeld=true;if(onLock)onLock();return 0;
}
int __cdecl MockUnlock(void* p) {
    ++unlocks;Check(outerHeld&&p==reinterpret_cast<void*>(g_base+ObjectRva+30848),"captured presentation unlock exactly once");outerHeld=false;
    if(throwUnlock)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    return fakeUnlockResult;
}
void __fastcall NativeSetter(void* object,const float* size,int mode) {
    ++setters;Check(outerHeld&&depth==1&&object==reinterpret_cast<void*>(g_base+ObjectRva),"leased GX and two locks at native dispatch");
    Check(mode==0 || mode==2,"exclusive-fullscreen branch is never reached");
    lastMode=mode;lastDimensions[0]=size[0];lastDimensions[1]=size[1];
    Check(reinterpret_cast<uintptr_t>(size)<g_base || reinterpret_cast<uintptr_t>(size)>=g_base+ImageSize,"private stack input, not borrowed game field");
    if(setterFault==1)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    if(setterFault==2) {
        // Compiled, unwindable fault seam: model an interrupted native recursion.
        // Do not throw across the copied leaf fixture's unregistered xdata.
        NativeEnter(reinterpret_cast<LPCRITICAL_SECTION>(g_base+ObjectRva+31432));
        RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    }
    // These are the original 590 setter bytes and 33 cookie-check bytes in a
    // private synthetic image. Every external CS call is redirected to mocks.
    // No game process, COM method, UI API or resource-rebuild routine is called.
    reinterpret_cast<window_display::SetterFn>(g_base+0x124FE0)(object,size,mode);
    if(setterFault==3)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
}
void Reset() {
    CodeAccess(PAGE_READWRITE);memset(reinterpret_cast<void*>(g_base),0,ImageSize);
    shared={};g_shared=&shared;shared.hostHeartbeat=fakeNow=100000;
    g_disabled=0;window_display::faulted=display_preview::faulted=renderer_diagnostics::faulted=false;
    g_gameThread=appId=GetCurrentThreadId();timingId=appId+1;windowThread=appId+2;
    timingProcess=windowProcess=GetCurrentProcessId();g_selectedVtable=g_base+0x100000;
    denied=deniedWrite=0;deniedSize=deniedWriteSize=0;
    outerHeld=tryBusy=throwUnlock=throwLeave=throwTry=throwLock=false;windowValid=threadAlive=true;
    depth=setterFault=lockResult=fakeUnlockResult=0;lastMode=-1;lastDimensions[0]=lastDimensions[1]=-1;
    locks=unlocks=tries=leaves=nativeEnters=nativeLeaves=setters=published=0;onLock=onInner=nullptr;
    GX<uintptr_t>(0)=g_base+display_preview::VtableRva;GX<uintptr_t>(736)=g_base+0x200000;GX<uintptr_t>(1144)=g_base+0x210000;
    GX<HANDLE>(784)=appHandle;GX<HANDLE>(792)=timingHandle;GX<uintptr_t>(1000)=g_base+AppAddress;GX<HWND>(1008)=windowHandle;
    At<uintptr_t>(display_preview::AppRva)=g_base+AppAddress;At<uintptr_t>(AppAddress)=g_selectedVtable;At<int>(AppAddress+4752)=-1;At<int>(display_preview::EpochRva)=-100;
    display_preview::testLock=MockLock;display_preview::testUnlock=MockUnlock;display_preview::testRuntimeAvailable=true;
    At<uintptr_t>(0x57B458)=reinterpret_cast<uintptr_t>(MockLock);At<uintptr_t>(0x57B450)=reinterpret_cast<uintptr_t>(MockUnlock);
    Seed(0x5061A0,display_preview::BrightnessCode);Seed(0x5061F0,display_preview::ColorCode);Seed(0x1268C0,display_preview::GammaCode);Seed(0x125D00,display_preview::ColorSetterCode);
    Seed(0x11C150,display_preview::GetterCode);Seed(0x43AD04,display_preview::LockCode);Seed(0x43AD0A,display_preview::UnlockCode);
    At<float>(0x5B532C)=50;At<float>(0x5A9CB4)=2.2f;
    window_display::testSetter=NativeSetter;window_display::testEnter=NativeEnter;window_display::testLeave=NativeLeave;window_display::testSystemRuntime=true;
    At<uintptr_t>(0x57B2D8)=reinterpret_cast<uintptr_t>(NativeEnter);At<uintptr_t>(0x57B2D0)=reinterpret_cast<uintptr_t>(NativeLeave);
    Seed(0x124FE0,window_display::SetterCode);Seed(0x439A60,window_display::CookieCode);
    At<uint64_t>(0x7591F8)=0x123456781234ull;
    At<float>(0x5A9CBC)=9;At<float>(0x623BC4)=16;At<float>(0x5A9C9C)=0.0625f;
    GX<int>(8)=1920;GX<int>(12)=1080;GX<int>(1032)=1280;GX<int>(1036)=720;GX<int>(1052)=1280;GX<int>(1056)=720;
    CodeAccess(PAGE_EXECUTE_READ);FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(g_base+0x124FE0),sizeof(window_display::SetterCode));
}
TrainerContext Context() { return {g_base,0,0,false}; }
TrainerResult Apply(unsigned slot=431,double w=1920,double h=1080) {
    const double args[8]={w,h};TrainerResult r{};Check(WindowDisplayHandle(Context(),slot,args,r),"action handled");return r;
}
bool Has(unsigned slot) { return (shared.valid[slot/64]&(uint64_t(1)<<(slot%64)))!=0; }
void Rejected(const char* label) {
    const auto r=Apply();Check(r.code==1&&setters==0&&!outerHeld&&depth==0,label);
}
void TestNativeActions() {
    const struct { double width,height;int outWidth,outHeight; } cases[]={
        {1920,1080,1920,1080},{1280,720,1280,720},{640,360,640,360},{7680,4320,7680,4320},
        {1024,768,1024,576},{1920,1200,1920,1080},{1366,768,1365,768},{1000,700,1000,562},
        {640,4320,640,360},{7680,360,640,360},{7679,4319,7678,4319}
    };
    for(const auto& c:cases) {
        Reset();BYTE before[64]{};memcpy(before,reinterpret_cast<void*>(g_base+ObjectRva+1016),sizeof(before));
        const auto r=Apply(431,c.width,c.height);
        Check(r.code==0&&setters==1&&lastMode==0&&lastDimensions[0]==c.width&&lastDimensions[1]==c.height,"original setter receives exact ABI/input once");
        Check(GX<int>(1032)==c.outWidth&&GX<int>(1036)==c.outHeight,"actual native float32 fit and truncation");
        Check(nativeEnters==1&&nativeLeaves==1&&leaves==1&&unlocks==1&&depth==0&&!outerHeld,"native recursive enter/leave and owned outer releases balance");
        const auto* after=reinterpret_cast<const BYTE*>(g_base+ObjectRva+1016);
        for(unsigned i=0;i<64;++i) {
            const unsigned offset=1016+i;
            if(offset<1024 || offset>1043 || offset==1027)Check(before[i]==after[i],"only documented request bytes changed");
        }
        Check(GX<int>(8)==1920&&GX<int>(12)==1080&&GX<int>(1048)==0,"queue ACK does not claim completed resize");
    }
    for(int current=0;current<=2;++current) {
        Reset();GX<int>(1048)=current;GX<BYTE>(1046)=current==1?1:0;
        GX<int>(1032)=1600;GX<int>(1036)=900;
        const auto r=Apply(432,std::numeric_limits<double>::quiet_NaN(),-1);
        Check(r.code==0&&setters==1&&lastMode==2&&GX<int>(1028)==2&&GX<BYTE>(1026)==0,"maximize works from every native mode without reading args");
        Check(GX<int>(1032)==1600&&GX<int>(1036)==900,"mode2 preserves requested dimensions");
        Check(GX<BYTE>(1024)==1,"original dirty comparison includes dimensions/mode/fullscreen");
        Reset();GX<int>(1048)=current;GX<BYTE>(1046)=current==1?1:0;
        GX<BYTE>(1025)=1;GX<BYTE>(1027)=0xa5;
        Check(Apply(431,1600,900).code==0&&lastMode==0&&GX<int>(1028)==0&&GX<BYTE>(1026)==0,
            "windowed request exits every observed native mode without enumeration");
        Check(GX<int>(1032)==1600&&GX<int>(1036)==900&&GX<BYTE>(1024)==1&&GX<BYTE>(1025)==0&&GX<BYTE>(1027)==0xa5,
            "native geometry flag reset and request padding preservation");
    }
    Reset();Apply(431,1280,720);Check(GX<BYTE>(1024)==0&&setters==1,"identical native request legitimately needs no resize");
    Reset();GX<int>(1048)=GX<int>(1028)=2;Apply(432);Check(GX<BYTE>(1024)==0,"already maximized identical request is a native no-op");
}
void TestArguments() {
    for(double v:{-1.0,0.0,639.0,7681.0,640.5,std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()}) {
        Reset();Check(Apply(431,v,720).code==1&&!locks&&!setters,"invalid width before game access");
    }
    for(double v:{-1.0,0.0,359.0,4321.0,360.5,std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()}) {
        Reset();Check(Apply(431,1280,v).code==1&&!locks&&!setters,"invalid height before game access");
    }
    Reset();TrainerResult result{};Check(!WindowDisplayHandle(Context(),430,nullptr,result)&&!WindowDisplayHandle(Context(),433,nullptr,result)&&!locks,"unowned slots not handled");
    Check(WindowDisplayHandle(Context(),431,nullptr,result)&&result.code==1&&!locks,"null size arguments rejected");
    Check(WindowDisplayHandle(Context(),432,nullptr,result)&&result.code==0&&lastMode==2,"maximize has no arguments");
}
void TestLifetimes() {
    const Mutation mutations[]={
        []{g_disabled=1;},[]{g_gameThread=0;},[]{++g_gameThread;},[]{g_shared=nullptr;},[]{shared.hostHeartbeat=0;},[]{fakeNow+=5001;},
        []{At<int>(display_preview::EpochRva)=0;},[]{At<int>(display_preview::EpochRva)=-1;},[]{GX<uintptr_t>(0)+=8;},
        []{GX<uintptr_t>(736)=0;},[]{GX<uintptr_t>(1144)=0;},[]{GX<HANDLE>(784)=nullptr;},[]{GX<HANDLE>(792)=nullptr;},
        []{GX<HANDLE>(792)=appHandle;},[]{timingId=appId;},[]{timingId=0;},[]{++timingProcess;},[]{threadAlive=false;},
        []{GX<int>(808)=1;},[]{At<int>(AppAddress+4752)=0;},[]{GX<uintptr_t>(1000)+=8;},[]{At<uintptr_t>(AppAddress)+=8;},[]{g_selectedVtable=0;},
        []{display_preview::testRuntimeAvailable=false;},[]{At<uintptr_t>(0x57B458)+=1;},[]{At<uintptr_t>(0x57B450)+=1;},
        []{window_display::testSystemRuntime=false;},[]{At<uintptr_t>(0x57B2D8)+=1;},[]{At<uintptr_t>(0x57B2D0)+=1;},
        []{At<uint64_t>(0x7591F8)=0;},[]{At<uint64_t>(0x7591F8)=0x1000000000000ull;},
        []{GX<HWND>(1008)=nullptr;},[]{windowValid=false;},[]{windowThread=0;},[]{++windowProcess;},
        []{At<float>(0x5A9CBC)=8;},[]{At<float>(0x623BC4)=15;},[]{At<float>(0x5A9C9C)=0.5f;}
    };
    for(auto m:mutations) {
        Reset();m();Rejected("invalid initial lease rejected without native setter");Check(!locks,"initial guard has no locks");
        Reset();onLock=m;Rejected("lease lost at outer acquisition rejected with captured unlock");Check(locks==1&&unlocks==1&&!tries,"second lease before resize CS");
        Reset();onInner=m;Rejected("lease lost at resize acquisition rejected with captured unlocks");Check(locks==1&&unlocks==1&&tries==1&&leaves==1,"third lease inside both locks");
    }
    for(auto m:{+[]{GX<uintptr_t>(736)+=8;},+[]{GX<uintptr_t>(1144)+=8;},+[]{++windowThread;}}) {
        Reset();onLock=m;Rejected("replacement valid identity differs from captured lease");
        Reset();onInner=m;Rejected("replacement under resize lock differs from captured lease");
    }
    for(const auto range: {std::pair<uintptr_t,SIZE_T>{ObjectRva+1024,20},{ObjectRva+31432,40},{0x57B2D0,16},{0x5A9CBC,4},{0x7591F8,8}}) {
        Reset();denied=g_base+range.first;deniedSize=range.second;Rejected("unreadable dependency");
    }
    for(SIZE_T offset:{SIZE_T(1024),SIZE_T(31432)}) {
        Reset();deniedWrite=g_base+ObjectRva+offset;deniedWriteSize=1;Rejected("nonwritable request or synchronization storage");
    }
    Reset();fakeNow=3;shared.hostHeartbeat=0xfffffffeu;Check(Apply().code==0,"heartbeat wrap remains fresh");
    Reset();windowThread=appId;Check(Apply().code==0,"window thread may equal application thread");
}
void TestPins() {
    for(unsigned i=0;i<sizeof(window_display::SetterCode);++i) { Reset();Corrupt(0x124FE0+i);Rejected("every setter byte pinned"); }
    for(unsigned i=0;i<sizeof(window_display::CookieCode);++i) { Reset();Corrupt(0x439A60+i);Rejected("every normal compiler-cookie helper byte pinned"); }
    Reset();onInner=+[]{Corrupt(0x124FE0+sizeof(window_display::SetterCode)-1);};Rejected("pin rechecked immediately before dispatch");
}
void TestStates() {
    const Mutation invalid[]={
        []{GX<BYTE>(1024)=2;},[]{GX<BYTE>(1044)=2;},[]{GX<BYTE>(1025)=2;},[]{GX<BYTE>(1045)=2;},[]{GX<BYTE>(1026)=2;},[]{GX<BYTE>(1046)=2;},
        []{GX<int>(1028)=-1;},[]{GX<int>(1028)=3;},[]{GX<int>(1048)=-1;},[]{GX<int>(1048)=3;},
        []{GX<float>(1040)=-1;},[]{GX<float>(1040)=61;},[]{GX<float>(1040)=std::numeric_limits<float>::infinity();},[]{GX<float>(1040)=std::numeric_limits<float>::quiet_NaN();},
        []{GX<int>(1072)=-1;},[]{GX<int>(1072)=4;},[]{GX<int>(8)=0;},[]{GX<int>(12)=16385;},
        []{GX<int>(1032)=0;},[]{GX<int>(1036)=16385;},[]{GX<int>(1052)=0;},[]{GX<int>(1056)=16385;}
    };
    for(auto m:invalid) { Reset();m();Rejected("invalid state gives no queue call");WindowDisplaySnapshot(Context());Check(!published,"invalid snapshot omitted, not reported as zero"); }
    for(auto m:{+[]{GX<BYTE>(1024)=1;},+[]{GX<BYTE>(1044)=1;},+[]{GX<float>(1040)=60;},+[]{GX<float>(1040)=0.5f;},+[]{GX<int>(1072)=1;},+[]{GX<int>(1072)=2;},+[]{GX<int>(1072)=3;},+[]{GX<int>(1064)=1;}}) {
        Reset();m();Rejected("pending native action is not replaced");WindowDisplaySnapshot(Context());Check(Has(436)&&shared.values[436]==1,"pending state remains observable");
        Reset();onInner=m;Rejected("pending inserted immediately before final check is not overwritten");
    }
    Reset();tryBusy=true;Rejected("busy resize lock causes no blocking call");Check(tries==1&&!leaves&&unlocks==1,"busy lock never released as if acquired");
    Reset();lockResult=1;Rejected("failed presentation lock causes no inner acquisition");Check(!unlocks&&!tries,"unacquired mutex not unlocked");
}
void TestFaults() {
    for(int fault:{1,2,3}) {
        Reset();setterFault=fault;const auto r=Apply();Check(r.code==2&&setters==1&&unlocks==1&&!outerHeld,"native dispatch fault never retried and outer mutex released");
        Check(depth==(fault==2?1:0),"only definitely-owned resize recursion released after native fault");
        Check(window_display::faulted&&display_preview::faulted&&renderer_diagnostics::faulted,"setter fault disables every shared renderer component");
        const auto oldLocks=locks;Apply();WindowDisplaySnapshot(Context());DisplaySnapshot(Context());RendererDiagnosticsSnapshot(Context());
        Check(locks==oldLocks&&setters==1&&!published,"no second user reaches damaged native locks");
        WindowDisplayReset(Context());Check(window_display::faulted,"reset cannot clear fatal latch");
    }
    const Mutation faults[]={[]{fakeUnlockResult=1;},[]{throwUnlock=true;},[]{throwLeave=true;},[]{throwTry=true;},[]{throwLock=true;}};
    for(auto m:faults) {
        Reset();m();const auto r=Apply();Check(r.code==2&&window_display::faulted&&display_preview::faulted&&renderer_diagnostics::faulted,"every uncertain synchronization failure latches restart");
        const auto oldLocks=locks;Apply();WindowDisplaySnapshot(Context());Check(locks==oldLocks,"uncertain lock failure not retried");
        Reset();m();WindowDisplaySnapshot(Context());Check(!published&&window_display::faulted&&display_preview::faulted&&renderer_diagnostics::faulted,"snapshot synchronization failure does not publish partial data");
    }
    Reset();WindowDisplayFailureReset(Context());Check(window_display::faulted&&display_preview::faulted&&renderer_diagnostics::faulted,"bridge failure reset shares permanent fault");
    Reset();display_preview::faulted=true;Check(Apply().code==2&&!locks,"display fault bars window actions");
    Reset();renderer_diagnostics::faulted=true;Check(Apply().code==2&&!locks,"diagnostics fault bars window actions");
}
void TestSnapshots() {
    Reset();WindowDisplaySnapshot(Context());Check(published==6&&!setters&&locks==1&&tries==1&&leaves==1&&unlocks==1,"six copied readouts without native setter");
    const double expected[]={1920,1080,0,0,1280,720};
    for(unsigned i=0;i<6;++i)Check(Has(433+i)&&shared.values[433+i]==expected[i],"actual versus requested dimensions and native mode units");
    for(int mode=0;mode<=2;++mode) { Reset();GX<int>(1048)=mode;GX<BYTE>(1046)=mode==1;WindowDisplaySnapshot(Context());Check(Has(435)&&shared.values[435]==mode,"all native observed modes supported"); }
    Reset();tryBusy=true;WindowDisplaySnapshot(Context());Check(!published&&!window_display::faulted,"temporarily busy state is absent without fault");
    Reset();WindowDisplayCapabilities();for(unsigned s=0;s<512;++s)Check(bool(shared.supported[s/64]&(uint64_t(1)<<(s%64)))==(s>=431&&s<=438),"only allocated capability slots");
    Reset();Apply();const int request=GX<int>(1032);const auto calls=setters;WindowDisplayReset(Context());Check(GX<int>(1032)==request&&setters==calls&&!window_display::faulted,"disconnect leaves queued request untouched, no automatic restore");
}
#endif
}
#ifndef WINDOW_DISPLAY_PRODUCTION_COMPILE
int main() {
    setvbuf(stdout,nullptr,_IONBF,0);
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,ImageSize,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(!g_base){printf("Fixture allocation failed\n");return 2;}
    TestNativeActions();TestArguments();TestLifetimes();TestPins();TestStates();TestFaults();TestSnapshots();
    printf("Window display checks: %u; failures: %u\n",checks,failures);
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
#endif
