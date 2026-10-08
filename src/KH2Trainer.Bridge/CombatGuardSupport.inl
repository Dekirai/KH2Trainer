// Included inside namespace combat. Contract: player-damage-guard-20261007.
// Original callbacks are captured before publication and remain immutable.
#include "CombatGuardPins.inl"
constexpr uintptr_t SoraDescriptor=0x750300,SoraTable=0x5CBA28,SoraDamageSlot=0x5CBB10,SoraDamage=0x404EE0;
constexpr uintptr_t MickeyDescriptor=0x7523B8,MickeyTable=0x5D15A0,MickeyDamageSlot=0x5D1688,MickeyDamage=0x415410;
constexpr unsigned OwnedGuardSlot=472,GuardOwnerLowSlot=473,GuardOwnerHighSlot=474;
using DamageFn=intptr_t (__fastcall*)(uintptr_t,uintptr_t,int,unsigned,BYTE);
enum GuardHookState { GuardUninstalled=0,GuardInstalled=1,GuardFault=2 };
LONG guardHookState=GuardUninstalled;
uintptr_t guardBase=0;
DamageFn originalSoraDamage=nullptr,originalMickeyDamage=nullptr;
struct GuardLease {
    bool enabled=false;
    uintptr_t player=0,status=0,scheduler=0,heap=0,descriptor=0,object=0;
    uint64_t generation=0,owner=0;
    unsigned character=0;
    int form=-1;
    BYTE room[10]{};
} guard;
uint64_t blockedHits=0; unsigned lastBlockedDamage=0;
#ifdef KH2_COMBAT_GUARD_TESTS
DamageFn testSoraDamage=nullptr,testMickeyDamage=nullptr;
bool testGuardPin=true;
SIZE_T (WINAPI* testGuardQuery)(LPCVOID,PMEMORY_BASIC_INFORMATION,SIZE_T)=VirtualQuery;
BOOL (WINAPI* testGuardProtect)(LPVOID,SIZE_T,DWORD,PDWORD)=VirtualProtect;
DWORD testGuardMemoryType=MEM_IMAGE;
bool testGuardForeignAllocation=false;
#endif
intptr_t __fastcall SoraDamageHook(uintptr_t,uintptr_t,int,unsigned,BYTE);
intptr_t __fastcall MickeyDamageHook(uintptr_t,uintptr_t,int,unsigned,BYTE);
bool GuardCodeReady() {
    if(!guardBase || guardBase!=g_base) return false;
    for(const auto& p:kCombatGuardPins)
        if(p.rva>UINTPTR_MAX-guardBase || !Readable(reinterpret_cast<const void*>(guardBase+p.rva),p.size) ||
           memcmp(reinterpret_cast<const void*>(guardBase+p.rva),p.bytes,p.size)) return false;
    return true;
}
bool GuardSlotLocation(uintptr_t rva,MEMORY_BASIC_INFORMATION& m) {
    if(!guardBase || (rva!=SoraDamageSlot && rva!=MickeyDamageSlot) || rva>UINTPTR_MAX-guardBase) return false;
    const uintptr_t p=guardBase+rva;
#ifdef KH2_COMBAT_GUARD_TESTS
    if(!testGuardQuery(reinterpret_cast<void*>(p),&m,sizeof(m))) return false;
    m.Type=testGuardMemoryType;
    if(testGuardForeignAllocation)m.AllocationBase=reinterpret_cast<void*>(guardBase+4096);
#else
    if(!VirtualQuery(reinterpret_cast<void*>(p),&m,sizeof(m))) return false;
#endif
    const uintptr_t region=reinterpret_cast<uintptr_t>(m.BaseAddress);
    return !(p&7) && m.State==MEM_COMMIT && m.Type==MEM_IMAGE &&
        m.AllocationBase==reinterpret_cast<void*>(guardBase) && region<=p &&
        m.RegionSize<=UINTPTR_MAX-region && sizeof(void*)<=UINTPTR_MAX-p && p+sizeof(void*)<=region+m.RegionSize;
}
bool GuardSlotEquals(uintptr_t rva,uintptr_t value) {
    MEMORY_BASIC_INFORMATION m{};
    return GuardSlotLocation(rva,m) && Readable(reinterpret_cast<void*>(guardBase+rva),8) &&
        *reinterpret_cast<const uintptr_t*>(guardBase+rva)==value;
}
bool GuardTablesReady() {
    return Readable(reinterpret_cast<void*>(guardBase+SoraDescriptor),8) &&
        Readable(reinterpret_cast<void*>(guardBase+MickeyDescriptor),8) &&
        At<uintptr_t>(SoraDescriptor)==guardBase+SoraTable && At<uintptr_t>(MickeyDescriptor)==guardBase+MickeyTable;
}
bool GuardHooksReady() {
    if(guardHookState!=GuardInstalled) return false;
    if(guardBase!=g_base || !GuardCodeReady() || !GuardTablesReady() ||
       !GuardSlotEquals(SoraDamageSlot,reinterpret_cast<uintptr_t>(&SoraDamageHook)) ||
       !GuardSlotEquals(MickeyDamageSlot,reinterpret_cast<uintptr_t>(&MickeyDamageHook))) {
        guardHookState=GuardFault; return false;
    }
    return true;
}
bool GuardProtect(uintptr_t rva,DWORD protection,DWORD& previous) {
#ifdef KH2_COMBAT_GUARD_TESTS
    return testGuardProtect(reinterpret_cast<void*>(guardBase+rva),8,protection,&previous)!=FALSE;
#else
    return VirtualProtect(reinterpret_cast<void*>(guardBase+rva),8,protection,&previous)!=FALSE;
#endif
}
bool GuardWritableProtection(DWORD value) {
    if(value&(PAGE_GUARD|PAGE_NOACCESS)) return false;
    const DWORD p=value&0xff;
    return p==PAGE_READWRITE || p==PAGE_WRITECOPY || p==PAGE_EXECUTE_READWRITE || p==PAGE_EXECUTE_WRITECOPY;
}
void GuardRecoverSlot(uintptr_t rva,uintptr_t ours,uintptr_t original,DWORD old) {
    __try {
        MEMORY_BASIC_INFORMATION m{};DWORD unused=0;
        if(!GuardSlotLocation(rva,m)) return;
        if(!GuardWritableProtection(m.Protect)) {
            GuardProtect(rva,PAGE_READWRITE,unused);
            if(!GuardSlotLocation(rva,m)) return;
        }
        if(GuardWritableProtection(m.Protect))
            InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(guardBase+rva),
                reinterpret_cast<void*>(original),reinterpret_cast<void*>(ours));
        GuardProtect(rva,old,unused);
    } __except(EXCEPTION_EXECUTE_HANDLER) { guardHookState=GuardFault; }
}
bool GuardSwapSlot(uintptr_t rva,uintptr_t expected,uintptr_t replacement) {
    MEMORY_BASIC_INFORMATION m{};DWORD old=0,unused=0;bool attempted=false;
    __try {
        if(!GuardSlotLocation(rva,m) || !Readable(reinterpret_cast<void*>(guardBase+rva),8) ||
           *reinterpret_cast<const uintptr_t*>(guardBase+rva)!=expected) return false;
        old=m.Protect;attempted=true;DWORD reported=old;
        if(!GuardProtect(rva,PAGE_READWRITE,reported)) { GuardRecoverSlot(rva,replacement,expected,old);return false; }
        MEMORY_BASIC_INFORMATION now{};
        if(!GuardSlotLocation(rva,now) || !GuardWritableProtection(now.Protect)) {
            GuardRecoverSlot(rva,replacement,expected,old);return false;
        }
        const bool changed=InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(guardBase+rva),
            reinterpret_cast<void*>(replacement),reinterpret_cast<void*>(expected))==reinterpret_cast<void*>(expected);
        const bool restored=GuardProtect(rva,old,unused);
        if(!restored) GuardRecoverSlot(rva,replacement,expected,old);
        return changed && restored;
    } __except(EXCEPTION_EXECUTE_HANDLER) {
        guardHookState=GuardFault;if(attempted)GuardRecoverSlot(rva,replacement,expected,old);return false;
    }
}
bool PinGuardModule() {
#ifdef KH2_COMBAT_GUARD_TESTS
    return testGuardPin;
#else
    HMODULE module=nullptr;
    return GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,
        reinterpret_cast<LPCWSTR>(&SoraDamageHook),&module)!=FALSE;
#endif
}
bool InstallGuardHooks() {
    if(GetCurrentThreadId()!=g_gameThread || !g_base) return false;
    if(guardHookState==GuardInstalled) return GuardHooksReady();
    if(guardHookState==GuardFault) return false;
    guardBase=g_base;
    if(!GuardCodeReady() || !GuardTablesReady() ||
       !GuardSlotEquals(SoraDamageSlot,guardBase+SoraDamage) ||
       !GuardSlotEquals(MickeyDamageSlot,guardBase+MickeyDamage) || !PinGuardModule()) {
        guardHookState=GuardFault;return false;
    }
#ifdef KH2_COMBAT_GUARD_TESTS
    originalSoraDamage=testSoraDamage;originalMickeyDamage=testMickeyDamage;
#else
    originalSoraDamage=reinterpret_cast<DamageFn>(guardBase+SoraDamage);
    originalMickeyDamage=reinterpret_cast<DamageFn>(guardBase+MickeyDamage);
#endif
    if(!originalSoraDamage || !originalMickeyDamage) { guardHookState=GuardFault;return false; }
    if(!GuardSwapSlot(SoraDamageSlot,guardBase+SoraDamage,reinterpret_cast<uintptr_t>(&SoraDamageHook)) ||
       !GuardSwapSlot(MickeyDamageSlot,guardBase+MickeyDamage,reinterpret_cast<uintptr_t>(&MickeyDamageHook))) {
        guardHookState=GuardFault;
        if(GuardSlotEquals(SoraDamageSlot,reinterpret_cast<uintptr_t>(&SoraDamageHook)))
            GuardSwapSlot(SoraDamageSlot,reinterpret_cast<uintptr_t>(&SoraDamageHook),guardBase+SoraDamage);
        if(GuardSlotEquals(MickeyDamageSlot,reinterpret_cast<uintptr_t>(&MickeyDamageHook)))
            GuardSwapSlot(MickeyDamageSlot,reinterpret_cast<uintptr_t>(&MickeyDamageHook),guardBase+MickeyDamage);
        return false;
    }
    guardHookState=GuardInstalled;return GuardHooksReady();
}
void StopGuard() {
    actor_lifetime::Unpin(guard.generation);
    guard={};
    // Keep transparent, module-pinned wrappers. Already dispatched callbacks
    // always have their immutable original target, including after disable/fault.
}
bool SameGuardScene() {
    return guard.scheduler==At<uintptr_t>(0x716868) && guard.heap==At<uintptr_t>(0x9BA920) &&
        !memcmp(guard.room,reinterpret_cast<void*>(g_base+0x717008),sizeof(guard.room));
}
bool GuardContext(const TrainerContext& c,bool allowFieldPause=false) {
    // Hit reactions may block controller input. Do not require full input
    // controllability while deciding whether a damage callback is protected.
    if(!guard.enabled || GetCurrentThreadId()!=g_gameThread || !HostFresh() ||
       !PlayerReady(c,allowFieldPause) || At<uintptr_t>(0x2A11478) ||
       c.player!=guard.player || c.status!=guard.status || !SameGuardScene() || !GuardHooksReady() ||
       actor_lifetime::Resolve(guard.generation)!=c.player || actor_lifetime::ObserveCurrent(c)!=guard.generation) return false;
    const auto role=player_role::Inspect(c);
    return (role.role==player_role::Sora || role.role==player_role::Roxas || role.role==player_role::Mickey) &&
        role.descriptor==guard.descriptor && role.object==guard.object && role.characterId==guard.character && role.form==guard.form;
}
bool MayBlock(uintptr_t expectedDescriptor,uintptr_t descriptor,uintptr_t actor,int delta,unsigned bar,int& hp) {
    if(delta>=0 || bar!=0 || descriptor!=guardBase+expectedDescriptor || descriptor!=guard.descriptor || actor!=guard.player) return false;
    const TrainerContext c{g_base,actor,guard.status,true};
    if(!GuardContext(c)) return false;
    hp=Field<int>(c.status,0);return true;
}
bool BlockDamage(uintptr_t expectedDescriptor,uintptr_t descriptor,uintptr_t actor,int delta,unsigned bar,int& hp) {
    // Other native threads must not inspect mutable update-thread lease state.
    if(GetCurrentThreadId()!=g_gameThread) return false;
    bool block=false;
    __try { block=MayBlock(expectedDescriptor,descriptor,actor,delta,bar,hp); }
    __except(EXCEPTION_EXECUTE_HANDLER) { block=false; }
    if(block) {
        if(blockedHits<9007199254740991ULL) ++blockedHits;
        lastBlockedDamage=static_cast<unsigned>(-static_cast<int64_t>(delta));
    }
    return block;
}
intptr_t __fastcall SoraDamageHook(uintptr_t descriptor,uintptr_t actor,int delta,unsigned bar,BYTE effects) {
    int hp=0;
    if(BlockDamage(SoraDescriptor,descriptor,actor,delta,bar,hp)) return hp;
    return originalSoraDamage(descriptor,actor,delta,bar,effects); // Native exceptions propagate.
}
intptr_t __fastcall MickeyDamageHook(uintptr_t descriptor,uintptr_t actor,int delta,unsigned bar,BYTE effects) {
    int hp=0;
    if(BlockDamage(MickeyDescriptor,descriptor,actor,delta,bar,hp)) return hp;
    return originalMickeyDamage(descriptor,actor,delta,bar,effects);
}
void TickGuard(const TrainerContext& c) {
    if(guard.enabled && !GuardContext(c,true)) StopGuard();
}
bool StartGuard(const TrainerContext& c,uint64_t owner=0,uint64_t expectedGeneration=0) {
    if(GetCurrentThreadId()!=g_gameThread || !HostFresh() || !PlayerReady(c) || At<uintptr_t>(0x2A11478) ||
       !PlayerHealthControlReady(c)) return false;
    const auto role=player_role::Inspect(c);
    if(role.role!=player_role::Sora && role.role!=player_role::Roxas && role.role!=player_role::Mickey) return false;
    const uint64_t generation=actor_lifetime::ObserveCurrent(c);
    if(!generation || (expectedGeneration && generation!=expectedGeneration)) return false;
    TickGuard(c);
    if(owner && guard.enabled && guard.owner!=owner) return false;
    if(guard.enabled && guard.owner==owner && guard.generation==generation && GuardContext(c)) return true;
    if(!InstallGuardHooks() || !actor_lifetime::Pin(generation)) return false;
    StopGuard();
    guard.enabled=true;guard.player=c.player;guard.status=c.status;guard.generation=generation;guard.owner=owner;
    guard.scheduler=At<uintptr_t>(0x716868);guard.heap=At<uintptr_t>(0x9BA920);
    guard.descriptor=role.descriptor;guard.object=role.object;guard.character=role.characterId;guard.form=role.form;
    memcpy(guard.room,reinterpret_cast<void*>(g_base+0x717008),sizeof(guard.room));
    blockedHits=0;lastBlockedDamage=0;return true;
}
uint64_t GuardWordPair(const double* args) {
    return static_cast<uint64_t>(static_cast<uint32_t>(args[0])) |
        (static_cast<uint64_t>(static_cast<uint32_t>(args[1]))<<32);
}
bool OwnedGuardHandle(const TrainerContext& c,const double args[8],TrainerResult& result) {
    result={2,L"Owned damage guard requires an operation and exact owner, bridge and player identifiers."};
    if(!IsInteger(args[0],0,1) || args[7]!=0) return true;
    for(unsigned i=1;i<=6;++i) if(!IsInteger(args[i],0,4294967295.0)) return true;
    const uint64_t owner=GuardWordPair(args+1),bridge=GuardWordPair(args+3),generation=GuardWordPair(args+5);
    if(!owner || !bridge || bridge!=actor_lifetime::BridgeInstance() || (args[0] && !generation)) return true;
    if(GetCurrentThreadId()!=g_gameThread) return true;
    if(!args[0]) {
        if(guard.enabled && guard.owner==owner && (!generation || guard.generation==generation)) StopGuard();
        result={0,L"Owned damage guard release acknowledged; a different owner is preserved."};return true;
    }
    if(!StartGuard(c,owner,generation)) {
        result={3,L"Waiting for the expected controlled player and an available damage guard; another owner is preserved."};return true;
    }
    result={0,L"Owned damage guard applied to the expected player instance."};return true;
}
