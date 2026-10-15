#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdint.h>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <initializer_list>
#include <limits>
#define KH2_DISPLAY_TESTS
namespace {
struct TrainerContext { uintptr_t base,player,status; bool sceneReady; };
struct TrainerResult { LONG code; const wchar_t* text; };
struct Shared { DWORD hostHeartbeat; double values[512]; uint64_t valid[8],supported[8]; } shared{};
uintptr_t g_base=0,g_selectedVtable=0; DWORD g_gameThread=0; LONG g_disabled=0;
Shared* g_shared=&shared;
constexpr SIZE_T ImageSize=0x900000;
DWORD fakeNow=100000,appId=0,timingId=0,timingProcess=0,fakeTimingExit=STILL_ACTIVE;
bool exitQueryWorks=true,throwTryLock=false,throwUnlock=false;
HANDLE appHandle=reinterpret_cast<HANDLE>(uintptr_t(0x1234));
HANDLE timingHandle=reinterpret_cast<HANDLE>(uintptr_t(0x5678));
DWORD Now() { return fakeNow; }
DWORD ThreadId(HANDLE h) { return h==appHandle?appId:(h==timingHandle?timingId:0); }
DWORD ProcessIdOfThread(HANDLE h) { return h==timingHandle?timingProcess:0; }
BOOL ExitCodeThread(HANDLE h,DWORD* result) { if(h!=timingHandle||!exitQueryWorks)return FALSE; *result=fakeTimingExit; return TRUE; }
#define GetTickCount Now
#define GetThreadId ThreadId
#define GetProcessIdOfThread ProcessIdOfThread
#define GetExitCodeThread ExitCodeThread
uintptr_t denied=0,deniedWrite=0; SIZE_T deniedSize=0,deniedWriteSize=0;
bool Inside(const void* p,SIZE_T n) {
    const auto a=reinterpret_cast<uintptr_t>(p);
    return a>=g_base && n<=ImageSize && a-g_base<=ImageSize-n;
}
bool Overlap(uintptr_t a,SIZE_T n,uintptr_t b,SIZE_T size) { return b && a<b+size && b<a+n; }
uintptr_t throwRead=0;
bool Readable(const void* p,SIZE_T n) {
    if(throwRead && reinterpret_cast<uintptr_t>(p)==throwRead)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    return Inside(p,n) && !Overlap(reinterpret_cast<uintptr_t>(p),n,denied,deniedSize);
}
bool Writable(const void* p,SIZE_T n) { return Readable(p,n) && !Overlap(reinterpret_cast<uintptr_t>(p),n,deniedWrite,deniedWriteSize); }
bool IsInteger(double v,double lo,double hi) { return std::isfinite(v)&&v>=lo&&v<=hi&&floor(v)==v; }
void SnapshotValue(unsigned slot,double value) { shared.values[slot]=value;shared.valid[slot/64]|=uint64_t(1)<<(slot%64); }
void SupportCapability(unsigned slot) { shared.supported[slot/64]|=uint64_t(1)<<(slot%64); }
#include "../../src/KH2Trainer.Bridge/DisplayFeatures.inl"
using namespace display_preview;
template<class T>T& At(uintptr_t rva) { return *reinterpret_cast<T*>(g_base+rva); }
template<class T>T& GX(SIZE_T offset) { return At<T>(ObjectRva+offset); }
unsigned checks=0,failures=0,locks=0,unlocks=0,brightCalls=0,colorCalls=0,blockingLocks=0,mutexTries=0;
int lockResult=0,unlockResult=0; bool held=false,allCallsLocked=true;
int16_t lastBrightness=0,lastType=0,lastSeverity=0;
unsigned raiseCall=0; bool changeSettingsInBrightness=false;
using Mutation=void(*)(); Mutation onLock=nullptr;
void Check(bool b,const char* label) { ++checks;if(!b){++failures;printf("FAIL %s\n",label);} }
int Acquire(void* p) {
    ++locks;Check(p==reinterpret_cast<void*>(g_base+ObjectRva+MutexOffset),"correct opaque mutex address");
    if(lockResult) return lockResult;
    Check(!held,"no recursive or unmatched acquisition");held=true;
    if(onLock)onLock();return 0;
}
int __cdecl MockLock(void* p) { ++blockingLocks;return Acquire(p); }
int __cdecl MockTryLock(void* p) {
    ++mutexTries;
    if(throwTryLock)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    return Acquire(p);
}
int __cdecl MockUnlock(void* p) {
    ++unlocks;Check(held&&p==reinterpret_cast<void*>(g_base+ObjectRva+MutexOffset),"matching mutex released exactly once");
    held=false;
    if(throwUnlock)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    return unlockResult;
}
void __fastcall MockBrightness(int16_t value) {
    allCallsLocked&=held;++brightCalls;lastBrightness=value;
    if(raiseCall==1)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    GX<float>(716)=static_cast<float>(value)/50;
    GX<float>(23360)=2.2f/(GX<float>(716)+2.2f);
    if(changeSettingsInBrightness) { At<int16_t>(FieldsRva+16)=3;At<int16_t>(FieldsRva+18)=10; }
}
void __fastcall MockColor(int16_t type,int16_t severity) {
    allCallsLocked&=held;++colorCalls;lastType=type;lastSeverity=severity;
    if(raiseCall==2)RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    GX<int>(23364)=type;GX<int>(23368)=severity;
}
template<SIZE_T N>void Seed(uintptr_t rva,const BYTE(&bytes)[N]) { memcpy(reinterpret_cast<void*>(g_base+rva),bytes,N); }
void Reset() {
    g_disabled=0;faulted=false;g_gameThread=appId=GetCurrentThreadId();timingId=appId+1;
    timingProcess=GetCurrentProcessId();fakeTimingExit=STILL_ACTIVE;exitQueryWorks=true;
    g_selectedVtable=g_base+0x100000;g_shared=&shared;shared={};shared.hostHeartbeat=fakeNow=100000;
    denied=deniedWrite=0;deniedSize=deniedWriteSize=0;
    locks=unlocks=brightCalls=colorCalls=blockingLocks=mutexTries=0;lockResult=unlockResult=0;held=false;allCallsLocked=true;
    throwTryLock=throwUnlock=false;throwRead=0;
    lastBrightness=lastType=lastSeverity=0;raiseCall=0;onLock=nullptr;changeSettingsInBrightness=false;
    GX<uintptr_t>(0)=g_base+VtableRva;GX<uintptr_t>(736)=g_base+0x200000;GX<uintptr_t>(1144)=g_base+0x210000;
    GX<HANDLE>(784)=appHandle;GX<HANDLE>(792)=timingHandle;GX<int>(808)=0;GX<uintptr_t>(1000)=g_base+0x220000;
    At<uintptr_t>(AppRva)=g_base+0x220000;At<uintptr_t>(0x220000)=g_selectedVtable;At<int>(0x220000+4752)=-1;
    At<int>(EpochRva)=-100;GX<float>(716)=0;GX<float>(23360)=1;GX<int>(23364)=1;GX<int>(23368)=5;
    testLock=MockLock;testUnlock=MockUnlock;testTryLock=MockTryLock;testBrightness=MockBrightness;testColor=MockColor;testRuntimeAvailable=true;
    At<uintptr_t>(0x57B458)=reinterpret_cast<uintptr_t>(testLock);At<uintptr_t>(0x57B450)=reinterpret_cast<uintptr_t>(testUnlock);
    Seed(0x5061A0,BrightnessCode);Seed(0x5061F0,ColorCode);Seed(0x1268C0,GammaCode);Seed(0x125D00,ColorSetterCode);
    Seed(0x11C150,GetterCode);Seed(0x43AD04,LockCode);Seed(0x43AD0A,UnlockCode);
    At<float>(0x5B532C)=50;At<float>(0x5A9CB4)=2.2f;
    memcpy(reinterpret_cast<void*>(g_base+0x715350),"SET-",4);At<unsigned>(0x715354)=8;At<unsigned>(0x715358)=508;
    At<int16_t>(FieldsRva+12)=-25;At<int16_t>(FieldsRva+16)=2;At<int16_t>(FieldsRva+18)=6;
}
TrainerContext Context() { return {g_base,0,0,false}; }
TrainerResult Execute(unsigned slot=304,double a=25,double b=5) {
    const auto c=Context();TrainerResult r{};const double args[8]{a,b};
    Check(DisplayHandle(c,slot,args,r),"owned command dispatched");return r;
}
bool Has(unsigned slot) { return (shared.valid[slot/64]&(uint64_t(1)<<(slot%64)))!=0; }
TrainerResult CompareColor(double operation,double expectedType,double expectedSeverity,double type,double severity) {
    TrainerResult result{}; const double args[8]{operation,expectedType,expectedSeverity,type,severity};
    Check(DisplayHandle(Context(),464,args,result),"conditional color command dispatched"); return result;
}
void Reject(const char* label,unsigned slot=304,double a=25,double b=5) {
    const auto r=Execute(slot,a,b);Check(r.code!=0&&brightCalls==0&&colorCalls==0&&locks==0&&unlocks==0,label);
}
void RejectAfterLock(Mutation mutation,const char* label) {
    Reset();onLock=mutation;const auto r=Execute();
    Check(r.code!=0&&brightCalls==0&&colorCalls==0&&locks==1&&unlocks==1&&!held,label);
}
bool CatchSetter(unsigned call,unsigned slot) {
    raiseCall=call;
    __try { Execute(slot); }
    __except(EXCEPTION_EXECUTE_HANDLER) { return true; }
    return false;
}
void TestInputs() {
    for(int value=-50;value<=50;++value) {
        Reset();const auto r=Execute(304,value);
        Check(!r.code&&brightCalls==1&&colorCalls==0&&lastBrightness==value&&allCallsLocked,"every native brightness level exactly once under mutex");
        DisplaySnapshot(Context());
        Check(Has(304)&&shared.values[304]==value,"brightness snapshot returns exact restorable integer including negative levels");
        Check(fabs(GX<float>(23360)-2.2/(2.2+value/50.0))<0.00001,"brightness uses native gamma relationship");
        DisplayTick(Context());DisplayReset(Context());Check(brightCalls==1&&colorCalls==0,"tick/reset never repeat or undo one-time preview");
    }
    for(int type=0;type<=3;++type)for(int severity=1;severity<=10;++severity) {
        Reset();const auto r=Execute(306,type,severity);
        Check(!r.code&&brightCalls==0&&colorCalls==1&&lastType==type&&lastSeverity==(type?severity:0)&&allCallsLocked,"every supported mode/severity pair reaches native ABI exactly once");
    }
    const double invalid[]={-51,5001,-0.5,0.5,5000.5,32767,32768,65536,65586,-32768,-65586,1e40,std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()};
    for(double v:invalid){Reset();Reject("invalid brightness rejected before lock",304,v);}
    for(double v:{-1.,4.,1.5,std::numeric_limits<double>::quiet_NaN()}){Reset();Reject("invalid color mode rejected before lock",306,v,5);}
    for(double v:{0.,11.,1.5,std::numeric_limits<double>::quiet_NaN()})for(double mode:{0.,2.}){Reset();Reject("invalid severity rejected even when mode is disabled",306,mode,v);}
}
void TestFullBrightnessRoundtrip() {
    // One fixture reset for the entire supported integer domain. Exercise the
    // actual command/snapshot/restore route, not an isolated inverse formula.
    Reset();BYTE settings[508]{};memcpy(settings,reinterpret_cast<void*>(g_base+0x715350),508);
    bool settersExact=true,snapshotsExact=true,restoresExact=true,gammaExact=true;
    unsigned levels=0;
    for(int value=-50;value<=5000;++value) {
        const double args[8]{static_cast<double>(value)};TrainerResult applied{};
        const bool dispatched=DisplayHandle(Context(),304,args,applied);
        settersExact&=dispatched&&!applied.code&&lastBrightness==value;
        const float adjustment=static_cast<float>(value)/50.0f;
        const float gamma=2.2f/(2.2f+adjustment);
        gammaExact&=GX<float>(716)==adjustment&&GX<float>(23360)==gamma;
        shared.valid[304/64]&=~(uint64_t(1)<<(304%64));
        shared.values[304]=std::numeric_limits<double>::quiet_NaN();
        DisplaySnapshot(Context());
        const bool exact=Has(304)&&shared.values[304]==static_cast<double>(value);
        snapshotsExact&=exact;
        const double restoreArgs[8]{shared.values[304]};TrainerResult restored{};
        restoresExact&=DisplayHandle(Context(),304,restoreArgs,restored)&&!restored.code&&lastBrightness==value&&
            GX<float>(716)==adjustment&&GX<float>(23360)==gamma;
        ++levels;
    }
    Check(levels==5051&&settersExact,"all 5051 accepted brightness integers reach the int16 setter without clamping or wrap");
    Check(snapshotsExact,"all 5051 native float adjustments publish their exact original integer");
    Check(restoresExact&&brightCalls==2*levels,"every sampled brightness can restore through native integer validation");
    Check(gammaExact&&allCallsLocked&&!held&&locks==3*levels&&unlocks==locks,"full command/read/restore domain preserves native gamma and balanced mutex calls");
    Check(!colorCalls&&GX<int>(23364)==1&&GX<int>(23368)==5&&
        !memcmp(settings,reinterpret_cast<void*>(g_base+0x715350),508),"full brightness domain leaves color and loaded settings unchanged");
    Check(blockingLocks==2*levels&&mutexTries==levels,"domain snapshots remain nonblocking while explicit commands use their validated lock");
    const float exponent=GX<float>(23360);
    Check(lastBrightness==5000&&GX<float>(716)==100.f&&fabs(static_cast<double>(exponent)-2.2/102.2)<1e-8,
        "Flashbang5000 produces adjustment100 and exponent approximately0.0215264");
    Check(exponent>0.f&&exponent<2.2f/3.2f&&std::pow(0.18f,exponent)>0.96f,
        "the modeled gamma transform at5000 brightens a positive midtone substantially more than level50");
    DisplayTick(Context());DisplayReset(Context());
    Check(brightCalls==2*levels&&!colorCalls,"extended brightness still has no repeated tick/reset setter");
}
void TestLifetime() {
    Reset();g_disabled=1;Reject("disabled bridge rejected");
    Reset();g_gameThread=0;Reject("unbound game thread rejected");
    Reset();++g_gameThread;Reject("wrong current thread rejected");
    Reset();shared.hostHeartbeat=0;Reject("missing heartbeat rejected");
    Reset();fakeNow+=5001;Reject("expired heartbeat rejected");
    Reset();g_shared=nullptr;Reject("missing shared memory rejected");
    Reset();shared.hostHeartbeat=0xfffffff0;fakeNow=15;Check(!Execute().code,"heartbeat wrap remains fresh");
    Reset();for(int epoch:{0,-1}){At<int>(EpochRva)=epoch;Reject("uninitialized singleton cannot be constructed by preview");}
    Reset();GX<uintptr_t>(0)=g_base+VtableRva+8;Reject("foreign renderer vtable rejected");
    Reset();GX<uintptr_t>(736)=0;Reject("device shutdown rejected");
    Reset();GX<uintptr_t>(1144)=0;Reject("root signature shutdown rejected");
    Reset();GX<HANDLE>(784)=nullptr;Reject("missing app thread rejected");
    Reset();GX<HANDLE>(792)=nullptr;Reject("missing timing thread rejected");
    Reset();GX<HANDLE>(792)=appHandle;Reject("same thread handle rejected");
    Reset();timingId=appId;Reject("duplicate handle for app thread rejected");
    Reset();appId+=1;Reject("foreign application thread rejected");
    Reset();timingId=0;Reject("dead timing thread rejected");
    Reset();timingProcess+=1;Reject("foreign-process timing thread rejected");
    Reset();fakeTimingExit=0;Reject("finished presentation thread rejected");
    Reset();exitQueryWorks=false;Reject("unknown thread lifetime rejected");
    Reset();GX<int>(808)=1;Reject("renderer stop requested");
    Reset();At<int>(0x220000+4752)=0;Reject("app exit requested while renderer still looks valid");
    Reset();GX<uintptr_t>(1000)+=8;Reject("app association mismatch rejected");
    Reset();At<uintptr_t>(AppRva)+=8;Reject("global app identity mismatch rejected");
    Reset();g_selectedVtable=0;Reject("unselected app vtable rejected");
    Reset();At<uintptr_t>(0x220000)+=8;Reject("app vtable changed rejected");
    Reset();testRuntimeAvailable=false;Reject("missing original runtime rejected");
    Reset();At<uintptr_t>(0x57B458)+=1;Reject("hooked lock IAT rejected");
    Reset();At<uintptr_t>(0x57B450)+=1;Reject("hooked unlock IAT rejected");
    for(uintptr_t rva:{uintptr_t(EpochRva),uintptr_t(AppRva),uintptr_t(ObjectRva+MutexOffset+79),uintptr_t(0x220000+4755),uintptr_t(0x57B450)}){
        Reset();denied=g_base+rva;deniedSize=1;Reject("unreadable lifetime boundary rejected");
    }
    for(uintptr_t rva:{uintptr_t(ObjectRva+716),uintptr_t(ObjectRva+23371),uintptr_t(ObjectRva+MutexOffset+79)}){
        Reset();deniedWrite=g_base+rva;deniedWriteSize=1;Reject("unwritable setter or opaque mutex rejected");
    }
    for(uintptr_t rva:{uintptr_t(0x5061A0),uintptr_t(0x506230),uintptr_t(0x1268FA),uintptr_t(0x125D29),uintptr_t(0x11C182),uintptr_t(0x43AD04),uintptr_t(0x43AD0A)}){
        Reset();At<BYTE>(rva)^=1;Reject("changed native wrapper/callee/getter/import bytes rejected");
    }
    Reset();At<float>(0x5B532C)=0;Reject("modified brightness divisor rejected");
    Reset();At<float>(0x5A9CB4)=0;Reject("modified gamma constant rejected");
    Reset();TrainerResult r{};double args[8]{};auto c=Context();c.base+=1;
    DisplayHandle(c,304,args,r);Check(r.code!=0&&!locks&&!brightCalls,"foreign context rejected");
}
void TestMutexAndRestore() {
    Reset();lockResult=1;Check(Execute().code!=0&&!unlocks&&!brightCalls&&!colorCalls,"failed acquisition makes no setter or unlock call");
    RejectAfterLock([]{GX<int>(808)=1;},"stop while waiting suppresses preview");
    RejectAfterLock([]{At<int>(0x220000+4752)=1;},"app exit while waiting suppresses preview");
    RejectAfterLock([]{GX<uintptr_t>(736)+=8;},"device replacement while waiting suppresses preview");
    RejectAfterLock([]{GX<uintptr_t>(1144)+=8;},"root replacement while waiting suppresses preview");
    RejectAfterLock([]{GX<HANDLE>(792)=nullptr;},"timing lifetime lost while waiting");
    RejectAfterLock([]{At<uintptr_t>(0x57B450)+=1;},"changed IAT rejected; captured original unlock still executes");
    RejectAfterLock([]{fakeNow+=5001;},"heartbeat expired during acquisition");
    RejectAfterLock([]{g_disabled=1;},"bridge disabled during acquisition");
    RejectAfterLock([]{At<BYTE>(0x5061A0)^=1;},"code changed during acquisition");
    Reset();Check(CatchSetter(1,304)&&unlocks==1&&!held,"SEH from first setter releases mutex");
    Reset();Check(CatchSetter(2,305)&&brightCalls==1&&colorCalls==1&&unlocks==1&&!held,"SEH from second restore setter releases mutex without retry");
    Reset();unlockResult=1;Check(Execute().code!=0&&brightCalls==1&&unlocks==1,"unlock failure is not reported as success");
    Check(Execute().code!=0&&brightCalls==1&&locks==1&&unlocks==1,"unlock failure permanently gates future module calls");
    DisplayReset(Context());Check(faulted,"reset does not erase uncertain mutex ownership");
    Reset();BYTE settings[508]{};memcpy(settings,reinterpret_cast<void*>(g_base+0x715350),508);
    Check(!Execute(305).code&&brightCalls==1&&colorCalls==1&&lastBrightness==-25&&lastType==2&&lastSeverity==6,"loaded restore calls both previews exactly once");
    Check(!memcmp(settings,reinterpret_cast<void*>(g_base+0x715350),508),"restore never writes configuration");
    Reset();changeSettingsInBrightness=true;Check(!Execute(305).code&&lastType==2&&lastSeverity==6,"restore uses immutable field snapshot after first setter");
    for(int16_t value:{int16_t(-50),int16_t(50)}){Reset();At<int16_t>(FieldsRva+12)=value;Check(!Execute(305).code&&lastBrightness==value&&brightCalls==1&&colorCalls==1,"loaded brightness retains original inclusive -50..50 bounds");}
    for(int16_t value:{int16_t(-51),int16_t(51),int16_t(5000),int16_t(32767),int16_t(-32768)}){Reset();At<int16_t>(FieldsRva+12)=value;Check(Execute(305).code!=0&&!brightCalls&&!colorCalls&&unlocks==1,"extended runtime range never broadens loaded brightness or performs partial restore");}
    for(int16_t value:{int16_t(-1),int16_t(4)}){Reset();At<int16_t>(FieldsRva+16)=value;Check(Execute(305).code!=0&&!brightCalls&&!colorCalls,"invalid loaded mode produces no partial restore");}
    for(int16_t value:{int16_t(0),int16_t(11)}){Reset();At<int16_t>(FieldsRva+18)=value;Check(Execute(305).code!=0&&!brightCalls&&!colorCalls,"invalid enabled loaded severity produces no partial restore");}
    Reset();At<int16_t>(FieldsRva+16)=0;At<int16_t>(FieldsRva+18)=-32768;
    Check(!Execute(305).code&&lastType==0&&lastSeverity==0,"disabled loaded mode ignores its unused severity");
    for(uintptr_t rva:{uintptr_t(0x715350),uintptr_t(0x715354),uintptr_t(0x715358)}){Reset();At<BYTE>(rva)^=1;Check(Execute(305).code!=0&&!brightCalls&&!colorCalls,"invalid SET header prevents restore");}
    Reset();denied=g_base+FieldsRva+19;deniedSize=1;Check(Execute(305).code!=0&&!brightCalls&&!colorCalls,"unreadable last config byte prevents restore");
}
bool CatchSnapshot() { __try { DisplaySnapshot(Context()); } __except(EXCEPTION_EXECUTE_HANDLER){return true;}return false; }
void TestSnapshotAndDispatch() {
    Reset();DisplaySnapshot(Context());Check(mutexTries==1&&!blockingLocks&&unlocks==1&&Has(304)&&Has(465),"passive display uses only nonblocking acquisition");
    Reset();lockResult=3;held=true;DisplaySnapshot(Context());Check(mutexTries==1&&!blockingLocks&&!unlocks&&held&&!faulted&&!Has(304)&&!Has(465),"busy display does not release another owner's mutex or publish");
    held=false;lockResult=0;DisplaySnapshot(Context());Check(mutexTries==2&&!blockingLocks&&unlocks==1&&Has(304),"a later display sample resumes after contention");
    Reset();testTryLock=nullptr;DisplaySnapshot(Context());Check(!mutexTries&&!blockingLocks&&!unlocks&&!Has(304),"missing optional try export skips observation");
    Check(Execute().code==0&&blockingLocks==1&&!mutexTries&&unlocks==1,"explicit display command still uses validated waiting lock");
    Reset();onLock=[]{testTryLock=nullptr;};DisplaySnapshot(Context());Check(!Has(304)&&!Has(465)&&unlocks==1&&!blockingLocks,"changed try export invalidates lease and uses captured release");
    Reset();throwTryLock=true;Check(CatchSnapshot()&&faulted&&!unlocks&&!blockingLocks&&!Has(304),"try-lock fault latches without guessing ownership");
    Reset();throwUnlock=true;Check(CatchSnapshot()&&faulted&&unlocks==1&&!blockingLocks&&!Has(304),"passive unlock fault latches and publishes nothing");
    Reset();onLock=[]{throwRead=g_base+EpochRva;};Check(CatchSnapshot()&&faulted&&unlocks==1&&!held&&!blockingLocks&&!Has(304),"passive capture fault releases acquired mutex through finally");
    Reset();for(float value:{-1.f,0.f,1.f,100.f}){GX<float>(716)=value;DisplaySnapshot(Context());Check(Has(304)&&shared.values[304]==value*50,"inclusive extended brightness snapshot bounds");}
    for(float value:{-1.01f,1.01f,0.01f,-0.03f,0.12345f,100.02f,
        std::nextafter(0.02f,1.f),std::nextafter(100.f,0.f),std::nextafter(100.f,101.f),
        std::numeric_limits<float>::denorm_min(),std::numeric_limits<float>::max(),
        std::numeric_limits<float>::infinity(),-std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN()}){
        Reset();GX<float>(716)=value;DisplaySnapshot(Context());
        Check(!Has(304)&&locks==1&&unlocks==1&&!blockingLocks&&mutexTries==1,"fractional non-native or out-of-range brightness cannot masquerade as a restorable integer");
        Check(Has(465)&&shared.values[465]==21,"unrestorable brightness does not discard independent valid color snapshot");
    }
    Reset();lockResult=1;DisplaySnapshot(Context());Check(!Has(304)&&!unlocks,"failed snapshot lock publishes no value");
    Reset();unlockResult=1;DisplaySnapshot(Context());Check(!Has(304)&&unlocks==1,"failed snapshot unlock publishes no value");
    Reset();onLock=[]{GX<uintptr_t>(736)+=8;};DisplaySnapshot(Context());Check(!Has(304)&&unlocks==1,"snapshot discards replacement renderer");
    Reset();g_disabled=1;DisplaySnapshot(Context());Check(!Has(304)&&!locks,"unavailable snapshot never locks or publishes stale fields");
    Reset();DisplayCapabilities();for(unsigned slot=300;slot<=311;++slot) {
        const bool supported=(shared.supported[slot/64]&(uint64_t(1)<<(slot%64)))!=0;
        Check(supported==(slot>=304&&slot<=306),"capabilities cover only allocated three slots");
    }
    for(unsigned slot:{303u,307u,511u}){TrainerResult r{123,L"unchanged"};double args[8]{};Check(!DisplayHandle(Context(),slot,args,r)&&r.code==123,"unowned command passed through");}
}
void TestHighBrightnessColorIsolation() {
    Reset();Check(!Execute(304,5000).code,"high brightness preview available for conditional color isolation");
    const float adjustment=GX<float>(716),gamma=GX<float>(23360);
    BYTE settings[508]{};memcpy(settings,reinterpret_cast<void*>(g_base+0x715350),508);
    Check(!CompareColor(0,1,5,3,10).code&&!CompareColor(1,3,10,1,5).code,
        "conditional color applies and restores while Flashbang brightness is active");
    Check(brightCalls==1&&colorCalls==2&&GX<float>(716)==adjustment&&GX<float>(23360)==gamma&&
        !memcmp(settings,reinterpret_cast<void*>(g_base+0x715350),508),"conditional color leaves high runtime brightness gamma and loaded configuration unchanged");
    DisplaySnapshot(Context());
    Check(Has(304)&&shared.values[304]==5000&&Has(465)&&shared.values[465]==21,
        "coherent snapshot independently retains high exact brightness and restored color pair");
}
void TestConditionalColor() {
    // Every canonical original/destination pair, both apply and restore, including disabled zero.
    for(int originalType=0;originalType<=3;++originalType)for(int originalSeverity=0;originalSeverity<=10;++originalSeverity) {
        if(!ColorPair(originalType,originalSeverity))continue;
        for(int type=0;type<=3;++type)for(int severity=0;severity<=10;++severity) {
            if(!ColorPair(type,severity))continue;
            for(int operation=0;operation<=1;++operation) {
                Reset();GX<int>(23364)=originalType;GX<int>(23368)=originalSeverity;
                BYTE settings[508]{};memcpy(settings,reinterpret_cast<void*>(g_base+0x715350),508);
                const auto result=CompareColor(operation,originalType,originalSeverity,type,severity);
                Check(!result.code&&colorCalls==1&&brightCalls==0&&lastType==type&&lastSeverity==severity&&allCallsLocked,
                    "matching pair calls only color exactly once inside mutex");
                Check(GX<float>(716)==0&&GX<float>(23360)==1&&!memcmp(settings,reinterpret_cast<void*>(g_base+0x715350),508),
                    "conditional color preserves brightness gamma and loaded configuration");
                DisplaySnapshot(Context());
                Check(Has(465)&&shared.values[465]==type*16+severity,"coherent packed pair is sampled including valid zero");
            }
        }
    }
    for(int operation=0;operation<=1;++operation) {
        Reset();auto result=CompareColor(operation,2,5,0,0);
        Check((result.code==0)==(operation==1)&&!colorCalls&&!brightCalls&&unlocks==1,
            "mode mismatch rejects apply but completes restore without native writes");
        Reset();result=CompareColor(operation,1,6,0,0);
        Check((result.code==0)==(operation==1)&&!colorCalls&&!brightCalls&&unlocks==1,
            "severity mismatch compares entire pair and never writes");
        Reset();onLock=[]{GX<int>(23364)=3;GX<int>(23368)=9;};result=CompareColor(operation,1,5,0,0);
        Check((result.code==0)==(operation==1)&&!colorCalls&&!brightCalls&&GX<int>(23364)==3&&GX<int>(23368)==9,
            "change after host snapshot but during lock acquisition wins over stale conditional request");
    }
    for(double bad:{-1.,2.,0.5,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}) {
        Reset();Check(CompareColor(bad,1,5,2,10).code!=0&&!locks&&!colorCalls,"invalid operation refused before mutex");
    }
    for(double bad:{-1.,4.,0.5,std::numeric_limits<double>::quiet_NaN()}) {
        Reset();Check(CompareColor(0,bad,5,2,10).code!=0&&!locks,"invalid expected mode refused");
        Reset();Check(CompareColor(1,1,5,bad,10).code!=0&&!locks,"invalid replacement mode refused");
    }
    for(double bad:{-1.,11.,0.5,std::numeric_limits<double>::infinity()}) {
        Reset();Check(CompareColor(0,1,bad,2,10).code!=0&&!locks,"invalid expected severity refused");
        Reset();Check(CompareColor(1,1,5,2,bad).code!=0&&!locks,"invalid replacement severity refused");
    }
    for(int type=0;type<=3;++type)for(int severity=0;severity<=10;++severity) {
        if(ColorPair(type,severity))continue;
        Reset();Check(CompareColor(0,type,severity,1,5).code!=0&&!locks,"noncanonical expected pair refused");
        Reset();Check(CompareColor(1,1,5,type,severity).code!=0&&!locks,"noncanonical destination pair refused");
        Reset();GX<int>(23364)=type;GX<int>(23368)=severity;
        Check(CompareColor(1,1,5,0,0).code!=0&&locks==1&&unlocks==1&&!colorCalls,"invalid native pair is unavailable not writable");
        DisplaySnapshot(Context());Check(!Has(465)&&Has(304),"invalid color pair does not masquerade as disabled or invalidate independent brightness");
    }
    Reset();TrainerResult result{};Check(DisplayHandle(Context(),464,nullptr,result)&&result.code&&!locks,"null conditional arguments rejected");
    Reset();g_disabled=1;Check(CompareColor(0,1,5,2,10).code&&!locks,"disabled conditional operation refuses before lock");
    Reset();lockResult=1;Check(CompareColor(0,1,5,2,10).code&&!unlocks&&!colorCalls,"conditional lock failure never calls native setter");
    Reset();onLock=[]{GX<uintptr_t>(736)+=8;};Check(CompareColor(1,1,5,0,0).code&&unlocks==1&&!colorCalls,
        "conditional restore discards a replaced renderer after acquisition");
    Reset();onLock=[]{GX<int>(808)=1;};Check(CompareColor(0,1,5,2,10).code&&unlocks==1&&!colorCalls,"conditional apply respects shutdown during lock");
    Reset();onLock=[]{fakeNow+=5001;};Check(CompareColor(1,1,5,0,0).code&&unlocks==1&&!colorCalls,"conditional restore respects expired heartbeat");
    Reset();unlockResult=1;Check(CompareColor(0,1,5,2,10).code==2&&colorCalls==1&&faulted,"conditional unlock error latches shared display failure");
    Check(CompareColor(1,2,10,1,5).code!=0&&colorCalls==1&&locks==1,"failed unlock prevents further conditional writes");
    Reset();lockResult=1;DisplaySnapshot(Context());Check(!Has(465)&&!unlocks,"failed coherent sample acquisition publishes no pair");
    Reset();unlockResult=1;DisplaySnapshot(Context());Check(!Has(465)&&faulted,"failed coherent sample release publishes no pair and latches");
    Reset();onLock=[]{GX<int>(808)=1;};DisplaySnapshot(Context());Check(!Has(465)&&unlocks==1,"coherent sample suppresses shutdown data");
    Reset();DisplayCapabilities();for(unsigned slot=464;slot<=466;++slot)
        Check(((shared.supported[slot/64]>>(slot%64))&1)==(slot<=465),"exactly new command and readback capabilities published");
    double args[8]{};result={123,L"untouched"};Check(!DisplayHandle(Context(),465,args,result)&&result.code==123,"packed readback is not a writable command");
}
bool CatchConditionalSetter() {
    raiseCall=2;
    __try { CompareColor(0,1,5,2,10); }
    __except(EXCEPTION_EXECUTE_HANDLER) { return true; }
    return false;
}
}
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,ImageSize,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(!g_base)return 2;
    TestInputs();TestFullBrightnessRoundtrip();TestLifetime();TestMutexAndRestore();TestSnapshotAndDispatch();TestConditionalColor();TestHighBrightnessColorIsolation();
    Reset();Check(CatchConditionalSetter()&&unlocks==1&&!held,"conditional setter SEH still releases captured mutex exactly once");
    printf("DisplayGuardTests: %u checks, %u failures\n",checks,failures);
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
