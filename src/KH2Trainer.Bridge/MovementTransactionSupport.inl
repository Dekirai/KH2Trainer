// Typed, journaled movement cohorts. Include after ActorLifetimeSupport and
// GameplayStateSupport. Dispatch only on the game's update thread. Every selected
// field is checked before any write; no native game call/yield occurs in a commit.
// This module is not active until the protocol-v4 bridge integration is installed.
#include "MovementProtocol.h"
namespace movement_tx {
constexpr unsigned LeaseCount=32,ReceiptCount=64;
struct Lease {
    bool used=false,pinned=false; State state=State::None; Reason faultReason=Reason::None;
    uint64_t client=0,owner=0,id=0,generation=0,revision=0;
    uint32_t mask=0,remaining=0,restored=0,superseded=0;
    uint32_t original[4]{},applied[4]{};
};
struct Receipt { bool used=false; Request request{}; Response response{}; };
static Lease leases[LeaseCount];
static Receipt receipts[ReceiptCount];
static uint64_t nextLease=0;
#ifdef KH2_MOVEMENT_TX_TESTS
int testFailAfterWrites=-1,testWriteCalls=0;
#endif
bool Terminal(State state) { return state==State::Released || state==State::Superseded || state==State::Destroyed; }
bool Mutation(Operation op) { return op==Operation::Acquire || op==Operation::Reapply || op==Operation::ReleaseIntent; }
bool Zero(const uint32_t* bits) { for(unsigned i=0;i<4;++i)if(bits[i])return false;return true; }
bool Encoding(const Request& q) {
    if(q.magic!=Magic || q.schema!=Schema || q.size!=sizeof(Request) || !q.clientId || !q.opId ||
       q.flags || q.reserved0 || q.reserved1 || q.mask>15) return false;
    if(q.operation<Operation::Acquire || q.operation>Operation::AcknowledgeReceipt)return false;
    if(q.operation==Operation::Acquire || q.operation==Operation::Reapply) {
        if(!q.actorGeneration || !q.effectOwnerId || !q.mask || q.targetOpId)return false;
        if(q.operation==Operation::Acquire ? (q.leaseId || q.expectedLeaseRevision) : (!q.leaseId || !q.expectedLeaseRevision))return false;
        for(unsigned i=0;i<4;++i)if(!(q.mask&(1u<<i))&&(q.expectedBits[i]||q.desiredBits[i]))return false;
        return true;
    }
    if(q.mask || !Zero(q.expectedBits) || !Zero(q.desiredBits))return false;
    if(q.operation==Operation::ReleaseIntent)return q.leaseId && q.effectOwnerId && q.expectedLeaseRevision && !q.targetOpId;
    if(q.operation==Operation::QueryOperation)return q.targetOpId && !q.leaseId && !q.effectOwnerId && !q.expectedLeaseRevision && !q.actorGeneration;
    if(q.operation==Operation::QueryLease)return q.leaseId && q.effectOwnerId && !q.targetOpId && !q.expectedLeaseRevision && !q.actorGeneration;
    const bool leaseTuple=q.leaseId && q.effectOwnerId && q.expectedLeaseRevision;
    return !q.actorGeneration && ((q.targetOpId && !q.leaseId && !q.effectOwnerId && !q.expectedLeaseRevision) || leaseTuple);
}
Response Envelope(const Request& q,uint32_t sequence) {
    Response r{};r.magic=Magic;r.schema=Schema;r.size=sizeof(Response);
    r.clientId=q.clientId;r.opId=q.opId;r.bridgeInstance=actor_lifetime::BridgeInstance();
    r.requestSequence=sequence;r.tick=GetTickCount();return r;
}
void Reject(Response& r,Reason reason) { r.outcome=Outcome::Rejected;r.reason=reason; }
Lease* FindLease(uint64_t id) { for(auto& l:leases)if(l.used && l.id==id)return &l;return nullptr; }
Receipt* FindReceipt(uint64_t client,uint64_t op) { for(auto& p:receipts)if(p.used && p.request.clientId==client && p.request.opId==op)return &p;return nullptr; }
bool SameRequest(const Request& a,const Request& b) { return !memcmp(&a,&b,sizeof(Request)); }
void Describe(const Lease& l,Response& r) {
    r.actorGeneration=l.generation;r.leaseId=l.id;r.revision=l.revision;r.effectOwnerId=l.owner;
    r.mask=l.mask;r.restoredMask=l.restored;r.supersededMask=l.superseded;r.journalState=l.state;
    if(l.state==State::Uncertain)r.reason=l.faultReason;
    memcpy(r.originalBits,l.original,sizeof(l.original));memcpy(r.appliedBits,l.applied,sizeof(l.applied));
    r.flags|=IdentityKnown;
}
void Unpin(Lease& l) { if(l.pinned){actor_lifetime::Unpin(l.generation);l.pinned=false;} }
bool Bump(Lease& l) {
    if(l.revision==UINT64_MAX){l.state=State::Uncertain;l.faultReason=Reason::RevisionMismatch;return false;}
    ++l.revision;return true;
}
void Refresh(Lease& l) {
    if(!l.used || Terminal(l.state) || l.state==State::Uncertain)return;
    if(!actor_lifetime::Ready()) { l.state=State::Uncertain;l.faultReason=Reason::ObserverFault;Bump(l);return; }
    if(actor_lifetime::IsRetired(l.generation)) {
        l.state=State::Destroyed;l.remaining=0;Bump(l);Unpin(l);
    }
}
uint32_t Bits(float value) { uint32_t bits;memcpy(&bits,&value,4);return bits; }
float Float(uint32_t bits) { float value;memcpy(&value,&bits,4);return value; }
bool Valid(unsigned i,uint32_t bits) {
    const double value=Float(bits);
    return isfinite(value) && value>=actor_movement::Minima[i] && value<=actor_movement::Maxima[i];
}
enum class Access { Snapshot, Mutation, Cleanup };
bool Current(const TrainerContext& c,uint64_t generation,Access access) {
    if(!actor_lifetime::Ready() || !generation || actor_lifetime::Resolve(generation)!=c.player ||
       !actor_movement::MovementReady(c,access==Access::Snapshot))return false;
    if(access==Access::Snapshot)return true;
    // Cleanup restores only still-owned fields on the exact live Actor. A lost
    // host cannot grant new effects, but must not strand an existing lease.
    return (access==Access::Cleanup?gameplay_state::InspectNative(c):gameplay_state::Inspect(c)).controllable;
}
void Observe(const TrainerContext& c,const Lease& l,Response& r) {
    if(!Current(c,l.generation,Access::Snapshot))return;
    for(unsigned i=0;i<4;++i)if(l.mask&(1u<<i))r.observedBits[i]=Bits(combat::Field<float>(c.player,actor_movement::Offsets[i]));
    r.flags|=ObservedKnown;
}
Reason Preflight(const TrainerContext& c,const Request& q,uint32_t observed[4]) {
    if(!actor_lifetime::Ready())return actor_lifetime::Status()==2?Reason::ObserverFault:Reason::ObserverUnavailable;
    if(!Current(c,q.actorGeneration,Access::Mutation))return actor_lifetime::Resolve(q.actorGeneration)!=c.player?Reason::ActorMismatch:Reason::NotReady;
    for(unsigned i=0;i<4;++i)if(q.mask&(1u<<i)) {
        observed[i]=Bits(combat::Field<float>(c.player,actor_movement::Offsets[i]));
        if(!Valid(i,observed[i]) || !Valid(i,q.desiredBits[i]))return Reason::InvalidValues;
        if(observed[i]!=q.expectedBits[i])return Reason::ExpectedMismatch;
        if(!Writable(reinterpret_cast<void*>(c.player+actor_movement::Offsets[i]),sizeof(float)))return Reason::NotReady;
    }
    return Reason::None;
}
// All writes run without calls into the game after one complete preflight.
void Write(const TrainerContext& c,uint32_t mask,const uint32_t values[4]) {
    for(unsigned i=0;i<4;++i)if(mask&(1u<<i)) {
#ifdef KH2_MOVEMENT_TX_TESTS
        if(testWriteCalls++==testFailAfterWrites)RaiseException(0xE0424101,0,0,nullptr);
#endif
        memcpy(reinterpret_cast<void*>(c.player+actor_movement::Offsets[i]),&values[i],sizeof(float));
    }
}
bool Commit(const TrainerContext& c,uint32_t mask,const uint32_t values[4],Lease& l) {
    bool success=false;
    // Only the trainer's scalar writes are inside this handler. No native game
    // callback runs here. A partial write freezes ownership as uncertain.
    __try { Write(c,mask,values);success=true; }
    __except(EXCEPTION_EXECUTE_HANDLER) {l.state=State::Uncertain;l.faultReason=Reason::WriteFault;Bump(l);}
    return success;
}
void CompleteRelease(const TrainerContext& c,Lease& l) {
    Refresh(l);
    if(l.state!=State::ReleasePending || !Current(c,l.generation,Access::Cleanup))return;
    uint32_t restore=0,superseded=0;
    for(unsigned i=0;i<4;++i)if(l.remaining&(1u<<i)) {
        const auto address=c.player+actor_movement::Offsets[i];
        if(Bits(combat::Field<float>(c.player,actor_movement::Offsets[i]))!=l.applied[i])superseded|=1u<<i;
        else if(Valid(i,l.original[i]) && Writable(reinterpret_cast<void*>(address),sizeof(float)))restore|=1u<<i;
    }
    if(!restore && !superseded)return;
    if(l.revision==UINT64_MAX){l.state=State::Uncertain;l.faultReason=Reason::RevisionMismatch;return;}
    if(!Commit(c,restore,l.original,l))return;
    l.restored|=restore;l.superseded|=superseded;l.remaining&=~(restore|superseded);
    ++l.revision;
    if(!l.remaining){l.state=l.superseded?State::Superseded:State::Released;Unpin(l);}
}
void Tick(const TrainerContext& c,bool releaseAll=false) {
    if(GetCurrentThreadId()!=g_gameThread)return;
    for(auto& l:leases)if(l.used) {
        Refresh(l);
        if(releaseAll && l.state==State::Active){l.state=State::ReleasePending;Bump(l);}
        CompleteRelease(c,l);
    }
}
bool Owned(const Request& q,Lease* l,Response& r,bool revision) {
    if(!l){Reject(r,Reason::LeaseNotFound);return false;}
    if(l->client!=q.clientId || l->owner!=q.effectOwnerId){Reject(r,Reason::NotOwner);return false;}
    Refresh(*l);Describe(*l,r);
    if(revision && l->revision!=q.expectedLeaseRevision){Reject(r,Reason::RevisionMismatch);return false;}
    return true;
}
void Mutate(const TrainerContext& c,const Request& q,Response& r) {
    if(q.operation==Operation::Acquire) {
        uint32_t observed[4]{};const Reason why=Preflight(c,q,observed);
        if(why!=Reason::None){Reject(r,why);return;}
        Lease* free=nullptr;
        for(auto& l:leases) {
            Refresh(l);
            if(!l.used && !free)free=&l;
            if(l.used && !Terminal(l.state) && l.generation==q.actorGeneration && (l.mask&q.mask)) {Reject(r,Reason::LeaseConflict);return;}
        }
        if(!free || nextLease==UINT64_MAX){Reject(r,Reason::JournalFull);return;}
        if(!actor_lifetime::Pin(q.actorGeneration)){Reject(r,Reason::ObserverUnavailable);return;}
        Lease proposed{};proposed.used=true;proposed.pinned=true;proposed.state=State::Active;
        proposed.client=q.clientId;proposed.owner=q.effectOwnerId;proposed.id=++nextLease;
        proposed.generation=q.actorGeneration;proposed.revision=1;proposed.mask=proposed.remaining=q.mask;
        memcpy(proposed.original,observed,sizeof(observed));memcpy(proposed.applied,q.desiredBits,sizeof(proposed.applied));
        // Publish private ownership before the writes so a fault cannot lose the originals.
        *free=proposed;
        if(!Commit(c,q.mask,q.desiredBits,*free)){Describe(*free,r);Reject(r,Reason::WriteFault);return;}
        Describe(*free,r);memcpy(r.observedBits,q.desiredBits,sizeof(r.observedBits));
        r.flags|=ObservedKnown;r.appliedMask=q.mask;r.outcome=Outcome::Applied;return;
    }
    Lease* l=FindLease(q.leaseId);
    if(!Owned(q,l,r,true))return;
    if(q.actorGeneration && q.actorGeneration!=l->generation){Reject(r,Reason::ActorMismatch);return;}
    if(q.operation==Operation::ReleaseIntent) {
        if(l->state==State::Uncertain){Reject(r,l->faultReason);return;}
        if(l->state==State::Active) {l->state=State::ReleasePending;if(!Bump(*l)){Describe(*l,r);Reject(r,Reason::ObserverFault);return;}}
        CompleteRelease(c,*l);Describe(*l,r);Observe(c,*l,r);
        if(l->state==State::Uncertain){Reject(r,l->faultReason);return;}
        r.outcome=Outcome::ReleaseAccepted;return;
    }
    if(l->state!=State::Active || q.mask!=l->mask){Reject(r,Reason::LeaseConflict);return;}
    if(l->revision==UINT64_MAX){Reject(r,Reason::RevisionMismatch);return;}
    uint32_t observed[4]{};const Reason why=Preflight(c,q,observed);
    if(why!=Reason::None){Reject(r,why);return;}
    for(unsigned i=0;i<4;++i)if(q.mask&(1u<<i)) {
        if(observed[i]!=l->applied[i])l->original[i]=observed[i];
        l->applied[i]=q.desiredBits[i];
    }
    if(!Commit(c,q.mask,q.desiredBits,*l)){Describe(*l,r);Reject(r,Reason::WriteFault);return;}
    ++l->revision;
    Describe(*l,r);memcpy(r.observedBits,q.desiredBits,sizeof(r.observedBits));r.flags|=ObservedKnown;
    r.appliedMask=q.mask;r.outcome=Outcome::Reapplied;
}
// Copy the packet at the boundary: later host IPC writes cannot alter the checked
// expected vector, applied vector or immutable receipt midway through dispatch.
Response Execute(const TrainerContext& c,const Request q,uint32_t sequence,Reason preRejected=Reason::None) {
    Response r=Envelope(q,sequence);
    if(q.magic!=Magic || q.schema!=Schema || q.size!=sizeof(Request)){Reject(r,Reason::UnsupportedSchema);return r;}
    if(!Encoding(q)){Reject(r,Reason::InvalidRequest);return r;}
    if(GetCurrentThreadId()!=g_gameThread){Reject(r,Reason::WrongThread);return r;}
    if(!q.bridgeInstance || q.bridgeInstance!=r.bridgeInstance){Reject(r,Reason::StaleBridge);return r;}
    if(Mutation(q.operation)) {
        if(auto* prior=FindReceipt(q.clientId,q.opId)) {
            if(!SameRequest(prior->request,q)){Reject(r,Reason::RequestIdConflict);return r;}
            r=prior->response;r.requestSequence=sequence;r.tick=GetTickCount();return r;
        }
        // An expired replay can still acknowledge an earlier committed mutation.
        // Expiry prevents new work; it cannot rewrite an immutable prior result.
        if(preRejected!=Reason::None){Reject(r,preRejected);return r;}
        Receipt* free=nullptr;for(auto& p:receipts)if(!p.used){free=&p;break;}
        if(!free){Reject(r,Reason::JournalFull);return r;}
        // Reserve a correlated uncertain result before any mutation. An unexpected
        // exception must follow normal engine handling; it is never treated as success.
        free->used=true;free->request=q;free->response=r;
        free->response.outcome=Outcome::Rejected;free->response.reason=Reason::WriteFault;
        free->response.journalState=State::Uncertain;free->response.flags=HasReceipt;free->response.receiptOpId=q.opId;
        Mutate(c,q,r);r.flags|=HasReceipt;r.receiptOpId=q.opId;free->response=r;return r;
    }
    if(preRejected!=Reason::None){Reject(r,preRejected);return r;}
    if(q.operation==Operation::QueryOperation) {
        auto* p=FindReceipt(q.clientId,q.targetOpId);
        if(!p){r.outcome=Outcome::OperationUnknown;r.reason=Reason::ReceiptNotFound;return r;}
        r=p->response;r.opId=q.opId;r.requestSequence=sequence;r.tick=GetTickCount();return r;
    }
    if(q.operation==Operation::QueryLease) {
        auto* l=FindLease(q.leaseId);
        if(Owned(q,l,r,false)){r.outcome=Outcome::LeaseObserved;Observe(c,*l,r);}return r;
    }
    Lease* l=nullptr;
    if(q.leaseId) {
        l=FindLease(q.leaseId);
        if(l && !Owned(q,l,r,true))return r;
        // A repeat of a completed terminal GC is an idempotent acknowledgement.
        if(l && !Terminal(l->state)){Reject(r,Reason::LeaseConflict);return r;}
    }
    if(auto* p=FindReceipt(q.clientId,q.targetOpId))*p=Receipt{};
    if(l) {
        bool referenced=false;for(const auto& p:receipts)if(p.used && p.response.leaseId==l->id)referenced=true;
        if(!referenced){Unpin(*l);*l=Lease{};}
    }
    r.outcome=Outcome::ReceiptAcknowledged;return r;
}
void Snapshot(const TrainerContext& c) {
    for(unsigned slot=Capability;slot<=ObserverStatus;++slot)SupportCapability(slot);
    SnapshotValue(Capability,Schema);
    const uint64_t generation=actor_lifetime::ObserveCurrent(c),instance=actor_lifetime::BridgeInstance();
    SnapshotValue(GenerationLow,static_cast<uint32_t>(generation));
    SnapshotValue(GenerationHigh,static_cast<uint32_t>(generation>>32));
    SnapshotValue(InstanceLow,static_cast<uint32_t>(instance));
    SnapshotValue(InstanceHigh,static_cast<uint32_t>(instance>>32));
    SnapshotValue(ObserverStatus,actor_lifetime::Status());
}
}
