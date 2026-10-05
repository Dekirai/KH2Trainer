// Runtime received-hit coefficients, not final HP-delta multipliers.
// Evidence: combat_scaling_deep*.json and damage_tuning_independent_review.txt.
// Included after CombatFeatures.inl. No retained actor pointers or native hooks.
namespace damage_tuning {
constexpr uintptr_t StatusPoolRva=0x2A17290, FreeListRva=0x2A23810, FreeCountRva=0x2A23950;
constexpr unsigned StatusCount=80, StatusSize=632;
bool PoolOwns(uintptr_t status) {
    const uintptr_t pool=g_base+StatusPoolRva;
    if(status<pool || status>=pool+StatusCount*StatusSize || (status-pool)%StatusSize ||
       !Readable(reinterpret_cast<void*>(status),StatusSize) ||
       combat::Field<int>(status,612)<=0) return false;
    const int count=At<int>(FreeCountRva);
    if(count<0 || count>static_cast<int>(StatusCount)) return false;
    bool free[StatusCount]{};
    for(int i=0;i<count;++i) {
        const int index=At<int>(FreeListRva+sizeof(int)*i);
        if(index<0 || index>=static_cast<int>(StatusCount) || free[index]) return false;
        free[index]=true;
    }
    return !free[(status-pool)/StatusSize];
}
bool Ready(const TrainerContext& c,bool allowPause=false) {
    return g_base && c.base==g_base && g_shared && !g_disabled &&
        g_gameThread && GetCurrentThreadId()==g_gameThread &&
        !At<uintptr_t>(0x2AE9FA8) && !(At<unsigned>(0x2A10504)&2) &&
        combat::PlayerReady(c,allowPause) && combat::Listed(c.player) && PoolOwns(c.status);
}
bool Resolve(const TrainerContext& c,bool target,bool allowPause,uintptr_t& status) {
    status=0;
    if(!Ready(c,allowPause)) return false;
    if(!target) { status=c.status; return true; }
    combat::Target t{};
    // Both the readout and the one-shot command name the manual lock-on target.
    if(!combat::GetTarget(c,t,true,allowPause) || !PoolOwns(t.status)) return false;
    status=t.status; return true;
}
}

bool DamageTuningHandle(const TrainerContext& c,unsigned slot,const double args[8],TrainerResult& result) {
    if(slot<272 || slot>293) return false;
    if(slot>=286) { result={1,L"Base damage limits are read-only diagnostics."}; return true; }
    if(!IsInteger(args[0],0,255)) { result={2,L"Use a whole-number damage coefficient from 0 to 255 percent."}; return true; }
    const bool target=slot>=279;
    uintptr_t status=0;
    if(!combat::HostFresh() || !damage_tuning::Resolve(c,target,false,status)) {
        result={3,target?L"Manually lock on to a living enemy in a stable playable scene first.":
            L"A living player in a stable playable scene and a fresh trainer connection are required."};
        return true;
    }
    const unsigned offset=424+slot-(target?279:272);
    if(!Writable(reinterpret_cast<void*>(status+offset),1)) { result={3,L"The current damage coefficient is not writable."}; return true; }
    combat::Field<BYTE>(status,offset)=static_cast<BYTE>(args[0]);
    result={0,L"Runtime received-hit coefficient applied once. Equipment, scripts or a new actor may replace it. Healing and direct scripted HP changes are separate."};
    return true;
}
void DamageTuningSnapshot(const TrainerContext& c) {
    for(unsigned target=0;target<2;++target) {
        uintptr_t status=0;
        if(!damage_tuning::Resolve(c,target!=0,true,status)) continue;
        for(unsigned i=0;i<7;++i) SnapshotValue(272+target*7+i,combat::Field<BYTE>(status,424+i));
        for(unsigned i=0;i<4;++i) SnapshotValue(286+target*4+i,combat::Field<int>(status,408+4*i));
    }
}
void DamageTuningCapabilities() { for(unsigned slot=272;slot<=293;++slot) SupportCapability(slot); }
