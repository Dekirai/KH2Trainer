#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <initializer_list>
#define KH2_STATUS_REVISION_TESTS
#include "../../src/KH2Trainer.Bridge/StatusRevisionLedger.h"
namespace status_revision {
struct LedgerTestAccess { static void Exhaust(Ledger& ledger) { ledger.serial=UINT64_MAX; } };
}
using namespace status_revision;
unsigned checks=0,failures=0;
void Check(bool value,const char* message) { ++checks;if(!value){++failures;printf("FAIL %s\n",message);} }
void EventOnce(Ledger& ledger,Event event,unsigned slot,int parameter=0,uint32_t mask=0) {
    const auto frame=ledger.Enter(event,slot,parameter,mask);ledger.Exit(frame);
}
Stamp Capture(Ledger& ledger,unsigned slot) { Stamp value;Check(ledger.Capture(slot,value,true),"capture validated allocation");return value; }
void Same(const Ledger& ledger,const Stamp& stamp,uint32_t mask,Match expected,uint32_t changed=0) {
    const auto match=ledger.Compare(stamp,mask);Check(match.result==expected && match.changedFields==changed,"exact revision comparison result/mask");
}
void BootstrapAndNativeWrites() {
    Ledger ledger;Stamp none;
    Check(!ledger.Capture(0,none,true),"uninstalled cannot capture");
    Check(ledger.Start(0x1122334455667788ULL),"start once");
    Check(!ledger.Capture(0,none,false) && !none.instance,"pool validation required");
    auto first=Capture(ledger,0),same=Capture(ledger,0);
    Check(first.instance==same.instance && first.allocation==same.allocation,"adoption not repeated");
    Same(ledger,first,AllFields,Match::Current);
    // Same actor, pointer and scalar bytes before and after the native rebuild.
    uint32_t scalars[]={100,0,0,0,0x3f800000};uint32_t before[FieldCount];memcpy(before,scalars,sizeof(scalars));
    auto frame=ledger.Enter(Event::Rebuild,0);
    Check(frame.ticket && ledger.ActiveCalls()==1,"before-entry revision raised");
    Check(!ledger.Capture(0,none,true),"cannot acquire during partial native rebuild");
    Same(ledger,first,AllFields,Match::Unavailable);
    memcpy(scalars,before,sizeof(scalars)); // A rebuild produces the identical defaults.
    ledger.Exit(frame);
    Check(!memcmp(scalars,before,sizeof(scalars)),"native same-value fixture remains identical");
    Same(ledger,first,AllFields,Match::Superseded,AllFields);
    auto rebuilt=Capture(ledger,0);
    Check(rebuilt.allocation==first.allocation,"rebuild is not allocation replacement");
    for(int index=0;index<6;++index)EventOnce(ledger,Event::GeneralWrite,0,index);
    Same(ledger,rebuilt,AllFields,Match::Current);
    EventOnce(ledger,Event::GeneralWrite,0,6);
    Same(ledger,rebuilt,AllFields,Match::Superseded,1u<<General);
    Same(ledger,rebuilt,AllFields&~(1u<<General),Match::Current);
    auto after=Capture(ledger,0);EventOnce(ledger,Event::Initialize,0);
    Same(ledger,after,AllFields,Match::AllocationEnded,AllFields);
    Check(Capture(ledger,0).allocation!=after.allocation,"same slot gets a new allocation token");
}
void IndependentFieldsAndSlots() {
    Ledger ledger;ledger.Start(2);
    Stamp original[SlotCount];for(unsigned i=0;i<SlotCount;++i)original[i]=Capture(ledger,i);
    // Each selected bit is invalidated even when a manual setter writes the same
    // float bits. Disjoint rewards retain their own valid field revisions.
    for(unsigned i=0;i<SlotCount;++i) {
        const uint32_t mask=(i%AllFields)+1;
        EventOnce(ledger,Event::ManualWrite,i,0,mask);
        Same(ledger,original[i],AllFields,Match::Superseded,mask);
        if(mask!=AllFields)Same(ledger,original[i],AllFields^mask,Match::Current);
        if(i+1<SlotCount)Same(ledger,original[i+1],AllFields,Match::Current);
    }
    for(unsigned i=0;i<SlotCount;++i) {
        auto value=Capture(ledger,i);EventOnce(ledger,Event::Release,i,2);
        Same(ledger,value,AllFields,Match::Current);
        EventOnce(ledger,Event::Release,i,1);
        Same(ledger,value,AllFields,Match::AllocationEnded,AllFields);
        EventOnce(ledger,Event::Initialize,i);
        auto next=Capture(ledger,i);Check(next.allocation!=value.allocation,"released address is never its previous allocation");
    }
}
void PoolEpochAndRetirement() {
    Ledger ledger;ledger.Start(3);const auto first=Capture(ledger,7);
    const auto epoch=ledger.PoolEpoch();EventOnce(ledger,Event::PoolReset,SlotCount);
    Check(ledger.PoolEpoch()!=epoch,"pool reset advances epoch");
    Same(ledger,first,AllFields,Match::AllocationEnded,AllFields);
    for(unsigned i=0;i<SlotCount;++i)Check(ledger.SlotLife(i)==Life::Retired,"pool reset retires each allocation");
    EventOnce(ledger,Event::Initialize,7);auto next=Capture(ledger,7);
    Check(next.poolEpoch!=first.poolEpoch && next.allocation!=first.allocation,"reset plus reallocation changes both identities");
    Same(ledger,first,AllFields,Match::AllocationEnded,AllFields);
    EventOnce(ledger,Event::Release,7,1);Stamp unexpected;
    Check(!ledger.Capture(7,unexpected,true) && ledger.Status()==Health::Fault,"observed retired slot cannot be adopted without init");
    Same(ledger,next,AllFields,Match::Unavailable);
}
void ReentrancyAndFailure() {
    Ledger ledger;ledger.Start(4);auto original=Capture(ledger,0);
    auto outer=ledger.Enter(Event::Rebuild,0),inner=ledger.Enter(Event::GeneralWrite,0,6);
    Check(ledger.ActiveCalls()==2,"nested entry tracked");
    ledger.Exit(inner);Stamp blocked;
    Check(ledger.ActiveCalls()==1 && !ledger.Capture(0,blocked,true),"nested return still inside original writer");
    // Normal nested returns keep the old original invalidated.
    ledger.Exit(outer);Same(ledger,original,AllFields,Match::Superseded,AllFields);
    ledger.Exit(outer);Check(ledger.Status()==Health::Fault,"reused frame faults permanently");
    Check(!ledger.Start(5),"lost observation cannot be reset");
    Ledger order;order.Start(6);outer=order.Enter(Event::Rebuild,0);inner=order.Enter(Event::Rebuild,0);
    order.Exit(outer);Check(order.Status()==Health::Fault,"out-of-order callback exit faults");
    order.Exit(inner);order.Exit(outer);Check(order.ActiveCalls()==0,"faulted valid finally paths can still drain");
    Ledger depth;depth.Start(7);Frame frames[FrameCapacity];
    for(auto& f:frames)f=depth.Enter(Event::Rebuild,0);
    Check(!depth.Enter(Event::Rebuild,0).ticket && depth.Status()==Health::Fault,"nesting overflow loses confidence before writes");
    for(unsigned i=FrameCapacity;i;--i)depth.Exit(frames[i-1]);
    Check(depth.ActiveCalls()==0,"overflow still permits paired exits");
    Ledger failed;failed.Start(8);auto stamp=Capture(failed,0);failed.Fault();
    Same(failed,stamp,AllFields,Match::Unavailable);Check(!failed.Enter(Event::Rebuild,0).ticket,"metadata fault creates no native-call obligation");
}
void InvalidInputsAndExhaustion() {
    Ledger zero;Check(!zero.Start(0) && zero.Status()==Health::Fault,"zero process nonce rejected");
    for(int index : {-1,7,96,INT32_MIN,INT32_MAX}) {
        Ledger l;l.Start(11);auto stamp=Capture(l,0);EventOnce(l,Event::GeneralWrite,0,index);
        Check(l.Status()==Health::Fault,"unbounded native coefficient index faults observation");Same(l,stamp,AllFields,Match::Unavailable);
    }
    for(int count : {0,-1,INT32_MIN}) { Ledger l;l.Start(12);EventOnce(l,Event::Release,0,count);Check(l.Status()==Health::Fault,"malformed pre-release count faults"); }
    for(uint32_t mask : {0u,32u,0xffffffffu}) {Ledger l;l.Start(13);EventOnce(l,Event::ManualWrite,0,0,mask);Check(l.Status()==Health::Fault,"invalid write mask faults");}
    for(unsigned slot : {SlotCount,UINT32_MAX}) {Ledger l;l.Start(14);Check(!l.Enter(Event::Rebuild,slot).ticket && l.Status()==Health::Fault,"invalid slot fails before indexing");}
    Ledger wrong;wrong.Start(15);auto stamp=Capture(wrong,0);auto copy=stamp;
    copy.instance++;Same(wrong,copy,AllFields,Match::Unavailable);
    copy=stamp;copy.poolEpoch=0;Same(wrong,copy,AllFields,Match::Unavailable);
    copy=stamp;copy.allocation=0;Same(wrong,copy,AllFields,Match::Unavailable);
    copy=stamp;copy.slot=SlotCount;Same(wrong,copy,AllFields,Match::Unavailable);
    copy=stamp;copy.fields[Lucky]=0;Same(wrong,copy,AllFields,Match::Unavailable);
    Same(wrong,copy,1u<<Draw,Match::Current);
    Same(wrong,stamp,0,Match::Unavailable);Same(wrong,stamp,32,Match::Unavailable);
    Check(!wrong.Enter(Event::Rebuild,0,0,0,0).ticket && wrong.Status()==Health::Fault,"missing native thread identity invalidates metadata");
    Ledger captureThread;captureThread.Start(16);Stamp no;Check(!captureThread.Capture(0,no,true,false) && captureThread.Status()==Health::Fault,"off-thread acquisition faults");
    for(Event event : {Event::Initialize,Event::Rebuild,Event::GeneralWrite,Event::PoolReset,Event::Release,Event::ManualWrite}) {
        Ledger l;l.Start(17);auto before=Capture(l,0);LedgerTestAccess::Exhaust(l);
        auto f=l.Enter(event,event==Event::PoolReset?SlotCount:0,event==Event::GeneralWrite?6:event==Event::Release?1:0,event==Event::ManualWrite?1:0);
        Check(!f.ticket && l.Status()==Health::Fault,"serial exhaustion never wraps an entry ticket");Same(l,before,AllFields,Match::Unavailable);
    }
    Ledger adoption;adoption.Start(18);LedgerTestAccess::Exhaust(adoption);Check(!adoption.Capture(0,no,true),"adoption token cannot wrap");
    Ledger event;event.Start(19);Check(!event.Enter(static_cast<Event>(100),0).ticket && event.Status()==Health::Fault,"unknown event rejected");
    Ledger reset;reset.Start(20);Check(!reset.Enter(Event::PoolReset,0).ticket && reset.Status()==Health::Fault,"pool reset requires pool sentinel");
}
void WorkerInterleavings() {
    Ledger ledger;ledger.Start(21);auto original=Capture(ledger,0);
    // Worker A's whole-status rebuild overlaps worker B's script write. Their
    // exit order is not a global stack and neither may be called unobserved.
    auto a=ledger.Enter(Event::Rebuild,0,0,0,101);
    auto b=ledger.Enter(Event::GeneralWrite,0,6,0,202);
    auto nested=ledger.Enter(Event::GeneralWrite,0,6,0,101);
    Check(a.ticket && b.ticket && nested.ticket && ledger.ActiveCalls()==3,"two native workers and nesting admitted");
    ledger.Exit(b);Check(ledger.Status()==Health::Observing && ledger.ActiveCalls()==2,"cross-thread early exit accepted");
    Stamp blocked;Check(!ledger.Capture(0,blocked,true),"worker in flight prevents acquisition");
    ledger.Exit(nested);ledger.Exit(a);
    Check(ledger.Status()==Health::Observing && ledger.ActiveCalls()==0,"worker overlap drains completely");
    Same(ledger,original,AllFields,Match::Superseded,AllFields);
    auto now=Capture(ledger,0);
    a=ledger.Enter(Event::ManualWrite,0,0,1u<<Draw,101);
    b=ledger.Enter(Event::GeneralWrite,0,6,0,202);
    ledger.Exit(a);ledger.Exit(b);
    Same(ledger,now,AllFields,Match::Superseded,(1u<<Draw)|(1u<<General));
    a=ledger.Enter(Event::Rebuild,0,0,0,101);auto forged=a;forged.thread=202;ledger.Exit(forged);
    Check(ledger.Status()==Health::Fault && ledger.ActiveCalls()==1,"wrong thread cannot close another callback");
    ledger.Exit(a);Check(ledger.ActiveCalls()==0,"real finally closes faulted callback");
    // Exercise reuse of every bounded frame record after overlapping exits.
    Ledger reuse;reuse.Start(22);Frame active[FrameCapacity];
    for(unsigned i=0;i<FrameCapacity;++i)active[i]=reuse.Enter(Event::Rebuild,i,0,0,1000+i);
    for(unsigned i=0;i<FrameCapacity;i+=2)reuse.Exit(active[i]);
    for(unsigned i=0;i<FrameCapacity;i+=2)active[i]=reuse.Enter(Event::Rebuild,i,0,0,2000+i);
    for(unsigned i=0;i<FrameCapacity;++i)reuse.Exit(active[i]);
    Check(reuse.Status()==Health::Observing && reuse.ActiveCalls()==0,"bounded records reused across interleaved native workers");
}
void OriginalExceptions() {
    for(Event event : {Event::Initialize,Event::Rebuild,Event::GeneralWrite,Event::PoolReset,Event::Release,Event::ManualWrite}) {
        Ledger ledger;ledger.Start(23);auto before=Capture(ledger,0);
        const auto frame=ledger.Enter(event,event==Event::PoolReset?SlotCount:0,
            event==Event::GeneralWrite?6:event==Event::Release?1:0,event==Event::ManualWrite?1:0);
        Check(frame.ticket!=0,"original-exception fixture entered");
        // The native body can throw before or after any writes, including before
        // a release actually decrements its refcount. Never call this destroyed.
        ledger.Exit(frame,false);
        Check(ledger.Status()==Health::Fault && ledger.ActiveCalls()==0,"abnormal native return faults and drains metadata");
        Same(ledger,before,AllFields,Match::Unavailable);
    }
}
int main() {
    BootstrapAndNativeWrites();IndependentFieldsAndSlots();PoolEpochAndRetirement();ReentrancyAndFailure();InvalidInputsAndExhaustion();WorkerInterleavings();OriginalExceptions();
    printf("%u checks, %u failures\n",checks,failures);return failures?1:0;
}
