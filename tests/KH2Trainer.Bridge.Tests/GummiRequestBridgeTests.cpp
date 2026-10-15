// Exercise the actual shipping dispatch and call ABI in a private synthetic image.
// No Gummi test hooks, game process, loaded resources or input are involved.
#define KH2DEV_PAYLOAD_TESTS
#include "../../src/KH2Trainer.Bridge/TrainerBridge.cpp"
#include <stdio.h>

namespace {
unsigned checks=0,failures=0;
SharedState shared{};
constexpr uintptr_t PlayerRva=0x50000,ComboRva=PlayerRva+4872;
void Check(bool value,const char* label) { ++checks;if(!value){++failures;printf("FAIL %s\n",label);} }
uint32_t Encode(uintptr_t address) {
    At<uintptr_t>(0x2B0D720+8)=address&~uintptr_t(0x1ffffff);
    return 0x82000000u|static_cast<uint32_t>(address&0x1ffffff);
}
void SetCombo(int phase,int index,float timer,int stock) {
    memset(reinterpret_cast<void*>(g_base+ComboRva),0,72);
    At<int>(ComboRva)=phase;At<uintptr_t>(ComboRva+8)=g_base+PlayerRva+1160;
    for(unsigned i=0;i<5;++i)At<int>(ComboRva+32+4*i)=1;
    At<int>(ComboRva+52)=index;At<int>(ComboRva+60)=stock;
    At<float>(ComboRva+64)=timer;At<unsigned>(ComboRva+68)=9;
}
void Queue() {
    shared.hostHeartbeat=GetTickCount();shared.commandIssuedAt=GetTickCount();
    shared.commandId=1485;ZeroMemory(shared.arguments,sizeof(shared.arguments));
    InterlockedIncrement(&shared.requestSequence);
}
void Dispatch() { Queue();TrainerFrame(); }
void Ready() {
    g_shared=&shared;g_gameThread=GetCurrentThreadId();g_disabled=0;
    At<uintptr_t>(gummi::ModuleRva)=g_base+gummi::ModuleVtableRva;
    At<uintptr_t>(gummi::ModuleRva+8)=g_base+0x90000;
    At<int>(gummi::ModuleRva+36)=1;
    At<uintptr_t>(gummi::ModeListRva)=g_base+gummi::ModuleRva;
    At<uintptr_t>(gummi::HeapRva)=At<uintptr_t>(gummi::ModuleHeapRva)=g_base+0xA0000;
    At<uintptr_t>(gummi::SchedulerRva)=g_base+0x90000;
    At<int>(gummi::MissionPhaseRva)=8;
    At<uintptr_t>(gummi::PlayerRva)=g_base+PlayerRva;
    At<uintptr_t>(gummi::DescriptorRva)=g_base+gummi::DescriptorVtableRva;
    At<uint32_t>(PlayerRva)=Encode(g_base+gummi::DescriptorRva);
    At<uintptr_t>(PlayerRva+0x550)=g_base+PlayerRva+0x570;
    At<uintptr_t>(PlayerRva+0x570)=g_base+gummi::StateVtableRva;
    At<float>(PlayerRva+0x578)=50;At<int>(PlayerRva+0x57C)=100;
    At<int>(PlayerRva+0x5D8)=2;At<unsigned>(PlayerRva+0x140C)=0;
    At<uintptr_t>(PlayerRva+1160)=g_base+0x5B5238;
    At<float>(0x717480)=1;
    SetCombo(0,0,0,1);
}
}
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,0x2C00000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(!g_base)return 2;
    for(const auto& s:gummi_extra::requestCode)memcpy(reinterpret_cast<void*>(g_base+s.rva),s.data,s.size);
    // Enable the leaf's page only. The consumer entry and dispatchers remain
    // on non-executable pages and cannot be called by a successful request.
    DWORD previous=0,ignored=0;
    Check(VirtualProtect(reinterpret_cast<void*>(g_base+gummi_extra::RequestSetterRva),5,PAGE_EXECUTE_READ,&previous)!=FALSE,
        "isolated request setter is executable");
    FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(g_base+gummi_extra::RequestSetterRva),5);
    Ready();
    BYTE before[0x1410];memcpy(before,reinterpret_cast<void*>(g_base+PlayerRva),sizeof(before));
    Dispatch();
    Check(shared.responseSequence==shared.requestSequence&&shared.resultCode==0&&wcsstr(shared.resultText,L"request queued once"),
        "command1485 reaches production native setter and acknowledges only the request");
    *reinterpret_cast<unsigned*>(before+4872+68)|=2;
    Check(!memcmp(before,reinterpret_cast<void*>(g_base+PlayerRva),sizeof(before)),
        "shipping path changes only request flag bytes in the whole ship");
    Check((shared.supportedCapabilities[485/64]&(uint64_t(1)<<(485%64)))!=0&&
        (shared.supportedCapabilities[486/64]&(uint64_t(1)<<(486%64)))!=0&&
        (shared.supportedCapabilities[487/64]&(uint64_t(1)<<(487%64)))!=0&&
        (shared.supportedCapabilities[488/64]&(uint64_t(1)<<(488%64)))!=0&&
        (shared.supportedCapabilities[492/64]&(uint64_t(1)<<(492%64)))!=0&&
        (shared.supportedCapabilities[493/64]&(uint64_t(1)<<(493%64)))!=0&&
        (shared.supportedCapabilities[498/64]&(uint64_t(1)<<(498%64)))!=0&&
        (shared.supportedCapabilities[499/64]&(uint64_t(1)<<(499%64)))==0,
        "shipping capabilities485..498 are advertised and adjacent499 remains reserved");
    At<unsigned>(ComboRva+68)&=~2u;TrainerFrame();
    Check((At<unsigned>(ComboRva+68)&2)==0,"an acknowledged wire sequence cannot replay the request");
    for(float timer:{10.f,50.f}) {
        SetCombo(3,1,timer,0);Dispatch();
        Check(shared.resultCode==0&&At<unsigned>(ComboRva+68)==11&&At<int>(ComboRva+60)==0&&At<int>(ComboRva)==3,
            "production continuation request accepts both endpoints without spending stock or advancing phase");
    }
    auto reject=[&](const char* label) {
        memcpy(before,reinterpret_cast<void*>(g_base+PlayerRva),sizeof(before));Dispatch();
        Check(shared.responseSequence==shared.requestSequence&&shared.resultCode!=0&&
            !memcmp(before,reinterpret_cast<void*>(g_base+PlayerRva),sizeof(before)),label);
    };
    SetCombo(0,0,0,0);reject("empty stock rejection does not reach generic writes");
    SetCombo(3,1,9.99f,0);reject("early continuation is rejected through wire dispatch");
    SetCombo(3,1,50.01f,0);reject("late continuation is rejected through wire dispatch");
    SetCombo(0,0,0,1);At<unsigned>(ComboRva+68)|=2;reject("already pending request is not issued again");
    SetCombo(0,0,0,1);At<int>(gummi::MissionPhaseRva)=14;reject("results scene rejection preserves the ship");
    At<int>(gummi::MissionPhaseRva)=8;
    Queue();shared.commandIssuedAt=GetTickCount()-9000;TrainerFrame();
    Check(shared.resultCode!=0&&At<unsigned>(ComboRva+68)==9,"expired transport command never queues a strike");
    At<uintptr_t>(gummi::PlayerRva)=0;Dispatch();
    Check(shared.resultCode!=0&&wcsstr(shared.resultText,L"Gummi"),"missing ship stops at its own native guard");
    Check(VirtualProtect(reinterpret_cast<void*>(g_base+gummi_extra::RequestSetterRva),5,previous,&ignored)!=FALSE,
        "isolated setter protection restored");
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);
    printf("GummiRequestBridgeTests: %u checks, %u failures\n",checks,failures);
    return failures?1:0;
}
