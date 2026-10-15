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

// The feature is compiled exactly as shipped: there are no feature test hooks.
// Only surrounding memory/time adapters use synthetic state.
namespace {
struct TrainerContext { uintptr_t base,player,status; bool sceneReady; };
struct TrainerResult { int code; const wchar_t* text; };
struct Shared { DWORD hostHeartbeat; double values[512]; uint64_t valid[8],supported[8]; } shared{},otherShared{};
uintptr_t g_base=0,allocation=0;
Shared* g_shared=&shared;
DWORD g_gameThread=0,fakeNow=100000;
volatile LONG g_disabled=0;
unsigned nowCalls=0,scalarChecks=0,unknownReads=0,publications=0;
unsigned mutateScalarCheck=0,finalContextMutation=0;
uintptr_t denied=0;SIZE_T deniedSize=0;
int mutationField=0;int32_t mutationValue=0;
DWORD Now() {
    if(++nowCalls==2) {
        if(finalContextMutation==1)shared.hostHeartbeat=0;
        if(finalContextMutation==2)shared.hostHeartbeat=fakeNow-5001;
        if(finalContextMutation==3)g_disabled=1;
        if(finalContextMutation==4)g_shared=&otherShared;
    }
    return fakeNow;
}
#define GetTickCount Now
bool Readable(const void*,SIZE_T);
void SnapshotValue(unsigned slot,double value) {
    ++publications;
    if(slot<512&&std::isfinite(value)) {g_shared->values[slot]=value;g_shared->valid[slot/64]|=uint64_t(1)<<(slot%64);}
}
void SupportCapability(unsigned slot) {g_shared->supported[slot/64]|=uint64_t(1)<<(slot%64);}
// Any accidental audio locking/call through these helpers must fail to compile.
#define TryEnterCriticalSection AudioRequestMustNotCallTryEnterCriticalSection
#define EnterCriticalSection AudioRequestMustNotCallEnterCriticalSection
#define LeaveCriticalSection AudioRequestMustNotCallLeaveCriticalSection
#define DecodePacked AudioRequestMustNotDecodePointers
#include "../../src/KH2Trainer.Bridge/AudioRequestFeatures.inl"
#undef TryEnterCriticalSection
#undef EnterCriticalSection
#undef LeaveCriticalSection
#undef DecodePacked

template<class T> T& Field(uintptr_t rva) {return *reinterpret_cast<T*>(allocation+rva);}
bool Overlap(uintptr_t a,SIZE_T n,uintptr_t b,SIZE_T m) {return a<b+m&&b<a+n;}
bool Readable(const void* p,SIZE_T n) {
    const uintptr_t a=reinterpret_cast<uintptr_t>(p);
    bool scalar=false,known=false;
    for(const auto& code:audio_request_signatures::Writers)
        if(a==allocation+code.rva&&n==code.size)known=true;
    for(const auto& span:std::initializer_list<std::pair<uintptr_t,SIZE_T>>{
        {audio_requests::FreeRva,4},{audio_requests::InhibitRva,1},{audio_requests::IntervalRva,4}})
        if(a==allocation+span.first&&n==span.second)scalar=known=true;
    if(scalar&&++scalarChecks==mutateScalarCheck) {
        if(mutationField==0)Field<int32_t>(audio_requests::FreeRva)=mutationValue;
        else if(mutationField==1)Field<int32_t>(audio_requests::IntervalRva)=mutationValue;
        else if(mutationField==2)Field<BYTE>(audio_requests::InhibitRva)=static_cast<BYTE>(mutationValue);
        else if(mutationField==3)shared.hostHeartbeat=0;
        else if(mutationField==4)g_disabled=1;
        else if(mutationField==5)g_gameThread=0;
    }
    if(!known)++unknownReads;
    return known&&(!denied||!Overlap(a,n,denied,deniedSize));
}
unsigned checks=0,failures=0;
void Check(bool ok,const char* text){++checks;if(!ok){++failures;printf("FAIL: %s\n",text);}}
TrainerContext Context(){return {g_base,UINTPTR_MAX,UINTPTR_MAX,false};}
bool Has(unsigned slot){return (shared.valid[slot/64]&(uint64_t(1)<<(slot%64)))!=0;}
void Setup(int32_t free=80,int32_t interval=0,BYTE inhibit=0) {
    g_base=allocation;g_shared=&shared;shared={};otherShared={};g_disabled=0;g_gameThread=GetCurrentThreadId();
    fakeNow=100000;shared.hostHeartbeat=fakeNow;otherShared.hostHeartbeat=fakeNow;
    denied=0;deniedSize=0;nowCalls=scalarChecks=unknownReads=publications=0;
    mutateScalarCheck=finalContextMutation=0;mutationField=0;mutationValue=0;
    Field<int32_t>(audio_requests::FreeRva)=free;Field<int32_t>(audio_requests::IntervalRva)=interval;Field<BYTE>(audio_requests::InhibitRva)=inhibit;
    for(const auto& code:audio_request_signatures::Writers)memcpy(reinterpret_cast<void*>(allocation+code.rva),code.bytes,code.size);
}
void Rejected(const TrainerContext& c,const char* why) {
    AudioRequestSnapshot(c);
    Check(!Has(482)&&!Has(483)&&!Has(484)&&publications==0,why);
    Check(unknownReads==0,"snapshot never probes non-scalar audio/Actor/request storage");
}
void Accepted(int32_t free,int32_t interval,BYTE inhibit) {
    BYTE before[56];memcpy(before,reinterpret_cast<void*>(allocation+audio_requests::FreeRva),sizeof(before));
    AudioRequestSnapshot(Context());
    const unsigned expected=(inhibit?1u:0u)|(free<=16?2u:0u)|(interval>24?4u:0u);
    Check(Has(482)&&Has(483)&&Has(484)&&publications==3,"all three observations publish together");
    Check(shared.values[482]==free&&shared.values[483]==interval&&shared.values[484]==expected,"exact counters and all native admission causes");
    Check(!memcmp(before,reinterpret_cast<void*>(allocation+audio_requests::FreeRva),sizeof(before)),"counter/control span remains byte-for-byte unchanged");
    Check(unknownReads==0&&scalarChecks==6&&nowCalls==2,"only two scalar copies and renewed host validation are used");
}
}
int main() {
    allocation=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,0xAD9400,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(!allocation)return 2;
    // Fixture contains no usable Actor, camera, bank, resource, request graph or
    // executable native body. Readable whitelists only code and nine scalar bytes.
    for(int32_t free=0;free<=80;++free)for(int32_t interval=0;interval<=25;++interval)for(BYTE inhibit=0;inhibit<=1;++inhibit){Setup(free,interval,inhibit);Accepted(free,interval,inhibit);}
    for(int32_t bad:{INT32_MIN,-1,81,INT32_MAX}){Setup(bad);Rejected(Context(),"out-of-range free count rejected");}
    for(int32_t bad:{INT32_MIN,-1,26,INT32_MAX}){Setup(80,bad);Rejected(Context(),"out-of-range reservation counter rejected");}
    for(unsigned bad=2;bad<=255;++bad){Setup(80,0,static_cast<BYTE>(bad));Rejected(Context(),"non-boolean inhibit rejected");}
    for(const auto& span:std::initializer_list<std::pair<uintptr_t,SIZE_T>>{{audio_requests::FreeRva,4},{audio_requests::InhibitRva,1},{audio_requests::IntervalRva,4}})
        for(SIZE_T i=0;i<span.second;++i){Setup();denied=allocation+span.first+i;deniedSize=1;Rejected(Context(),"each scalar byte must be readable");}
    for(const auto& code:audio_request_signatures::Writers){
        for(SIZE_T offset=0;offset<code.size;++offset){Setup();*reinterpret_cast<BYTE*>(allocation+code.rva+offset)^=1;Rejected(Context(),"every writer signature byte is checked");}
        Setup();denied=allocation+code.rva+code.size-1;deniedSize=1;Rejected(Context(),"entire writer signature must be readable");
    }
    Setup();g_shared=nullptr;Rejected(Context(),"missing shared state");
    Setup();g_disabled=1;Rejected(Context(),"disabled bridge");
    Setup();g_gameThread=0;Rejected(Context(),"unbound update thread");
    Setup();g_gameThread=GetCurrentThreadId()+1;Rejected(Context(),"wrong update thread");
    Setup();auto c=Context();++c.base;Rejected(c,"context image differs");
    Setup();g_base=0;Rejected(Context(),"no image");
    Setup();g_base=UINTPTR_MAX;Rejected(Context(),"image arithmetic overflow rejected");
    Setup();shared.hostHeartbeat=0;Rejected(Context(),"missing heartbeat");
    Setup();shared.hostHeartbeat=fakeNow-5001;Rejected(Context(),"expired heartbeat");
    Setup();shared.hostHeartbeat=fakeNow-5000;Accepted(80,0,0);
    Setup();fakeNow=2000;shared.hostHeartbeat=UINT32_MAX-1999;Accepted(80,0,0);
    Setup();fakeNow=2000;shared.hostHeartbeat=UINT32_MAX-4000;Rejected(Context(),"heartbeat expiry is wrap-aware");
    // Any field changed between copies must discard the complete tuple.
    for(int field=0;field<3;++field)for(unsigned probe=4;probe<=6;++probe){
        Setup();mutationField=field;mutationValue=field==0?79:1;mutateScalarCheck=probe;Rejected(Context(),"second-copy change rejects all three values");
    }
    // Invalid values appearing during either preflight are rejected, rather
    // than clamped or converted into a measured zero.
    for(int field=0;field<3;++field)for(unsigned probe=1;probe<=6;++probe){
        Setup();mutationField=field;mutationValue=field==0?-1:field==1?26:2;mutateScalarCheck=probe;Rejected(Context(),"invalid first/second read change rejects sample");
    }
    for(int field=3;field<=5;++field)for(unsigned probe=1;probe<=6;++probe){Setup();mutationField=field;mutateScalarCheck=probe;Rejected(Context(),"host/disable/thread loss during either copy prevents publication");}
    for(unsigned mutation=1;mutation<=4;++mutation){Setup();finalContextMutation=mutation;Rejected(Context(),"final context/host loss prevents publication");}
    Setup();AudioRequestCapabilities();for(unsigned slot=0;slot<512;++slot)Check(bool(shared.supported[slot/64]&(uint64_t(1)<<(slot%64)))==(slot>=482&&slot<=484),"exact capability allocation");
    for(unsigned slot=481;slot<=485;++slot){Setup();double arguments[8]{std::numeric_limits<double>::quiet_NaN()};TrainerResult result{};BYTE before[56];memcpy(before,reinterpret_cast<void*>(allocation+audio_requests::FreeRva),sizeof(before));
        const bool handled=AudioRequestHandle(Context(),slot,arguments,result);
        Check(handled==(slot>=482&&slot<=484),"only allocated readouts are claimed");
        if(handled)Check(result.code==1&&wcsstr(result.text,L"read-only"),"readout command explicitly rejected");
        Check(!memcmp(before,reinterpret_cast<void*>(allocation+audio_requests::FreeRva),sizeof(before))&&publications==0&&scalarChecks==0,"read-only rejection never touches request state");
    }
    printf("AudioRequestGuardTests: %u checks, %u failures. Synthetic scalar memory; no original code executed.\n",checks,failures);
    VirtualFree(reinterpret_cast<void*>(allocation),0,MEM_RELEASE);return failures?1:0;
}
