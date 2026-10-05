// Current-player loot ability values. Full native evidence: loot_controls_deep_*.
// Included after DamageTuningFeatures.inl; shares the allocated STATUS guard.
// No retained actor pointers, callbacks, save edits, or continuous overrides.
namespace loot_features {
constexpr unsigned First=352, LastEdit=355, Last=359;
constexpr unsigned Offsets[]={520,568,572,580};
constexpr double Maxima[]={5000,9,99,100};
bool PlayerReady(const TrainerContext& c,bool paused=false) {
    return damage_tuning::Ready(c,paused) &&
        combat::Field<uintptr_t>(c.status,504)==c.status;
}
bool PartyTotals(const TrainerContext& c,double& quantity,double& luck,double& retained) {
    quantity=At<float>(0x2A11418); luck=1; retained=1;
    if(!isfinite(quantity)) return false;
    for(unsigned i=0;i<3;++i) {
        const uintptr_t actor=i?At<uintptr_t>(0x2A239B0+(i-1)*sizeof(uintptr_t)):c.player;
        if(!actor) continue;
        // The native calculation includes each non-deleting listed party actor,
        // including actors whose HP is zero. Missing actors contribute nothing.
        if(!combat::Listed(actor)) continue;
        if(!Readable(reinterpret_cast<void*>(actor),2708)) return false;
        if(combat::Field<unsigned>(actor,288)&0x10080000) continue;
        const uintptr_t status=combat::Field<uintptr_t>(actor,1472);
        if(!status) continue;
        if(!damage_tuning::PoolOwns(status) ||
           DecodePacked(combat::Field<uint32_t>(status,616))!=actor ||
           combat::Field<uintptr_t>(status,504)!=status) return false;
        const float q=combat::Field<float>(status,568), l=combat::Field<float>(status,572),
                    r=combat::Field<float>(status,580);
        if(!isfinite(q)||!isfinite(l)||!isfinite(r)) return false;
        // Match native float32 additions/products, rather than suggesting
        // extra precision in a readout of the game's actual computation.
        quantity=static_cast<float>(static_cast<float>(quantity)+q);
        luck=static_cast<float>(static_cast<float>(luck)+l);
        retained=static_cast<float>(static_cast<float>(retained)*r);
    }
    return isfinite(quantity)&&isfinite(luck)&&isfinite(retained);
}
}

bool LootHandle(const TrainerContext& c,unsigned slot,const double args[8],TrainerResult& result) {
    using namespace loot_features;
    if(slot<First||slot>Last) return false;
    if(slot>LastEdit) { result={1,L"This loot value is a read-only calculation."}; return true; }
    const unsigned index=slot-First;
    if(!combat::FiniteRange(args[0],0,Maxima[index])) {
        result={2,L"Choose a finite loot value within the displayed range."}; return true;
    }
    if(!combat::HostFresh()||!PlayerReady(c)) {
        result={3,L"A living player with an allocated status in a stable playable scene is required."}; return true;
    }
    const uintptr_t address=c.status+Offsets[index];
    if(!Writable(reinterpret_cast<void*>(address),sizeof(float))) {
        result={3,L"The current loot value is not writable."}; return true;
    }
    *reinterpret_cast<float*>(address)=static_cast<float>(index==3?args[0]/100.0:args[0]);
    result={0,L"Current-player loot value applied once. Status rebuilds may replace it; ordinary drop, collection and mission rules still apply."};
    return true;
}
void LootSnapshot(const TrainerContext& c) {
    using namespace loot_features;
    if(!PlayerReady(c,true)) return;
    for(unsigned i=0;i<4;++i) {
        const float value=combat::Field<float>(c.status,Offsets[i]);
        if(isfinite(value)) SnapshotValue(First+i,i==3?value*100.0:value);
    }
    const float draw=combat::Field<float>(c.status,520), extra=combat::Field<float>(c.status,452);
    if(isfinite(draw)&&isfinite(extra)) {
        float radius=120;
        if(combat::Field<unsigned>(c.player,1736)&4) radius+=draw;
        radius+=extra;
        if(isfinite(radius)) SnapshotValue(356,radius);
    }
    double quantity=0,luck=0,retained=0;
    if(PartyTotals(c,quantity,luck,retained)) {
        SnapshotValue(357,quantity); SnapshotValue(358,luck); SnapshotValue(359,retained*100);
    }
}
void LootCapabilities() { for(unsigned slot=loot_features::First;slot<=loot_features::Last;++slot) SupportCapability(slot); }
