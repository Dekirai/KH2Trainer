// Player motion playback: work/trainer/research/motion_control.*.
// Commands and lease maintenance run after update on the engine thread.
namespace motion_features {
constexpr uintptr_t kWriter=0x42FCE0,kSlot=0x755A20,kBank=0x755370,kBankRoot=0x753498;
constexpr BYTE kWriterBytes[]={0x48,0x83,0xec,0x38,0x0f,0x29,0x74,0x24,0x20,0xf3,0x0f,0x10,0x71,0x08,0x8b,0x09,0xe8,0x7b,0xd5,0x07,0x00,0x8b,0x48,0x04,0xe8,0x73,0xd5,0x07,0x00,0xf3,0x0f,0x11,0xb0,0xa8,0x02,0x00,0x00,0x0f,0x28,0x74,0x24,0x20,0x48,0x83,0xc4,0x38,0xc3};
using WriterFn=void (__fastcall*)(uint32_t*);
WriterFn originalWriter=nullptr;
#ifdef KH2_MOTION_TESTS
WriterFn testWriter=nullptr;
bool testPin=true;
#endif
template<class T> T& Field(uintptr_t p,SIZE_T offset) { return *reinterpret_cast<T*>(p+offset); }
bool Range(uintptr_t p,SIZE_T n) { return p && Readable(reinterpret_cast<const void*>(p),n); }
bool Finite(double x,double low,double high) { return isfinite(x)&&x>=low&&x<=high; }
uint32_t Bits(float value) { uint32_t bits=0; memcpy(&bits,&value,4); return bits; }
bool OnThread() { return g_gameThread && GetCurrentThreadId()==g_gameThread; }
bool HostFresh() {
    return !InterlockedCompareExchange(&g_disabled,0,0) && g_shared && g_shared->hostHeartbeat &&
        static_cast<DWORD>(GetTickCount()-g_shared->hostHeartbeat)<=5000;
}
bool Listed(uintptr_t actor) {
    uintptr_t seen[2048]{}; unsigned count=0; bool found=false;
    uintptr_t node=At<uintptr_t>(0x2A171C8);
    while(node) {
        if(count==_countof(seen) || !Range(node,2708)) return false;
        for(unsigned i=0;i<count;++i) if(seen[i]==node) return false;
        seen[count++]=node; found|=node==actor; node=DecodePacked(Field<uint32_t>(node,2704));
    }
    return found;
}
bool ScenePhase() {
    const int phase=At<int>(0x716884);
    return At<BYTE>(0x9BA8D0)==1 && !At<BYTE>(0x9BA8D1) && (phase==1 || phase==2) &&
        !At<uintptr_t>(0x9BA928) && !At<BYTE>(0x9006B0) && !At<uintptr_t>(0xAC0F48) &&
        !At<BYTE>(0xABAC58) && !At<BYTE>(0xABAC59) && !At<uintptr_t>(0x2AE9FA8) &&
        !(At<unsigned>(0x2A10504)&2) && Range(At<uintptr_t>(0x2A25370),8) &&
        Range(At<uintptr_t>(0x716868),72);
}
bool ActorReady(const TrainerContext& c,bool requireScene) {
    if(c.base!=g_base || (requireScene && (!c.sceneReady || !ScenePhase())) || !c.player || !c.status ||
        At<uintptr_t>(0x2A105D0)!=c.player || !Range(c.player,3608) || !Range(c.status,632) ||
        Field<uintptr_t>(c.player,1472)!=c.status || DecodePacked(Field<uint32_t>(c.status,616))!=c.player ||
        Field<int>(c.status,608)!=1 || DecodePacked(Field<uint32_t>(c.player,0))!=g_base+0x750300 ||
        (Field<unsigned>(c.player,1736)&0x1000080)!=0x1000080 || (Field<unsigned>(c.player,288)&0x10080100) ||
        (Field<unsigned>(c.player,2488)&4) || Field<uintptr_t>(c.player,360)!=c.player ||
        Field<int>(c.status,0)<=0 || Field<int>(c.status,0)>Field<int>(c.status,4) || Field<int>(c.status,4)>255 ||
        Field<int>(c.player,3552)<0 || Field<int>(c.player,3552)>6 ||
        At<BYTE>(0x9ACDD4)!=Field<int>(c.player,3552)) return false;
    return Listed(c.player);
}
struct View {
    uintptr_t model=0,modelResource=0,modelVtable=0,motion=0,resource=0;
    unsigned format=0; float speed=0,frame=0,duration=0,blend=0,blendTarget=0;
    int logical=-1,resolved=-1;
};
bool ReadView(const TrainerContext& c,View& v) {
    if(!ActorReady(c,true)) return false;
    v.model=Field<uintptr_t>(c.player,1968);
    if(!Range(v.model,856)) return false;
    v.modelResource=Field<uintptr_t>(v.model,32);
    if(!Range(v.modelResource,16)) return false;
    v.modelVtable=Field<uintptr_t>(v.modelResource,0);
    if(!Range(v.modelVtable,88)) return false;
    v.motion=Field<uintptr_t>(c.player,368);
    if(!Range(v.motion,48)) return false;
    const uintptr_t type=Field<uintptr_t>(v.motion,0);
    if(type==g_base+0x5B4958) v.format=0;
    else if(type==g_base+0x5B4A38) v.format=1;
    else return false;
    v.resource=Field<uintptr_t>(v.motion,8);
    if(!Range(v.resource,v.format?96:160) || Field<unsigned>(v.resource,0)!=v.format) return false;
    const unsigned duration=Field<unsigned>(v.resource,v.format?32:20);
    const unsigned joints=v.format?Field<unsigned>(v.resource,16):Field<uint16_t>(v.resource,16);
    if(!duration || duration>1000000 || !joints || joints>4096) return false;
    if(!v.format) {
        const unsigned total=Field<uint16_t>(v.resource,18);
        if(total<joints || total>4096) return false;
    } else if(!Field<unsigned>(v.resource,36) || Field<unsigned>(v.resource,36)>1000000) return false;
    const float rate=Field<float>(v.resource,v.format?88:152);
    const float start=Field<float>(v.resource,v.format?80:144),end=Field<float>(v.resource,v.format?92:156);
    if(!Finite(rate,0.001,1000000) || !Finite(start,-1000000,1000000) || !Finite(end,-1000000,1000000) ||
        !Finite((static_cast<double>(end)-start)*60/rate,-1000000,1000000)) return false;
    v.speed=Field<float>(c.player,680); v.frame=Field<float>(c.player,412); v.duration=Field<float>(c.player,408);
    v.blend=Field<float>(c.player,416); v.blendTarget=Field<float>(c.player,420);
    v.logical=Field<int>(c.player,384); v.resolved=Field<int>(c.player,388);
    return Finite(v.speed,-1000,1000) && Finite(v.frame,-1000000,1000000) &&
        v.duration==static_cast<float>(duration) && Finite(v.blend,0,1000000) &&
        Finite(v.blendTarget,-1000000,1000000) && v.logical>=-1 && v.logical<=65535 &&
        v.resolved>=-1 && v.resolved<=65535;
}
enum State : unsigned { Off=0,Active=1,Disabled=2,ScriptChanged=3,ValueChanged=4,IdentityChanged=5,HostExpired=6,HookChanged=7,ResourceInvalid=8,HookUnavailable=9 };
struct Lease {
    bool enabled=false; uintptr_t actor=0,status=0,heap=0,fieldScheduler=0,actorScheduler=0,model=0,modelResource=0,modelVtable=0;
    int form=0; uint32_t baseline=0,written=0; BYTE room[10]{};
} lease{};
float desired=1;
State state=Off;
void* volatile observedActor=nullptr;
volatile LONG scriptChanged=0;
bool hooked=false;
SRWLOCK writerLock=SRWLOCK_INIT;
void __fastcall WriterHook(uint32_t* args);
bool TableReady() {
    return g_base && At<uintptr_t>(kBankRoot)==g_base+kBank && At<unsigned>(kSlot+8)==2 &&
        At<unsigned>(kSlot+12)==0 && Range(g_base+kWriter,sizeof(kWriterBytes)) &&
        !memcmp(reinterpret_cast<const void*>(g_base+kWriter),kWriterBytes,sizeof(kWriterBytes));
}
bool OwnSlot() { return At<uintptr_t>(kSlot)==reinterpret_cast<uintptr_t>(&WriterHook); }
bool SwapSlot(uintptr_t expected,uintptr_t replacement) {
    auto slot=reinterpret_cast<void* volatile*>(g_base+kSlot);
    DWORD oldProtection=0,unused=0;
    if(!VirtualProtect(reinterpret_cast<void*>(g_base+kSlot),sizeof(void*),PAGE_READWRITE,&oldProtection)) return false;
    const bool changed=InterlockedCompareExchangePointer(slot,reinterpret_cast<void*>(replacement),
        reinterpret_cast<void*>(expected))==reinterpret_cast<void*>(expected);
    const bool restored=VirtualProtect(reinterpret_cast<void*>(g_base+kSlot),sizeof(void*),oldProtection,&unused)!=FALSE;
    if(!restored && changed) {
        InterlockedCompareExchangePointer(slot,reinterpret_cast<void*>(expected),reinterpret_cast<void*>(replacement));
        VirtualProtect(reinterpret_cast<void*>(g_base+kSlot),sizeof(void*),oldProtection,&unused);
    }
    return changed && restored;
}
bool PinModule() {
#ifdef KH2_MOTION_TESTS
    return testPin;
#else
    HMODULE module=nullptr;
    return GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,
        reinterpret_cast<LPCWSTR>(&WriterHook),&module)!=FALSE;
#endif
}
bool Install() {
    if(!TableReady() || !PinModule()) return false;
    if(OwnSlot()) return originalWriter!=nullptr;
    if(At<uintptr_t>(kSlot)!=g_base+kWriter) return false;
    // Immutable after the first install: an already-dispatched wrapper may run
    // after slot removal. The bridge stays pinned for the process lifetime.
    if(!originalWriter) {
#ifdef KH2_MOTION_TESTS
        originalWriter=testWriter;
#else
        originalWriter=reinterpret_cast<WriterFn>(g_base+kWriter);
#endif
    }
    if(!originalWriter) return false;
    const bool ok=SwapSlot(g_base+kWriter,reinterpret_cast<uintptr_t>(&WriterHook));
    hooked=OwnSlot(); return ok;
}
void RemoveHook() {
    if(OwnSlot()) SwapSlot(reinterpret_cast<uintptr_t>(&WriterHook),g_base+kWriter);
    hooked=OwnSlot();
}
void ObserveScript(uint32_t* args) {
    const uintptr_t watched=reinterpret_cast<uintptr_t>(InterlockedCompareExchangePointer(&observedActor,nullptr,nullptr));
    if(!watched || !Range(reinterpret_cast<uintptr_t>(args),12)) return;
    const uintptr_t handle=DecodePacked(args[0]);
    if(!Range(handle,8)) return;
    const uintptr_t actor=DecodePacked(Field<uint32_t>(handle,4));
    // This only revokes trainer ownership; no Actor is dereferenced or written.
    // Observe even during teardown/host loss, and even if the float is unchanged.
    if(actor==watched) InterlockedExchange(&scriptChanged,1);
}
void __fastcall WriterHook(uint32_t* args) {
    AcquireSRWLockExclusive(&writerLock);
    __try {
        __try { ObserveScript(args); }
        __except(EXCEPTION_EXECUTE_HANDLER) { InterlockedExchange(&scriptChanged,1); }
        // Never swallow engine exceptions or alter the synchronous operand ABI.
        // Native42FCE0 only decodes pointers and stores; it cannot reenter this slot.
        originalWriter(args);
    } __finally { ReleaseSRWLockExclusive(&writerLock); }
}
bool SameScene() {
    return At<uintptr_t>(0x9BA920)==lease.heap && At<uintptr_t>(0x716868)==lease.fieldScheduler &&
        At<uintptr_t>(0x2A17180)==lease.actorScheduler &&
        !memcmp(reinterpret_cast<const void*>(g_base+0x717008),lease.room,10);
}
bool CurrentOwner() {
    // Never follow a retained Actor pointer. Resolve the current player first.
    if(!ScenePhase() || !SameScene() || At<uintptr_t>(0x2A105D0)!=lease.actor) return false;
    const TrainerContext c{g_base,At<uintptr_t>(0x2A105D0),lease.status,false};
    return ActorReady(c,false) && Field<int>(c.player,3552)==lease.form;
}
void Stop(State reason,bool restore) {
    AcquireSRWLockExclusive(&writerLock);
    __try {
        if(lease.enabled && restore && TableReady() && OwnSlot() &&
            !InterlockedCompareExchange(&scriptChanged,0,0) && CurrentOwner() &&
            Writable(reinterpret_cast<void*>(lease.actor+680),4) && Field<uint32_t>(lease.actor,680)==lease.written)
            Field<uint32_t>(lease.actor,680)=lease.baseline;
        InterlockedExchangePointer(&observedActor,nullptr);
        lease={}; state=reason;
    } __finally { ReleaseSRWLockExclusive(&writerLock); }
    RemoveHook();
}
void Maintain(const TrainerContext& c) {
    if(!lease.enabled) { if(hooked) RemoveHook(); return; }
    if(InterlockedCompareExchange(&scriptChanged,0,0)) { Stop(ScriptChanged,false); return; }
    if(!HostFresh()) { Stop(HostExpired,c.sceneReady && c.base==g_base); return; }
    if(!CurrentOwner() || !c.sceneReady || !ScenePhase()) { Stop(IdentityChanged,false); return; }
    if(!TableReady() || !OwnSlot()) { Stop(HookChanged,false); return; }
    if(Field<uint32_t>(lease.actor,680)!=lease.written) { Stop(ValueChanged,false); return; }
    View view{};
    if(!ReadView(c,view)) { Stop(ResourceInvalid,true); return; }
    if(view.model!=lease.model || view.modelResource!=lease.modelResource || view.modelVtable!=lease.modelVtable) { Stop(IdentityChanged,true); return; }
}
bool Start(const TrainerContext& c) {
    View view{};
    if(!HostFresh() || !ReadView(c,view) || Field<uint32_t>(c.player,1696) ||
        !Finite(view.speed,0,16) || !Writable(reinterpret_cast<void*>(c.player+680),4) ||
        !Range(At<uintptr_t>(0x9BA920),8) || !Range(At<uintptr_t>(0x716868),72) ||
        !Range(At<uintptr_t>(0x2A17180),72)) return false;
    if(!Install()) { state=HookUnavailable; return false; }
    bool applied=false;
    AcquireSRWLockExclusive(&writerLock);
    __try {
        // A foreign writer can have run between the initial validation and lock.
        // Capture its latest value as baseline; do not restore an older snapshot.
        if(HostFresh() && TableReady() && OwnSlot() && ReadView(c,view) && Finite(view.speed,0,16) &&
            Writable(reinterpret_cast<void*>(c.player+680),4)) {
            lease={true,c.player,c.status,At<uintptr_t>(0x9BA920),At<uintptr_t>(0x716868),At<uintptr_t>(0x2A17180),
                view.model,view.modelResource,view.modelVtable,Field<int>(c.player,3552),Field<uint32_t>(c.player,680),Bits(desired),{}};
            memcpy(lease.room,reinterpret_cast<const void*>(g_base+0x717008),10);
            InterlockedExchange(&scriptChanged,0);
            InterlockedExchangePointer(&observedActor,reinterpret_cast<void*>(c.player));
            Field<uint32_t>(c.player,680)=lease.written; state=Active; applied=true;
        }
    } __finally { ReleaseSRWLockExclusive(&writerLock); }
    if(!applied) RemoveHook();
    return applied;
}
bool UpdateRate() {
    bool updated=false;
    AcquireSRWLockExclusive(&writerLock);
    __try {
        if(lease.enabled && HostFresh() && TableReady() && OwnSlot() &&
            !InterlockedCompareExchange(&scriptChanged,0,0) && CurrentOwner() &&
            Field<uint32_t>(lease.actor,680)==lease.written && Writable(reinterpret_cast<void*>(lease.actor+680),4)) {
            lease.written=Bits(desired); Field<uint32_t>(lease.actor,680)=lease.written; updated=true;
        }
    } __finally { ReleaseSRWLockExclusive(&writerLock); }
    return updated;
}
}
bool MotionHandle(const TrainerContext& c,unsigned slot,const double args[8],TrainerResult& result) {
    using namespace motion_features;
    if(slot<160 || slot>170) return false;
    result={1,L"This motion value is read-only."};
    if(slot!=160 && slot!=161) return true;
    if(!OnThread() || !HostFresh()) { result={2,L"Motion controls require the game thread and a connected trainer."}; return true; }
    if(slot==160 && !Finite(args[0],0.1,3)) { result={2,L"Animation speed must be between 0.1 and 3.0."}; return true; }
    if(slot==161 && !IsInteger(args[0],0,1)) { result={2,L"Choose On or Off."}; return true; }
    Maintain(c);
    if(slot==160) {
        desired=static_cast<float>(args[0]);
        if(lease.enabled) {
            if(!UpdateRate()) { Stop(ResourceInvalid,false); result={3,L"The current animation rate is no longer owned or writable."}; return true; }
        }
        result={0,lease.enabled?L"Current Sora animation speed updated.":L"Animation speed stored. Enable the override to apply it to the current Sora Actor."}; return true;
    }
    if(!args[0]) { Stop(Disabled,true); result={0,L"Animation override disabled; the original speed was restored only while still owned."}; return true; }
    if(lease.enabled) { result={0,L"Animation override is already active for this Sora Actor."}; return true; }
    if(!Start(c)) { result={3,L"A living Sora with a supported loaded motion and the original script callback is required."}; return true; }
    result={0,L"Sora animation speed override enabled. Scripts, Actor/Form/scene changes or external changes end ownership."}; return true;
}
void MotionTick(const TrainerContext& c) { if(motion_features::OnThread()) motion_features::Maintain(c); }
void MotionReset(const TrainerContext& c) {
    if(motion_features::OnThread()) motion_features::Stop(motion_features::Disabled,c.sceneReady && c.base==g_base);
}
void MotionCapabilities() { for(unsigned slot=160;slot<=170;++slot) SupportCapability(slot); }
void MotionSnapshot(const TrainerContext& c) {
    using namespace motion_features;
    SnapshotValue(160,desired); SnapshotValue(161,lease.enabled && !InterlockedCompareExchange(&scriptChanged,0,0)?1:0);
    SnapshotValue(170,InterlockedCompareExchange(&scriptChanged,0,0) && lease.enabled?ScriptChanged:state);
    View view{};
    if(!ReadView(c,view)) return;
    SnapshotValue(162,view.speed); SnapshotValue(163,view.frame); SnapshotValue(164,view.duration);
    SnapshotValue(165,view.logical); SnapshotValue(166,view.resolved); SnapshotValue(167,view.blend);
    SnapshotValue(168,view.blendTarget); SnapshotValue(169,view.format);
}
