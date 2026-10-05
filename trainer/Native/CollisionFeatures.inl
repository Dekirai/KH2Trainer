// Last native collision results and an owned Sora body-separation flag.
// Evidence: actor_collision_round4_*.json. Include after ActorMovementFeatures.
// No probe getters, collision resolvers, shape mutation, or retained collider nodes.
namespace collision_features {
constexpr unsigned First=376, Last=391;
constexpr uint32_t SeparationDisabled=2;
struct Lease {
    bool active;
    uintptr_t actor,status,scheduler,heap;
    int form;
    BYTE map[10];
} lease{};

bool SameIdentity() {
    // Restoration deliberately does not need a live host or positive HP. It
    // does need a fresh, stable native scene and the still allocated actor.
    if(!lease.active || !g_base || !g_gameThread || GetCurrentThreadId()!=g_gameThread ||
       At<BYTE>(0x9BA8D0)!=1 || At<BYTE>(0x9BA8D1) || At<uintptr_t>(0x9BA928) ||
       At<uintptr_t>(0x2AE9FA8) || (At<unsigned>(0x2A10504)&2) ||
       At<uintptr_t>(0x2A105D0)!=lease.actor ||
       At<uintptr_t>(0x716868)!=lease.scheduler || At<uintptr_t>(0x9BA920)!=lease.heap ||
       !Readable(reinterpret_cast<void*>(lease.scheduler),72) ||
       !Readable(reinterpret_cast<void*>(lease.heap),8) ||
       memcmp(lease.map,reinterpret_cast<void*>(g_base+0x717008),sizeof(lease.map)) ||
       !combat::Listed(lease.actor) || !Readable(reinterpret_cast<void*>(lease.actor),3608) ||
       !damage_tuning::PoolOwns(lease.status)) return false;
    return combat::Field<uintptr_t>(lease.actor,1472)==lease.status &&
        DecodePacked(combat::Field<uint32_t>(lease.status,616))==lease.actor &&
        combat::Field<int>(lease.status,608)==1 &&
        DecodePacked(combat::Field<uint32_t>(lease.actor,0))==g_base+0x750300 &&
        combat::Field<uintptr_t>(lease.actor,360)==lease.actor &&
        combat::Field<int>(lease.actor,3552)==lease.form && At<BYTE>(0x9ACDD4)==lease.form &&
        !(combat::Field<unsigned>(lease.actor,288)&0x10080000);
}
void Release() {
    if(SameIdentity() && Writable(reinterpret_cast<void*>(lease.actor+288),sizeof(LONG))) {
        auto flags=reinterpret_cast<volatile LONG*>(lease.actor+288);
        const LONG before=*flags;
        if(before&SeparationDisabled)
            InterlockedCompareExchange(flags,before&~LONG(SeparationDisabled),before);
    }
    // A replaced actor, changed scene, removed bit, or lost CAS relinquishes
    // ownership. Never force an old actor back into the native list.
    lease={};
}
bool BodyBuffer(uintptr_t actor,int& count) {
    count=0;
    const uintptr_t buffer=combat::Field<uintptr_t>(actor,2560);
    if(!Readable(reinterpret_cast<void*>(buffer),24) ||
       combat::Field<uintptr_t>(buffer,8)!=actor || combat::Field<unsigned>(buffer,16)!=1) return false;
    const int n=combat::Field<int>(buffer,0);
    const uintptr_t resource=combat::Field<uintptr_t>(actor,2744);
    if(!Readable(reinterpret_cast<void*>(resource),64)) return false;
    const int capacity=combat::Field<int>(resource,0);
    // 4096 is a diagnostic policy bound, not an asserted game-format limit.
    if(capacity<0 || capacity>4096 || n<0 || n>capacity ||
       !Readable(reinterpret_cast<void*>(resource),64+size_t(capacity)*20)) return false;
    int bodyCapacity=0;
    for(int i=0;i<capacity;++i)if(combat::Field<BYTE>(resource,64+size_t(i)*20+4)==1)++bodyCapacity;
    if(n>bodyCapacity || !Readable(reinterpret_cast<void*>(buffer),24+size_t(n)*40))return false;
    count=n;return true;
}
bool WorldEnabled(uintptr_t actor) {
    return (combat::Field<unsigned>(actor,2488)&1) &&
        !(combat::Field<unsigned>(actor,288)&1) && !combat::Field<uint32_t>(actor,1696);
}
bool CacheEligible(uintptr_t actor) {
    const uintptr_t stopContext=At<uintptr_t>(0xBF2AC8);
    if(stopContext) {
        if(!Readable(reinterpret_cast<void*>(stopContext),112))return false;
        for(unsigned i=0;i<4;++i)if(combat::Field<uintptr_t>(stopContext,80+i*8))return false;
    }
    return WorldEnabled(actor) && At<int>(0x716884)==1 &&
        !(combat::Field<unsigned>(actor,292)&0x40) &&
        !(combat::Field<unsigned>(actor,288)&0x400) &&
        !(combat::Field<BYTE>(actor,1612)&1) && !(At<unsigned>(0x2A11400)&0x20) &&
        (combat::Field<unsigned>(actor,1736)&0x44) &&
        Readable(At<void*>(0xABD448),248);
}
}

bool CollisionHandle(const TrainerContext& c,unsigned slot,const double args[8],TrainerResult& result) {
    using namespace collision_features;
    if(slot<First || slot>Last)return false;
    if(slot!=First){result={1,L"This is a read-only record of native collision state."};return true;}
    if(!IsInteger(args[0],0,1)){result={2,L"Choose On or Off."};return true;}
    if(!args[0]){Release();result={0,L"Sora body-separation override released where still owned."};return true;}
    if(!combat::HostFresh() || !actor_movement::Ready(c)) {
        result={3,L"A living Sora in a stable playable scene is required. Finish transformations first."};return true;
    }
    if(lease.active) {
        if(SameIdentity() && (combat::Field<unsigned>(c.player,288)&SeparationDisabled)) {
            result={0,L"Sora body-separation override is already active."};return true;
        }
        Release();
    }
    int count=0;
    if(!BodyBuffer(c.player,count) || count==0 || (combat::Field<unsigned>(c.player,2488)&0x1000) ||
       (combat::Field<unsigned>(c.player,288)&SeparationDisabled) ||
       !Writable(reinterpret_cast<void*>(c.player+288),sizeof(LONG))) {
        result={3,L"A valid active Sora body-shape buffer is required. An existing native separation override is left unchanged."};return true;
    }
    Lease candidate={true,c.player,c.status,At<uintptr_t>(0x716868),At<uintptr_t>(0x9BA920),
        combat::Field<int>(c.player,3552),{}};
    memcpy(candidate.map,reinterpret_cast<void*>(g_base+0x717008),sizeof(candidate.map));
    const LONG before=combat::Field<LONG>(c.player,288);
    if(InterlockedCompareExchange(reinterpret_cast<volatile LONG*>(c.player+288),
       before|LONG(SeparationDisabled),before)!=before) {
        result={3,L"The actor flags changed before the override could be acquired."};return true;
    }
    lease=candidate;
    result={0,L"Sora no longer participates in actor body separation. World collision and hit detection keep their own rules. The override ends with this actor or scene."};
    return true;
}
void CollisionTick(const TrainerContext& c) {
    using namespace collision_features;
    if(!lease.active)return;
    if(!combat::HostFresh() || !actor_movement::Ready(c,true) || !SameIdentity() ||
       !(combat::Field<unsigned>(lease.actor,288)&SeparationDisabled))Release();
}
void CollisionReset(const TrainerContext&) { collision_features::Release(); }
void CollisionSnapshot(const TrainerContext& c) {
    using namespace collision_features;
    if(!actor_movement::Ready(c,true))return;
    const uintptr_t actor=c.player;
    SnapshotValue(376,lease.active && SameIdentity() && (combat::Field<unsigned>(actor,288)&SeparationDisabled)?1:0);
    SnapshotValue(377,WorldEnabled(actor)?1:0);
    int shapes=0;
    if(BodyBuffer(actor,shapes))SnapshotValue(378,shapes>0 &&
        !(combat::Field<unsigned>(actor,288)&SeparationDisabled) &&
        !(combat::Field<unsigned>(actor,2488)&0x1000)?1:0);
    const uint32_t flags=combat::Field<uint32_t>(actor,1860);
    SnapshotValue(379,flags);
    SnapshotValue(391,(combat::Field<unsigned>(actor,1856)>>3)&15);
    const unsigned offsets[]={1776,1780,1852};
    for(unsigned i=0;i<3;++i) {
        const float value=combat::Field<float>(actor,offsets[i]);
        if(isfinite(value))SnapshotValue(384+i,value);
    }
    // These are last-evaluated cached values, not a new collision query. Even
    // with these guards no native per-result frame/generation stamp is known.
    if(!CacheEligible(actor))return;
    const uint16_t polygon=combat::Field<uint16_t>(actor,1840);
    SnapshotValue(383,(flags&4)?1:0);
    const float height=combat::Field<float>(actor,1848);
    if(!(flags&2) && isfinite(height))SnapshotValue(381,height);
    if(polygon==0xFFFF || (flags&2) || !isfinite(height))return;
    SnapshotValue(380,polygon);
    SnapshotValue(382,(flags&1)?0:1);
    SnapshotValue(390,combat::Field<uintptr_t>(actor,1864)?1:0);
    // Copy the already transformed/normalized support cache. Do not follow
    // its borrowed dynamic-collider pointer or invoke a mutating probe getter.
    const float x=combat::Field<float>(actor,1880),y=combat::Field<float>(actor,1884),z=combat::Field<float>(actor,1888);
    const double length=double(x)*x+double(y)*y+double(z)*z;
    if(isfinite(x)&&isfinite(y)&&isfinite(z)&&length>=0.99&&length<=1.01) {
        SnapshotValue(387,x);SnapshotValue(388,y);SnapshotValue(389,z);
    }
}
void CollisionCapabilities() { for(unsigned slot=collision_features::First;slot<=collision_features::Last;++slot)SupportCapability(slot); }
