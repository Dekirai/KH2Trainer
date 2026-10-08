#pragma once
#include <windows.h>
#include <tlhelp32.h>
#include <stdint.h>
#include <string.h>

// Conservative bootstrap for the five STATUS writers. No game hook is installed
// here. The caller must prove their normal call closure cannot park an older
// writer on another stack and that every root retains its frame across helpers.
// Every possible root return PC, including ordinary data that happens to look
// like one, defers bootstrap. A negative scan requires the ENTIRE active stack.
// Concurrent foreign ResumeThread/SetThreadContext, custom stack switching and
// arbitrary exception callbacks are outside this native contract. Suspend
// counters cannot detect a foreign resume/re-suspend ABA during the copy.
// The byte limit bounds work, not wall time: paging/kernel waits can take longer.
namespace status_thread_drain {
constexpr unsigned RootCount=5,MaxThreads=1024;
constexpr size_t MaxStackBytes=2*1024*1024;
struct Range { uintptr_t begin=0,end=0; };
enum class Scan { Clear,PotentialWriter,Unknown };
enum class Capture { Complete,Exited,Unavailable,ExternalSuspend,TooLarge,ResumeFailed };
enum class Phase { Empty,Scanning,Drained,Fault,Closed };
using GateCheck=bool (*)(void*) noexcept;

inline bool Contains(const Range& r,uintptr_t pc) noexcept { return r.begin<=pc && pc<r.end; }
inline bool ValidRoots(const Range (&roots)[RootCount]) noexcept {
    for(unsigned i=0;i<RootCount;++i) {
        if(!roots[i].begin || roots[i].end<=roots[i].begin || roots[i].end-roots[i].begin>65536)return false;
        for(unsigned j=0;j<i;++j)if(roots[i].begin<roots[j].end && roots[j].begin<roots[i].end)return false;
    }
    return true;
}
inline bool ReadOwn(uintptr_t from,void* to,size_t bytes) noexcept {
    SIZE_T read=0;
    return from && bytes && bytes<=UINTPTR_MAX-from &&
        ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<const void*>(from),to,bytes,&read) && read==bytes;
}
struct Snapshot {
    Snapshot()=default;Snapshot(const Snapshot&)=delete;Snapshot& operator=(const Snapshot&)=delete;
    CONTEXT context{};
    uintptr_t low=0,high=0;
    unsigned char* bytes=nullptr;
    size_t capacity=0,size=0;
    bool complete=false;
    void Reset() noexcept { context={};low=high=0;size=0;complete=false; }
    // Allocate and touch storage BEFORE any suspension; never grow in Capture.
    bool Allocate(size_t wanted=MaxStackBytes) noexcept {
        if(bytes || !wanted || wanted>MaxStackBytes)return false;
        bytes=static_cast<unsigned char*>(VirtualAlloc(nullptr,wanted,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
        if(!bytes)return false;
        capacity=wanted;memset(bytes,0,wanted);return true;
    }
    void Free() noexcept { if(bytes)VirtualFree(bytes,0,MEM_RELEASE);bytes=nullptr;capacity=0;Reset(); }
};
inline Scan Inspect(const Snapshot& snapshot,const Range (&roots)[RootCount]) noexcept {
    if(!ValidRoots(roots) || !snapshot.complete || !snapshot.bytes ||
       (snapshot.context.ContextFlags&CONTEXT_FULL)!=CONTEXT_FULL || !snapshot.context.Rip ||
       snapshot.low!=snapshot.context.Rsp || (snapshot.low&7) || (snapshot.high&7) ||
       snapshot.high<=snapshot.low || snapshot.high-snapshot.low!=snapshot.size ||
       snapshot.size>snapshot.capacity || snapshot.size>MaxStackBytes)return Scan::Unknown;
    for(const auto& root:roots)if(Contains(root,snapshot.context.Rip))return Scan::PotentialWriter;
    for(size_t offset=0;offset<snapshot.size;offset+=sizeof(uintptr_t)) {
        uintptr_t value=0;memcpy(&value,snapshot.bytes+offset,sizeof(value));
        for(const auto& root:roots)if(Contains(root,value))return Scan::PotentialWriter;
    }
    return Scan::Clear;
}

struct ResumeDebt {
    HANDLE thread=nullptr;
    // A failed Resume never licenses closing this handle or discarding debt.
    bool owed=false;
    DWORD lastCount=DWORD(-1);
#ifdef KH2_STATUS_THREAD_DRAIN_TESTS
    unsigned testResumeFailures=0;
#endif
    bool Retry() noexcept {
        if(!owed)return true;
#ifdef KH2_STATUS_THREAD_DRAIN_TESTS
        if(testResumeFailures){--testResumeFailures;lastCount=DWORD(-1);return false;}
#endif
        lastCount=ResumeThread(thread);
        if(lastCount==DWORD(-1)) {
            if(WaitForSingleObject(thread,0)!=WAIT_OBJECT_0)return false;
        }
        owed=false;thread=nullptr;return true;
    }
};
// NtQueryInformationThread is resolved once, outside suspension. The basic-info
// ABI only supplies a TEB address; the active TIB is read AFTER suspension so a
// prior normal fiber change cannot leave stale stack bounds.
struct NativeThreadInfo {
    LONG exitStatus;PVOID teb;HANDLE processId,threadId;
    ULONG_PTR affinity;LONG priority,basePriority;
};
using QueryThread=LONG (NTAPI*)(HANDLE,ULONG,PVOID,ULONG,PULONG);
static_assert(sizeof(NativeThreadInfo)==48,"Win64 thread basic information ABI");
inline QueryThread ResolveQuery() noexcept {
    return reinterpret_cast<QueryThread>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"NtQueryInformationThread"));
}
inline uintptr_t QueryTeb(QueryThread query,HANDLE thread,DWORD id) noexcept {
    NativeThreadInfo info{};ULONG returned=0;
    if(!query || query(thread,0,&info,sizeof(info),&returned)<0 || returned!=sizeof(info) ||
       reinterpret_cast<uintptr_t>(info.processId)!=GetCurrentProcessId() ||
       reinterpret_cast<uintptr_t>(info.threadId)!=id || !info.teb)return 0;
    return reinterpret_cast<uintptr_t>(info.teb);
}
inline Capture CopyActiveStack(uintptr_t teb,Snapshot& snapshot) noexcept {
    NT_TIB tib{};
    if(!ReadOwn(teb,&tib,sizeof(tib)) || reinterpret_cast<uintptr_t>(tib.Self)!=teb)return Capture::Unavailable;
    const uintptr_t limit=reinterpret_cast<uintptr_t>(tib.StackLimit),top=reinterpret_cast<uintptr_t>(tib.StackBase);
    const uintptr_t sp=snapshot.context.Rsp;
    if(!limit || limit>=top || sp<limit || sp>=top || (sp&7) || (top&7) ||
       (snapshot.context.ContextFlags&CONTEXT_FULL)!=CONTEXT_FULL || !snapshot.context.Rip)return Capture::Unavailable;
    const size_t bytes=top-sp;
    if(bytes>snapshot.capacity || bytes>MaxStackBytes)return Capture::TooLarge;
    if(!ReadOwn(sp,snapshot.bytes,bytes))return Capture::Unavailable;
    snapshot.low=sp;snapshot.high=top;snapshot.size=bytes;snapshot.complete=true;return Capture::Complete;
}
inline Capture CaptureRemote(HANDLE thread,DWORD id,uintptr_t teb,Snapshot& snapshot,ResumeDebt& debt) noexcept {
    snapshot.Reset();
    if(!thread || !id || id==GetCurrentThreadId() || GetThreadId(thread)!=id ||
       GetProcessIdOfThread(thread)!=GetCurrentProcessId() || !teb || !snapshot.bytes || debt.owed)return Capture::Unavailable;
    if(WaitForSingleObject(thread,0)==WAIT_OBJECT_0)return Capture::Exited;
    const DWORD previous=SuspendThread(thread);
    if(previous==DWORD(-1))return WaitForSingleObject(thread,0)==WAIT_OBJECT_0?Capture::Exited:Capture::Unavailable;
    debt.thread=thread;debt.owed=true;debt.lastCount=DWORD(-1);
    Capture result=Capture::Unavailable;
    __try {
        if(previous)result=Capture::ExternalSuspend;
        else {
            snapshot.context.ContextFlags=CONTEXT_FULL;
            if(GetThreadContext(thread,&snapshot.context))result=CopyActiveStack(teb,snapshot);
        }
    } __finally {
        // Only context/memory reads and resume/exit-check APIs run
        // inside this interval. No metadata lock, heap, loader or unwind call.
        if(!debt.Retry())result=Capture::ResumeFailed;
        else if(debt.lastCount!=1 && result==Capture::Complete)result=Capture::ExternalSuspend;
        if(result!=Capture::Complete)snapshot.complete=false;
    }
    return result;
}
__declspec(noinline) inline Capture CaptureCurrent(Snapshot& snapshot) noexcept {
    snapshot.Reset();if(!snapshot.bytes)return Capture::Unavailable;
    RtlCaptureContext(&snapshot.context);
    // This function/frame remains alive while its stack is copied. All older
    // frames are stable; younger helper calls use addresses BELOW captured RSP.
    return CopyActiveStack(reinterpret_cast<uintptr_t>(NtCurrentTeb()),snapshot);
}

struct PollResult { Phase phase=Phase::Empty;unsigned remaining=0;DWORD thread=0;Capture capture=Capture::Unavailable;Scan scan=Scan::Unknown; };
class Drain {
    struct Thread { HANDLE handle=nullptr;DWORD id=0;uintptr_t teb=0;bool done=false; } threads[MaxThreads]{};
    Range roots[RootCount]{};
    Snapshot snapshot{};ResumeDebt debt{};
    GateCheck gates=nullptr;void* gateContext=nullptr;
    QueryThread query=nullptr;
    Phase phase=Phase::Empty;
    unsigned count=0,remaining=0,cursor=0;
    DWORD owner=0;
    HANDLE ownerHandle=nullptr;
    bool Verify() noexcept { return gates && gates(gateContext); }
    bool OnOwner() const noexcept {
        // The retained owner object must still be alive; a recycled DWORD ID
        // never transfers bootstrap authority to a newly created thread.
        return owner==GetCurrentThreadId() && ownerHandle && WaitForSingleObject(ownerHandle,0)==WAIT_TIMEOUT;
    }
    void Fail() noexcept { phase=Phase::Fault; }
public:
    Drain()=default;Drain(const Drain&)=delete;Drain& operator=(const Drain&)=delete;
    // Explicit Close is required; do not destroy the process-lifetime instance
    // while a resume debt exists. There is no implicit handle cleanup on fault.
    bool Begin(const Range (&writerRoots)[RootCount],GateCheck check,void* context) noexcept {
        if(phase!=Phase::Empty)return false;
        owner=GetCurrentThreadId();gates=check;gateContext=context;
        if(!ValidRoots(writerRoots) || !Verify()){Fail();return false;}
        memcpy(roots,writerRoots,sizeof(roots));query=ResolveQuery();
        if(!query || !snapshot.Allocate()){Fail();return false;}
        // Snapshot occurs after complete publication. Real retained handles,
        // rather than IDs, identify old thread lifetimes through later polls.
        const HANDLE list=CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD,0);
        if(list==INVALID_HANDLE_VALUE){Fail();return false;}
        THREADENTRY32 entry{};entry.dwSize=sizeof(entry);
        BOOL found=Thread32First(list,&entry);bool okay=found!=FALSE,hasOwner=false;
        while(found && okay) {
            if(entry.dwSize<sizeof(entry)){okay=false;break;}
            if(entry.th32OwnerProcessID==GetCurrentProcessId()) {
                const HANDLE handle=OpenThread(SYNCHRONIZE|THREAD_QUERY_INFORMATION|THREAD_GET_CONTEXT|THREAD_SUSPEND_RESUME,FALSE,entry.th32ThreadID);
                if(!handle) {
                    // A snapshot ID that no longer exists has ended; other
                    // access failures leave the old-thread set unproved.
                    if(GetLastError()!=ERROR_INVALID_PARAMETER)okay=false;
                } else if(count==MaxThreads) { CloseHandle(handle);okay=false; }
                else {
                    auto& saved=threads[count++];saved.handle=handle;saved.id=entry.th32ThreadID;
                    saved.done=WaitForSingleObject(handle,0)==WAIT_OBJECT_0;
                    if(!saved.done) {
                        saved.teb=QueryTeb(query,handle,saved.id);
                        if(!saved.teb && WaitForSingleObject(handle,0)==WAIT_OBJECT_0)saved.done=true;
                        else if(!saved.teb)okay=false;
                    }
                    if(!saved.done)++remaining;
                    hasOwner=hasOwner || saved.id==owner;
                    if(saved.id==owner)ownerHandle=handle;
                }
            }
            entry.dwSize=sizeof(entry);found=Thread32Next(list,&entry);
        }
        if(okay && GetLastError()!=ERROR_NO_MORE_FILES)okay=false;
        CloseHandle(list);
        if(!okay || !hasOwner || !Verify()){Fail();return false;}
        phase=remaining?Phase::Scanning:Phase::Drained;return true;
    }
    PollResult Poll(unsigned budget=1) noexcept {
        PollResult result{phase,remaining};
        if(!OnOwner() || !budget || budget>MaxThreads)return result;
        // Repay an unsuccessful resume before any other state-dependent work.
        if(debt.owed && !debt.Retry()){Fail();result.phase=phase;return result;}
        if(phase!=Phase::Scanning && phase!=Phase::Drained)return result;
        if(!Verify()){Fail();result.phase=phase;return result;}
        unsigned visited=0,probed=0;
        while(phase==Phase::Scanning && visited<count && probed<budget) {
            auto& thread=threads[cursor];cursor=(cursor+1)%count;++visited;
            if(thread.done)continue;
            ++probed;result.thread=thread.id;
            result.capture=thread.id==owner?CaptureCurrent(snapshot):CaptureRemote(thread.handle,thread.id,thread.teb,snapshot,debt);
            result.scan=result.capture==Capture::Complete?Inspect(snapshot,roots):Scan::Unknown;
            if(result.capture==Capture::ResumeFailed){Fail();break;}
            if(!Verify()){Fail();break;}
            if(result.capture==Capture::Exited || result.scan==Scan::Clear) {
                thread.done=true;--remaining;
                if(!remaining)phase=Phase::Drained;
            }
        }
        result.phase=phase;result.remaining=remaining;return result;
    }
    bool Ready() noexcept {
        if(!OnOwner() || phase!=Phase::Drained || debt.owed)return false;
        if(!Verify()){Fail();return false;}
        return true;
    }
    Phase Status() const noexcept { return phase; }
    unsigned Remaining() const noexcept { return remaining; }
    // Owner-thread query, deliberately without locks. While true, do not enter
    // metadata/loader/heap work: the retained suspended thread may hold its lock.
    // A foreign caller gets conservative pending without reading mutable debt.
    // Poll must continue servicing this even after Fault.
    bool ResumePending() const noexcept {
        return (owner && owner!=GetCurrentThreadId()) || debt.owed;
    }
#ifdef KH2_STATUS_THREAD_DRAIN_TESTS
    void TestFailNextResumes(unsigned failures) noexcept { debt.testResumeFailures=failures; }
#endif
    bool Close() noexcept {
        if(owner && owner!=GetCurrentThreadId())return false;
        if(debt.owed && !debt.Retry()){Fail();return false;}
        for(unsigned i=0;i<count;++i)if(threads[i].handle)CloseHandle(threads[i].handle);
        memset(threads,0,sizeof(threads));ownerHandle=nullptr;snapshot.Free();count=remaining=cursor=0;phase=Phase::Closed;return true;
    }
};
} // namespace status_thread_drain
