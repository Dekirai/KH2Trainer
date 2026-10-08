#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdint.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <limits>
#include <initializer_list>
namespace {
DWORD g_gameThread=0;
struct TrainerContext { uintptr_t base=0,player=0,status=0;bool sceneReady=true; } context;
alignas(16) unsigned char actors[3][512];
bool canMove=true,controlled=true,canWrite=true;
namespace actor_movement {
constexpr unsigned Offsets[]={296,300,312,304};
constexpr double Minima[]={0,0,.1,0},Maxima[]={32,64,100,1000};
bool MovementReady(const TrainerContext& c,bool=false){return canMove && c.player && c.sceneReady;}
}
namespace combat { template<class T>T& Field(uintptr_t actor,unsigned offset){return *reinterpret_cast<T*>(actor+offset);} }
namespace gameplay_state { struct State{bool controllable;};State Inspect(const TrainerContext&){return {controlled};} }
namespace actor_lifetime {
struct Watch {uint64_t gen;uintptr_t actor;bool retired;unsigned pins;};
Watch watch[64]{};bool ready=true;unsigned status=1;
uint64_t instance=0xabcdefabcd1234ULL;
bool Ready(){return ready;}unsigned Status(){return status;}uint64_t BridgeInstance(){return instance;}
uintptr_t Resolve(uint64_t gen){if(ready)for(auto& w:watch)if(w.gen==gen&&!w.retired)return w.actor;return 0;}
bool IsRetired(uint64_t gen){if(!ready)return false;for(auto& w:watch)if(w.gen==gen)return w.retired;return true;}
bool Pin(uint64_t gen){if(!ready)return false;for(auto& w:watch)if(w.gen==gen&&!w.retired){++w.pins;return true;}return false;}
void Unpin(uint64_t gen){for(auto& w:watch)if(w.gen==gen&&w.pins){--w.pins;return;}}
uint64_t ObserveCurrent(const TrainerContext& c){if(ready)for(auto& w:watch)if(w.actor==c.player&&!w.retired)return w.gen;return 0;}
}
double published[512]{};bool supported[512]{};
void SupportCapability(unsigned slot){supported[slot]=true;}
void SnapshotValue(unsigned slot,double value){published[slot]=value;}
bool Writable(const void*,size_t){return canWrite;}
#define KH2_MOVEMENT_TX_TESTS
#include "../../src/KH2Trainer.Bridge/MovementTransactionSupport.inl"
using namespace movement_tx;
unsigned checks=0,failures=0;uint64_t operation=0;
void Check(bool value,const char* name){++checks;if(!value){++failures;printf("FAIL %s\n",name);}}
void Set(unsigned index,float value,unsigned actor=0){memcpy(actors[actor]+actor_movement::Offsets[index],&value,4);}
float Get(unsigned index,unsigned actor=0){float value;memcpy(&value,actors[actor]+actor_movement::Offsets[index],4);return value;}
void Reset(){
    for(auto& l:leases)l=Lease{};for(auto& p:receipts)p=Receipt{};nextLease=0;operation=0;testFailAfterWrites=-1;testWriteCalls=0;
    memset(actors,0,sizeof(actors));for(auto& w:actor_lifetime::watch)w={};
    g_gameThread=GetCurrentThreadId();canMove=controlled=canWrite=actor_lifetime::ready=true;actor_lifetime::status=1;
    context={1,reinterpret_cast<uintptr_t>(actors[0]),1,true};
    actor_lifetime::watch[0]={1,context.player,false,0};
    actor_lifetime::watch[1]={2,reinterpret_cast<uintptr_t>(actors[1]),false,0};
    for(unsigned a=0;a<3;++a){Set(0,2,a);Set(1,8,a);Set(2,20,a);Set(3,160,a);}
}
Request Base(Operation op){Request q{};q.magic=Magic;q.schema=Schema;q.size=sizeof(q);q.clientId=1;q.opId=++operation;q.bridgeInstance=actor_lifetime::instance;q.operation=op;return q;}
Request Acquire(uint32_t mask=3,uint64_t generation=1,uint64_t owner=10){
    auto q=Base(Operation::Acquire);q.mask=mask;q.actorGeneration=generation;q.effectOwnerId=owner;
    const float desired[4]={5,20,5,400};
    for(unsigned i=0;i<4;++i)if(mask&(1u<<i)){q.expectedBits[i]=Bits(combat::Field<float>(context.player,actor_movement::Offsets[i]));q.desiredBits[i]=Bits(desired[i]);}return q;
}
Request LeaseRequest(Operation op,const Response& prior){auto q=Base(op);q.leaseId=prior.leaseId;q.effectOwnerId=prior.effectOwnerId;
    if(op==Operation::Reapply||op==Operation::ReleaseIntent||op==Operation::AcknowledgeReceipt)q.expectedLeaseRevision=prior.revision;return q;}
Response Run(const Request& q){return Execute(context,q,static_cast<uint32_t>(q.opId));}
void Ack(const Response& prior,bool terminal=false){auto q=Base(Operation::AcknowledgeReceipt);q.targetOpId=prior.receiptOpId;
    if(terminal){q.leaseId=prior.leaseId;q.effectOwnerId=prior.effectOwnerId;q.expectedLeaseRevision=prior.revision;}
    Check(Run(q).outcome==Outcome::ReceiptAcknowledged,"receipt acknowledged");}
void Layout(){
    Check(sizeof(Request)==128&&sizeof(Response)==192,"binary packet sizes");
    Check(offsetof(Request,desiredBits)==72&&offsetof(Request,expectedLeaseRevision)==88,"request scalar offsets");
    Check(offsetof(Response,journalState)==84&&offsetof(Response,receiptOpId)==152,"response scalar offsets");
    Reset();Snapshot(context);Check(supported[466]&&supported[471]&&published[466]==1&&published[467]==1&&published[468]==0,"snapshot schema and current generation are coherent");
    Check(published[469]==static_cast<uint32_t>(actor_lifetime::instance)&&published[470]==static_cast<uint32_t>(actor_lifetime::instance>>32),"snapshot transports full uint64 nonce without double rounding");
    actor_lifetime::ready=false;actor_lifetime::status=2;Snapshot(context);
    Check(supported[466]&&published[466]==1&&published[467]==0&&published[471]==2&&published[469]!=0,"journal capability and bridge nonce remain available after observer fault");
}
void Cohorts(){
    for(uint32_t mask=1;mask<16;++mask){Reset();auto q=Acquire(mask);auto r=Run(q);
        Check(r.outcome==Outcome::Applied && r.mask==mask && r.appliedMask==mask,"all nonempty masks atomically admitted");
        Check(r.clientId==q.clientId&&r.opId==q.opId&&r.requestSequence==q.opId&&r.receiptOpId==q.opId,"ack directly correlates operation");
        Check((r.flags&(HasReceipt|IdentityKnown|ObservedKnown))==(HasReceipt|IdentityKnown|ObservedKnown),"receipt carries identity and exact observation");
        for(unsigned i=0;i<4;++i){Check(Bits(Get(i))==((mask&(1u<<i))?q.desiredBits[i]:Bits(i==0?2.f:i==1?8.f:i==2?20.f:160.f)),"only selected fields changed");
            if(mask&(1u<<i))Check(r.originalBits[i]==q.expectedBits[i]&&r.appliedBits[i]==q.desiredBits[i],"native receipt originals and applied bits exact");}
        auto release=Run(LeaseRequest(Operation::ReleaseIntent,r));
        Check(release.journalState==State::Released&&release.restoredMask==mask,"selected cohort restored");
        Check(Get(0)==2&&Get(1)==8&&Get(2)==20&&Get(3)==160,"original full movement block restored");
        Check(actor_lifetime::watch[0].pins==0,"terminal lease unpins lifetime");Ack(r);Ack(release,true);
        Check(FindLease(r.leaseId)==nullptr,"terminal record garbage collected only after receipts acknowledged");
    }
}
void Races(){
    Reset();auto q=Acquire();Set(1,9);auto r=Run(q);Check(r.reason==Reason::ExpectedMismatch&&Get(0)==2&&Get(1)==9,"last field conflict prevents first field write");
    Reset();q=Acquire();context.player=reinterpret_cast<uintptr_t>(actors[1]);r=Run(q);
    Check(r.reason==Reason::ActorMismatch&&Get(0)==2&&Get(0,1)==2,"actor switched before dispatch cannot receive old write");
    Reset();q=Acquire();actor_lifetime::watch[0].retired=true;actor_lifetime::watch[1]={2,context.player,false,0};r=Run(q);
    Check(r.reason==Reason::ActorMismatch&&Get(1)==8,"same address reused for a new generation rejects stale request");
    Reset();q=Acquire();auto applied=Run(q);Set(0,7);auto replay=Run(q);
    Check(replay.outcome==Outcome::Applied&&Get(0)==7&&replay.originalBits[0]==Bits(2.f),"duplicate mutation returns retained receipt without applying again");
    for(auto reason:{Reason::Expired,Reason::HostExpired}){
        auto late=Execute(context,q,998,reason);
        Check(late.outcome==Outcome::Applied&&late.receiptOpId==applied.receiptOpId&&late.originalBits[0]==Bits(2.f)&&late.requestSequence==998&&Get(0)==7,"expired replay preserves immutable original mutation receipt");
    }
    q.desiredBits[0]=Bits(6.f);Check(Run(q).reason==Reason::RequestIdConflict&&Get(0)==7,"same id with different payload rejected");
    auto query=Base(Operation::QueryOperation);query.targetOpId=applied.receiptOpId;auto observed=Run(query);
    Check(observed.opId==query.opId&&observed.receiptOpId==applied.receiptOpId&&observed.originalBits[0]==Bits(2.f),"lost ack recovered from journal and current scalar ignored");
    Ack(applied);Check(Run(query).outcome==Outcome::OperationUnknown,"ack explicitly ends retained mutation lifetime");
}
void RestoreOwnership(){
    Reset();auto r=Run(Acquire());Ack(r);Set(0,11);auto release=Run(LeaseRequest(Operation::ReleaseIntent,r));
    Check(release.journalState==State::Superseded&&release.supersededMask==1&&release.restoredMask==2,"cleanup preserves different script value per field");
    Check(Get(0)==11&&Get(1)==8,"only still-owned run value restored");
    Reset();r=Run(Acquire());Ack(r);Set(0,7);Set(1,9);auto q=LeaseRequest(Operation::Reapply,r);q.actorGeneration=1;q.mask=3;
    q.expectedBits[0]=Bits(7.f);q.expectedBits[1]=Bits(9.f);q.desiredBits[0]=Bits(5.f);q.desiredBits[1]=Bits(20.f);
    auto reapplied=Run(q);Check(reapplied.outcome==Outcome::Reapplied&&reapplied.originalBits[0]==Bits(7.f)&&reapplied.originalBits[1]==Bits(9.f),"successful sustain captures current external originals");
    release=Run(LeaseRequest(Operation::ReleaseIntent,reapplied));Check(Get(0)==7&&Get(1)==9,"sustained lease restores latest captured script baseline");
    Reset();r=Run(Acquire());Set(1,9);q=LeaseRequest(Operation::Reapply,r);q.actorGeneration=1;q.mask=3;
    q.expectedBits[0]=Bits(5.f);q.expectedBits[1]=Bits(9.f);q.desiredBits[0]=Bits(5.f);q.desiredBits[1]=Bits(20.f);
    reapplied=Run(q);Check(reapplied.originalBits[0]==Bits(2.f)&&reapplied.originalBits[1]==Bits(9.f),"one changed field does not recapture the other applied value as original");
    release=Run(LeaseRequest(Operation::ReleaseIntent,reapplied));Check(Get(0)==2&&Get(1)==9,"mixed unchanged and script-modified pair restores independent originals");
    Reset();r=Run(Acquire());q=LeaseRequest(Operation::Reapply,r);q.actorGeneration=1;q.mask=3;q.expectedBits[0]=Bits(5.f);q.expectedBits[1]=Bits(100.f);q.desiredBits[0]=Bits(5.f);q.desiredBits[1]=Bits(20.f);Set(1,100);
    auto bad=Run(q);Check(bad.reason==Reason::InvalidValues&&FindLease(r.leaseId)->original[1]==Bits(8.f)&&Get(1)==100,"out-of-policy sustain preserves script and original");
    Reset();Set(0,-0.0f);r=Run(Acquire(1));Set(0,+0.0f);release=Run(LeaseRequest(Operation::ReleaseIntent,r));
    Check(release.journalState==State::Superseded&&Bits(Get(0))==0,"bitwise ownership preserves external signed-zero change");
}
void Lifetimes(){
    Reset();auto r=Run(Acquire());context.player=reinterpret_cast<uintptr_t>(actors[1]);auto release=Run(LeaseRequest(Operation::ReleaseIntent,r));
    Check(release.journalState==State::ReleasePending&&actor_lifetime::watch[0].pins==1,"off-current living Sora remains pinned while Mickey is current");
    Check(Get(1)==20&&Get(1,1)==8,"off-current restore never writes either actor");
    auto mickey=Run(Acquire(3,2));Check(mickey.outcome==Outcome::Applied&&mickey.originalBits[1]==Bits(8.f),"new actor receives separately captured baseline");
    context.player=reinterpret_cast<uintptr_t>(actors[0]);Tick(context);Check(Get(1)==8&&FindLease(r.leaseId)->state==State::Released,"return to exact original generation completes deferred cleanup");
    Reset();r=Run(Acquire());actor_lifetime::watch[0].retired=true;actor_lifetime::watch[1]={2,context.player,false,0};Set(1,20);Tick(context);
    Check(FindLease(r.leaseId)->state==State::Destroyed&&Get(1)==20,"replacement with identical applied value is never restored using old original");
    Reset();r=Run(Acquire());actor_lifetime::ready=false;actor_lifetime::status=2;Tick(context);
    Check(FindLease(r.leaseId)->state==State::Uncertain&&Get(1)==20&&actor_lifetime::watch[0].pins==1,"observer failure does not pretend actor destruction or discard originals");
}
void Gates(){
    for(unsigned mode=0;mode<5;++mode){Reset();auto q=Acquire();if(mode==0)controlled=false;if(mode==1)canMove=false;if(mode==2)canWrite=false;if(mode==3)context.sceneReady=false;if(mode==4)g_gameThread=0;
        auto r=Run(q);Check(r.outcome==Outcome::Rejected&&Get(0)==2&&Get(1)==8,"all command gates precede cohort writes");}
    Reset();auto r=Run(Acquire());controlled=false;auto release=Run(LeaseRequest(Operation::ReleaseIntent,r));
    Check(release.journalState==State::ReleasePending&&Get(1)==20,"release intent accepted in menu without game writes");
    Tick(context);Check(Get(1)==20,"menu continues to defer restoration");controlled=true;Tick(context);Check(Get(1)==8,"control recovery finishes exact-generation cleanup");
    Reset();r=Run(Acquire());controlled=false;Tick(context,true);Check(Get(1)==20&&FindLease(r.leaseId)->state==State::ReleasePending,"host expiry marks intent while control blocked");
    controlled=true;Tick(context,true);Check(Get(1)==8,"host expiry cleanup does not need a live host");
    for(auto reason:{Reason::Expired,Reason::HostExpired,Reason::InvalidRequest}){Reset();auto q=Acquire();auto rejected=Execute(context,q,987,reason);
        Check(rejected.clientId==q.clientId&&rejected.opId==q.opId&&rejected.requestSequence==987&&rejected.reason==reason&&!(rejected.flags&HasReceipt),"global rejection carries fresh typed response");Check(Get(1)==8,"pre-rejected command writes nothing");}
}
void Bounds(){
    Reset();auto q=Acquire();for(unsigned i=0;i<ReceiptCount;++i){q.opId=++operation;q.expectedBits[0]=Bits(-1.f);Check(Run(q).outcome==Outcome::Rejected,"rejected mutation retained");}
    auto full=Run(Acquire());Check(full.reason==Reason::JournalFull&&Get(1)==8,"full receipt journal blocks before any write");
    auto ack=Base(Operation::AcknowledgeReceipt);ack.targetOpId=receipts[0].request.opId;Check(Run(ack).outcome==Outcome::ReceiptAcknowledged,"ack remains possible with full journal");
    Check(Run(Acquire()).outcome==Outcome::Applied,"receipt capacity available after explicit ack");
    Reset();for(unsigned i=0;i<LeaseCount;++i){actor_lifetime::watch[i]={i+1,context.player,false,0};auto acquired=Run(Acquire(1,i+1,100+i));Check(acquired.outcome==Outcome::Applied,"bounded independent lifetime lease acquired");Ack(acquired);}
    actor_lifetime::watch[LeaseCount]={LeaseCount+1,context.player,false,0};auto overflow=Run(Acquire(1,LeaseCount+1));Check(overflow.reason==Reason::JournalFull,"no live lease eviction at capacity");
    Reset();auto r=Run(Acquire());auto overlap=Run(Acquire());Check(overlap.reason==Reason::LeaseConflict,"overlapping lease refused");
    auto disjoint=Run(Acquire(12));Check(disjoint.outcome==Outcome::Applied,"disjoint jump cohort coexists with speed");
    auto wrong=LeaseRequest(Operation::ReleaseIntent,r);wrong.clientId=2;Check(Run(wrong).reason==Reason::NotOwner,"foreign client cannot restore a lease");
    wrong=LeaseRequest(Operation::ReleaseIntent,r);++wrong.expectedLeaseRevision;Check(Run(wrong).reason==Reason::RevisionMismatch,"stale revision cannot restore");
    auto malformed=Acquire();malformed.reserved1=1;Check(Run(malformed).reason==Reason::InvalidRequest,"nonzero reserved data rejected");
    malformed=Acquire();malformed.bridgeInstance++;Check(Run(malformed).reason==Reason::StaleBridge,"prior process token rejected");
}
void PartialWrites(){
    for(unsigned stage=0;stage<3;++stage){
        Reset();Response prior{};Request q{};
        if(stage==0)q=Acquire();
        else {prior=Run(Acquire());Ack(prior);
            if(stage==1){Set(0,7);Set(1,9);q=LeaseRequest(Operation::Reapply,prior);q.actorGeneration=1;q.mask=3;
                q.expectedBits[0]=Bits(7.f);q.expectedBits[1]=Bits(9.f);q.desiredBits[0]=Bits(5.f);q.desiredBits[1]=Bits(20.f);}
            else q=LeaseRequest(Operation::ReleaseIntent,prior);
        }
        testWriteCalls=0;testFailAfterWrites=1;auto fault=Run(q);
        Check(fault.outcome==Outcome::Rejected&&fault.reason==Reason::WriteFault&&fault.journalState==State::Uncertain,"partial write has no fabricated success");
        Check(fault.leaseId&&fault.actorGeneration==1&&fault.effectOwnerId==10&&(fault.flags&HasReceipt),"partial-write receipt binds retained lease and lifetime");
        auto* l=FindLease(fault.leaseId);Check(l&&l->state==State::Uncertain&&l->pinned,"partial-write ownership remains pinned and uncertain");
        Check(fault.originalBits[0]==Bits(stage==1?7.f:2.f)&&fault.originalBits[1]==Bits(stage==1?9.f:8.f),"partial-write receipt keeps correct originals");
        const float walk=Get(0),run=Get(1);testFailAfterWrites=-1;Tick(context,true);
        Check(Get(0)==walk&&Get(1)==run,"tick and host expiry never retry an uncertain write");
        auto query=Base(Operation::QueryOperation);query.targetOpId=q.opId;auto recovered=Run(query);
        Check(recovered.leaseId==fault.leaseId&&recovered.journalState==State::Uncertain&&recovered.reason==Reason::WriteFault,"lost partial-write ack resolves to bound uncertain result");
        auto released=Run(LeaseRequest(Operation::ReleaseIntent,fault));Check(released.outcome==Outcome::Rejected&&Get(0)==walk&&Get(1)==run,"release refuses to guess after partial write");
        auto ack=LeaseRequest(Operation::AcknowledgeReceipt,fault);ack.targetOpId=fault.receiptOpId;
        Check(Run(ack).outcome==Outcome::Rejected&&FindLease(fault.leaseId),"terminal GC cannot delete uncertain originals");
    }
}
}
int main(){Layout();Cohorts();Races();RestoreOwnership();Lifetimes();Gates();Bounds();PartialWrites();printf("MovementTransactionTests: %u checks, %u failures\n",checks,failures);return failures?1:0;}
