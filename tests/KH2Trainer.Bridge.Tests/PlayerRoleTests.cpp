// Included by DriveGuardTests.cpp. Exercises the production classifier and Drive
// gates using coherent and deliberately malformed synthetic engine structures.
namespace {
void SetRoleFixture(unsigned character,unsigned form,uintptr_t descriptor,unsigned flags) {
    const auto c=Context();
    const uintptr_t object=Row(objectsRva,0,96);
    Put<uint32_t>(c.player,8,static_cast<uint32_t>(object-g_base));
    Put<uint16_t>(object,76,static_cast<uint16_t>(character));
    Put<signed char>(object,87,static_cast<signed char>(form));
    Put<unsigned>(c.status,608,character); Put<int>(c.player,3552,static_cast<int>(form));
    Put<uint32_t>(c.player,0,static_cast<uint32_t>(descriptor));
    Put<unsigned>(c.player,1736,flags);
}
void RunPlayerRoleTests() {
    using namespace player_role;
    for(unsigned form=0;form<=6;++form) {
        Setup(); SetForm(form); const auto info=Inspect(Context());
        Check(info.role==Sora && info.characterId==1 && info.form==static_cast<int>(form),"Sora and all six forms classify from coherent native fields");
    }
    for(unsigned form:{0u,10u}) {
        Setup(); SetRoleFixture(14,form,0x750300,0x1000080);
        const auto info=Inspect(Context());
        Check(info.role==Roxas && info.characterId==14 && info.form==static_cast<int>(form),"Roxas and dual Roxas classify without save-slot inference");
    }
    Setup(); SetRoleFixture(4,11,0x7523B8,0x2000080);
    Check(Inspect(Context()).role==Mickey,"Mickey rescue uses its own descriptor and form11");
    for(unsigned character:{1u,4u,14u}) {
        Setup(); SetRoleFixture(character,11,0x74A518,0x80);
        Check(Inspect(Context()).role==Other,"common but unsupported player class is Other");
    }
    Setup(); At<uintptr_t>(0x750300)=g_base+0x5D15A0;
    Check(Inspect(Context()).role==Other,"changed descriptor implementation cannot classify Sora");
    Setup(); Put<int>(Context().player,3552,6);
    Check(Inspect(Context()).role==Other,"object and current form mismatch cannot classify Sora");
    Setup(); Put<uint16_t>(Row(objectsRva,0,96),76,14);
    Check(Inspect(Context()).role==Unknown,"object Roxas with Sora status fails coherence");
    Setup(); Put<unsigned>(Context().status,608,14);
    Check(Inspect(Context()).role==Unknown,"status Roxas with Sora object fails coherence");
    Setup(); Put<uint32_t>(Context().status,616,0);
    Check(Inspect(Context()).role==Unknown,"missing current status backlink rejected");
    Setup(); Put<uintptr_t>(Context().player,1472,0);
    Check(Inspect(Context()).role==Unknown,"missing actor status rejected");
    Setup(); auto c=Context(); c.player+=16;
    Check(Inspect(c).role==Unknown,"retained actor pointer is not current player");
    Setup(); c=Context(); c.status+=4;
    Check(Inspect(c).role==Unknown,"misaligned pool pointer rejected");
    Setup(); c=Context(); c.base=0;
    Check(Inspect(c).role==Unknown,"wrong module base rejected");
    Setup(); At<int>(0x2A23950)=1; At<int>(0x2A23810)=0;
    Check(Inspect(Context()).role==Unknown,"freed status cannot classify");
    Setup(); At<int>(0x2A23950)=2; At<int>(0x2A23810)=1; At<int>(0x2A23814)=1;
    Check(Inspect(Context()).role==Unknown,"duplicate free indices reject entire status pool");
    for(int invalid:{-1,81}) {
        Setup(); At<int>(0x2A23950)=invalid;
        Check(Inspect(Context()).role==Unknown,"invalid free-list count rejected");
    }
    Setup(); At<int>(0x2A23950)=1; At<int>(0x2A23810)=80;
    Check(Inspect(Context()).role==Unknown,"out-of-bounds free index rejected");
    for(int refs:{0,-1,INT_MAX}) {
        Setup(); Put<int>(Context().status,612,refs);
        Check(Inspect(Context()).role==Unknown,"invalid status reference count rejected");
    }
    Setup(); At<uintptr_t>(0x2A171C8)=0;
    Check(Inspect(Context()).role==Unknown,"actor absent from active list rejected");
    Setup(); Put<uint32_t>(Context().player,2704,actorRva);
    Check(Inspect(Context()).role==Unknown,"list cycle after current actor rejected");
    Setup(); Put<uint32_t>(Context().player,2704,0x2C00000);
    Check(Inspect(Context()).role==Unknown,"unreadable later actor rejected");
    Setup(); Put<uint32_t>(Context().player,8,0x108000);
    Check(Inspect(Context()).role==Unknown,"unowned detached object copy rejected");
    for(int count:{-1,0,65537}) {
        Setup(); At<int>(objectsRva+4)=count;
        Check(Inspect(Context()).role==Unknown,"invalid object-table count rejected");
    }
    Setup(); Put<uint32_t>(Context().player,8,static_cast<uint32_t>(objectsRva+9));
    Check(Inspect(Context()).role==Unknown,"misaligned object row rejected");
    for(unsigned character:{0u,16u,65535u}) {
        Setup(); SetRoleFixture(character,0,0x750300,0x1000080);
        Check(Inspect(Context()).role==Unknown,"unsupported character ID rejected before role output");
    }
    // Identity alone deliberately survives pause; gameplay readiness owns that gate.
    Setup(); c=Context(); c.sceneReady=false; At<int>(0x716884)=2;
    Check(Inspect(c).role==Sora,"role remains identifiable during field pause");
    DWORD old=0;
    Setup(); VirtualProtect(reinterpret_cast<void*>(g_base+objectsRva),4096,PAGE_NOACCESS,&old);
    Check(Inspect(Context()).role==Unknown,"unreadable current object table fails closed");
    VirtualProtect(reinterpret_cast<void*>(g_base+objectsRva),4096,old,&old);
    for(unsigned character:{4u,14u}) for(unsigned target=1;target<=6;++target) {
        Setup(); SetRoleFixture(character,character==4?11u:0u,character==4?0x7523B8u:0x750300u,character==4?0x2000080u:0x1000080u);
        Rejected("non-Sora roles cannot queue any Drive Form",122,target);
        Check(At<uint16_t>(0x9ABDA0+3588+56*(target-1))==0,"role rejection leaves second-weapon records unchanged");
    }
    for(unsigned target=1;target<=6;++target) {
        Setup(); Put<uint16_t>(Row(objectsRva,target,96),76,14);
        Rejected("mapped Roxas target cannot be used for Sora Drive",122,target);
    }
    QueueFrom(1,5); CompleteNative(0); SetRoleFixture(14,0,0x750300,0x1000080); Tick();
    AssertStopped(drive_features::SafetyRejected,1,"Roxas replacing base Sora cancels pending follow-up");
    QueueFrom(1,5); CompleteNative(0); SetRoleFixture(4,11,0x7523B8,0x2000080); Tick();
    AssertStopped(drive_features::SafetyRejected,1,"Mickey replacement cancels pending follow-up without another transition");
}
}
