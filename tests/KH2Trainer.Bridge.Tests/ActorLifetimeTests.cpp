#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <intrin.h>
#include <stdint.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <initializer_list>
#ifndef ACTOR_LIFETIME_PRODUCTION_COMPILE
#define KH2_ACTOR_LIFETIME_TESTS
#endif
namespace {
uintptr_t g_base=0;
DWORD g_gameThread=0;
struct TrainerContext { uintptr_t base,player,status; bool sceneReady; };
template<class T>T& At(uintptr_t rva){return *reinterpret_cast<T*>(g_base+rva);}
bool Readable(const void* p,SIZE_T n) {
    MEMORY_BASIC_INFORMATION m{};
    return p && n<=UINTPTR_MAX-reinterpret_cast<uintptr_t>(p) && VirtualQuery(p,&m,sizeof(m)) &&
        m.State==MEM_COMMIT && !(m.Protect&(PAGE_GUARD|PAGE_NOACCESS)) &&
        reinterpret_cast<uintptr_t>(p)+n<=reinterpret_cast<uintptr_t>(m.BaseAddress)+m.RegionSize;
}
uintptr_t DecodePacked(uint32_t p){return p?g_base+p:0;}
#include "../../src/KH2Trainer.Bridge/PlayerRoleSupport.inl"
#include "../../src/KH2Trainer.Bridge/ActorLifetimeSupport.inl"
#ifndef ACTOR_LIFETIME_PRODUCTION_COMPILE
using namespace actor_lifetime;
constexpr uintptr_t Actor=0x50000,Second=0x60000,Pool=0x2A17290,Table=0xC0000,Object=Table+8;
unsigned checks=0,failures=0,birthCalls=0,soraCalls=0,mickeyCalls=0;
uintptr_t seenThis=0,seenActor=0;
uint64_t expectedDead=0;
bool deadBeforeOriginal=false,raiseOriginal=false;
unsigned protectMode=0,protectCalls=0;
SIZE_T WINAPI RaisingQuery(LPCVOID,PMEMORY_BASIC_INFORMATION,SIZE_T){RaiseException(0xE0425152,0,0,nullptr);return 0;}
SIZE_T WINAPI ReservedQuery(LPCVOID p,PMEMORY_BASIC_INFORMATION m,SIZE_T n){const auto r=VirtualQuery(p,m,n);m->State=MEM_RESERVE;return r;}
BOOL WINAPI FailingProtect(LPVOID p,SIZE_T n,DWORD value,PDWORD previous){
    const unsigned call=protectCalls++;
    if(call==0 && protectMode==1)return FALSE;
    if(call==0 && protectMode==2){VirtualProtect(p,n,value,previous);return FALSE;}
    if(call==0 && protectMode==7){
        const BOOL result=VirtualProtect(p,n,value,previous);if(result)*reinterpret_cast<uintptr_t*>(p)=g_base+0x1234;return result;
    }
    if(call==1 && protectMode>=3){
        if(protectMode==6)*reinterpret_cast<uintptr_t*>(p)=g_base+0x1234;
        if(protectMode>=4)VirtualProtect(p,n,value,previous);
        return FALSE;
    }
    if(protectMode==5 && call>1 && value==PAGE_READWRITE)return FALSE;
    return VirtualProtect(p,n,value,previous);
}
TrainerContext context{};
void Check(bool yes,const char* name){++checks;if(!yes){++failures;printf("FAIL %s\n",name);}}
void __fastcall FakeBirth(uintptr_t self,uintptr_t actor){
    ++birthCalls;seenThis=self;seenActor=actor;
    if(raiseOriginal)RaiseException(0xE0425151,0,0,nullptr);
}
uintptr_t FakeDeath(uintptr_t self,uintptr_t actor,bool mickey){
    if(mickey)++mickeyCalls;else++soraCalls;seenThis=self;seenActor=actor;
    const Watch* w=FindLocked(expectedDead);
    deadBeforeOriginal=w && !w->alive;
    if(raiseOriginal)RaiseException(0xE0425151,0,0,nullptr);
    return mickey?0xFEDCBA9876543210ULL:0x123456789ABCDEF0ULL;
}
uintptr_t __fastcall FakeSora(uintptr_t self,uintptr_t actor){return FakeDeath(self,actor,false);}
uintptr_t __fastcall FakeMickey(uintptr_t self,uintptr_t actor){return FakeDeath(self,actor,true);}
void ActorData(uintptr_t actor,uintptr_t status,unsigned character,int form,bool mickey=false,unsigned objectIndex=0) {
    At<uint32_t>(actor)=mickey?0x7523B8:0x750300;
    At<uint32_t>(actor+8)=static_cast<uint32_t>(Object+objectIndex*96);
    At<uintptr_t>(actor+1472)=g_base+status;
    At<unsigned>(actor+1736)=mickey?0x2000080:0x1000080;
    At<int>(actor+3552)=form;
    At<uint16_t>(Object+objectIndex*96+76)=static_cast<uint16_t>(character);
    At<signed char>(Object+objectIndex*96+87)=static_cast<signed char>(form);
    At<unsigned>(status+608)=character;At<int>(status+612)=1;
    At<uint32_t>(status+616)=static_cast<uint32_t>(actor);
}
void SwitchCurrent(uintptr_t actor,uintptr_t status){
    At<uintptr_t>(0x2A105D0)=g_base+actor;context={g_base,g_base+actor,g_base+status,true};
}
void ResetState() {
    memset(watches,0,sizeof(watches));observerStatus=0;installedBase=0;bridgeInstance=nextSerial=0;
    originalBirth=nullptr;originalSoraDeath=nullptr;originalMickeyDeath=nullptr;
    testBirth=&FakeBirth;testSoraDeath=&FakeSora;testMickeyDeath=&FakeMickey;
    testPin=testRandom=true;testSwapFailure=-1;testSwapCalls=0;testReturnOverride=0;
    testQuery=VirtualQuery;testProtect=VirtualProtect;testMemoryType=MEM_IMAGE;
    testForeignAllocation=testNotifyFault=false;protectMode=protectCalls=0;
    birthCalls=soraCalls=mickeyCalls=0;seenThis=seenActor=0;expectedDead=0;deadBeforeOriginal=raiseOriginal=false;
}
void Setup(unsigned character=1,int form=0,bool mickey=false){
    DWORD old=0;VirtualProtect(reinterpret_cast<void*>(g_base),0x2C00000,PAGE_READWRITE,&old);
    memset(reinterpret_cast<void*>(g_base),0,0x2C00000);ResetState();g_gameThread=GetCurrentThreadId();
    for(const auto& p:kPins)memcpy(reinterpret_cast<void*>(g_base+p.rva),p.bytes,p.count);
    At<uintptr_t>(kActionTable)=g_base+kAction;At<uintptr_t>(kAction)=g_base+kActionVtable;
    At<uintptr_t>(0x750300)=g_base+kSoraSlot;At<uintptr_t>(0x7523B8)=g_base+kMickeySlot;
    At<uintptr_t>(kBirthSlot)=g_base+kBirth;At<uintptr_t>(kSoraSlot)=g_base+kSoraDeath;
    At<uintptr_t>(kMickeySlot)=g_base+kMickeyDeath;
    At<uintptr_t>(0x2A25030)=g_base+Table;At<int>(Table+4)=2;
    At<uintptr_t>(0x2A171C8)=g_base+Actor;At<uint32_t>(Actor+2704)=Second;
    At<int>(0x2A23950)=78;for(int i=0;i<78;++i)At<int>(0x2A23810+4*i)=i+2;
    ActorData(Actor,Pool,character,form,mickey);
    ActorData(Second,Pool+632,4,11,true,1);
    SwitchCurrent(Actor,Pool);
}
uint64_t Adopt(){
    Check(Install(context),"complete observer install");
    const auto gen=ObserveCurrent(context);Check(gen!=0,"valid current Actor adopted");return gen;
}
void Constructor(uintptr_t actor){
    testReturnOverride=g_base+kBirthReturn;BirthHook(g_base+kAction,actor);testReturnOverride=0;
}
DWORD WINAPI ForeignBirth(void*) {
    testReturnOverride=g_base+kBirthReturn;BirthHook(g_base+kAction,g_base+Actor);return 0;
}
bool InvokeRaisingBirth(){
    __try { BirthHook(g_base+kAction,g_base+Actor); }
    __except(GetExceptionCode()==0xE0425151?EXCEPTION_EXECUTE_HANDLER:EXCEPTION_CONTINUE_SEARCH) { return true; }
    return false;
}
bool InvokeRaisingDeath(){
    __try { SoraDeathHook(g_base+0x750300,g_base+Actor); }
    __except(GetExceptionCode()==0xE0425151?EXCEPTION_EXECUTE_HANDLER:EXCEPTION_CONTINUE_SEARCH) { return true; }
    return false;
}
#endif
}
#ifndef ACTOR_LIFETIME_PRODUCTION_COMPILE
int main(){
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,0x2C00000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(!g_base)return 2;
    // Actual shared role helper, all supported form variants.
    for(int form=0;form<=6;++form){
        Setup(1,form);auto g=Adopt();Check(Status()==Observing&&Ready(),"ready status");
        Check(BridgeInstance()==testInstance&&g==1,"fresh opaque instance and serial");
        Check(Resolve(g)==context.player&&!IsRetired(g),"live exact generation");
        Check(ObserveCurrent(context)==g,"frame observation preserves generation");
    }
    for(int form:{0,10}){Setup(14,form);auto g=Adopt();Check(Resolve(g)==context.player,"Roxas lifetime supported");}
    Setup(4,11,true);auto g=Adopt();Check(Resolve(g)==context.player,"rescue Mickey lifetime supported");
    Setup();At<int>(Pool+608)=14;Check(Install(context)&&!ObserveCurrent(context),"incoherent role not adopted");
    Setup();At<uint32_t>(Actor)=0x74A518;At<uintptr_t>(0x74A518)=g_base+0x5B1110;
    Check(Install(context)&&!ObserveCurrent(context),"Other descriptor not adopted");

    // Crucial ABA: same bytes, same address, new native construction.
    Setup();g=Adopt();Check(Pin(g),"old receipt pinned");Constructor(context.player);
    Check(birthCalls==1&&seenThis==g_base+kAction&&seenActor==context.player,"constructor original once exact arguments");
    Check(IsRetired(g)&&!Resolve(g),"same-address construction retires old generation immediately");
    const auto fresh=ObserveCurrent(context);Check(fresh>g&&Resolve(fresh)==context.player,"identical new Actor receives fresh generation");
    Check(Pin(fresh)&&FindLocked(g)->pins==1,"old pinned tombstone retained beside same-address new lifetime");
    Unpin(g);Check(!FindLocked(g)&&IsRetired(g),"resolved old tombstone may be removed, never reused");
    Check(!Pin(g),"retired token cannot pin new same-address Actor");

    Setup();g=Adopt();Pin(g);
    Constructor(g_base+0x90000);Check(Resolve(g)==context.player,"unrelated Actor birth preserves watched lifetime");
    BirthHook(g_base+kAction,context.player);Check(Resolve(g)==context.player,"unrecognized ordinary action call does not mint birth");
    for(uintptr_t site:{uintptr_t(0x3B4DDA),uintptr_t(0x3B62E3),uintptr_t(kBirthReturn-1),uintptr_t(kBirthReturn+1)}){
        testReturnOverride=g_base+site;BirthHook(g_base+kAction,context.player);
        Check(Resolve(g)==context.player,"nonconstructor returnsite preserves lifetime");
    }
    testReturnOverride=0;

    Setup();g=Adopt();Pin(g);context.sceneReady=false;
    Check(ObserveCurrent(context)==g&&Resolve(g)==context.player,"unready phase preserves identity without writing Actor");
    SwitchCurrent(Second,Pool+632);auto m=ObserveCurrent(context);Check(m>g&&Pin(m),"Mickey separate pinned lifetime");
    Check(Resolve(g)==g_base+Actor&&!IsRetired(g),"offcurrent living Sora remains resolvable");
    expectedDead=m;const auto mr=MickeyDeathHook(g_base+0x7523B8,g_base+Second);
    Check(mr==0xFEDCBA9876543210ULL&&mickeyCalls==1&&deadBeforeOriginal,"Mickey death observed before original; return preserved");
    Check(IsRetired(m)&&Resolve(g)==g_base+Actor,"Mickey death does not retire offcurrent Sora");
    SwitchCurrent(Actor,Pool);Check(ObserveCurrent(context)==g,"return to same live Sora retains original generation");
    expectedDead=g;const auto sr=SoraDeathHook(g_base+0x750300,g_base+Actor);
    Check(sr==0x123456789ABCDEF0ULL&&soraCalls==1&&deadBeforeOriginal&&IsRetired(g),"Sora death observed before original");
    Check(SoraDeathHook(g_base+0x750300,0)==sr&&soraCalls==2,"null destructor actor still forwarded");

    Setup();g=Adopt();Pin(g);At<uintptr_t>(0x2A171C8)=0;
    Check(!Resolve(g)&&!IsRetired(g),"bulk teardown absence is unresolved, not invented death");
    At<uintptr_t>(0x2A171C8)=g_base+Actor;Constructor(context.player);Check(IsRetired(g),"later observed birth resolves old stale lifetime");
    Setup();g=Adopt();Pin(g);At<uintptr_t>(kBirthSlot)=g_base+kBirth;
    Check(!Ready()&&Status()==Fault&&!Resolve(g)&&!IsRetired(g),"hook loss is uncertain, not known destruction");
    Check(FindLocked(g)->pins==1,"fault retains pinned receipt bookkeeping");Unpin(g);
    Check(FindLocked(g)&&FindLocked(g)->pins==0,"unpin allowed after fault without discarding alive record");
    Constructor(g_base+Actor);Check(birthCalls==1,"late callback after fault still forwards");
    Check(!Install(context),"fault cannot silently reinstall under old serials");

    Setup();g=Adopt();Pin(g);At<uintptr_t>(kActionTable)=g_base+kAction+16;
    Check(!ObserveCurrent(context)&&!IsRetired(g)&&Status()==Fault,"table replacement blocks without false death");
    Setup();g=Adopt();Pin(g);++At<uintptr_t>(kAction);
    Check(!Ready()&&!IsRetired(g),"default action vptr replacement blocks");
    Setup();g=Adopt();Pin(g);++At<BYTE>(0x3B3200);
    Check(!Resolve(g)&&!IsRetired(g),"constructor code change blocks generation proof");
    Setup();g=Adopt();Pin(g);SoraDeathHook(g_base+0x7523B8,context.player);
    Check(soraCalls==1&&Status()==Fault&&!IsRetired(g),"unexpected descriptor fails observation but forwards");
    Setup();g=Adopt();Pin(g);testReturnOverride=g_base+kBirthReturn;BirthHook(g_base+kAction,0);
    Check(birthCalls==1&&Status()==Fault&&!IsRetired(g),"null constructor signal faults and forwards");
    Setup();g=Adopt();Pin(g);
    HANDLE thread=CreateThread(nullptr,0,&ForeignBirth,nullptr,0,nullptr);
    Check(thread!=nullptr,"foreign callback test thread");
    if(thread){WaitForSingleObject(thread,INFINITE);CloseHandle(thread);}
    Check(birthCalls==1&&Status()==Fault&&!IsRetired(g),"foreign thread fails closed; original once, no false death");

    Setup();g=Adopt();Pin(g);raiseOriginal=true;testReturnOverride=g_base+kBirthReturn;
    Check(InvokeRaisingBirth()&&birthCalls==1&&IsRetired(g),"original birth exception propagates after observation");
    Check(Ready(),"observation lock released before raising original");
    Setup();g=Adopt();Pin(g);expectedDead=g;raiseOriginal=true;
    Check(InvokeRaisingDeath()&&soraCalls==1&&IsRetired(g)&&deadBeforeOriginal,"original death exception propagates");
    Check(Ready(),"destructor exception leaves observation lock available");

    Setup();g=Adopt();Pin(g);testNotifyFault=true;Constructor(context.player);
    Check(birthCalls==1&&Status()==Fault&&!IsRetired(g),"birth metadata exception still forwards and keeps receipts uncertain");
    Check(Ready()==false,"birth metadata exception releases lock");
    Setup();g=Adopt();Pin(g);testNotifyFault=true;
    Check(SoraDeathHook(g_base+0x750300,context.player)==0x123456789ABCDEF0ULL&&soraCalls==1&&Status()==Fault,
        "Sora notification exception cannot suppress native destructor");
    Setup(4,11,true);g=Adopt();Pin(g);testNotifyFault=true;
    Check(MickeyDeathHook(g_base+0x7523B8,context.player)==0xFEDCBA9876543210ULL&&mickeyCalls==1&&Status()==Fault,
        "Mickey notification exception cannot suppress native destructor");
    Setup();g=Adopt();Pin(g);testQuery=&RaisingQuery;Constructor(context.player);
    Check(birthCalls==1&&Status()==Fault&&!IsRetired(g),"real metadata-query fault is isolated from original callback");

    // Each hook-install failure rolls back only owned slots.
    for(int fail=0;fail<3;++fail){
        Setup();testSwapFailure=fail;
        Check(!Install(context)&&Status()==Fault,"partial install rejected");
        Check(At<uintptr_t>(kBirthSlot)==g_base+kBirth&&At<uintptr_t>(kSoraSlot)==g_base+kSoraDeath&&
              At<uintptr_t>(kMickeySlot)==g_base+kMickeyDeath,"partial install restores own original slots");
        Check(!ObserveCurrent(context),"no baseline after partial observer install");
    }
    for(unsigned which=0;which<3;++which){
        Setup();const uintptr_t slots[]={kBirthSlot,kSoraSlot,kMickeySlot};
        At<uintptr_t>(slots[which])=g_base+0x1234;
        Check(!Install(context)&&At<uintptr_t>(slots[which])==g_base+0x1234,"foreign slot never overwritten");
    }
    Setup();testPin=false;Check(!Install(context)&&At<uintptr_t>(kBirthSlot)==g_base+kBirth,"pin-module failure installs nothing");
    Setup();testRandom=false;Check(!Install(context)&&At<uintptr_t>(kBirthSlot)==g_base+kBirth,"nonce failure installs nothing");
    Setup();testBirth=nullptr;Check(!Install(context)&&At<uintptr_t>(kBirthSlot)==g_base+kBirth,"null original test callback never published");
    Setup();++g_gameThread;Check(!Install(context)&&Status()==Uninstalled,"wrong thread cannot install");
    Setup();auto wrong=context;wrong.base+=16;Check(!Install(wrong)&&Status()==Uninstalled,"foreign base cannot install");

    Setup();testMemoryType=MEM_PRIVATE;Check(!Install(context)&&At<uintptr_t>(kBirthSlot)==g_base+kBirth,"MEM_PRIVATE slot rejected");
    Setup();testForeignAllocation=true;Check(!Install(context)&&At<uintptr_t>(kBirthSlot)==g_base+kBirth,"foreign image allocation rejected");
    Setup();testQuery=&ReservedQuery;Check(!Install(context)&&At<uintptr_t>(kBirthSlot)==g_base+kBirth,"uncommitted slot rejected");
    Setup();installedBase=g_base;MEMORY_BASIC_INFORMATION mbi{};
    Check(!SlotLocation(kBirthSlot+1,mbi)&&!Swap(kBirthSlot+1,g_base+kBirth,0),"unaligned/unrecognized slot cannot mutate");
    ++installedBase;Check(!SlotLocation(kBirthSlot,mbi),"misaligned image base rejected");
    for(unsigned mode=1;mode<=7;++mode){
        Setup();DWORD old=0;VirtualProtect(reinterpret_cast<void*>(g_base+kBirthSlot),8,PAGE_READONLY,&old);
        protectMode=mode;testProtect=&FailingProtect;
        Check(!Install(context)&&Status()==Fault,"protection failure fails observer install");
        MEMORY_BASIC_INFORMATION after{};VirtualQuery(reinterpret_cast<void*>(g_base+kBirthSlot),&after,sizeof(after));
        Check(after.Protect==PAGE_READONLY,"read-only protection best-effort restored across uncertain failure outcomes");
        if(mode==5){
            Check(At<uintptr_t>(kBirthSlot)==reinterpret_cast<uintptr_t>(&BirthHook),"unrecoverable read-only hook never receives unsafe rollback CAS");
            Constructor(g_base+Actor);Check(birthCalls==1,"already published wrapper remains safely forwardable after failed rollback");
        }else if(mode==6||mode==7)
            Check(At<uintptr_t>(kBirthSlot)==g_base+0x1234,"rollback preserves foreign pointer after own install or CAS conflict");
        else Check(At<uintptr_t>(kBirthSlot)==g_base+kBirth,"recoverable failed install removes only owned wrapper");
    }

    // All occupied pinned watches block further adoption rather than evict receipts.
    Setup();Adopt();
    for(unsigned i=0;i<kCapacity;++i)watches[i]={g_base+0x1000+i*16,++nextSerial,1,true};
    Check(!ObserveCurrent(context)&&Status()==Fault,"full pinned watch table fails closed");
    for(const auto& w:watches)Check(w.pins==1&&w.alive,"capacity failure preserves existing watches");
    Setup();g=Adopt();Pin(g);for(unsigned i=1;i<kCapacity;++i)watches[i]={g_base+0x1000+i*16,++nextSerial,0,true};
    SwitchCurrent(Second,Pool+632);m=ObserveCurrent(context);
    Check(m>g&&FindLocked(g)&&FindLocked(g)->pins==1,"eviction chooses unpinned record and retains old lease");
    Setup();Adopt();nextSerial=UINT64_MAX;Constructor(context.player);
    Check(!ObserveCurrent(context)&&Status()==Fault,"serial exhaustion never wraps");
    Setup();g=Adopt();FindLocked(g)->pins=UINT_MAX;
    Check(!Pin(g)&&Status()==Fault,"reference counter overflow faults");
    Setup();g=Adopt();Check(!IsRetired(0)&&!IsRetired(g+1)&&!Pin(0)&&!Resolve(g+1),"never-issued tokens rejected");

    // Directly exercise every pinned original byte, without running game code.
    Setup();installedBase=g_base;Check(CodeReady(),"all original complete bodies accepted");
    for(const auto& p:kPins)for(SIZE_T i=0;i<p.count;++i){
        BYTE& b=At<BYTE>(p.rva+i);b^=1;
        Check(!CodeReady(),"any original-body byte drift rejected");b^=1;
    }
    Check(CodeReady(),"all original code restored in fixture");
    printf("ActorLifetimeTests: %u checks, %u failures\n",checks,failures);
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
#endif
