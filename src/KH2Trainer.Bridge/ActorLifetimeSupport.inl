// Bridge-owned Actor lifetime observation. Original-build contract and full pins:
// docs/research/actor-lifetime-20261007. No Actor fields are written here.
// Include after PlayerRoleSupport; callers run on the engine thread.
// Native callbacks always forward, including after observer failure.
#pragma once
namespace actor_lifetime {
#include "ActorLifetimePins.inl"
constexpr unsigned kCapacity=128;
constexpr uintptr_t kActionTable=0x750D30,kAction=0x750950,kActionVtable=0x5CCEB8;
constexpr uintptr_t kBirthSlot=0x5CCEC0,kBirth=0x409AB0,kBirthReturn=0x3B396D;
constexpr uintptr_t kSoraSlot=0x5CBA28,kSoraDeath=0x4049E0;
constexpr uintptr_t kMickeySlot=0x5D15A0,kMickeyDeath=0x414DD0;
enum ObserverStatus : unsigned { Uninstalled=0, Observing=1, Fault=2 };
struct Watch { uintptr_t actor=0; uint64_t generation=0; unsigned pins=0; bool alive=false; };
Watch watches[kCapacity]{};
SRWLOCK lock=SRWLOCK_INIT;
volatile LONG observerStatus=Uninstalled;
uintptr_t installedBase=0;
uint64_t bridgeInstance=0,nextSerial=0;
using BirthFn=void (__fastcall*)(uintptr_t,uintptr_t);
using DeathFn=uintptr_t (__fastcall*)(uintptr_t,uintptr_t);
BirthFn originalBirth=nullptr;
DeathFn originalSoraDeath=nullptr,originalMickeyDeath=nullptr;
#ifdef KH2_ACTOR_LIFETIME_TESTS
BirthFn testBirth=nullptr;
DeathFn testSoraDeath=nullptr,testMickeyDeath=nullptr;
bool testPin=true,testRandom=true;
int testSwapFailure=-1,testSwapCalls=0;
uint64_t testInstance=0x1234567812345678ULL;
uintptr_t testReturnOverride=0;
SIZE_T (WINAPI* testQuery)(LPCVOID,PMEMORY_BASIC_INFORMATION,SIZE_T)=VirtualQuery;
BOOL (WINAPI* testProtect)(LPVOID,SIZE_T,DWORD,PDWORD)=VirtualProtect;
DWORD testMemoryType=MEM_IMAGE;
bool testForeignAllocation=false;
bool testNotifyFault=false;
#endif
bool OnThread() { return g_gameThread && GetCurrentThreadId()==g_gameThread; }
bool Range(uintptr_t p,SIZE_T n) {
    return p && n<=UINTPTR_MAX-p && Readable(reinterpret_cast<const void*>(p),n);
}
template<class T> const T& Read(uintptr_t rva) {
    return *reinterpret_cast<const T*>(installedBase+rva);
}
unsigned Status() { return static_cast<unsigned>(InterlockedCompareExchange(&observerStatus,0,0)); }
void FailLocked() { InterlockedExchange(&observerStatus,Fault); }
__declspec(noinline) void __fastcall BirthHook(uintptr_t action,uintptr_t actor);
__declspec(noinline) uintptr_t __fastcall SoraDeathHook(uintptr_t descriptor,uintptr_t actor);
__declspec(noinline) uintptr_t __fastcall MickeyDeathHook(uintptr_t descriptor,uintptr_t actor);
bool CodeReady() {
    if(!installedBase || installedBase!=g_base) return false;
    for(const auto& p:kPins)
        if(p.rva>UINTPTR_MAX-installedBase || !Range(installedBase+p.rva,p.count) ||
           memcmp(reinterpret_cast<const void*>(installedBase+p.rva),p.bytes,p.count)) return false;
    return true;
}
bool TablesReady() {
    return Range(installedBase+kActionTable,8) && Read<uintptr_t>(kActionTable)==installedBase+kAction &&
        Range(installedBase+kAction,8) && Read<uintptr_t>(kAction)==installedBase+kActionVtable &&
        Range(installedBase+0x750300,8) && Read<uintptr_t>(0x750300)==installedBase+kSoraSlot &&
        Range(installedBase+0x7523B8,8) && Read<uintptr_t>(0x7523B8)==installedBase+kMickeySlot;
}
bool SlotLocation(uintptr_t rva,MEMORY_BASIC_INFORMATION& m) {
    if(!installedBase || rva>UINTPTR_MAX-installedBase ||
       (rva!=kBirthSlot && rva!=kSoraSlot && rva!=kMickeySlot)) return false;
    const uintptr_t p=installedBase+rva;
    if((p&(sizeof(void*)-1)) || sizeof(void*)>UINTPTR_MAX-p) return false;
#ifdef KH2_ACTOR_LIFETIME_TESTS
    if(!testQuery(reinterpret_cast<void*>(p),&m,sizeof(m))) return false;
    m.Type=testMemoryType;
    if(testForeignAllocation)m.AllocationBase=reinterpret_cast<void*>(installedBase+4096);
#else
    if(!VirtualQuery(reinterpret_cast<void*>(p),&m,sizeof(m))) return false;
#endif
    const uintptr_t region=reinterpret_cast<uintptr_t>(m.BaseAddress);
    return m.State==MEM_COMMIT && m.Type==MEM_IMAGE &&
        m.AllocationBase==reinterpret_cast<void*>(installedBase) && region<=p &&
        m.RegionSize<=UINTPTR_MAX-region && p+sizeof(void*)<=region+m.RegionSize;
}
bool SlotEquals(uintptr_t rva,uintptr_t expected) {
    MEMORY_BASIC_INFORMATION m{};
    return SlotLocation(rva,m) && Range(installedBase+rva,8) && Read<uintptr_t>(rva)==expected;
}
bool OwnSlots() {
    return SlotEquals(kBirthSlot,reinterpret_cast<uintptr_t>(&BirthHook)) &&
        SlotEquals(kSoraSlot,reinterpret_cast<uintptr_t>(&SoraDeathHook)) &&
        SlotEquals(kMickeySlot,reinterpret_cast<uintptr_t>(&MickeyDeathHook));
}
bool IntegrityLocked() {
    if(Status()!=Observing) return false;
    bool good=false;
    __try { good=OnThread() && CodeReady() && TablesReady() && OwnSlots(); }
    __except(EXCEPTION_EXECUTE_HANDLER) { good=false; }
    if(!good) FailLocked();
    return good;
}
bool Ready() {
    AcquireSRWLockExclusive(&lock);
    bool ok=false;
    __try { ok=IntegrityLocked(); }
    __finally { ReleaseSRWLockExclusive(&lock); }
    return ok;
}
bool PinModule() {
#ifdef KH2_ACTOR_LIFETIME_TESTS
    return testPin;
#else
    HMODULE module=nullptr;
    return GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,
        reinterpret_cast<LPCWSTR>(&BirthHook),&module)!=FALSE;
#endif
}
bool NewInstance(uint64_t& value) {
#ifdef KH2_ACTOR_LIFETIME_TESTS
    value=testInstance; return testRandom && value!=0;
#else
    // Obtain an opaque session nonce without adding a linker dependency.
    HMODULE module=LoadLibraryExW(L"bcrypt.dll",nullptr,LOAD_LIBRARY_SEARCH_SYSTEM32);
    if(!module) return false;
    using RandomFn=LONG (WINAPI*)(void*,unsigned char*,ULONG,ULONG);
    auto random=reinterpret_cast<RandomFn>(GetProcAddress(module,"BCryptGenRandom"));
    const bool ok=random && random(nullptr,reinterpret_cast<unsigned char*>(&value),sizeof(value),2)>=0 && value;
    FreeLibrary(module); return ok;
#endif
}
bool ProtectSlot(uintptr_t rva,DWORD protection,DWORD& previous) {
#ifdef KH2_ACTOR_LIFETIME_TESTS
    return testProtect(reinterpret_cast<void*>(installedBase+rva),sizeof(void*),protection,&previous)!=FALSE;
#else
    return VirtualProtect(reinterpret_cast<void*>(installedBase+rva),sizeof(void*),protection,&previous)!=FALSE;
#endif
}
bool IsWriteProtection(DWORD protection) {
    if(protection&(PAGE_GUARD|PAGE_NOACCESS)) return false;
    const DWORD p=protection&0xff;
    return p==PAGE_READWRITE || p==PAGE_WRITECOPY || p==PAGE_EXECUTE_READWRITE || p==PAGE_EXECUTE_WRITECOPY;
}
void RecoverSlot(uintptr_t rva,uintptr_t ours,uintptr_t original,DWORD previous) {
    // A failing VirtualProtect may leave either protection outcome. Query the
    // real page again; never attempt rollback CAS merely because it was RW once.
    __try {
        MEMORY_BASIC_INFORMATION m{};DWORD unused=0;
        if(!SlotLocation(rva,m)) return;
        if(!IsWriteProtection(m.Protect)) {
            ProtectSlot(rva,PAGE_READWRITE,unused);
            if(!SlotLocation(rva,m)) return;
        }
        if(IsWriteProtection(m.Protect))
            InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(installedBase+rva),
                reinterpret_cast<void*>(original),reinterpret_cast<void*>(ours));
        // Also restore protection after a CAS conflict: the foreign pointer is
        // preserved, while our temporary page-protection change is best-effort.
        ProtectSlot(rva,previous,unused);
    } __except(EXCEPTION_EXECUTE_HANDLER) { FailLocked(); }
}
bool Swap(uintptr_t slotRva,uintptr_t expected,uintptr_t replacement) {
#ifdef KH2_ACTOR_LIFETIME_TESTS
    if(testSwapCalls++==testSwapFailure) return false;
#endif
    MEMORY_BASIC_INFORMATION m{};DWORD old=0,unused=0;bool protectionAttempted=false;
    __try {
        if(!SlotLocation(slotRva,m) || !Range(installedBase+slotRva,8) || Read<uintptr_t>(slotRva)!=expected) return false;
        old=m.Protect;protectionAttempted=true;
        DWORD reportedOld=old;
        if(!ProtectSlot(slotRva,PAGE_READWRITE,reportedOld)) {
            RecoverSlot(slotRva,replacement,expected,old);return false;
        }
        MEMORY_BASIC_INFORMATION now{};
        if(!SlotLocation(slotRva,now) || !IsWriteProtection(now.Protect)) {
            RecoverSlot(slotRva,replacement,expected,old);return false;
        }
        const bool changed=InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(installedBase+slotRva),
            reinterpret_cast<void*>(replacement),reinterpret_cast<void*>(expected))==reinterpret_cast<void*>(expected);
        const bool restored=ProtectSlot(slotRva,old,unused);
        if(!restored) RecoverSlot(slotRva,replacement,expected,old);
        return changed && restored;
    } __except(EXCEPTION_EXECUTE_HANDLER) {
        FailLocked();if(protectionAttempted)RecoverSlot(slotRva,replacement,expected,old);return false;
    }
}
void RollbackSlots() {
    if(Range(installedBase+kBirthSlot,8) && Read<uintptr_t>(kBirthSlot)==reinterpret_cast<uintptr_t>(&BirthHook))
        Swap(kBirthSlot,reinterpret_cast<uintptr_t>(&BirthHook),installedBase+kBirth);
    if(Range(installedBase+kSoraSlot,8) && Read<uintptr_t>(kSoraSlot)==reinterpret_cast<uintptr_t>(&SoraDeathHook))
        Swap(kSoraSlot,reinterpret_cast<uintptr_t>(&SoraDeathHook),installedBase+kSoraDeath);
    if(Range(installedBase+kMickeySlot,8) && Read<uintptr_t>(kMickeySlot)==reinterpret_cast<uintptr_t>(&MickeyDeathHook))
        Swap(kMickeySlot,reinterpret_cast<uintptr_t>(&MickeyDeathHook),installedBase+kMickeyDeath);
}
bool Install(const TrainerContext& c) {
    if(!OnThread() || !g_base || c.base!=g_base) return false;
    AcquireSRWLockExclusive(&lock);
    bool ok=false;
    __try {
        if(Status()==Observing) { ok=IntegrityLocked();__leave; }
        if(Status()==Fault) __leave; // Never adopt after an observation gap.
        installedBase=g_base;
        if(!CodeReady() || !TablesReady() ||
           !SlotEquals(kBirthSlot,installedBase+kBirth) ||
           !SlotEquals(kSoraSlot,installedBase+kSoraDeath) ||
           !SlotEquals(kMickeySlot,installedBase+kMickeyDeath) ||
           !PinModule() || !NewInstance(bridgeInstance)) { FailLocked();__leave; }
        // Immutable before publishing ANY wrapper. Already-dispatched callbacks
        // retain their original target even after a failed install/foreign hook.
#ifdef KH2_ACTOR_LIFETIME_TESTS
        originalBirth=testBirth;originalSoraDeath=testSoraDeath;originalMickeyDeath=testMickeyDeath;
#else
        originalBirth=reinterpret_cast<BirthFn>(installedBase+kBirth);
        originalSoraDeath=reinterpret_cast<DeathFn>(installedBase+kSoraDeath);
        originalMickeyDeath=reinterpret_cast<DeathFn>(installedBase+kMickeyDeath);
#endif
        if(!originalBirth || !originalSoraDeath || !originalMickeyDeath) { FailLocked();__leave; }
        if(!Swap(kBirthSlot,installedBase+kBirth,reinterpret_cast<uintptr_t>(&BirthHook)) ||
           !Swap(kSoraSlot,installedBase+kSoraDeath,reinterpret_cast<uintptr_t>(&SoraDeathHook)) ||
           !Swap(kMickeySlot,installedBase+kMickeyDeath,reinterpret_cast<uintptr_t>(&MickeyDeathHook))) {
            FailLocked();RollbackSlots();__leave;
        }
        InterlockedExchange(&observerStatus,Observing);
        ok=IntegrityLocked();
    } __finally { ReleaseSRWLockExclusive(&lock); }
    return ok;
}
void RetireAddressLocked(uintptr_t actor) {
    for(auto& w:watches) if(w.generation && w.actor==actor && w.alive) w.alive=false;
}
void NotifyBirth(uintptr_t action,uintptr_t actor,uintptr_t returnAddress) {
    AcquireSRWLockExclusive(&lock);
    __try {
#ifdef KH2_ACTOR_LIFETIME_TESTS
        if(testNotifyFault)RaiseException(0xE0425152,0,0,nullptr);
#endif
        if(!IntegrityLocked()) __leave;
        if(action!=installedBase+kAction) { FailLocked();__leave; }
        // Normal action changes also enter this slot. Only the fully pinned
        // common constructor call is a birth. Do not dereference partial Actor.
        if(returnAddress==installedBase+kBirthReturn) {
            if(!actor) FailLocked();
            else RetireAddressLocked(actor);
        }
    } __finally { ReleaseSRWLockExclusive(&lock); }
}
void NotifyDeath(uintptr_t descriptor,uintptr_t actor,uintptr_t expectedDescriptor) {
    AcquireSRWLockExclusive(&lock);
    __try {
#ifdef KH2_ACTOR_LIFETIME_TESTS
        if(testNotifyFault)RaiseException(0xE0425152,0,0,nullptr);
#endif
        if(!IntegrityLocked()) __leave;
        if(descriptor!=installedBase+expectedDescriptor) { FailLocked();__leave; }
        if(actor) RetireAddressLocked(actor);
    } __finally { ReleaseSRWLockExclusive(&lock); }
}
__declspec(noinline) void __fastcall BirthHook(uintptr_t action,uintptr_t actor) {
    uintptr_t caller=reinterpret_cast<uintptr_t>(_ReturnAddress());
#ifdef KH2_ACTOR_LIFETIME_TESTS
    if(testReturnOverride) caller=testReturnOverride;
#endif
    __try { NotifyBirth(action,actor,caller); }
    __except(EXCEPTION_EXECUTE_HANDLER) { InterlockedExchange(&observerStatus,Fault); }
    originalBirth(action,actor); // No catch: native exceptions propagate.
}
__declspec(noinline) uintptr_t __fastcall SoraDeathHook(uintptr_t descriptor,uintptr_t actor) {
    __try { NotifyDeath(descriptor,actor,0x750300); }
    __except(EXCEPTION_EXECUTE_HANDLER) { InterlockedExchange(&observerStatus,Fault); }
    return originalSoraDeath(descriptor,actor); // No Actor access after original.
}
__declspec(noinline) uintptr_t __fastcall MickeyDeathHook(uintptr_t descriptor,uintptr_t actor) {
    __try { NotifyDeath(descriptor,actor,0x7523B8); }
    __except(EXCEPTION_EXECUTE_HANDLER) { InterlockedExchange(&observerStatus,Fault); }
    return originalMickeyDeath(descriptor,actor);
}
Watch* FindLocked(uint64_t generation) {
    if(!generation) return nullptr;
    for(auto& w:watches) if(w.generation==generation) return &w;
    return nullptr;
}
uint64_t ObserveCurrent(const TrainerContext& c) {
    AcquireSRWLockExclusive(&lock);
    uint64_t result=0;
    __try {
        if(!IntegrityLocked() || c.base!=installedBase) __leave;
        const auto role=player_role::Inspect(c);
        if(role.role!=player_role::Sora && role.role!=player_role::Roxas && role.role!=player_role::Mickey) __leave;
        for(auto& w:watches) if(w.generation && w.alive && w.actor==c.player) { result=w.generation;__leave; }
        if(result) __leave;
        Watch* empty=nullptr;
        for(auto& w:watches) if(!w.generation) { empty=&w;break; }
        if(!empty) for(auto& w:watches) if(!w.pins) { empty=&w;break; }
        if(!empty || nextSerial==UINT64_MAX) { FailLocked();__leave; }
        *empty={c.player,++nextSerial,0,true};result=empty->generation;
    } __finally { ReleaseSRWLockExclusive(&lock); }
    return result;
}
uintptr_t Resolve(uint64_t generation) {
    AcquireSRWLockExclusive(&lock);
    uintptr_t result=0;
    __try {
        if(!IntegrityLocked()) __leave;
        const Watch* w=FindLocked(generation);
        // A watch can outlive native bulk teardown. Lack of current live-list
        // membership blocks resolution without inventing a destructor event.
        if(w && w->alive && player_role::Listed(w->actor)) result=w->actor;
    } __finally { ReleaseSRWLockExclusive(&lock); }
    return result;
}
bool IsRetired(uint64_t generation) {
    AcquireSRWLockExclusive(&lock);
    bool result=false;
    __try {
        if(!IntegrityLocked() || !generation || generation>nextSerial) __leave;
        const Watch* w=FindLocked(generation);
        // Missing unpinned serials are retired observation tokens. A pinned
        // receipt cannot disappear, so its true death/birth state is retained.
        result=!w || !w->alive;
    } __finally { ReleaseSRWLockExclusive(&lock); }
    return result;
}
bool Pin(uint64_t generation) {
    AcquireSRWLockExclusive(&lock);
    bool result=false;
    __try {
        if(!IntegrityLocked()) __leave;
        Watch* w=FindLocked(generation);
        if(w && w->alive && w->pins<UINT_MAX) { ++w->pins;result=true; }
        else if(w && w->pins==UINT_MAX) FailLocked();
    } __finally { ReleaseSRWLockExclusive(&lock); }
    return result;
}
void Unpin(uint64_t generation) {
    if(!OnThread()) return;
    AcquireSRWLockExclusive(&lock);
    __try {
        Watch* w=FindLocked(generation);
        if(w && w->pins) { --w->pins; if(!w->pins && !w->alive) *w={}; }
    } __finally { ReleaseSRWLockExclusive(&lock); }
}
uint64_t BridgeInstance() { return bridgeInstance; }
} // namespace actor_lifetime
