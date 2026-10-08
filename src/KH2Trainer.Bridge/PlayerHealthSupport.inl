// HP/MP dispatch for the three audited field-player classes.
// Included after PlayerLiving/PlayerField. Evidence: docs/research/player-health-20261007.
namespace player_health {
#include "PlayerHealthPins.inl"
template<class T> const T& Field(uintptr_t p,SIZE_T offset) { return *reinterpret_cast<const T*>(p+offset); }
bool Range(uintptr_t p,SIZE_T n) { return p && n<=UINTPTR_MAX-p && Readable(reinterpret_cast<const void*>(p),n); }
bool WriteRange(uintptr_t p,SIZE_T n) { return Range(p,n) && Writable(reinterpret_cast<void*>(p),n); }
bool Span(uintptr_t base,uint64_t offset,SIZE_T n,uintptr_t& out) {
    out=0;
    if(!base || offset>UINTPTR_MAX-base) return false;
    const uintptr_t p=base+static_cast<uintptr_t>(offset);
    if(!Range(p,n)) return false;
    out=p; return true;
}
bool CodeReady(unsigned path) {
    for(const auto& pin:pins)
        if((pin.paths&path) && (!Range(g_base+pin.rva,pin.size) ||
            memcmp(reinterpret_cast<const void*>(g_base+pin.rva),pin.bytes,pin.size))) return false;
    // Ptr32 initialization must have completed. Native decoding still uses the
    // game's normal CRT/TLS machinery, on the already established game thread.
    return Range(g_base+0x2B0D920,4) && At<int>(0x2B0D920)!=0 && At<int>(0x2B0D920)!=-1;
}
bool Common(const TrainerContext& c) {
    if(!g_base || c.base!=g_base || g_disabled || !g_shared || !g_gameThread ||
        g_gameThread!=GetCurrentThreadId() || !g_shared->hostHeartbeat ||
        static_cast<DWORD>(GetTickCount()-g_shared->hostHeartbeat)>5000 || !PlayerLiving(c)) return false;
    const auto role=player_role::Inspect(c).role;
    return (role==player_role::Sora || role==player_role::Roxas || role==player_role::Mickey) && PlayerHealthControlReady(c);
}
bool SequenceReady(uintptr_t member,unsigned clip) {
    uintptr_t sequence=0;
    if(!Span(member,32,396,sequence) || !WriteRange(member,497)) return false;
    const uintptr_t animations=Field<uintptr_t>(sequence,224);
    if(!Field<unsigned>(sequence,316) && !animations) return true; // Native early return.
    uintptr_t row=0;
    if(!Span(animations,uint64_t(clip)*36,36,row)) return false;
    const unsigned first=Field<uint16_t>(row,0),count=Field<uint16_t>(row,2);
    if(!count) return true; // Native never dereferences its computed track pointer.
    uintptr_t tracks=0;
    return Span(Field<uintptr_t>(sequence,216),uint64_t(first)*144,static_cast<SIZE_T>(count)*144,tracks);
}
bool HudReady(const TrainerContext& c,int target) {
    const uintptr_t hud=At<uintptr_t>(0x2A24E90);
    if(!Range(hud,52)) return false; // 3DCBB0/3DCC10 dereference the global unconditionally.
    const uintptr_t widget=Field<uintptr_t>(hud,40);
    if(!widget || DecodePacked(Field<uint32_t>(hud,4))!=c.player || Field<int>(hud,48)!=0) return true;
    // Only the currently selected player HP widget can reach these consumers.
    // Require its maximum/history to agree with the byte-bounded player gauge;
    // this bounds native bar loops to at most one additional segment.
    if(!WriteRange(widget,19224)) return false;
    const int maximum=Field<int>(widget,19212),previous=Field<int>(widget,19220);
    if(maximum!=Field<int>(c.status,4) || previous<0 || previous>maximum) return false;
    const int current=Field<int>(c.status,0);
    if(target>current) return target<=200 || SequenceReady(widget+3584,44);
    if(!SequenceReady(widget+2072,41)) return false;
    return previous<=200 || SequenceReady(widget+3584,target>200?44u:46u);
}
bool HpReadyRaw(const TrainerContext& c,int target) {
    if(!Common(c)) return false;
    const int current=Field<int>(c.status,0),maximum=Field<int>(c.status,4),minimum=Field<int>(c.status,8);
    if(target<1 || target>maximum || minimum<0 || minimum>current || minimum>maximum) return false;
    if(target==current) return true; // Do not call native damage/HUD code for a no-op.
    if(!CodeReady(1)) return false;
    const int actual=target<minimum?minimum:target;
    if(!HudReady(c,actual)) return false;
    if(target>current) {
        const uintptr_t entries=g_base+0xABCFE8;
        if(!Range(entries,36)) return false;
        for(unsigned i=0;i<3;++i)
            if(Field<uintptr_t>(entries,i*8)==c.player && !WriteRange(entries+24+i*4,4)) return false;
    }
    return true;
}
bool MpReadyRaw(const TrainerContext& c) {
    if(!Common(c)) return false;
    if(Field<int>(c.status,384)==Field<int>(c.status,388) && Field<float>(c.status,448)<=0) return true;
    // Full MP clears positive recharge before adding a nonnegative, byte-bounded
    // maximum. With effects=0 no native recovery animation or depletion branch runs.
    return CodeReady(2);
}
bool HpReady(const TrainerContext& c,int target) {
    __try { return HpReadyRaw(c,target); } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool MpReady(const TrainerContext& c) {
    __try { return MpReadyRaw(c); } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
using HpFn=int (__fastcall*)(void*,int,unsigned,BYTE);
using MpFn=void (__fastcall*)(void*,BYTE);
#ifdef KH2_PLAYER_HEALTH_TESTS
HpFn testHp=nullptr;
MpFn testMp=nullptr;
#endif
bool SetHp(const TrainerContext& c,int target) {
    if(!HpReady(c,target)) return false;
    const int delta=target-Field<int>(c.status,0);
    if(!delta) return true;
    HpFn fn=reinterpret_cast<HpFn>(c.base+0x3D2EB0);
#ifdef KH2_PLAYER_HEALTH_TESTS
    fn=testHp;
    if(!fn) return false;
#endif
    fn(reinterpret_cast<void*>(c.player),delta,0,0);
    return true;
}
bool FullMp(const TrainerContext& c) {
    if(!MpReady(c)) return false;
    if(Field<int>(c.status,384)==Field<int>(c.status,388) && Field<float>(c.status,448)<=0) return true;
    MpFn fn=reinterpret_cast<MpFn>(c.base+0x3C2040);
#ifdef KH2_PLAYER_HEALTH_TESTS
    fn=testMp;
    if(!fn) return false;
#endif
    fn(reinterpret_cast<void*>(c.status),0);
    return true;
}
}
