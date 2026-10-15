// Read-only observations of the resident audio request pool's admission counters.
// No resource/list/Actor dereference or native audio call. Equal copies are a
// bounded sample, not a lock, ABA detector or promise of successful playback.
#include "AudioRequestSignatures.h"
namespace audio_requests {
constexpr uintptr_t FreeRva=0xAD9390, InhibitRva=0xAD93C0, IntervalRva=0xAD93C4;
constexpr unsigned FreeSlot=482,IntervalSlot=483,GatesSlot=484;
struct Sample { int32_t free,interval; BYTE inhibit; };

bool ContextReady(const TrainerContext& c) {
    if(!g_base || c.base!=g_base || !g_gameThread || GetCurrentThreadId()!=g_gameThread ||
       InterlockedCompareExchange(&g_disabled,0,0) || !g_shared) return false;
    const auto* observedShared=g_shared;
    const DWORD now=GetTickCount();
    if(g_shared!=observedShared) return false;
    const DWORD heartbeat=observedShared->hostHeartbeat;
    return heartbeat && static_cast<DWORD>(now-heartbeat)<=5000 &&
        !InterlockedCompareExchange(&g_disabled,0,0) && c.base==g_base && GetCurrentThreadId()==g_gameThread;
}
bool Span(uintptr_t rva,SIZE_T size) {
    return size && g_base<=UINTPTR_MAX-rva && g_base+rva<=UINTPTR_MAX-size &&
        Readable(reinterpret_cast<const void*>(g_base+rva),size);
}
bool CodeReady() {
    for(const auto& code:audio_request_signatures::Writers)
        if(!Span(code.rva,code.size) || memcmp(reinterpret_cast<const void*>(g_base+code.rva),code.bytes,code.size)) return false;
    return true;
}
bool ReadSample(Sample& s) {
    if(!Span(FreeRva,sizeof(s.free)) || !Span(InhibitRva,sizeof(s.inhibit)) || !Span(IntervalRva,sizeof(s.interval))) return false;
    s.free=*reinterpret_cast<const volatile int32_t*>(g_base+FreeRva);
    s.inhibit=*reinterpret_cast<const volatile BYTE*>(g_base+InhibitRva);
    s.interval=*reinterpret_cast<const volatile int32_t*>(g_base+IntervalRva);
    return s.free>=0 && s.free<=80 && s.interval>=0 && s.interval<=25 && s.inhibit<=1;
}
bool Same(const Sample& a,const Sample& b) { return a.free==b.free && a.interval==b.interval && a.inhibit==b.inhibit; }
unsigned Gates(const Sample& s) { return (s.inhibit?1u:0u)|(s.free<=16?2u:0u)|(s.interval>24?4u:0u); }
}
bool AudioRequestHandle(const TrainerContext&,unsigned slot,const double[8],TrainerResult& result) {
    if(slot<audio_requests::FreeSlot || slot>audio_requests::GatesSlot) return false;
    result={1,L"Audio request observations are read-only."};return true;
}
void AudioRequestCapabilities() {
    for(unsigned slot=audio_requests::FreeSlot;slot<=audio_requests::GatesSlot;++slot) SupportCapability(slot);
}
void AudioRequestSnapshot(const TrainerContext& c) {
    using namespace audio_requests;
    if(!ContextReady(c) || !CodeReady()) return;
    const auto* observedShared=g_shared;
    Sample before{},after{};
    if(!ReadSample(before) || !ReadSample(after) || !Same(before,after) ||
       !ContextReady(c) || g_shared!=observedShared) return;
    // TrainerFrame cleared the three valid bits before this call and publishes
    // the completed snapshot under its existing sequence counter. Never report
    // unavailable observations as measured zero or retain them for later frames.
    SnapshotValue(FreeSlot,after.free);
    SnapshotValue(IntervalSlot,after.interval);
    SnapshotValue(GatesSlot,Gates(after));
}
