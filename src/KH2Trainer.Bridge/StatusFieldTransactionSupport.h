#pragma once
#include <string.h>
#include <math.h>
#include "StatusObserverSupport.h"

// Typed STATUS transactions for the exact retail layout. Not an installer or IPC
// endpoint. The owner must retain the Journal, Observer and Actor provider until
// process exit; only the bound game thread may call Journal methods.
namespace status_fields {
constexpr unsigned FieldCount=status_revision::FieldCount,LeaseCount=32,ReceiptCount=64,ClientCount=16;
constexpr unsigned Offsets[FieldCount]={430,520,568,572,580};
constexpr unsigned Widths[FieldCount]={1,4,4,4,4};
constexpr uint32_t AllFields=status_revision::AllFields;
enum class Role : unsigned { Unknown,Sora,Roxas,Mickey };
enum class ActorState : unsigned { Unavailable,OffCurrent,Current,Retired };
struct ActorInfo { uintptr_t actor=0;Role role=Role::Unknown;bool controllable=false; };
// These are trusted bridge metadata callbacks, not data supplied by an IPC
// client. Inspect must validate the lifetime observer's integrity, generation,
// actual current Actor/role and gameplay gates afresh. Pin must retain exactly
// that generation (including while off-current); Retired is positive lifetime
// evidence, never a synonym for OffCurrent or unavailable. All callbacks execute
// inside the STATUS metadata lock and must not enter game code, reenter the
// Observer/Journal, wait for another native callback, throw, or change game state.
// Integration must establish a noncyclic lock order with Actor lifetime metadata.
// Pin retains the observation token; it is NOT a native Actor reference. The
// integration must also prove that Actor destruction/rebinding cannot race this
// game-thread transaction after Inspect. A generation number alone proves none
// of these conditions.
struct ActorProvider {
    void* context=nullptr;
    ActorState (*inspect)(void*,uint64_t,ActorInfo&) noexcept=nullptr;
    bool (*pin)(void*,uint64_t) noexcept=nullptr;
    void (*unpin)(void*,uint64_t) noexcept=nullptr;
};
enum class Operation : unsigned { Acquire,ReleaseIntent,ManualWrite,QueryOperation,QueryLease,Acknowledge,AcknowledgeLease };
enum class State : unsigned { None,Active,ReleasePending,Released,Superseded,AllocationEnded,BindingChanged,ActorRetired,Uncertain };
enum class Outcome : unsigned { Rejected,Applied,ReleaseAccepted,ManualApplied,OperationObserved,LeaseObserved,Acknowledged,Unknown };
enum class Reason : unsigned {
    None,InvalidRequest,WrongThread,StaleInstance,ObserverUnavailable,ObserverFault,
    ActorUnavailable,NotCurrent,NotControllable,UnsupportedRole,InvalidBinding,
    InvalidValues,NotWritable,ExpectedMismatch,RevisionMismatch,AllocationMismatch,
    Conflict,Capacity,NotOwner,LeaseMissing,ReceiptMissing,RequestIdConflict,RetiredRequest,WriteFault
};
struct Snapshot {
    uint64_t bridgeInstance=0,actorGeneration=0;
    uint32_t mask=0,bits[FieldCount]{};
    status_revision::Stamp stamp{};
};
// Internal C++ API; no ABI/IPC schema is assigned. Unselected bits/revisions in a
// supplied snapshot are ignored; its allocation identity is always checked.
struct Request {
    Operation operation=Operation::Acquire;
    uint64_t clientId=0,opId=0,bridgeInstance=0,ownerId=0,actorGeneration=0;
    uint64_t leaseId=0,leaseRevision=0,targetOpId=0;
    uint32_t mask=0,expectedBits[FieldCount]{},desiredBits[FieldCount]{};
    status_revision::Stamp expectedStamp{};
};
struct Response {
    Outcome outcome=Outcome::Rejected;Reason reason=Reason::None;State state=State::None;
    uint64_t clientId=0,opId=0,bridgeInstance=0,receiptOpId=0,ownerId=0,actorGeneration=0;
    uint64_t leaseId=0,leaseRevision=0;
    uint32_t mask=0,remainingMask=0,restoredMask=0,supersededMask=0;
    uint32_t originalBits[FieldCount]{},appliedBits[FieldCount]{};
};
inline uint32_t Bits(float value) noexcept {uint32_t result;memcpy(&result,&value,4);return result;}
inline float Float(uint32_t bits) noexcept {float value;memcpy(&value,&bits,4);return value;}
inline bool Valid(unsigned field,uint32_t bits) noexcept {
    if(field==status_revision::General)return bits<=255;
    if(field>=FieldCount)return false;
    const float value=Float(bits);
    constexpr float maxima[FieldCount]={255,5000,9,99,1};
    return isfinite(value) && value>=0 && value<=maxima[field];
}
inline bool WritableSpan(uintptr_t address,size_t size) noexcept {
    if(!address || !size || size>UINTPTR_MAX-address)return false;
    const uintptr_t end=address+size;
    while(address<end) {
        MEMORY_BASIC_INFORMATION info{};
        if(VirtualQuery(reinterpret_cast<void*>(address),&info,sizeof(info))!=sizeof(info) ||
           info.State!=MEM_COMMIT || (info.Protect&(PAGE_GUARD|PAGE_NOACCESS)))return false;
        const DWORD access=info.Protect&0xff;
        if(access!=PAGE_READWRITE && access!=PAGE_WRITECOPY &&
           access!=PAGE_EXECUTE_READWRITE && access!=PAGE_EXECUTE_WRITECOPY)return false;
        const uintptr_t region=reinterpret_cast<uintptr_t>(info.BaseAddress);
        if(!info.RegionSize || info.RegionSize>UINTPTR_MAX-region || region+info.RegionSize<=address)return false;
        address=region+info.RegionSize;
    }
    return true;
}
inline bool Terminal(State state) noexcept {
    return state==State::Released || state==State::Superseded || state==State::AllocationEnded || state==State::BindingChanged || state==State::ActorRetired;
}

class Journal {
    struct Lease {
        bool used=false,pinned=false;State state=State::None;Reason reason=Reason::None;
        uint64_t client=0,owner=0,id=0,generation=0,revision=0;
        uint32_t mask=0,remaining=0,restored=0,superseded=0;
        uint32_t original[FieldCount]{},applied[FieldCount]{};
        status_revision::Stamp stamp{};
    };
    struct Receipt {bool used=false;Request request{};Response response{};};
    // Tombstones are monotonic per client and survive acknowledgement. A delayed
    // replay can never become a new write after its receipt was collected.
    struct Client {uint64_t id=0,highWater=0;};
    Lease leases[LeaseCount]{};Receipt receipts[ReceiptCount]{};Client clients[ClientCount]{};
    status_observer::Observer* observer=nullptr;
    ActorProvider actors{};uintptr_t packedBases=0;DWORD gameThread=0;
    uint64_t instance=0,nextLease=0;
#ifdef KH2_STATUS_FIELDS_TESTS
public:
    int testFailAfterWrites=-1,testWriteCalls=0;
private:
#endif
    bool OnThread() const noexcept {return gameThread && gameThread==GetCurrentThreadId();}
    static bool Mutation(Operation operation) noexcept {
        return operation==Operation::Acquire || operation==Operation::ReleaseIntent || operation==Operation::ManualWrite;
    }
    static bool SameStamp(const status_revision::Stamp& a,const status_revision::Stamp& b) noexcept {
        if(a.instance!=b.instance || a.poolEpoch!=b.poolEpoch || a.allocation!=b.allocation || a.slot!=b.slot)return false;
        for(unsigned i=0;i<FieldCount;++i)if(a.fields[i]!=b.fields[i])return false;
        return true;
    }
    static bool Same(const Request& a,const Request& b) noexcept {
        if(a.operation!=b.operation || a.clientId!=b.clientId || a.opId!=b.opId || a.bridgeInstance!=b.bridgeInstance ||
           a.ownerId!=b.ownerId || a.actorGeneration!=b.actorGeneration || a.leaseId!=b.leaseId ||
           a.leaseRevision!=b.leaseRevision || a.targetOpId!=b.targetOpId || a.mask!=b.mask || !SameStamp(a.expectedStamp,b.expectedStamp))return false;
        for(unsigned i=0;i<FieldCount;++i)if(a.expectedBits[i]!=b.expectedBits[i] || a.desiredBits[i]!=b.desiredBits[i])return false;
        return true;
    }
    static bool Encoding(const Request& q) noexcept {
        if(!q.clientId || !q.opId || q.operation>Operation::AcknowledgeLease || (q.mask&~AllFields))return false;
        const bool fieldWrite=q.operation==Operation::Acquire || q.operation==Operation::ManualWrite;
        if(fieldWrite) {
            if(!q.ownerId || !q.actorGeneration || !q.mask || q.leaseId || q.leaseRevision || q.targetOpId)return false;
            for(unsigned i=0;i<FieldCount;++i)if(!(q.mask&(1u<<i)) && (q.expectedBits[i] || q.desiredBits[i]))return false;
            return true;
        }
        if(q.mask || q.actorGeneration || !SameStamp(q.expectedStamp,status_revision::Stamp{}))return false;
        for(unsigned i=0;i<FieldCount;++i)if(q.expectedBits[i] || q.desiredBits[i])return false;
        if(q.operation==Operation::ReleaseIntent || q.operation==Operation::AcknowledgeLease)return q.ownerId && q.leaseId && q.leaseRevision && !q.targetOpId;
        if(q.operation==Operation::QueryLease)return q.ownerId && q.leaseId && !q.leaseRevision && !q.targetOpId;
        return q.targetOpId && !q.ownerId && !q.leaseId && !q.leaseRevision;
    }
    Response Envelope(const Request& q) const noexcept {
        Response r{};r.clientId=q.clientId;r.opId=q.opId;r.bridgeInstance=instance;return r;
    }
    static void Reject(Response& r,Reason why) noexcept {r.outcome=Outcome::Rejected;r.reason=why;}
    Lease* FindLease(uint64_t id) noexcept {for(auto& l:leases)if(l.used && l.id==id)return &l;return nullptr;}
    Receipt* FindReceipt(uint64_t client,uint64_t op) noexcept {
        for(auto& r:receipts)if(r.used && r.request.clientId==client && r.request.opId==op)return &r;
        return nullptr;
    }
    void Describe(const Lease& l,Response& r) const noexcept {
        r.state=l.state;r.reason=l.reason;r.ownerId=l.owner;r.actorGeneration=l.generation;
        r.leaseId=l.id;r.leaseRevision=l.revision;r.mask=l.mask;r.remainingMask=l.remaining;
        r.restoredMask=l.restored;r.supersededMask=l.superseded;
        memcpy(r.originalBits,l.original,sizeof(l.original));memcpy(r.appliedBits,l.applied,sizeof(l.applied));
    }
    void Unpin(Lease& l) noexcept {if(l.pinned){actors.unpin(actors.context,l.generation);l.pinned=false;}}
    bool Bump(Lease& l) noexcept {
        if(l.revision==UINT64_MAX){l.state=State::Uncertain;l.reason=Reason::RevisionMismatch;return false;}
        ++l.revision;return true;
    }
    void Uncertain() noexcept {
        for(auto& l:leases)if(l.used && !Terminal(l.state) && l.state!=State::Uncertain) {
            l.state=State::Uncertain;l.reason=Reason::ObserverFault;Bump(l);
        }
    }
    void Collect() noexcept {
        for(auto& l:leases)if(l.used && Terminal(l.state) && !l.pinned) {
            bool referenced=false;for(const auto& p:receipts)if(p.used && p.response.leaseId==l.id)referenced=true;
            if(!referenced)l=Lease{};
        }
    }
    void Refresh(status_observer::TransactionContext& tx,Lease& l) noexcept {
        if(!l.used || Terminal(l.state) || l.state==State::Uncertain)return;
        const auto match=tx.ledger.Compare(l.stamp,l.remaining);
        if(match.result==status_revision::Match::Unavailable) {l.state=State::Uncertain;l.reason=Reason::ObserverFault;Bump(l);return;}
        if(match.result==status_revision::Match::AllocationEnded) {l.state=State::AllocationEnded;l.remaining=0;Bump(l);Unpin(l);return;}
        if(match.changedFields) {
            l.superseded|=match.changedFields;l.remaining&=~match.changedFields;Bump(l);
            if(!l.remaining){l.state=State::Superseded;Unpin(l);return;}
        }
        ActorInfo info{};const auto actor=actors.inspect(actors.context,l.generation,info);
        if(actor==ActorState::Retired){l.state=State::ActorRetired;l.remaining=0;Bump(l);Unpin(l);}
        else if(actor==ActorState::Unavailable){l.state=State::Uncertain;l.reason=Reason::ActorUnavailable;Bump(l);}
    }
    Reason Binding(status_observer::TransactionContext& tx,uint64_t generation,uint32_t mask,
                   uintptr_t& status,unsigned& slot) noexcept {
        ActorInfo info{};const auto state=actors.inspect(actors.context,generation,info);
        if(state==ActorState::Unavailable || state==ActorState::Retired)return Reason::ActorUnavailable;
        if(state!=ActorState::Current)return Reason::NotCurrent;
        if(!info.controllable)return Reason::NotControllable;
        if(info.role!=Role::Sora && info.role!=Role::Roxas && info.role!=Role::Mickey)return Reason::UnsupportedRole;
        // Rescue Mickey bypasses ordinary Lucky item rolls and retained munny.
        // Structural layout compatibility does not make those rewards useful.
        if(info.role==Role::Mickey && (mask&((1u<<status_revision::Lucky)|(1u<<status_revision::Retention))))return Reason::UnsupportedRole;
        if(!status_observer::ReadableSpan(info.actor,1480))return Reason::InvalidBinding;
        status=*reinterpret_cast<const uintptr_t*>(info.actor+1472);
        int refs=0;if(!tx.pool.Owns(status,slot,refs))return Reason::InvalidBinding;
        if(*reinterpret_cast<const uintptr_t*>(status+504)!=status)return Reason::InvalidBinding;
        const uint32_t packed=*reinterpret_cast<const uint32_t*>(status+616);
        if(!packed || !status_observer::ReadableSpan(packedBases,64*sizeof(uintptr_t)))return Reason::InvalidBinding;
        const uintptr_t actorBase=reinterpret_cast<const uintptr_t*>(packedBases)[(packed&0x7fffffffu)>>25];
        if((actorBase|(packed&0x1ffffffu))!=info.actor)return Reason::InvalidBinding;
        return Reason::None;
    }
    static uint32_t Read(uintptr_t status,unsigned i) noexcept {
        uint32_t bits=0;memcpy(&bits,reinterpret_cast<const void*>(status+Offsets[i]),Widths[i]);return bits;
    }
    Reason Preflight(status_observer::TransactionContext& tx,const Request& q,uintptr_t& status,
                     unsigned& slot,uint32_t original[FieldCount]) noexcept {
        Reason why=Binding(tx,q.actorGeneration,q.mask,status,slot);if(why!=Reason::None)return why;
        if(q.expectedStamp.slot!=slot)return Reason::AllocationMismatch;
        const auto match=tx.ledger.Compare(q.expectedStamp,q.mask);
        if(match.result==status_revision::Match::AllocationEnded)return Reason::AllocationMismatch;
        if(match.result!=status_revision::Match::Current)return Reason::RevisionMismatch;
        for(unsigned i=0;i<FieldCount;++i)if(q.mask&(1u<<i)) {
            original[i]=Read(status,i);
            if(!Valid(i,original[i]) || !Valid(i,q.desiredBits[i]))return Reason::InvalidValues;
            if(original[i]!=q.expectedBits[i])return Reason::ExpectedMismatch;
            if(!WritableSpan(status+Offsets[i],Widths[i]))return Reason::NotWritable;
        }
        return Reason::None;
    }
    bool Commit(status_observer::TransactionContext& tx,uintptr_t status,unsigned slot,uint32_t mask,
                const uint32_t values[FieldCount],status_revision::Stamp& stamp) noexcept {
        if(!mask)return true;
        const auto frame=tx.ledger.Enter(status_revision::Event::ManualWrite,slot,0,mask,gameThread);
        if(!frame.ticket || tx.ledger.Status()!=status_revision::Health::Observing) {
            if(frame.ticket)tx.ledger.Exit(frame,false);return false;
        }
        bool complete=false;
        __try {
            for(unsigned i=0;i<FieldCount;++i)if(mask&(1u<<i)) {
#ifdef KH2_STATUS_FIELDS_TESTS
                if(testWriteCalls++==testFailAfterWrites)RaiseException(0xE0425354,0,0,nullptr);
#endif
                memcpy(reinterpret_cast<void*>(status+Offsets[i]),&values[i],Widths[i]);
            }
            complete=true;
        } __except(EXCEPTION_EXECUTE_HANDLER) {complete=false;}
        tx.ledger.Exit(frame,complete);
        return complete && tx.ledger.Capture(slot,stamp,true);
    }
    void CompleteRelease(status_observer::TransactionContext& tx,Lease& l) noexcept {
        Refresh(tx,l);
        if(l.state!=State::ReleasePending)return;
        uintptr_t status=0;unsigned slot=status_revision::SlotCount;
        if(Binding(tx,l.generation,l.remaining,status,slot)!=Reason::None)return;
        // The original allocation can remain live or shared after this Actor
        // switches STATUS. That is loss of our binding, not proof of pool death.
        if(slot!=l.stamp.slot){l.state=State::BindingChanged;l.remaining=0;Bump(l);Unpin(l);return;}
        uint32_t restore=0,superseded=0;
        for(unsigned i=0;i<FieldCount;++i)if(l.remaining&(1u<<i)) {
            if(Read(status,i)!=l.applied[i])superseded|=1u<<i;
            else if(Valid(i,l.original[i]) && WritableSpan(status+Offsets[i],Widths[i]))restore|=1u<<i;
        }
        if(!restore && !superseded)return;
        if(l.revision==UINT64_MAX){l.state=State::Uncertain;l.reason=Reason::RevisionMismatch;return;}
        status_revision::Stamp after{};
        if(!Commit(tx,status,slot,restore,l.original,after)) {
            l.state=State::Uncertain;l.reason=Reason::WriteFault;Bump(l);return;
        }
        // A partial writable cohort still needs the original revisions for the
        // remaining fields. Our own writes only revised the restored fields.
        l.restored|=restore;l.superseded|=superseded;l.remaining&=~(restore|superseded);++l.revision;
        if(!l.remaining){l.state=l.superseded?State::Superseded:State::Released;Unpin(l);}
    }
    void Mutate(status_observer::TransactionContext& tx,const Request& q,Response& r) noexcept {
        if(q.operation==Operation::Acquire || q.operation==Operation::ManualWrite) {
            uintptr_t status=0;unsigned slot=status_revision::SlotCount;uint32_t original[FieldCount]{};
            const auto why=Preflight(tx,q,status,slot,original);if(why!=Reason::None){Reject(r,why);return;}
            if(q.operation==Operation::ManualWrite) {
                r.ownerId=q.ownerId;r.actorGeneration=q.actorGeneration;r.mask=q.mask;
                memcpy(r.originalBits,original,sizeof(original));memcpy(r.appliedBits,q.desiredBits,sizeof(r.appliedBits));
                status_revision::Stamp after{};
                if(!Commit(tx,status,slot,q.mask,q.desiredBits,after)){r.state=State::Uncertain;Reject(r,Reason::WriteFault);return;}
                r.outcome=Outcome::ManualApplied;return;
            }
            Lease* free=nullptr;
            for(auto& l:leases) {
                Refresh(tx,l);
                if(!l.used && !free)free=&l;
                // STATUS can be shared by more than one Actor. Conflict is a
                // pool allocation plus field overlap, not just actor generation.
                if(l.used && !Terminal(l.state) && l.stamp.slot==slot &&
                   l.stamp.poolEpoch==q.expectedStamp.poolEpoch && l.stamp.allocation==q.expectedStamp.allocation &&
                   (l.remaining&q.mask)){Reject(r,Reason::Conflict);return;}
            }
            if(!free || nextLease==UINT64_MAX){Reject(r,Reason::Capacity);return;}
            if(!actors.pin(actors.context,q.actorGeneration)){Reject(r,Reason::ActorUnavailable);return;}
            Lease proposed{};proposed.used=proposed.pinned=true;proposed.state=State::Active;
            proposed.client=q.clientId;proposed.owner=q.ownerId;proposed.id=++nextLease;
            proposed.generation=q.actorGeneration;proposed.revision=1;proposed.mask=proposed.remaining=q.mask;
            proposed.stamp=q.expectedStamp;
            memcpy(proposed.original,original,sizeof(original));memcpy(proposed.applied,q.desiredBits,sizeof(proposed.applied));
            *free=proposed; // ownership and originals durable BEFORE any byte write
            if(!Commit(tx,status,slot,q.mask,q.desiredBits,free->stamp)) {
                free->state=State::Uncertain;free->reason=Reason::WriteFault;Describe(*free,r);Reject(r,Reason::WriteFault);return;
            }
            Describe(*free,r);r.outcome=Outcome::Applied;return;
        }
        auto* l=FindLease(q.leaseId);
        if(!l){Reject(r,Reason::LeaseMissing);return;}
        if(l->client!=q.clientId || l->owner!=q.ownerId){Reject(r,Reason::NotOwner);return;}
        // Check the submitted revision before Refresh may advance it on native
        // takeover. A valid intent can safely finish as Superseded/AllocationEnded.
        if(q.leaseRevision!=l->revision){Describe(*l,r);Reject(r,Reason::RevisionMismatch);return;}
        Refresh(tx,*l);
        if(l->state==State::Active){l->state=State::ReleasePending;Bump(*l);}
        CompleteRelease(tx,*l);Describe(*l,r);
        if(l->state==State::Uncertain){Reject(r,l->reason);return;}
        r.outcome=Outcome::ReleaseAccepted;
    }
    struct Work {Journal* self;const Request* request;Response* response;bool tick=false,releaseAll=false,entered=false;};
    static bool Dispatch(status_observer::TransactionContext& tx,void* value) noexcept {
        auto& work=*static_cast<Work*>(value);auto& self=*work.self;work.entered=true;
        if(tx.ledger.Instance()!=self.instance)return false;
        if(work.tick) {
            for(auto& l:self.leases)if(l.used) {
                self.Refresh(tx,l);
                if(work.releaseAll && l.state==State::Active){l.state=State::ReleasePending;self.Bump(l);}
                self.CompleteRelease(tx,l);
            }
        } else if(work.request->operation==Operation::QueryLease) {
            const auto& q=*work.request;auto& r=*work.response;auto* l=self.FindLease(q.leaseId);
            if(!l){Reject(r,Reason::LeaseMissing);return true;}
            if(l->client!=q.clientId || l->owner!=q.ownerId){Reject(r,Reason::NotOwner);return true;}
            self.Refresh(tx,*l);self.Describe(*l,r);r.outcome=Outcome::LeaseObserved;
        } else self.Mutate(tx,*work.request,*work.response);
        return true;
    }
    struct ReadWork {Journal* self;uint64_t generation;uint32_t mask;Snapshot snapshot{};Reason reason=Reason::None;};
    static bool ReadSnapshot(status_observer::TransactionContext& tx,void* value) noexcept {
        auto& w=*static_cast<ReadWork*>(value);uintptr_t status=0;unsigned slot=status_revision::SlotCount;
        if(tx.ledger.Instance()!=w.self->instance){w.reason=Reason::StaleInstance;return false;}
        w.reason=w.self->Binding(tx,w.generation,w.mask,status,slot);if(w.reason!=Reason::None)return false;
        for(unsigned i=0;i<FieldCount;++i)if(w.mask&(1u<<i)) {
            w.snapshot.bits[i]=Read(status,i);
            if(!Valid(i,w.snapshot.bits[i])){w.reason=Reason::InvalidValues;return false;}
        }
        if(!tx.ledger.Capture(slot,w.snapshot.stamp,true)){w.reason=Reason::ObserverUnavailable;return false;}
        w.snapshot.bridgeInstance=w.self->instance;w.snapshot.actorGeneration=w.generation;w.snapshot.mask=w.mask;return true;
    }
public:
    Journal()=default;Journal(const Journal&)=delete;Journal& operator=(const Journal&)=delete;
    bool Bind(status_observer::Observer& statusObserver,const ActorProvider& provider,uintptr_t nativePackedBaseTable,
              uint64_t bridgeInstance,DWORD ownerThread) noexcept {
        if(observer || !provider.inspect || !provider.pin || !provider.unpin || !nativePackedBaseTable ||
           64*sizeof(uintptr_t)>UINTPTR_MAX-nativePackedBaseTable || !bridgeInstance || !ownerThread || ownerThread!=GetCurrentThreadId())return false;
        observer=&statusObserver;actors=provider;packedBases=nativePackedBaseTable;instance=bridgeInstance;gameThread=ownerThread;return true;
    }
    bool ReadCurrent(uint64_t generation,uint32_t mask,Snapshot& output,Reason& reason) noexcept {
        output={};reason=Reason::None;
        if(!observer || !OnThread()){reason=Reason::WrongThread;return false;}
        if(!generation || !mask || (mask&~AllFields)){reason=Reason::InvalidRequest;return false;}
        ReadWork work{this,generation,mask};
        if(!observer->WithMetadata(&ReadSnapshot,&work)) {
            const bool fault=observer->Inspect().phase==status_observer::Phase::Fault;if(fault)Uncertain();
            reason=work.reason!=Reason::None?work.reason:(fault?Reason::ObserverFault:Reason::ObserverUnavailable);return false;
        }
        output=work.snapshot;return true;
    }
    void Tick(bool releaseAll=false) noexcept {
        if(!observer || !OnThread())return;
        Work work{this,nullptr,nullptr,true,releaseAll};
        if(!observer->WithMetadata(&Dispatch,&work) && observer->Inspect().phase==status_observer::Phase::Fault)Uncertain();
    }
    Response Execute(const Request q) noexcept {
        Response r=Envelope(q);
        if(!observer || !OnThread()){Reject(r,Reason::WrongThread);return r;}
        if(!Encoding(q)){Reject(r,Reason::InvalidRequest);return r;}
        if(q.bridgeInstance!=instance){Reject(r,Reason::StaleInstance);return r;}
        if(Mutation(q.operation)) {
            if(auto* old=FindReceipt(q.clientId,q.opId)) {
                if(!Same(old->request,q)){Reject(r,Reason::RequestIdConflict);return r;}
                return old->response;
            }
            Client* client=nullptr;Client* freeClient=nullptr;Receipt* receipt=nullptr;
            for(auto& c:clients){if(c.id==q.clientId)client=&c;if(!c.id && !freeClient)freeClient=&c;}
            if(client && q.opId<=client->highWater){Reject(r,Reason::RetiredRequest);return r;}
            for(auto& p:receipts)if(!p.used){receipt=&p;break;}
            if(!receipt || (!client && !freeClient)){Reject(r,Reason::Capacity);return r;}
            if(!client){client=freeClient;client->id=q.clientId;}client->highWater=q.opId;
            receipt->used=true;receipt->request=q;
            r.receiptOpId=q.opId;r.state=State::Uncertain;Reject(r,Reason::WriteFault);receipt->response=r;
            Response result=Envelope(q);result.receiptOpId=q.opId;
            Work work{this,&q,&result};const bool ok=observer->WithMetadata(&Dispatch,&work);
            if(!ok) {
                const bool fault=observer->Inspect().phase==status_observer::Phase::Fault;if(fault)Uncertain();
                if(!work.entered){result.state=State::None;Reject(result,fault?Reason::ObserverFault:Reason::ObserverUnavailable);}
                else if(fault && result.reason!=Reason::WriteFault){result.state=State::Uncertain;Reject(result,Reason::ObserverFault);}
                else if(!fault && result.reason==Reason::None)Reject(result,Reason::StaleInstance);
            }
            receipt->response=result;return result;
        }
        if(q.operation==Operation::QueryOperation || q.operation==Operation::Acknowledge) {
            auto* receipt=FindReceipt(q.clientId,q.targetOpId);
            if(!receipt){Reject(r,Reason::ReceiptMissing);return r;}
            if(q.operation==Operation::QueryOperation){r=receipt->response;r.opId=q.opId;return r;}
            *receipt=Receipt{};Collect();r.outcome=Outcome::Acknowledged;return r;
        }
        if(q.operation==Operation::AcknowledgeLease) {
            auto* l=FindLease(q.leaseId);
            if(!l){Reject(r,Reason::LeaseMissing);return r;}
            if(l->client!=q.clientId || l->owner!=q.ownerId){Reject(r,Reason::NotOwner);return r;}
            Describe(*l,r);
            if(l->revision!=q.leaseRevision){Reject(r,Reason::RevisionMismatch);return r;}
            if(!Terminal(l->state) || l->pinned){Reject(r,Reason::Conflict);return r;}
            for(const auto& p:receipts)if(p.used && p.response.leaseId==l->id){Reject(r,Reason::Conflict);return r;}
            *l=Lease{};r.outcome=Outcome::Acknowledged;return r;
        }
        Work work{this,&q,&r};
        if(!observer->WithMetadata(&Dispatch,&work)) {
            const bool fault=observer->Inspect().phase==status_observer::Phase::Fault;if(fault)Uncertain();
            auto* l=FindLease(q.leaseId);
            if(l && l->client==q.clientId && l->owner==q.ownerId){
                Describe(*l,r);r.outcome=Outcome::LeaseObserved;
                // This is retained journal state, not a new native observation.
                if(!fault && !Terminal(l->state) && l->state!=State::Uncertain)r.reason=Reason::ObserverUnavailable;
            }
            else Reject(r,fault?Reason::ObserverFault:Reason::ObserverUnavailable);
        }
        return r;
    }
};
} // namespace status_fields
