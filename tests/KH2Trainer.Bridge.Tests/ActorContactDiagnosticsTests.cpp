#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstdint>
namespace {
uintptr_t countedTail=0;
unsigned tailQueries=0;
SIZE_T WINAPI CountedQuery(LPCVOID p,PMEMORY_BASIC_INFORMATION m,SIZE_T n) {
    if(reinterpret_cast<uintptr_t>(p)==countedTail)++tailQueries;
    return ::VirtualQuery(p,m,n);
}
}
#define VirtualQuery CountedQuery
#define KH2DEV_PAYLOAD_TESTS
#include "../../src/KH2Trainer.Bridge/TrainerBridge.cpp"
#undef VirtualQuery
#include <cstdio>
#include <vector>

namespace {
constexpr uintptr_t Actor=0x110000,Enemy=0x114000,EnemyStatus=0x118000;
constexpr uintptr_t ObjectTable=0x120000,Pad=0x124000,Pool=0x2A17290;
unsigned checks=0,failures=0;
SharedState state{};
void Check(bool ok,const char* name) { ++checks;if(!ok){++failures;std::printf("FAIL: %s\n",name);} }
uint32_t Packed(uintptr_t p) {
    if(!p)return 0;
    const uintptr_t high=p&~uintptr_t(0x1ffffff);
    for(unsigned i=1;i<64;++i) {
        auto& base=At<uintptr_t>(0x2B0D720+i*8);
        if(!base||base==high){base=high;return 0x80000000u|(i<<25)|static_cast<uint32_t>(p&0x1ffffff);}
    }
    abort();
}
TrainerContext Context() {return {g_base,g_base+Actor,g_base+Pool,true};}
bool Valid(unsigned slot) {return (state.validValues[slot/64]&(uint64_t(1)<<(slot%64)))!=0;}
bool Supported(unsigned slot) {return (state.supportedCapabilities[slot/64]&(uint64_t(1)<<(slot%64)))!=0;}
void Refresh(const TrainerContext& c) {
    // TrainerFrame clears every publication, so absent samples cannot reuse an old value.
    ZeroMemory(state.validValues,sizeof(state.validValues));ZeroMemory(state.values,sizeof(state.values));
    GameplayStateSnapshot(c);CombatSnapshot(c);
}
void Refresh() {Refresh(Context());}
bool Three(unsigned first) {return Valid(first)&&Valid(first+1)&&Valid(first+2);}
bool None(unsigned first) {return !Valid(first)&&!Valid(first+1)&&!Valid(first+2);}
void Role(unsigned character,int form) {
    At<uint16_t>(ObjectTable+8+76)=static_cast<uint16_t>(character);
    At<signed char>(ObjectTable+8+87)=static_cast<signed char>(form);
    At<unsigned>(Pool+608)=character;At<int>(Actor+3552)=form;
    At<uint32_t>(Actor)=Packed(g_base+(character==4?0x7523B8:0x750300));
    At<unsigned>(Actor+1736)=character==4?0x2000080:0x1000080;
}
void Setup() {
    DWORD old=0;VirtualProtect(reinterpret_cast<void*>(g_base),kImageSize,PAGE_READWRITE,&old);
    memset(reinterpret_cast<void*>(g_base),0,kImageSize);ZeroMemory(&state,sizeof(state));
    g_shared=&state;g_gameThread=GetCurrentThreadId();g_disabled=0;g_hostExpired=false;
    state.hostHeartbeat=GetTickCount();
    for(const auto& p:gameplay_state::pins)memcpy(reinterpret_cast<void*>(g_base+p.rva),p.bytes,p.size);
    At<uintptr_t>(0x750300)=g_base+0x5CBA28;At<uintptr_t>(0x7523B8)=g_base+0x5D15A0;
    At<uintptr_t>(0x5CBA28+120)=g_base+0x404C50;At<uintptr_t>(0x5D15A0+120)=g_base+0x415280;
    At<uintptr_t>(0x5CBA28+24)=g_base+0x404A30;At<uintptr_t>(0x5D15A0+24)=g_base+0x4150D0;
    At<uintptr_t>(0x2A10620)=g_base+0x5C4C68;
    At<uintptr_t>(0x5C4C68+16)=g_base+0x3F29E0;At<uintptr_t>(0x5C4C68+24)=g_base+0x3F2470;
    At<uintptr_t>(0x2A105D0)=g_base+Actor;At<uintptr_t>(0x2A171C8)=g_base+Actor;
    At<uintptr_t>(0x2A25030)=g_base+ObjectTable;At<int>(ObjectTable+4)=1;
    At<uint32_t>(Actor+8)=Packed(g_base+ObjectTable+8);At<uintptr_t>(Actor+1472)=g_base+Pool;
    At<uint32_t>(Pool+616)=Packed(g_base+Actor);At<int>(Pool+612)=1;
    At<int>(Pool)=100;At<int>(Pool+4)=255;
    At<int>(0x2A23950)=79;for(int i=0;i<79;++i)At<int>(0x2A23810+4*i)=i+1;
    At<unsigned>(Actor+2488)=0x80;At<uintptr_t>(Actor+3512)=g_base+Pad;
    At<uintptr_t>(Actor+3520)=g_base+0x2A10620;At<uintptr_t>(Actor+3536)=g_base+0x2A10620;
    At<uintptr_t>(0x2A10620+2784)=g_base+Actor;At<uintptr_t>(0x2A10620+3128)=g_base+Actor;
    At<uintptr_t>(0x2A10620+2792)=g_base+Pad;
    At<BYTE>(0x9BA8D0)=1;At<int>(0x716884)=1;
    At<uintptr_t>(0x716868)=g_base+0x130000;At<uintptr_t>(0x9BA888)=g_base+0x130000;
    At<uintptr_t>(0x9BA920)=g_base+0x132000;
    Role(1,0);
    At<uintptr_t>(Actor+3528)=g_base+combat::LockRva;At<uintptr_t>(combat::LockRva+56)=g_base+Actor;
    At<int>(combat::LockRva)=2;At<uint32_t>(combat::LockRva+4)=Packed(g_base+Enemy);
    At<uint32_t>(Actor+2704)=Packed(g_base+Enemy);At<uint32_t>(Enemy+1736)=0x12;
    At<uintptr_t>(Enemy+1472)=g_base+EnemyStatus;At<uint32_t>(EnemyStatus+616)=Packed(g_base+Enemy);
    At<int>(EnemyStatus)=80;At<int>(EnemyStatus+4)=500;
    At<float>(Enemy+3400)=17;At<float>(Enemy+3404)=100;
    At<uint32_t>(Actor+1464)=2;At<uint32_t>(Enemy+1464)=7;
}
void RejectTargetActions() {
    const int hp=At<int>(EnemyStatus);const float revenge=At<float>(Enemy+3400);
    for(unsigned slot:{102u,103u,104u,110u,486u}) {
        const double args[8]{25};TrainerResult result{};
        Check(CombatHandle(Context(),slot,args,result)&&result.code!=0,"retirement diagnostic never admits target mutation");
    }
    Check(At<int>(EnemyStatus)==hp && At<float>(Enemy+3400)==revenge,"rejected mutations preserve target HP and revenge");
}
void ValuesAndFlags() {
    Setup();GameplayStateCapabilities();CombatCapabilities();
    for(unsigned slot=493;slot<=498;++slot)Check(Supported(slot),"six readout capabilities exposed");
    Check(!Supported(499),"unassigned adjacent capability stays unavailable");
    Refresh();Check(Three(493)&&Three(496)&&state.values[493]==2&&state.values[496]==7,"current Sora and target counters are independent");
    Check(Valid(98)&&state.values[98]==80&&Valid(100)&&state.values[100]==17,"existing living-target HP and revenge readouts remain unchanged");
    for(uint32_t counter:{0u,1u,2u,0x7fffffffu,0x80000000u,0xffffffffu}) {
        At<uint32_t>(Actor+1464)=counter;At<uint32_t>(Enemy+1464)=counter;Refresh();
        Check(Three(493)&&Three(496)&&state.values[493]==static_cast<double>(counter)&&state.values[496]==static_cast<double>(counter),
            "zero and full unsigned DWORD values remain exact, without signed clamp or attack-count conversion");
    }
    for(uint32_t bits:{0u,0x10000000u,0x80000u,0x10080000u}) {
        Setup();At<uint32_t>(Actor+288)=bits;Refresh();
        Check(Three(493)&&state.values[494]==((bits&0x10000000)?1:0)&&state.values[495]==((bits&0x80000)?1:0),
            "Sora retirement request and dead-list mark are independently observable even when input is blocked");
        Setup();At<uint32_t>(Enemy+288)=bits;Refresh();
        Check(Three(496)&&state.values[497]==((bits&0x10000000)?1:0)&&state.values[498]==((bits&0x80000)?1:0),
            "target retirement flags are raw independent observations on a still-listed Actor");
        if(bits){Check(!Valid(98)&&!Valid(100),"retiring target does not become a living HP/revenge observation");RejectTargetActions();}
    }
    Setup();At<int>(EnemyStatus)=0;Refresh();Check(Three(496)&&!Valid(98),"zero-HP listed target remains diagnostic-only");RejectTargetActions();
    Setup();At<unsigned>(Enemy+2488)=4;Refresh();Check(Three(496)&&!Valid(98),"action-disabled listed target remains diagnostic-only");RejectTargetActions();
    Setup();At<int>(Pool)=0;Refresh();Check(Three(493),"zero-HP coherent Sora retains raw retirement diagnostics");
    for(unsigned form=0;form<=6;++form){Setup();Role(1,static_cast<int>(form));Refresh();Check(Three(493),"all verified Sora forms share the base counter readout");}
    for(unsigned role:{4u,14u}){Setup();Role(role,role==4?11:0);Refresh();Check(None(493),"Mickey and Roxas are not mislabeled Sora");}
}
void UnavailableAndBindings() {
    Setup();Refresh();Check(Three(493)&&Three(496),"unavailable-clearing test starts with valid previous data");
    At<uintptr_t>(0x2A105D0)=0;Refresh();Check(None(493)&&None(496)&&state.values[493]==0&&state.values[496]==0,"new publication clears unavailable observations instead of retaining the previous actor");
    Setup();At<uintptr_t>(0x2A171C8)=0;Refresh();Check(None(493)&&None(496),"removed actors are never followed through retained pointers");
    Setup();At<uint32_t>(Enemy+2704)=Packed(g_base+Enemy);Refresh();Check(None(493)&&None(496),"cycle after matching actor invalidates the complete live-list observation");
    Setup();At<uint32_t>(Actor+2704)=0;Refresh();Check(Three(493)&&None(496),"target binding alone cannot replace active-list membership");
    for(uintptr_t offset:{combat::LockRva+56,Actor+3528}){Setup();At<uintptr_t>(offset)=0;Refresh();Check(None(496),"both current lock-on owner bindings are required");}
    for(int mode:{0,3,4,-1}){Setup();At<int>(combat::LockRva)=mode;Refresh();Check(None(496),"inactive and invalid lock modes have no target observation");}
    Setup();At<int>(combat::LockRva)=1;Refresh();Check(Three(496),"native auto-target mode is observable");RejectTargetActions();
    Setup();At<uint32_t>(combat::LockRva+12)=1;Refresh();Check(None(496),"invalid lock target state is unavailable");
    Setup();At<uint32_t>(combat::LockRva+4)=Packed(g_base+Actor);Refresh();Check(None(496),"current player is not an enemy target");
    Setup();At<uint32_t>(EnemyStatus+616)=Packed(g_base+Actor);Refresh();Check(None(496),"target status must refer back to the same Actor");
    for(uintptr_t offset:{EnemyStatus+592,EnemyStatus+620}){Setup();At<uint32_t>(offset)=1;Refresh();Check(None(496),"save-backed character status is not an enemy diagnostic");}
    for(unsigned flags:{0u,2u,0x10u}){Setup();At<unsigned>(Enemy+1736)=flags;Refresh();Check(None(496),"enemy category bits remain mandatory");}
    struct Invalid{uintptr_t offset;int value;};
    for(auto bad:std::initializer_list<Invalid>{{EnemyStatus,-1},{EnemyStatus,501},{EnemyStatus+4,0},{EnemyStatus+4,1000001},{EnemyStatus+8,-1},{EnemyStatus+8,501}}) {
        Setup();At<int>(bad.offset)=bad.value;Refresh();Check(None(496),"inconsistent enemy health ranges suppress raw diagnostics too");
    }
    Setup();At<uintptr_t>(Enemy+1472)=UINTPTR_MAX-16;Refresh();Check(None(496),"unreadable target status is rejected before access");
    Setup();At<uint32_t>(combat::LockRva+4)=Packed(g_base+0x180000);Refresh();Check(None(496),"different target address needs its own complete fresh validation");
    Setup();At<uint32_t>(Actor+8)=0;Refresh();Check(None(493),"Sora requires the verified object and descriptor identity");
    Setup();At<int>(0x2A23950)=80;At<int>(0x2A23810+79*4)=0;Refresh();Check(None(493),"released player status slot suppresses Sora diagnostics");
}
void PhaseAndReadOnly() {
    Setup();Refresh({g_base,g_base+Actor,g_base+Pool,false});Check(None(493)&&None(496),"absent scene publishes no actor diagnostics");
    for(uintptr_t offset:{0x9BA928u,0x2AE9FA8u}) {
        Setup();At<uintptr_t>(offset)=1;Refresh();
        Check(None(493),"Sora transition is unavailable");
        if(offset==0x9BA928)Check(None(496),"existing target phase gate excludes field transition");
    }
    Setup();At<BYTE>(0x9BA8D1)=1;Refresh();Check(None(493)&&None(496),"closing scene publishes no actor diagnostics");
    Setup();g_disabled=1;Refresh();Check(None(493)&&None(496),"disabled bridge publishes no new contact values");
    Setup();g_gameThread=0;Refresh();Check(None(493)&&None(496),"non-game-thread caller cannot publish actor diagnostics");
    Setup();state.hostHeartbeat=GetTickCount()-6001;Refresh();Check(None(493)&&None(496),"stale host suppresses actor diagnostics");
    Setup();Refresh({g_base+1,g_base+Actor,g_base+Pool,true});Check(None(493)&&None(496),"wrong module context suppresses actor diagnostics");
    Setup();At<int>(0x716884)=2;Refresh();Check(Three(493)&&Three(496),"read-only observations remain useful while field is paused");
    Setup();At<BYTE>(0x9006B0)=1;Refresh();Check(Three(493)&&None(496),"Sora raw flags remain visible in menu; target keeps its existing phase gate");
    Setup();At<uintptr_t>(Actor+1456)=UINTPTR_MAX;At<uintptr_t>(Enemy+1456)=UINTPTR_MAX;
    At<uint32_t>(Actor+1464)=At<uint32_t>(Enemy+1464)=0;
    const std::vector<BYTE> before(reinterpret_cast<BYTE*>(g_base),reinterpret_cast<BYTE*>(g_base+kImageSize));
    DWORD old=0;Check(VirtualProtect(reinterpret_cast<void*>(g_base),kImageSize,PAGE_READONLY,&old)!=FALSE,"fixture image is read-only and non-executable");
    Refresh();
    Check(Three(493)&&Three(496),"zero counters do not call native predicates or dereference the poisoned VM pointers");
    Check(!memcmp(before.data(),reinterpret_cast<void*>(g_base),kImageSize),"all game image bytes remain unchanged after contact observations");
    Check(actor_lifetime::observerStatus==actor_lifetime::Uninstalled,"readouts install no actor lifetime hooks");
    VirtualProtect(reinterpret_cast<void*>(g_base),kImageSize,PAGE_READWRITE,&old);
}
void TraversalBudget() {
    Setup();constexpr uintptr_t Tail=0x11C000;
    At<uint32_t>(Enemy+2704)=Packed(g_base+Tail);
    countedTail=g_base+Tail;tailQueries=0;
    CombatSnapshot(Context());
    Check(Three(496)&&tailQueries==1,"CombatSnapshot reuses exactly one complete live-list traversal for old and new target readouts");
    tailQueries=0;GameplayStateSnapshot(Context());
    Check(Three(493)&&tailQueries==1,"Sora contact readouts reuse the existing gameplay identity traversal without another list scan");
    tailQueries=0;Refresh();
    Check(Three(493)&&Three(496)&&tailQueries==2,"combined publication adds no target or player live-list traversal");
    countedTail=0;
}
}
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,kImageSize,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(!g_base)return 2;
    ValuesAndFlags();UnavailableAndBindings();PhaseAndReadOnly();TraversalBudget();
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);g_base=0;g_shared=nullptr;
    std::printf("%u checks, %u failures\n",checks,failures);
    return failures?1:0;
}
