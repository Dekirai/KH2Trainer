// Read-only current-player identity. Include at shared scope after TrainerContext,
// At/Readable/DecodePacked and before feature modules. No native calls or writes.
// Evidence: research/player_roles_drive_20261007 (original build only).
#pragma once
namespace player_role {
enum Role : unsigned { Unknown=0, Sora=1, Roxas=2, Mickey=3, Other=4 };
struct Info {
    Role role=Unknown;
    unsigned characterId=0;
    int form=-1;
    uintptr_t descriptor=0,object=0;
};
template<class T> const T& Field(uintptr_t p,SIZE_T off) {
    return *reinterpret_cast<const T*>(p+off);
}
bool Range(uintptr_t p,SIZE_T n) {
    return p && n<=UINTPTR_MAX-p && Readable(reinterpret_cast<const void*>(p),n);
}
bool AllocatedStatus(uintptr_t status) {
    constexpr uintptr_t poolRva=0x2A17290;
    const uintptr_t pool=g_base+poolRva;
    if(status<pool || status>=pool+80*632 || (status-pool)%632 ||
       !Range(g_base+0x2A23950,4) || !Range(g_base+0x2A23810,80*4)) return false;
    const int count=At<int>(0x2A23950);
    if(count<0 || count>80) return false;
    bool free[80]{};
    for(int i=0;i<count;++i) {
        const int index=At<int>(0x2A23810+4*i);
        if(index<0 || index>=80 || free[index]) return false;
        free[index]=true;
    }
    return !free[(status-pool)/632] && Field<int>(status,612)>0 && Field<int>(status,612)<INT_MAX;
}
bool Listed(uintptr_t actor) {
    if(!Range(g_base+0x2A171C8,8)) return false;
    uintptr_t seen[2048]{}; unsigned count=0; bool found=false;
    uintptr_t node=At<uintptr_t>(0x2A171C8);
    while(node) {
        if(count==2048 || !Range(node,2708)) return false;
        for(unsigned i=0;i<count;++i) if(seen[i]==node) return false;
        seen[count++]=node; found|=node==actor;
        node=DecodePacked(Field<uint32_t>(node,2704));
    }
    return found;
}
bool ObjectMember(uintptr_t object) {
    if(!Range(g_base+0x2A25030,3*sizeof(uintptr_t))) return false;
    bool found=false;
    for(unsigned i=0;i<3;++i) {
        const uintptr_t table=At<uintptr_t>(0x2A25030+sizeof(uintptr_t)*i);
        if(!table) continue;
        if(!Range(table,8)) return false;
        const int count=Field<int>(table,4);
        if(count<1 || count>65536 || !Range(table,8+static_cast<SIZE_T>(count)*96)) return false;
        const uintptr_t first=table+8,end=first+static_cast<SIZE_T>(count)*96;
        if(object>=first && object<end && (object-first)%96==0) found=true;
    }
    return found;
}
Info Inspect(const TrainerContext& c) {
    Info result;
    // This identifies a coherent current Actor, not a safe gameplay phase. The
    // caller must run on the game thread and apply its scene/input/feature gates.
    if(!g_base || c.base!=g_base || !Range(g_base+0x2A105D0,8) ||
       !c.player || At<uintptr_t>(0x2A105D0)!=c.player || !Range(c.player,3592) ||
       !Range(c.status,632) || Field<uintptr_t>(c.player,1472)!=c.status ||
       DecodePacked(Field<uint32_t>(c.status,616))!=c.player ||
       !AllocatedStatus(c.status) || !Listed(c.player)) return result;
    const uintptr_t object=DecodePacked(Field<uint32_t>(c.player,8));
    const uintptr_t descriptor=DecodePacked(Field<uint32_t>(c.player,0));
    if(!Range(object,96) || !ObjectMember(object) || !Range(descriptor,8)) return result;
    const unsigned character=Field<uint16_t>(object,76);
    if(character<1 || character>15 || Field<unsigned>(c.status,608)!=character) return result;
    result={Other,character,Field<int>(c.player,3552),descriptor,object};
    const unsigned flags=Field<unsigned>(c.player,1736);
    // 405030 sets this descriptor for normal Sora/Roxas. Object+76 is the
    // character identity; shared save slot1 is deliberately not used.
    if(descriptor==g_base+0x750300 && Field<uintptr_t>(descriptor,0)==g_base+0x5CBA28 &&
       (flags&0x1000080)==0x1000080 && Field<signed char>(object,87)==result.form) {
        if(character==1 && result.form>=0 && result.form<=6) result.role=Sora;
        else if(character==14 && (result.form==0 || result.form==10)) result.role=Roxas;
    } else if(descriptor==g_base+0x7523B8 && Field<uintptr_t>(descriptor,0)==g_base+0x5D15A0 &&
              (flags&0x2000080)==0x2000080 && character==4 && result.form==11 &&
              Field<signed char>(object,87)==11) {
        result.role=Mickey; // 415670/4158C0 rescue class, not any Mickey model.
    }
    return result;
}
}
