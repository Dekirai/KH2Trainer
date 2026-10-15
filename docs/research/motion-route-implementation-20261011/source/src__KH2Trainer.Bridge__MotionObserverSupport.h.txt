#pragma once
#include <windows.h>
#include <stdint.h>

// Typed forwarding support for retail RVA 3C8CD0. This does not install a hook,
// establish a game thread/barrier, track resource ownership, or enable Scale.
// The installer must retain the Observer, callbacks/context, and original
// trampoline for every possible entrant. Bind exactly once before publication.
namespace motion_observer {
static_assert(sizeof(uintptr_t)==8 && sizeof(int32_t)==4 && sizeof(float)==4,
    "Motion observation requires the retail Win64 ABI");

// RCX=controller, EDX=signed selection, XMM2=blend, XMM3=frame; result in AL.
using OriginalFn=uint8_t (__fastcall*)(uintptr_t,int32_t,float,float);
using BeforeFn=uint64_t (__fastcall*)(void* context,uintptr_t controller);
using AfterFn=void (__fastcall*)(void* context,uintptr_t controller,uint64_t ticket,
    bool beforeCompleted,bool normalReturn);
constexpr DWORD UnboundCallException=0xe0424d01;

class Observer final {
    OriginalFn original=nullptr;
    BeforeFn before=nullptr;
    AfterFn after=nullptr;
    void* context=nullptr;
    volatile LONG binding=0; // 0=empty, 1=publishing immutable fields, 2=bound.
    volatile LONG fault=0;
    void Fault() noexcept { InterlockedExchange(&fault,1); }
public:
    Observer()=default;
    Observer(const Observer&)=delete;
    Observer& operator=(const Observer&)=delete;
    bool Bound() const noexcept {
        return InterlockedCompareExchange(const_cast<volatile LONG*>(&binding),0,0)==2;
    }
    bool Faulted() const noexcept {
        return InterlockedCompareExchange(const_cast<volatile LONG*>(&fault),0,0)!=0;
    }
    bool Bind(OriginalFn native,BeforeFn entering,AfterFn leaving,void* owner) noexcept {
        if(!native || !entering || !leaving || InterlockedCompareExchange(&binding,1,0)!=0)return false;
        original=native;before=entering;after=leaving;context=owner;
        InterlockedExchange(&binding,2);return true;
    }

    // Tickets, completion flags and LastError are local to each invocation.
    // No lock is held across either callback or the original; callbacks own any
    // metadata synchronization and may reenter. Ticket zero is a valid value.
    // Before failures propagate without calling the original. After runs once,
    // even if Before fails; beforeCompleted only means Before returned, not that
    // a Scale revoke succeeded. A future owner must check its own outcome.
    // After failures propagate on normal return. During an existing unwind only
    // secondary After failures are contained, preserving the primary exception.
    // LastError follows that primary/propagated failure; successful After leaves
    // the original's outgoing value intact. Faulted() is sticky, but does not
    // independently suppress later calls. Reentrant native failures follow the
    // same policy as direct failures; no exception-origin classification is used.
    __declspec(noinline) uint8_t Select(uintptr_t controller,int32_t selection,float blend,float frame) {
        const DWORD incomingError=GetLastError();
        if(!Bound()) {
            Fault();
            // Publishing an unbound entry is an installer programming error.
            // There is no original to forward and no invented success result.
            RaiseException(UnboundCallException,EXCEPTION_NONCONTINUABLE,0,nullptr);
            return 0;
        }
        uint64_t ticket=0;
        bool beforeCompleted=false,normalReturn=false;
        uint8_t result=0;
        __try {
            ticket=before(context,controller);
            beforeCompleted=true;
            SetLastError(incomingError);
            result=original(controller,selection,blend,frame);
            normalReturn=true;
        } __finally {
            const DWORD outgoingError=GetLastError();
            const bool unwinding=AbnormalTermination()!=FALSE;
            if(unwinding) {
                Fault();
                __try { after(context,controller,ticket,beforeCompleted,normalReturn); }
                __except(EXCEPTION_EXECUTE_HANDLER) { Fault(); }
                SetLastError(outgoingError);
            } else {
                bool afterCompleted=false;
                __try {
                    after(context,controller,ticket,beforeCompleted,normalReturn);
                    afterCompleted=true;
                } __finally {
                    const DWORD afterError=GetLastError();
                    if(!afterCompleted)Fault();
                    SetLastError(afterCompleted?outgoingError:afterError);
                }
            }
        }
        return result;
    }
};

template<Observer& Owner> struct Entrypoints {
    static __declspec(noinline) uint8_t __fastcall Select(uintptr_t controller,int32_t selection,float blend,float frame) {
        return Owner.Select(controller,selection,blend,frame);
    }
};
} // namespace motion_observer
