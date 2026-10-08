#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include <initializer_list>
namespace {
struct TrainerContext { uintptr_t base,player,status; bool sceneReady; };
struct Shared { DWORD hostHeartbeat; double values[512]; uint64_t valid[8],supported[8]; } shared{};
uintptr_t g_base=0;Shared* g_shared=&shared;DWORD g_gameThread=0;LONG g_disabled=0;
constexpr SIZE_T ImageSize=0x2C30000;
constexpr uintptr_t Actor=0x110000,Status=0x112000,Pad=0x114000,Window=0x116000,Mission=0x117000;
DWORD fakeNow=100000;
DWORD Now() { return fakeNow; }
template<class T>T& At(uintptr_t rva) { return *reinterpret_cast<T*>(g_base+rva); }
uintptr_t denied=0;SIZE_T deniedSize=0;bool fault=false;
bool Readable(const void* p,SIZE_T n) {
    if(fault) RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr);
    const auto a=reinterpret_cast<uintptr_t>(p);
    return a>=g_base && n<=ImageSize && a-g_base<=ImageSize-n &&
        (!denied || a+n<=denied || a>=denied+deniedSize);
}
void SnapshotValue(unsigned slot,double v) { shared.values[slot]=v;shared.valid[slot/64]|=uint64_t(1)<<(slot%64); }
void SupportCapability(unsigned slot) { shared.supported[slot/64]|=uint64_t(1)<<(slot%64); }
namespace player_role {
enum class Role { Unknown=0,Sora=1,Roxas=2,Mickey=3,Other=4 };
struct Info { Role role=Role::Sora;unsigned characterId=1;int form=0;uintptr_t descriptor=0,object=0; };
Info next{};
Info Inspect(const TrainerContext&) { return next; }
}
namespace world_features {
enum class PausePhase {Off,Requested,Held,Step};
PausePhase pausePhase=PausePhase::Off;
bool pauseGlobalsOwned=false,actorFreezeOwned=false;
bool samePause=true,sameFreeze=true;
constexpr unsigned pauseTimerMask=0x40000000u;
bool SamePauseScene() {return samePause;}
bool SameFreezeScene() {return sameFreeze;}
}
#define GetTickCount Now
#include "../../src/KH2Trainer.Bridge/GameplayStateSupport.inl"
#undef GetTickCount
unsigned checks=0,failed=0;
void Check(bool ok,const char* name) {++checks;if(!ok){++failed;std::printf("FAIL: %s\n",name);}}
TrainerContext Context() {return {g_base,g_base+Actor,g_base+Status,true};}
void Reset() {
    memset(reinterpret_cast<void*>(g_base),0,ImageSize);
    shared={};g_shared=&shared;g_gameThread=GetCurrentThreadId();g_disabled=0;
    fakeNow=100000;shared.hostHeartbeat=fakeNow;denied=0;deniedSize=0;fault=false;
    player_role::next={};
    world_features::pausePhase=world_features::PausePhase::Off;world_features::pauseGlobalsOwned=false;
    world_features::actorFreezeOwned=false;world_features::samePause=true;world_features::sameFreeze=true;
    for(const auto& p:gameplay_state::pins) memcpy(reinterpret_cast<void*>(g_base+p.rva),p.bytes,p.size);
    At<uintptr_t>(0x5CBA28+120)=g_base+0x404C50;
    At<uintptr_t>(0x5D15A0+120)=g_base+0x415280;
    At<BYTE>(0x9BA8D0)=1;At<int>(0x716884)=1;At<uintptr_t>(0x2A105D0)=g_base+Actor;
    At<int>(Status)=100;At<int>(Status+4)=100;At<unsigned>(Actor+1736)=0x80;
    At<unsigned>(Actor+2488)=0x80;
    At<uintptr_t>(Actor+3512)=g_base+Pad;
    At<uintptr_t>(Actor+3520)=g_base+0x2A10620;At<uintptr_t>(Actor+3536)=g_base+0x2A10620;
    At<uintptr_t>(0x2A10620+2784)=g_base+Actor;
    At<uintptr_t>(0x2A10620+3128)=g_base+Actor;At<uintptr_t>(0x2A10620+2792)=g_base+Pad;
}
auto Read() { return gameplay_state::Inspect(Context()); }
void Has(unsigned bits,const char* name) {const auto s=Read();Check((s.blockers&bits)==bits && !s.controllable,name);}
void ExpectUnknown(const char* name) {const auto s=Read();Check(!s.known && (s.blockers&gameplay_state::Unknown) && !s.controllable,name);}
void OwnedField() {
    world_features::pausePhase=world_features::PausePhase::Held;
    world_features::pauseGlobalsOwned=true;
    At<int>(0x716884)=2;At<BYTE>(0xABADE0)=1;At<unsigned>(0xABB854)=world_features::pauseTimerMask;
}
void OwnedFreeze() {world_features::actorFreezeOwned=true;At<unsigned>(0x2A11400)|=0x20;}
void Basics() {
    using namespace gameplay_state;
    Reset();auto s=Read();Check(s.known && s.controllable && !s.blockers,"normal controllable Sora");
    for(auto role:{player_role::Role::Sora,player_role::Role::Roxas,player_role::Role::Mickey}) {
        player_role::next.role=role;s=Read();Check(s.known && s.controllable && s.role==role,"supported role");
    }
    player_role::next.role=player_role::Role::Unknown;ExpectUnknown("role unavailable");
    player_role::next.role=player_role::Role::Other;s=Read();Check(s.known && !s.controllable && (s.blockers&gameplay_state::Unknown),"known unsupported role");
    Reset();At<uintptr_t>(0x2A105D0)=0;s=Read();Check(s.known && (s.blockers&NoPlayer),"no player globally");
    Reset();auto c=Context();c.player=0;s=Inspect(c);Check(!s.known && (s.blockers&NoPlayer),"missing fresh context");
    Reset();c=Context();c.base++;s=Inspect(c);Check(!s.known,"wrong imagebase");
    Reset();At<int>(Status)=0;Has(Dead,"zero HP");
    Reset();At<int>(Status)=-1;ExpectUnknown("negative HP");Has(Dead,"negative HP blocked");
    Reset();At<int>(Status)=101;ExpectUnknown("HP beyond max");
    Reset();At<int>(Status+4)=256;ExpectUnknown("max HP beyond native bound");
    Reset();At<BYTE>(0x9BA8D0)=0;Has(Loading,"scene loading");
    Reset();At<BYTE>(0x9BA8D1)=1;Has(Loading,"scene closing");
    for(int phase:{0,3}) {Reset();At<int>(0x716884)=phase;Has(Loading,"field inactive or closing");}
    for(int phase:{-1,4}) {Reset();At<int>(0x716884)=phase;ExpectUnknown("unknown field phase");}
    Reset();At<BYTE>(0x9BA8D0)=2;ExpectUnknown("unknown scene-ready value");
    Reset();At<BYTE>(0x9BA8D1)=2;ExpectUnknown("unknown closing value");
    for(uintptr_t rva:std::initializer_list<uintptr_t>{0xABAC58u,0xABAC59u}) {Reset();At<BYTE>(rva)=1;Has(Loading,"native reset loading");}
    for(uintptr_t rva:std::initializer_list<uintptr_t>{0x9BA928u,0x2AE9FA8u}) {Reset();At<uintptr_t>(rva)=1;Has(Transition,"native transition pointer");}
    Reset();At<BYTE>(0x9006B0)=1;Has(Menu,"pause menu flag");
    Reset();At<uintptr_t>(0xAC0F48)=1;Has(Menu,"menu window task");
    Reset();At<uintptr_t>(0x2A11478)=1;Has(Cutscene,"event presence without unsafe dereference");
    Reset();At<uintptr_t>(0xBF2AC8)=g_base+Window;At<uintptr_t>(Window+80+24)=1;Has(Menu,"last popup slot");
    Reset();At<uintptr_t>(0xBF2AC8)=g_base+ImageSize-32;ExpectUnknown("unreadable popup context");
    Reset();At<int>(0x716884)=2;Has(InputBlocked,"external field suspension");
}
void InputMatrix() {
    using namespace gameplay_state;
    struct Mask {uintptr_t rva;unsigned bits;};
    const Mask masks[]={{0x2A171E8,1},{Actor+292,0x200000},{0x2A11400,0x100000},
        {Actor+288,0x10000000},{Actor+288,0x80000},{Actor+288,0x400},
        {0x2A10620+36,1},{0x2A10500,1},{0x2A10500,0x80000000},{Pad+80,1},{0x2A11400,0x20}};
    for(auto m:masks) {Reset();At<unsigned>(m.rva)|=m.bits;Has(InputBlocked,"native input/core-stop mask");}
    Reset();At<unsigned>(Actor+2488)&=~0x80u;Has(InputBlocked,"native actor input predicate false");
    Reset();At<BYTE>(0x2A16328)=1;Has(InputBlocked,"native player predicate global");
    Reset();At<BYTE>(Actor+1612)=1;Has(InputBlocked,"actor stop controller");
    Reset();At<int>(0x2A24EDC)=1;Has(InputBlocked,"summon stops normal actor category");
    Reset();At<int>(0x2A24EDC)=1;At<unsigned>(Actor+1736)|=4;Check(Read().controllable,"summon exempt actor category");
    Reset();At<unsigned>(Actor+1736)=0;ExpectUnknown("not native player category");
    Reset();At<uintptr_t>(0x2A0FF68)=g_base+Mission;At<unsigned>(Mission+4)=0x10;Has(InputBlocked,"mission control ended");
    Reset();At<uintptr_t>(0x2A0FF68)=g_base+ImageSize-4;ExpectUnknown("invalid mission context");
    for(uintptr_t rva:std::initializer_list<uintptr_t>{Actor+3536,Actor+3520,0x2A10620u+2784,0x2A10620u+3128,0x2A10620u+2792,Actor+3512}) {
        Reset();At<uintptr_t>(rva)=0;ExpectUnknown("controller/pad identity absent");
    }
    Reset();At<uintptr_t>(Actor+3536)=g_base+Window;ExpectUnknown("unverified script controller");
    Reset();At<unsigned>(Actor+288)|=0x100;Check(Read().controllable,"ordinary action flag is not falsely classified as a cutscene");
    Reset();At<unsigned>(0x2A10504)=2;Check(Read().controllable,"Drive-only rule does not block general controls");
}
void Ownership() {
    using namespace gameplay_state;
    Reset();OwnedField();auto s=Read();Check(s.blockers==TrainerFieldPause,"owned field pause only");
    Reset();OwnedFreeze();s=Read();Check(s.blockers==TrainerActorFreeze,"owned actor freeze only");
    Reset();OwnedField();OwnedFreeze();s=Read();Check(s.blockers==(TrainerFieldPause|TrainerActorFreeze),"two trainer blockers distinct");
    Reset();OwnedField();At<BYTE>(0x9006B0)=1;Has(Menu|TrainerFieldPause,"native menu remains during own pause");
    Reset();OwnedField();At<uintptr_t>(0x2A11478)=1;Has(Cutscene|TrainerFieldPause,"event remains during own pause");
    Reset();OwnedField();At<unsigned>(0xABB854)|=4;Has(gameplay_state::Unknown|TrainerFieldPause,"foreign timer owner remains during own pause");
    Reset();OwnedFreeze();At<unsigned>(0x2A10500)=1;Has(InputBlocked|TrainerActorFreeze,"script lock remains during own freeze");
    Reset();OwnedFreeze();At<uintptr_t>(0x9BA928)=1;Has(Transition|TrainerActorFreeze,"transition remains during own freeze");
    Reset();OwnedField();world_features::samePause=false;s=Read();Check(!(s.blockers&TrainerFieldPause) && (s.blockers&InputBlocked),"old room does not own pause");
    Reset();OwnedFreeze();world_features::sameFreeze=false;s=Read();Check(!(s.blockers&TrainerActorFreeze) && (s.blockers&InputBlocked),"old room does not own freeze");
    Reset();OwnedField();world_features::pauseGlobalsOwned=false;Has(InputBlocked,"field lease not acquired");
    Reset();OwnedField();At<BYTE>(0xABADE0)=0;Has(InputBlocked,"capture lease changed");
    Reset();OwnedField();At<unsigned>(0xABB854)=0;Has(InputBlocked,"timer lease changed");
    Reset();world_features::pausePhase=world_features::PausePhase::Requested;Check(Read().controllable,"pending pause not yet actual pause");
    Reset();world_features::pausePhase=world_features::PausePhase::Step;Check(Read().controllable,"single step currently runs field");
    Reset();OwnedFreeze();At<unsigned>(0x2A11400)=0;Check(Read().controllable,"native cleared freeze not reported held");
}
void Guards() {
    Reset();g_disabled=1;ExpectUnknown("disabled bridge");
    Reset();g_gameThread++;ExpectUnknown("not engine thread");
    Reset();g_shared=nullptr;ExpectUnknown("no shared memory");
    Reset();shared.hostHeartbeat=0;ExpectUnknown("zero heartbeat");
    Reset();shared.hostHeartbeat=fakeNow-5001;ExpectUnknown("expired host");
    Reset();fakeNow=100;shared.hostHeartbeat=0xFFFFFF00;Check(Read().controllable,"heartbeat wrap accepted");
    Reset();fault=true;ExpectUnknown("read access fault fail closed");fault=false;
    Reset();At<uintptr_t>(0x5CBA28+120)=g_base+0x404C60;ExpectUnknown("Sora predicate pointer replaced");
    Reset();player_role::next.role=player_role::Role::Mickey;At<uintptr_t>(0x5D15A0+120)=g_base+0x404C50;ExpectUnknown("Mickey predicate pointer replaced");
    Reset();denied=g_base+0x5CBA28+120;deniedSize=8;ExpectUnknown("input predicate vtable unreadable");
    Reset();At<unsigned>(0xABB854)=2;ExpectUnknown("script timer pause without verified control mode");
    for(const auto& p:gameplay_state::pins) {
        Reset();At<BYTE>(p.rva)^=1;ExpectUnknown("native pin first-byte mismatch");
        Reset();At<BYTE>(p.rva+p.size-1)^=1;ExpectUnknown("native pin last-byte mismatch");
        Reset();denied=g_base+p.rva;deniedSize=p.size;ExpectUnknown("native pin unreadable");
    }
    for(uintptr_t rva:std::initializer_list<uintptr_t>{0x716868u,0x717008u,0x9006B0u,0x9BA888u,0x9BA8D0u,0x9BA920u,
        0xABAC58u,0xABADE0u,0xABB854u,0xAC0F48u,0xBF2AC8u,0x2A0FF68u,0x2A10500u,
        0x2A105D0u,0x2A11400u,0x2A11478u,0x2A16328u,0x2A171E8u,0x2A24EDCu,0x2AE9FA8u,
        Actor,Status,0x2A10620u,Pad}) {
        Reset();denied=g_base+rva;deniedSize=1;ExpectUnknown("required memory unreadable");
    }
    Reset();std::vector<BYTE> before(reinterpret_cast<BYTE*>(g_base),reinterpret_cast<BYTE*>(g_base)+ImageSize);
    GameplayStateCapabilities();GameplayStateSnapshot(Context());
    Check(!memcmp(before.data(),reinterpret_cast<void*>(g_base),ImageSize),"observation leaves every synthetic game byte unchanged");
    for(unsigned i=456;i<=462;++i) {
        Check((shared.supported[i/64]&(uint64_t(1)<<(i%64)))!=0,"capability published");
        Check((shared.valid[i/64]&(uint64_t(1)<<(i%64)))!=0,"snapshot validity published");
    }
    Check(!(shared.valid[463/64]&(uint64_t(1)<<(463%64))),"root owns publication tick");
    Check(shared.values[456]==1 && shared.values[457]==1 && shared.values[458]==0 &&
        shared.values[459]==1 && shared.values[460]==1 && shared.values[461]==1 && shared.values[462]==0,"slot mapping");
}
}
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,ImageSize,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(!g_base) return 2;
    Basics();InputMatrix();Ownership();Guards();
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);
    std::printf("GameplayStateGuardTests: %u checks, %u failures\n",checks,failed);
    return failed?1:0;
}
