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
uintptr_t g_base=0; Shared* g_shared=&shared; DWORD g_gameThread=0; LONG g_disabled=0;
constexpr SIZE_T ImageSize=0x2C30000;
constexpr uintptr_t Manager=0x120000, Layout=0x110000, Members=0x130000, PointerList=0x121000;
DWORD fakeNow=100000; DWORD Now() { return fakeNow; }
template<class T> T& At(uintptr_t rva) { return *reinterpret_cast<T*>(g_base+rva); }
uintptr_t denied=0,poison=0,faultAt=0; SIZE_T deniedSize=0;
uintptr_t readOnly=0; SIZE_T readOnlySize=0;
unsigned poisonReads=0,readCalls=0,faultReadCount=0;
unsigned tries=0,releases=0; uintptr_t tried[16]{},released[16]{};
unsigned mutateOnInner=0; bool busyOuter=false,busyInner=false,throwTryInner=false,throwLeaveInner=false;
bool publicationLocked=false;
CRITICAL_SECTION* Outer() { return reinterpret_cast<CRITICAL_SECTION*>(g_base+0x2B81278); }
CRITICAL_SECTION* Inner() { return reinterpret_cast<CRITICAL_SECTION*>(g_base+Manager+776); }
bool Own(CRITICAL_SECTION* cs) { return reinterpret_cast<uintptr_t>(cs->OwningThread)==GetCurrentThreadId(); }
bool Readable(const void* p,SIZE_T size) {
    ++readCalls;
    const uintptr_t address=reinterpret_cast<uintptr_t>(p);
    if(address==poison && poison) ++poisonReads;
    if((faultAt && address==faultAt) || (faultReadCount && readCalls==faultReadCount))
        RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    return address>=g_base && size<=ImageSize && address-g_base<=ImageSize-size &&
        (!denied || address+size<=denied || address>=denied+deniedSize);
}
bool Writable(void* p,SIZE_T size) {
    const auto address=reinterpret_cast<uintptr_t>(p);
    return Readable(p,size) && (!readOnly || address+size<=readOnly || address>=readOnly+readOnlySize);
}
void SnapshotValue(unsigned slot,double value) {
    publicationLocked=publicationLocked||Own(Outer())||Own(Inner());
    if(slot<512 && std::isfinite(value)) { shared.values[slot]=value;shared.valid[slot/64]|=uint64_t(1)<<(slot%64); }
}
void SupportCapability(unsigned slot) { if(slot<512) shared.supported[slot/64]|=uint64_t(1)<<(slot%64); }
BOOL TryLock(CRITICAL_SECTION* cs) {
    if(tries<16) tried[tries]=reinterpret_cast<uintptr_t>(cs);
    ++tries;
    if(cs==Outer() && busyOuter) return FALSE;
    if(cs==Inner()) {
        if(throwTryInner) RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
        if(busyInner) return FALSE;
    }
    const BOOL acquired=TryEnterCriticalSection(cs);
    if(acquired && cs==Inner()) {
        switch(mutateOnInner) {
        case 1: At<uintptr_t>(0x2B81DF8)=0;break;
        case 2: At<uintptr_t>(0x2B81DE8)=0;break;
        case 3: At<uintptr_t>(0x2B81DE0)=0;break;
        case 4: At<BYTE>(Manager+816)=0;break;
        case 5: At<uintptr_t>(Manager)=g_base+0x61A5B0;break;
        case 6: shared.hostHeartbeat=0;break;
        case 7: fakeNow+=5001;break;
        case 8: At<uintptr_t>(Manager+8)=0;break;
        case 9: At<uintptr_t>(Layout+8)=0;break;
        default:break;
        }
    }
    return acquired;
}
void Unlock(CRITICAL_SECTION* cs) {
    if(releases<16) released[releases]=reinterpret_cast<uintptr_t>(cs);
    ++releases;
    LeaveCriticalSection(cs);
    // Deliberately raise after releasing to test the outer finally's pairing.
    if(cs==Inner() && throwLeaveInner) RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
}
#define GetTickCount Now
#define TryEnterCriticalSection TryLock
#define LeaveCriticalSection Unlock
#pragma warning(push)
#pragma warning(disable:4505) // Existing audio command API is included for real helpers; no gain action is invoked.
#include "../../../trainer/Native/AudioFeatures.inl"
#pragma warning(pop)
#include "../../../trainer/Native/SpatialAudioFeatures.inl"
#undef TryEnterCriticalSection
#undef LeaveCriticalSection
#undef GetTickCount

unsigned checks=0,failures=0;
void Check(bool condition,const char* name) { ++checks;if(!condition) { ++failures;printf("FAIL %s\n",name); } }
bool Has(unsigned slot) { return (shared.valid[slot/64]&(uint64_t(1)<<(slot%64)))!=0; }
uintptr_t MemberPointer(unsigned index) { return g_base+Members+index*256; }
TrainerContext Context() { return {g_base,0,0,false}; }
void ClearOutput() { memset(shared.valid,0,sizeof(shared.valid));for(auto& value:shared.values) value=-9999; }
void SeedMember(unsigned index,BYTE kind,uint32_t id,uint32_t priority,bool enabled=true) {
    const uintptr_t rva=Members+index*256;
    memset(reinterpret_cast<void*>(g_base+rva),0,256);
    At<uintptr_t>(rva)=g_base+(kind==1?spatial_audio::BaseVtable:kind==2?spatial_audio::PointVtable:spatial_audio::LineVtable);
    At<BYTE>(rva+8)=kind;At<uint32_t>(rva+12)=id;At<uintptr_t>(rva+16)=g_base+Manager;
    At<uint32_t>(rva+120)=priority;At<BYTE>(rva+132)=enabled?1:0;
    At<uintptr_t>(PointerList+index*sizeof(uintptr_t))=g_base+rva;
}
void Setup(int count=3,int capacity=8) {
    shared={};shared.hostHeartbeat=fakeNow=100000;g_shared=&shared;g_disabled=0;g_gameThread=GetCurrentThreadId();
    denied=poison=faultAt=readOnly=0;deniedSize=readOnlySize=0;poisonReads=readCalls=faultReadCount=0;
    tries=releases=0;memset(tried,0,sizeof(tried));memset(released,0,sizeof(released));
    mutateOnInner=0;busyOuter=busyInner=throwTryInner=throwLeaveInner=false;publicationLocked=false;
    memset(reinterpret_cast<void*>(g_base+0x100000),0,0x20000);
    // Preserve the initialized inner CS while resetting surrounding native data.
    memset(reinterpret_cast<void*>(g_base+Manager),0,776);
    memset(reinterpret_cast<void*>(g_base+Manager+816),0,992-816);
    memset(reinterpret_cast<void*>(g_base+PointerList),0,1024*sizeof(uintptr_t));
    At<uintptr_t>(audio_mix::DriverRva)=g_base+0x100000;
    At<uintptr_t>(audio_mix::MasterRva)=g_base+0x101000;
    At<uintptr_t>(audio_mix::ListRva)=g_base+0x102000;
    At<int>(audio_mix::CountRva)=8;
    At<uintptr_t>(0x100000)=g_base+audio_mix::DriverVtable;At<BYTE>(0x100000+52)=1;
    At<uintptr_t>(audio_mix::DriverVtable+152)=g_base+0x0936A0;
    At<uintptr_t>(0x101000)=g_base+audio_mix::MasterXaVtable;
    At<uintptr_t>(0x101000+336)=g_base+0x102000;At<int>(0x101000+344)=8;
    At<unsigned>(0x8BBD14)=0;At<unsigned>(0x8BBD18)=0;
    At<uintptr_t>(spatial_audio::ManagerRva)=g_base+Manager;
    At<uintptr_t>(spatial_audio::LayoutRva)=g_base+Layout;
    At<uintptr_t>(Manager)=g_base+spatial_audio::ManagerVtable;
    At<uintptr_t>(Layout)=g_base+spatial_audio::LayoutVtable;
    At<uintptr_t>(Manager+8)=g_base+Layout;At<uintptr_t>(Layout+8)=g_base+Manager;
    At<BYTE>(Manager+816)=1;At<int>(Manager+24)=count;At<int>(Manager+28)=count;At<int>(Manager+32)=capacity;
    At<uintptr_t>(Manager+768)=g_base+PointerList;
    for(int i=0;i<count;++i) SeedMember(static_cast<unsigned>(i),static_cast<BYTE>(1+i%3),static_cast<uint32_t>(i+1),static_cast<uint32_t>(i*10));
    At<uintptr_t>(Manager+120)=count?MemberPointer(static_cast<unsigned>(count-1)):0;
    At<float>(Manager+132)=1.25f;At<float>(Manager+136)=-2.5f;At<float>(Manager+140)=0;At<float>(Manager+144)=1;
    for(unsigned base:{164u,228u}) for(unsigned i=0;i<16;++i) At<float>(Manager+base+i*4)=i%5==0?1.0f:0.0f;
    ClearOutput();
}
void Read() { SpatialAudioSnapshot(Context()); }
void Rejected(const char* reason) {
    Read();Check(Has(408)&&shared.values[408]==0,reason);
    for(unsigned slot=409;slot<=418;++slot) Check(!Has(slot),"rejected graph leaves dependent values invalid");
    Check(!Own(Outer())&&!Own(Inner()),"rejected capture releases both acquired locks");
}
void NoActive(const char* reason) {
    Read();Check(Has(408)&&shared.values[408]==1&&Has(409)&&Has(412),reason);
    for(unsigned slot=413;slot<=418;++slot) Check(!Has(slot),"invalid selected/cache suppresses all active fields");
    Check(!Own(Outer())&&!Own(Inner()),"structural snapshot releases locks");
}
bool FaultRead() {
    __try { Read(); }
    __except(EXCEPTION_EXECUTE_HANDLER) { return true; }
    return false;
}
struct Busy { CRITICAL_SECTION* cs;HANDLE ready,release; };
DWORD WINAPI Hold(void* value) {
    auto item=static_cast<Busy*>(value);EnterCriticalSection(item->cs);SetEvent(item->ready);
    WaitForSingleObject(item->release,5000);LeaveCriticalSection(item->cs);return 0;
}
void RealBusy(CRITICAL_SECTION* cs) {
    Busy item{cs,CreateEventW(nullptr,TRUE,FALSE,nullptr),CreateEventW(nullptr,TRUE,FALSE,nullptr)};
    HANDLE thread=CreateThread(nullptr,0,Hold,&item,0,nullptr);
    const bool acquired=thread&&WaitForSingleObject(item.ready,1000)==WAIT_OBJECT_0;
    Check(acquired,"busy fixture acquires native Win32 lock on another thread");
    if(acquired) { const ULONGLONG start=GetTickCount64();Rejected("real busy lock rejects snapshot");Check(GetTickCount64()-start<1000,"busy snapshot never waits for lock owner"); }
    SetEvent(item.release);if(thread) { WaitForSingleObject(thread,5000);CloseHandle(thread); }
    CloseHandle(item.ready);CloseHandle(item.release);
}
bool AvailableOnOtherThread(CRITICAL_SECTION* cs) {
    Busy item{cs,CreateEventW(nullptr,TRUE,FALSE,nullptr),CreateEventW(nullptr,TRUE,FALSE,nullptr)};
    HANDLE thread=CreateThread(nullptr,0,Hold,&item,0,nullptr);
    const bool acquired=thread&&WaitForSingleObject(item.ready,1000)==WAIT_OBJECT_0;
    SetEvent(item.release);if(thread) { WaitForSingleObject(thread,5000);CloseHandle(thread); }
    CloseHandle(item.ready);CloseHandle(item.release);return acquired;
}
}

int main() {
    using namespace spatial_audio;
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,ImageSize,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    if(!g_base) return 2;
    InitializeCriticalSection(Outer());InitializeCriticalSection(Inner());
    Setup();Read();
    for(unsigned slot=408;slot<=418;++slot) Check(Has(slot),"all11 diagnostic values available on valid graph");
    Check(shared.values[408]==1&&shared.values[409]==3&&shared.values[410]==8&&shared.values[411]==3&&shared.values[412]==3,"structural fields match native list");
    Check(shared.values[413]==3&&shared.values[414]==3&&shared.values[415]==20,"selected ID/kind/priority match enabled unsigned winner");
    Check(shared.values[416]==1.25&&shared.values[417]==-2.5&&shared.values[418]==0,"cached native position includes a valid zero coordinate");
    Check(tries==2&&tried[0]==reinterpret_cast<uintptr_t>(Outer())&&tried[1]==reinterpret_cast<uintptr_t>(Inner()),"global lock acquired before manager lock");
    Check(releases==2&&released[0]==reinterpret_cast<uintptr_t>(Inner())&&released[1]==reinterpret_cast<uintptr_t>(Outer()),"captured manager lock released before global");
    Check(!publicationLocked&&!Own(Outer())&&!Own(Inner()),"IPC publication follows all unlocks");
    Check(At<BYTE>(Manager+816)==1,"snapshot does not write the native lock flag");
    for(BYTE kind:{BYTE(1),BYTE(2),BYTE(3)}) {
        Setup(1);SeedMember(0,kind,UINT32_MAX,UINT32_MAX);Read();
        Check(Has(414)&&shared.values[414]==kind&&shared.values[413]==4294967295.0&&shared.values[415]==4294967295.0,"all exact native kinds and full unsigned IDs/priorities supported");
    }
    Setup(1);At<BYTE>(Members+9)=0xff;At<BYTE>(Members+10)=0xee;At<BYTE>(Members+11)=0xdd;Read();Check(Has(414)&&shared.values[414]==1,"kind reads one byte and ignores adjacent padding");
    Setup();At<uint32_t>(Members+120)=0x80000000u;At<uintptr_t>(Manager+120)=MemberPointer(0);Read();Check(Has(415)&&shared.values[415]==2147483648.0,"unsigned priority above INT_MAX wins over positive signed values");
    Setup();for(unsigned i=0;i<3;++i) At<uint32_t>(Members+i*256+120)=7;Read();Check(shared.values[413]==3,"later member wins an equal priority");
    Setup();for(unsigned i=0;i<3;++i) At<uint32_t>(Members+i*256+120)=7;At<uintptr_t>(Manager+120)=MemberPointer(0);NoActive("earlier tied member is not a current selected winner");
    Setup();At<BYTE>(Members+2*256+132)=0;At<uintptr_t>(Manager+120)=MemberPointer(1);Read();Check(shared.values[412]==2&&shared.values[413]==2,"disabled highest priority is skipped");
    Setup();At<BYTE>(Members+2*256+132)=0xfe;At<uintptr_t>(Manager+120)=MemberPointer(1);Read();Check(shared.values[412]==2&&shared.values[413]==2,"only enabled bit0 participates in selection");
    Setup(1);At<uint32_t>(Members+120)=0;At<float>(Manager+132)=At<float>(Manager+136)=At<float>(Manager+140)=0;Read();Check(Has(415)&&shared.values[415]==0&&Has(416)&&Has(417)&&Has(418),"zero priority and zero vector are valid measurements");
    Setup(0);Read();Check(Has(409)&&shared.values[409]==0&&Has(412)&&shared.values[412]==0&&!Has(413),"empty list preserves valid zero structural counts with no active listener");
    Setup();for(unsigned i=0;i<3;++i) At<BYTE>(Members+i*256+132)=0;NoActive("no enabled listeners keeps structural graph available");
    Setup();At<uintptr_t>(Manager+120)=0;NoActive("selected null does not manufacture active zero values");
    Setup();poison=1;At<uintptr_t>(Manager+120)=poison;NoActive("freed selected pointer is compared without dereference");Check(poisonReads==0,"nonmember selected pointer never enters Readable or member field access");
    Setup();At<uintptr_t>(Manager+120)=MemberPointer(0);NoActive("registered but outdated selected priority winner is unavailable");
    Setup();At<int>(Manager+28)=8;Read();Check(shared.values[411]==8,"peak may exceed current count up to capacity");
    Setup(1024,1024);Read();Check(Has(408)&&shared.values[409]==1024&&shared.values[413]==1024,"full bounded1024-member list supported");

    for(int value:{-1,1025}) { Setup();At<int>(Manager+24)=value;Rejected("negative/oversized count rejected"); }
    Setup();At<int>(Manager+24)=9;Rejected("count above capacity rejected");
    for(int value:{-1,0,1025}) { Setup();At<int>(Manager+32)=value;Rejected("capacity outside1..1024 rejected"); }
    for(int value:{-1,2,9}) { Setup();At<int>(Manager+28)=value;Rejected("peak below count or above capacity rejected"); }
    for(unsigned index:{0u,1u,2u}) {
        Setup();At<uintptr_t>(PointerList+index*8)=0;Rejected("every counted member must be nonnull");
        Setup();At<uint32_t>(Members+index*256+12)=0;Rejected("every counted ID must be nonzero");
        Setup();At<uintptr_t>(Members+index*256+16)=g_base+Manager+8;Rejected("every counted owner backlink validated");
        Setup();At<uintptr_t>(Members+index*256)=0;Rejected("every member requires known vtable");
        Setup();At<BYTE>(Members+index*256+8)=7;Rejected("every member requires exact BYTE kind");
    }
    Setup();At<uintptr_t>(PointerList+8)=MemberPointer(0);Rejected("duplicate pointer rejected");
    Setup();At<uint32_t>(Members+256+12)=1;Rejected("duplicate ID on distinct pointer rejected");
    Setup();At<BYTE>(Members+2*256+8)=2;Rejected("vtable and kind must agree");
    Setup();denied=MemberPointer(2)+136;deniedSize=48;Rejected("line listener requires full184-byte range");
    Setup(1);denied=MemberPointer(0)+136;deniedSize=48;Read();Check(Has(413),"base listener requires only136 bytes");
    Setup(1);SeedMember(0,2,1,0);denied=MemberPointer(0)+136;deniedSize=48;Read();Check(Has(413),"point listener requires only136 bytes");
    Setup();denied=g_base+PointerList+7*8;deniedSize=8;Rejected("full capacity array is validated beyond counted prefix");
    Setup();At<uintptr_t>(Manager+768)=UINTPTR_MAX-7;Rejected("overflowing list address rejected");
    Setup();At<uintptr_t>(PointerList)=UINTPTR_MAX-8;Rejected("overflowing member address rejected");
    Setup();At<uintptr_t>(ManagerRva)=UINTPTR_MAX-10;Rejected("overflowing manager address rejected before TryEnter");Check(tries==1,"invalid manager never attempts inner lock");
    Setup();At<uintptr_t>(LayoutRva)=0;Rejected("absent layout rejected");
    Setup();At<uintptr_t>(ManagerRva)=0;Rejected("absent manager rejected");
    Setup();At<uintptr_t>(Manager)=g_base+0x61A5B0;Rejected("destructing interface vtable rejected despite lock flag1");Check(tries==1,"destructing manager lock not attempted");
    Setup();At<uintptr_t>(Layout)=0;Rejected("foreign layout vtable rejected");
    Setup();At<uintptr_t>(Manager+8)=0;Rejected("manager/layout backlink required");
    Setup();At<uintptr_t>(Layout+8)=0;Rejected("layout/manager backlink required");
    for(BYTE value:{BYTE(0),BYTE(2)}) { Setup();At<BYTE>(Manager+816)=value;Rejected("lock flag must be exact1");Check(tries==1,"invalid lock flag prevents inner TryEnter"); }
    Setup();denied=g_base+Manager+991;deniedSize=1;Rejected("entire manager allocation readable before lock");
    Setup();denied=g_base+Layout+1439;deniedSize=1;Rejected("entire layout allocation readable before lock");
    Setup();At<uintptr_t>(audio_mix::DriverRva)=0;Rejected("audio driver lifetime gate required");
    Setup();At<BYTE>(0x100000+52)=0;Rejected("disabled driver rejects stale listener graph");
    Setup();At<uintptr_t>(audio_mix::MasterRva)=0;Rejected("dead master graph rejected");
    Setup();At<uintptr_t>(0x101000+336)=0;Rejected("mismatched existing audio graph rejected");

    for(unsigned offset=132;offset<148;offset+=4) { Setup();At<float>(Manager+offset)=std::numeric_limits<float>::quiet_NaN();NoActive("all cached position components must be finite"); }
    for(unsigned offset=164;offset<292;offset+=4) { Setup();At<float>(Manager+offset)=std::numeric_limits<float>::infinity();NoActive("both cached transform matrices must be finite"); }
    Setup();At<float>(Manager+148)=std::numeric_limits<float>::quiet_NaN();Read();Check(Has(413),"unproven manager+148 field is not misread as velocity or used as a gate");
    Setup();At<float>(Members+2*256+56)=std::numeric_limits<float>::quiet_NaN();Read();Check(Has(413),"latest listener matrix is not falsely substituted for finite cached last-update position");

    Setup();g_gameThread=0;Rejected("missing app thread rejects before any lock");Check(tries==0,"thread gate precedes locks");
    Setup();++g_gameThread;Rejected("wrong app thread rejected");
    Setup();g_disabled=1;Rejected("disabled bridge rejected");
    Setup();g_shared=nullptr;Rejected("missing host mapping rejected");
    Setup();shared.hostHeartbeat=0;Rejected("zero host heartbeat rejected");
    Setup();fakeNow+=5001;Rejected("expired host heartbeat rejected");
    Setup();shared.hostHeartbeat=fakeNow+1;Rejected("future heartbeat not mistaken for fresh");
    Setup();fakeNow+=5000;Read();Check(Has(413),"exact5000ms heartbeat boundary accepted");
    Setup();fakeNow=15;shared.hostHeartbeat=UINT32_MAX-100;Read();Check(Has(413),"DWORD heartbeat wrap handled by existing audio gate");
    Setup();auto context=Context();context.base+=8;SpatialAudioSnapshot(context);Check(Has(408)&&shared.values[408]==0&&!Has(409)&&tries==0,"foreign module context rejected");
    Setup();denied=reinterpret_cast<uintptr_t>(Outer());deniedSize=sizeof(CRITICAL_SECTION);Rejected("unreadable outer lock gate");Check(tries==0,"unreadable global lock not entered");
    Setup();readOnly=reinterpret_cast<uintptr_t>(Outer());readOnlySize=sizeof(CRITICAL_SECTION);Rejected("readable but read-only global CS rejected");Check(tries==0,"read-only global CS never passed to TryEnter");
    Setup();readOnly=reinterpret_cast<uintptr_t>(Inner());readOnlySize=sizeof(CRITICAL_SECTION);Rejected("readable but read-only manager CS rejected");Check(tries==1&&releases==1,"read-only manager CS never passed to TryEnter and outer is released");
    Setup();busyOuter=true;Rejected("busy outer lock rejected");Check(tries==1&&releases==0,"failed outer acquisition releases nothing");
    Setup();busyInner=true;Rejected("busy manager lock rejected");Check(tries==2&&releases==1&&released[0]==reinterpret_cast<uintptr_t>(Outer()),"failed inner acquisition releases only outer");
    Setup();RealBusy(Outer());Setup();RealBusy(Inner());
    for(unsigned mutation=1;mutation<=9;++mutation) {
        Setup();mutateOnInner=mutation;Rejected("roots/readiness/host revalidated after inner acquisition");
        Check(releases==2&&released[0]==reinterpret_cast<uintptr_t>(Inner())&&released[1]==reinterpret_cast<uintptr_t>(Outer()),"captured locks released despite changed roots or flag");
    }
    Setup();faultAt=MemberPointer(2);Check(FaultRead(),"fault on last member propagates after cleanup");
    Check(Has(408)&&shared.values[408]==0&&!Has(409)&&!Own(Outer())&&!Own(Inner())&&releases==2,"fault cannot publish partial graph and releases both locks");
    Check(AvailableOnOtherThread(Outer())&&AvailableOnOtherThread(Inner()),"both locks usable by another thread after read fault");
    Setup();throwTryInner=true;Check(FaultRead()&&releases==1&&!Own(Outer()),"inner TryEnter fault still releases acquired outer lock");
    Setup();throwLeaveInner=true;Check(FaultRead()&&releases==2&&!Own(Outer())&&!Own(Inner()),"outer finally still runs if inner release raises");
    Setup();Read();const unsigned reads=readCalls;
    for(unsigned fault=1;fault<=reads;++fault) {
        Setup();faultReadCount=fault;
        Check(FaultRead(),"each Readable-call fault propagates");
        Check(!Own(Outer())&&!Own(Inner())&&!Has(409),"every read-fault position leaves no lock or partial structural publication");
    }
    Setup();Read();ClearOutput();At<uintptr_t>(ManagerRva)=0;Read();Check(Has(408)&&shared.values[408]==0&&!Has(413)&&shared.values[413]==-9999,"fresh snapshot validity never substitutes old ID or zero after destruction");
    Setup();BYTE nativeBefore[992];memcpy(nativeBefore,reinterpret_cast<void*>(g_base+Manager),sizeof(nativeBefore));Read();
    Check(!memcmp(nativeBefore,reinterpret_cast<void*>(g_base+Manager),776)&&!memcmp(nativeBefore+816,reinterpret_cast<void*>(g_base+Manager+816),992-816),"all manager data outside OS lock remain unchanged");
    Setup();SpatialAudioCapabilities();
    for(unsigned slot=0;slot<512;++slot) Check(((shared.supported[slot/64]>>(slot%64))&1)==static_cast<uint64_t>(slot>=408&&slot<=418),"capabilities expose exactly408..418 and leave419..423 unused");
    DeleteCriticalSection(Inner());DeleteCriticalSection(Outer());VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);
    printf("Spatial audio guard tests: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
