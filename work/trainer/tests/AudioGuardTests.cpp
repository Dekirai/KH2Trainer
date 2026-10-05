#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdint.h>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <initializer_list>
#include <limits>
#define KH2_AUDIO_TESTS
namespace {
struct TrainerContext { uintptr_t base,player,status; bool sceneReady; };
struct TrainerResult { int code; const wchar_t* text; };
struct Shared { DWORD hostHeartbeat; double values[512]; uint64_t valid[8],supported[8]; } shared{};
uintptr_t g_base=0; Shared* g_shared=&shared; DWORD g_gameThread=0; LONG g_disabled=0;
DWORD fakeNow=100000; DWORD Now() { return fakeNow; }
#define GetTickCount Now
template<class T> T& At(uintptr_t rva) { return *reinterpret_cast<T*>(g_base+rva); }
uintptr_t denied=0; SIZE_T deniedSize=0;
bool Readable(const void* p,SIZE_T n) {
    const auto a=reinterpret_cast<uintptr_t>(p);
    return a>=g_base && n<=0x2C00000 && a-g_base<=0x2C00000-n &&
        (!denied || a+n<=denied || a>=denied+deniedSize);
}
bool Writable(void* p,SIZE_T n) { return Readable(p,n); }
void SnapshotValue(unsigned slot,double value) { if(slot<512&&std::isfinite(value)) { shared.values[slot]=value; shared.valid[slot/64]|=uint64_t(1)<<(slot%64); } }
void SupportCapability(unsigned slot) { shared.supported[slot/64]|=uint64_t(1)<<(slot%64); }
#include "../../../trainer/Native/AudioFeatures.inl"
unsigned checks=0,failures=0;
void Check(bool b,const char* s) { ++checks; if(!b) { ++failures; printf("FAIL %s\n",s); } }
struct Call { unsigned id; float gain; unsigned ms; } calls[16]{};
unsigned constructs=0,sets=0,destroys=0,badFactory=0,failSetter=0,raiseSetter=0,changeGraph=0;
bool underLock=true;
CRITICAL_SECTION* Lock() { return reinterpret_cast<CRITICAL_SECTION*>(g_base+audio_mix::LockRva); }
bool OwnLock() { return reinterpret_cast<uintptr_t>(Lock()->OwningThread)==GetCurrentThreadId(); }
uintptr_t Bus(unsigned id) { return id?g_base+0x103000+id*0x400:g_base+0x101000; }
audio_mix::Controller* __fastcall MockConstruct(audio_mix::Controller* c,unsigned id) {
    ++constructs; underLock=underLock&&OwnLock();
    c->vtable=g_base+0x61ACD0; c->id=static_cast<int>(id); c->backend=g_base+0x110000;
    if(constructs==badFactory) ++c->id;
    if(constructs==changeGraph) At<uintptr_t>(audio_mix::MasterRva)+=8;
    return c;
}
void __fastcall MockSet(audio_mix::Controller* c,float gain,unsigned ms) {
    underLock=underLock&&OwnLock(); calls[sets++]={static_cast<unsigned>(c->id),gain,ms};
    if(sets==raiseSetter) RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    if(sets==failSetter) return;
    auto bus=Bus(static_cast<unsigned>(c->id));
    *reinterpret_cast<float*>(bus+36)=gain; *reinterpret_cast<int*>(bus+44)=static_cast<int>(ms);
}
void __fastcall MockDestroy(audio_mix::Controller*) { ++destroys; underLock=underLock&&OwnLock(); }
template<SIZE_T N> void SeedCode(uintptr_t rva,const BYTE(&bytes)[N]) { memcpy(reinterpret_cast<void*>(g_base+rva),bytes,N); }
void Setup() {
    using namespace audio_mix;
    shared={}; shared.hostHeartbeat=fakeNow=100000; g_shared=&shared; g_disabled=0; g_gameThread=GetCurrentThreadId();
    denied=0; deniedSize=0; constructs=sets=destroys=badFactory=failSetter=raiseSetter=changeGraph=0; underLock=true;
    memset(reinterpret_cast<void*>(g_base+0x100000),0,0x20000);
    At<uintptr_t>(DriverRva)=g_base+0x100000; At<uintptr_t>(MasterRva)=Bus(0); At<uintptr_t>(ListRva)=g_base+0x102000;
    At<int>(CountRva)=8; At<uintptr_t>(0x2B81DE8)=g_base+0x110000;
    At<uintptr_t>(0x100000)=g_base+DriverVtable; At<BYTE>(0x100000+52)=1;
    At<uintptr_t>(DriverVtable+152)=g_base+0x0936A0;
    At<uintptr_t>(MasterXaVtable+24)=g_base+0x0A8830; At<uintptr_t>(MasterGenericVtable+24)=g_base+0x0C4B80;
    At<uintptr_t>(BusVtable+24)=g_base+0x0A54D0;
    At<unsigned>(0x8BBD14)=0; At<unsigned>(0x8BBD18)=0; At<float>(0x5AAA40)=0.9f;
    for(unsigned id=0;id<=8;++id) {
        const uintptr_t bus=Bus(id);
        if(id) At<uintptr_t>(0x102000+(id-1)*8)=bus;
        *reinterpret_cast<uintptr_t*>(bus)=g_base+(id?BusVtable:MasterXaVtable);
        *reinterpret_cast<int*>(bus+8)=static_cast<int>(id);
        *reinterpret_cast<uintptr_t*>(bus+24)=g_base+DynamicVtable;
        for(unsigned off : {32u,36u,52u}) *reinterpret_cast<float*>(bus+off)=0.8f;
        *reinterpret_cast<float*>(bus+56)=1;
        *reinterpret_cast<BYTE*>(bus+332)=1; *reinterpret_cast<BYTE*>(bus+333)=1;
    }
    At<uintptr_t>(0x101000+336)=g_base+0x102000; At<int>(0x101000+344)=8;
    memcpy(reinterpret_cast<void*>(g_base+0x715350),"SET-",4); At<unsigned>(0x715354)=8; At<unsigned>(0x715358)=508;
    for(unsigned i=0;i<4;++i) At<uint16_t>(0x715364+20+2*i)=static_cast<uint16_t>(i+2);
    for(unsigned i=0;i<=10;++i) At<float>(0x5AB960+4*i)=i/10.0f;
    SeedCode(0x079C90,ConstructCode); SeedCode(0x07FAD0,SetCode); SeedCode(0x07F7E0,DestroyCode); SeedCode(0x0936A0,FactoryCode);
    SeedCode(0x0A54D0,BusSetCode); SeedCode(0x0A8830,XaSetCode); SeedCode(0x0C4B80,GenericSetCode);
    testConstruct=MockConstruct; testSet=MockSet; testDestroy=MockDestroy;
}
TrainerContext Context() { return {g_base,0,0,false}; }
TrainerResult Execute(unsigned slot=144,double value=50) {
    auto c=Context(); TrainerResult r{}; double args[8]{value};
    Check(AudioHandle(c,slot,args,r),"audio owns its command"); return r;
}
void Rejected(const char* name,unsigned slot=144) { const auto r=Execute(slot); Check(r.code!=0&&sets==0,name); }
bool Has(unsigned slot) { return (shared.valid[slot/64]&(uint64_t(1)<<(slot%64)))!=0; }
bool Near(double a,double b) { return std::fabs(a-b)<0.00001; }
bool CatchFault() {
    __try { Execute(146); }
    __except(EXCEPTION_EXECUTE_HANDLER) { return true; }
    return false;
}
struct BusyArgs { HANDLE ready,release; };
DWORD WINAPI HoldLock(void* p) {
    auto a=static_cast<BusyArgs*>(p); EnterCriticalSection(Lock()); SetEvent(a->ready);
    WaitForSingleObject(a->release,5000); LeaveCriticalSection(Lock()); return 0;
}
bool ReleasedToOtherThread() {
    BusyArgs a{CreateEventW(nullptr,TRUE,FALSE,nullptr),CreateEventW(nullptr,TRUE,FALSE,nullptr)};
    HANDLE thread=CreateThread(nullptr,0,HoldLock,&a,0,nullptr);
    const bool acquired=thread&&WaitForSingleObject(a.ready,1000)==WAIT_OBJECT_0;
    SetEvent(a.release); if(thread) { WaitForSingleObject(thread,5000); CloseHandle(thread); }
    CloseHandle(a.ready); CloseHandle(a.release); return acquired;
}
}
int main() {
    using namespace audio_mix;
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,0x2C00000,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    if(!g_base) return 2;
    InitializeCriticalSection(Lock());
    for(unsigned swap=0;swap<2;++swap) for(unsigned soften=0;soften<2;++soften)
    for(unsigned slot=144;slot<=147;++slot) for(double percent : {0.0,50.0,100.0}) {
        Setup(); At<unsigned>(0x8BBD14)=swap; At<unsigned>(0x8BBD18)=soften;
        const auto r=Execute(slot,percent); const unsigned first=slot==144?0:slot==145?1:slot==146?(swap?3:2):(swap?2:3);
        const float factor=slot==147&&!swap&&soften?0.9f:1.0f;
        Check(r.code==0&&sets==(slot==146?6u:1u),"all four mix controls support mute/mid/full on both native routings");
        Check(calls[0].id==first&&Near(calls[0].gain,percent/100*factor),"group maps to native bus with title-specific voice factor");
        for(unsigned i=0;i<sets;++i) Check(calls[i].ms==1&&Near(calls[i].gain,percent/100*factor),"gain uses one millisecond and exact requested normalized value");
        if(slot==146) for(unsigned i=1;i<sets;++i) Check(calls[i].id==i+3,"effects includes buses4 through8");
        Check(underLock&&constructs==sets&&destroys==constructs,"construct/set/destroy remain under outer audio lock");
        Check(Field<BYTE>(Bus(first),332)==1&&Field<BYTE>(Bus(first),333)==1,"volume preserves native pause ownership flags");
        Check(!OwnLock(),"successful request releases lock");
    }
    for(unsigned swap=0;swap<2;++swap) for(unsigned soften=0;soften<2;++soften) {
        Setup(); At<unsigned>(0x8BBD14)=swap; At<unsigned>(0x8BBD18)=soften;
        BYTE config[508]; memcpy(config,reinterpret_cast<void*>(g_base+0x715350),sizeof(config));
        const auto r=Execute(148);
        Check(r.code==0&&sets==9&&Near(calls[0].gain,0.2)&&Near(calls[1].gain,0.3)&&Near(calls[2].gain,0.4),"reset uses loaded master/music/effects levels");
        Check(Near(calls[8].gain,(!swap&&soften)?0.45:0.5),"reset restores loaded voice level and factor");
        Check(!memcmp(config,reinterpret_cast<void*>(g_base+0x715350),sizeof(config)),"reset does not rewrite or save configuration");
    }
    Setup(); At<uintptr_t>(0x101000)=g_base+MasterGenericVtable; Check(Execute().code==0&&sets==1,"generic native master implementation accepted");
    for(double invalid : {-1.0,100.01,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}) {
        Setup(); Check(Execute(144,invalid).code!=0&&sets==0,"invalid user level rejected");
    }
    Setup(); TrainerResult r{}; double args[8]{}; Check(!AudioHandle(Context(),149,args,r),"readout/unowned slot not handled as command");
    Setup(); g_gameThread=0; Rejected("wrong thread rejected");
    Setup(); g_disabled=1; Rejected("disabled bridge rejected");
    Setup(); shared.hostHeartbeat=0; Rejected("disconnected host rejected");
    Setup(); fakeNow+=5001; Rejected("expired host rejected");
    Setup(); auto c=Context(); c.base=0; AudioHandle(c,144,args,r); Check(r.code!=0&&sets==0,"foreign module base rejected");
    for(uintptr_t rva : {0x079C90u,0x07FAD0u,0x07F7E0u,0x0936A0u,0x0A8830u}) { Setup(); At<BYTE>(rva)^=1; Rejected("changed native code rejected"); }
    Setup(); At<BYTE>(0x0A54D0)^=1; Rejected("changed child setter rejected",145);
    Setup(); At<uintptr_t>(DriverRva)=0; Rejected("absent driver rejects readable stale buses");
    Setup(); At<uintptr_t>(0x100000)=0; Rejected("unknown driver implementation rejected");
    Setup(); At<BYTE>(0x100000+52)=0; Rejected("disabled native driver rejected");
    Setup(); At<uintptr_t>(DriverVtable+152)=0; Rejected("foreign virtual controller constructor rejected");
    for(int count : {0,-1,1025}) { Setup(); At<int>(CountRva)=count; Rejected("invalid bus list count rejected"); }
    Setup(); At<uintptr_t>(ListRva)=1; Rejected("invalid bus list pointer rejected");
    Setup(); At<uintptr_t>(MasterRva)=0; Rejected("absent master rejected");
    Setup(); At<uintptr_t>(0x101000+336)=0; Rejected("master/list identity mismatch rejected");
    Setup(); At<int>(0x101000+344)=7; Rejected("master/count mismatch rejected");
    Setup(); At<unsigned>(0x8BBD14)=2; Rejected("invalid routing flag rejected");
    Setup(); At<unsigned>(0x8BBD18)=2; Rejected("invalid voice scale flag rejected");
    Setup(); At<unsigned>(0x8BBD18)=1; At<float>(0x5AAA40)=0; Rejected("invalid voice scale rejected");
    Setup(); At<uintptr_t>(0x102000+7*8)=0; Rejected("all effects targets preflight before any write",146);
    Setup(); At<int>(0x103000+2*0x400+8)=0; Rejected("child cannot fall back to master",146);
    Setup(); At<uintptr_t>(0x101000+24)=0; Rejected("unknown DynamicValue rejected");
    Setup(); At<float>(0x101000+32)=std::numeric_limits<float>::quiet_NaN(); Rejected("invalid current envelope rejected");
    Setup(); At<float>(0x101000+36)=-1; Rejected("negative gain rejected");
    Setup(); At<int>(0x101000+44)=-1; Rejected("invalid remaining duration rejected");
    Setup(); At<int>(0x101000+48)=-1; Rejected("invalid original duration rejected");
    Setup(); At<BYTE>(0x101000+61)=16; Rejected("invalid envelope curve rejected");
    Setup(); denied=Bus(8); deniedSize=64; Rejected("unreadable late target causes zero writes",146);
    Setup(); badFactory=6; Check(Execute(146).code==2&&sets==0&&destroys==6,"all controllers are checked before first native write");
    Setup(); changeGraph=6; Check(Execute(146).code==2&&sets==0&&destroys==6,"graph replaced during construction causes zero gain writes");
    Setup(); failSetter=2; Check(Execute(146).code==2&&sets==2&&destroys==6,"unexpected native failure reports partial change without further setters");
    for(unsigned i=0;i<4;++i) for(unsigned invalid : {0u,11u}) { Setup(); At<uint16_t>(0x715364+20+2*i)=static_cast<uint16_t>(invalid); Rejected("each loaded setting level validated",148); }
    Setup(); At<unsigned>(0x715354)=9; Rejected("unknown config version rejected",148);
    Setup(); At<unsigned>(0x715358)=0; Rejected("unknown config size rejected",148);
    Setup(); At<BYTE>(0x715350)=0; Rejected("unknown config magic rejected",148);
    Setup(); At<float>(0x5AB960+8)=std::numeric_limits<float>::infinity(); Rejected("invalid level conversion table rejected",148);
    Setup(); AudioSnapshot(Context());
    Check(Has(159)&&shared.values[159]==1&&shared.values[149]==8,"audio status/count snapshot available without Sora scene");
    for(unsigned slot=144;slot<=147;++slot) Check(Has(slot)&&Near(shared.values[slot],80),"logical control target snapshot maps to mixer");
    for(unsigned slot=150;slot<=158;++slot) Check(Has(slot)&&Near(shared.values[slot],80),"current gain stage snapshots cover master and eight buses");
    Setup(); *reinterpret_cast<float*>(Bus(4)+36)=0.5f; AudioSnapshot(Context()); Check(!Has(146),"mixed effects targets are not reported as one uniform value");
    Setup(); At<uintptr_t>(DriverRva)=0; AudioSnapshot(Context()); Check(Has(159)&&shared.values[159]==0&&!Has(150),"dead audio graph cannot publish stale master gain");
    Setup(); AudioCapabilities(); for(unsigned slot=144;slot<=159;++slot) Check(shared.supported[slot/64]&(uint64_t(1)<<(slot%64)),"audio capability published");
    Setup(); raiseSetter=1; Check(CatchFault()&&destroys==6&&!OwnLock(),"native exception still destroys controllers and releases outer lock");
    Check(ReleasedToOtherThread(),"outer CS is available to another thread after exception");
    Setup(); BusyArgs busy{CreateEventW(nullptr,TRUE,FALSE,nullptr),CreateEventW(nullptr,TRUE,FALSE,nullptr)};
    HANDLE thread=CreateThread(nullptr,0,HoldLock,&busy,0,nullptr);
    const bool held=thread&&WaitForSingleObject(busy.ready,1000)==WAIT_OBJECT_0; Check(held,"worker lock fixture acquired");
    if(held) { Check(Execute().code!=0&&sets==0,"busy audio rejects without waiting or writing"); AudioSnapshot(Context()); Check(shared.values[159]==0&&!Has(150),"busy snapshot returns unavailable without sampling objects"); }
    SetEvent(busy.release); if(thread) { WaitForSingleObject(thread,5000); CloseHandle(thread); } CloseHandle(busy.ready); CloseHandle(busy.release);
    DeleteCriticalSection(Lock()); VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);
    printf("Audio guard tests: %u checks, %u failures\n",checks,failures); return failures?1:0;
}
