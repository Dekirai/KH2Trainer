#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdint.h>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <initializer_list>
#include <limits>
#include <vector>
namespace {
struct TrainerContext { uintptr_t base,player,status; bool sceneReady; };
struct TrainerResult { LONG code; const wchar_t* text; };
struct Shared { DWORD hostHeartbeat; double values[512]; uint64_t valid[8],supported[8]; } shared{};
uintptr_t g_base=0,g_selectedVtable=0; DWORD g_gameThread=0; LONG g_disabled=0;
Shared* g_shared=&shared;
bool IsInteger(double v,double lo,double hi) { return std::isfinite(v)&&v>=lo&&v<=hi&&floor(v)==v; }
#ifdef AA_PRODUCTION_COMPILE
bool Readable(const void*,SIZE_T) { return false; }
bool Writable(const void*,SIZE_T) { return false; }
void SnapshotValue(unsigned,double) {}
void SupportCapability(unsigned) {}
#include "../../src/KH2Trainer.Bridge/DisplayFeatures.inl"
#include "../../src/KH2Trainer.Bridge/RendererAaFeatures.inl"
#else
#define KH2_DISPLAY_TESTS
#define KH2_RENDERER_AA_TESTS
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
DWORD creationSerial=1; bool creationWorks=true;
BOOL Times(HANDLE h,FILETIME* creation,FILETIME*,FILETIME*,FILETIME*) { if(!creationWorks || (h!=appHandle&&h!=timingHandle))return FALSE;*creation={creationSerial+(h==timingHandle?1u:0u),0};return TRUE; }
void SnapshotValue(unsigned slot,double value) {
    Check(!outerHeld&&!innerHeld,"publish only after both releases");++published;
    shared.values[slot]=value;shared.valid[slot/64]|=uint64_t(1)<<(slot%64);
}
void SupportCapability(unsigned slot) { shared.supported[slot/64]|=uint64_t(1)<<(slot%64); }
#define GetTickCount Now
#define GetThreadId ThreadId
#define GetProcessIdOfThread ProcessIdOfThread
#define GetExitCodeThread ExitCodeThread
#define GetThreadTimes Times
#define QueryPerformanceFrequency ClockFrequency
#define QueryPerformanceCounter ClockNow
#define TryEnterCriticalSection TryHistory
#define LeaveCriticalSection LeaveHistory
#include "../../src/KH2Trainer.Bridge/DisplayFeatures.inl"
#include "../../src/KH2Trainer.Bridge/RendererAaFeatures.inl"
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
unsigned allocations=0,frees=0,protects=0,flushes=0,swaps=0,originalCalls=0;
unsigned failProtect=0,failFlush=0;
unsigned exceptionProtect=0,exceptionFlush=0,exceptionCas=0;
bool afterProtectException=false,afterCasException=false;
bool permit=true,pin=true,denyAlloc=false,denyQuery=false,foreignCas=false,throwCas=false;
bool failRestoreAlways=false,throwNative=false;
DWORD imageProtection=PAGE_EXECUTE_READ;
int nativeResult=2;
std::vector<void*> owned;
Mutation onFlush=nullptr;
void* seenHistory=nullptr;int seenInterval=0,seenCurrent=0,seenMin=0,seenMax=0;float seenBudget=0;
int __fastcall NativeDecision(void* h,int interval,float budget,int current,int minimum,int maximum) {
    ++originalCalls;seenHistory=h;seenInterval=interval;seenBudget=budget;seenCurrent=current;seenMin=minimum;seenMax=maximum;
    if(throwNative)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    return nativeResult;
}
SIZE_T Query(const void* p,MEMORY_BASIC_INFORMATION* m,SIZE_T n) {
    if(denyQuery)return 0;
    const SIZE_T got=VirtualQuery(p,m,n);
    if(got && Inside(p,5)){m->Type=MEM_IMAGE;m->AllocationBase=reinterpret_cast<void*>(g_base);m->Protect=imageProtection;}
    return got;
}
LPVOID Alloc(LPVOID p,SIZE_T n,DWORD type,DWORD prot) {
    ++allocations;Check(outerHeld&&type==(MEM_COMMIT|MEM_RESERVE)&&prot==PAGE_READWRITE,"relay starts RW under native lock");
    if(denyAlloc)return nullptr;void* q=VirtualAlloc(p,n,type,prot);if(q)owned.push_back(q);return q;
}
BOOL Free(LPVOID p,SIZE_T n,DWORD type) {
    ++frees;Check(!renderer_aa::exposed,"production never frees an exposed relay");
    for(auto& q:owned)if(q==p)q=nullptr;
    return VirtualFree(p,n,type);
}
BOOL Protection(LPVOID p,SIZE_T n,DWORD prot,PDWORD old) {
    ++protects;Check(outerHeld,"all code protection changes at native safe point");
    if(protects==exceptionProtect&&!afterProtectException)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    if(protects==failProtect || (failRestoreAlways&&Inside(p,5)&&prot==PAGE_EXECUTE_READ))return FALSE;
    if(Inside(p,5)) { Check(n==5,"only target code page affected");*old=imageProtection;imageProtection=prot;
        if(protects==exceptionProtect)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);return TRUE; }
    Check(prot==PAGE_EXECUTE_READ,"relay never RWX");const BOOL ok=VirtualProtect(p,n,prot,old);
    if(protects==exceptionProtect)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);return ok;
}
BOOL Cache(HANDLE process,LPCVOID p,SIZE_T n) {
    ++flushes;Check(process==GetCurrentProcess()&&outerHeld,"code flush under quiescence");
    if(onFlush)onFlush();
    if(flushes==exceptionFlush)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    if(flushes==failFlush)return FALSE;
    return FlushInstructionCache(process,p,n);
}
LONG Swap(volatile LONG* p,LONG value,LONG expected) {
    ++swaps;Check(outerHeld&&imageProtection==PAGE_EXECUTE_READWRITE && reinterpret_cast<uintptr_t>(p)==g_base+renderer_aa::SiteRva+1,"operand CAS only inside writable quiescent image");
    if(throwCas || (swaps==exceptionCas&&!afterCasException))RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    if(foreignCas){*p=0x12345678;return 0x12345678;}
    const LONG previous=InterlockedCompareExchange(p,value,expected);
    if(swaps==exceptionCas)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);return previous;
}
void Reset() {
    for(void* p:owned)if(p)VirtualFree(p,0,MEM_RELEASE);owned.clear();
    memset(reinterpret_cast<void*>(g_base),0,ImageSize);shared={};g_shared=&shared;shared.hostHeartbeat=fakeNow=100000;
    g_disabled=0;g_gameThread=appId=GetCurrentThreadId();timingId=appId+1;timingProcess=GetCurrentProcessId();
    fakeTimingExit=STILL_ACTIVE;exitQueryWorks=true;g_selectedVtable=g_base+0x100000;creationWorks=true;creationSerial=1;
    display_preview::faulted=false;renderer_aa::mode=renderer_aa::faulted=0;renderer_aa::original=nullptr;
    renderer_aa::relay=nullptr;renderer_aa::relayRel=0;renderer_aa::installed=renderer_aa::exposed=renderer_aa::lifetimeBound=false;
    renderer_aa::decisionValid=false;renderer_aa::requested=renderer_aa::lastNative=renderer_aa::lastChosen=0;
    denied=deniedWrite=throwRead=0;deniedSize=deniedWriteSize=0;throwUnlock=outerHeld=innerHeld=false;
    locks=unlocks=published=allocations=frees=protects=flushes=swaps=originalCalls=0;fakeLockResult=fakeUnlockResult=0;
    failProtect=failFlush=exceptionProtect=exceptionFlush=exceptionCas=0;afterProtectException=afterCasException=false;imageProtection=PAGE_EXECUTE_READ;permit=pin=true;
    denyAlloc=denyQuery=foreignCas=throwCas=failRestoreAlways=throwNative=false;nativeResult=2;onLock=onInner=onFlush=nullptr;
    GX<uintptr_t>(0)=g_base+display_preview::VtableRva;GX<uintptr_t>(736)=g_base+0x200000;GX<uintptr_t>(1144)=g_base+0x210000;
    GX<HANDLE>(784)=appHandle;GX<HANDLE>(792)=timingHandle;GX<int>(808)=0;GX<uintptr_t>(1000)=g_base+AppAddress;
    At<uintptr_t>(display_preview::AppRva)=g_base+AppAddress;At<uintptr_t>(AppAddress)=g_selectedVtable;At<int>(AppAddress+4752)=-1;
    At<int>(display_preview::EpochRva)=-100;
    display_preview::testLock=MockLock;display_preview::testUnlock=MockUnlock;display_preview::testRuntimeAvailable=true;
    At<uintptr_t>(0x57B458)=reinterpret_cast<uintptr_t>(MockLock);At<uintptr_t>(0x57B450)=reinterpret_cast<uintptr_t>(MockUnlock);
    Seed(0x5061A0,display_preview::BrightnessCode);Seed(0x5061F0,display_preview::ColorCode);Seed(0x1268C0,display_preview::GammaCode);
    Seed(0x125D00,display_preview::ColorSetterCode);Seed(0x11C150,display_preview::GetterCode);
    Seed(0x43AD04,display_preview::LockCode);Seed(0x43AD0A,display_preview::UnlockCode);
    At<float>(0x5B532C)=50;At<float>(0x5A9CB4)=2.2f;
    for(const auto& s:renderer_aa::Signatures)memcpy(reinterpret_cast<void*>(g_base+s.rva),s.data,s.size);
    GX<unsigned>(1108)=8;GX<int>(30556)=2;GX<int>(44)=1;GX<float>(856)=16.0f;
    renderer_aa::platform={Query,Alloc,Free,Protection,Cache,[]{return permit;},[]{return pin;},Swap};
    renderer_aa::testOriginal=NativeDecision;renderer_aa::testCaller=g_base+renderer_aa::ReturnRva;
}
TrainerContext Context(){return {g_base,0,0,false};}
TrainerResult Apply(int mode=1,int samples=8) {
    double a[8]={static_cast<double>(mode),static_cast<double>(samples)};TrainerResult r{};
    Check(RendererAaHandle(Context(),447,a,r),"apply command recognized");return r;
}
bool Has(unsigned slot){return (shared.valid[slot/64]&(uint64_t(1)<<(slot%64)))!=0;}
int Invoke(int min=0,int max=3) {
    return renderer_aa::Policy(reinterpret_cast<void*>(g_base+ObjectRva+30568),1,16.0f,GX<int>(30556),min,max);
}
bool CatchInvoke() { __try{Invoke();}__except(EXCEPTION_EXECUTE_HANDLER){return true;}return false; }
bool CatchRelay() { __try{reinterpret_cast<renderer_aa::DecisionFn>(renderer_aa::relay)(nullptr,1,16.0f,2,0,3);}__except(EXCEPTION_EXECUTE_HANDLER){return true;}return false; }
bool CatchApply() { __try{Apply();}__except(EXCEPTION_EXECUTE_HANDLER){return true;}return false; }
void TestNormal() {
    Reset();Check(Apply().code==0,"install fixed8 succeeds");
    Check(locks==1&&unlocks==1&&!outerHeld&&protects==3&&flushes==2&&swaps==1,"single transaction with restored page and two cache flushes");
    Check(imageProtection==PAGE_EXECUTE_READ&&renderer_aa::exposed&&renderer_aa::installed,"resident publication tracked");
    Check(At<BYTE>(renderer_aa::SiteRva)==0xE8&&At<LONG>(renderer_aa::SiteRva+1)==renderer_aa::relayRel,"only aligned operand changes");
    Check(Invoke()==3&&originalCalls==1&&seenInterval==1&&seenBudget==16&&seenCurrent==2&&seenMin==0&&seenMax==3,"native once with all mixed register and stack args");
    const auto p=static_cast<const BYTE*>(renderer_aa::relay);uintptr_t destination=0;memcpy(&destination,p+6,8);
    Check(p[0]==0xFF&&p[1]==0x25&&!p[2]&&!p[3]&&!p[4]&&!p[5]&&destination==reinterpret_cast<uintptr_t>(&renderer_aa::Policy),"14-byte immutable leaf tailjump");
    MEMORY_BASIC_INFORMATION mb{};VirtualQuery(p,&mb,sizeof(mb));Check(mb.Protect==PAGE_EXECUTE_READ,"actual relay RX");
    const auto relayCall=reinterpret_cast<renderer_aa::DecisionFn>(renderer_aa::relay);
    Check(relayCall(reinterpret_cast<void*>(g_base+ObjectRva+30568),1,16.0f,2,0,3)==3&&originalCalls==2,"actual RX relay preserves six-argument call ABI");
    DWORD64 image=0;Check(RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(&renderer_aa::Policy),&image,nullptr)!=nullptr,"compiled nonleaf wrapper has PE unwind entry");
    Check(RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(p),&image,nullptr)==nullptr,"leaf relay intentionally has no dynamic unwind record");
    throwNative=true;Check(CatchRelay()&&originalCalls==3,"native exception unwinds through real leaf relay and compiled wrapper exactly once");throwNative=false;
    RendererAaSnapshot(Context());Check(Has(449)&&shared.values[449]==1&&Has(450)&&shared.values[450]==8&&shared.values[451]==8&&shared.values[452]==4,"distinct requested capability and actual samples");
    Check(shared.values[453]==4&&shared.values[454]==8&&shared.values[455]==1,"last native and policy decision explicit");
    const unsigned before=swaps;RendererAaReset(Context());Check(Invoke()==2&&originalCalls==4&&!renderer_aa::mode&&swaps==before&&!frees,"reset is resident native pass-through");
    Check(Apply(2,2).code==0&&swaps==before&&Invoke()==1,"existing resident hook can receive maximum2 policy");
    RendererAaCapabilities();for(unsigned i=0;i<512;++i)Check(bool(shared.supported[i/64]&(uint64_t(1)<<(i%64)))==(i>=447&&i<=455),"exact nine capability slots");
}
void TestPolicyGrid() {
    Reset();Check(Apply().code==0,"grid installed");
    for(int mode=1;mode<=2;++mode)for(int req=0;req<4;++req)for(int cap=0;cap<4;++cap)
    for(int current=0;current<4;++current)for(int proposal=0;proposal<4;++proposal)for(int vendor=0;vendor<2;++vendor) {
        GX<unsigned>(1108)=1u<<cap;GX<BYTE>(1224)=static_cast<BYTE>(vendor);GX<int>(30556)=current;
        renderer_aa::requested=req;renderer_aa::mode=mode;nativeResult=proposal;const int max=vendor?0:cap;
        const int limit=req<max?req:max;const int expected=mode==2&&proposal<limit?proposal:limit;
        const auto calls=originalCalls;Check(Invoke(0,max)==expected&&originalCalls==calls+1,"all fixed/capped/current/proposal/cap/vendor combinations call original once");
    }
}
void TestGuards() {
    const Mutation invalid[]={[]{g_shared=nullptr;},[]{shared.hostHeartbeat=0;},[]{fakeNow+=5001;},[]{g_disabled=1;},
        []{display_preview::faulted=true;},[]{At<int>(display_preview::EpochRva)=0;},[]{At<int>(display_preview::EpochRva)=-1;},
        []{GX<uintptr_t>(736)=0;},[]{GX<uintptr_t>(1144)=0;},[]{GX<int>(808)=1;},[]{At<int>(AppAddress+4752)=0;},
        []{GX<HANDLE>(784)=nullptr;},[]{GX<HANDLE>(792)=nullptr;},[]{GX<HANDLE>(792)=appHandle;},[]{++appId;},
        []{timingId=0;},[]{timingId=appId;},[]{timingProcess=0;},[]{fakeTimingExit=0;},[]{exitQueryWorks=false;},
        []{GX<uintptr_t>(1000)+=8;},[]{At<uintptr_t>(AppAddress)+=8;},[]{At<BYTE>(0x43AD04)^=1;},
        []{display_preview::testRuntimeAvailable=false;},[]{creationWorks=false;},[]{GX<unsigned>(1108)=3;},[]{GX<int>(30556)=4;},
        []{GX<int>(22944)=1;},[]{GX<int>(1072)=1;}};
    for(auto f:invalid){Reset();f();Check(Apply().code!=0&&!swaps&&!renderer_aa::mode&&unlocks==locks,"unsafe start rejected without publication");}
    for(auto f:invalid){Reset();onLock=f;Check(Apply().code!=0&&!swaps&&!outerHeld&&unlocks==locks,"fresh postlock validation rejects mutation");}
    Reset();Check(Apply().code==0,"guard active");fakeNow+=5001;Check(Invoke()==2&&!renderer_aa::mode&&!renderer_aa::faulted,"expired host disables without permanent fault");
    shared.hostHeartbeat=fakeNow;Check(Apply().code==0,"explicit re-enable after reconnect");++creationSerial;RendererAaTick(Context());Check(renderer_aa::faulted&&!renderer_aa::mode,"handle reuse distinguished by creation time");
    Reset();Apply();++At<int>(display_preview::EpochRva);RendererAaTick(Context());Check(renderer_aa::faulted&&!renderer_aa::mode&&Apply().code!=0,"changed epoch permanently invalidates lease");
    Reset();Apply();GX<uintptr_t>(736)+=8;renderer_aa::mode=0;RendererAaTick(Context());Check(renderer_aa::faulted,"disabled resident still invalidates replaced device");
    Reset();Apply();GX<BYTE>(1024)=1;Check(Invoke()==2&&renderer_aa::mode==1&&!renderer_aa::decisionValid,"pending resize bypass remains transient");GX<BYTE>(1024)=0;Check(Invoke()==3,"next normal decision resumes same lifetime policy");
    Reset();Apply();renderer_aa::testCaller++;Check(Invoke()==2&&!renderer_aa::mode,"unknown caller pass-through disables policy");
    Reset();Apply();++g_gameThread;Check(Invoke()==2&&renderer_aa::mode==1,"foreign thread original-only without policy mutation");
    Reset();TrainerResult r{};Check(RendererAaHandle(Context(),447,nullptr,r)&&r.code!=0&&!locks,"null arguments rejected");
    for(double a:{0.0,3.0,1.5,std::numeric_limits<double>::quiet_NaN()}){Reset();double args[8]={a,4};RendererAaHandle(Context(),447,args,r);Check(r.code!=0&&!locks,"invalid mode rejected");}
    for(double a:{0.0,3.0,16.0,std::numeric_limits<double>::infinity()}){Reset();double args[8]={1,a};RendererAaHandle(Context(),447,args,r);Check(r.code!=0&&!locks,"invalid samples rejected");}
    Reset();RendererAaSnapshot(Context());Check(!Has(450)&&!Has(453)&&!Has(454)&&Has(451),"unobserved decision is invalid rather than invented zero");
    Reset();Apply();throwNative=true;Check(CatchInvoke()&&originalCalls==1&&!renderer_aa::faulted,"native exception propagates and original is never retried");
    throwNative=false;throwRead=g_base+display_preview::EpochRva;outerHeld=true;Check(Invoke()==2&&originalCalls==2&&renderer_aa::faulted,"only post-native own read failure is swallowed into pass-through");outerHeld=false;
    Reset();for(const auto& sig:renderer_aa::Signatures){At<BYTE>(sig.rva)^=1;Check(Apply().code!=0&&!swaps,"each critical complete native body pinned");At<BYTE>(sig.rva)^=1;}
}
void TestTransactions() {
    Reset();fakeLockResult=1;Check(Apply().code!=0&&locks==1&&!unlocks&&!allocations,"failed acquisition never releases unowned mutex");
    Reset();fakeUnlockResult=1;Check(Apply().code!=0&&renderer_aa::faulted&&display_preview::faulted&&!renderer_aa::mode,"unlock return failure latches both clients");
    Reset();throwUnlock=true;Check(CatchApply()&&renderer_aa::faulted&&display_preview::faulted&&unlocks==1,"unlock exception still permanently latches");
    for(unsigned phase=1;phase<=3;++phase){Reset();failProtect=phase;Check(Apply().code!=0&&!renderer_aa::mode&&!outerHeld,"each protection phase failure fails closed");
        Check(At<LONG>(renderer_aa::SiteRva+1)==renderer_aa::OriginalRel,"protection error leaves or rolls back original operand");
        Check(imageProtection==PAGE_EXECUTE_READ,"protection failure restores original RX where OS succeeds");
        if(phase==3)Check(renderer_aa::faulted&&renderer_aa::exposed&&!frees,"postpublication restore failure retains relay and faults even after successful retry");}
    for(unsigned phase=1;phase<=2;++phase){Reset();failFlush=phase;Check(Apply().code!=0&&!renderer_aa::mode&&!outerHeld,"relay/image cache failure fails closed");
        Check(At<LONG>(renderer_aa::SiteRva+1)==renderer_aa::OriginalRel&&imageProtection==PAGE_EXECUTE_READ,"cache error preserves or owner-rolls-back operand");
        if(phase==2){const auto count=allocations;failFlush=0;Check(Apply().code!=0&&allocations==count&&renderer_aa::faulted&&!frees,"postpublication cache failure never retries or frees reachable relay");}}
    Reset();foreignCas=true;Check(Apply().code!=0&&At<LONG>(renderer_aa::SiteRva+1)==0x12345678&&renderer_aa::faulted,"CAS loses race without overwriting foreign displacement");
    Reset();failFlush=2;onFlush=[]{if(flushes==2)At<LONG>(renderer_aa::SiteRva+1)=123456;};Check(Apply().code!=0&&At<LONG>(renderer_aa::SiteRva+1)==123456,"rollback preserves a later foreign hook");
    Reset();failRestoreAlways=true;Check(Apply().code!=0&&renderer_aa::faulted&&imageProtection==PAGE_EXECUTE_READWRITE,"persistent OS protection failure is exposed as restart-required fault");
    failRestoreAlways=false;Check(Apply().code!=0&&renderer_aa::faulted,"partial failure cannot be retried by command");
    Reset();throwCas=true;Check(Apply().code!=0&&renderer_aa::faulted&&renderer_aa::exposed&&imageProtection==PAGE_EXECUTE_READ&&!frees&&!outerHeld,"unexpected publication and rollback exceptions preserve relay and cleanup");
    for(unsigned i=1;i<=3;++i)for(int after=0;after<2;++after){Reset();exceptionProtect=i;afterProtectException=after!=0;
        Check(Apply().code!=0&&renderer_aa::faulted&&!renderer_aa::mode&&!outerHeld&&imageProtection==PAGE_EXECUTE_READ,"protection SEH before or after write cannot skip final restore");}
    for(unsigned i=1;i<=3;++i){Reset();exceptionFlush=i;if(i==3)failFlush=2;
        Check(Apply().code!=0&&renderer_aa::faulted&&!renderer_aa::mode&&!outerHeld&&imageProtection==PAGE_EXECUTE_READ,"cache SEH including rollback cannot skip image restoration");}
    for(unsigned i=1;i<=2;++i)for(int after=0;after<2;++after){Reset();exceptionCas=i;afterCasException=after!=0;if(i==2)failFlush=2;
        Check(Apply().code!=0&&renderer_aa::faulted&&!renderer_aa::mode&&!outerHeld&&imageProtection==PAGE_EXECUTE_READ,"CAS SEH including uncertain committed write and rollback still restores image");}
    Reset();Apply();GX<unsigned>(1108)=3;Check(Apply().code!=0&&!renderer_aa::mode,"valid replacement request disables previous mode even if later preparation fails");
    Reset();onLock=[]{++creationSerial;};Check(Apply().code!=0&&!swaps,"creation time changed while waiting rejects first installation");
    Reset();onLock=[]{++At<int>(display_preview::EpochRva);};Check(Apply().code!=0&&!swaps,"initialization guard changed while waiting rejects first installation");
    for(int which=0;which<3;++which){Reset();if(which==0)permit=false;else if(which==1)pin=false;else denyQuery=true;
        Check(Apply().code!=0&&!swaps&&!renderer_aa::mode,"mitigation/pin/query failure rejects installation");}
    Reset();imageProtection=PAGE_EXECUTE_READWRITE;Check(Apply().code!=0&&!allocations,"preexisting writable code page rejected");
    LONG result=0;Check(renderer_aa::Rel32(0x100000000ull,0x17FFFFFFFull,result)&&result==2147483647,"rel32 positive edge");
    Check(renderer_aa::Rel32(0x100000000ull,0x80000000ull,result)&&result==(-2147483647L-1),"rel32 negative edge");
    Check(!renderer_aa::Rel32(0x100000000ull,0x180000000ull,result)&&!renderer_aa::Rel32(0x100000000ull,0x7FFFFFFFull,result),"rel32 out-of-range rejected before narrowing");
}
void TestExecutedCallsite() {
    Reset();Check(Apply().code==0,"machine-code fixture installs real aligned operand");RendererAaReset(Context());
    // Synthetic caller only, never the game body: copy two caller stack args,
    // CALL the genuinely patched E8 at its expected address, then return.
    // No exception is raised through this test stub (it has no unwind table).
    constexpr BYTE prefix[]={0x48,0x83,0xEC,0x38,0x8B,0x44,0x24,0x60,0x89,0x44,0x24,0x20,0x8B,0x44,0x24,0x68,0x89,0x44,0x24,0x28};
    constexpr BYTE suffix[]={0x48,0x83,0xC4,0x38,0xC3};
    const uintptr_t begin=g_base+renderer_aa::SiteRva-sizeof(prefix);
    memcpy(reinterpret_cast<void*>(begin),prefix,sizeof(prefix));memcpy(reinterpret_cast<void*>(g_base+renderer_aa::ReturnRva),suffix,sizeof(suffix));
    DWORD old=0;Check(VirtualProtect(reinterpret_cast<void*>(begin),64,PAGE_EXECUTE_READ,&old)!=FALSE,"synthetic callsite RX before execution");
    Check(FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(begin),64)!=FALSE,"actual patched callsite flushed");
    nativeResult=42;auto call=reinterpret_cast<renderer_aa::DecisionFn>(begin);
    Check(call(reinterpret_cast<void*>(uintptr_t(0x76543210)),3,7.25f,11,12,13)==42&&originalCalls==1&&
        seenHistory==reinterpret_cast<void*>(uintptr_t(0x76543210))&&seenInterval==3&&seenBudget==7.25f&&seenCurrent==11&&seenMin==12&&seenMax==13,
        "executed E8-rel32 to RX-relay to compiled-wrapper passes every ABI argument and return exactly once");
    Check(VirtualProtect(reinterpret_cast<void*>(begin),64,old,&old)!=FALSE,"synthetic fixture returns to writable teardown state");
}
int RunAll() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,ImageSize,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(!g_base)return 2;
    TestNormal();TestPolicyGrid();TestGuards();TestTransactions();TestExecutedCallsite();Reset();VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);
    printf("Renderer AA: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
#endif
}
#ifndef AA_PRODUCTION_COMPILE
int main(){return RunAll();}
#endif
