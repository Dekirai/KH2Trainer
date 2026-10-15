#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdio.h>
#include <string.h>
#ifndef MOTION_ORIGINAL_PRODUCTION_COMPILE
#define KH2_MOTION_ORIGINAL_TESTS
#endif
#include "../../src/KH2Trainer.Bridge/MotionOriginalTrampoline.h"
#ifdef MOTION_ORIGINAL_PRODUCTION_COMPILE
bool CompileMotionOriginal(motion_original::Image& image,uintptr_t base,motion_observer::OriginalFn& out) {
    if(!image.Prepare(base))return image.ReleaseUnpublished();
    return image.Bind(out);
}
#else
namespace {
unsigned checks=0,failures=0;
void Check(bool value,const char* name){++checks;if(!value){++failures;printf("FAIL %s\n",name);}}
constexpr size_t ModuleSize=4*1024*1024;
using Kind=motion_entry_plan::Kind;
const motion_entry_plan::Definition& Definition(){return *motion_entry_plan::Get(Kind::NormalBind);}
unsigned char* MakeModule() {
    auto* p=static_cast<unsigned char*>(VirtualAlloc(nullptr,ModuleSize,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(p)memcpy(p+Definition().rva,Definition().original,Definition().originalSize);
    return p;
}
bool Registered(uintptr_t entry) {
    DWORD64 base=0;auto* found=RtlLookupFunctionEntry(entry,&base,nullptr);
    return found==reinterpret_cast<PRUNTIME_FUNCTION>(entry+motion_entry_plan::RuntimeOffset)&&base==entry;
}
void CheckImage(const motion_original::Image& image,uintptr_t module) {
    MEMORY_BASIC_INFORMATION page{};const auto entry=image.Entry();
    Check(VirtualQuery(reinterpret_cast<void*>(entry),&page,sizeof(page))==sizeof(page)&&page.Protect==PAGE_EXECUTE_READ,"original-call allocation is RX");
    motion_entry_plan::Plan plan{};
    Check(motion_entry_plan::BuildBreakpoint(Kind::NormalBind,module,reinterpret_cast<void*>(module+Definition().rva),Definition().originalSize,entry,plan)==motion_entry_plan::Error::None,"allocated address has an exact valid plan");
    Check(!memcmp(reinterpret_cast<void*>(entry),plan.image,sizeof(plan.image)),"code and unwind metadata match plan");
    Check(Registered(entry),"Windows resolves the actual dynamic function table");
    Check(!memcmp(reinterpret_cast<void*>(module+Definition().rva),Definition().original,Definition().originalSize),"preparation leaves synthetic source unchanged");
}
void Failures(uintptr_t module) {
    using namespace motion_original;
    Image invalid;motion_observer::OriginalFn blank=nullptr;
    Check(!invalid.Prepare(1)&&invalid.LastError()==Error::Source,"unreadable source rejected");
    Check(!invalid.Bind(blank)&&!blank,"failure publishes no original");
    Check(invalid.ReleaseUnpublished()&&invalid.Status()==State::Closed,"failed image closes explicitly");
    auto* bytes=reinterpret_cast<unsigned char*>(module+Definition().rva);
    bytes[Definition().originalSize-1]^=1;
    Image changed;
    Check(!changed.Prepare(module)&&changed.LastError()==Error::Plan&&!changed.Entry(),"changed tail byte rejects full-body fingerprint and rolls back");
    bytes[Definition().originalSize-1]^=1;
    Image add;add.testFailAdd=true;
    Check(!add.Prepare(module)&&add.LastError()==Error::Register&&!add.Entry(),"registration failure frees unpublished code");
    Check(add.testAddCalls==1&&add.testDeleteCalls==0&&add.testFreeCalls==1,"failed registration creates no dangling OS table");
    Image remove;Check(remove.Prepare(module),"prepare deletion failure fixture");const auto retained=remove.Entry();remove.testFailDelete=true;
    Check(!remove.ReleaseUnpublished()&&remove.LastError()==Error::Unregister&&remove.Entry()==retained,"failed table deletion retains exact allocation");
    Check(remove.testFreeCalls==0&&Registered(retained),"registered unwind storage is never freed");
    Check(!remove.Bind(blank)&&!blank,"partially failed cleanup cannot publish");
    remove.testFailDelete=false;
    Check(remove.ReleaseUnpublished()&&!remove.Entry()&&!Registered(retained),"deletion can be retried without dangling registration");
    Image free;Check(free.Prepare(module),"prepare free failure fixture");const auto allocation=free.Entry();free.testFailFree=true;
    Check(!free.ReleaseUnpublished()&&free.LastError()==Error::Free&&free.Entry()==allocation,"failed free retains allocation for retry");
    Check(!Registered(allocation)&&free.testDeleteCalls==1,"registration is gone before failed free");
    free.testFailFree=false;
    Check(free.ReleaseUnpublished()&&free.testDeleteCalls==1&&free.testFreeCalls==2,"free retry does not delete table twice");
}

motion_observer::Observer observer;
struct Call {
    uintptr_t controller=0;int32_t id=0;uint32_t blend=0,frame=0;
    unsigned before=0,original=0,after=0;bool expectException=false;
} call;
constexpr DWORD InputError=0x13572468,OutputError=0x24681357,FixtureException=0xe0214321;
uint32_t Bits(float v){uint32_t b;memcpy(&b,&v,4);return b;}
float Float(uint32_t b){float v;memcpy(&v,&b,4);return v;}
uint64_t __fastcall Before(void*,uintptr_t controller) {
    Check(controller==call.controller&&call.original==0&&call.after==0,"Before runs synchronously before original continuation");
    ++call.before;SetLastError(777);return 0x123456789abcdef0ULL;
}
void __fastcall After(void*,uintptr_t controller,uint64_t ticket,bool completed,bool normal) {
    Check(controller==call.controller&&ticket==0x123456789abcdef0ULL&&completed,"After receives this call's exact ticket");
    Check(call.before==1&&call.original==1&&normal!=call.expectException,"After observes original normal/exception outcome");
    ++call.after;SetLastError(888);
}
__declspec(noinline) uint8_t __fastcall FixtureOriginal(uintptr_t controller,int32_t id,float blend,float frame) {
    Check(controller==call.controller&&id==call.id,"trampoline preserves integer arguments");
    Check(Bits(blend)==call.blend&&Bits(frame)==call.frame,"trampoline and typed wrapper preserve float bits");
    Check(call.before==1&&call.after==0,"original runs after Before and before After");
    Check(GetLastError()==InputError,"Before preserves incoming LastError for original");
    ++call.original;SetLastError(OutputError);
    if(call.expectException)RaiseException(FixtureException,0,0,nullptr);
    return static_cast<uint8_t>(id&1);
}
DWORD CallWithException() {
    __try {motion_observer::Entrypoints<observer>::Select(call.controller,call.id,Float(call.blend),Float(call.frame));}
    __except(EXCEPTION_EXECUTE_HANDLER){return GetExceptionCode();}
    return 0;
}
void ExecutePrivatePrefix(unsigned char* module) {
    // The private module initially contains exact original bytes for Prepare.
    // After that check, replace ONLY this synthetic module's continuation with
    // a tail jump to FixtureOriginal. Thus the real copied five-byte prolog and
    // generated trampoline execute, but no game body, resource or global runs.
    // This fixture does not claim original-body execution or live hook safety.
    motion_observer::OriginalFn escaped=nullptr;uintptr_t entry=0;
    {
        motion_original::Image temporary;
        Check(temporary.Prepare(reinterpret_cast<uintptr_t>(module)),"prepare private executed prefix");
        CheckImage(temporary,reinterpret_cast<uintptr_t>(module));
        Check(temporary.Bind(escaped)&&escaped,"bind typed original before wrapper publication");entry=temporary.Entry();
        Check(!temporary.ReleaseUnpublished()&&temporary.Status()==motion_original::State::Bound,"published original has process lifetime");
        Check(temporary.testDeleteCalls==0&&temporary.testFreeCalls==0,"bound image never tears down OS storage");
    }
    Check(Registered(entry),"dynamic table survives owner object lifetime");
    auto* continuation=module+Definition().rva+Definition().prefixSize;
    unsigned char jump[12]={0x48,0xb8};const uintptr_t target=reinterpret_cast<uintptr_t>(&FixtureOriginal);
    memcpy(jump+2,&target,8);jump[10]=0xff;jump[11]=0xe0;memcpy(continuation,jump,sizeof(jump));
    DWORD old=0;Check(VirtualProtect(module,ModuleSize,PAGE_EXECUTE_READ,&old)!=FALSE,"private continuation becomes RX");
    Check(FlushInstructionCache(GetCurrentProcess(),module,ModuleSize)!=FALSE,"private continuation instruction cache flushed");
    Check(observer.Bind(escaped,&Before,&After,nullptr),"bind wrapper to registered typed trampoline");
    const uint32_t patterns[]={0,0x80000000,0x3f800000,0xbf800000,0x00000001,0x7f800000,0xff800000,0x7fc12345};
    for(unsigned i=0;i<sizeof(patterns)/sizeof(patterns[0]);++i) {
        call={};call.controller=0x1234567890ULL+i;call.id=-31+static_cast<int32_t>(i);call.blend=patterns[i];call.frame=patterns[7-i];
        SetLastError(InputError);
        const auto result=motion_observer::Entrypoints<observer>::Select(call.controller,call.id,Float(call.blend),Float(call.frame));
        Check(result==static_cast<uint8_t>(call.id&1),"AL result is forwarded exactly");
        Check(call.before==1&&call.original==1&&call.after==1,"one original and one before/after per routed call");
        Check(GetLastError()==OutputError,"After preserves original LastError");
    }
    Check(!observer.Faulted(),"successful private calls leave observer healthy");
    call={};call.controller=0x1234567800ULL;call.id=INT32_MIN;call.blend=0x80000000;call.frame=0x7fc12345;call.expectException=true;
    SetLastError(InputError);
    Check(CallWithException()==FixtureException,"original SEH traverses compiled wrapper and retains its code");
    Check(call.before==1&&call.original==1&&call.after==1&&observer.Faulted(),"exception path calls After once and faults observation");
}
}
int main() {
    auto* module=MakeModule();Check(module!=nullptr,"private source module allocated");if(!module)return 1;
    Failures(reinterpret_cast<uintptr_t>(module));
    ExecutePrivatePrefix(module);
    // Published source, executable image and unwind table stay until this
    // isolated test process exits, exactly as required by the binding contract.
    printf("MotionOriginalTrampolineTests: %u checks, %u failures. Private original prefix and fixture continuation only.\n",checks,failures);
    return failures?1:0;
}
#endif
