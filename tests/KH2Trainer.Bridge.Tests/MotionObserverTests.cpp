#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "../../src/KH2Trainer.Bridge/MotionObserverSupport.h"
#include <stdio.h>
#include <string.h>
#include <limits.h>
#include <type_traits>
#include <initializer_list>

using namespace motion_observer;
static unsigned checks=0,failures=0;
static void Check(bool value,const char* label) {
    ++checks;if(!value){++failures;printf("FAIL: %s\n",label);}
}
static uint32_t Bits(float value) { uint32_t bits=0;memcpy(&bits,&value,4);return bits; }
static float Float(uint32_t bits) { float value=0;memcpy(&value,&bits,4);return value; }
constexpr DWORD NativeException=0xe0424d10,BeforeException=0xe0424d11,
    AfterException=0xe0424d12,SecondaryNativeException=0xe0424d13;
constexpr DWORD Incoming=0x1234abcd,Outgoing=0xabcd4321,BeforeNoise=0x10101010,AfterNoise=0x20202020;
enum class Nested { None,Before,Original,After };
struct Fixture;
struct Scenario {
    Fixture* fixture=nullptr;
    Scenario* child=nullptr;
    Nested nested=Nested::None;
    uintptr_t controller=0xabcdef0123456780ull;
    int32_t selection=-1;
    uint32_t blend=0x80000000,frame=0x7fc12345;
    uint64_t ticket=0xfedcba9876543210ull;
    uint8_t result=1;
    int tag=1;
    unsigned beforeCalls=0,originalCalls=0,afterCalls=0;
    bool beforeRaises=false,originalRaises=false,afterRaises=false,expectNormal=true;
    bool expectBeforeCompleted=true;
    unsigned expectedOriginalCalls=1;
    DWORD incoming=Incoming,outgoing=Outgoing;
    DWORD expectedAfterError=Outgoing,nativeException=NativeException;
};
struct Event { char kind;int tag; };
struct Fixture {
    Observer* observer;
    OriginalFn entry;
    Event events[32]{};
    unsigned eventCount=0;
    void Log(char kind,int tag) {
        if(eventCount<32)events[eventCount++]={kind,tag};else Check(false,"event log capacity");
    }
};
static thread_local Scenario* active=nullptr;
static uint8_t Invoke(Fixture& f,Scenario& s) {
    Scenario* previous=active;active=&s;s.fixture=&f;
    SetLastError(s.incoming);
    // Restore the outer scenario even when a nested original raises SEH.
    __try { return f.entry(s.controller,s.selection,Float(s.blend),Float(s.frame)); }
    __finally { active=previous; }
}
static void NestedCall(Scenario& s,Nested stage) {
    if(s.nested!=stage)return;
    Check(s.child!=nullptr,"nested scenario exists");
    if(!s.child)return;
    const uint8_t result=Invoke(*s.fixture,*s.child);
    Check(result==s.child->result,"nested AL result preserved");
    Check(GetLastError()==s.child->outgoing,"nested LastError preserved");
    Check(active==&s,"nested return restores outer invocation");
}
static uint64_t __fastcall Before(void* context,uintptr_t controller) {
    Scenario& s=*active;auto& f=*static_cast<Fixture*>(context);
    Check(&f==s.fixture,"Before receives immutable context");
    Check(controller==s.controller,"Before receives exact controller");
    Check(GetLastError()==s.incoming,"Before receives incoming LastError");
    ++s.beforeCalls;f.Log('B',s.tag);
    NestedCall(s,Nested::Before);
    SetLastError(BeforeNoise);
    if(s.beforeRaises)RaiseException(BeforeException,0,0,nullptr);
    return s.ticket;
}
static __declspec(noinline) uint8_t __fastcall Original(uintptr_t controller,int32_t selection,float blend,float frame) {
    Scenario& s=*active;auto& f=*s.fixture;
    Check(s.beforeCalls==1,"synchronous Before precedes original exactly once");
    Check(s.afterCalls==0,"After has not run before original");
    Check(GetLastError()==s.incoming,"original LastError excludes Before side effects");
    Check(controller==s.controller,"RCX controller bits preserved");
    Check(selection==s.selection,"signed EDX selection preserved");
    Check(Bits(blend)==s.blend,"XMM2 float payload preserved bit for bit");
    Check(Bits(frame)==s.frame,"XMM3 float payload preserved bit for bit");
    ++s.originalCalls;f.Log('O',s.tag);
    NestedCall(s,Nested::Original);
    SetLastError(s.outgoing);
    if(s.originalRaises)RaiseException(s.nativeException,0,0,nullptr);
    return s.result;
}
static void __fastcall After(void* context,uintptr_t controller,uint64_t ticket,bool beforeCompleted,bool normalReturn) {
    Scenario& s=*active;auto& f=*static_cast<Fixture*>(context);
    Check(&f==s.fixture && controller==s.controller,"After receives invocation context");
    Check(s.originalCalls==s.expectedOriginalCalls,"After sees precise original invocation count");
    Check(beforeCompleted==s.expectBeforeCompleted,"Before completion flag is precise");
    Check(ticket==(s.expectBeforeCompleted?s.ticket:0),"local ticket survives nesting or Before fault");
    Check(normalReturn==s.expectNormal,"original normal-return flag is precise");
    Check(GetLastError()==s.expectedAfterError,"After receives completed or failing operation LastError");
    ++s.afterCalls;f.Log('A',s.tag);
    NestedCall(s,Nested::After);
    SetLastError(AfterNoise);
    if(s.afterRaises)RaiseException(AfterException,0,0,nullptr);
}

Observer BasicObserver,NativeFaultObserver,BeforeFaultObserver,AfterFaultObserver,
    DoubleFaultObserver,BeforeDoubleFaultObserver,NestedFaultObserver,
    NestedBeforeFaultObserver,NestedAfterFaultObserver,NestedSecondaryFaultObserver,UnboundObserver;
using BasicEntry=Entrypoints<BasicObserver>;
static_assert(std::is_same_v<decltype(&BasicEntry::Select),OriginalFn>,"Actual entry retains mixed Win64 ABI");
static void Bind(Fixture& f) {
    Check(!f.observer->Bound() && !f.observer->Faulted(),"new support unbound and healthy");
    Check(!f.observer->Bind(nullptr,Before,After,&f),"null original rejected before publication");
    Check(!f.observer->Bind(Original,nullptr,After,&f),"missing Before rejected");
    Check(!f.observer->Bind(Original,Before,nullptr,&f),"missing After rejected");
    Check(f.observer->Bind(Original,Before,After,&f),"valid immutable binding");
    Check(f.observer->Bound(),"binding published");
    Check(!f.observer->Bind(Original,Before,After,nullptr),"rebind cannot replace retained context");
}
static void Once(Fixture& f,Scenario& s) {
    const uint8_t result=Invoke(f,s);
    const DWORD last=GetLastError();
    Check(result==s.result,"all returned AL bits preserved");
    Check(last==s.outgoing,"native LastError survives After side effects");
    Check(s.beforeCalls==1 && s.originalCalls==1 && s.afterCalls==1,"one Before/original/After per invocation");
    Check(active==nullptr,"outer invocation restored TLS");
}
static void Order(const Fixture& f,const char* kinds,const int* tags,unsigned count) {
    Check(f.eventCount==count,"exact synchronous event count");
    for(unsigned i=0;i<count && i<f.eventCount;++i)
        Check(f.events[i].kind==kinds[i] && f.events[i].tag==tags[i],"nested event order");
}
static DWORD Catch(Fixture& f,Scenario& s) {
    __try { Invoke(f,s); }
    __except(EXCEPTION_EXECUTE_HANDLER) { return GetExceptionCode(); }
    return 0;
}
static void PayloadsAndReentrancy() {
    static Fixture f{&BasicObserver,&BasicEntry::Select};Bind(f);
    struct Input { uint32_t blend,frame;int32_t selection;uint8_t result; };
    // Distinct registers, both zero signs, subnormals, finite extremes, infinities
    // and NaN payloads. No float arithmetic or integer-to-float casts in this test.
    const Input inputs[]={
        {0x00000000,0x80000000,0,0}, {0x80000000,0x00000000,-1,1},
        {0x00000001,0x807fffff,INT_MIN,0}, {0x7f7fffff,0xff7fffff,INT_MAX,1},
        {0x7f800000,0xff800000,42,0}, {0x7fc12345,0xffc54321,-32768,1},
        {0x7f812345,0xff812346,65535,0x80}, {0x3f123456,0xc1234567,-2,0xff}
    };
    for(const auto& input:inputs) {
        Scenario s{};s.blend=input.blend;s.frame=input.frame;s.selection=input.selection;s.result=input.result;
        s.ticket=input.selection==0?0:s.ticket;f.eventCount=0;Once(f,s);
        const int tags[]={1,1,1};Order(f,"BOA",tags,3);
        Check(!f.observer->Faulted(),"bit patterns alone do not fault forwarding");
    }
    for(Nested stage:{Nested::Before,Nested::Original,Nested::After}) {
        Scenario outer{},child{};child.tag=2;child.controller=0x123456789abcdef0ull;
        child.ticket=0x0102030405060708ull;child.blend=0xffcabcde;child.frame=0x00000001;
        child.selection=INT_MIN;child.result=0;outer.nested=stage;outer.child=&child;
        f.eventCount=0;Once(f,outer);
        Check(child.beforeCalls==1 && child.originalCalls==1 && child.afterCalls==1,"nested call has independent completion");
        if(stage==Nested::Before) { const int tags[]={1,2,2,2,1,1};Order(f,"BBOAOA",tags,6); }
        if(stage==Nested::Original) { const int tags[]={1,1,2,2,2,1};Order(f,"BOBOAA",tags,6); }
        if(stage==Nested::After) { const int tags[]={1,1,1,2,2,2};Order(f,"BOABOA",tags,6); }
        Check(!f.observer->Faulted(),"nested callbacks need no lock held across original");
    }
}
static void FaultsAndExceptions() {
    static Fixture before{&BeforeFaultObserver,&Entrypoints<BeforeFaultObserver>::Select};Bind(before);
    Scenario b{};b.beforeRaises=true;b.expectBeforeCompleted=false;b.expectNormal=false;
    b.expectedOriginalCalls=0;b.expectedAfterError=BeforeNoise;
    Check(Catch(before,b)==BeforeException,"Before SEH propagates without inventing native success");
    Check(GetLastError()==BeforeNoise,"Before failure LastError survives successful After");
    Check(b.beforeCalls==1 && b.originalCalls==0 && b.afterCalls==1,"failed Before skips original and runs one After");
    Check(before.observer->Faulted() && active==nullptr,"Before SEH faults and unwinds invocation");
    Scenario next{};Once(before,next);
    Check(before.observer->Faulted(),"later forwarding cannot silently clear sticky fault");

    static Fixture after{&AfterFaultObserver,&Entrypoints<AfterFaultObserver>::Select};Bind(after);
    Scenario a{};a.afterRaises=true;
    Check(Catch(after,a)==AfterException,"After SEH propagates following normal original return");
    Check(GetLastError()==AfterNoise,"propagated After failure retains its LastError");
    Check(a.beforeCalls==1 && a.originalCalls==1 && a.afterCalls==1,"After failure does not rerun After or original");
    Check(after.observer->Faulted() && active==nullptr,"After SEH faults and unwinds invocation");

    static Fixture native{&NativeFaultObserver,&Entrypoints<NativeFaultObserver>::Select};Bind(native);
    Scenario n{};n.originalRaises=true;n.expectNormal=false;
    Check(Catch(native,n)==NativeException,"original SEH propagates unchanged");
    Check(GetLastError()==Outgoing,"original SEH preserves LastError through After");
    Check(n.beforeCalls==1 && n.originalCalls==1 && n.afterCalls==1,"original exception still runs one After");
    Check(native.observer->Faulted() && active==nullptr,"abnormal return faults observer and unwinds invocation");

    static Fixture both{&DoubleFaultObserver,&Entrypoints<DoubleFaultObserver>::Select};Bind(both);
    Scenario d{};d.originalRaises=true;d.afterRaises=true;d.expectNormal=false;
    Check(Catch(both,d)==NativeException,"faulting After does not replace pending original SEH");
    Check(GetLastError()==Outgoing && d.afterCalls==1 && both.observer->Faulted(),"combined fault keeps native LastError and one After");

    static Fixture beforeBoth{&BeforeDoubleFaultObserver,&Entrypoints<BeforeDoubleFaultObserver>::Select};Bind(beforeBoth);
    Scenario bd{};bd.beforeRaises=true;bd.afterRaises=true;bd.expectBeforeCompleted=false;bd.expectNormal=false;
    bd.expectedOriginalCalls=0;bd.expectedAfterError=BeforeNoise;
    Check(Catch(beforeBoth,bd)==BeforeException,"secondary After SEH does not replace primary Before SEH");
    Check(GetLastError()==BeforeNoise,"secondary After failure cannot overwrite primary Before LastError");
    Check(bd.beforeCalls==1 && bd.originalCalls==0 && bd.afterCalls==1,"Before plus After failure skips original and finishes After once");
    Check(beforeBoth.observer->Faulted() && active==nullptr,"Before plus After failure restores invocation and latches fault");

    static Fixture nested{&NestedFaultObserver,&Entrypoints<NestedFaultObserver>::Select};Bind(nested);
    Scenario outer{},child{};outer.nested=Nested::Original;outer.child=&child;outer.expectNormal=false;
    child.tag=2;child.ticket=7;child.originalRaises=true;child.expectNormal=false;
    Check(Catch(nested,outer)==NativeException,"nested original SEH crosses both wrappers unchanged");
    Check(GetLastError()==Outgoing && active==nullptr,"nested exceptional finally restores outer invocation and error");
    Check(outer.afterCalls==1 && child.afterCalls==1 && nested.observer->Faulted(),"both exception frames complete independently");
    const int tags[]={1,1,2,2,2,1};Order(nested,"BOBOAA",tags,6);

    Fixture unbound{&UnboundObserver,&Entrypoints<UnboundObserver>::Select};Scenario u{};
    Check(Catch(unbound,u)==UnboundCallException,"unbound entry is an explicit installer error");
    Check(u.beforeCalls==0 && u.originalCalls==0 && u.afterCalls==0 && UnboundObserver.Faulted(),"unbound entry invents no native success");
}
static void CallbackNestedNativeExceptions() {
    // The old catch-all around callbacks swallowed both of these native faults.
    // No callback-origin classifier is involved: only an already pending primary
    // exception permits suppression of a secondary After failure.
    static Fixture before{&NestedBeforeFaultObserver,&Entrypoints<NestedBeforeFaultObserver>::Select};Bind(before);
    Scenario b{},bc{};b.nested=Nested::Before;b.child=&bc;
    b.expectBeforeCompleted=false;b.expectNormal=false;b.expectedOriginalCalls=0;
    bc.tag=2;bc.originalRaises=true;bc.expectNormal=false;bc.outgoing=0x30303030;
    b.expectedAfterError=bc.expectedAfterError=bc.outgoing;
    Check(Catch(before,b)==NativeException,"native SEH from Before reentry propagates to caller");
    Check(GetLastError()==bc.outgoing && active==nullptr,"Before reentry preserves native failure LastError and restores invocation");
    Check(b.beforeCalls==1 && b.originalCalls==0 && b.afterCalls==1,"Before reentry failure prevents outer original and runs outer After once");
    Check(bc.beforeCalls==1 && bc.originalCalls==1 && bc.afterCalls==1 && before.observer->Faulted(),"Before child failure finishes once and latches fault");
    const int beforeTags[]={1,2,2,2,1};Order(before,"BBOAA",beforeTags,5);

    static Fixture after{&NestedAfterFaultObserver,&Entrypoints<NestedAfterFaultObserver>::Select};Bind(after);
    Scenario a{},ac{};a.nested=Nested::After;a.child=&ac;
    ac.tag=2;ac.originalRaises=true;ac.expectNormal=false;ac.outgoing=0x40404040;ac.expectedAfterError=ac.outgoing;
    Check(Catch(after,a)==NativeException,"native SEH from normal After reentry propagates to caller");
    Check(GetLastError()==ac.outgoing && active==nullptr,"After reentry preserves native failure LastError and restores invocation");
    Check(a.beforeCalls==1 && a.originalCalls==1 && a.afterCalls==1,"normal outer return then After failure does not rerun callbacks");
    Check(ac.beforeCalls==1 && ac.originalCalls==1 && ac.afterCalls==1 && after.observer->Faulted(),"After child failure finishes once and latches fault");
    const int afterTags[]={1,1,1,2,2,2};Order(after,"BOABOA",afterTags,6);

    static Fixture secondary{&NestedSecondaryFaultObserver,&Entrypoints<NestedSecondaryFaultObserver>::Select};Bind(secondary);
    Scenario p{},sc{};p.originalRaises=true;p.expectNormal=false;p.nested=Nested::After;p.child=&sc;
    sc.tag=2;sc.originalRaises=true;sc.expectNormal=false;sc.nativeException=SecondaryNativeException;
    sc.outgoing=0x50505050;sc.expectedAfterError=sc.outgoing;
    Check(Catch(secondary,p)==NativeException,"secondary nested-native After SEH cannot replace distinct primary original SEH");
    Check(GetLastError()==p.outgoing && active==nullptr,"secondary nested-native fault cannot overwrite primary LastError");
    Check(p.beforeCalls==1 && p.originalCalls==1 && p.afterCalls==1,"primary exception completes outer callbacks once");
    Check(sc.beforeCalls==1 && sc.originalCalls==1 && sc.afterCalls==1 && secondary.observer->Faulted(),"secondary exception completes nested callbacks once");
    Order(secondary,"BOABOA",afterTags,6);
}
int main() {
    PayloadsAndReentrancy();FaultsAndExceptions();CallbackNestedNativeExceptions();
    printf("Motion observer tests: %u checks, %u failures\n",checks,failures);
    return failures?1:0;
}
