#define KH2DEV_PAYLOAD_TESTS
#define KH2_PLAYER_HEALTH_TESTS
#include "../../src/KH2Trainer.Bridge/TrainerBridge.cpp"
#include <cstdio>
#include <vector>

namespace {
constexpr uintptr_t ActorRva=0x110000,HudRva=0x112000,WidgetRva=0x114000;
constexpr uintptr_t PadRva=0x11A000,ObjectRva=0x120000,AnimationRva=0x124000,TracksRva=0x128000;
unsigned checks=0,failures=0,hpCalls=0,mpCalls=0;
SharedState state{};
void Check(bool ok,const char* name) { ++checks;if(!ok){++failures;std::printf("FAIL: %s\n",name);} }
__declspec(noinline) uint32_t Packed(uintptr_t p) {
    if(!p) return 0;
    const uintptr_t high=p&~uintptr_t(0x1ffffff);
    for(unsigned i=0;i<64;++i) {
        auto& base=At<uintptr_t>(0x2B0D720+i*8);
        if(!base || base==high) {base=high;return (i<<25)|static_cast<uint32_t>(p&0x1ffffff);}
    }
    return 0;
}
int __fastcall HpCall(void* object,int delta,unsigned stat,BYTE effects) {
    ++hpCalls;Check(reinterpret_cast<uintptr_t>(object)==g_base+ActorRva && stat==0 && effects==0,"HP ABI and no-animation arguments");
    auto& hp=At<int>(0x2A17290);const int lo=At<int>(0x2A17290+8),hi=At<int>(0x2A17290+4);
    hp=(hp+delta<lo)?lo:(hp+delta>hi?hi:hp+delta);return hp;
}
void __fastcall MpCall(void* object,BYTE effects) {
    ++mpCalls;Check(reinterpret_cast<uintptr_t>(object)==g_base+0x2A17290 && effects==0,"MP ABI and no-animation arguments");
    At<int>(0x2A17290+384)=At<int>(0x2A17290+388);
    if(At<float>(0x2A17290+448)>0) At<uint64_t>(0x2A17290+444)=0;
}
TrainerContext Context() { return {g_base,g_base+ActorRva,g_base+0x2A17290,true}; }
void Role(unsigned character,int form) {
    auto c=Context();const auto object=g_base+ObjectRva+8;
    PlayerField<uint16_t>(object,76)=static_cast<uint16_t>(character);
    PlayerField<signed char>(object,87)=static_cast<signed char>(form);
    PlayerField<unsigned>(c.status,608)=character;PlayerField<int>(c.player,3552)=form;
    PlayerField<uint32_t>(c.player,0)=Packed(g_base+(character==4?0x7523B8:0x750300));
    PlayerField<unsigned>(c.player,1736)=character==4?0x2000080:0x1000080;
}
void Setup() {
    memset(reinterpret_cast<void*>(g_base),0,kImageSize);ZeroMemory(&state,sizeof(state));g_shared=&state;g_disabled=0;
    g_gameThread=GetCurrentThreadId();state.hostHeartbeat=GetTickCount();hpCalls=mpCalls=0;
    for(const auto& p:gameplay_state::pins) memcpy(reinterpret_cast<void*>(g_base+p.rva),p.bytes,p.size);
    for(const auto& p:player_health::pins) memcpy(reinterpret_cast<void*>(g_base+p.rva),p.bytes,p.size);
    const auto c=Context();
    At<uintptr_t>(0x750300)=g_base+0x5CBA28;At<uintptr_t>(0x7523B8)=g_base+0x5D15A0;
    At<uintptr_t>(0x5CBA28+120)=g_base+0x404C50;At<uintptr_t>(0x5D15A0+120)=g_base+0x415280;
    At<uintptr_t>(0x5CBA28+24)=g_base+0x404A30;At<uintptr_t>(0x5D15A0+24)=g_base+0x4150D0;
    At<uintptr_t>(0x2A10620)=g_base+0x5C4C68;
    At<uintptr_t>(0x5C4C68+16)=g_base+0x3F29E0;At<uintptr_t>(0x5C4C68+24)=g_base+0x3F2470;
    At<uintptr_t>(0x2A105D0)=c.player;At<uintptr_t>(0x2A171C8)=c.player;
    At<uintptr_t>(0x2A25030)=g_base+ObjectRva;At<int>(ObjectRva+4)=1;
    PlayerField<uintptr_t>(c.player,1472)=c.status;
    PlayerField<uint32_t>(c.status,616)=Packed(c.player);PlayerField<int>(c.status,612)=1;
    PlayerField<uint32_t>(c.player,8)=Packed(g_base+ObjectRva+8);
    PlayerField<int>(c.status,0)=100;PlayerField<int>(c.status,4)=255;
    PlayerField<int>(c.status,384)=25;PlayerField<int>(c.status,388)=100;
    PlayerField<unsigned>(c.player,2488)=0x80;
    PlayerField<uintptr_t>(c.player,3512)=g_base+PadRva;
    PlayerField<uintptr_t>(c.player,3520)=g_base+0x2A10620;PlayerField<uintptr_t>(c.player,3536)=g_base+0x2A10620;
    At<uintptr_t>(0x2A10620+2784)=c.player;At<uintptr_t>(0x2A10620+3128)=c.player;At<uintptr_t>(0x2A10620+2792)=g_base+PadRva;
    At<BYTE>(0x9BA8D0)=1;At<int>(0x716884)=1;At<int>(0x2B0D920)=-2;
    At<uintptr_t>(0x2A24E90)=g_base+HudRva;
    At<uintptr_t>(0xABCFE8)=c.player;
    Role(1,0);player_health::testHp=HpCall;player_health::testMp=MpCall;
    memset(g_playerEffects,0,sizeof(g_playerEffects));
}
void Widget(bool selected=true) {
    At<uintptr_t>(HudRva+40)=g_base+WidgetRva;
    At<uint32_t>(HudRva+4)=Packed(g_base+(selected?ActorRva:ActorRva+16));
    At<int>(WidgetRva+19212)=255;At<int>(WidgetRva+19220)=230;
}
void Animated(uintptr_t member,unsigned clip,unsigned count=1) {
    const uintptr_t sequence=member+32;
    PlayerField<uintptr_t>(sequence,224)=g_base+AnimationRva;
    PlayerField<uintptr_t>(sequence,216)=g_base+TracksRva;
    At<uint16_t>(AnimationRva+clip*36)=2;At<uint16_t>(AnimationRva+clip*36+2)=static_cast<uint16_t>(count);
}
int Command(unsigned slot,double value=0) {
    const double args[8]={value};TrainerResult result{};
    Check(PlayerHandle(Context(),slot,args,result),"health command handled");return result.code;
}
void Basics() {
    for(unsigned role:{1u,14u,4u}) {
        const int last=role==1?6:role==14?1:0;
        for(int i=0;i<=last;++i) {
            Setup();Role(role,role==4?11:role==14?i*10:i);
            Check(player_role::Inspect(Context()).role==(role==1?player_role::Sora:role==14?player_role::Roxas:player_role::Mickey),"actual role classifier");
            Check(PlayerHealthControlReady(Context()),"actual gameplay controller accepts supported role");
            Check(Command(4)==0 && hpCalls==1 && At<int>(0x2A17290)==255,"heal uses native callback for every audited form/role");
            Check(Command(0,1)==0 && hpCalls==2 && At<int>(0x2A17290)==1,"nonlethal one HP for every audited form/role");
            At<float>(0x2A17290+444)=3;At<float>(0x2A17290+448)=10;
            Check(Command(6)==0 && hpCalls==3 && mpCalls==1 && At<float>(0x2A17290+448)==0,"full restore checks both paths and clears recharge");
        }
    }
    Setup();At<int>(0x2A17290+8)=50;
    Check(Command(0,1)==0 && At<int>(0x2A17290)==50,"native scripted minimum HP preserved");
    Setup();At<uintptr_t>(0x2A24E90)=0;
    Check(Command(0,100)==0 && !hpCalls,"same HP is no-op without touching missing HUD");
    Check(Command(4)!=0 && !hpCalls && At<int>(0x2A17290)==100,"missing HUD blocks HP before native dispatch");
    Check(Command(5)==0 && mpCalls==1,"MP has no HP HUD dependency");
    Setup();At<int>(0x2A17290+388)=0;At<int>(0x2A17290+384)=0;
    Check(Command(5)==0 && !mpCalls,"zero MP no-op invokes no native function");
    Setup();At<int>(0x2A17290+8)=101;
    Check(Command(4)!=0 && !hpCalls,"invalid HP minimum rejected");
    for(unsigned character:{2u,4u,14u}) {
        Setup();Role(character,3);
        Check(Command(4)!=0 && Command(5)!=0 && !hpCalls && !mpCalls,"unrecognized role/form has no native calls");
    }
}
void HudAndAnimation() {
    Setup();Widget();Check(Command(4)==0,"HUD positive path with native animation early-out");
    Setup();Widget();Animated(g_base+WidgetRva+3584,44);
    Check(Command(4)==0,"positive HP segment follows animation44");
    Setup();Widget();Animated(g_base+WidgetRva+2072,41);Animated(g_base+WidgetRva+3584,46);
    Check(Command(0,1)==0,"negative HP follows animations41 and46");
    Setup();Widget();At<int>(0x2A17290)=250;Animated(g_base+WidgetRva+2072,41);Animated(g_base+WidgetRva+3584,44);
    Check(Command(0,220)==0,"negative HP keeping upper segment follows44");
    Setup();Widget(false);At<uintptr_t>(HudRva+40)=1;
    Check(Command(4)==0,"different HUD actor skips unrelated widget");
    Setup();Widget();At<int>(HudRva+48)=1;At<uintptr_t>(HudRva+40)=1;
    Check(Command(4)==0,"other HUD stat skips HP widget");
    Setup();Widget();At<uintptr_t>(HudRva+40)=1;
    Check(Command(4)!=0 && !hpCalls,"unreadable selected widget rejected");
    Setup();Widget();At<int>(WidgetRva+19212)=254;
    Check(Command(4)!=0,"stale widget maximum rejected");
    Setup();Widget();At<int>(WidgetRva+19220)=256;
    Check(Command(0,1)!=0,"unbounded previous HP rejected before native animation loop");
    Setup();Widget();const uintptr_t seq=g_base+WidgetRva+3584+32;
    PlayerField<unsigned>(seq,316)=1;
    Check(Command(4)!=0,"active animation requires row pointer");
    PlayerField<uintptr_t>(seq,224)=UINTPTR_MAX-16;
    Check(Command(4)!=0,"animation row arithmetic overflow rejected");
    Animated(g_base+WidgetRva+3584,44);
    PlayerField<uintptr_t>(seq,216)=1;
    Check(Command(4)!=0,"unreadable track span rejected");
    At<uint16_t>(AnimationRva+44*36+2)=0;
    Check(Command(4)==0,"zero tracks preserve native no-dereference branch");
    Setup();Widget();DWORD old=0,unused=0;
    Check(VirtualProtect(reinterpret_cast<void*>(g_base+WidgetRva),0x5000,PAGE_READONLY,&old)!=FALSE,"read-only widget fixture");
    Check(Command(4)!=0 && !hpCalls,"read-only widget rejected before native HP mutation");
    VirtualProtect(reinterpret_cast<void*>(g_base+WidgetRva),0x5000,old,&unused);
}
void PausesAndPins() {
    Setup();const auto c=Context();
    Check(Command(18,1)==0 && Command(19,1)==0,"continuous health toggles accepted");
    At<BYTE>(0x9006B0)=1;PlayerTick(c);
    Check(!hpCalls && !mpCalls && Command(6)!=0,"menu pauses native HP/MP ticks and manual restore");
    At<BYTE>(0x9006B0)=0;At<uintptr_t>(0x2A11478)=1;PlayerTick(c);
    Check(!hpCalls && !mpCalls,"cutscene pauses native HP/MP ticks");
    At<uintptr_t>(0x2A11478)=0;At<unsigned>(0x2A10620+36)=1;PlayerTick(c);
    Check(!hpCalls && !mpCalls,"input lock pauses native HP/MP ticks");
    At<unsigned>(0x2A10620+36)=0;PlayerTick(c);
    Check(hpCalls==1 && mpCalls==1,"native health effects resume when control returns");
    Setup();for(const auto& pin:player_health::pins) {
        for(SIZE_T i:{SIZE_T(0),pin.size/2,pin.size-1}) {
            auto& byte=At<BYTE>(pin.rva+i);byte^=1;
            if(pin.paths&1) Check(!player_health::HpReady(Context(),255),"changed reachable HP body blocks dispatch");
            if(pin.paths&2) Check(!player_health::MpReady(Context()),"changed reachable MP body blocks dispatch");
            byte^=1;
        }
    }
    Setup();At<BYTE>(0x3c2040)^=1;
    Check(Command(6)!=0 && !hpCalls && !mpCalls && At<int>(0x2A17290)==100,"invalid MP rejects full restore before HP write");
    Setup();for(int epoch:{0,-1}) {At<int>(0x2B0D920)=epoch;Check(Command(4)!=0 && Command(5)!=0,"Ptr32 must be initialized");}
    Setup();state.hostHeartbeat=GetTickCount()-6000;
    Check(Command(4)!=0 && Command(5)!=0,"expired host rejects native health");
    Setup();g_gameThread++;
    Check(Command(4)!=0 && Command(5)!=0,"wrong thread rejects native health");
    Setup();Widget();std::vector<BYTE> before(kImageSize);
    memcpy(before.data(),reinterpret_cast<void*>(g_base),kImageSize);
    Check(player_health::HpReady(Context(),255) && player_health::MpReady(Context()),"valid read-only preflight");
    Check(!memcmp(before.data(),reinterpret_cast<void*>(g_base),kImageSize),"preflight changes no game bytes");
}
}
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,kImageSize,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(!g_base) return 2;
    Basics();HudAndAnimation();PausesAndPins();
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);
    std::printf("PlayerHealthGuardTests: %u checks, %u failures\n",checks,failures);
    return failures?1:0;
}
