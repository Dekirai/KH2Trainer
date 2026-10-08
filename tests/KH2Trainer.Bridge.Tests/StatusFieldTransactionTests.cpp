#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <limits>
#include <initializer_list>
#ifndef STATUS_FIELDS_PRODUCTION_COMPILE
#define KH2_STATUS_FIELDS_TESTS
#endif
#include "../../src/KH2Trainer.Bridge/StatusFieldTransactionSupport.h"

#ifdef STATUS_FIELDS_PRODUCTION_COMPILE
status_fields::Response ProductionCompile(status_fields::Journal& journal,const status_fields::Request& request) {
    return journal.Execute(request);
}
#else
namespace {
using namespace status_fields;
unsigned checks=0,failures=0;
void Check(bool passed,const char* name){++checks;if(!passed){++failures;printf("FAIL: %s\n",name);}}
uint64_t __fastcall Init(uintptr_t value){return value;}
HANDLE enteredOriginal=nullptr,finishOriginal=nullptr;
uint64_t __fastcall Rebuild(uintptr_t value,const unsigned char*){
    if(enteredOriginal){SetEvent(enteredOriginal);if(WaitForSingleObject(finishOriginal,10000)!=WAIT_OBJECT_0)ExitProcess(5);}
    return value;
}
uint64_t __fastcall Coefficient(uintptr_t value,int,int){return value;}
uint64_t __fastcall Release(uintptr_t value){return value;}
void __fastcall ResetPool(uintptr_t){}
constexpr uint64_t Instance=0xA5A51234ABCD9876ULL;
struct Fixture {
    unsigned char* memory=nullptr;
    uintptr_t pool=0,actor=0,table=0;
    status_observer::Observer observer{};
    Journal journal{};
    uint64_t nextOperation=0,generation=0x4000000000000001ULL;
    unsigned pins=0,inspectCalls=0;Role role=Role::Sora;
    ActorState actorState=ActorState::Current;bool controllable=true,pinGood=true;
    static ActorState Inspect(void* pointer,uint64_t generation,ActorInfo& out) noexcept {
        auto& f=*static_cast<Fixture*>(pointer);++f.inspectCalls;
        if(generation!=f.generation)return ActorState::Retired;
        out={f.actor,f.role,f.controllable};return f.actorState;
    }
    static bool Pin(void* pointer,uint64_t generation) noexcept {
        auto& f=*static_cast<Fixture*>(pointer);
        if(!f.pinGood || generation!=f.generation || f.actorState!=ActorState::Current)return false;
        ++f.pins;return true;
    }
    static void Unpin(void* pointer,uint64_t) noexcept {auto& f=*static_cast<Fixture*>(pointer);if(f.pins)--f.pins;}
    explicit Fixture(bool arm=true) {
        memory=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x20000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
        if(!memory){printf("fatal allocation failure\n");ExitProcess(3);}
        pool=reinterpret_cast<uintptr_t>(memory);actor=pool+0x10000;table=pool+0x18000;
        *reinterpret_cast<int*>(pool+status_observer::FreeCountOffset)=79;
        for(unsigned i=0;i<79;++i)reinterpret_cast<int*>(pool+status_observer::FreeListOffset)[i]=static_cast<int>(i+1);
        for(unsigned slot=0;slot<status_revision::SlotCount;++slot) {
            const auto status=pool+slot*status_observer::StatusSize;
            *reinterpret_cast<int*>(status+612)=1;*reinterpret_cast<uintptr_t*>(status+504)=status;
            *reinterpret_cast<uint32_t*>(status+616)=Pack(actor);
            const uint32_t defaults[5]={100,Bits(10.f),Bits(1.f),Bits(2.f),Bits(1.f)};
            for(unsigned i=0;i<FieldCount;++i)memcpy(reinterpret_cast<void*>(status+Offsets[i]),&defaults[i],Widths[i]);
        }
        *reinterpret_cast<uintptr_t*>(actor+1472)=pool;
        reinterpret_cast<uintptr_t*>(table)[1]=actor&~uintptr_t(0x1ffffffu);
        Check(observer.Bind({&Init,&Rebuild,&Coefficient,&ResetPool,&Release},pool,Instance,GetCurrentThreadId()),"fixture Observer bind");
        if(arm)Check(observer.ArmAfterProvenBarrier(Instance),"synthetic fixture has no preexisting writers");
        Check(journal.Bind(observer,{this,&Inspect,&Pin,&Unpin},table,Instance,GetCurrentThreadId()),"Journal binds once");
    }
    ~Fixture(){VirtualFree(memory,0,MEM_RELEASE);}
    static uint32_t Pack(uintptr_t value){return (1u<<25)|static_cast<uint32_t>(value&0x1ffffffu);}
    uintptr_t Status(){return *reinterpret_cast<uintptr_t*>(actor+1472);}
    uint32_t Get(unsigned field){uint32_t bits=0;memcpy(&bits,reinterpret_cast<void*>(Status()+Offsets[field]),Widths[field]);return bits;}
    void Set(unsigned field,uint32_t bits){memcpy(reinterpret_cast<void*>(Status()+Offsets[field]),&bits,Widths[field]);}
    Request Base(Operation operation){Request q{};q.operation=operation;q.clientId=1;q.opId=++nextOperation;q.bridgeInstance=Instance;return q;}
    Snapshot Capture(uint32_t mask=AllFields){Snapshot value{};Reason why{};Check(journal.ReadCurrent(generation,mask,value,why),"snapshot captures validated exact fields");return value;}
    Request Write(Operation operation=Operation::Acquire,uint32_t mask=AllFields) {
        const auto snapshot=Capture(mask);auto q=Base(operation);q.ownerId=100;q.actorGeneration=generation;
        q.mask=mask;q.expectedStamp=snapshot.stamp;memcpy(q.expectedBits,snapshot.bits,sizeof(q.expectedBits));
        const uint32_t desired[5]={50,Bits(600.f),Bits(4.f),Bits(9.f),Bits(.25f)};
        for(unsigned i=0;i<FieldCount;++i)if(mask&(1u<<i))q.desiredBits[i]=desired[i];return q;
    }
    Request LeaseRequest(Operation operation,const Response& response){auto q=Base(operation);q.ownerId=response.ownerId;q.leaseId=response.leaseId;
        if(operation==Operation::ReleaseIntent || operation==Operation::AcknowledgeLease)q.leaseRevision=response.leaseRevision;return q;}
    Response Query(const Response& response){return journal.Execute(LeaseRequest(Operation::QueryLease,response));}
    void Ack(const Response& response){auto q=Base(Operation::Acknowledge);q.targetOpId=response.receiptOpId;Check(journal.Execute(q).outcome==Outcome::Acknowledged,"explicit receipt acknowledgement");}
};
void FieldsAndCohorts(){
    Check(Offsets[0]==430 && Widths[0]==1 && Offsets[1]==520 && Offsets[2]==568 && Offsets[3]==572 && Offsets[4]==580,"retail BYTE and float32 field layout");
    for(uint32_t mask=1;mask<=AllFields;++mask){Fixture f;const auto q=f.Write(Operation::Acquire,mask);unsigned char before[632];memcpy(before,reinterpret_cast<void*>(f.Status()),632);
        const auto applied=f.journal.Execute(q);Check(applied.outcome==Outcome::Applied&&applied.remainingMask==mask&&applied.receiptOpId==q.opId,"all nonempty field cohorts acquired");
        Check(applied.actorGeneration==f.generation&&applied.bridgeInstance==Instance&&applied.leaseId&&f.pins==1,"receipt binds full width instance and pinned actor generation");
        for(unsigned i=0;i<FieldCount;++i){if(mask&(1u<<i)){
            Check(f.Get(i)==q.desiredBits[i],"selected native field receives exact desired bits");
            Check(applied.originalBits[i]==q.expectedBits[i]&&applied.appliedBits[i]==q.desiredBits[i],"lease retains exact original and applied bits");
            memcpy(before+Offsets[i],&q.desiredBits[i],Widths[i]);}}
        Check(!memcmp(before,reinterpret_cast<void*>(f.Status()),632),"all bytes outside typed field widths unchanged");
        const auto released=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,applied));
        Check(released.state==State::Released&&released.restoredMask==mask&&f.pins==0,"all still owned field cohorts restore");
        for(unsigned i=0;i<FieldCount;++i)if(mask&(1u<<i))Check(f.Get(i)==q.expectedBits[i],"restore exact captured original bits");
        f.Ack(applied);f.Ack(released);Check(f.Query(released).reason==Reason::LeaseMissing,"terminal lease collected only after all referencing receipts acknowledged");
    }
}
void RevisionsAndBits(){
    for(unsigned field=0;field<FieldCount;++field){Fixture f;auto q=f.Write(Operation::Acquire,1u<<field);const auto applied=f.journal.Execute(q);
        f.observer.Rebuild(f.Status(),nullptr);const auto released=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,applied));
        Check(released.state==State::Superseded&&released.supersededMask==(1u<<field)&&f.Get(field)==q.desiredBits[field],"same-value native rebuild supersedes every selected field");}
    {Fixture f;auto q=f.Write();f.observer.Rebuild(f.Status(),nullptr);auto stale=f.journal.Execute(q);
        Check(stale.reason==Reason::RevisionMismatch&&f.Get(0)==100&&f.pins==0,"same-value rebuild between snapshot and Acquire rejects stale revision");}
    {Fixture f;auto q=f.Write();++q.expectedStamp.allocation;Check(f.journal.Execute(q).reason==Reason::AllocationMismatch,"wrong allocation serial rejected before write");}
    {Fixture f;auto q=f.Write();q.expectedStamp.fields[4]++;Check(f.journal.Execute(q).reason==Reason::RevisionMismatch&&f.Get(0)==100,"last field revision mismatch blocks earlier field write");}
    {Fixture f;auto q=f.Write();f.Set(4,Bits(.5f));Check(f.journal.Execute(q).reason==Reason::ExpectedMismatch&&f.Get(0)==100,"last field exact-bit mismatch blocks entire cohort");}
    {Fixture f;auto q=f.Write();const auto applied=f.journal.Execute(q);f.Set(0,77);f.Set(2,Bits(7.f));
        auto released=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,applied));
        Check(released.state==State::Superseded&&released.supersededMask==5&&released.restoredMask==26,"external exact-bit changes preserve fields independently");
        Check(f.Get(0)==77&&f.Get(2)==Bits(7.f)&&f.Get(1)==Bits(10.f),"only exact still-owned bits restore");}
    {Fixture f;f.Set(1,Bits(-0.f));auto q=f.Write(Operation::Acquire,2);auto applied=f.journal.Execute(q);
        auto released=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,applied));
        Check(released.state==State::Released&&f.Get(1)==0x80000000u,"negative zero original preserved exactly through restore");}
    {Fixture f;auto q=f.Write(Operation::Acquire,2);q.desiredBits[1]=Bits(-0.f);auto applied=f.journal.Execute(q);f.Set(1,Bits(+0.f));
        auto released=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,applied));
        Check(released.state==State::Superseded&&f.Get(1)==0,"signed-zero external write not overwritten");}
    {Fixture f;auto all=f.journal.Execute(f.Write());auto manual=f.Write(Operation::ManualWrite,2);manual.desiredBits[1]=f.Get(1);
        Check(f.journal.Execute(manual).outcome==Outcome::ManualApplied,"same-value typed manual store succeeds");
        auto released=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,all));
        Check(released.supersededMask==2&&released.restoredMask==29&&f.Get(1)==manual.desiredBits[1],"same-value ManualWrite supersedes exactly its selected field");}
    {Fixture f;auto all=f.journal.Execute(f.Write());f.observer.Coefficient(f.Status(),6,50);
        auto released=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,all));
        Check(released.supersededMask==1&&released.restoredMask==30,"native General setter invalidates only General");}
    {Fixture f;auto all=f.journal.Execute(f.Write());f.observer.Coefficient(f.Status(),5,50);
        auto released=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,all));
        Check(released.restoredMask==AllFields,"different native element coefficient does not supersede selected fields");}
}
void AllocationAndActors(){
    for(unsigned kind=0;kind<3;++kind){Fixture f;auto q=f.Write();auto applied=f.journal.Execute(q);
        if(kind==0)f.observer.Reset(f.pool);else if(kind==1)f.observer.Release(f.Status());else f.observer.Initialize(f.Status());
        const auto released=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,applied));
        Check(released.state==State::AllocationEnded&&released.restoredMask==0&&f.Get(0)==q.desiredBits[0]&&f.pins==0,"reset release or same-address initialization ends old allocation without restore");}
    {Fixture f;auto applied=f.journal.Execute(f.Write());*reinterpret_cast<int*>(f.Status()+612)=2;f.observer.Release(f.Status());
        Check(f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,applied)).state==State::Released,"nonfinal reference release preserves ownership");}
    {Fixture f;auto applied=f.journal.Execute(f.Write());f.actorState=ActorState::OffCurrent;
        const auto pending=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,applied));
        Check(pending.state==State::ReleasePending&&f.pins==1&&f.Get(0)==50,"living off-current Sora remains pending and pinned");
        DWORD old=0;VirtualProtect(reinterpret_cast<void*>(f.actor),4096,PAGE_NOACCESS,&old);f.journal.Tick();
        Check(f.Query(pending).state==State::ReleasePending,"off-current path never dereferences former Actor");
        VirtualProtect(reinterpret_cast<void*>(f.actor),4096,old,&old);f.actorState=ActorState::Current;f.journal.Tick();
        Check(f.Query(pending).state==State::Released&&f.Get(0)==100,"return to exact current generation completes pending cleanup");}
    {Fixture f;auto applied=f.journal.Execute(f.Write());f.actorState=ActorState::OffCurrent;f.observer.Rebuild(f.Status(),nullptr);
        Check(f.Query(applied).state==State::Superseded&&f.Get(0)==50&&f.pins==0,"off-current native rebuild supersedes without stale scalar reads");}
    {Fixture f;auto applied=f.journal.Execute(f.Write());++f.generation;f.journal.Tick();
        Check(f.Query(applied).state==State::ActorRetired&&f.Get(0)==50&&f.pins==0,"same-address Actor generation replacement never restores old baseline");}
    {Fixture f;auto q=f.Write();++f.generation;Check(f.journal.Execute(q).reason==Reason::ActorUnavailable,"stale generation Acquire rejected");}
    {Fixture f;auto applied=f.journal.Execute(f.Write());f.actorState=ActorState::Unavailable;f.journal.Tick();
        Check(f.Query(applied).state==State::Uncertain&&f.pins==1,"unavailable Actor observer never fabricates destruction");
        f.actorState=ActorState::Current;f.journal.Tick(true);Check(f.Get(0)==50,"uncertain Actor ownership never retried");}
    {Fixture f;auto applied=f.journal.Execute(f.Write());*reinterpret_cast<int*>(f.pool+status_observer::FreeCountOffset)=0;
        *reinterpret_cast<uintptr_t*>(f.actor+1472)=f.pool+status_observer::StatusSize;
        auto ended=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,applied));
        Check(ended.state==State::BindingChanged&&*reinterpret_cast<unsigned char*>(f.pool+430)==50&&f.Get(0)==100,"changed Actor STATUS binding preserves both still allocated slots");}
}
void GatesAndLayout(){
    for(auto role:{Role::Sora,Role::Roxas,Role::Mickey}){Fixture f;f.role=role;
        const auto q=f.Write(Operation::Acquire,role==Role::Mickey?7:AllFields);auto applied=f.journal.Execute(q);
        Check(applied.outcome==Outcome::Applied,"validated Sora Roxas and Mickey supported field cohort");
        Check(f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,applied)).state==State::Released,"supported role restores typed fields");}
    for(unsigned mode=0;mode<12;++mode){Fixture f;auto q=f.Write();
        if(mode==0)f.controllable=false;
        if(mode==1)f.role=Role::Unknown;
        if(mode==2)f.actorState=ActorState::OffCurrent;
        if(mode==3)f.pinGood=false;
        if(mode==4)*reinterpret_cast<uintptr_t*>(f.Status()+504)=f.Status()+8;
        if(mode==5)*reinterpret_cast<uint32_t*>(f.Status()+616)=0;
        if(mode==6)*reinterpret_cast<int*>(f.Status()+612)=0;
        if(mode==7)*reinterpret_cast<int*>(f.pool+status_observer::FreeCountOffset)=81;
        if(mode==8)reinterpret_cast<int*>(f.pool+status_observer::FreeListOffset)[0]=0;
        if(mode==9)reinterpret_cast<int*>(f.pool+status_observer::FreeListOffset)[1]=1;
        if(mode==10)*reinterpret_cast<uintptr_t*>(f.actor+1472)=f.pool+1;
        if(mode==11)f.role=Role::Mickey;
        auto r=f.journal.Execute(q);Check(r.outcome==Outcome::Rejected&&*reinterpret_cast<unsigned char*>(f.pool+430)==100&&f.pins==0,"every admission guard precedes first field write or pin");
    }
    {Fixture f;auto q=f.Write();DWORD old=0;VirtualProtect(reinterpret_cast<void*>(f.pool),4096,PAGE_READONLY,&old);
        Check(f.journal.Execute(q).reason==Reason::NotWritable&&f.Get(0)==100,"read-only STATUS page rejects before write");
        VirtualProtect(reinterpret_cast<void*>(f.pool),4096,old,&old);}
    {Fixture f;auto q=f.Write();DWORD old=0;VirtualProtect(reinterpret_cast<void*>(f.table),4096,PAGE_NOACCESS,&old);
        Check(f.journal.Execute(q).reason==Reason::InvalidBinding&&f.Get(0)==100,"unreadable native packed base table rejects");
        VirtualProtect(reinterpret_cast<void*>(f.table),4096,old,&old);}
    {Fixture f;auto q=f.Write();reinterpret_cast<uintptr_t*>(f.table)[1]^=uintptr_t(1)<<40;
        Check(f.journal.Execute(q).reason==Reason::InvalidBinding,"wrong high packed backlink bits reject");}
    {Fixture f(false);Snapshot snapshot{};Reason why{};
        Check(!f.journal.ReadCurrent(f.generation,AllFields,snapshot,why)&&why==Reason::ObserverUnavailable,"bootstrap never admits field snapshot");}
    {Fixture f;auto applied=f.journal.Execute(f.Write());f.controllable=false;
        auto pending=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,applied));
        Check(pending.state==State::ReleasePending&&f.Get(0)==50,"menu or cutscene accepts release intent without writes");
        f.journal.Tick(true);Check(f.Get(0)==50,"host expiry does not bypass control gates");
        f.controllable=true;f.journal.Tick();Check(f.Get(0)==100,"control recovery completes queued restore");}
    {Fixture f;auto applied=f.journal.Execute(f.Write());f.observer.Fault();f.journal.Tick();
        Check(f.Query(applied).state==State::Uncertain&&f.Get(0)==50&&f.pins==1,"STATUS observer fault preserves uncertain ownership and original bytes");}
    {Fixture f;auto applied=f.journal.Execute(f.Write());f.observer.Coefficient(f.Status(),-1,50);
        auto rejected=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,applied));
        Check(rejected.reason==Reason::ObserverFault&&f.Query(applied).state==State::Uncertain&&f.Get(0)==50,"unsupported native signed index blocks typed ownership globally");}
    {Fixture f;*reinterpret_cast<int*>(f.pool+status_observer::FreeCountOffset)=0;
        *reinterpret_cast<uintptr_t*>(f.actor+1472)=f.pool+38*status_observer::StatusSize;
        auto applied=f.journal.Execute(f.Write());const uintptr_t firstPage=(f.Status()+430)&~uintptr_t(4095);DWORD old=0;
        VirtualProtect(reinterpret_cast<void*>(firstPage),4096,PAGE_READONLY,&old);
        auto pending=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,applied));
        Check(pending.state==State::ReleasePending&&pending.restoredMask==28&&pending.remainingMask==3,"temporarily read-only fields defer while independent writable fields restore");
        Check(f.Get(0)==50&&f.Get(1)==Bits(600.f)&&f.Get(2)==Bits(1.f),"partial ready cohort commits only writable owned bytes");
        VirtualProtect(reinterpret_cast<void*>(firstPage),4096,old,&old);f.journal.Tick();
        auto completed=f.Query(pending);Check(completed.state==State::Released&&completed.restoredMask==31&&f.Get(0)==100&&f.Get(1)==Bits(10.f),"remaining exact revisions survive earlier partial restore and finish later");}
    for(unsigned slot=0;slot<80;++slot){Fixture f;*reinterpret_cast<int*>(f.pool+status_observer::FreeCountOffset)=0;
        *reinterpret_cast<uintptr_t*>(f.actor+1472)=f.pool+slot*status_observer::StatusSize;
        auto applied=f.journal.Execute(f.Write(Operation::Acquire,1));
        Check(applied.outcome==Outcome::Applied&&f.Get(0)==50,"all eighty pool slots map exact General byte");
        Check(f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,applied)).state==State::Released&&f.Get(0)==100,"all eighty slots restore only their own allocation");}
}
void Values(){
    for(unsigned i=0;i<FieldCount;++i)for(uint32_t invalid:{0x7fc00001u,0x7f800000u,0xff800000u,0xbf800000u}) {
        Fixture f;auto q=f.Write(Operation::Acquire,1u<<i);q.desiredBits[i]=invalid;
        Check(f.journal.Execute(q).reason==Reason::InvalidValues&&f.pins==0,"NaN infinity negative or oversized byte desired value rejected without clamp");
    }
    const uint32_t maximum[5]={255,Bits(5000.f),Bits(9.f),Bits(99.f),Bits(1.f)};
    for(unsigned i=0;i<FieldCount;++i){Fixture f;auto q=f.Write(Operation::Acquire,1u<<i);q.desiredBits[i]=maximum[i];
        Check(f.journal.Execute(q).outcome==Outcome::Applied&&f.Get(i)==maximum[i],"inclusive field maximum retained exactly");}
    {Fixture f;auto q=f.Write(Operation::Acquire,1);q.desiredBits[0]=256;Check(f.journal.Execute(q).reason==Reason::InvalidValues,"General upper bits cannot silently truncate");}
    {Fixture f;auto q=f.Write(Operation::Acquire,2);f.Set(1,0x7fc00001u);q.expectedBits[1]=f.Get(1);
        Check(f.journal.Execute(q).reason==Reason::InvalidValues&&f.Get(1)==0x7fc00001u,"invalid native adoption value is preserved and not clamped");}
    {Fixture f;auto applied=f.journal.Execute(f.Write(Operation::Acquire,2));f.Set(1,0x7fc00001u);
        auto released=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,applied));
        Check(released.state==State::Superseded&&f.Get(1)==0x7fc00001u,"external NaN at cleanup supersedes and is preserved exactly");}
}
void ReceiptsAndBounds(){
    {Fixture f;auto q=f.Write();auto applied=f.journal.Execute(q);f.Set(0,77);const int writes=f.journal.testWriteCalls;
        auto replay=f.journal.Execute(q);Check(replay.outcome==Outcome::Applied&&replay.leaseId==applied.leaseId&&f.Get(0)==77&&writes==f.journal.testWriteCalls,"duplicate request replays immutable receipt without scalar access or writes");
        q.desiredBits[0]=11;Check(f.journal.Execute(q).reason==Reason::RequestIdConflict&&f.Get(0)==77,"same request ID different payload conflicts");q.desiredBits[0]=50;
        auto query=f.Base(Operation::QueryOperation);query.targetOpId=applied.receiptOpId;
        auto found=f.journal.Execute(query);Check(found.leaseId==applied.leaseId&&found.receiptOpId==applied.opId&&found.opId==query.opId,"lost acknowledgement resolved from exact durable receipt");
        f.Ack(applied);Check(f.journal.Execute(q).reason==Reason::RetiredRequest&&f.Get(0)==77,"acknowledged ID retains monotonic tombstone and can never write again");
        Check(f.journal.Execute(query).reason==Reason::ReceiptMissing,"acknowledged operation is explicitly absent");}
    {Fixture f;auto q=f.Write();q.expectedBits[0]=0;const auto rejected=f.journal.Execute(q);q.expectedBits[0]=100;
        Check(rejected.reason==Reason::ExpectedMismatch&&f.journal.Execute(q).reason==Reason::RequestIdConflict,"rejected mutations also retain request identity");}
    {Fixture f;auto q=f.Write();q.clientId=2;auto r=f.journal.Execute(q);auto foreign=f.LeaseRequest(Operation::ReleaseIntent,r);
        Check(f.journal.Execute(foreign).reason==Reason::NotOwner&&f.Get(0)==50,"foreign client cannot release another owner's lease");
        foreign.clientId=2;foreign.opId=++f.nextOperation;foreign.ownerId++;
        Check(f.journal.Execute(foreign).reason==Reason::NotOwner,"wrong effect owner rejected");}
    {Fixture f;auto applied=f.journal.Execute(f.Write());auto stale=f.LeaseRequest(Operation::ReleaseIntent,applied);++stale.leaseRevision;
        Check(f.journal.Execute(stale).reason==Reason::RevisionMismatch&&f.Get(0)==50,"stale lease revision cannot restore");}
    {Fixture f;auto q=f.Write();Response first{};
        for(unsigned i=0;i<ReceiptCount;++i){q.opId=++f.nextOperation;q.desiredBits[0]=256;auto r=f.journal.Execute(q);if(!i)first=r;
            Check(r.reason==Reason::InvalidValues&&r.receiptOpId==q.opId,"bounded journal retains every rejected mutation");}
        q.opId=++f.nextOperation;q.desiredBits[0]=50;Check(f.journal.Execute(q).reason==Reason::Capacity&&f.Get(0)==100,"receipt capacity exhausted before any mutation");
        f.Ack(first);Check(f.journal.Execute(q).outcome==Outcome::Applied,"capacity refusal did not consume operation ID or drop existing receipt");}
    {Fixture f;auto q=f.Write();q.desiredBits[0]=256;
        for(unsigned i=0;i<ClientCount;++i){q.clientId=i+1;q.opId=1;Check(f.journal.Execute(q).reason==Reason::InvalidValues,"bounded client tombstones allocated");}
        q.clientId=ClientCount+1;Check(f.journal.Execute(q).reason==Reason::Capacity&&f.Get(0)==100,"client capacity never evicts an acknowledged-ID tombstone");}
    {Fixture f;auto first=f.journal.Execute(f.Write(Operation::Acquire,1));
        auto overlap=f.journal.Execute(f.Write(Operation::Acquire,1));Check(overlap.reason==Reason::Conflict,"overlapping allocation field lease rejected");
        auto disjoint=f.journal.Execute(f.Write(Operation::Acquire,2));Check(disjoint.outcome==Outcome::Applied&&f.pins==2,"disjoint native fields coexist");
        auto r1=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,first));auto r2=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,disjoint));
        Check(r1.state==State::Released&&r2.state==State::Released&&f.pins==0,"disjoint restore revisions do not invalidate each other");}
    {Fixture f;auto q=f.Write();++q.bridgeInstance;Check(f.journal.Execute(q).reason==Reason::StaleInstance,"stale bridge session rejected");}
    {Fixture f;auto q=f.Write();q.mask=32;Check(f.journal.Execute(q).reason==Reason::InvalidRequest,"unknown field mask rejected");}
    {Fixture f;auto q=f.Write(Operation::Acquire,1);q.desiredBits[4]=Bits(.5f);Check(f.journal.Execute(q).reason==Reason::InvalidRequest,"unselected field payload rejected");}
    {Fixture f;*reinterpret_cast<int*>(f.pool+status_observer::FreeCountOffset)=0;
        for(unsigned slot=0;slot<LeaseCount;++slot){*reinterpret_cast<uintptr_t*>(f.actor+1472)=f.pool+slot*status_observer::StatusSize;
            auto acquired=f.journal.Execute(f.Write(Operation::Acquire,1));Check(acquired.outcome==Outcome::Applied,"bounded distinct STATUS allocation lease reserved");f.Ack(acquired);}
        *reinterpret_cast<uintptr_t*>(f.actor+1472)=f.pool+LeaseCount*status_observer::StatusSize;
        Check(f.journal.Execute(f.Write(Operation::Acquire,1)).reason==Reason::Capacity&&f.Get(0)==100&&f.pins==LeaseCount,"lease capacity never evicts live ownership or writes unjournaled bytes");}
    {Fixture f;auto q=f.Write();q.opId=UINT64_MAX;auto acquired=f.journal.Execute(q);Check(acquired.outcome==Outcome::Applied,"maximum operation token has no arithmetic wrap");f.Ack(acquired);
        q.opId=1;Check(f.journal.Execute(q).reason==Reason::RetiredRequest,"wrapped low operation ID can never be accepted as new");}
    {Fixture f;auto acquired=f.journal.Execute(f.Write());
        Check(f.journal.Execute(f.LeaseRequest(Operation::AcknowledgeLease,acquired)).reason==Reason::Conflict,"active lease cannot be garbage collected");
        f.Ack(acquired);f.controllable=false;auto pending=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,acquired));f.Ack(pending);
        f.controllable=true;f.journal.Tick();auto terminal=f.Query(pending);
        Check(terminal.state==State::Released,"asynchronous terminal state remains queryable after operation receipts acknowledged");
        auto gc=f.LeaseRequest(Operation::AcknowledgeLease,terminal);Check(f.journal.Execute(gc).outcome==Outcome::Acknowledged,"explicit terminal acknowledgement collects orphaned completed lease");
        Check(f.Query(terminal).reason==Reason::LeaseMissing,"explicit terminal GC frees bounded journal slot");
        Check(f.journal.Execute(gc).reason==Reason::LeaseMissing&&f.Get(0)==100,"delayed duplicate GC cannot mutate game fields");}
    {Fixture f;auto acquired=f.journal.Execute(f.Write());auto terminal=f.journal.Execute(f.LeaseRequest(Operation::ReleaseIntent,acquired));
        Check(f.journal.Execute(f.LeaseRequest(Operation::AcknowledgeLease,terminal)).reason==Reason::Conflict,"terminal GC cannot discard state referenced by durable receipts");}
}
void PartialWrites(){
    for(unsigned stage=0;stage<3;++stage)for(int failed=0;failed<5;++failed){Fixture f;Response applied{};Request q{};
        if(stage<2)q=f.Write(stage==0?Operation::Acquire:Operation::ManualWrite);
        else {applied=f.journal.Execute(f.Write());q=f.LeaseRequest(Operation::ReleaseIntent,applied);}
        f.journal.testWriteCalls=0;f.journal.testFailAfterWrites=failed;const auto fault=f.journal.Execute(q);
        Check(fault.outcome==Outcome::Rejected&&fault.state==State::Uncertain&&fault.reason==Reason::WriteFault,"partial Acquire ManualWrite or restore reports correlated uncertainty");
        Check(fault.receiptOpId==q.opId&&fault.actorGeneration==f.generation&&fault.originalBits[0]==100,"uncertain receipt preserves request binding and pre-write originals");
        uint32_t after[5];for(unsigned i=0;i<5;++i)after[i]=f.Get(i);
        const int attempts=f.journal.testWriteCalls;f.journal.testFailAfterWrites=-1;
        const auto replay=f.journal.Execute(q);Check(replay.state==State::Uncertain&&f.journal.testWriteCalls==attempts,"uncertain operation replay never repeats ambiguous writes");
        f.journal.Tick(true);for(unsigned i=0;i<5;++i)Check(f.Get(i)==after[i],"uncertain tick does not restore or complete unconfirmed write");
        auto query=f.Base(Operation::QueryOperation);query.targetOpId=q.opId;
        Check(f.journal.Execute(query).state==State::Uncertain,"uncertain durable receipt query survives STATUS observer fault");
        if(stage!=1){Check(f.Query(fault).state==State::Uncertain&&f.pins==1,"uncertain lease pins Actor and retains originals indefinitely");
            auto retry=f.LeaseRequest(Operation::ReleaseIntent,fault);Check(f.journal.Execute(retry).reason==Reason::ObserverFault,"new release request cannot repair uncertain writes");
            Check(f.journal.Execute(f.LeaseRequest(Operation::AcknowledgeLease,fault)).reason==Reason::Conflict,"uncertain baseline cannot be garbage collected");}
        Check(f.observer.Inspect().phase==status_observer::Phase::Fault,"partial manual-write ledger event permanently faults observation");
    }
}
struct ThreadWork {Fixture* fixture;Request request;Response response{};};
DWORD WINAPI ForeignThread(void* value){auto& w=*static_cast<ThreadWork*>(value);w.response=w.fixture->journal.Execute(w.request);w.fixture->journal.Tick(true);return 0;}
DWORD WINAPI BlockedRebuild(void* value){auto& f=*static_cast<Fixture*>(value);f.observer.Rebuild(f.Status(),nullptr);return 0;}
void ThreadAndBootstrap(){
    Fixture f;ThreadWork work{&f,f.Write()};HANDLE thread=CreateThread(nullptr,0,&ForeignThread,&work,0,nullptr);
    Check(thread!=nullptr,"foreign test thread created");if(!thread)return;
    if(WaitForSingleObject(thread,10000)!=WAIT_OBJECT_0){printf("fatal worker did not join\n");ExitProcess(4);}CloseHandle(thread);
    Check(work.response.reason==Reason::WrongThread&&f.Get(0)==100&&f.pins==0,"foreign thread cannot access or mutate journal metadata");
    Check(f.journal.Execute(work.request).outcome==Outcome::Applied,"wrong-thread rejection did not consume game-thread request ID");
    {Fixture overlap;auto applied=overlap.journal.Execute(overlap.Write());auto release=overlap.LeaseRequest(Operation::ReleaseIntent,applied);
        enteredOriginal=CreateEventW(nullptr,TRUE,FALSE,nullptr);finishOriginal=CreateEventW(nullptr,TRUE,FALSE,nullptr);
        if(!enteredOriginal || !finishOriginal)ExitProcess(6);
        HANDLE worker=CreateThread(nullptr,0,&BlockedRebuild,&overlap,0,nullptr);if(!worker)ExitProcess(7);
        if(WaitForSingleObject(enteredOriginal,10000)!=WAIT_OBJECT_0)ExitProcess(8);
        Check(overlap.observer.Inspect().inFlight==1,"synthetic native writer remains active outside metadata lock");
        Check(overlap.Query(applied).reason==Reason::ObserverUnavailable,"query distinguishes retained lease state from unavailable current observation");
        const auto blocked=overlap.journal.Execute(release);
        Check(blocked.reason==Reason::ObserverUnavailable&&overlap.Get(0)==50,"in-flight native writer blocks typed cleanup transaction");
        Snapshot snapshot{};Reason why{};Check(!overlap.journal.ReadCurrent(overlap.generation,AllFields,snapshot,why)&&why==Reason::ObserverUnavailable,"in-flight native writer prevents adoption snapshot");
        SetEvent(finishOriginal);if(WaitForSingleObject(worker,10000)!=WAIT_OBJECT_0)ExitProcess(9);
        CloseHandle(worker);CloseHandle(enteredOriginal);CloseHandle(finishOriginal);enteredOriginal=finishOriginal=nullptr;
        Check(overlap.journal.Execute(release).reason==Reason::ObserverUnavailable,"previously refused ID remains immutable after native return");
        auto renewed=overlap.journal.Execute(overlap.LeaseRequest(Operation::ReleaseIntent,applied));
        Check(renewed.state==State::Superseded&&renewed.restoredMask==0&&overlap.Get(0)==50,"new cleanup request sees native revision takeover after writer returns");}
}
}
int main(){FieldsAndCohorts();RevisionsAndBits();AllocationAndActors();GatesAndLayout();Values();ReceiptsAndBounds();PartialWrites();ThreadAndBootstrap();
    printf("StatusFieldTransactionTests: %u checks, %u failures\n",checks,failures);return failures?1:0;}
#endif
