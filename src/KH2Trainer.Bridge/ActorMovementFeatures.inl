// Current playable-character movement parameters. Evidence: actor_controls_deep.*
// and docs/research/actor-movement-roles-20261007. The shared Actor base initializes
// this block for Sora, Roxas and rescue Mickey; individual Actions may override it.
// Include after DamageTuningFeatures.inl. These are one-time runtime edits;
// there are no retained Actor pointers, callbacks, save edits or auto-restores.
#include <limits.h>
#include "PlayerRoleSupport.inl"
namespace actor_movement {
constexpr unsigned First=344,Last=347;
constexpr unsigned Offsets[]={296,300,312,304};
constexpr double Minima[]={0,0,0.1,0};
constexpr double Maxima[]={32,64,100,1000};
// Preserve this original Sora-only contract: CollisionFeatures and
// TargetingFeatures also use Ready. Only this module uses MovementReady below.
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
bool MovementReady(const TrainerContext& c,bool allowPause=false) {
    if(!damage_tuning::Ready(c,allowPause) ||
       !Readable(reinterpret_cast<void*>(c.player),3608) ||
       (combat::Field<unsigned>(c.player,288)&0x10080100) ||
       combat::Field<uint32_t>(c.player,1696) ||
       combat::Field<uintptr_t>(c.player,360)!=c.player ||
       At<BYTE>(0xABAC58) || At<BYTE>(0xABAC59) ||
       !Readable(At<void*>(0x9BA920),8)) return false;
    const player_role::Info identity=player_role::Inspect(c);
    uintptr_t vtable=0,callback=0;
    const BYTE* code=nullptr;
    static const BYTE normalCode[]={0x48,0x8B,0xCA,0xE9,0xE8,0x3F,0xFA,0xFF};
    static const BYTE mickeyCode[]={0x48,0x8B,0xCA,0xE9,0xB8,0x3A,0xF9,0xFF};
    if(identity.role==player_role::Sora || identity.role==player_role::Roxas) {
        vtable=0x5CBA28; callback=0x404FB0; code=normalCode;
        // This saved active-Drive byte belongs to Sora. Roxas/Mickey identity
        // is instead established from the actual Actor/object/status tuple.
        if(identity.role==player_role::Sora && At<BYTE>(0x9ACDD4)!=identity.form) return false;
    } else if(identity.role==player_role::Mickey) {
        vtable=0x5D15A0; callback=0x4154E0; code=mickeyCode;
    } else return false;
    // Both exact wrappers pass RDX=Actor to the shared 3A8FA0 consumer.
    // These bytes are inspected only; no callback or executable page is changed.
    return At<uintptr_t>(vtable+296)==g_base+callback &&
        Readable(reinterpret_cast<void*>(g_base+callback),sizeof(normalCode)) &&
        !memcmp(reinterpret_cast<void*>(g_base+callback),code,sizeof(normalCode));
}
}
bool ActorMovementHandle(const TrainerContext& c,unsigned slot,const double args[8],TrainerResult& result) {
    using namespace actor_movement;
    if(slot<First||slot>Last) return false;
    const unsigned index=slot-First;
    if(!combat::FiniteRange(args[0],Minima[index],Maxima[index])) {
        result={2,L"Choose a finite movement value within the displayed range."}; return true;
    }
    if(!combat::HostFresh()||!MovementReady(c)) {
        result={3,L"Living Sora, Roxas or rescue Mickey in a stable playable scene is required. Finish transformations and leave attached states first."}; return true;
    }
    const uintptr_t address=c.player+Offsets[index];
    if(!Writable(reinterpret_cast<void*>(address),sizeof(float))) {
        result={3,L"The current player's movement value is not writable."}; return true;
    }
    *reinterpret_cast<float*>(address)=static_cast<float>(args[0]);
    result={0,index==3?
        L"Base jump height applied once. High Jump and special actions can select a different height; an active jump is not restarted.":
        L"Player movement value applied once. Scripts, a new actor or a form transition can replace it; special actions may use different movement rules."};
    return true;
}
void ActorMovementSnapshot(const TrainerContext& c) {
    using namespace actor_movement;
    if(!MovementReady(c,true)) return;
    for(unsigned i=0;i<_countof(Offsets);++i) {
        const float value=combat::Field<float>(c.player,Offsets[i]);
        // Show finite native values even outside the trainer's edit policy.
        if(isfinite(value)) SnapshotValue(First+i,value);
    }
}
void ActorMovementCapabilities() {
    for(unsigned slot=actor_movement::First;slot<=actor_movement::Last;++slot) SupportCapability(slot);
}
