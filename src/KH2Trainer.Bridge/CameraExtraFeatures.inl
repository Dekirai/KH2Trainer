// Native camera contract: research archive (see README): camera_deep.json.
// Include after WorldFeatures. All state and native calls belong to the engine thread.
namespace camera_extra {
using TaskFn = void (__fastcall *)(void*);
using RequestFn = void (__fastcall *)();
constexpr uintptr_t Controller=0x718C60, Camera=0xAC1020;
constexpr float Pi=3.14159265358979323846f;
constexpr DWORD RequestTimeout=1500;
constexpr BYTE FollowBytes[]={0x33,0xd2,0x48,0x8d,0x0d,0xf7,0x43,0x5b,0x00,0xe9,0x92,0x18,0x00,0x00};
constexpr BYTE RecenterBytes[]={0x48,0x83,0xec,0x28,0xe8,0x07,0x43,0xd3,0xff,0x48,0x8b,0xc8,0x48,0x83,0xc4,0x28,0xe9,0xcb,0x4e,0xd3,0xff};
constexpr BYTE SnapBytes[]={0x48,0x83,0xec,0x28,0xe8,0x27,0x43,0xd3,0xff,0x48,0x8b,0xc8,0x48,0x83,0xc4,0x28,0xe9,0x6b,0x50,0xd3,0xff};
constexpr BYTE RecenterSetter[]={0xc6,0x41,0x41,0x01,0xc3};
constexpr BYTE SnapSetter[]={0xc6,0x41,0x40,0x01,0xc3};
constexpr BYTE ControllerGetter[]={0x48,0x8d,0x05,0xe9,0x3d,0x5b,0x00,0xc3};
struct Lease {
    uintptr_t scheduler,heap,player,status,actorController;
    BYTE map[10];
};
struct Pending { unsigned action; DWORD started; Lease lease; } pending{};
#ifdef KH2_CAMERA_EXTRA_TESTS
TaskFn testFollow=nullptr;
RequestFn testRecenter=nullptr,testSnap=nullptr;
DWORD testNow=100;
void (*testBeforeSwap)()=nullptr;
#endif
DWORD Now() {
#ifdef KH2_CAMERA_EXTRA_TESTS
    return testNow;
#else
    return GetTickCount();
#endif
}
bool ThreadReady() { return g_base && g_gameThread && GetCurrentThreadId()==g_gameThread; }
bool WritesAllowed() {
    return ThreadReady() && !InterlockedCompareExchange(&g_disabled,0,0) && g_shared &&
        g_shared->hostHeartbeat && static_cast<DWORD>(Now()-g_shared->hostHeartbeat)<=5000;
}
bool GlobalReadable() {
    return Readable(reinterpret_cast<const void*>(g_base+Controller),232) &&
        Readable(reinterpret_cast<const void*>(g_base+0x716868),40) &&
        Readable(reinterpret_cast<const void*>(g_base+0x717008),10) &&
        Readable(reinterpret_cast<const void*>(g_base+0x9BA8D0),2) &&
        Readable(reinterpret_cast<const void*>(g_base+0x9BA920),16) &&
        Readable(reinterpret_cast<const void*>(g_base+0x9006B0),1) &&
        Readable(reinterpret_cast<const void*>(g_base+0xAC0F48),8) &&
        Readable(reinterpret_cast<const void*>(g_base+Camera),128) &&
        Readable(reinterpret_cast<const void*>(g_base+0xAC1528),8) &&
        Readable(reinterpret_cast<const void*>(g_base+0xAC1838),5);
}
template<class T>T Read(uintptr_t object,size_t offset) { return *reinterpret_cast<const T*>(object+offset); }
bool SameLease(const Lease& a,const Lease& b) {
    return a.scheduler==b.scheduler && a.heap==b.heap && a.player==b.player &&
        a.status==b.status && a.actorController==b.actorController && !memcmp(a.map,b.map,10);
}
bool FreshLease(Lease& out) {
    if (!WritesAllowed() || !GlobalReadable() || At<BYTE>(0x9BA8D0)!=1 ||
        At<BYTE>(0x9BA8D1) || At<int>(0x716884)!=1 || At<uintptr_t>(0x9BA928) ||
        At<BYTE>(0x9006B0) || At<uintptr_t>(0xAC0F48) || At<int>(0xAC1528)!=0 ||
        At<int>(0x718CA8)!=0 || At<int>(0xAC1838)!=0 || At<BYTE>(0xAC183C)) return false;
    const TrainerContext c=MakeTrainerContext();
    if (!c.sceneReady || c.base!=g_base || !c.player || !c.status ||
        !Readable(reinterpret_cast<const void*>(c.player),0xDE4) ||
        !Readable(reinterpret_cast<const void*>(c.status),632) ||
        At<uintptr_t>(Controller+80)!=c.player || At<uintptr_t>(0x2A105D0)!=c.player ||
        Read<uintptr_t>(c.player,1472)!=c.status || DecodePacked(Read<uint32_t>(c.status,616))!=c.player ||
        !(Read<unsigned>(c.player,0x6C8)&0x80) || Read<int>(c.status,0)<=0) return false;
    const uintptr_t actorController=DecodePacked(Read<uint32_t>(c.player,0));
    if (!Readable(reinterpret_cast<const void*>(actorController),128) ||
        !Readable(reinterpret_cast<const void*>(Read<uintptr_t>(actorController,0)),128)) return false;
    const uintptr_t scheduler=At<uintptr_t>(0x716868),heap=At<uintptr_t>(0x9BA920);
    if (!Readable(reinterpret_cast<const void*>(scheduler),72) ||
        !Readable(reinterpret_cast<const void*>(heap),8) ||
        !Writable(reinterpret_cast<void*>(g_base+Controller+64),2)) return false;
    out={scheduler,heap,c.player,c.status,actorController,{}};
    memcpy(out.map,reinterpret_cast<const void*>(g_base+0x717008),10);
    return true;
}
bool Signature(uintptr_t rva,const BYTE* bytes,size_t count) {
    return Readable(reinterpret_cast<const void*>(g_base+rva),count) &&
        !memcmp(reinterpret_cast<const void*>(g_base+rva),bytes,count);
}
bool CodeReady() {
    return Signature(0x164860,FollowBytes,sizeof(FollowBytes)) &&
        Signature(0x430B60,RecenterBytes,sizeof(RecenterBytes)) &&
        Signature(0x430B40,SnapBytes,sizeof(SnapBytes)) &&
        Signature(0x165A40,RecenterSetter,sizeof(RecenterSetter)) &&
        Signature(0x165BC0,SnapSetter,sizeof(SnapSetter)) &&
        Signature(0x164E70,ControllerGetter,sizeof(ControllerGetter));
}
void __fastcall FollowFrame(void* task);
// Scan the entire fresh list; reject ambiguity, cycles, torn links and continuations.
// Never cache a task address. The caller may only install/uninstall outside iteration.
uintptr_t FindTask(uintptr_t manager) {
    if (!Readable(reinterpret_cast<const void*>(manager),72) || Read<uintptr_t>(manager,32)) return 0;
    uintptr_t node=Read<uintptr_t>(manager,16),previous=0,candidate=0;
    unsigned count=0,matches=0; int lastPriority=(-2147483647-1);
    while (node) {
        if (++count>2048 || !Readable(reinterpret_cast<const void*>(node),152) ||
            Read<uintptr_t>(node,88)!=manager || Read<uintptr_t>(node,128)!=previous) return 0;
        const int priority=Read<int>(node,100);
        if (priority<lastPriority) return 0;
        lastPriority=priority;
        const uintptr_t fn=Read<uintptr_t>(node,0);
        if (priority==26000 && Read<unsigned>(node,96)==1) {
            if (Read<uintptr_t>(node,112) || (fn!=g_base+0x164860 && fn!=reinterpret_cast<uintptr_t>(FollowFrame))) return 0;
            ++matches; candidate=node;
        }
        previous=node; node=Read<uintptr_t>(node,120);
    }
    return matches==1 && previous==Read<uintptr_t>(manager,24) ? candidate : 0;
}
bool ChangeHook(uintptr_t manager,bool install) {
    if (!ThreadReady() || At<uintptr_t>(0x716868)!=manager) return false;
    const uintptr_t node=FindTask(manager),wrapper=reinterpret_cast<uintptr_t>(FollowFrame);
    if (!node || !Writable(reinterpret_cast<void*>(node),sizeof(uintptr_t))) return false;
    const uintptr_t fn=Read<uintptr_t>(node,0);
    if (fn==(install?wrapper:g_base+0x164860)) return true;
#ifdef KH2_CAMERA_EXTRA_TESTS
    if (testBeforeSwap) testBeforeSwap();
#endif
    const uintptr_t expected=install?g_base+0x164860:wrapper;
    return InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(node),
        reinterpret_cast<void*>(install?wrapper:g_base+0x164860),reinterpret_cast<void*>(expected))==reinterpret_cast<void*>(expected);
}
bool CurrentTask(void* task,const Lease& lease) {
    const uintptr_t node=reinterpret_cast<uintptr_t>(task);
    return Readable(task,152) && Read<uintptr_t>(node,88)==lease.scheduler &&
        Read<uintptr_t>(lease.scheduler,32)==node && Read<unsigned>(node,96)==1 &&
        Read<int>(node,100)==26000 && !Read<uintptr_t>(node,112) &&
        Read<uintptr_t>(node,0)==reinterpret_cast<uintptr_t>(FollowFrame);
}
bool StillPending(Lease& now) {
    return pending.action && static_cast<DWORD>(Now()-pending.started)<=RequestTimeout &&
        FreshLease(now) && SameLease(pending.lease,now) && !WorldCameraExtraIsHeld();
}
unsigned BeforeFollow(void* task) {
    if (!pending.action || !ThreadReady()) return 0;
    Lease fresh{};
    if (!StillPending(fresh) || !CurrentTask(task,fresh) || !CodeReady() ||
        At<BYTE>(Controller+64) || At<BYTE>(Controller+65)) { pending={}; return 0; }
    const unsigned action=pending.action;
    pending={};
    RequestFn request=reinterpret_cast<RequestFn>(g_base+(action==1?0x430B60:0x430B40));
#ifdef KH2_CAMERA_EXTRA_TESTS
    request=action==1?testRecenter:testSnap;
#endif
    request();
    return action;
}
void __fastcall FollowFrame(void* task) {
    __try { BeforeFollow(task); }
    __except(EXCEPTION_EXECUTE_HANDLER) { pending={}; }
    TaskFn original=reinterpret_cast<TaskFn>(g_base+0x164860);
#ifdef KH2_CAMERA_EXTRA_TESTS
    original=testFollow;
#endif
    original(task); // The normal task runs exactly once, including all canceled paths.
    // Native166100/165110 consume the request synchronously. Do not clear a
    // post-call byte: an equal value could be a later native/script request.
}
bool ReadoutReady(const TrainerContext& c) {
    return ThreadReady() && c.base==g_base && GlobalReadable() && At<BYTE>(0x9BA8D0)==1 &&
        !At<uintptr_t>(0x9BA928) && (At<int>(0x716884)==1 || At<int>(0x716884)==2) &&
        At<int>(0xAC1838)==0 && !At<BYTE>(0xAC183C);
}
}
void CameraExtraCapabilities() { for (unsigned s=240;s<=248;++s) SupportCapability(s); }
void CameraExtraTick(const TrainerContext&) {
    if (!camera_extra::ThreadReady() || !camera_extra::pending.action) return;
    camera_extra::Lease fresh{};
    if (!camera_extra::StillPending(fresh)) camera_extra::pending={};
}
void CameraExtraReset(const TrainerContext&) {
    if (!camera_extra::ThreadReady()) return;
    camera_extra::pending={};
    if (camera_extra::GlobalReadable()) camera_extra::ChangeHook(At<uintptr_t>(0x716868),false);
}
void CameraExtraSnapshot(const TrainerContext& c) {
    using namespace camera_extra;
    if (!ReadoutReady(c)) return;
    const float roll=WorldCameraExtraIsHeld()?WorldCameraExtraRoll():At<float>(Camera+120);
    if (isfinite(roll) && roll>=-Pi && roll<=Pi) SnapshotValue(240,roll*(180.0/static_cast<double>(Pi)));
    SnapshotValue(241,At<int>(0xAC1528));
    const int mode=At<int>(0x718CA8);
    if (mode>=0 && mode<=10) SnapshotValue(242,mode);
    SnapshotValue(245,pending.action);
    const TrainerContext current=MakeTrainerContext();
    SnapshotValue(246,current.player && current.status && current.base==g_base && At<uintptr_t>(Controller+80)==current.player?1:0);
    const float nativeDistance=At<float>(Controller+88);
    if (mode==0 && current.player && At<uintptr_t>(Controller+80)==current.player &&
        isfinite(nativeDistance) && nativeDistance>=0 && nativeDistance<=1000000) SnapshotValue(247,nativeDistance);
    double distanceSquared=0; bool valid=true;
    for (unsigned axis=0;axis<3;++axis) {
        const double eye=At<float>(Camera+72+4*axis),target=At<float>(Camera+88+4*axis);
        if (!isfinite(eye) || !isfinite(target) || fabs(eye)>1000000 || fabs(target)>1000000) { valid=false; break; }
        distanceSquared+=(target-eye)*(target-eye);
    }
    if (valid && distanceSquared>=0.0001 && distanceSquared<=1e12) SnapshotValue(248,sqrt(distanceSquared));
}
bool CameraExtraHandle(const TrainerContext& c,unsigned slot,const double* args,TrainerResult& result) {
    using namespace camera_extra;
    if (slot<240 || slot>248) return false;
    if (slot!=240 && slot!=243 && slot!=244) { result={2,L"This camera value is read only."}; return true; }
    if (c.base!=g_base || !WritesAllowed()) { result={3,L"The camera command needs a fresh connection on the game thread."}; return true; }
    if (slot==240) {
        if (!args || !isfinite(args[0]) || args[0]<-180 || args[0]>180) result={2,L"Camera roll must be between -180 and 180 degrees."};
        else if (!WorldCameraExtraIsHeld() || !WorldCameraExtraSetRoll(static_cast<float>(args[0]*(static_cast<double>(Pi)/180.0))))
            result={3,L"Enable free camera in the current normal field camera first."};
        else result={0,L"Held camera roll adjusted."};
        return true;
    }
    Lease fresh{};
    if (!FreshLease(fresh) || WorldCameraExtraIsHeld()) { result={3,L"Return to the normal camera while following the living player in a playable scene."}; return true; }
    if (pending.action || At<BYTE>(Controller+64) || At<BYTE>(Controller+65)) { result={3,L"A native camera request is already pending. Wait for the next field update."}; return true; }
    if (!CodeReady() || !ChangeHook(fresh.scheduler,true)) { result={3,L"The native follow task is missing, modified, busy or ambiguous."}; return true; }
    Lease checked{};
    if (!FreshLease(checked) || !SameLease(fresh,checked) || WorldCameraExtraIsHeld()) { result={3,L"Camera ownership changed before the request could be queued."}; return true; }
    pending={slot==243?1u:2u,Now(),checked};
    result={0,slot==243?L"Recenter queued for the next normal camera update.":L"Camera snap queued for the next normal camera update."};
    return true;
}
