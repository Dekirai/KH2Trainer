#define KH2DEV_PAYLOAD_TESTS
#define KH2_ACTOR_LIFETIME_TESTS
#include "../../src/KH2Trainer.Bridge/TrainerBridge.cpp"
#include <stdio.h>

// Private memory only. Seed a previously acquired lock to test the production
// TrainerFrame teardown/dispatch, without constructing Sora or calling game code.
namespace {
unsigned checks=0,failures=0;
SharedState fixture{};
constexpr uintptr_t barRva=0x2A30000,tableRva=barRva+0x100,rowRva=tableRva+8;
constexpr uint64_t owner=0xFD123456AB7890CDULL,instance=0xAA994433CCDDEEFFULL;
void Check(bool good,const char* text) {++checks;if(!good){++failures;printf("FAIL: %s\n",text);}}
uint32_t EncodeFixture(uintptr_t address) {
    const uintptr_t region=address&~uintptr_t(0x1ffffff);
    for(unsigned i=1;i<64;++i) {
        uintptr_t& entry=At<uintptr_t>(0x2B0D720+i*sizeof(uintptr_t));
        if(!entry || entry==region) {
            entry=region;
            return 0x80000000u|(i<<25)|static_cast<uint32_t>(address&0x1ffffff);
        }
    }
    abort();
}
void Setup(uint16_t prior=0) {
    namespace rl=drive_features::revert_lock;
    ZeroMemory(reinterpret_cast<void*>(g_base),kImageSize);ZeroMemory(&fixture,sizeof(fixture));
    g_shared=&fixture;g_gameThread=GetCurrentThreadId();g_disabled=0;g_hostExpired=false;g_snapshotSchedule={};
    actor_lifetime::observerStatus=actor_lifetime::Fault;
    fixture.hostHeartbeat=GetTickCount();drive_features::queue={};
    At<uintptr_t>(0x2AE5E50)=g_base+barRva;At<uintptr_t>(0x2A161E8)=g_base+tableRva;
    At<unsigned>(barRva-16)=0x1000;At<unsigned>(barRva-12)=0x23234141;At<unsigned>(barRva-8)=1;
    At<unsigned>(barRva)=0x01524142;At<int>(barRva+4)=1;At<uint32_t>(barRva+8)=EncodeFixture(g_base+barRva);
    At<uint16_t>(barRva+16)=2;At<unsigned>(barRva+20)=0x00646D63;
    At<uint32_t>(barRva+24)=EncodeFixture(g_base+tableRva);At<unsigned>(barRva+28)=56;
    At<int>(tableRva+4)=1;At<uint16_t>(rowRva)=At<uint16_t>(rowRva+2)=5;
    At<uint16_t>(rowRva+44)=prior;
    rl::Binding binding{};Check(rl::ReadBinding(binding),"private original-arena binding is valid");
    rl::bridge=instance;rl::bridgeBase=g_base;rl::randomAttempted=true;
    rl::lease={1,owner,binding,static_cast<uint16_t>(0x7E&~prior),static_cast<uint16_t>(prior|0x7E)};
    At<uint16_t>(rowRva+44)=static_cast<uint16_t>(prior|0x7E);
    for(const auto& p:rl::kPins)memcpy(reinterpret_cast<void*>(g_base+p.rva),p.bytes,p.size);
}
void RequestRelease(uint64_t requestedOwner=owner,uint64_t requestedInstance=instance) {
    fixture.commandId=1488;fixture.commandIssuedAt=GetTickCount();
    ZeroMemory(fixture.arguments,sizeof(fixture.arguments));
    fixture.arguments[1]=static_cast<uint32_t>(requestedOwner);fixture.arguments[2]=static_cast<uint32_t>(requestedOwner>>32);
    fixture.arguments[3]=static_cast<uint32_t>(requestedInstance);fixture.arguments[4]=static_cast<uint32_t>(requestedInstance>>32);
    InterlockedIncrement(&fixture.requestSequence);TrainerFrame();
    Check(fixture.responseSequence==fixture.requestSequence,"real dispatch acknowledges release request");
}
}
int main() {
    namespace rl=drive_features::revert_lock;
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,kImageSize,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    if(!g_base)return 2;
    Setup(0x8001);DWORD old=0,unused=0;
    Check(VirtualProtect(reinterpret_cast<void*>(g_base+tableRva),4096,PAGE_READONLY,&old)!=FALSE,"make owned table readonly");
    fixture.hostHeartbeat=0;TrainerFrame();
    Check(g_hostExpired&&rl::lease.state==2&&rl::lease.owner==owner&&At<uint16_t>(rowRva+44)==0x807F,"first actual expired frame retains readonly cleanup");
    Check(!fixture.sceneReady&&fixture.values[488]==2&&fixture.values[489]==uint32_t(owner&UINT32_MAX),"pending ownership is published with no player scene");
    TrainerFrame();Check(rl::lease.state==2,"next expired frame preserves unwriteable owner");
    Check(VirtualProtect(reinterpret_cast<void*>(g_base+tableRva),4096,old,&unused)!=FALSE,"restore owned table writability");
    TrainerFrame();Check(g_hostExpired&&!rl::lease.state&&At<uint16_t>(rowRva+44)==0x8001,"later actual expired frame restores only trainer-added bits without a player");
    TrainerFrame();Check(!rl::lease.state&&At<uint16_t>(rowRva+44)==0x8001,"expired frames never reacquire a released lock");

    Setup();At<uintptr_t>(0x2A161E8)=0;fixture.hostHeartbeat=0;TrainerFrame();
    Check(rl::lease.state==2&&At<uint16_t>(rowRva+44)==0x7E,"actual expired frame retains cleanup when installed pointer temporarily disappears");
    At<uintptr_t>(0x2A161E8)=g_base+tableRva;TrainerFrame();
    Check(!rl::lease.state&&At<uint16_t>(rowRva+44)==0,"restored binding is cleaned on a later expired frame");

    Setup();RequestRelease(owner+1);
    Check(fixture.resultCode==0&&rl::lease.owner==owner&&At<uint16_t>(rowRva+44)==0x7E,"wire foreign-owner release succeeds without modifying current owner");
    RequestRelease(owner,instance+1);
    Check(fixture.resultCode!=0&&rl::lease.owner==owner&&At<uint16_t>(rowRva+44)==0x7E,"wire foreign bridge release is rejected without writes");
    RequestRelease();Check(fixture.resultCode==0&&!rl::lease.state&&At<uint16_t>(rowRva+44)==0,"wire owner release works without live scene or player");
    RequestRelease();Check(fixture.resultCode==0&&!rl::lease.state,"wire repeated release is idempotent");
    printf("TrainerFrame Revert cleanup integration: %u checks, %u failures. Private memory only; no game code called.\n",checks,failures);
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
