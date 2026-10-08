#pragma once
#include <windows.h>
#include <stdint.h>
#include <stddef.h>
#include "StatusRevisionLedger.h"

// Fixed-build STATUS observers; no hook installation or game-code execution.
// The installer must retain this object and its immutable original trampolines
// for every possible entrant, including after confidence has been lost.
namespace status_observer {
static_assert(sizeof(uintptr_t)==8 && sizeof(int)==4,"STATUS observers require the retail Win64 ABI");
constexpr size_t StatusSize=632, RefCountOffset=612;
constexpr size_t FreeListOffset=StatusSize*status_revision::SlotCount;
constexpr size_t FreeCountOffset=FreeListOffset+sizeof(int)*status_revision::SlotCount;
constexpr size_t PoolSize=FreeCountOffset+sizeof(int);

// Preserve all 64 bits of the observed integer return register even where the
// retail caller ignores the result. Reset has no defined return value.
using InitOriginal=uint64_t (__fastcall*)(uintptr_t);
using RebuildOriginal=uint64_t (__fastcall*)(uintptr_t,const unsigned char*);
using CoefficientOriginal=uint64_t (__fastcall*)(uintptr_t,int,int);
using ResetOriginal=void (__fastcall*)(uintptr_t);
using ReleaseOriginal=uint64_t (__fastcall*)(uintptr_t);
struct Originals {
    InitOriginal initialize=nullptr;
    RebuildOriginal rebuild=nullptr;
    CoefficientOriginal coefficient=nullptr;
    ResetOriginal reset=nullptr;
    ReleaseOriginal release=nullptr;
};
enum class Phase : unsigned { Dormant, Bootstrap, Observing, Fault };
struct State {
    Phase phase=Phase::Dormant;
    status_revision::Health health=status_revision::Health::Uninstalled;
    uint64_t inFlight=0;
    unsigned ledgerFrames=0;
};

inline bool ReadableSpan(uintptr_t address,size_t size) noexcept {
    if(!address || !size || size>UINTPTR_MAX-address)return false;
    const uintptr_t end=address+size;
    while(address<end) {
        MEMORY_BASIC_INFORMATION mbi{};
        if(VirtualQuery(reinterpret_cast<const void*>(address),&mbi,sizeof(mbi))!=sizeof(mbi) ||
           mbi.State!=MEM_COMMIT || (mbi.Protect&(PAGE_GUARD|PAGE_NOACCESS)))return false;
        const DWORD access=mbi.Protect&0xff;
        if(access!=PAGE_READONLY && access!=PAGE_READWRITE && access!=PAGE_WRITECOPY &&
           access!=PAGE_EXECUTE_READ && access!=PAGE_EXECUTE_READWRITE &&
           access!=PAGE_EXECUTE_WRITECOPY)return false;
        const uintptr_t region=reinterpret_cast<uintptr_t>(mbi.BaseAddress);
        if(!mbi.RegionSize || mbi.RegionSize>UINTPTR_MAX-region)return false;
        const uintptr_t next=region+mbi.RegionSize;
        if(next<=address)return false;
        address=next;
    }
    return true;
}

struct PoolView {
    uintptr_t base=0;
    bool Slot(uintptr_t status,unsigned& index) const noexcept {
        index=status_revision::SlotCount;
        if(!base || PoolSize>UINTPTR_MAX-base || status<base || status-base>=FreeListOffset ||
           (status-base)%StatusSize)return false;
        index=static_cast<unsigned>((status-base)/StatusSize);
        return true;
    }
    // Init is also called for every FREE slot during process startup. Its old
    // refcount and the not-yet-built free list cannot be an Init precondition.
    bool Initializable(uintptr_t status,unsigned& index) const noexcept {
        return Slot(status,index) && ReadableSpan(status,StatusSize);
    }
    bool Owns(uintptr_t status,unsigned& index,int& preRefCount) const noexcept {
        preRefCount=0;
        if(!Slot(status,index) || !ReadableSpan(status,StatusSize) ||
           !ReadableSpan(base+FreeListOffset,PoolSize-FreeListOffset))return false;
        __try {
            const int count=*reinterpret_cast<const volatile int*>(base+FreeCountOffset);
            if(count<0 || count>static_cast<int>(status_revision::SlotCount))return false;
            bool free[status_revision::SlotCount]{};
            for(int i=0;i<count;++i) {
                const int value=*reinterpret_cast<const volatile int*>(base+FreeListOffset+sizeof(int)*i);
                if(value<0 || value>=static_cast<int>(status_revision::SlotCount) || free[value])return false;
                free[value]=true;
            }
            if(free[index])return false;
            preRefCount=*reinterpret_cast<const volatile int*>(status+RefCountOffset);
            return preRefCount>0;
        } __except(EXCEPTION_EXECUTE_HANDLER) {
            // Only our observation reads are inside this handler. A native
            // original's exception is never caught or converted to success.
            return false;
        }
    }
};

// Trusted in-bridge transactions can validate the current pool/backlink,
// compare revisions and exact field bits, notify a ManualWrite, and write while
// holding ONE metadata lock. The callback must not call originals, reenter any
// Observer method, block on another callback, or let C++ exceptions escape.
// It must validate Actor generation/context and field writability itself.
struct TransactionContext { status_revision::Ledger& ledger; const PoolView& pool; };
using Transaction=bool (*)(TransactionContext&,void*) noexcept;

class Observer {
#ifdef KH2_STATUS_OBSERVER_TESTS
    friend struct ObserverTestAccess;
#endif
    SRWLOCK lock=SRWLOCK_INIT;
    status_revision::Ledger ledger{};
    Originals originals{};
    PoolView pool{};
    Phase phase=Phase::Dormant;
    uint64_t instance=0,inFlight=0;
    DWORD gameThread=0;
    struct Ticket { status_revision::Frame frame{}; bool counted=false; };

    void FaultLocked() noexcept { phase=Phase::Fault;ledger.Fault(); }
    Ticket Before(status_revision::Event event,uintptr_t argument,int parameter=0) noexcept {
        Ticket ticket{};
        AcquireSRWLockExclusive(&lock);
        __try {
            if(phase==Phase::Dormant || inFlight==UINT64_MAX) { FaultLocked();return ticket; }
            ++inFlight;ticket.counted=true;
            if(phase!=Phase::Observing)return ticket;
            unsigned slot=status_revision::SlotCount;
            int refs=0;
            bool valid=false;
            switch(event) {
            case status_revision::Event::PoolReset:
                valid=argument==pool.base;break;
            case status_revision::Event::Initialize:
                valid=pool.Initializable(argument,slot);break;
            default:
                valid=pool.Owns(argument,slot,refs);break;
            }
            if(!valid) { FaultLocked();return ticket; }
            if(event==status_revision::Event::Release)parameter=refs;
            ticket.frame=ledger.Enter(event,slot,parameter,0,GetCurrentThreadId());
            if(ledger.Status()!=status_revision::Health::Observing)FaultLocked();
        } __finally {
            ReleaseSRWLockExclusive(&lock);
        }
        return ticket;
    }
    void After(Ticket ticket,bool normal) noexcept {
        AcquireSRWLockExclusive(&lock);
        __try {
            if(!normal)FaultLocked();
            if(ticket.frame.ticket)ledger.Exit(ticket.frame,normal);
            if(ticket.counted) {
                if(inFlight)--inFlight;else FaultLocked();
            }
            if(ledger.Status()==status_revision::Health::Fault)FaultLocked();
        } __finally {
            ReleaseSRWLockExclusive(&lock);
        }
    }
public:
    Observer()=default;
    Observer(const Observer&)=delete;
    Observer& operator=(const Observer&)=delete;

    // Call before ANY entry can reach this instance. Once bound, neither the
    // originals nor this object's address can change, including on faults.
    // A failed first configuration publishes nothing and may be corrected.
    bool Bind(const Originals& functions,uintptr_t poolBase,uint64_t bridgeInstance,DWORD ownerThread) noexcept {
        const DWORD error=GetLastError();
        bool ok=false;
        AcquireSRWLockExclusive(&lock);
        __try {
            if(phase!=Phase::Dormant)FaultLocked();
            else if(functions.initialize && functions.rebuild && functions.coefficient &&
                    functions.reset && functions.release && poolBase && !(poolBase&3) &&
                    PoolSize<=UINTPTR_MAX-poolBase && bridgeInstance && ownerThread) {
                originals=functions;pool.base=poolBase;instance=bridgeInstance;
                gameThread=ownerThread;phase=Phase::Bootstrap;ok=true;
            }
        } __finally { ReleaseSRWLockExclusive(&lock);SetLastError(error); }
        return ok;
    }
    // This method does NOT prove installation or quiescence. The installer may
    // call it only after all five entries, trampoline lifetime/unwind metadata,
    // and a barrier draining PREEXISTING unobserved writers are established.
    // A relocated old call has no Before ticket; inFlight==0 alone is not proof.
    bool ArmAfterProvenBarrier(uint64_t expectedInstance) noexcept {
        const DWORD error=GetLastError();
        bool ok=false;
        AcquireSRWLockExclusive(&lock);
        __try {
            if(phase==Phase::Bootstrap && !inFlight && instance==expectedInstance &&
               gameThread==GetCurrentThreadId() && ledger.Start(instance)) {
                phase=Phase::Observing;ok=true;
            }
        } __finally { ReleaseSRWLockExclusive(&lock);SetLastError(error); }
        return ok;
    }
    void Fault() noexcept {
        const DWORD error=GetLastError();
        AcquireSRWLockExclusive(&lock);FaultLocked();ReleaseSRWLockExclusive(&lock);SetLastError(error);
    }
    State Inspect() noexcept {
        const DWORD error=GetLastError();
        AcquireSRWLockExclusive(&lock);
        const State state{phase,ledger.Status(),inFlight,ledger.ActiveCalls()};
        ReleaseSRWLockExclusive(&lock);SetLastError(error);return state;
    }
    bool WithMetadata(Transaction action,void* argument) noexcept {
        const DWORD error=GetLastError();
        bool result=false;
        AcquireSRWLockExclusive(&lock);
        __try {
            __try {
                if(action && phase==Phase::Observing && !inFlight && gameThread==GetCurrentThreadId()) {
                    TransactionContext context{ledger,pool};
                    result=action(context,argument);
                    if(ledger.Status()!=status_revision::Health::Observing) { FaultLocked();result=false; }
                }
            } __except(EXCEPTION_EXECUTE_HANDLER) {
                // A failed metadata transaction loses confidence; it never
                // retries a possibly completed write or calls a native original.
                FaultLocked();result=false;
            }
        } __finally { ReleaseSRWLockExclusive(&lock);SetLastError(error); }
        return result;
    }

    // Entry use requires successful Bind before publication. An unbound null
    // original is an installer programming error and cannot be forwarded.
    uint64_t Initialize(uintptr_t status) {
        const DWORD incomingError=GetLastError();
        const Ticket ticket=Before(status_revision::Event::Initialize,status);
        uint64_t result=0;
        SetLastError(incomingError);
        __try { result=originals.initialize(status); }
        __finally { const DWORD error=GetLastError();After(ticket,!AbnormalTermination());SetLastError(error); }
        return result;
    }
    uint64_t Rebuild(uintptr_t status,const unsigned char* save) {
        const DWORD incomingError=GetLastError();
        const Ticket ticket=Before(status_revision::Event::Rebuild,status);
        uint64_t result=0;
        SetLastError(incomingError);
        __try { result=originals.rebuild(status,save); }
        __finally { const DWORD error=GetLastError();After(ticket,!AbnormalTermination());SetLastError(error); }
        return result;
    }
    uint64_t Coefficient(uintptr_t status,int index,int percentage) {
        const DWORD incomingError=GetLastError();
        const Ticket ticket=Before(status_revision::Event::GeneralWrite,status,index);
        uint64_t result=0;
        SetLastError(incomingError);
        __try { result=originals.coefficient(status,index,percentage); }
        __finally { const DWORD error=GetLastError();After(ticket,!AbnormalTermination());SetLastError(error); }
        return result;
    }
    void Reset(uintptr_t nativePool) {
        const DWORD incomingError=GetLastError();
        const Ticket ticket=Before(status_revision::Event::PoolReset,nativePool);
        SetLastError(incomingError);
        __try { originals.reset(nativePool); }
        __finally { const DWORD error=GetLastError();After(ticket,!AbnormalTermination());SetLastError(error); }
    }
    uint64_t Release(uintptr_t status) {
        const DWORD incomingError=GetLastError();
        const Ticket ticket=Before(status_revision::Event::Release,status);
        uint64_t result=0;
        SetLastError(incomingError);
        __try { result=originals.release(status); }
        __finally { const DWORD error=GetLastError();After(ticket,!AbnormalTermination());SetLastError(error); }
        return result;
    }
};

// Actual Win64 entry signatures contain no implicit `this` argument. The
// reference binds a stable instance at compile time; no mutable global dispatch
// pointer is read by a native caller. Installer chooses the relays targeting
// these functions and owns the instance/module's lifetime.
template<Observer& Owner> struct Entrypoints {
    static uint64_t __fastcall Initialize(uintptr_t status) { return Owner.Initialize(status); }
    static uint64_t __fastcall Rebuild(uintptr_t status,const unsigned char* save) { return Owner.Rebuild(status,save); }
    static uint64_t __fastcall Coefficient(uintptr_t status,int index,int percent) { return Owner.Coefficient(status,index,percent); }
    static void __fastcall Reset(uintptr_t pool) { Owner.Reset(pool); }
    static uint64_t __fastcall Release(uintptr_t status) { return Owner.Release(status); }
};
} // namespace status_observer
