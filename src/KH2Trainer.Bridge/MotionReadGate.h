#pragma once
#include "MotionObserverSupport.h"
#include "MotionPayloadCopy.h"

// Local exclusion for cooperating typed mutator wrappers. This does NOT install
// routes, drain older calls, close asynchronous/alias writers, prove a resource
// owner, or establish game-thread admission. No public arm/trusted flag does so.
// A future provider must independently establish those facts before supplying a
// ReadScope. Once a router can expose these callbacks, retain the Gate/context,
// Observer and original continuation until process exit, including on fault.
namespace motion_read_gate {
constexpr DWORD ReadMutationException=0xe0424d31;
constexpr unsigned MaxActiveCalls=64;

enum class Status { NotPrepared,Prepared,Copied,Busy,Faulted,Reentrant,CopyRejected,Unwound };
struct Outcome {
    Status status=Status::NotPrepared;
    motion_payload_copy::Error copyError=motion_payload_copy::Error::NotPrepared;
};
struct Snapshot { bool available=false,faulted=false; uint64_t activeCalls=0; };
class Gate;

// Thread-confined workspace. Prepare/TakeResult/destruction occur outside any
// held read scope. Do not share a job across simultaneous or reentrant callers.
// Encapsulation prevents a Busy/fault before Copy from exporting an older result.
class CopyJob final {
    motion_payload_copy::PreparedCopy prepared{};
    Outcome outcome{};
    friend class Gate;
public:
    CopyJob()=default;
    CopyJob(const CopyJob&)=delete;
    CopyJob& operator=(const CopyJob&)=delete;
    bool Prepare(motion_payload_copy::Limits limits={}) noexcept {
        const bool okay=prepared.Prepare(limits);
        outcome={okay?Status::Prepared:Status::NotPrepared,prepared.Status()};
        return okay;
    }
    Outcome Inspect() const noexcept {return outcome;}
    motion_payload_copy::Result TakeResult() noexcept {
        if(outcome.status!=Status::Copied)return motion_payload_copy::Result(outcome.copyError);
        auto result=prepared.TakeResult();
        outcome={Status::NotPrepared,motion_payload_copy::Error::NotPrepared};
        return result;
    }
};

class Gate final {
    SRWLOCK lock=SRWLOCK_INIT;
    volatile LONG fault=0,readerThread=0;
    uint64_t serial=0,active=0;
    struct Call { uint64_t ticket=0; uintptr_t controller=0; DWORD thread=0; } calls[MaxActiveCalls]{};
    void LatchFault() noexcept {InterlockedExchange(&fault,1);}
    uint64_t Enter(uintptr_t controller) {
        if(ReadingOnThisThread()) {
            // The Observer will call After(false,false) while the outer read
            // still holds lock. Leave handles this before attempting Acquire.
            LatchFault();
            RaiseException(ReadMutationException,EXCEPTION_NONCONTINUABLE,0,nullptr);
            return 0;
        }
        const DWORD incoming=GetLastError();
        uint64_t ticket=0;
        unsigned slot=MaxActiveCalls;
        AcquireSRWLockExclusive(&lock);
        __try {
            if(Faulted())__leave;
            if(serial==UINT64_MAX || active==MaxActiveCalls){LatchFault();__leave;}
            for(unsigned i=0;i<MaxActiveCalls;++i)if(!calls[i].ticket){slot=i;break;}
            if(slot==MaxActiveCalls){LatchFault();__leave;}
            ticket=++serial;
            calls[slot]={ticket,controller,GetCurrentThreadId()};
            ++active;
        } __finally {
            const DWORD outgoing=GetLastError();
            const bool abnormal=AbnormalTermination()!=FALSE;
            if(abnormal) {
                LatchFault();
                if(ticket && slot<MaxActiveCalls){calls[slot]={};if(active)--active;}
            }
            ReleaseSRWLockExclusive(&lock);
            SetLastError(abnormal?outgoing:incoming);
        }
        return ticket;
    }
    void Leave(uintptr_t controller,uint64_t ticket,bool beforeCompleted,bool normalReturn) noexcept {
        if(ReadingOnThisThread()) {
            // No counted native call can coexist with an admitted reader. In
            // particular the forbidden reentrant Before never issued a ticket.
            LatchFault();return;
        }
        const DWORD incoming=GetLastError();
        AcquireSRWLockExclusive(&lock);
        __try {
            if(!beforeCompleted || !normalReturn)LatchFault();
            if(!ticket) {
                if(!Faulted())LatchFault();
                __leave; // Calls forwarded after Fault have no counted ticket.
            }
            unsigned slot=MaxActiveCalls;
            for(unsigned i=0;i<MaxActiveCalls;++i)if(calls[i].ticket==ticket){slot=i;break;}
            if(slot==MaxActiveCalls || !beforeCompleted || !active ||
               calls[slot].controller!=controller || calls[slot].thread!=GetCurrentThreadId()) {
                LatchFault();__leave;
            }
            calls[slot]={};--active;
        } __finally {ReleaseSRWLockExclusive(&lock);SetLastError(incoming);}
    }
public:
    Gate()=default;
    Gate(const Gate&)=delete;
    Gate& operator=(const Gate&)=delete;
    bool Faulted() const noexcept {
        return InterlockedCompareExchange(const_cast<volatile LONG*>(&fault),0,0)!=0;
    }
    bool ReadingOnThisThread() const noexcept {
        return static_cast<DWORD>(InterlockedCompareExchange(const_cast<volatile LONG*>(&readerThread),0,0))==GetCurrentThreadId();
    }
    // Irreversible loss of read confidence; native forwarding is not disabled.
    void Invalidate() noexcept {LatchFault();}
    Snapshot Inspect() noexcept {
        if(ReadingOnThisThread())return {false,Faulted(),0};
        if(!TryAcquireSRWLockExclusive(&lock))return {false,Faulted(),0};
        const Snapshot result{true,Faulted(),active};
        ReleaseSRWLockExclusive(&lock);return result;
    }
    static uint64_t __fastcall Before(void* context,uintptr_t controller) {
        return static_cast<Gate*>(context)->Enter(controller);
    }
    static void __fastcall After(void* context,uintptr_t controller,uint64_t ticket,
                                 bool beforeCompleted,bool normalReturn) noexcept {
        static_cast<Gate*>(context)->Leave(controller,ticket,beforeCompleted,normalReturn);
    }

    // The caller/provider is trusted to supply known live, serialized source
    // spans and complete writer/queue/bootstrap coverage. This lock protects only
    // calls entering THIS Gate; zero active calls is not that external proof.
    // Scope callbacks perform bounded observation only: no allocation/free,
    // logging, engine callout, blocking wait, other observer lock, or reentry.
    // Prepare and TakeResult are deliberately absent from this held interval.
    // A provider/SEH exception propagates unchanged; finally latches Fault,
    // prevents result publication and releases lock. No native exception filter.
    Outcome TryCopy(CopyJob& job,motion_payload_copy::ReadScope& scope) {
        using Error=motion_payload_copy::Error;
        const DWORD incoming=GetLastError();
        if(ReadingOnThisThread()) {
            LatchFault();job.outcome={Status::Reentrant,Error::Changed};
            return job.outcome;
        }
        job.outcome={Status::Busy,Error::NoAdmission};
        if(!TryAcquireSRWLockExclusive(&lock))return job.outcome;
        __try {
            if(Faulted()){job.outcome={Status::Faulted,Error::Changed};__leave;}
            if(active)__leave;
            InterlockedExchange(&readerThread,static_cast<LONG>(GetCurrentThreadId()));
            const Error result=job.prepared.Copy(scope);
            job.outcome=Faulted()?Outcome{Status::Faulted,Error::Changed}:
                Outcome{result==Error::None?Status::Copied:Status::CopyRejected,result};
        } __finally {
            const DWORD outgoing=GetLastError();
            const bool abnormal=AbnormalTermination()!=FALSE;
            if(abnormal){LatchFault();job.outcome={Status::Unwound,Error::Changed};}
            InterlockedExchange(&readerThread,0);
            ReleaseSRWLockExclusive(&lock);
            SetLastError(abnormal?outgoing:incoming);
        }
        return job.outcome;
    }
};
} // namespace motion_read_gate
