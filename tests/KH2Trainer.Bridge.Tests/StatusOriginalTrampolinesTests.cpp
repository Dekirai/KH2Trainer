#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdio.h>
#ifndef STATUS_ORIGINALS_PRODUCTION_COMPILE
#define KH2_STATUS_ORIGINALS_TESTS
#endif
#include "../../src/KH2Trainer.Bridge/StatusOriginalTrampolines.h"
#ifdef STATUS_ORIGINALS_PRODUCTION_COMPILE
bool CompileOriginals(status_originals::Batch& batch,uintptr_t source,status_observer::Originals& out) {
    if(!batch.Prepare(source))return batch.ReleaseUnpublished();
    return batch.Bindings(out);
}
#else
namespace {
using status_entry_plan::Kind;
unsigned checks=0,failures=0;
void Check(bool value,const char* name){++checks;if(!value){++failures;printf("FAIL %s\n",name);}}
constexpr size_t ModuleSize=4*1024*1024;
unsigned char* MakeModule() {
    auto* p=static_cast<unsigned char*>(VirtualAlloc(nullptr,ModuleSize,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(!p)return nullptr;
    for(unsigned i=0;i<status_originals::Count;++i) {
        const auto& d=*status_entry_plan::Get(static_cast<Kind>(i));memcpy(p+d.rva,d.original,d.originalSize);
    }
    return p;
}
void CheckImages(status_originals::Batch& batch,uintptr_t source) {
    for(unsigned i=0;i<status_originals::Count;++i) {
        const auto kind=static_cast<Kind>(i);const auto& d=*status_entry_plan::Get(kind);const auto address=batch.Entry(kind);
        MEMORY_BASIC_INFORMATION page{};
        Check(VirtualQuery(reinterpret_cast<void*>(address),&page,sizeof(page))==sizeof(page) && page.Protect==PAGE_EXECUTE_READ,
            "published original image is RX");
        status_entry_plan::Plan expected{};
        Check(status_entry_plan::BuildBreakpoint(kind,source,reinterpret_cast<const unsigned char*>(source+d.rva),d.originalSize,address,expected)==status_entry_plan::Error::None,
            "exact original planner agrees with allocated address");
        Check(!memcmp(reinterpret_cast<const void*>(address),expected.image,sizeof(expected.image)),"generated code and unwind bytes match verified plan");
        DWORD64 base=0;auto* runtime=RtlLookupFunctionEntry(address,&base,nullptr);
        Check(runtime==reinterpret_cast<PRUNTIME_FUNCTION>(address+status_entry_plan::RuntimeOffset) && base==address,
            "real Windows lookup resolves each independently registered original");
        Check(!memcmp(reinterpret_cast<const void*>(source+d.rva),d.original,d.originalSize),"source body not patched by preparation");
    }
}
bool RegisteredAt(uintptr_t address) {
    DWORD64 base=0;auto* entry=RtlLookupFunctionEntry(address,&base,nullptr);
    return entry==reinterpret_cast<PRUNTIME_FUNCTION>(address+status_entry_plan::RuntimeOffset)&&base==address;
}
void CheckRetainedBytes(status_originals::Batch& batch,uintptr_t source) {
    for(unsigned i=0;i<status_originals::Count;++i) {
        const auto kind=static_cast<Kind>(i);const auto& d=*status_entry_plan::Get(kind);const uintptr_t address=batch.Entry(kind);
        status_entry_plan::Plan expected{};
        Check(status_entry_plan::BuildBreakpoint(kind,source,reinterpret_cast<void*>(source+d.rva),d.originalSize,address,expected)==status_entry_plan::Error::None,
            "retained image still has a valid exact original plan");
        Check(!memcmp(reinterpret_cast<void*>(address),expected.image,sizeof(expected.image)),"all retained code and unwind/table bytes unchanged after cleanup failure");
        MEMORY_BASIC_INFORMATION page{};
        Check(VirtualQuery(reinterpret_cast<void*>(address),&page,sizeof(page))==sizeof(page)&&page.State==MEM_COMMIT&&page.Protect==PAGE_EXECUTE_READ,
            "cleanup failure retains complete RX allocation");
    }
}
void FailurePaths(uintptr_t source) {
    using namespace status_originals;
    for(int fail=0;fail<static_cast<int>(Count);++fail) {
        Batch batch;batch.testFailAddAt=fail;
        Check(!batch.Prepare(source)&&batch.Status()==State::Fault&&batch.LastError()==Error::Register,
            "one injected registration failure rejects preparation");
        Check(batch.testAddCalls==fail+1&&batch.testDeleteCalls==fail&&batch.testFreeCalls==1,
            "partial Add failure deletes every successful real registration once");
        Check(batch.Entry(Kind::Init)==0&&batch.testLastAllocation,"successful registration rollback frees unpublished allocation");
        for(unsigned i=0;i<Count;++i)Check(!RegisteredAt(batch.testLastAllocation+PageSize*i),"partial registration rollback leaves no OS function-table entry");
        Check(batch.ReleaseUnpublished()&&batch.Status()==State::Closed,"fully rolled back batch can close without a second free");
    }
    for(int fail=0;fail<static_cast<int>(Count);++fail) {
        Batch batch;Check(batch.Prepare(source),"prepare real tables for injected deletion failure");
        const uintptr_t address=batch.Entry(Kind::Init);batch.testFailDeleteAt=fail;
        Check(!batch.ReleaseUnpublished()&&batch.Status()==State::Fault&&batch.LastError()==Error::Unregister,
            "failed real-table deletion reports retained cleanup state");
        Check(batch.Entry(Kind::Init)==address&&batch.testFreeCalls==0,"any live OS table forbids freeing allocation");
        for(unsigned i=0;i<Count;++i)Check(RegisteredAt(address+PageSize*i)==(i==static_cast<unsigned>(fail)),
            "only injected failed deletion remains registered with actual Windows lookup");
        CheckRetainedBytes(batch,source);
        status_observer::Originals out{};Check(!batch.Bindings(out)&&!out.initialize,"partial cleanup cannot publish callable originals");
        batch.testFailDeleteAt=-1;
        Check(batch.ReleaseUnpublished()&&batch.Status()==State::Closed&&batch.LastError()==Error::None,
            "unpublished cleanup retries remaining registration and closes");
        Check(batch.testDeleteCalls==static_cast<int>(Count)+1&&batch.testFreeCalls==1&&batch.Entry(Kind::Init)==0,
            "retry deletes only still-registered table and frees once");
        for(unsigned i=0;i<Count;++i)Check(!RegisteredAt(address+PageSize*i),"successful cleanup retry leaves no registered table");
    }
    for(int fail=1;fail<static_cast<int>(Count);++fail) {
        Batch batch;batch.testFailAddAt=fail;batch.testFailDeleteAt=fail-1;
        Check(!batch.Prepare(source)&&batch.LastError()==Error::Unregister&&batch.Entry(Kind::Init)!=0,
            "registration failure with rollback failure retains owning allocation");
        CheckRetainedBytes(batch,source);const uintptr_t address=batch.Entry(Kind::Init);
        for(unsigned i=0;i<Count;++i)Check(RegisteredAt(address+PageSize*i)==(i==static_cast<unsigned>(fail-1)),
            "combined Add/Delete failure keeps precisely the unresolved registration");
        Check(batch.testFreeCalls==0,"combined rollback failure never frees registered storage");
        batch.testFailDeleteAt=-1;Check(batch.ReleaseUnpublished()&&batch.Entry(Kind::Init)==0,"combined failure supports explicit unpublished retry");
    }
    for(unsigned mode=0;mode<2;++mode) {
        Batch batch;batch.testFailFreeAt=0;
        if(mode) {
            batch.testFailAddAt=2;Check(!batch.Prepare(source)&&batch.LastError()==Error::Free,"rollback free failure reports final unresolved cleanup error");
        } else {Check(batch.Prepare(source),"prepare real registrations before free failure");Check(!batch.ReleaseUnpublished(),"injected VirtualFree failure rejects cleanup");}
        const uintptr_t address=batch.Entry(Kind::Init);
        Check(address&&batch.Status()==State::Fault&&batch.LastError()==Error::Free,"free failure retains original address and error state");
        CheckRetainedBytes(batch,source);
        for(unsigned i=0;i<Count;++i)Check(!RegisteredAt(address+PageSize*i),"all OS registrations removed before free attempt");
        const int deletes=batch.testDeleteCalls;batch.testFailFreeAt=-1;
        Check(batch.ReleaseUnpublished()&&batch.Entry(Kind::Init)==0&&batch.testFreeCalls==2,"unpublished owner retries exact failed allocation free");
        Check(batch.testDeleteCalls==deletes,"free-only retry does not delete already removed tables");
    }
}
void BoundObjectLifetime(uintptr_t source) {
    uintptr_t address=0;status_observer::Originals escaped{};
    {
        status_originals::Batch temporary;
        Check(temporary.Prepare(source)&&temporary.Bindings(escaped),"temporary owner publishes process-lifetime code and tables");
        address=temporary.Entry(Kind::Init);
        const int deletes=temporary.testDeleteCalls,frees=temporary.testFreeCalls;
        Check(!temporary.ReleaseUnpublished()&&temporary.Status()==status_originals::State::Bound,
            "published owner remains sealed after cleanup request");
        Check(temporary.testDeleteCalls==deletes&&temporary.testFreeCalls==frees,"sealed batch makes no delete or free API call");
        status_observer::Originals repeated{};Check(temporary.Bindings(repeated)&&repeated.initialize==escaped.initialize&&repeated.release==escaped.release,
            "repeated Bindings preserves published original addresses");
        Check(!temporary.Prepare(source)&&temporary.Status()==status_originals::State::Bound,"published batch cannot prepare replacement storage");
        Check(temporary.Entry(Kind::Count)==0,"invalid entry kind cannot escape page allocation");
    }
    for(unsigned i=0;i<status_originals::Count;++i) {
        const uintptr_t entry=address+status_originals::PageSize*i;
        Check(RegisteredAt(entry),"OS table and runtime storage survive Batch object destruction after Bindings");
        MEMORY_BASIC_INFORMATION page{};
        Check(VirtualQuery(reinterpret_cast<void*>(entry),&page,sizeof(page))==sizeof(page)&&page.State==MEM_COMMIT&&page.Protect==PAGE_EXECUTE_READ,
            "escaped callable image remains RX for process lifetime");
    }
    Check(reinterpret_cast<uintptr_t>(escaped.initialize)==address,"escaped typed original still names retained allocation");
}
}
int main() {
    auto* module=MakeModule();Check(module!=nullptr,"synthetic module allocated");if(!module)return 1;
    FailurePaths(reinterpret_cast<uintptr_t>(module));
    BoundObjectLifetime(reinterpret_cast<uintptr_t>(module));
    status_originals::Batch batch;
    Check(batch.Prepare(reinterpret_cast<uintptr_t>(module)),"prepare all five original trampolines");
    CheckImages(batch,reinterpret_cast<uintptr_t>(module));
    const uintptr_t old=batch.Entry(Kind::Init);
    Check(batch.ReleaseUnpublished(),"unpublished original tables can be removed");
    DWORD64 unused=0;Check(RtlLookupFunctionEntry(old,&unused,nullptr)==nullptr,"OS lookup has no dangling deleted table");
    Check(!batch.Prepare(reinterpret_cast<uintptr_t>(module)),"closed allocation instance cannot be rebound");
    for(unsigned i=0;i<status_originals::Count;++i) {
        const auto& d=*status_entry_plan::Get(static_cast<Kind>(i));module[d.rva+d.originalSize-1]^=1;
        status_originals::Batch damaged;
        Check(!damaged.Prepare(reinterpret_cast<uintptr_t>(module)) && damaged.Status()==status_originals::State::Fault,
            "a changed byte in any full original rejects preparation");
        Check(damaged.Entry(Kind::Init)==0 && damaged.ReleaseUnpublished(),"failed preparation leaves no published image");
        module[d.rva+d.originalSize-1]^=1;
    }
    status_originals::Batch inaccessible;
    Check(!inaccessible.Prepare(1) && inaccessible.LastError()==status_originals::Error::Source,"unreadable source rejected without dereference");
    status_observer::Originals blank{};
    Check(!inaccessible.Bindings(blank) && !blank.initialize,"failed batch publishes no callable originals");
    Check(inaccessible.ReleaseUnpublished(),"failed unpublished batch can close");
    // This final batch is intentionally retained until this isolated process
    // exits, as required once callable pointers have escaped. No game code runs.
    static status_originals::Batch bound;
    Check(bound.Prepare(reinterpret_cast<uintptr_t>(module)),"prepare process-lifetime batch");
    status_observer::Originals originals{};
    Check(bound.Bindings(originals) && bound.Status()==status_originals::State::Bound,"publishing bindings seals memory lifetime");
    Check(reinterpret_cast<uintptr_t>(originals.initialize)==bound.Entry(Kind::Init) &&
          reinterpret_cast<uintptr_t>(originals.rebuild)==bound.Entry(Kind::Rebuild) &&
          reinterpret_cast<uintptr_t>(originals.coefficient)==bound.Entry(Kind::Coefficient) &&
          reinterpret_cast<uintptr_t>(originals.reset)==bound.Entry(Kind::PoolReset) &&
          reinterpret_cast<uintptr_t>(originals.release)==bound.Entry(Kind::Release),"typed original pointers retain five exact entry mappings");
    Check(!bound.ReleaseUnpublished(),"published original storage cannot be torn down");
    CheckImages(bound,reinterpret_cast<uintptr_t>(module));
    printf("StatusOriginalTrampolinesTests: %u checks, %u failures. Generated images are not executed.\n",checks,failures);
    return failures?1:0;
}
#endif
