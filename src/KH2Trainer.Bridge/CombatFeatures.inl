// Combat evidence: research archive (see README): combat.json and combat_evidence.json.
// All installation, commands, and snapshots run on the game's update thread.
namespace combat {
constexpr uintptr_t LockRva=0x2A11208;
template<class T> T& Field(uintptr_t p,size_t n) { return *reinterpret_cast<T*>(p+n); }
bool FiniteRange(double v,double low,double high) { return isfinite(v)&&v>=low&&v<=high; }
bool PhaseReady(bool allowFieldPause=false) {
    const int phase=At<int>(0x716884);
    return At<BYTE>(0x9BA8D0)==1 && !At<BYTE>(0x9BA8D1) && (phase==1||(allowFieldPause&&phase==2)) &&
           !At<uintptr_t>(0x9BA928) && !At<BYTE>(0x9006B0) && !At<uintptr_t>(0xAC0F48) &&
           Readable(At<void*>(0x716868),72);
}
bool HostFresh() {
    return !InterlockedCompareExchange(&g_disabled,0,0) && g_shared &&
           g_shared->hostHeartbeat!=0 && DWORD(GetTickCount()-g_shared->hostHeartbeat)<=5000;
}
bool PlayerReady(const TrainerContext& c,bool allowFieldPause=false) {
    return c.sceneReady && c.player && c.status && PhaseReady(allowFieldPause) &&
           At<uintptr_t>(0x2A105D0)==c.player && Readable(reinterpret_cast<void*>(c.player),3588) &&
           Readable(reinterpret_cast<void*>(c.status),632) && Field<uintptr_t>(c.player,1472)==c.status &&
           DecodePacked(Field<uint32_t>(c.status,616))==c.player &&
           (Field<uint32_t>(c.player,1736)&0x80) && !(Field<uint32_t>(c.player,288)&0x10080000) &&
           !(Field<uint32_t>(c.player,2488)&4) && Field<int>(c.status,0)>0 &&
           Field<int>(c.status,0)<=Field<int>(c.status,4) && Field<int>(c.status,4)<=255;
}
// Validate the complete bounded live list before trusting a target. No retained
// target pointer is ever dereferenced by a later frame or reset operation.
bool Listed(uintptr_t actor) {
    uintptr_t seen[2048]{}; unsigned count=0; bool found=false;
    uintptr_t node=At<uintptr_t>(0x2A171C8);
    while(node) {
        if(count==_countof(seen)||!Readable(reinterpret_cast<void*>(node),2708))return false;
        for(unsigned i=0;i<count;++i)if(seen[i]==node)return false;
        seen[count++]=node;
        if(node==actor)found=true;
        node=DecodePacked(Field<uint32_t>(node,2704));
    }
    return found;
}
struct Target { uintptr_t actor,status; int mode; bool revenge; };
bool GetTarget(const TrainerContext& c,Target& t,bool manual=false,bool allowFieldPause=false) {
    t={};
    if(!PlayerReady(c,allowFieldPause)||Field<uintptr_t>(c.player,3528)!=c.base+LockRva||
       At<uintptr_t>(LockRva+56)!=c.player)return false;
    const int mode=At<int>(LockRva);
    if((mode!=1&&mode!=2)||(manual&&mode!=2)||At<uint32_t>(LockRva+12))return false;
    const uintptr_t actor=DecodePacked(At<uint32_t>(LockRva+4));
    if(!actor||actor==c.player||!Listed(actor)||!Readable(reinterpret_cast<void*>(actor),3408)||
       !(Field<uint32_t>(actor,1736)&0x10)||!(Field<uint32_t>(actor,1736)&2)||
       (Field<uint32_t>(actor,288)&0x10080000)||(Field<uint32_t>(actor,2488)&4))return false;
    const uintptr_t status=Field<uintptr_t>(actor,1472);
    if(!Readable(reinterpret_cast<void*>(status),632)||DecodePacked(Field<uint32_t>(status,616))!=actor||
       Field<uint32_t>(status,592)||Field<uint32_t>(status,620)||
       Field<int>(status,0)<=0||Field<int>(status,4)<=0||Field<int>(status,4)>1000000||
       Field<int>(status,0)>Field<int>(status,4)||Field<int>(status,8)<0||
       Field<int>(status,8)>Field<int>(status,4))return false;
    t={actor,status,mode,FiniteRange(Field<float>(actor,3400),0,1000000)&&
                          FiniteRange(Field<float>(actor,3404),0.000001,1000000)};
    return true;
}
#include "CombatGuardSupport.inl"

}

bool CombatHandle(const TrainerContext& c,unsigned slot,const double args[8],TrainerResult& result) {
    if(slot==combat::OwnedGuardSlot) return combat::OwnedGuardHandle(c,args,result);
    if(slot<98||slot>110||slot==109)return false;
    result={1,L"This combat value is read-only."};
    if(slot==106) {
        if(!IsInteger(args[0],0,1)){result={2,L"Choose On or Off."};return true;}
        if(!args[0]){combat::StopGuard();result={0,L"Player HP damage guard disabled."};return true;}
        if(!combat::StartGuard(c)){result={3,L"A controlled supported player, a fresh connection and verified native callbacks are required."};return true;}
        result={0,L"HP damage through the player callback is blocked, including its damage-driven Drive and MP gains. Hit reactions and direct scripted changes still apply."};return true;
    }
    if(slot!=102&&slot!=103&&slot!=104&&slot!=110)return true;
    combat::Target t{};
    if(!combat::GetTarget(c,t,true)){result={3,L"Manually lock on to a living enemy during gameplay first."};return true;}
    if(slot==102||slot==110) {
        const int maximum=combat::Field<int>(t.status,4);
        const int floor=combat::Field<int>(t.status,8);
        const int minimum=floor>1?floor:1;
        if(slot==110&&!IsInteger(args[0],minimum,maximum)){result={2,L"Target HP must be an integer above zero, at least its native HP floor, and no higher than its maximum."};return true;}
        if(!Writable(reinterpret_cast<void*>(t.status),12)){result={3,L"Target HP is not writable."};return true;}
        // A nonlethal assignment avoids native death/reward callbacks. No max,
        // minimum-HP, character save, AI state, or damage callback is changed.
        combat::Field<int>(t.status,0)=slot==102?maximum:static_cast<int>(args[0]);
        result={0,L"Living target HP updated. Battle phase scripts may react to the new HP."};return true;
    }
    if(!t.revenge||!Writable(reinterpret_cast<void*>(t.actor+3400),4)) {
        result={3,L"This enemy does not expose a validated revenge value."};return true;
    }
    if(slot==104&&!combat::FiniteRange(args[0],0,1000000)){result={2,L"Revenge value must be finite and between 0 and 1000000."};return true;}
    combat::Field<float>(t.actor,3400)=slot==103?0.0f:static_cast<float>(args[0]);
    result={0,L"Target revenge value updated. Its native threshold and AI remain unchanged."};return true;
}
void CombatTick(const TrainerContext& c) { combat::TickGuard(c); }
void CombatSnapshot(const TrainerContext& c) {
    const bool effective=combat::GuardContext(c);
    const uint64_t owner=effective?combat::guard.owner:0;
    SnapshotValue(106,effective?1:0);
    SnapshotValue(combat::GuardOwnerLowSlot,static_cast<uint32_t>(owner));
    SnapshotValue(combat::GuardOwnerHighSlot,static_cast<uint32_t>(owner>>32));
    SnapshotValue(107,static_cast<double>(combat::blockedHits));
    SnapshotValue(108,combat::lastBlockedDamage);
    if(combat::PlayerReady(c,true)&&combat::Field<uintptr_t>(c.player,3528)==c.base+combat::LockRva&&
       At<uintptr_t>(combat::LockRva+56)==c.player) {
        const int mode=At<int>(combat::LockRva);
        if(mode>=0&&mode<=3)SnapshotValue(105,mode);
    }
    combat::Target t{};
    if(combat::GetTarget(c,t,false,true)) {
        SnapshotValue(98,combat::Field<int>(t.status,0));SnapshotValue(99,combat::Field<int>(t.status,4));
        if(t.revenge){SnapshotValue(100,combat::Field<float>(t.actor,3400));SnapshotValue(101,combat::Field<float>(t.actor,3404));}
    }
}
void CombatCapabilities() {
    for(unsigned s=98;s<=110;++s)if(s!=109)SupportCapability(s);
    SupportCapability(combat::OwnedGuardSlot);
    SupportCapability(combat::GuardOwnerLowSlot);SupportCapability(combat::GuardOwnerHighSlot);
}
void CombatReset(const TrainerContext&) { combat::StopGuard(); }
