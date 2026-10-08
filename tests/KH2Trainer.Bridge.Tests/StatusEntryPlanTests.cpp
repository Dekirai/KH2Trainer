#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../../src/KH2Trainer.Bridge/StatusEntryPlan.h"
namespace {
using namespace status_entry_plan;
unsigned checks=0,failures=0;
void Check(bool value,const char* name) { ++checks;if(!value){++failures;printf("FAIL %s\n",name);} }
constexpr uintptr_t Module=0x140000000ull,Relay=Module+0x400000;
constexpr uint64_t OriginalB=0x1234123412341234ull,OriginalD=0x5678567856785678ull;
constexpr uint64_t OriginalS=0xABCDABCDABCDABCDull,ReturnPC=0x123456781000ull;
void Write64(uintptr_t p,uint64_t v) { memcpy(reinterpret_cast<void*>(p),&v,8); }
void Simulate(Kind k,unsigned offset,CONTEXT& c) {
    if(k==Kind::Init || k==Kind::Coefficient) {
        if(offset>=5)Write64(c.Rsp+8,c.Rbx);
    } else if(k==Kind::Rebuild) {
        if(offset>=2){c.Rsp-=8;Write64(c.Rsp,c.Rbx);}
        if(offset>=3){c.Rsp-=8;Write64(c.Rsp,c.Rdi);}
        if(offset>=7)c.Rsp-=40;
    } else if(k==Kind::Release) {
        if(offset>=2){c.Rsp-=8;Write64(c.Rsp,c.Rbx);}
        if(offset>=6)c.Rsp-=32;
    }
    // PoolReset's first instruction is an ordinary store with no stack effect.
}
void WindowsUnwind(Kind k,const Plan& plan) {
    auto* memory=static_cast<unsigned char*>(VirtualAlloc(nullptr,4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    Check(memory!=nullptr,"private unwind image allocation");if(!memory)return;
    memcpy(memory,plan.image,ImageSize);
    auto* fn=reinterpret_cast<PRUNTIME_FUNCTION>(memory+RuntimeOffset);
    Check(sizeof(*fn)==sizeof(RuntimeFunction),"AMD64 runtime record size");
    DWORD old=0;const bool protectedRx=VirtualProtect(memory,4096,PAGE_EXECUTE_READ,&old)!=FALSE;
    Check(protectedRx && old==PAGE_READWRITE,"private image becomes RX");
    if(!protectedRx){VirtualFree(memory,0,MEM_RELEASE);return;}
    const bool registered=RtlAddFunctionTable(fn,1,reinterpret_cast<DWORD64>(memory))!=FALSE;
    Check(registered,"register exact synthetic function table");
    if(registered) {
        for(unsigned i=0;i<=plan.boundaryCount;++i) {
            const unsigned offset=i==plan.boundaryCount?plan.prefixSize+10:plan.boundaries[i];
            alignas(16) unsigned char stack[4096];memset(stack,0xA5,sizeof(stack));
            const uintptr_t entrySp=reinterpret_cast<uintptr_t>(stack)+2040;
            CONTEXT context{};context.ContextFlags=CONTEXT_FULL;
            context.Rsp=entrySp;context.Rbx=OriginalB;context.Rdi=OriginalD;context.Rsi=OriginalS;
            context.Rip=reinterpret_cast<uintptr_t>(memory)+offset;
            Write64(entrySp,ReturnPC);Simulate(k,offset,context);
            // Poison saved registers only after the corresponding save completed.
            // This verifies the actual unwind slot, not merely an unchanged GPR.
            if((k==Kind::Init || k==Kind::Coefficient) && offset>=5)context.Rbx=0x11;
            if((k==Kind::Rebuild || k==Kind::Release) && offset>=2)context.Rbx=0x22;
            if(k==Kind::Rebuild && offset>=3)context.Rdi=0x33;
            unsigned char stackBefore[sizeof(stack)];memcpy(stackBefore,stack,sizeof(stack));
            DWORD64 imageBase=0;
            const auto* found=RtlLookupFunctionEntry(context.Rip,&imageBase,nullptr);
            Check(found==fn && imageBase==reinterpret_cast<DWORD64>(memory),"OS lookup resolves dynamic table");
            PVOID handlerData=nullptr;DWORD64 establisher=0;
            const auto handler=RtlVirtualUnwind(UNW_FLAG_NHANDLER,reinterpret_cast<DWORD64>(memory),
                context.Rip,fn,&context,&handlerData,&establisher,nullptr);
            if(context.Rsp!=entrySp+8 || context.Rip!=ReturnPC || context.Rbx!=OriginalB || context.Rdi!=OriginalD || context.Rsi!=OriginalS)
                printf("unwind kind=%u offset=%u rspDelta=%lld rip=%llx rbx=%llx rdi=%llx rsi=%llx\n",
                    static_cast<unsigned>(k),offset,static_cast<long long>(context.Rsp-entrySp),
                    context.Rip,context.Rbx,context.Rdi,context.Rsi);
            Check(handler==nullptr,"no synthetic exception handler");
            Check(context.Rsp==entrySp+8 && context.Rip==ReturnPC,"unwind restores caller stack and return");
            Check(context.Rbx==OriginalB && context.Rdi==OriginalD && context.Rsi==OriginalS,"unwind restores exact nonvolatile registers");
            Check(!memcmp(stack,stackBefore,sizeof(stack)),"unwind reads but does not alter synthetic stack");
            Check(!memcmp(memory,plan.image,ImageSize),"unwind preserves RX payload");
        }
        DWORD64 imageBase=0;
        Check(RtlLookupFunctionEntry(reinterpret_cast<uintptr_t>(memory)+plan.codeSize,&imageBase,nullptr)==nullptr,
            "address after trampoline is outside runtime code extent");
        Check(RtlDeleteFunctionTable(fn)!=FALSE,"unregister private table before freeing");
    }
    Check(VirtualFree(memory,0,MEM_RELEASE)!=FALSE,"release private image");
}
void Plans() {
    constexpr unsigned char Prefixes[]={5,7,5,10,6};
    for(unsigned n=0;n<static_cast<unsigned>(Kind::Count);++n) {
        const auto kind=static_cast<Kind>(n);const auto& d=*Get(kind);
        auto* input=static_cast<unsigned char*>(VirtualAlloc(nullptr,4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
        Check(input!=nullptr,"fingerprint fixture allocation");if(!input)return;
        memcpy(input,d.original,d.originalSize);DWORD old=0;
        Check(VirtualProtect(input,4096,PAGE_READONLY,&old)!=FALSE,"fingerprint fixture readonly");
        Plan p{};
        Check(Build(kind,Module,input,d.originalSize,0x180000000,Relay,p)==Error::None,"valid exact-build plan");
        Check(p.valid && p.prefixSize==Prefixes[n] && p.entry==Module+d.rva,"correct source boundary");
        Check(!memcmp(input,d.original,d.originalSize),"planner leaves original input untouched");
        Check(!memcmp(p.image,input,p.prefixSize),"trampoline preserves stolen prefix bytes");
        Check(p.image[p.prefixSize]==0x49 && p.image[p.prefixSize+1]==0xBB &&
            p.image[p.prefixSize+10]==0x41 && p.image[p.prefixSize+11]==0xFF && p.image[p.prefixSize+12]==0xE3,
            "absolute R11 tail uses non-epilog register-indirect jump");
        uint64_t destination=0;memcpy(&destination,p.image+p.prefixSize+2,8);
        Check(destination==p.entry+p.prefixSize,"absolute jump resumes exact continuation");
        int32_t delta=0;memcpy(&delta,p.entryPatch+1,4);
        Check(p.entryPatch[0]==0xE9 && p.entry+5+int64_t(delta)==Relay,"entry patch targets observer relay");
        bool padding=true;for(unsigned i=5;i<p.prefixSize;++i)padding=padding && p.entryPatch[i]==0x90;
        Check(padding,"whole-instruction patch tail padding");
        RuntimeFunction runtime{};memcpy(&runtime,p.image+RuntimeOffset,sizeof(runtime));
        Check(runtime.BeginAddress==0 && runtime.EndAddress==unsigned(p.prefixSize)+13 && runtime.UnwindData==UnwindOffset,
            "runtime code range covers both tail instructions");
        Check(p.image[UnwindOffset+1]==p.prefixSize,"unwind prolog describes exactly the copied instructions");
        for(unsigned offset=0;offset<=p.prefixSize;++offset) {
            uintptr_t mapped=0x1234;bool boundary=false;
            for(unsigned i=0;i+1<p.boundaryCount;++i)boundary=boundary || p.boundaries[i]==offset;
            const auto result=MapSuspendedInstruction(p,p.entry+offset,mapped);
            Check(result==(offset==p.prefixSize?Relocation::Outside:boundary?Relocation::Boundary:Relocation::InvalidInterior),
                "suspended IP classification covers every byte");
            Check(mapped==(boundary?p.trampoline+offset:0x1234),"only exact suspended boundaries are relocated");
        }
        uintptr_t mapped=0;Check(MapSuspendedInstruction(p,p.entry-1,mapped)==Relocation::Outside,"earlier PC untouched");
        WindowsUnwind(kind,p);
        Plan prior=p;
        Check(Build(kind,Module,input,d.originalSize-1,p.trampoline,Relay,p)==Error::InputSpan && !memcmp(&p,&prior,sizeof(p)),"short span rejects without output mutation");
        Check(Build(kind,Module,nullptr,d.originalSize,p.trampoline,Relay,p)==Error::InputSpan,"null input rejects");
        Check(Build(kind,UINTPTR_MAX,input,d.originalSize,p.trampoline,Relay,p)==Error::InvalidAddress,"module address overflow rejects");
        Check(Build(kind,Module,input,d.originalSize,UINTPTR_MAX-15,Relay,p)==Error::InvalidAddress,"image address overflow rejects");
        Check(Build(kind,Module,input,d.originalSize,0x180000001,Relay,p)==Error::InvalidAddress,"unaligned runtime image rejects");
        Check(Build(kind,Module,input,d.originalSize,p.entry,Relay,p)==Error::Alias,"trampoline inside original rejects");
        Check(Build(kind,Module,input,d.originalSize,p.trampoline,p.trampoline,p)==Error::Alias,"observer relay cannot equal original trampoline");
        Check(Build(kind,Module,input,d.originalSize,p.trampoline,p.entry,p)==Error::Alias,"observer relay cannot point into source");
        const uintptr_t next=p.entry+5;
        Check(Build(kind,Module,input,d.originalSize,p.trampoline,next+uint64_t(INT32_MAX)+1,p)==Error::RelayRange,"positive rel32 overflow rejects");
        Check(Build(kind,Module,input,d.originalSize,p.trampoline,next-uint64_t(INT32_MAX)-2,p)==Error::RelayRange,"negative rel32 overflow rejects");
        Check(Build(kind,Module,input,d.originalSize,p.trampoline,next+INT32_MAX,p)==Error::None,"max positive rel32 accepted");
        Check(Build(kind,Module,input,d.originalSize,p.trampoline,next-uint64_t(INT32_MAX)-1,p)==Error::None,"min negative rel32 accepted");
        VirtualProtect(input,4096,PAGE_READWRITE,&old);
        for(size_t i=0;i<d.originalSize;++i) {
            input[i]^=1;
            Check(Build(kind,Module,input,d.originalSize,0x180000000,Relay,p)==Error::Fingerprint,"every original body byte participates in fingerprint");
            input[i]^=1;
        }
        Check(VirtualFree(input,0,MEM_RELEASE)!=FALSE,"fingerprint fixture release");
    }
    Plan p{};uintptr_t mapped=17;
    Check(Build(Kind::Count,Module,nullptr,0,0,0,p)==Error::InvalidKind,"unknown entry rejected");
    Check(MapSuspendedInstruction(p,0,mapped)==Relocation::InvalidInterior && mapped==17,"unbuilt plan cannot relocate");
}
}
int main() { Plans();printf("StatusEntryPlanTests: %u checks, %u failures\n",checks,failures);return failures?1:0; }
