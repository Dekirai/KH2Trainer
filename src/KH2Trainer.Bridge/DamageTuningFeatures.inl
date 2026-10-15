// Runtime received-hit coefficients, not final HP-delta multipliers.
// Evidence: combat_scaling_deep*.json and damage_tuning_independent_review.txt.
// Included after CombatFeatures.inl. No retained actor pointers or native hooks.
namespace damage_tuning {
constexpr uintptr_t StatusPoolRva=0x2A17290, FreeListRva=0x2A23810, FreeCountRva=0x2A23950, EnemyParamsRva=0x2AE57C0;
constexpr unsigned StatusCount=80, StatusSize=632, EnemyRowSize=92, EnemyRowLimit=4096;
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
// Evidence: actor-rebind-context-20261008. 3C2240 stores EncodeNullable(row) at
// STATUS+624; 3EBF30 bsearches 92-byte rows at [2AE57C0]+8, signed count at +4.
bool EnemyRow(uintptr_t status,uintptr_t& row) {
    row=0;
    const uintptr_t table=At<uintptr_t>(EnemyParamsRva);
    if(!Readable(reinterpret_cast<void*>(table),8)) return false;
    const int count=combat::Field<int>(table,4);
    if(count<1 || count>static_cast<int>(EnemyRowLimit)) return false;
    const uintptr_t rows=table+8,candidate=DecodePacked(combat::Field<uint32_t>(status,624));
    if(candidate<rows || candidate-rows>=uintptr_t(EnemyRowSize)*static_cast<uintptr_t>(count) ||
       (candidate-rows)%EnemyRowSize || !Readable(reinterpret_cast<void*>(candidate),EnemyRowSize)) return false;
    row=candidate; return true;
}
}

bool DamageTuningHandle(const TrainerContext& c,unsigned slot,const double args[8],TrainerResult& result) {
    if(slot<272 || slot>297) return false;
    if(slot==297) {
        uintptr_t status=0,row=0;
        if(!combat::HostFresh() || !damage_tuning::Resolve(c,true,false,status) || !damage_tuning::EnemyRow(status,row)) {
            result={3,L"Manually lock on to a living enemy with a validated enemy parameter entry in a stable playable scene first."};
            return true;
        }
        if(!Writable(reinterpret_cast<void*>(status+424),7)) { result={3,L"The target damage coefficients are not writable."}; return true; }
        // 3C2240 initializes STATUS+424..430 from parameter bytes +72,+74,...,+84.
        for(unsigned i=0;i<7;++i) combat::Field<BYTE>(status,424+i)=combat::Field<BYTE>(row,72+2*i);
        result={0,L"Target damage coefficients reset to its enemy parameter defaults. Every actor sharing this STATUS is affected; scripts or a new actor may replace them."};
        return true;
    }
    if(slot>=294) { result={1,L"Enemy parameter readouts are read-only diagnostics."}; return true; }
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
        if(!target) continue;
        // STATUS+612 is the record's reference count; 3C06B0 reuses an enemy record by row and increments it.
        SnapshotValue(296,combat::Field<int>(status,612));
        uintptr_t row=0;
        if(!damage_tuning::EnemyRow(status,row)) continue;
        SnapshotValue(294,combat::Field<uint16_t>(row,0));
        SnapshotValue(295,combat::Field<uint16_t>(row,2)); // Level selector; 0 selects the native default row.
    }
}
void DamageTuningCapabilities() { for(unsigned slot=272;slot<=297;++slot) SupportCapability(slot); }
