// Regression include for DriveGuardTests.cpp; no standalone main or game access.
// Root includes this after its shared fake-memory helpers and calls RunWeaponTests.
// This independent consumer models the native dependency proven at
// 3E0CC0 -> 3EF8B0 -> 3A7A40 -> 3D7600 -> 3B5D40.
namespace {
constexpr uintptr_t WeaponMapRva=0x170000,WeaponMsetRva=0x171000,FakeWeaponRva=0x172000,WeaponBarRva=0x16F000;
constexpr uint16_t MainKeyblade=600,OtherKeyblade=601;
constexpr unsigned MainModel=200,OtherModel=201,WeaponClass=1;
BYTE weaponSaveBefore[progression::SaveSize]{};
unsigned weaponObservedCalls=0; uint16_t weaponExpectedRecord=0,weaponObservedRecord=0;
bool weaponExactWrite=false,weaponConsumerSafe=false;
uintptr_t FormWeaponRecord(unsigned form) { return g_base+0x9ABDA0+3588+56*(form-1); }
bool DualWeaponForm(unsigned form) { return form==1||form==4||form==5; }
// Deliberately exercise the actual first dereference in 3B5D40 with synthetic
// memory. Null is caught here; no process, injected DLL or game code is used.
bool ProbeNativeWeaponContent(uintptr_t weapon) {
    __try { volatile uintptr_t content=*reinterpret_cast<uintptr_t*>(weapon+2744); return content!=0; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
const BYTE* WeaponFixtureItem(uint16_t id) {
    for(int i=0;i<At<int>(itemsRva+4);++i) {
        const BYTE* row=reinterpret_cast<const BYTE*>(Row(itemsRva,static_cast<unsigned>(i),24));
        if(*reinterpret_cast<const uint16_t*>(row)==id)return row;
    }
    return nullptr;
}
unsigned NativeShapedModel(unsigned form,unsigned slot) {
    const unsigned object=At<uint16_t>(0x2A252F0+2*(form+11));
    uintptr_t row=0;
    for(int i=0;i<At<int>(objectsRva+4);++i)if(*reinterpret_cast<unsigned*>(Row(objectsRva,static_cast<unsigned>(i),96))==object)row=Row(objectsRva,static_cast<unsigned>(i),96);
    if(!row)return 0;
    const unsigned category=*reinterpret_cast<uint16_t*>(row+78);
    const uint16_t item=slot?*reinterpret_cast<uint16_t*>(FormWeaponRecord(form)):At<uint16_t>(0x9ABDA0);
    if(!category||!item)return 0;
    const BYTE* itemRow=WeaponFixtureItem(item);if(!itemRow)return 0;
    const uintptr_t map=At<uintptr_t>(0x2AE5A38);
    if(!map)return 0;
    const unsigned offset=*reinterpret_cast<unsigned*>(map+4*category);
    if(!offset)return 0;
    return *reinterpret_cast<unsigned*>(map+4*(offset+*reinterpret_cast<const uint16_t*>(itemRow+4)));
}
void __fastcall ObserveWeaponBegin(uintptr_t actor,int form) {
    ++weaponObservedCalls;
    if(form>0) {
        weaponObservedRecord=*reinterpret_cast<uint16_t*>(FormWeaponRecord(static_cast<unsigned>(form)));
        BYTE expected[progression::SaveSize];memcpy(expected,weaponSaveBefore,sizeof(expected));
        if(DualWeaponForm(static_cast<unsigned>(form))) {
            const uintptr_t offset=FormWeaponRecord(static_cast<unsigned>(form))-(g_base+progression::SaveRva);
            memcpy(expected+offset,&weaponExpectedRecord,sizeof(weaponExpectedRecord));
        }
        weaponExactWrite=!memcmp(expected,reinterpret_cast<void*>(g_base+progression::SaveRva),sizeof(expected));
        // Loader skips a zero model; constructor then leaves offhand null.
        const unsigned model=NativeShapedModel(static_cast<unsigned>(form),1);
        const uintptr_t weapon=model?g_base+FakeWeaponRva:0;
        if(weapon)*reinterpret_cast<uintptr_t*>(weapon+2744)=g_base+FakeWeaponRva+3000;
        weaponConsumerSafe=ProbeNativeWeaponContent(weapon);
    }
    Begin(actor,form); // the existing harness's native queue double, exactly once
}
void SetupWeaponFixture() {
    Setup();
    At<uint16_t>(0x9ABDA0)=MainKeyblade;
    At<int>(itemsRva+4)=8;
    for(unsigned i=0;i<2;++i) {
        const uintptr_t row=Row(itemsRva,6+i,24);
        Put<uint16_t>(row,0,static_cast<uint16_t>(MainKeyblade+i));Put<BYTE>(row,2,2);
        Put<uint16_t>(row,4,static_cast<uint16_t>(i+1));Put<uint16_t>(row,18,static_cast<uint16_t>(20+i));
    }
    // Sort fixture rows by ID without assuming the production helper's search.
    for(unsigned i=0;i<8;++i)for(unsigned j=i+1;j<8;++j)if(*reinterpret_cast<uint16_t*>(Row(itemsRva,j,24))<*reinterpret_cast<uint16_t*>(Row(itemsRva,i,24))) {
        BYTE swap[24];memcpy(swap,reinterpret_cast<void*>(Row(itemsRva,i,24)),24);
        memcpy(reinterpret_cast<void*>(Row(itemsRva,i,24)),reinterpret_cast<void*>(Row(itemsRva,j,24)),24);
        memcpy(reinterpret_cast<void*>(Row(itemsRva,j,24)),swap,24);
    }
    At<int>(objectsRva+4)=9;
    for(unsigned i=0;i<7;++i) {
        const uintptr_t row=Row(objectsRva,i,96);
        Put<uint16_t>(row,76,1);Put<uint16_t>(row,78,WeaponClass);Put<BYTE>(row,87,static_cast<BYTE>(i));
    }
    for(unsigned i=0;i<2;++i) {
        const uintptr_t row=Row(objectsRva,7+i,96);Put<unsigned>(row,0,MainModel+i);
        memcpy(reinterpret_cast<void*>(row+8),i?"W_EX020":"W_EX010",8);
    }
    At<uintptr_t>(0x2AE5A38)=g_base+WeaponMapRva;
    At<unsigned>(WeaponMapRva+4*WeaponClass)=16;
    At<unsigned>(WeaponMapRva+4*17)=MainModel;At<unsigned>(WeaponMapRva+4*18)=OtherModel;
    At<uintptr_t>(0x2AE5A40)=g_base+WeaponMsetRva;
    At<uintptr_t>(0x2AE5E50)=g_base+WeaponBarRva;
    At<unsigned>(WeaponBarRva-16)=0x4000;At<unsigned>(WeaponBarRva-12)=0x23234141;At<unsigned>(WeaponBarRva-8)=1;
    At<unsigned>(WeaponBarRva)=0x01524142;At<unsigned>(WeaponBarRva+4)=3;
    At<uint32_t>(WeaponBarRva+8)=static_cast<uint32_t>(WeaponBarRva);
    At<uint16_t>(WeaponBarRva+16)=2;At<unsigned>(WeaponBarRva+20)=0x746e6577;
    At<uint32_t>(WeaponBarRva+24)=static_cast<uint32_t>(WeaponMapRva);At<unsigned>(WeaponBarRva+28)=256;
    At<uint16_t>(WeaponBarRva+32)=2;At<unsigned>(WeaponBarRva+36)=0x74736d77;
    At<uint32_t>(WeaponBarRva+40)=static_cast<uint32_t>(WeaponMsetRva);At<unsigned>(WeaponBarRva+44)=128;
    memcpy(reinterpret_cast<void*>(g_base+WeaponMsetRva+32*(2*WeaponClass)),"W_EX010",8);
    memcpy(reinterpret_cast<void*>(g_base+WeaponMsetRva+32*(2*WeaponClass+1)),"W_EX010",8);
    for(unsigned form=1;form<=6;++form)*reinterpret_cast<uint16_t*>(FormWeaponRecord(form))=0;
    weaponObservedCalls=0;weaponObservedRecord=0;weaponConsumerSafe=false;weaponExactWrite=false;
    weaponExpectedRecord=MainKeyblade;
    memcpy(weaponSaveBefore,reinterpret_cast<void*>(g_base+progression::SaveRva),sizeof(weaponSaveBefore));
    drive_features::testBegin=ObserveWeaponBegin;
}

void CaptureWeaponSave(uint16_t expected);
void RejectWeaponRequest(const char* label,unsigned form=5);
void RunWeaponTests() {
    SetupWeaponFixture(); At<unsigned>(0x9A98B0+14016)=0xffffffff;
    CaptureWeaponSave(MainKeyblade);
    Check(Execute(122,5).code==0 && weaponObservedRecord==MainKeyblade && weaponExactWrite && weaponConsumerSafe,
          "unlocked Final with empty second weapon receives the same validated fallback");
    using namespace drive_features;
    SetupWeaponFixture();
    Check(NativeShapedModel(5,1)==0,"empty Final record yields no offhand model in the native-shaped loader");
    Check(!ProbeNativeWeaponContent(0),"native-shaped offhand content dereference faults on the old null weapon");
    for(unsigned form:{1u,4u,5u}) {
        SetupWeaponFixture();CaptureWeaponSave(MainKeyblade);
        const auto r=Execute(122,form);
        Check(r.code==0&&begins==1&&weaponObservedCalls==1,"all dual forms queue once with a planned fallback");
        Check(weaponObservedRecord==MainKeyblade&&weaponExactWrite,"only the exact two-byte form weapon changed before NativeBegin");
        Check(weaponConsumerSafe&&NativeShapedModel(form,1)==MainModel,"offhand now satisfies the native-shaped dereference");
        Check(At<uint16_t>(0x9ABDA0)==MainKeyblade&&At<unsigned>(0x9A98B0+14016)==0,"main weapon and unlock bits remain unchanged");
        SetupWeaponFixture();*reinterpret_cast<uint16_t*>(FormWeaponRecord(form))=OtherKeyblade;CaptureWeaponSave(OtherKeyblade);
        Check(Execute(122,form).code==0&&weaponObservedRecord==OtherKeyblade&&weaponExactWrite&&weaponConsumerSafe,"valid existing form weapon is preserved");
        SetupWeaponFixture();*reinterpret_cast<uint16_t*>(FormWeaponRecord(form))=26;CaptureWeaponSave(MainKeyblade);
        Check(Execute(122,form).code==0&&weaponObservedRecord==MainKeyblade&&weaponExactWrite,"wrong item type in form slot gets valid fallback");
        SetupWeaponFixture();*reinterpret_cast<uint16_t*>(FormWeaponRecord(form))=999;CaptureWeaponSave(MainKeyblade);
        Check(Execute(122,form).code==0&&weaponObservedRecord==MainKeyblade&&weaponExactWrite,"unknown stale form item gets valid fallback");
        SetupWeaponFixture();*reinterpret_cast<uint16_t*>(FormWeaponRecord(form))=OtherKeyblade;
        At<unsigned>(WeaponMapRva+4*18)=0;CaptureWeaponSave(MainKeyblade);
        Check(Execute(122,form).code==0&&weaponObservedRecord==MainKeyblade&&weaponExactWrite,"existing unmapped form weapon gets valid mapped main weapon");
    }
    for(unsigned form:{2u,3u,6u}) {
        SetupWeaponFixture();CaptureWeaponSave(0);
        Check(Execute(122,form).code==0&&weaponObservedRecord==0&&weaponExactWrite,"non-dual forms leave empty form weapon unchanged");
    }
    SetupWeaponFixture();At<uint16_t>(0x9ABDA0)=0;RejectWeaponRequest("empty primary item cannot provide offhand fallback");
    SetupWeaponFixture();At<uint16_t>(0x9ABDA0)=26;RejectWeaponRequest("non-Keyblade primary cannot provide offhand fallback");
    SetupWeaponFixture();At<uint16_t>(0x9ABDA0)=999;RejectWeaponRequest("missing primary item rejected");
    SetupWeaponFixture();At<uintptr_t>(0x2AE5A38)=0;RejectWeaponRequest("missing weapon mapping rejected");
    SetupWeaponFixture();At<uintptr_t>(0x2AE5A38)=1;RejectWeaponRequest("unreadable weapon mapping rejected");
    SetupWeaponFixture();At<unsigned>(WeaponMapRva+4*WeaponClass)=0;RejectWeaponRequest("zero weapon-class mapping offset rejected");
    SetupWeaponFixture();At<unsigned>(WeaponMapRva+4*WeaponClass)=UINT_MAX;RejectWeaponRequest("large mapping offset cannot wrap to a readable entry");
    SetupWeaponFixture();At<unsigned>(WeaponMapRva+4*17)=0;RejectWeaponRequest("zero primary mapped model rejected");
    SetupWeaponFixture();At<unsigned>(WeaponMapRva+4*17)=566;RejectWeaponRequest("context-dependent model alias rejected");
    SetupWeaponFixture();At<unsigned>(WeaponMapRva+4*17)=999;RejectWeaponRequest("unknown primary weapon model rejected");
    SetupWeaponFixture();Put<BYTE>(Row(objectsRva,7,96),8,0);RejectWeaponRequest("empty model name rejected");
    SetupWeaponFixture();At<uintptr_t>(0x2AE5A40)=0;RejectWeaponRequest("missing weapon MSET table rejected");
    SetupWeaponFixture();At<uintptr_t>(0x2AE5A40)=1;RejectWeaponRequest("unreadable weapon MSET table rejected");
    SetupWeaponFixture();At<BYTE>(WeaponMsetRva+32*3)=0;RejectWeaponRequest("empty offhand MSET name rejected");
    SetupWeaponFixture();memset(reinterpret_cast<void*>(g_base+WeaponMsetRva+32*3),'X',32);RejectWeaponRequest("unterminated offhand MSET name rejected");
    SetupWeaponFixture();At<uintptr_t>(0x2AE5E50)=0;RejectWeaponRequest("missing owning system BAR rejected");
    SetupWeaponFixture();At<unsigned>(WeaponBarRva)=0;RejectWeaponRequest("invalid system BAR signature rejected");
    SetupWeaponFixture();At<unsigned>(WeaponBarRva-12)=0;RejectWeaponRequest("foreign allocation header rejected");
    SetupWeaponFixture();At<unsigned>(WeaponBarRva-16)=0x1040;RejectWeaponRequest("MSET entry beyond allocation rejected despite mapped memory");
    SetupWeaponFixture();At<unsigned>(WeaponBarRva-8)=0;RejectWeaponRequest("wrong BAR allocation kind rejected");
    SetupWeaponFixture();At<uint32_t>(WeaponBarRva+8)=0;RejectWeaponRequest("BAR self pointer identity rejected");
    SetupWeaponFixture();At<unsigned>(WeaponBarRva+4)=0xffffffff;RejectWeaponRequest("invalid BAR count rejected");
    SetupWeaponFixture();At<uint32_t>(WeaponBarRva+24)=static_cast<uint32_t>(WeaponMapRva+4);RejectWeaponRequest("BAR mapping pointer must equal the live mapping global");
    SetupWeaponFixture();At<unsigned>(WeaponBarRva+28)=4;RejectWeaponRequest("mapping class cell must lie within BAR entry bytes");
    SetupWeaponFixture();At<unsigned>(WeaponBarRva+28)=68;RejectWeaponRequest("model cell cannot cross declared BAR entry end despite readable memory");
    SetupWeaponFixture();At<unsigned>(WeaponBarRva+44)=127;RejectWeaponRequest("32-byte MSET name cannot cross declared BAR entry end");
    SetupWeaponFixture();Put<uint16_t>(Row(objectsRva,5,96),76,2);RejectWeaponRequest("Final model is not a Sora/Roxas weapon owner");
    SetupWeaponFixture();Put<uint16_t>(Row(objectsRva,5,96),78,0);RejectWeaponRequest("Final model has no weapon class");
    SetupWeaponFixture();Put<BYTE>(Row(objectsRva,5,96),87,4);RejectWeaponRequest("Final model aliases a different form record");
    SetupWeaponFixture();Put<BYTE>(Row(objectsRva,5,96),87,0xff);RejectWeaponRequest("negative native signed form index rejected");
    SetupWeaponFixture();At<BYTE>(0x9ABDA0+3588+56*4+2)=8;RejectWeaponRequest("later invalid form gate causes no weapon write");
    SetupWeaponFixture();At<float>(0x107000+104)=0;RejectWeaponRequest("later timer rejection causes no weapon write");
    SetupWeaponFixture();At<uintptr_t>(0x2A11498)=0;RejectWeaponRequest("later message rejection causes no weapon write");
    SetupWeaponFixture();DWORD oldProtection=0,ignoredProtection=0;
    void* protectedPage=reinterpret_cast<void*>(FormWeaponRecord(5)&~uintptr_t(4095));
    Check(VirtualProtect(protectedPage,4096,PAGE_READONLY,&oldProtection)!=FALSE,"real form-save page made read-only");
    RejectWeaponRequest("read-only form record rejected before any native call");
    VirtualProtect(protectedPage,4096,oldProtection,&ignoredProtection);
    SetupWeaponFixture();SetForm(1);*reinterpret_cast<uint16_t*>(FormWeaponRecord(1))=MainKeyblade;
    At<uint16_t>(0x2A252F0+16)=999;RejectWeaponRequest("Revert-resource preflight failure cannot mutate the queued target");
    SetupWeaponFixture();SetForm(1);*reinterpret_cast<uint16_t*>(FormWeaponRecord(1))=MainKeyblade;
    CaptureWeaponSave(MainKeyblade);Check(Execute(122,5).code==0&&begins==1&&calls[0].form==0,"active form begins native Revert first");
    Check(*reinterpret_cast<uint16_t*>(FormWeaponRecord(5))==0,"future Final record remains untouched during Revert");
    CompleteNative(0);CaptureWeaponSave(MainKeyblade);Tick();
    Check(begins==2&&calls[1].form==5&&weaponObservedRecord==MainKeyblade&&weaponExactWrite&&weaponConsumerSafe,"fresh base step prepares Final immediately before its native loader");
    SetupWeaponFixture();SetForm(1);*reinterpret_cast<uint16_t*>(FormWeaponRecord(1))=MainKeyblade;
    Check(Execute(122,5).code==0,"queue created before changed weapon resource");
    CompleteNative(0);At<unsigned>(WeaponMapRva+4*17)=0;Tick();
    Check(begins==1&&queue.phase==Idle&&queue.outcome==SafetyRejected&&*reinterpret_cast<uint16_t*>(FormWeaponRecord(5))==0,"changed second-step resource rejects with no target mutation");
    SetupWeaponFixture();SetForm(1);*reinterpret_cast<uint16_t*>(FormWeaponRecord(1))=MainKeyblade;
    Check(Execute(122,5).code==0,"queue created before cancellation");Execute(126);CompleteNative(0);Tick();
    Check(begins==1&&*reinterpret_cast<uint16_t*>(FormWeaponRecord(5))==0,"cancelled follow-up never initializes target weapon");
    SetupWeaponFixture();queueWorks=false;CaptureWeaponSave(MainKeyblade);
    Check(Execute(122,5).code!=0&&begins==1&&weaponExactWrite&&*reinterpret_cast<uint16_t*>(FormWeaponRecord(5))==0,"no native context means the unconsumed preparatory weapon write is rolled back");
    // These are one-time equipment initialization writes. They remain valid
    // after disconnect and may be saved by the game; no unlock/bag mutation.
    SetupWeaponFixture();CaptureWeaponSave(MainKeyblade);Check(Execute(122,5).code==0,"valid Final request for disconnect case");
    shared.hostHeartbeat=0;DriveReset(Context());
    Check(*reinterpret_cast<uint16_t*>(FormWeaponRecord(5))==MainKeyblade,"disconnect preserves initialized offhand instead of recreating null");
    drive_features::testBegin=Begin;
}
void CaptureWeaponSave(uint16_t expected) {
    weaponExpectedRecord=expected;
    memcpy(weaponSaveBefore,reinterpret_cast<void*>(g_base+progression::SaveRva),sizeof(weaponSaveBefore));
}
void RejectWeaponRequest(const char* label,unsigned form) {
    BYTE before[progression::SaveSize];memcpy(before,reinterpret_cast<void*>(g_base+progression::SaveRva),sizeof(before));
    const auto r=Execute(122,form);
    Check(r.code!=0&&begins==0&&weaponObservedCalls==0,label);
    Check(!memcmp(before,reinterpret_cast<void*>(g_base+progression::SaveRva),sizeof(before)),"rejected weapon preflight changes zero save bytes");
}

constexpr uintptr_t SkeletonRva=0x171100;
void RejectSkeletonRequest(const char* label,unsigned target=5) {
    RejectWeaponRequest(label,target);
    Check(drive_features::queue.outcome==drive_features::SafetyRejected,
        "skeleton rejection terminates the trainer queue");
}
void RunSkeletonTests() {
    using namespace drive_features;
    // BYTE7=7 and WORD78=1 intentionally differ. A guard reading the mapping
    // class instead of the attachment key would reject this valid native row.
    for(unsigned form=1;form<=6;++form) {
        SetupWeaponFixture();CaptureWeaponSave(DualWeaponForm(form)?MainKeyblade:0);
        Check(Execute(122,form).code==0 && begins==1 && weaponExactWrite,
            "all six forms accept the exact BYTE7 skeleton key without unlocks");
        Check(At<unsigned>(0x9A98B0+14016)==0,"skeleton validation does not unlock forms");
    }
    SetupWeaponFixture(); Put<BYTE>(Row(objectsRva,5,96),7,1);
    RejectSkeletonRequest("existing WORD78 mapping does not replace a missing BYTE7 skeleton key");
    SetupWeaponFixture(); Put<BYTE>(Row(objectsRva,5,96),7,255);
    Check(Execute(122,5).code==0,"maximum BYTE key is accepted");
    SetupWeaponFixture(); At<int16_t>(SkeletonRva+8+8+4)=INT16_MIN;
    At<int16_t>(SkeletonRva+8+8+6)=-1; CaptureWeaponSave(MainKeyblade);
    Check(Execute(122,5).code==0 && weaponExactWrite &&
        At<int16_t>(SkeletonRva+20)==INT16_MIN && At<int16_t>(SkeletonRva+22)==-1,
        "signed joint values remain unchanged without an invented sign rule");

    SetupWeaponFixture(); At<uintptr_t>(0x2AE5798)=0; RejectSkeletonRequest("missing installed skeleton rejected");
    SetupWeaponFixture(); At<uintptr_t>(0x2AE5798)=1; RejectSkeletonRequest("unreadable installed skeleton rejected");
    SetupWeaponFixture(); At<uintptr_t>(0x2AE5798)+=8; RejectSkeletonRequest("installed skeleton must match first BAR payload");
    SetupWeaponFixture(); At<unsigned>(WeaponBarRva+52)=0; RejectSkeletonRequest("missing sklt tag rejected");
    SetupWeaponFixture(); At<uint16_t>(WeaponBarRva+48)=3; RejectSkeletonRequest("wrong entry type cannot supply sklt");
    SetupWeaponFixture(); At<unsigned>(WeaponBarRva+60)=0; RejectSkeletonRequest("empty skeleton entry rejected");
    SetupWeaponFixture(); At<unsigned>(WeaponBarRva+60)=7; RejectSkeletonRequest("skeleton header must fit entry");
    SetupWeaponFixture(); At<unsigned>(WeaponBarRva+60)=39; RejectSkeletonRequest("last row cannot cross declared span");
    for(int count:{0,-1,INT_MAX}) {
        SetupWeaponFixture(); At<int>(SkeletonRva+4)=count;
        RejectSkeletonRequest("invalid or oversized signed skeleton count rejected before traversal");
    }
    SetupWeaponFixture(); At<unsigned>(SkeletonRva+16)=8; RejectSkeletonRequest("missing exact row rejected");
    SetupWeaponFixture(); At<unsigned>(SkeletonRva+24)=7; RejectSkeletonRequest("duplicate skeleton keys rejected");
    SetupWeaponFixture(); At<unsigned>(SkeletonRva+24)=6; RejectSkeletonRequest("unsorted skeleton keys rejected");
    SetupWeaponFixture(); At<unsigned>(SkeletonRva+32)=UINT_MAX;
    RejectSkeletonRequest("native comparator wrap inversion is rejected");
    SetupWeaponFixture(); At<unsigned>(SkeletonRva+32)=0x80000000u+7u;
    Check(Execute(122,5).code==0,"largest key distance with ordered signed subtraction accepted");
    SetupWeaponFixture(); At<unsigned>(SkeletonRva+32)=0x80000000u+8u;
    RejectSkeletonRequest("first overflowing comparator distance rejected");
    SetupWeaponFixture(); At<uint32_t>(WeaponBarRva+56)=static_cast<uint32_t>(WeaponBarRva+16);
    At<uintptr_t>(0x2AE5798)=g_base+WeaponBarRva+16;
    RejectSkeletonRequest("skeleton cannot alias BAR entry metadata");
    SetupWeaponFixture(); At<uint32_t>(WeaponBarRva+56)=0x180000;
    At<uintptr_t>(0x2AE5798)=g_base+0x180000;
    memcpy(reinterpret_cast<void*>(g_base+0x180000),reinterpret_cast<void*>(g_base+SkeletonRva),40);
    RejectSkeletonRequest("readable matching global outside owning BAR is rejected");
    SetupWeaponFixture(); At<unsigned>(WeaponBarRva+60)=UINT_MAX;
    RejectSkeletonRequest("payload extent cannot exceed owning allocation");

    // First-match semantics include link flags. Later duplicates neither repair
    // a bad first payload nor invalidate an already accepted first match.
    SetupWeaponFixture(); At<unsigned>(WeaponBarRva+4)=4;
    memcpy(reinterpret_cast<void*>(g_base+WeaponBarRva+64),reinterpret_cast<void*>(g_base+WeaponBarRva+48),16);
    At<unsigned>(WeaponBarRva+60)=7;
    RejectSkeletonRequest("later valid duplicate cannot hide invalid first sklt");
    SetupWeaponFixture(); At<unsigned>(WeaponBarRva+4)=4;
    memcpy(reinterpret_cast<void*>(g_base+WeaponBarRva+64),reinterpret_cast<void*>(g_base+WeaponBarRva+48),16);
    At<uint32_t>(WeaponBarRva+72)=0;
    Check(Execute(122,5).code==0,"valid first sklt wins over invalid later duplicate");
    SetupWeaponFixture(); At<unsigned>(WeaponBarRva+4)=4;
    memcpy(reinterpret_cast<void*>(g_base+WeaponBarRva+64),reinterpret_cast<void*>(g_base+WeaponBarRva+48),16);
    At<uint16_t>(WeaponBarRva+48)=3;At<uint32_t>(WeaponBarRva+56)=0;
    Check(Execute(122,5).code==0,"wrong type is skipped before first matching type2 sklt");
    SetupWeaponFixture(); At<uint16_t>(WeaponBarRva+50)=0xffff;
    Check(Execute(122,5).code==0,"link flags do not change native first-match semantics");

    // Native hand0 reaches the same lookup on Revert and all non-dual forms.
    for(unsigned form:{2u,3u,6u}) {
        SetupWeaponFixture(); At<uintptr_t>(0x2AE5798)=0;
        RejectSkeletonRequest("non-dual main hand still requires skeleton row",form);
        SetupWeaponFixture(); At<uintptr_t>(0x2AE5798)=0; At<BYTE>(WeaponMsetRva+64)=0;
        Check(Execute(122,form).code==0,"empty main motion with absent offhand skips only skeleton requirement");
        SetupWeaponFixture(); At<uintptr_t>(0x2AE5798)=0; At<BYTE>(WeaponMsetRva+64)=0;
        *reinterpret_cast<uint16_t*>(FormWeaponRecord(form))=MainKeyblade;
        RejectSkeletonRequest("non-dual existing offhand can independently require skeleton",form);
    }
    SetupWeaponFixture(); At<uintptr_t>(0x2AE5798)=0; At<uint16_t>(0x9ABDA0)=0;
    Check(Execute(122,6).code==0,"no resolved weapon means no skeleton lookup");
    SetupWeaponFixture(); At<uintptr_t>(0x2AE5798)=0;Put<uint16_t>(Row(objectsRva,6,96),78,0);
    Check(Execute(122,6).code==0,"native zero weapon group skip does not require skeleton");
    SetupWeaponFixture(); At<uintptr_t>(0x2AE5798)=0;At<unsigned>(WeaponMapRva+4)=0;
    Check(Execute(122,6).code==0,"native zero mapping base skip does not require skeleton");
    SetupWeaponFixture(); At<uintptr_t>(0x2AE5798)=0;At<unsigned>(WeaponMapRva+68)=0;
    Check(Execute(122,6).code==0,"native zero model skip does not require skeleton");
    SetupWeaponFixture(); SetForm(1); At<uintptr_t>(0x2AE5798)=0;
    BYTE before[progression::SaveSize];memcpy(before,reinterpret_cast<void*>(g_base+progression::SaveRva),sizeof(before));
    Check(Execute(123).code!=0 && !begins && !memcmp(before,reinterpret_cast<void*>(g_base+progression::SaveRva),sizeof(before)),
        "Revert main weapon skeleton rejection causes no native call or save write");
    SetupWeaponFixture(); SetForm(1);Put<BYTE>(Row(objectsRva,0,96),7,8);
    RejectSkeletonRequest("valid target cannot hide invalid Revert skeleton");
    SetupWeaponFixture(); SetForm(1);Put<BYTE>(Row(objectsRva,5,96),7,8);
    RejectSkeletonRequest("invalid future target is rejected before first Revert");
    SetupWeaponFixture();SetForm(1);
    Check(Execute(122,5).code==0 && begins==1,"valid skeleton permits initial Revert");
    CompleteNative(0);At<unsigned>(SkeletonRva+16)=8;
    memcpy(before,reinterpret_cast<void*>(g_base+progression::SaveRva),sizeof(before));Tick();
    Check(begins==1 && queue.phase==Idle && queue.outcome==SafetyRejected &&
        !memcmp(before,reinterpret_cast<void*>(g_base+progression::SaveRva),sizeof(before)),
        "fresh second-step row loss causes no fallback write or second Begin");
    At<unsigned>(SkeletonRva+16)=7;Tick();Check(begins==1,"restored row does not restart rejected queue");
    SetupWeaponFixture();SetForm(1);Check(Execute(122,5).code==0,"queue starts before owner change");
    CompleteNative(0);At<uintptr_t>(0x2AE5798)=0;Tick();
    Check(begins==1 && queue.outcome==SafetyRejected && *reinterpret_cast<uint16_t*>(FormWeaponRecord(5))==0,
        "fresh second-step installed pointer is revalidated");
    SetupWeaponFixture();Check(CanStart(Context(),5),"preliminary target check succeeds before table changes");
    At<unsigned>(SkeletonRva+16)=8;
    memcpy(before,reinterpret_cast<void*>(g_base+progression::SaveRva),sizeof(before));
    Check(!drive_features::Begin(Context(),5,WaitingForForm) && !begins &&
        !memcmp(before,reinterpret_cast<void*>(g_base+progression::SaveRva),sizeof(before)),
        "Begin itself rechecks attachment row before preparatory weapon writes");

    for(const auto& pin:kSkeletonPins) for(SIZE_T i=0;i<pin.size;++i) {
        SetupWeaponFixture();At<BYTE>(pin.rva+i)^=1;
        RejectSkeletonRequest("every changed skeleton-contract instruction byte rejects before writes");
    }
    SetupWeaponFixture();DWORD oldProtect=0,unused=0;
    Check(VirtualProtect(reinterpret_cast<void*>(g_base+SkeletonRva-0x100),4096,PAGE_NOACCESS,&oldProtect)!=FALSE,
        "skeleton fixture page made inaccessible");
    RejectSkeletonRequest("unreadable owning payload is rejected");
    VirtualProtect(reinterpret_cast<void*>(g_base+SkeletonRva-0x100),4096,oldProtect,&unused);
    drive_features::testBegin=Begin;
}
}
