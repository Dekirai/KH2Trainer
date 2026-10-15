#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../../src/KH2Trainer.Bridge/MotionEntryPlan.h"

namespace {
using namespace motion_entry_plan;
unsigned checks=0,failures=0;
void Check(bool value,const char* name) { ++checks;if(!value){++failures;printf("FAIL %s\n",name);} }
constexpr uintptr_t Module=0x140000000ull,Entry=Module+0x3C8CD0;
constexpr uintptr_t Trampoline=0x180000000ull,Relay=Module+0x400000;
constexpr uint64_t SavedB=0x123456789ABCDEF0ull,ReturnPC=0x123456781000ull;
void Write64(uintptr_t p,uint64_t value) { memcpy(reinterpret_cast<void*>(p),&value,sizeof(value)); }
bool Same(const Plan& a,const Plan& b) { return !memcmp(&a,&b,sizeof(a)); }

// Windows consumes private code/unwind metadata; none of the planned code is run.
void Unwind(const Plan& plan) {
    auto* page=static_cast<unsigned char*>(VirtualAlloc(nullptr,4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    Check(page!=nullptr,"allocate private unwind fixture");if(!page)return;
    memcpy(page,plan.image,ImageSize);
    auto* function=reinterpret_cast<PRUNTIME_FUNCTION>(page+RuntimeOffset);
    DWORD old=0;
    if(!VirtualProtect(page,4096,PAGE_EXECUTE_READ,&old)) {
        Check(false,"protect private unwind fixture");VirtualFree(page,0,MEM_RELEASE);return;
    }
    Check(old==PAGE_READWRITE,"private fixture becomes RX");
    const bool registered=RtlAddFunctionTable(function,1,reinterpret_cast<DWORD64>(page))!=FALSE;
    Check(registered,"register private runtime function");
    if(registered) {
        // Entry, copied-prefix completion, and the register-indirect tail JMP.
        const unsigned offsets[]={0,5,15};
        for(unsigned offset:offsets) {
            alignas(16) unsigned char stack[512];memset(stack,0xA5,sizeof(stack));
            const uintptr_t sp=reinterpret_cast<uintptr_t>(stack)+248;
            CONTEXT c{};c.ContextFlags=CONTEXT_FULL;c.Rsp=sp;c.Rbx=SavedB;
            c.Rdi=0x2345;c.Rsi=0x3456;c.Rbp=0x4567;c.R12=0x5678;
            c.R13=0x6789;c.R14=0x789A;c.R15=0x89AB;
            c.Xmm6={0xAABB,0x1122};c.Xmm7={0xCCDD,0x3344};
            c.Rip=reinterpret_cast<uintptr_t>(page)+offset;
            Write64(sp,ReturnPC);
            if(offset>=5) { Write64(sp+8,SavedB);c.Rbx=0xDEAD; }
            unsigned char before[sizeof(stack)];memcpy(before,stack,sizeof(stack));
            DWORD64 imageBase=0;
            Check(RtlLookupFunctionEntry(c.Rip,&imageBase,nullptr)==function && imageBase==reinterpret_cast<DWORD64>(page),
                "OS lookup resolves exact private code range");
            PVOID handlerData=nullptr;DWORD64 establisher=0;
            const auto handler=RtlVirtualUnwind(UNW_FLAG_NHANDLER,imageBase,c.Rip,function,&c,&handlerData,&establisher,nullptr);
            Check(handler==nullptr,"no exception handler in planned unwind");
            Check(c.Rsp==sp+8 && c.Rip==ReturnPC,"unwind restores caller stack and return");
            Check(c.Rbx==SavedB,"unwind restores RBX from its actual saved slot");
            Check(c.Rdi==0x2345 && c.Rsi==0x3456 && c.Rbp==0x4567 && c.R12==0x5678 &&
                c.R13==0x6789 && c.R14==0x789A && c.R15==0x89AB,"untouched nonvolatile GPRs stay intact");
            Check(c.Xmm6.Low==0xAABB && c.Xmm6.High==0x1122 && c.Xmm7.Low==0xCCDD && c.Xmm7.High==0x3344,
                "copied prefix does not unwind later original XMM saves");
            Check(!memcmp(stack,before,sizeof(stack)),"unwind only reads synthetic stack");
            Check(!memcmp(page,plan.image,ImageSize),"unwind leaves private RX image unchanged");
        }
        DWORD64 imageBase=0;
        Check(RtlLookupFunctionEntry(reinterpret_cast<uintptr_t>(page)+plan.codeSize,&imageBase,nullptr)==nullptr,
            "runtime range excludes unwind data and padding");
        const bool deleted=RtlDeleteFunctionTable(function)!=FALSE;
        Check(deleted,"unregister private table");
        // Keep registered storage alive if deletion ever fails.
        if(!deleted)return;
    }
    Check(VirtualFree(page,0,MEM_RELEASE)!=FALSE,"release private unwind fixture");
}

void Reject(Error expected,Kind kind,uintptr_t module,const void* input,size_t size,
    uintptr_t trampoline,uintptr_t relay,Plan& plan,bool breakpoint=false) {
    const Plan before=plan;
    const Error error=BuildPlan(kind,module,input,size,trampoline,relay,plan,breakpoint);
    Check(error==expected,"invalid plan returns specific error");
    Check(Same(plan,before),"failed plan preserves every output byte");
}

void Plans() {
    const auto* d=Get(Kind::NormalBind);
    Check(d && d->rva==0x3C8CD0 && d->originalSize==287,"exact entry definition and whole body extent");
    if(!d)return;
    Check(Get(Kind::Count)==nullptr && Get(static_cast<Kind>(UINT32_MAX))==nullptr,"unknown kinds have no definition");
    SYSTEM_INFO info{};GetSystemInfo(&info);const size_t pageSize=info.dwPageSize;
    auto* allocation=static_cast<unsigned char*>(VirtualAlloc(nullptr,pageSize*2,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    Check(allocation!=nullptr,"allocate guarded fingerprint fixture");if(!allocation)return;
    auto* input=allocation+pageSize-d->originalSize;memcpy(input,d->original,d->originalSize);
    DWORD old=0;
    Check(VirtualProtect(allocation+pageSize,pageSize,PAGE_NOACCESS,&old)!=FALSE,"guard immediately after complete source body");
    Check(VirtualProtect(allocation,pageSize,PAGE_READONLY,&old)!=FALSE,"source fixture readonly");
    Plan plan{};
    Check(Build(Kind::NormalBind,Module,input,d->originalSize,Trampoline,Relay,plan)==Error::None,"build relative-entry plan");
    Check(plan.valid && plan.entry==Entry && plan.trampoline==Trampoline && plan.relay==Relay,"planned addresses");
    Check(plan.prefixSize==5 && plan.codeSize==18 && plan.patchSize==5 && plan.boundaryCount==2,
        "minimal whole-instruction prefix and complete tail extent");
    const unsigned char prefix[]={0x48,0x89,0x5C,0x24,0x08};
    Check(!memcmp(plan.image,prefix,sizeof(prefix)),"one MOV home-slot save copied exactly");
    Check(plan.boundaries[0]==0 && plan.boundaries[1]==5,"exact prefix instruction boundaries");
    Check(plan.image[5]==0x49 && plan.image[6]==0xBB && plan.image[15]==0x41 && plan.image[16]==0xFF && plan.image[17]==0xE3,
        "MOV R11 and mod11 JMP preserve Windows unwind interpretation");
    uint64_t continuation=0;memcpy(&continuation,plan.image+7,8);
    Check(continuation==Entry+5,"absolute continuation follows copied MOV");
    int32_t displacement=0;memcpy(&displacement,plan.entryPatch+1,4);
    Check(plan.entryPatch[0]==0xE9 && Entry+5+int64_t(displacement)==Relay,"rel32 patch targets separate relay");
    const unsigned char unwind[]={1,5,2,0,5,0x34,1,0};
    Check(plan.unwindSize==sizeof(unwind) && !memcmp(plan.image+UnwindOffset,unwind,sizeof(unwind)),
        "only copied RBX save appears in unwind metadata");
    RuntimeFunction runtime{};memcpy(&runtime,plan.image+RuntimeOffset,sizeof(runtime));
    Check(runtime.BeginAddress==0 && runtime.EndAddress==18 && runtime.UnwindData==32,"runtime range includes both tail instructions");
    Check(!memcmp(input,d->original,d->originalSize),"successful planner preserves readonly source");
    for(unsigned offset=0;offset<=6;++offset) {
        uintptr_t mapped=0xDEAD;
        const auto actual=MapSuspendedInstruction(plan,Entry+offset,mapped);
        const auto expected=offset==0?Relocation::Boundary:offset<5?Relocation::InvalidInterior:Relocation::Outside;
        Check(actual==expected,"every prefix byte and continuation classified");
        Check(mapped==(offset==0?Trampoline:0xDEAD),"only complete copied instruction entry remapped");
    }
    uintptr_t mapped=0xBEEF;
    Check(MapSuspendedInstruction(plan,Entry-1,mapped)==Relocation::Outside && mapped==0xBEEF,"preceding instruction untouched");
    Unwind(plan);
    Plan breakpoint{};
    Check(BuildBreakpoint(Kind::NormalBind,Module,input,d->originalSize,Trampoline,breakpoint)==Error::None,"build permanent breakpoint plan");
    Check(breakpoint.patchSize==1 && breakpoint.entryPatch[0]==0xCC && breakpoint.relay==0,"breakpoint replaces only first byte");
    Check(!memcmp(breakpoint.image,plan.image,ImageSize),"both entry strategies have identical original-call image");
    bool zeros=true;for(unsigned i=1;i<sizeof(breakpoint.entryPatch);++i)zeros=zeros && !breakpoint.entryPatch[i];
    Check(zeros,"breakpoint patch has no trailing writes");

    Reject(Error::InvalidKind,Kind::Count,Module,input,d->originalSize,Trampoline,Relay,plan);
    Reject(Error::InvalidKind,static_cast<Kind>(UINT32_MAX),Module,input,d->originalSize,Trampoline,Relay,plan);
    Reject(Error::InvalidAddress,Kind::NormalBind,0,input,d->originalSize,Trampoline,Relay,plan);
    Reject(Error::InvalidAddress,Kind::NormalBind,UINTPTR_MAX,input,d->originalSize,Trampoline,Relay,plan);
    Reject(Error::InvalidAddress,Kind::NormalBind,UINTPTR_MAX-d->rva-10,input,d->originalSize,Trampoline,Relay,plan);
    Reject(Error::InvalidAddress,Kind::NormalBind,Module,input,d->originalSize,0,Relay,plan);
    Reject(Error::InvalidAddress,Kind::NormalBind,Module,input,d->originalSize,Trampoline+1,Relay,plan);
    Reject(Error::InvalidAddress,Kind::NormalBind,Module,input,d->originalSize,UINTPTR_MAX-15,Relay,plan);
    Reject(Error::InvalidAddress,Kind::NormalBind,Module,input,d->originalSize,Trampoline,0,plan);
    Reject(Error::InvalidAddress,Kind::NormalBind,Module,input,d->originalSize,Trampoline,UINTPTR_MAX-12,plan);
    Reject(Error::InvalidAddress,Kind::NormalBind,Module,input,d->originalSize,Trampoline,Relay,plan,true);
    Reject(Error::InputSpan,Kind::NormalBind,Module,nullptr,d->originalSize,Trampoline,Relay,plan);
    Reject(Error::InputSpan,Kind::NormalBind,Module,reinterpret_cast<const void*>(UINTPTR_MAX-1),d->originalSize,Trampoline,Relay,plan);
    for(size_t size=0;size<d->originalSize;++size)
        Reject(Error::InputSpan,Kind::NormalBind,Module,input,size,Trampoline,Relay,plan);
    Reject(Error::Alias,Kind::NormalBind,Module,input,d->originalSize,Entry,Relay,plan);
    Reject(Error::Alias,Kind::NormalBind,Module,input,d->originalSize,Entry-16,Relay,plan);
    Reject(Error::Alias,Kind::NormalBind,Module,input,d->originalSize,Trampoline,Entry,plan);
    Reject(Error::Alias,Kind::NormalBind,Module,input,d->originalSize,Trampoline,Entry-13,plan);
    Reject(Error::Alias,Kind::NormalBind,Module,input,d->originalSize,Trampoline,Trampoline+ImageSize-1,plan);
    Reject(Error::Alias,Kind::NormalBind,Module,input,d->originalSize,Trampoline,Trampoline-13,plan);
    Reject(Error::Alias,Kind::NormalBind,Module,&plan,d->originalSize,Trampoline,Relay,plan);
    Reject(Error::RelayRange,Kind::NormalBind,Module,input,d->originalSize,Trampoline,Entry+5+uint64_t(INT32_MAX)+1,plan);
    Reject(Error::RelayRange,Kind::NormalBind,Module,input,d->originalSize,Trampoline,Entry+5-uint64_t(INT32_MAX)-2,plan);
    Check(Build(Kind::NormalBind,Module,input,d->originalSize,Trampoline,Entry+5+INT32_MAX,plan)==Error::None,"max positive rel32");
    memcpy(&displacement,plan.entryPatch+1,4);Check(displacement==INT32_MAX,"positive boundary encoded exactly");
    Check(Build(Kind::NormalBind,Module,input,d->originalSize,Trampoline,Entry+5-uint64_t(INT32_MAX)-1,plan)==Error::None,"min negative rel32");
    memcpy(&displacement,plan.entryPatch+1,4);Check(displacement==INT32_MIN,"negative boundary encoded exactly");
    // A larger advertised span must not cause even a one-byte read past the body.
    Check(BuildBreakpoint(Kind::NormalBind,Module,input,SIZE_MAX,Trampoline,plan)==Error::None,"fingerprint reads exact extent despite larger advertised span");
    Check(VirtualProtect(allocation,pageSize,PAGE_READWRITE,&old)!=FALSE,"make synthetic source mutable for mismatch cases");
    for(size_t i=0;i<d->originalSize;++i) {
        input[i]^=1;
        Reject(Error::Fingerprint,Kind::NormalBind,Module,input,d->originalSize,Trampoline,Relay,plan);
        Reject(Error::Fingerprint,Kind::NormalBind,Module,input,d->originalSize,Trampoline,0,plan,true);
        input[i]^=1;
    }
    Check(VirtualFree(allocation,0,MEM_RELEASE)!=FALSE,"release guarded source fixture");
    Plan invalid{};mapped=0xFEED;
    Check(MapSuspendedInstruction(invalid,Entry,mapped)==Relocation::InvalidInterior && mapped==0xFEED,"unbuilt plan rejects mapping");
    invalid=plan;invalid.boundaryCount=255;
    Check(MapSuspendedInstruction(invalid,Entry,mapped)==Relocation::InvalidInterior && mapped==0xFEED,"malformed boundary count cannot read past array");
    invalid=plan;invalid.prefixSize=255;
    Check(MapSuspendedInstruction(invalid,Entry,mapped)==Relocation::InvalidInterior,"malformed prefix rejects mapping");
    invalid=plan;invalid.boundaries[1]=4;
    Check(MapSuspendedInstruction(invalid,Entry,mapped)==Relocation::InvalidInterior,"interior continuation rejects mapping");
}
}
int main() { Plans();printf("MotionEntryPlanTests: %u checks, %u failures\n",checks,failures);return failures?1:0; }
