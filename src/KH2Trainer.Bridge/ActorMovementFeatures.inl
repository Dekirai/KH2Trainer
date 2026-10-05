// Current Sora movement parameters. Evidence: actor_controls_deep.*.
// Include after DamageTuningFeatures.inl. These are one-time runtime edits;
// there are no retained Actor pointers, callbacks, save edits or auto-restores.
namespace actor_movement {
constexpr unsigned First=344,Last=347;
constexpr unsigned Offsets[]={296,300,312,304};
constexpr double Minima[]={0,0,0.1,0};
constexpr double Maxima[]={32,64,100,1000};
bool Ready(const TrainerContext& c,bool allowPause=false) {
    if(!damage_tuning::Ready(c,allowPause) ||
       !Readable(reinterpret_cast<void*>(c.player),3608) ||
       combat::Field<int>(c.status,608)!=1 ||
       DecodePacked(combat::Field<uint32_t>(c.player,0))!=g_base+0x750300 ||
       At<uintptr_t>(0x750300)!=g_base+0x5CBA28 ||
       At<uintptr_t>(0x5CBA28+296)!=g_base+0x404FB0 ||
       (combat::Field<unsigned>(c.player,1736)&0x1000080)!=0x1000080 ||
       (combat::Field<unsigned>(c.player,288)&0x10080100) ||
       combat::Field<uint32_t>(c.player,1696) ||
       combat::Field<uintptr_t>(c.player,360)!=c.player ||
       At<BYTE>(0xABAC58) || At<BYTE>(0xABAC59) ||
       !Readable(At<void*>(0x9BA920),8)) return false;
    const int form=combat::Field<int>(c.player,3552);
    return form>=0 && form<=6 && At<BYTE>(0x9ACDD4)==form;
}
}
bool ActorMovementHandle(const TrainerContext& c,unsigned slot,const double args[8],TrainerResult& result) {
    using namespace actor_movement;
    if(slot<First||slot>Last) return false;
    const unsigned index=slot-First;
    if(!combat::FiniteRange(args[0],Minima[index],Maxima[index])) {
        result={2,L"Choose a finite movement value within the displayed range."}; return true;
    }
    if(!combat::HostFresh()||!Ready(c)) {
        result={3,L"A living Sora in a stable playable scene is required. Finish transformations and leave attached or special-character states first."}; return true;
    }
    const uintptr_t address=c.player+Offsets[index];
    if(!Writable(reinterpret_cast<void*>(address),sizeof(float))) {
        result={3,L"The current Sora movement value is not writable."}; return true;
    }
    *reinterpret_cast<float*>(address)=static_cast<float>(args[0]);
    result={0,index==3?
        L"Base jump height applied once. High Jump and special actions can select a different height; an active jump is not restarted.":
        L"Sora movement value applied once. Scripts, a new actor or a form transition can replace it; special actions may use different movement rules."};
    return true;
}
void ActorMovementSnapshot(const TrainerContext& c) {
    using namespace actor_movement;
    if(!Ready(c,true)) return;
    for(unsigned i=0;i<_countof(Offsets);++i) {
        const float value=combat::Field<float>(c.player,Offsets[i]);
        // Show finite native values even outside the trainer's edit policy.
        if(isfinite(value)) SnapshotValue(First+i,value);
    }
}
void ActorMovementCapabilities() {
    for(unsigned slot=actor_movement::First;slot<=actor_movement::Last;++slot) SupportCapability(slot);
}
