#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdint.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <initializer_list>
#include <limits>
// Synthetic memory and local mock call targets only. No game process or files.
namespace {
uintptr_t g_base=0;
struct TrainerContext { uintptr_t base,player,status; bool sceneReady; };
struct TrainerResult { LONG code; const wchar_t* text; };
struct Shared { double values[128]; uint64_t valid[2],supported[2]; } shared{};
template<class T> T& At(uintptr_t rva) { return *reinterpret_cast<T*>(g_base+rva); }
bool Readable(const void* p,size_t size) {
    MEMORY_BASIC_INFORMATION m{};
    if(!p || reinterpret_cast<uintptr_t>(p)>UINTPTR_MAX-size || !VirtualQuery(p,&m,sizeof(m)) ||
       m.State!=MEM_COMMIT || (m.Protect&(PAGE_GUARD|PAGE_NOACCESS))) return false;
    return reinterpret_cast<uintptr_t>(p)+size<=reinterpret_cast<uintptr_t>(m.BaseAddress)+m.RegionSize;
}
bool Writable(const void* p,size_t size) { return Readable(p,size); }
uintptr_t DecodePacked(uint32_t n) { return n ? g_base+n : 0; }
bool IsInteger(double n,double low,double high) { return isfinite(n)&&n>=low&&n<=high&&floor(n)==n; }
void SnapshotValue(unsigned s,double n) { shared.values[s]=n;shared.valid[s/64]|=uint64_t(1)<<(s%64); }
void SupportCapability(unsigned s) { shared.supported[s/64]|=uint64_t(1)<<(s%64); }
#include "../../../trainer/Native/ProgressionFeatures.inl"
unsigned checks=0,failures=0,gives=0,removes=0,refreshes=0,expCalls=0; int lastExp=0;
TrainerContext context{};
void Check(bool ok,const char* name) { ++checks;if(!ok){++failures;printf("FAIL %s\n",name);} }
char __fastcall MockGive(unsigned id,unsigned destination,unsigned char enabled) {
    Check(destination==100&&enabled==0,"give ABI forwards stock destination"); ++gives;
    progression::ItemTable table{}; progression::Items(context,table);
    const BYTE* row=progression::FindItem(table,id); const unsigned index=progression::ItemSlot(row);
    if(row[3]&1) At<BYTE>(progression::SaveRva+progression::Unique+index/8)|=BYTE(1u<<(index%8));
    else ++At<BYTE>(progression::SaveRva+progression::Stock+index);
    return 1;
}
char __fastcall MockRemove(unsigned id,int amount) {
    ++removes;progression::ItemTable table{};progression::Items(context,table);
    At<BYTE>(progression::SaveRva+progression::Stock+progression::ItemSlot(progression::FindItem(table,id)))-=BYTE(amount);return 1;
}
void __fastcall MockRefresh(uintptr_t status) { Check(status==context.status,"refresh ABI passes status");++refreshes; }
intptr_t __fastcall MockExp(int amount) { ++expCalls;lastExp=amount;At<int32_t>(progression::SaveRva+progression::Experience)+=amount;return 0; }
void Stub(uintptr_t rva,uintptr_t destination) {
    BYTE bytes[12]={0x48,0xb8};memcpy(bytes+2,&destination,8);bytes[10]=0xff;bytes[11]=0xe0;
    DWORD old{};VirtualProtect(reinterpret_cast<void*>(g_base+rva),12,PAGE_EXECUTE_READWRITE,&old);
    memcpy(reinterpret_cast<void*>(g_base+rva),bytes,12);FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(g_base+rva),12);
}
TrainerResult Command(unsigned slot,double a=0,double b=0,double d=0) { double args[8]={a,b,d};TrainerResult r{};Check(ProgressionHandle(context,slot,args,r),"command handled");return r; }
void Row(unsigned index,unsigned id,BYTE type,BYTE flags,unsigned inventorySlot,unsigned ordinal=0) {
    const uintptr_t r=0x40008+24*index;At<WORD>(r)=WORD(id);At<BYTE>(r+2)=type;At<BYTE>(r+3)=flags;At<WORD>(r+18)=WORD(inventorySlot);At<WORD>(r+4)=WORD(ordinal);
}
}
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,0x2C00000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!g_base)return 2;
    context={g_base,g_base+0x50000,g_base+0x60000,true};
    Stub(0x3C3F00,reinterpret_cast<uintptr_t>(&MockGive));Stub(0x3C4A40,reinterpret_cast<uintptr_t>(&MockRemove));
    Stub(0x3C2100,reinterpret_cast<uintptr_t>(&MockRefresh));Stub(0x3ECF30,reinterpret_cast<uintptr_t>(&MockExp));
    At<uint32_t>(progression::SaveRva)=0x4A32484B;At<uint32_t>(progression::SaveRva+4)=0x3A;
    At<uintptr_t>(0x50000+1472)=context.status;At<uint32_t>(0x60000+592)=DWORD(progression::SaveRva+progression::Characters);
    At<uint32_t>(0x60000+616)=0x50000;At<uint32_t>(0x60000+620)=DWORD(progression::SaveRva+progression::Characters);At<unsigned>(0x60000+608)=1;
    At<uintptr_t>(0x2AE5760)=g_base+0x20000;At<uintptr_t>(0x2A11678)=g_base+0x21000;
    At<uintptr_t>(0x2AEA8A0)=g_base+0x30000;At<int>(0x30004)=1;
    At<uintptr_t>(0x2A25370)=g_base+0x40000;At<int>(0x40004)=13;
    for(unsigned i=0;i<7;++i)Row(i,i+1,0,0,i);
    Row(7,138,19,0,12,19);Row(8,159,20,1,36);Row(9,26,21,1,1);Row(10,768,2,0,65535);
    Row(11,1000,14,0,20);Row(12,1001,15,0,21);
    At<uintptr_t>(0x2AE58A8)=g_base+0x10000;At<int>(0x10004)=16;
    for(unsigned i=1;i<=13;++i){At<int>(0x10008+4*i)=32;At<BYTE>(progression::SaveRva+progression::Characters+276*(i-1)+15)=1;}
    At<int>(0x10080)=99;
    Check(Command(80,999999).code==0&&At<int>(progression::SaveRva+9280)==999999,"munny upper bound stored");
    Check(Command(80,1000000).code!=0&&At<int>(progression::SaveRva+9280)==999999,"munny over bound preserves value");
    Check(Command(80,std::numeric_limits<double>::quiet_NaN()).code!=0,"NaN rejected");
    context.sceneReady=false;Check(Command(80,1).code!=0,"scene gate rejects mutation");context.sceneReady=true;
    At<uint32_t>(progression::SaveRva+4)=0;Check(Command(80,1).code!=0,"save header gate rejects mutation");At<uint32_t>(progression::SaveRva+4)=0x3A;
    Check(Command(83,1,3).code==0&&gives==3&&At<BYTE>(progression::SaveRva+progression::Stock)==3,"stock increase uses bounded native grants");
    Check(Command(83,1,1).code==0&&removes==1&&At<BYTE>(progression::SaveRva+progression::Stock)==1,"stock decrease forwards exact delta");
    unsigned calls=gives;Check(Command(83,138,99).code!=0&&gives==calls,"ability rejected from stock path");
    Check(Command(83,768,1).code!=0&&gives==calls,"mod item out-of-range slot rejected");
    Check(Command(84,26).code!=0&&gives==calls,"form excluded from incomplete unlock path");
    Check(Command(84,159).code==0&&(At<BYTE>(progression::SaveRva+progression::Unique+4)&16),"unique grant sets validated bit through native mock");
    const uintptr_t abilities=progression::SaveRva+progression::Characters+84;
    Check(Command(85,1,138,1).code==0&&At<WORD>(abilities)==(138|0x8000)&&refreshes==1,"ability added and active status refreshed");
    Check(Command(85,1,138,1).code!=0&&refreshes==1,"duplicate ability rejected before refresh");
    Check(Command(86,1,138,0).code==0&&At<WORD>(abilities)==138,"disable preserves ability ID");
    At<WORD>(abilities+2)=WORD(138|0x8000);Check(Command(86,1,138,0).code==0&&At<WORD>(abilities+2)==138,"disable handles owned duplicate copies");
    Check(Command(87,1,138).code==0&&At<WORD>(abilities)==138&&At<WORD>(abilities+2)==0,"remove deletes exactly one copy and preserves dense list");
    At<uint32_t>(0x60000+596)=0x70000;Check(Command(86,1,138,1).code!=0&&At<WORD>(abilities)==138,"form blocks unsupported rebuild");At<uint32_t>(0x60000+596)=0;
    At<uint32_t>(0x60000+620)=0;Check(Command(86,1,138,1).code!=0,"wrong character base prevents rebuild");At<uint32_t>(0x60000+620)=DWORD(progression::SaveRva+progression::Characters);
    At<WORD>(0x3000A)=999;Check(Command(86,1,138,1).code!=0,"missing equipment effect ability blocks rebuild");At<WORD>(0x3000A)=0;
    At<WORD>(0x40008+24*7+4)=300;Check(Command(86,1,138,1).code!=0,"unbounded ability ordinal rejected");At<WORD>(0x40008+24*7+4)=19;
    At<int>(progression::SaveRva+progression::Experience)=9999990;
    Check(Command(82,100).code==0&&expCalls==1&&lastExp==9,"EXP caps delta before native call");
    Check(Command(82,-1).code!=0&&expCalls==1,"negative EXP rejected");
    Check(Command(94,2).code==0,"validated basic consumable preset accepted");
    for(unsigned i=0;i<7;++i)Check(At<BYTE>(progression::SaveRva+progression::Stock+i)==2,"preset stock exact");
    Check(Command(88,13).code==0&&progression::selectedCharacter==13,"character selection updated");
    Check(Command(88,14).code!=0&&progression::selectedCharacter==13,"alias outside UI slots rejected");
    ProgressionSnapshot(context);Check(shared.values[89]==1&&shared.values[95]==14,"snapshot matches selected character and stock");
    const uintptr_t character=progression::SaveRva+progression::Characters;
    At<BYTE>(character+16)=1;At<BYTE>(character+17)=1;At<BYTE>(progression::SaveRva+progression::Stock+20)=1;
    Check(Command(96,1,1000,0).code==0&&At<WORD>(character+20)==1000&&At<BYTE>(progression::SaveRva+progression::Stock+20)==0,"armor moves bag copy into slot");
    Check(Command(96,1,0,0).code==0&&At<WORD>(character+20)==0&&At<BYTE>(progression::SaveRva+progression::Stock+20)==1,"unequip returns bag copy");
    Check(Command(97,1,1000,0).code!=0&&At<WORD>(character+36)==0,"equipment wrong type rejected");
    Check(Command(96,1,1000,1).code!=0,"locked equipment slot rejected");
    At<WORD>(character+20)=1000;At<BYTE>(progression::SaveRva+progression::Stock+20)=99;
    Check(Command(96,1,0,0).code!=0&&At<WORD>(character+20)==1000,"full stock prevents losing returned equipment");
    ProgressionReset(context);Check(At<int>(progression::SaveRva+9280)==999999,"reset does not undo one-time progression");
    ProgressionCapabilities();Check((shared.supported[1]&0x3ffff0000ull)==0x3ffff0000ull,"all progression slots advertised");
    printf("Progression synthetic tests: %u checks, %u failures\n",checks,failures);VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
