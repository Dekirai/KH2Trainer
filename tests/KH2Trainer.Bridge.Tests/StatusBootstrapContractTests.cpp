#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define KH2_STATUS_BOOTSTRAP_CONTRACT_TESTS
#include <windows.h>
#include <stdio.h>
#include "../../src/KH2Trainer.Bridge/StatusBootstrapContract.h"
#include "../../src/KH2Trainer.Bridge/StatusEntryPlan.h"
namespace {
using namespace status_bootstrap;
unsigned checks=0,failures=0;
void Check(bool okay,const char* name) {++checks;if(!okay){++failures;printf("FAIL %s\n",name);}}
struct Fixture {
    unsigned char* image=nullptr;ApiTargets targets{};
    uint32_t denied=UINT32_MAX;unsigned eventReads=0;bool mutateEvent=false;
    Fixture() {
        image=static_cast<unsigned char*>(VirtualAlloc(nullptr,ImageSize,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
        if(!image){printf("FATAL fixture allocation\n");ExitProcess(90);}
        for(unsigned i=0;i<ImportCount;++i)targets.imports[i]=0x180000000+0x1000*(i+1);
        targets.sleep=0x180010000;targets.wake=0x180020000;Reset();
    }
    ~Fixture(){VirtualFree(image,0,MEM_RELEASE);}
    uintptr_t Base() const {return reinterpret_cast<uintptr_t>(image);}
    void Put(uint32_t rva,uintptr_t value){memcpy(image+rva,&value,8);}
    void Cv(uintptr_t cookie) {
        Put(EventSlot,0);Put(CookieSlot,cookie);
        Put(SleepSlot,RotateRight(targets.sleep,64-static_cast<unsigned>(cookie&63))^cookie);
        Put(WakeSlot,RotateRight(targets.wake,64-static_cast<unsigned>(cookie&63))^cookie);
    }
    void Reset() {
        denied=UINT32_MAX;eventReads=0;mutateEvent=false;
        IMAGE_DOS_HEADER dos{};dos.e_magic=IMAGE_DOS_SIGNATURE;dos.e_lfanew=PeOffset;memcpy(image,&dos,sizeof(dos));
        IMAGE_NT_HEADERS64 nt{};nt.Signature=IMAGE_NT_SIGNATURE;nt.FileHeader.Machine=IMAGE_FILE_MACHINE_AMD64;
        nt.FileHeader.TimeDateStamp=TimeStamp;nt.FileHeader.SizeOfOptionalHeader=sizeof(IMAGE_OPTIONAL_HEADER64);
        nt.OptionalHeader.Magic=IMAGE_NT_OPTIONAL_HDR64_MAGIC;nt.OptionalHeader.SizeOfImage=ImageSize;
        nt.OptionalHeader.DllCharacteristics=DllCharacteristics;memcpy(image+PeOffset,&nt,sizeof(nt));
        for(const auto& body:Bodies)memcpy(image+body.rva,body.bytes,body.size);
        for(unsigned i=0;i<ImportCount;++i)Put(Imports[i].rva,targets.imports[i]);
        Put(DispatchSlot,Base()+DispatchThunk);Cv(0x123456789abcdef1);
    }
    void Gates(unsigned mask=31) {for(unsigned i=0;i<RootCount;++i)image[Bodies[i].rva]=(mask&(1u<<i))?0xcc:Bodies[i].bytes[0];}
    static bool ReadImage(void* context,uintptr_t address,void* output,size_t size,bool) noexcept {
        auto& f=*static_cast<Fixture*>(context);
        if(address<f.Base() || address>=f.Base()+ImageSize || size>f.Base()+ImageSize-address)return false;
        const auto rva=static_cast<uint32_t>(address-f.Base());
        if(rva<=f.denied && size>f.denied-rva)return false;
        if(rva==EventSlot && f.mutateEvent && ++f.eventReads==2)f.Put(EventSlot,1);
        memcpy(output,f.image+rva,size);return true;
    }
    Reader Source(){return {ReadImage,this};}
    bool Prepare(Contract& c){return c.TestPrepare(Base(),Source(),targets);}
};
void RootsAndModes(Fixture& f) {
    for(unsigned i=0;i<RootCount;++i) {
        const auto& d=status_entry_plan::Definitions[i];
        Check(Bodies[i].root==static_cast<int>(i) && d.rva==Bodies[i].rva && d.originalSize==Bodies[i].size &&
            !memcmp(d.original,Bodies[i].bytes,d.originalSize),"same five complete originals as entry planner");
    }
    Contract c;Range ranges[RootCount]{};
    Check(!c.RootRanges(ranges),"unprepared object exposes no root ranges");
    Check(f.Prepare(c) && c.Status()==Phase::Prepared,"unmodified retail fixture accepted");
    Check(c.Verify(EntryMode::Original),"prepared original can be rechecked");
    Check(c.RootRanges(ranges),"prepared exact root ranges available");
    for(unsigned i=0;i<RootCount;++i)Check(ranges[i].begin==f.Base()+Bodies[i].rva && ranges[i].end-ranges[i].begin==Bodies[i].size,"drain receives complete root extent");
    f.Gates();Check(c.Verify(EntryMode::FiveGates) && c.Status()==Phase::Gated,"all five owned CC gates advance phase");
    Check(c.Verify(EntryMode::FiveGates),"resident contract rechecks");
    f.Gates(30);Check(!c.Verify(EntryMode::FiveGates) && c.Status()==Phase::Fault,"one lost gate faults");
    f.Gates();Check(!c.Verify(EntryMode::FiveGates) && !c.RootRanges(ranges),"restoring gate does not erase uncertainty");
    f.Reset();Contract reverse;Check(f.Prepare(reverse),"prepare reverse-phase case");f.Gates();Check(reverse.Verify(EntryMode::FiveGates),"gate reverse-phase case");
    f.Gates(0);Check(!reverse.Verify(EntryMode::Original),"cannot return from gated phase to originals");
    for(unsigned mask=0;mask<31;++mask) {
        f.Reset();Contract partial;Check(f.Prepare(partial),"prepare partial publication case");f.Gates(mask);
        Check(!partial.Verify(EntryMode::FiveGates),"every incomplete gate mask rejected");
    }
    f.Reset();f.Gates();Contract prepatched;Check(!f.Prepare(prepatched),"prepare requires untouched originals");
    f.Reset();Contract rebound;Check(f.Prepare(rebound) && !f.Prepare(rebound) && rebound.Status()==Phase::Fault,"configuration cannot be rebound");
}
void ExactBytes(Fixture& f) {
    f.Reset();
    for(const auto& body:Bodies)for(size_t i=0;i<body.size;++i) {
        f.image[body.rva+i]^=1;Contract bad;
        Check(!f.Prepare(bad) && bad.Failure()==Error::Body,"every original closure/thunk byte is pinned");
        f.image[body.rva+i]^=1;
    }
    for(const auto& body:Bodies)for(size_t i=body.root>=0?1:0;i<body.size;++i) {
        Contract bad;const bool prepared=f.Prepare(bad);f.Gates();f.image[body.rva+i]^=1;
        Check(prepared && !bad.Verify(EntryMode::FiveGates) && bad.Failure()==Error::Body,"all bytes beyond permitted CC substitutions stay pinned");
        f.image[body.rva+i]^=1;f.Gates(0);
    }
}
void ImportAndDispatch(Fixture& f) {
    for(unsigned i=0;i<ImportCount;++i) {
        f.Reset();f.Put(Imports[i].rva,f.targets.imports[(i+1)%ImportCount]);Contract wrong;
        Check(!f.Prepare(wrong) && wrong.Failure()==Error::Import,"IAT slot requires its own named export");
        f.Reset();Contract lost;Check(f.Prepare(lost),"prepare import-drift case");f.Put(Imports[i].rva,0);
        Check(!lost.Verify(EntryMode::Original),"post-prepare import mutation rejected");
    }
    f.Reset();f.Put(DispatchSlot,f.Base()+DispatchThunk+1);Contract dispatch;
    Check(!f.Prepare(dispatch) && dispatch.Failure()==Error::Dispatch,"foreign dispatch never accepted or rewritten");
    f.Reset();auto* nt=reinterpret_cast<IMAGE_NT_HEADERS64*>(f.image+PeOffset);nt->OptionalHeader.DllCharacteristics|=IMAGE_DLLCHARACTERISTICS_GUARD_CF;
    Contract cfg;Check(!f.Prepare(cfg) && cfg.Failure()==Error::Header,"different CFG contract fails closed");
    f.Reset();f.image[0]=0;Contract header;Check(!f.Prepare(header),"wrong image header rejected");
}
void ConfigurationCases(Fixture& f) {
    for(unsigned rotation=0;rotation<64;++rotation) {
        f.Reset();f.Cv(0xfedcba9876543200|rotation);Contract c;
        Check(f.Prepare(c) && c.Verify(EntryMode::Original),"native decoding supports every rotate count including zero");
    }
    const uint32_t slots[]={CookieSlot,SleepSlot,WakeSlot};
    for(auto slot:slots) {
        f.Reset();Contract c;Check(f.Prepare(c),"prepare encoded callback mutation");f.image[slot]^=1;
        Check(!c.Verify(EntryMode::Original),"cookie or callback mutation faults");
    }
    f.Reset();Contract reencoded;Check(f.Prepare(reencoded),"prepare stable encoding identity");f.Cv(17);
    Check(!reencoded.Verify(EntryMode::Original),"same decoded functions with changed cookie/encoding still fault");
    f.Reset();Contract switchToEvent;Check(f.Prepare(switchToEvent),"prepare CV mode switch");f.Put(EventSlot,4);
    Check(!switchToEvent.Verify(EntryMode::Original),"CV to event mode cannot reset confidence");
    f.Reset();f.Put(EventSlot,4);f.Put(SleepSlot,0);f.Put(WakeSlot,UINTPTR_MAX);Contract event;
    ApiTargets noCv=f.targets;noCv.sleep=noCv.wake=0;
    Check(event.TestPrepare(f.Base(),f.Source(),noCv),"nonzero native event branch does not inspect unused callback slots");
    f.Put(CookieSlot,0);f.Put(SleepSlot,123);f.Put(WakeSlot,456);
    Check(event.Verify(EntryMode::Original),"unused encoding changes do not invalidate stable event branch");
    f.Put(EventSlot,8);Check(!event.Verify(EntryMode::Original),"changing event handle faults");
    f.Reset();f.Put(EventSlot,4);Contract switchToCv;Check(f.Prepare(switchToCv),"prepare event mode switch");f.Cv(5);
    Check(!switchToCv.Verify(EntryMode::Original),"event to CV mode cannot reset confidence");
    f.Reset();Contract unavailable;Check(!unavailable.TestPrepare(f.Base(),f.Source(),noCv),"zero event needs resolved CV exports");
    f.Reset();f.mutateEvent=true;Contract torn;
    Check(!f.Prepare(torn) && torn.Failure()==Error::Configuration,"observed configuration change across reads defers");
}
void ReadsAndRealApis(Fixture& f) {
    const uint32_t denied[]={0,PeOffset,Bodies[0].rva,Bodies[24].rva,DispatchThunk,DispatchSlot,Imports[5].rva,EventSlot,CookieSlot,SleepSlot,WakeSlot};
    for(auto rva:denied){f.Reset();f.denied=rva;Contract c;Check(!f.Prepare(c) && c.Failure()==Error::Read,"unreadable required span never passes");}
    ApiTargets exports{};
    Check(ResolveApis(exports,true),"real isolated-process Kernel32 and CRT API-set exports resolve and pin");
    HMODULE kernel=GetModuleHandleW(L"kernel32.dll");
    for(unsigned i=0;i<5;++i)Check(exports.imports[i]==reinterpret_cast<uintptr_t>(GetProcAddress(kernel,Imports[i].name)),"real named OS import matches resolver");
    Check(exports.sleep && exports.wake && exports.imports[5],"both CV callbacks and bsearch have real owners");
    f.targets=exports;f.Reset();Contract actualTargets;
    Check(f.Prepare(actualTargets),"real API bindings validate synthetic image without executing native game code");
    ApiTargets eventExports{};Check(ResolveApis(eventExports,false) && !eventExports.sleep && !eventExports.wake,"event resolver does not require unused CV exports");
    unsigned char copy=0;
    Check(!NativeRead(reinterpret_cast<void*>(f.Base()),f.Base(),&copy,1,false),"production reader rejects private synthetic image");
    Contract unrelated;
    Check(!unrelated.Prepare(reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr))),"production prepare rejects the unrelated test executable");
}
}
int main() {
    Fixture f;RootsAndModes(f);ExactBytes(f);ImportAndDispatch(f);ConfigurationCases(f);ReadsAndRealApis(f);
    printf("StatusBootstrapContractTests: %u checks, %u failures. Synthetic image and own-process OS exports only.\n",checks,failures);
    return failures?1:0;
}
