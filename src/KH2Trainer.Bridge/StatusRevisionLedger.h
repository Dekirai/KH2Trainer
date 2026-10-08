#pragma once
#include <stdint.h>
#include <stddef.h>

// Pure ownership metadata for the retail STATUS pool. This is a prerequisite,
// not a live observer: callers must first install and verify the complete native
// entry set, serialize notifications, and validate the actual pool allocation.
// No native pointer is retained or dereferenced and no STATUS bytes are written.
namespace status_revision {
constexpr unsigned SlotCount=80, FieldCount=5, FrameCapacity=32;
constexpr uint32_t AllFields=(1u<<FieldCount)-1;
enum Field : unsigned { General=0, Draw=1, Jackpot=2, Lucky=3, Retention=4 };
enum class Health : unsigned { Uninstalled=0, Observing=1, Fault=2 };
enum class Life : unsigned { Unknown=0, Allocated=1, Retired=2 };
enum class Event : unsigned { Initialize, Rebuild, GeneralWrite, PoolReset, Release, ManualWrite };
enum class Match : unsigned { Current, Superseded, AllocationEnded, Unavailable };
struct Stamp {
    uint64_t instance=0, poolEpoch=0, allocation=0;
    uint64_t fields[FieldCount]{};
    unsigned slot=SlotCount;
};
struct Observation {
    Match result=Match::Unavailable;
    uint32_t changedFields=0;
};
struct Frame {
    uint64_t ticket=0;
    uint32_t thread=0;
    unsigned index=FrameCapacity;
};

class Ledger {
#ifdef KH2_STATUS_REVISION_TESTS
    friend struct LedgerTestAccess;
#endif
    struct Slot {
        Life life=Life::Unknown;
        uint64_t allocation=0, fields[FieldCount]{};
    };
    Slot slots[SlotCount]{};
    Frame frames[FrameCapacity]{};
    Health health=Health::Uninstalled;
    uint64_t instance=0, epoch=0, serial=0;
    unsigned activeCalls=0;

    uint64_t Next() noexcept {
        if(serial==UINT64_MAX) { Fault();return 0; }
        return ++serial;
    }
    bool Allocate(unsigned index) noexcept {
        const uint64_t value=Next();if(!value)return false;
        auto& s=slots[index];s.life=Life::Allocated;s.allocation=value;
        for(auto& field:s.fields)field=value;
        return true;
    }
    bool Write(unsigned index,uint32_t mask) noexcept {
        if(!mask || (mask&~AllFields) || slots[index].life==Life::Retired) { Fault();return false; }
        // A preexisting allocation can first appear through a native rebuild.
        // Capture still requires an independent, current PoolOwns/backlink check.
        if(slots[index].life==Life::Unknown && !Allocate(index))return false;
        const uint64_t value=Next();if(!value)return false;
        for(unsigned i=0;i<FieldCount;++i)if(mask&(1u<<i))slots[index].fields[i]=value;
        return true;
    }
public:
    Health Status() const noexcept { return health; }
    unsigned ActiveCalls() const noexcept { return activeCalls; }
    uint64_t Instance() const noexcept { return instance; }
    uint64_t PoolEpoch() const noexcept { return epoch; }
    Life SlotLife(unsigned slot) const noexcept { return slot<SlotCount?slots[slot].life:Life::Unknown; }
    void Fault() noexcept { health=Health::Fault; }

    // Exactly once per object/process instance. A fault cannot be reset to hide
    // a period in which native writes were unobserved. Never use a saved nonce.
    bool Start(uint64_t bridgeInstance) noexcept {
        if(health!=Health::Uninstalled || !bridgeInstance) { Fault();return false; }
        instance=bridgeInstance;epoch=Next();
        if(!epoch)return false;
        health=Health::Observing;return true;
    }

    // Before the original native call, even if that call will early-return or
    // throw. parameter is the signed coefficient index or pre-release refcount.
    // Native motion events can enter the VM on worker threads. Notifications
    // from every thread must be serialized by the caller, but the lock must be
    // released before calling the native original. Cross-thread exits may occur
    // in either order; only a single thread's nested calls must follow LIFO.
    // All callbacks continue to forward the original even when Enter fails.
    Frame Enter(Event event,unsigned slot,int parameter=0,uint32_t mask=0,uint32_t threadId=1) noexcept {
        if(health!=Health::Observing)return {};
        if(!threadId || activeCalls==FrameCapacity ||
           (event!=Event::PoolReset && slot>=SlotCount)) { Fault();return {}; }
        if(event<Event::Initialize || event>Event::ManualWrite ||
           (event==Event::PoolReset && slot!=SlotCount) ||
           (event!=Event::ManualWrite && mask) ||
           (event!=Event::GeneralWrite && event!=Event::Release && parameter)) { Fault();return {}; }
        const uint64_t ticket=Next();if(!ticket)return {};
        unsigned index=0;while(index<FrameCapacity && frames[index].ticket)++index;
        if(index==FrameCapacity) { Fault();return {}; }
        const Frame entered{ticket,threadId,index};frames[index]=entered;++activeCalls;
        switch(event) {
        case Event::Initialize:
            Allocate(slot);break;
        case Event::Rebuild:
            Write(slot,AllFields);break;
        case Event::GeneralWrite:
            // Native 3C2650 has no signed-index bound. An unexpected index can
            // alias fields outside the coefficient array: confidence is lost.
            if(parameter<0 || parameter>6)Fault();
            else if(parameter==6)Write(slot,1u<<General);
            break;
        case Event::PoolReset: {
            const uint64_t value=Next();if(!value)break;
            epoch=value;
            for(auto& s:slots) { s.life=Life::Retired;s.allocation=0;for(auto& field:s.fields)field=0; }
            break;
        }
        case Event::Release:
            if(parameter<=0)Fault();
            else if(parameter==1) {
                // This invalidates before a potentially failing native saveback.
                // It says nothing about the corresponding Actor's lifetime.
                auto& s=slots[slot];s.life=Life::Retired;s.allocation=0;
                for(auto& field:s.fields)field=0;
            }
            break;
        case Event::ManualWrite:
            Write(slot,mask);break;
        }
        return entered;
    }
    // Call from the wrapper's finally path, including native exceptions. Pass
    // !AbnormalTermination(): a failed native release/reset may leave allocation
    // intact even though its before-entry metadata was already invalidated.
    // This never handles or converts the original exception into success.
    void Exit(Frame frame,bool completedNormally=true) noexcept {
        if(!completedNormally)Fault();
        if(!frame.ticket) { if(frame.thread || frame.index!=FrameCapacity)Fault();return; }
        if(!activeCalls || frame.index>=FrameCapacity || !frame.thread ||
           frames[frame.index].ticket!=frame.ticket || frames[frame.index].thread!=frame.thread) { Fault();return; }
        for(const auto& active:frames)if(active.thread==frame.thread && active.ticket>frame.ticket) { Fault();return; }
        frames[frame.index]={};--activeCalls;
    }

    // The actual pool/free-list, refcount and Actor backlink must have just been
    // validated by the caller, on the engine thread with no native call between
    // that validation and Capture. Unknown entries allow bootstrap adoption;
    // retired entries require an observed Initialize, never pointer reuse alone.
    bool Capture(unsigned slot,Stamp& output,bool allocationValidated,bool onGameThread=true) noexcept {
        output={};
        if(health!=Health::Observing)return false;
        if(!onGameThread || slot>=SlotCount) { Fault();return false; }
        if(activeCalls || !allocationValidated)return false;
        if(slots[slot].life==Life::Retired) { Fault();return false; }
        if(slots[slot].life==Life::Unknown && !Allocate(slot))return false;
        const auto& s=slots[slot];output.instance=instance;output.poolEpoch=epoch;
        output.allocation=s.allocation;output.slot=slot;
        for(unsigned i=0;i<FieldCount;++i)output.fields[i]=s.fields[i];
        return true;
    }

    // Does not inspect live STATUS memory. The caller must additionally bind an
    // Actor generation, current role/context, exact scalar bits and writability.
    Observation Compare(const Stamp& captured,uint32_t mask) const noexcept {
        if(health!=Health::Observing || activeCalls || !mask || (mask&~AllFields) ||
           !captured.instance || captured.instance!=instance || !captured.poolEpoch ||
           !captured.allocation || captured.slot>=SlotCount)return {};
        for(unsigned i=0;i<FieldCount;++i)if((mask&(1u<<i)) && !captured.fields[i])return {};
        const auto& s=slots[captured.slot];
        if(captured.poolEpoch!=epoch || s.life==Life::Retired ||
           (s.life==Life::Allocated && captured.allocation!=s.allocation))
            return {Match::AllocationEnded,mask};
        if(s.life!=Life::Allocated)return {};
        uint32_t changed=0;
        for(unsigned i=0;i<FieldCount;++i)if((mask&(1u<<i)) && captured.fields[i]!=s.fields[i])changed|=1u<<i;
        return {changed?Match::Superseded:Match::Current,changed};
    }
};
}
