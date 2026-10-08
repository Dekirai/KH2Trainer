#define KH2DEV_PAYLOAD_TESTS
#define KH2_ACTOR_LIFETIME_TESTS
#define KH2_COMBAT_GUARD_TESTS
#include "../../src/KH2Trainer.Bridge/TrainerBridge.cpp"
#include <cstdio>
#include <limits>

namespace {
constexpr uintptr_t Actor=0x110000, EnemyActor=0x114000, EnemyStatus=0x118000;
constexpr uintptr_t ObjectTable=0x120000, Pad=0x124000, Pool=0x2A17290;
constexpr intptr_t SoraResult=0x1234567887654321LL,MickeyResult=0x2345678998765432LL;
unsigned checks=0,failures=0,forwardCalls=0,birthCalls=0,deathCalls=0;
unsigned protectMode=0,protectCalls=0;
bool raiseNative=false;
struct Call { uintptr_t descriptor,actor; int delta; unsigned bar; BYTE effects; bool mickey; } last{};
SharedState state{};
void Check(bool ok,const char* name) { ++checks;if(!ok){++failures;std::printf("FAIL: %s\n",name);} }
uint32_t Packed(uintptr_t p) {
    if(!p)return 0;
    const uintptr_t high=p&~uintptr_t(0x1ffffff);
    for(unsigned i=1;i<64;++i) {
        auto& base=At<uintptr_t>(0x2B0D720+i*8);
        if(!base||base==high) { base=high;return 0x80000000u|(i<<25)|static_cast<uint32_t>(p&0x1ffffff); }
    }
    abort();
}
TrainerContext Context() { return {g_base,g_base+Actor,g_base+Pool,true}; }
intptr_t Record(bool mickey,uintptr_t descriptor,uintptr_t actor,int delta,unsigned bar,BYTE effects) {
    ++forwardCalls;last={descriptor,actor,delta,bar,effects,mickey};
    if(raiseNative)RaiseException(0xE0437771,0,0,nullptr);
    return mickey?MickeyResult:SoraResult;
}
intptr_t __fastcall FakeSora(uintptr_t d,uintptr_t a,int n,unsigned b,BYTE e) { return Record(false,d,a,n,b,e); }
intptr_t __fastcall FakeMickey(uintptr_t d,uintptr_t a,int n,unsigned b,BYTE e) { return Record(true,d,a,n,b,e); }
void __fastcall FakeBirth(uintptr_t,uintptr_t) { ++birthCalls; }
uintptr_t __fastcall FakeDeath(uintptr_t,uintptr_t) { ++deathCalls;return 0xFEDCBA9876543210ULL; }
void Role(unsigned character,int form) {
    At<uint16_t>(ObjectTable+8+76)=static_cast<uint16_t>(character);
    At<signed char>(ObjectTable+8+87)=static_cast<signed char>(form);
    At<unsigned>(Pool+608)=character;At<int>(Actor+3552)=form;
    At<uint32_t>(Actor)=Packed(g_base+(character==4?combat::MickeyDescriptor:combat::SoraDescriptor));
    At<unsigned>(Actor+1736)=character==4?0x2000080:0x1000080;
}
void Setup(unsigned character=1,int form=0) {
    DWORD old=0;
    Check(VirtualProtect(reinterpret_cast<void*>(g_base),kImageSize,PAGE_READWRITE,&old)!=FALSE,"fixture pages writable");
    memset(reinterpret_cast<void*>(g_base),0,kImageSize);ZeroMemory(&state,sizeof(state));
    g_shared=&state;g_disabled=0;g_hostExpired=false;g_gameThread=GetCurrentThreadId();state.hostHeartbeat=GetTickCount();
    g_collision={};g_bookmarkValid=false;g_bookmarkGeneration=0;memset(g_playerEffects,0,sizeof(g_playerEffects));
    combat::guard={};combat::guardHookState=combat::GuardUninstalled;combat::guardBase=0;
    combat::originalSoraDamage=combat::originalMickeyDamage=nullptr;
    combat::blockedHits=0;combat::lastBlockedDamage=0;combat::testSoraDamage=FakeSora;combat::testMickeyDamage=FakeMickey;
    combat::testGuardPin=true;combat::testGuardQuery=VirtualQuery;combat::testGuardProtect=VirtualProtect;
    combat::testGuardMemoryType=MEM_IMAGE;combat::testGuardForeignAllocation=false;
    memset(actor_lifetime::watches,0,sizeof(actor_lifetime::watches));
    actor_lifetime::observerStatus=actor_lifetime::Uninstalled;actor_lifetime::installedBase=0;
    actor_lifetime::bridgeInstance=actor_lifetime::nextSerial=0;
    actor_lifetime::originalBirth=nullptr;actor_lifetime::originalSoraDeath=actor_lifetime::originalMickeyDeath=nullptr;
    actor_lifetime::testBirth=FakeBirth;actor_lifetime::testSoraDeath=actor_lifetime::testMickeyDeath=FakeDeath;
    actor_lifetime::testPin=actor_lifetime::testRandom=true;actor_lifetime::testSwapFailure=-1;
    actor_lifetime::testSwapCalls=0;actor_lifetime::testReturnOverride=0;
    actor_lifetime::testQuery=VirtualQuery;actor_lifetime::testProtect=VirtualProtect;
    actor_lifetime::testMemoryType=MEM_IMAGE;actor_lifetime::testForeignAllocation=actor_lifetime::testNotifyFault=false;
    forwardCalls=birthCalls=deathCalls=protectMode=protectCalls=0;raiseNative=false;last={};
    for(const auto& p:gameplay_state::pins)memcpy(reinterpret_cast<void*>(g_base+p.rva),p.bytes,p.size);
    for(const auto& p:actor_lifetime::kPins)memcpy(reinterpret_cast<void*>(g_base+p.rva),p.bytes,p.count);
    for(const auto& p:combat::kCombatGuardPins)memcpy(reinterpret_cast<void*>(g_base+p.rva),p.bytes,p.size);
    At<uintptr_t>(actor_lifetime::kActionTable)=g_base+actor_lifetime::kAction;
    At<uintptr_t>(actor_lifetime::kAction)=g_base+actor_lifetime::kActionVtable;
    At<uintptr_t>(combat::SoraDescriptor)=g_base+combat::SoraTable;
    At<uintptr_t>(combat::MickeyDescriptor)=g_base+combat::MickeyTable;
    At<uintptr_t>(actor_lifetime::kBirthSlot)=g_base+actor_lifetime::kBirth;
    At<uintptr_t>(actor_lifetime::kSoraSlot)=g_base+actor_lifetime::kSoraDeath;
    At<uintptr_t>(actor_lifetime::kMickeySlot)=g_base+actor_lifetime::kMickeyDeath;
    At<uintptr_t>(combat::SoraDamageSlot)=g_base+combat::SoraDamage;
    At<uintptr_t>(combat::MickeyDamageSlot)=g_base+combat::MickeyDamage;
    At<uintptr_t>(combat::SoraTable+120)=g_base+0x404C50;
    At<uintptr_t>(combat::MickeyTable+120)=g_base+0x415280;
    At<uintptr_t>(0x5CBA28+24)=g_base+0x404A30;At<uintptr_t>(0x5D15A0+24)=g_base+0x4150D0;
    At<uintptr_t>(0x2A10620)=g_base+0x5C4C68;
    At<uintptr_t>(0x5C4C68+16)=g_base+0x3F29E0;At<uintptr_t>(0x5C4C68+24)=g_base+0x3F2470;
    At<uintptr_t>(0x2A105D0)=g_base+Actor;At<uintptr_t>(0x2A171C8)=g_base+Actor;
    At<uintptr_t>(0x2A25030)=g_base+ObjectTable;At<int>(ObjectTable+4)=1;
    At<uint32_t>(Actor+8)=Packed(g_base+ObjectTable+8);At<uintptr_t>(Actor+1472)=g_base+Pool;
    At<uint32_t>(Pool+616)=Packed(g_base+Actor);At<int>(Pool+612)=1;
    At<int>(Pool)=100;At<int>(Pool+4)=255;At<int>(Pool+384)=25;At<int>(Pool+388)=100;
    At<int>(0x2A23950)=79;for(int i=0;i<79;++i)At<int>(0x2A23810+4*i)=i+1;
    At<unsigned>(Actor+2488)=0x80;At<uintptr_t>(Actor+3512)=g_base+Pad;
    At<uintptr_t>(Actor+3520)=g_base+0x2A10620;At<uintptr_t>(Actor+3536)=g_base+0x2A10620;
    At<uintptr_t>(0x2A10620+2784)=g_base+Actor;At<uintptr_t>(0x2A10620+3128)=g_base+Actor;
    At<uintptr_t>(0x2A10620+2792)=g_base+Pad;At<uintptr_t>(0xABCFE8)=g_base+Actor;
    At<BYTE>(0x9BA8D0)=1;At<int>(0x716884)=1;At<int>(0x2B0D920)=-2;
    At<uintptr_t>(0x716868)=g_base+0x130000;At<uintptr_t>(0x9BA888)=g_base+0x130000;
    At<uintptr_t>(0x9BA920)=g_base+0x132000;At<uintptr_t>(0x2A25370)=g_base+0x134000;
    Role(character,form);
    Check(actor_lifetime::Install(Context())&&actor_lifetime::ObserveCurrent(Context())!=0,"real lifetime and role fixture ready");
}
TrainerResult Command(unsigned slot,double value=0) {
    const double args[8]{value};TrainerResult result{};
    Check(CombatHandle(Context(),slot,args,result),"combat command routed");
    return result;
}
uint64_t Generation() { return actor_lifetime::ObserveCurrent(Context()); }
unsigned Pins(uint64_t generation) { const auto w=actor_lifetime::FindLocked(generation);return w?w->pins:0; }
bool Active(bool expected) { return combat::guard.enabled==expected; }
bool Activate() { return Command(106,1).code==0; }
intptr_t Hit(int delta=-10,unsigned bar=0,BYTE effects=1) {
    const bool mickey=At<unsigned>(Pool+608)==4;
    const uintptr_t descriptor=g_base+(mickey?combat::MickeyDescriptor:combat::SoraDescriptor);
    auto wrapper=mickey?&combat::MickeyDamageHook:&combat::SoraDamageHook;
    return wrapper(descriptor,g_base+Actor,delta,bar,effects);
}
void Constructor() {
    actor_lifetime::testReturnOverride=g_base+actor_lifetime::kBirthReturn;
    actor_lifetime::BirthHook(g_base+actor_lifetime::kAction,g_base+Actor);
    actor_lifetime::testReturnOverride=0;
}
bool RaisingHit() {
    __try { Hit(10,7,0xED); }
    __except(GetExceptionCode()==0xE0437771?EXCEPTION_EXECUTE_HANDLER:EXCEPTION_CONTINUE_SEARCH) { return true; }
    return false;
}
SIZE_T WINAPI RaisingQuery(LPCVOID,PMEMORY_BASIC_INFORMATION,SIZE_T) {
    RaiseException(0xE0437772,0,0,nullptr);return 0;
}
bool RaisingNegativeHit() {
    __try { Hit(-20,0,0xDB); }
    __except(GetExceptionCode()==0xE0437771?EXCEPTION_EXECUTE_HANDLER:EXCEPTION_CONTINUE_SEARCH) { return true; }
    return false;
}
void RolesAndAbi() {
    for(unsigned character:{1u,14u,4u})for(int index=0;index<(character==1?7:character==14?2:1);++index) {
        Setup(character,character==1?index:character==14?index*10:11);
        Check(PlayerHealthControlReady(Context()),"actual controlled player admission");
        Check(Activate()&&Pins(Generation())==1,"all audited roles/forms acquire one guard pin");
        const bool mickey=character==4;const auto original=mickey?MickeyResult:SoraResult;
        const uintptr_t slot=mickey?combat::MickeyDamageSlot:combat::SoraDamageSlot;
        auto callback=reinterpret_cast<combat::DamageFn>(At<uintptr_t>(slot));
        Check(callback(g_base+(mickey?combat::MickeyDescriptor:combat::SoraDescriptor),g_base+Actor,-20,0,0xA7)==100&&
            !forwardCalls&&At<int>(Pool)==100,"actual installed derived slot blocks negative HP without native call or HP write");
        Check(Hit(INT_MIN)==100&&combat::lastBlockedDamage==2147483648u,"INT_MIN diagnostic magnitude uses wider arithmetic");
        for(int delta:{-10,0,10})for(unsigned bar:{0u,1u,UINT_MAX}) {
            const unsigned before=forwardCalls;const auto result=Hit(delta,bar,0xE7);
            if(delta<0&&bar==0)Check(result==100&&before==forwardCalls,"only negative HP is blocked");
            else Check(result==original&&forwardCalls==before+1&&last.delta==delta&&last.bar==bar&&
                last.effects==0xE7&&last.mickey==mickey&&last.actor==g_base+Actor&&
                last.descriptor==g_base+(mickey?combat::MickeyDescriptor:combat::SoraDescriptor),
                "original receives all five exact arguments and its full return is preserved");
        }
        combat::blockedHits=9007199254740991ULL;Hit();
        Check(combat::blockedHits==9007199254740991ULL,"snapshot-safe hit count saturates");
        const auto generation=Generation();
        Check(Command(106,0).code==0&&Pins(generation)==0&&
            At<uintptr_t>(combat::SoraDamageSlot)==reinterpret_cast<uintptr_t>(&combat::SoraDamageHook)&&
            At<uintptr_t>(combat::MickeyDamageSlot)==reinterpret_cast<uintptr_t>(&combat::MickeyDamageHook),
            "disable releases lease only and retains transparent resident wrappers");
        Check(Hit()==original,"disabled wrapper forwards");
        raiseNative=true;Check(RaisingHit(),"native exception propagates outside validation catch");raiseNative=false;
    }
    Setup();Check(Activate(),"enemy forwarding fixture");unsigned before=forwardCalls;
    Check(combat::SoraDamageHook(g_base+combat::SoraDescriptor,g_base+EnemyActor,-15,0,0xBC)==SoraResult&&
        forwardCalls==before+1&&last.actor==g_base+EnemyActor,"other Actor forwards without interpreting enemy as player");
    before=forwardCalls;
    Check(combat::MickeyDamageHook(g_base+combat::MickeyDescriptor,g_base+Actor,-7,0,0xAB)==MickeyResult&&
        forwardCalls==before+1,"wrong wrapper/descriptor does not substitute other original");
    const auto generation=Generation();At<uintptr_t>(0x2A10620+36)=1;
    Check(!PlayerHealthControlReady(Context())&&Hit()==100,"hit-induced input lock does not remove existing protection");
    Check(!combat::StartGuard(Context(),55,generation),"input lock rejects a new admission");
    Check(Pins(generation)==1&&combat::guard.owner==0,"rejected admission preserves existing owner/pin");
}
void LifetimeAndPhases() {
    Setup();Check(Activate(),"lifetime fixture");const auto old=Generation();Constructor();
    Check(Hit()==SoraResult&&actor_lifetime::IsRetired(old),"same-address new construction cannot inherit protection");
    CombatTick(Context());Check(!combat::guard.enabled&&!actor_lifetime::FindLocked(old),"retired lease unpinned without Actor write");
    Check(Activate()&&Generation()!=old,"explicit acquire can protect new lifetime");
    const auto deathGeneration=Generation();actor_lifetime::SoraDeathHook(g_base+combat::SoraDescriptor,g_base+Actor);
    Check(Hit()==SoraResult&&deathCalls==1,"observed death forwards and retires protection");
    CombatTick(Context());Check(!actor_lifetime::FindLocked(deathGeneration),"death retirement releases guard pin");
    for(unsigned kind=0;kind<15;++kind) {
        Setup();Check(Activate(),"phase mutation fixture");const auto generation=Generation();
        switch(kind) {
        case 0: state.hostHeartbeat=0;break;
        case 1: state.hostHeartbeat=GetTickCount()-6001;break;
        case 2: state.hostHeartbeat=GetTickCount()+6000;break;
        case 3: At<BYTE>(0x9006B0)=1;break;
        case 4: At<uintptr_t>(0xAC0F48)=g_base+0x1000;break;
        case 5: At<uintptr_t>(0x2A11478)=g_base+0x1000;break;
        case 6: At<uintptr_t>(0x9BA928)=1;break;
        case 7: At<uintptr_t>(0x716868)+=8;break;
        case 8: At<uintptr_t>(0x9BA920)+=8;break;
        case 9: At<BYTE>(0x717009)=1;break;
        case 10: At<int>(Pool)=0;break;
        case 11: At<unsigned>(Actor+2488)|=4;break;
        case 12: At<BYTE>(0x9BA8D0)=0;break;
        case 13: At<uintptr_t>(0x2A105D0)=0;break;
        case 14: g_disabled=1;break;
        }
        const auto hp=At<int>(Pool);
        Check(Hit()==SoraResult&&At<int>(Pool)==hp,"unavailable/changed/defeated context forwards without HP writes");
        CombatTick(Context());Check(!combat::guard.enabled&&Pins(generation)==0,"unsafe phase drops guard policy and pin");
    }
    Setup();Check(Activate(),"field-pause fixture");At<int>(0x716884)=2;CombatTick(Context());
    Check(combat::guard.enabled&&Hit()==SoraResult,"field pause retains policy but forwards callbacks");
    At<int>(0x716884)=1;Check(Hit()==100,"resumed field step regains policy");
    Setup();Check(Activate(),"coherent form-change fixture");const auto generation=Generation();Role(1,5);
    Check(Hit()==SoraResult,"different form/model identity cannot inherit guard");CombatTick(Context());
    Check(!combat::guard.enabled&&Pins(generation)==0,"same-lifetime form change releases old guard");
    Setup();Check(Activate(),"foreign thread fixture");const auto thread=g_gameThread;g_gameThread++;
    Check(Hit()==SoraResult&&actor_lifetime::Status()==actor_lifetime::Observing,
        "foreign callback thread forwards before touching lifetime/lease validation");g_gameThread=thread;
    Setup();Check(Activate(),"unknown role fixture");At<unsigned>(Pool+608)=14;
    Check(Hit()==SoraResult,"mismatched object/status role forwards");CombatTick(Context());Check(!combat::guard.enabled,"unknown role drops protection");
    Setup();Check(Activate(),"observer fault fixture");const auto faultGeneration=Generation();
    At<uintptr_t>(actor_lifetime::kBirthSlot)=g_base+actor_lifetime::kBirth;
    Check(Hit()==SoraResult&&actor_lifetime::Status()==actor_lifetime::Fault,"observer loss forwards");
    CombatTick(Context());Check(!combat::guard.enabled&&Pins(faultGeneration)==0,"fault releases read-only guard lease without game-field restore");
    Setup();Check(Activate(),"validation exception fixture");combat::guard.status=1;
    Check(Hit()==SoraResult&&forwardCalls==1,"bad validation memory does not suppress native forwarding");
    Setup();Check(Activate(),"metadata SEH fixture");combat::testGuardQuery=RaisingQuery;
    Check(Hit(-20,0,0xAB)==SoraResult&&forwardCalls==1&&last.effects==0xAB,
        "metadata SEH fails open to exactly one native original");
    raiseNative=true;Check(RaisingNegativeHit()&&forwardCalls==2,
        "native exception is not swallowed even after metadata validation exception");raiseNative=false;
}
void OwnerArgs(double args[8],bool enable,uint64_t owner,uint64_t bridge,uint64_t generation) {
    memset(args,0,8*sizeof(double));args[0]=enable?1:0;
    args[1]=static_cast<uint32_t>(owner);args[2]=static_cast<uint32_t>(owner>>32);
    args[3]=static_cast<uint32_t>(bridge);args[4]=static_cast<uint32_t>(bridge>>32);
    args[5]=static_cast<uint32_t>(generation);args[6]=static_cast<uint32_t>(generation>>32);
}
TrainerResult Owned(const double args[8]) {
    TrainerResult r{};Check(CombatHandle(Context(),472,args,r),"owned command routes through CombatHandle");return r;
}
void OwnersAndIpc() {
    Setup();const auto generation=Generation(),bridge=actor_lifetime::BridgeInstance();
    constexpr uint64_t owner=0xFEDCBA9876543210ULL,other=0x123456789ABCDEFFULL;
    double args[8];OwnerArgs(args,true,owner,bridge,generation);
    Check(!Owned(args).code&&combat::guard.owner==owner&&Pins(generation)==1,"exact uint64 owner acquires");
    Check(!Owned(args).code&&Pins(generation)==1,"same owner ensure is idempotent");
    CombatCapabilities();CombatSnapshot(Context());
    Check(state.values[106]==1&&state.values[473]==static_cast<uint32_t>(owner)&&
        state.values[474]==static_cast<uint32_t>(owner>>32),"effective guard and exact owner halves published");
    OwnerArgs(args,true,other,bridge,generation);Check(Owned(args).code&&combat::guard.owner==owner,"different CC owner cannot steal active guard");
    OwnerArgs(args,false,other,bridge,generation);Check(!Owned(args).code&&combat::guard.enabled,"other owner release is harmless acknowledgement");
    OwnerArgs(args,false,owner,bridge+1,generation);Check(Owned(args).code&&combat::guard.enabled,"foreign bridge release rejected");
    OwnerArgs(args,false,owner,bridge,generation+1);Check(!Owned(args).code&&combat::guard.enabled,"stale generation release preserves policy");
    Check(Activate()&&combat::guard.owner==0&&Pins(generation)==1,"manual activation takes over with balanced pin");
    OwnerArgs(args,false,owner,bridge,generation);Check(!Owned(args).code&&combat::guard.enabled&&combat::guard.owner==0,"delayed CC cleanup preserves manual takeover");
    Command(106,0);OwnerArgs(args,true,owner,bridge,generation+1);
    Check(Owned(args).code&&!combat::guard.enabled,"stale requested generation cannot acquire");
    OwnerArgs(args,true,owner,bridge,generation);Check(!Owned(args).code,"owner reacquire after explicit manual disable");
    OwnerArgs(args,false,owner,bridge,generation);Check(!Owned(args).code&&!combat::guard.enabled&&Pins(generation)==0,"matching owner cleanup releases exactly one pin");
    for(unsigned index=0;index<8;++index)for(double bad:{-1.0,0.5,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}) {
        OwnerArgs(args,true,owner,bridge,generation);args[index]=bad;
        Check(Owned(args).code&&!combat::guard.enabled,"malformed owned command fails closed");
    }
    OwnerArgs(args,true,0,bridge,generation);Check(Owned(args).code,"zero owner rejected");
    OwnerArgs(args,true,owner,0,generation);Check(Owned(args).code,"zero bridge rejected");
    OwnerArgs(args,true,owner,bridge,0);Check(Owned(args).code,"zero acquire generation rejected");
    // Actual common command1472 dispatch, seqlock snapshot and stale owner release.
    OwnerArgs(args,true,owner,bridge,generation);
    state.commandId=1472;state.commandIssuedAt=GetTickCount();state.hostHeartbeat=GetTickCount();
    memcpy(state.arguments,args,sizeof(args));++state.requestSequence;TrainerFrame();
    Check(state.responseSequence==state.requestSequence&&!state.resultCode&&combat::guard.owner==owner&&
        state.values[106]==1&&!(state.snapshotSequence&1),"actual TrainerFrame routes owned acquire and publishes coherent snapshot");
    Check(Activate()&&combat::guard.owner==0,"manual takeover after IPC acquire");
    OwnerArgs(args,false,owner,bridge,generation);memcpy(state.arguments,args,sizeof(args));
    state.commandIssuedAt=GetTickCount();++state.requestSequence;TrainerFrame();
    Check(state.responseSequence==state.requestSequence&&!state.resultCode&&combat::guard.enabled&&combat::guard.owner==0,
        "actual stale CC release cannot remove manual guard");
    state.hostHeartbeat=GetTickCount()-6001;TrainerFrame();
    Check(!combat::guard.enabled&&Pins(generation)==0,"actual expired-host frame drops guard lease");
}
SIZE_T WINAPI NoQuery(LPCVOID,PMEMORY_BASIC_INFORMATION,SIZE_T) { return 0; }
SIZE_T WINAPI ReservedQuery(LPCVOID p,PMEMORY_BASIC_INFORMATION m,SIZE_T n) {
    auto result=VirtualQuery(p,m,n);if(result)m->State=MEM_RESERVE;return result;
}
BOOL WINAPI FaultProtect(LPVOID p,SIZE_T n,DWORD desired,PDWORD old) {
    ++protectCalls;
    if((protectMode==1||protectMode==2)&&protectCalls==1) {
        if(protectMode==2)VirtualProtect(p,n,desired,old);return FALSE;
    }
    if(protectCalls==2&&(protectMode==3||protectMode==4||protectMode==5||protectMode==6)) {
        if(protectMode>=4)VirtualProtect(p,n,desired,old);
        if(protectMode==6) {
            DWORD previous=0,unused=0;VirtualProtect(p,n,PAGE_READWRITE,&previous);
            *static_cast<uintptr_t*>(p)=g_base+0x1234;VirtualProtect(p,n,previous,&unused);
        }
        return FALSE;
    }
    if(protectMode==5&&protectCalls>=3&&desired==PAGE_READWRITE)return FALSE;
    if(protectMode==7&&protectCalls==1) {
        const auto ok=VirtualProtect(p,n,desired,old);*static_cast<uintptr_t*>(p)=g_base+0x1234;return ok;
    }
    if(protectMode==8&&protectCalls==3)return FALSE; // Second slot installation, first slot already published.
    return VirtualProtect(p,n,desired,old);
}
void PinsTablesProtection() {
    Setup();combat::guardBase=g_base;Check(combat::GuardCodeReady(),"complete original pins valid");
    for(const auto& p:combat::kCombatGuardPins)for(SIZE_T i=0;i<p.size;++i) {
        At<BYTE>(p.rva+i)^=1;Check(!combat::GuardCodeReady(),"every original pin byte is checked");At<BYTE>(p.rva+i)^=1;
    }
    Check(combat::GuardCodeReady(),"all pins restored");
    for(unsigned which=0;which<2;++which) {
        Setup();const uintptr_t descriptor=which?combat::MickeyDescriptor:combat::SoraDescriptor;
        At<uintptr_t>(descriptor)+=8;Check(!combat::InstallGuardHooks(),"both descriptor tables checked");
        Setup();const uintptr_t slot=which?combat::MickeyDamageSlot:combat::SoraDamageSlot;
        At<uintptr_t>(slot)=g_base+0x1234;Check(!combat::InstallGuardHooks()&&At<uintptr_t>(slot)==g_base+0x1234,"foreign initial slot preserved");
        Setup();Check(Activate(),"slot takeover fixture");const auto generation=Generation();
        At<uintptr_t>(slot)=g_base+0x1234;Check(Hit()==SoraResult,"slot loss forwards rather than protecting");
        CombatTick(Context());Check(!combat::guard.enabled&&Pins(generation)==0&&At<uintptr_t>(slot)==g_base+0x1234,"foreign installed slot preserved after cleanup");
    }
    Setup();combat::testGuardPin=false;Check(!combat::InstallGuardHooks(),"module pin failure prevents publication");
    Setup();combat::testMickeyDamage=nullptr;Check(!combat::InstallGuardHooks(),"null original prevents either publication");
    Setup();combat::testGuardMemoryType=MEM_PRIVATE;Check(!combat::InstallGuardHooks(),"non-image slot rejected");
    Setup();combat::testGuardForeignAllocation=true;Check(!combat::InstallGuardHooks(),"foreign image allocation rejected");
    Setup();combat::testGuardQuery=NoQuery;Check(!combat::InstallGuardHooks(),"unqueryable slot rejected");
    Setup();combat::testGuardQuery=ReservedQuery;Check(!combat::InstallGuardHooks(),"uncommitted slot rejected");
    Setup();combat::guardBase=g_base;MEMORY_BASIC_INFORMATION m{};
    Check(!combat::GuardSlotLocation(combat::SoraDamageSlot+1,m),"unknown or unaligned slot rejected");
    combat::guardBase++;Check(!combat::GuardSlotLocation(combat::SoraDamageSlot,m),"misaligned image base rejected");
    for(unsigned mode=1;mode<=8;++mode) {
        Setup();DWORD old=0;VirtualProtect(reinterpret_cast<void*>(g_base+combat::SoraDamageSlot),8,PAGE_READONLY,&old);
        protectMode=mode;combat::testGuardProtect=FaultProtect;
        Check(!combat::InstallGuardHooks()&&combat::guardHookState==combat::GuardFault,"uncertain protection failure faults installation");
        VirtualQuery(reinterpret_cast<void*>(g_base+combat::SoraDamageSlot),&m,sizeof(m));
        Check(m.Protect==PAGE_READONLY,"protection rollback queries and restores actual page state");
        if(mode==5) Check(At<uintptr_t>(combat::SoraDamageSlot)==reinterpret_cast<uintptr_t>(&combat::SoraDamageHook),
            "unrecoverable readonly wrapper is not written through readonly memory");
        else if(mode==6||mode==7) Check(At<uintptr_t>(combat::SoraDamageSlot)==g_base+0x1234,"rollback preserves foreign slot");
        else Check(At<uintptr_t>(combat::SoraDamageSlot)==g_base+combat::SoraDamage,"recoverable failure removes only own wrapper");
        Check(combat::SoraDamageHook(g_base+combat::SoraDescriptor,g_base+Actor,-3,0,0xBA)==SoraResult&&forwardCalls==1,
            "immutable original forwards after partial/faulted installation");
    }
}
void Enemy() {
    At<uintptr_t>(Actor+3528)=g_base+combat::LockRva;At<uintptr_t>(combat::LockRva+56)=g_base+Actor;
    At<int>(combat::LockRva)=2;At<uint32_t>(combat::LockRva+4)=Packed(g_base+EnemyActor);
    At<uint32_t>(combat::LockRva+12)=0;At<uint32_t>(Actor+2704)=Packed(g_base+EnemyActor);
    At<uint32_t>(EnemyActor+2704)=0;At<uint32_t>(EnemyActor+1736)=0x12;
    At<uint32_t>(EnemyActor+288)=At<uint32_t>(EnemyActor+2488)=0;
    At<uintptr_t>(EnemyActor+1472)=g_base+EnemyStatus;At<uint32_t>(EnemyStatus+616)=Packed(g_base+EnemyActor);
    At<int>(EnemyStatus)=80;At<int>(EnemyStatus+4)=500;At<int>(EnemyStatus+8)=0;
    At<uint32_t>(EnemyStatus+592)=At<uint32_t>(EnemyStatus+620)=0;
    At<float>(EnemyActor+3400)=17;At<float>(EnemyActor+3404)=100;
}
void TargetRegression() {
    Setup();Enemy();CombatSnapshot(Context());
    Check(state.values[98]==80&&state.values[99]==500&&state.values[100]==17&&state.values[101]==100,"validated target snapshot retained");
    At<int>(0x716884)=2;CombatSnapshot(Context());Check(state.values[98]==80&&Command(102).code,"pause allows display but not target mutation");
    At<int>(0x716884)=1;
    Check(!Command(102).code&&At<int>(EnemyStatus)==500,"refill living target");
    Check(!Command(110,1).code&&At<int>(EnemyStatus)==1,"target HP remains nonlethal");
    for(double bad:{0.,501.,1.5})Check(Command(110,bad).code,"target HP bounds retained");
    At<int>(EnemyStatus+8)=100;Check(Command(110,99).code&&!Command(110,100).code,"native target floor respected");
    At<int>(EnemyStatus+8)=501;Check(Command(102).code,"corrupt target floor rejected");Enemy();
    Check(!Command(103).code&&At<float>(EnemyActor+3400)==0&&At<float>(EnemyActor+3404)==100,"revenge reset preserves threshold");
    Check(!Command(104,99.5).code&&At<float>(EnemyActor+3400)==99.5f,"fractional revenge supported");
    for(double bad:{-1.,1000001.,std::numeric_limits<double>::infinity()})Check(Command(104,bad).code,"invalid revenge rejected");
    for(unsigned kind=0;kind<12;++kind) {
        Enemy();
        switch(kind) {
        case 0: At<int>(combat::LockRva)=1;break;
        case 1: At<uintptr_t>(0x2A171C8)=0;break;
        case 2: At<uint32_t>(EnemyActor+2704)=Packed(g_base+EnemyActor);break;
        case 3: At<uint32_t>(EnemyActor+2704)=Packed(g_base+kImageSize+0x1000);break;
        case 4: At<uint32_t>(EnemyActor+1736)=2;break;
        case 5: At<uint32_t>(EnemyActor+2488)=4;break;
        case 6: At<int>(EnemyStatus)=0;break;
        case 7: At<uint32_t>(EnemyStatus+616)=Packed(g_base+Actor);break;
        case 8: At<uint32_t>(EnemyStatus+620)=1;break;
        case 9: At<uintptr_t>(combat::LockRva+56)=0;break;
        case 10: At<uint32_t>(combat::LockRva+12)=1;break;
        case 11: At<uint32_t>(EnemyActor+288)=0x80000;break;
        }
        Check(Command(102).code,"target ownership and complete-list guards retained");At<uintptr_t>(0x2A171C8)=g_base+Actor;
    }
    Enemy();At<float>(EnemyActor+3400)=std::numeric_limits<float>::quiet_NaN();Check(Command(103).code,"NaN target revenge rejected");
    const double args[8]{};TrainerResult r{};
    Check(!CombatHandle(Context(),109,args,r)&&!CombatHandle(Context(),111,args,r),"unclaimed slots stay unclaimed");
}
// Joint regression: actual gameplay, movement, role and Actor-lifetime code in a
// private image. Native callback forwarding uses the existing fixture doubles.
uint64_t movementOperation=0;
void SetupMovement(unsigned character=1) {
    Setup(character,character==4?11:0);
    for(auto& l:movement_tx::leases)l={};
    for(auto& r:movement_tx::receipts)r={};
    movement_tx::nextLease=0;movementOperation=0;
    At<uintptr_t>(Actor+360)=g_base+Actor;
    const BYTE normal[]={0x48,0x8B,0xCA,0xE9,0xE8,0x3F,0xFA,0xFF};
    const BYTE mickey[]={0x48,0x8B,0xCA,0xE9,0xB8,0x3A,0xF9,0xFF};
    memcpy(reinterpret_cast<void*>(g_base+0x404FB0),normal,sizeof(normal));
    memcpy(reinterpret_cast<void*>(g_base+0x4154E0),mickey,sizeof(mickey));
    At<uintptr_t>(0x5CBA28+296)=g_base+0x404FB0;
    At<uintptr_t>(0x5D15A0+296)=g_base+0x4154E0;
    At<float>(Actor+296)=2;At<float>(Actor+300)=8;
    Check(actor_movement::MovementReady(Context()) && gameplay_state::Inspect(Context()).controllable,
        "real movement and gameplay guards admit synthetic supported role");
}
movement_tx::Request MovementAcquire() {
    using namespace movement_tx;
    Request q{};q.magic=Magic;q.schema=Schema;q.size=sizeof(q);q.operation=Operation::Acquire;
    q.clientId=1;q.opId=++movementOperation;q.bridgeInstance=actor_lifetime::BridgeInstance();
    q.actorGeneration=Generation();q.effectOwnerId=10;q.mask=3;
    q.expectedBits[0]=Bits(At<float>(Actor+296));q.expectedBits[1]=Bits(At<float>(Actor+300));
    q.desiredBits[0]=Bits(5.f);q.desiredBits[1]=Bits(20.f);return q;
}
movement_tx::Response ApplyMovement() {
    const auto q=MovementAcquire();const auto r=movement_tx::Execute(Context(),q,static_cast<uint32_t>(q.opId));
    Check(r.outcome==movement_tx::Outcome::Applied && r.leaseId && At<float>(Actor+300)==20,
        "joint fixture acquires real movement lease before disconnect");
    return r;
}
void DisconnectedMovementCleanup() {
    using namespace movement_tx;
    for(unsigned character:{1u,14u,4u})for(unsigned heartbeat=0;heartbeat<3;++heartbeat) {
        SetupMovement(character);const auto acquired=ApplyMovement();
        state.hostHeartbeat=heartbeat==0?0:heartbeat==1?GetTickCount()-6001:GetTickCount()+6000;
        Check(!gameplay_state::Inspect(Context()).controllable && gameplay_state::InspectNative(Context()).controllable,
            "missing stale or future heartbeat blocks admission while native controls remain available");
        auto q=MovementAcquire();auto rejected=Execute(Context(),q,static_cast<uint32_t>(q.opId));
        Check(rejected.outcome==Outcome::Rejected && rejected.reason==Reason::NotReady && At<float>(Actor+300)==20,
            "disconnected Acquire cannot apply through the native cleanup gate");
        q.opId=++movementOperation;q.operation=Operation::Reapply;q.leaseId=acquired.leaseId;q.expectedLeaseRevision=acquired.revision;
        rejected=Execute(Context(),q,static_cast<uint32_t>(q.opId));
        Check(rejected.outcome==Outcome::Rejected && rejected.reason==Reason::NotReady && At<float>(Actor+300)==20,
            "disconnected Reapply cannot extend an existing effect");
        Tick(Context(),true);const auto* lease=FindLease(acquired.leaseId);
        Check(lease && lease->state==State::Released && lease->restored==3 && !lease->pinned &&
            At<float>(Actor+296)==2 && At<float>(Actor+300)==8 && Pins(acquired.actorGeneration)==0,
            "host-expiry tick restores exact originals for Sora Roxas and rescue Mickey without reconnect");
    }
    // Every blocker remains in the same real native-control path during cleanup.
    for(unsigned gate=0;gate<12;++gate) {
        SetupMovement();const auto acquired=ApplyMovement();state.hostHeartbeat=0;
        uintptr_t address=0;uint32_t prior=0;
        switch(gate) {
        case 0: address=0x9006B0;break; // menu
        case 1: address=0x2A11478;break; // event pointer, only presence is read
        case 2: address=0x9BA928;break; // transition
        case 3: address=0xABAC58;break; // loading
        case 4: address=0x2A10500;break; // input lock
        case 5: address=Actor+1612;break; // actor stop
        case 6: address=0xABB854;break; // unknown timer owner
        case 7: address=0x716884;break; // suspended field
        case 8: address=Pool;break; // dead
        case 9: address=0x2A105D0;break; // original actor temporarily not current
        case 10: g_disabled=1;break;
        case 11: ++g_gameThread;break;
        }
        if(address) {prior=At<uint32_t>(address);At<uint32_t>(address)=gate==6?4:gate==7?2:gate==8||gate==9?0:1;}
        Tick(Context(),true);const auto* lease=FindLease(acquired.leaseId);
        Check(lease && !Terminal(lease->state) && At<float>(Actor+296)==5 && At<float>(Actor+300)==20,
            "native blocker defers disconnected cleanup without altering either field");
        if(address)At<uint32_t>(address)=prior;g_disabled=0;g_gameThread=GetCurrentThreadId();
        Tick(Context(),true);lease=FindLease(acquired.leaseId);
        Check(lease && lease->state==State::Released && At<float>(Actor+296)==2 && At<float>(Actor+300)==8,
            "clearing native blocker completes pending release without heartbeat recovery");
    }
    SetupMovement();auto acquired=ApplyMovement();state.hostHeartbeat=0;At<float>(Actor+296)=11;
    Tick(Context(),true);auto* lease=FindLease(acquired.leaseId);
    Check(lease && lease->state==State::Superseded && lease->superseded==1 && lease->restored==2 &&
        At<float>(Actor+296)==11 && At<float>(Actor+300)==8,"disconnected cleanup preserves external field replacement");
    SetupMovement();acquired=ApplyMovement();state.hostHeartbeat=0;
    actor_lifetime::SoraDeathHook(g_base+combat::SoraDescriptor,g_base+Actor);Tick(Context(),true);lease=FindLease(acquired.leaseId);
    Check(lease && lease->state==State::Destroyed && At<float>(Actor+300)==20,
        "observed Actor death discards cleanup intent without writing the old allocation");
}
}
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,kImageSize,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    if(!g_base)return 2;
    RolesAndAbi();LifetimeAndPhases();OwnersAndIpc();PinsTablesProtection();TargetRegression();DisconnectedMovementCleanup();
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);
    std::printf("CombatGuardTests: %u checks, %u failures. Synthetic memory; no game code executed.\n",checks,failures);
    return failures?1:0;
}
