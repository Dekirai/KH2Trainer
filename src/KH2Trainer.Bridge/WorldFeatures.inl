// Native world/time/camera features for the SHA256-pinned KH2 build.
// Included inside TrainerBridge's anonymous namespace. All entry points run on
// the engine thread. No executable bytes or saved configuration files change.
namespace world_features {
using TaskFn = void (__fastcall *)(void*);
struct Vec4 { float x, y, z, w; };
using SetCameraFn = void (__fastcall *)(void*,const Vec4*,const Vec4*,const Vec4*);
using SetRollFn = void (__fastcall *)(void*,const Vec4*,const Vec4*,float);
using SetFovFn = void (__fastcall *)(void*,float,int);
#ifdef KH2_WORLD_TESTS
SetCameraFn testSetCamera = nullptr;
SetRollFn testSetRoll = nullptr;
SetFovFn testSetFov = nullptr;
TaskFn testCameraFrame = nullptr;
#endif
#pragma pack(push, 1)
struct MapTarget { BYTE world, area, entrance, reserved; short map, battle, event; };
#pragma pack(pop)
static_assert(sizeof(MapTarget) == 10, "Native map target layout");
using RetryFn = intptr_t (__fastcall *)(const MapTarget*,unsigned,int,BYTE,unsigned);
#ifdef KH2_WORLD_TESTS
// Synthetic harness replaces only this callout; production always uses152990.
RetryFn testRetryCall = nullptr;
void (*testCaptureCall)() = nullptr;
#endif

struct OwnedBit { uintptr_t rva; unsigned mask; bool owned, before, desired; };
OwnedBit bits[] = {{0x749804,0x04000000,false,false,false},
                   {0x749804,0x08000000,false,false,false},
                   {0x749838,1,false,false,false}};
float speed = 1.0f, fovDegrees = 70.0f;
bool fovEnabled = false, freeCamera = false;
Vec4 eye{}, target{}, up{};
uintptr_t cameraScene = 0, cameraHeap = 0;
MapTarget cameraRoom{};
int cameraSubmode = -1;
float heldRoll = 0;
bool timeHook = false, cameraHook = false;
bool actorFreezeOwned = false;
uintptr_t actorFreezeScheduler = 0, actorFreezeHeap = 0;
unsigned short actorFreezeRoom = 0xffff;
enum class PausePhase { Off, Requested, Held, Step };
PausePhase pausePhase=PausePhase::Off;
uintptr_t pauseOuter=0, pauseScheduler=0, pauseHeap=0;
MapTarget pauseRoom{};
bool pauseGlobalsOwned=false, pauseTimerAfterStep=false;
// Native157130/157110 implement an opaque DWORD owner mask. All native call
// sites use1/2/4/8/16; this separate bit keeps their ownership intact.
constexpr unsigned pauseTimerMask=0x40000000u;

bool Finite(double v) { return v == v && v <= 1.7976931348623157e308 && v >= -1.7976931348623157e308; }
bool CallbackWritesAllowed() {
    return !InterlockedCompareExchange(&g_disabled,0,0) && g_gameThread == GetCurrentThreadId() &&
           g_shared && g_shared->hostHeartbeat && static_cast<DWORD>(GetTickCount()-g_shared->hostHeartbeat) <= 5000;
}
bool Range(double v, double lo, double hi) { return Finite(v) && v >= lo && v <= hi; }
bool VFinite(const Vec4& v) { return Finite(v.x) && Finite(v.y) && Finite(v.z); }
float Length(const Vec4& v) { return sqrtf(v.x*v.x + v.y*v.y + v.z*v.z); }
Vec4 Sub(const Vec4& a, const Vec4& b) { return {a.x-b.x,a.y-b.y,a.z-b.z,0}; }
Vec4 Cross(const Vec4& a, const Vec4& b) { return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x,0}; }
bool VectorsValid(const Vec4& e, const Vec4& t, const Vec4& u) {
    if (!VFinite(e) || !VFinite(t) || !VFinite(u)) return false;
    const Vec4 d = Sub(t,e);
    return Range(Length(d),0.01,1000000) && Range(Length(u),0.01,1000000) &&
           Range(Length(Cross(d,u)),0.001,1e12);
}
bool StableScene() {
    return At<BYTE>(0x9BA8D0) == 1 && !At<BYTE>(0x9BA8D1) &&
           At<int>(0x716884) == 1 && !At<uintptr_t>(0x9BA928) &&
           !At<BYTE>(0x9006B0) && !At<uintptr_t>(0xAC0F48) &&
           Readable(At<void*>(0x716868),72);
}
bool CameraAvailable() {
    return StableScene() && !At<BYTE>(0xAC183C) && At<int>(0xAC1528)==0 &&
           At<int>(0x718C60+72)==0 && Readable(At<void*>(0x9BA920),1) &&
           Writable(reinterpret_cast<void*>(g_base+0xAC1020),128) &&
           Writable(reinterpret_cast<void*>(g_base+0xAC1840),388) &&
           Range(At<float>(0xAC1840+76),0.0001,100000) &&
           Range(At<float>(0xAC1840+80),0.0001,100000);
}
bool SameCameraScene() {
    return cameraScene == At<uintptr_t>(0x716868) && cameraHeap == At<uintptr_t>(0x9BA920) &&
           cameraSubmode == At<int>(0x718C60+72) &&
           !memcmp(&cameraRoom,&At<MapTarget>(0x717008),sizeof(MapTarget));
}
void CaptureCameraLease() {
    cameraScene=At<uintptr_t>(0x716868); cameraHeap=At<uintptr_t>(0x9BA920);
    cameraRoom=At<MapTarget>(0x717008); cameraSubmode=At<int>(0x718C60+72);
}
void ClearCamera();
bool SameFreezeScene() {
    return actorFreezeScheduler == At<uintptr_t>(0x716868) &&
           actorFreezeHeap == At<uintptr_t>(0x9BA920) && actorFreezeRoom == At<unsigned short>(0x717008);
}
void RestoreActorFreeze() {
    // The native room initializer 39C860 -> 3ABAB0 resets this global word.
    // Never clear a new scene's independently acquired native freeze bit.
    if (actorFreezeOwned && SameFreezeScene() && (At<unsigned>(0x2A11400)&0x20))
        At<unsigned>(0x2A11400)&=~0x20u;
    actorFreezeOwned=false;
    actorFreezeScheduler=0; actorFreezeHeap=0; actorFreezeRoom=0xffff;
}

bool SamePauseScene() {
    return pauseOuter==At<uintptr_t>(0x9BA888) && pauseScheduler==At<uintptr_t>(0x716868) &&
           pauseHeap==At<uintptr_t>(0x9BA920) && !memcmp(&pauseRoom,&At<MapTarget>(0x717008),sizeof(MapTarget));
}
bool NativePauseTakeover() {
    return At<BYTE>(0x9006B0) || At<uintptr_t>(0xAC0F48) || At<BYTE>(0x9BA8D1) ||
           At<BYTE>(0xABAC58) || At<BYTE>(0xABAC59);
}
bool PauseSceneReady(int state) {
    return SamePauseScene() && At<BYTE>(0x9BA8D0)==1 && !NativePauseTakeover() &&
           !At<uintptr_t>(0x9BA928) && At<int>(0x716884)==state && !At<BYTE>(0xAC183C);
}
void ReleaseFieldPause() {
    if (pausePhase==PausePhase::Off) return;
    if (pauseGlobalsOwned) {
        // This mask belongs to the trainer, independent of native menu bits.
        At<unsigned>(0xABB854)&=~pauseTimerMask;
        // Preserve a native menu/event's state2/capture ownership. Do not write
        // fields belonging to a newly loaded scene or a module already closing.
        if (SamePauseScene() && !NativePauseTakeover() && At<int>(0x716884)==2) {
            if (At<BYTE>(0xABADE0)==1) At<BYTE>(0xABADE0)=0;
            At<int>(0x716884)=1;
        }
    }
    pausePhase=PausePhase::Off; pauseGlobalsOwned=false; pauseTimerAfterStep=false;
    pauseOuter=pauseScheduler=pauseHeap=0;
}
bool PauseTasksPresent() {
    const uintptr_t manager=At<uintptr_t>(0x9BA888);
    if (!Readable(reinterpret_cast<void*>(manager),72) || *reinterpret_cast<uintptr_t*>(manager+32)) return false;
    uintptr_t node=*reinterpret_cast<uintptr_t*>(manager+16), previous=0;
    unsigned count=0, drawCount=0, fieldCount=0, timingCount=0;
    int previousPriority=-2147483647;
    while (node) {
        if (++count>2048 || !Readable(reinterpret_cast<void*>(node),152) ||
            *reinterpret_cast<uintptr_t*>(node+88)!=manager || *reinterpret_cast<uintptr_t*>(node+128)!=previous) return false;
        const uintptr_t fn=*reinterpret_cast<uintptr_t*>(node), fiber=*reinterpret_cast<uintptr_t*>(node+112);
        const unsigned group=*reinterpret_cast<unsigned*>(node+96);
        const int priority=*reinterpret_cast<int*>(node+100);
        if (priority<previousPriority) return false;
        previousPriority=priority;
        if (priority==100000 && group==0 && fn==g_base+0x1567A0 && !fiber) ++drawCount;
        if (priority==130000 && group==0x80001 && fn==g_base+0x150310 &&
            *reinterpret_cast<uintptr_t*>(node+24)==g_base+0x716860 && Readable(reinterpret_cast<void*>(fiber),48) &&
            *reinterpret_cast<BYTE*>(fiber+24)==1 && *reinterpret_cast<int*>(fiber+28)==0 &&
            *reinterpret_cast<float*>(fiber+32)==0) ++fieldCount;
        // Callback equality is checked separately by EnsureTimeHook.
        if (priority==800000 && group==0 && !fiber) ++timingCount;
        previous=node; node=*reinterpret_cast<uintptr_t*>(node+120);
    }
    return previous==*reinterpret_cast<uintptr_t*>(manager+24) && drawCount==1 && fieldCount==1 && timingCount==1;
}
void PauseBeforeTiming() {
    if (pausePhase==PausePhase::Off) return;
    if (g_gameThread!=GetCurrentThreadId()) return;
    if (!CallbackWritesAllowed()) { ReleaseFieldPause(); return; }
    if (pausePhase==PausePhase::Held) {
        if (!PauseSceneReady(2) || At<BYTE>(0xABADE0)!=1 || !(At<unsigned>(0xABB854)&pauseTimerMask)) ReleaseFieldPause();
        return;
    }
    if (!PauseSceneReady(1) || At<BYTE>(0xABADE0) || At<unsigned>(0xABB854)) { ReleaseFieldPause(); return; }
    const bool wasStep=pausePhase==PausePhase::Step;
    // Native153430 allocates only when its recreate flag is set. Otherwise it
    // unconditionally passes the existing pointer into the renderer.
    if (!At<BYTE>(0x9BAA50) && !Readable(At<void*>(0x9BAA08),24)) { ReleaseFieldPause(); return; }
    // Same renderer phase as native menu capture1515E0: after field rendering,
    // before1548E0 finalizes/presents. Never capture from the post-Update IPC call.
#ifdef KH2_WORLD_TESTS
    testCaptureCall();
#else
    reinterpret_cast<void (__fastcall *)()>(g_base+0x153430)();
#endif
    if (!Readable(At<void*>(0x9BAA08),24)) { ReleaseFieldPause(); return; }
    At<BYTE>(0xABADE0)=1; At<int>(0x716884)=2;
    pauseGlobalsOwned=true; pausePhase=PausePhase::Held;
    pauseTimerAfterStep=wasStep;
    if (!wasStep) At<unsigned>(0xABB854)|=pauseTimerMask;
}
void PauseAfterTiming() {
    if (g_gameThread!=GetCurrentThreadId()) return;
    // A requested step includes this one native timing update. Resume freezing
    // the mission clock afterwards; integer fiber waits advance once naturally.
    if (pauseTimerAfterStep) {
        pauseTimerAfterStep=false;
        if (pausePhase==PausePhase::Held && CallbackWritesAllowed() && PauseSceneReady(2) && At<BYTE>(0xABADE0)==1)
            At<unsigned>(0xABB854)|=pauseTimerMask;
        else ReleaseFieldPause();
    }
}

// Scan a fresh list, validate the entire chain before replacing any callback,
// and keep no task address after returning. Scene teardown may free every node.
unsigned SetTaskHook(uintptr_t manager, uintptr_t original, TaskFn replacement, bool install, bool timing) {
    if (!Readable(reinterpret_cast<void*>(manager),72) || *reinterpret_cast<uintptr_t*>(manager+32)) return 0;
    uintptr_t nodes[2048]{};
    unsigned count = 0, matches = 0;
    uintptr_t node = *reinterpret_cast<uintptr_t*>(manager+16), previous = 0;
    while (node) {
        if (count == _countof(nodes) || !Readable(reinterpret_cast<void*>(node),152) ||
            *reinterpret_cast<uintptr_t*>(node+88) != manager ||
            *reinterpret_cast<uintptr_t*>(node+128) != previous) return 0;
        nodes[count++] = node;
        previous = node;
        node = *reinterpret_cast<uintptr_t*>(node+120);
    }
    if (previous != *reinterpret_cast<uintptr_t*>(manager+24)) return 0;
    for (unsigned i=0; i<count; ++i) {
        node = nodes[i];
        const uintptr_t fn = *reinterpret_cast<uintptr_t*>(node);
        const unsigned group = *reinterpret_cast<unsigned*>(node+96);
        const int priority = *reinterpret_cast<int*>(node+100);
        if (*reinterpret_cast<uintptr_t*>(node+112) ||
            (timing ? (group != 0 || priority != 800000) :
                       ((group != 3 && group != 5) || (priority != 30000 && priority != 90030)))) continue;
        const uintptr_t wrapper = reinterpret_cast<uintptr_t>(replacement);
        if (install && fn == wrapper) { ++matches; continue; }
        const uintptr_t expected = install ? original : wrapper;
        if (fn != expected || !Writable(reinterpret_cast<void*>(node),sizeof(uintptr_t))) continue;
        if (InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(node),
                reinterpret_cast<void*>(install ? wrapper : original),reinterpret_cast<void*>(expected)) ==
                reinterpret_cast<void*>(expected)) ++matches;
    }
    return matches;
}
void __fastcall TimingFrame(void* task) {
    __try { PauseBeforeTiming(); }
    __except(EXCEPTION_EXECUTE_HANDLER) { if (g_gameThread==GetCurrentThreadId()) ReleaseFieldPause(); }
    reinterpret_cast<TaskFn>(g_base+0x1548E0)(task);
    __try {
        PauseAfterTiming();
        if (CallbackWritesAllowed() && speed != 1.0f && StableScene()) {
            const float nativeDelta = At<float>(0x717480);
            if (Range(nativeDelta,0.000001,6)) {
                float scaled = nativeDelta * speed;
                if (scaled > 6) scaled = 6;
                At<float>(0x717480) = scaled;
                At<float>(0x717488) = 1.0f/scaled;
            }
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) { speed = 1.0f; if (g_gameThread==GetCurrentThreadId()) ReleaseFieldPause(); }
}
void __fastcall CameraFrame(void* task) {
    __try {
        if (g_gameThread==GetCurrentThreadId() && (freeCamera || fovEnabled) &&
            (!CallbackWritesAllowed() || !CameraAvailable() || !SameCameraScene())) ClearCamera();
        if (CallbackWritesAllowed() && At<int>(0xAC1838) == 0 && CameraAvailable() && SameCameraScene()) {
            if (freeCamera && VectorsValid(eye,target,up) && Range(heldRoll,-3.141592741012574,3.141592741012574)) {
                SetCameraFn setCamera=reinterpret_cast<SetCameraFn>(g_base+0x19D340);
                SetRollFn setRoll=reinterpret_cast<SetRollFn>(g_base+0x19D3D0);
#ifdef KH2_WORLD_TESTS
                setCamera=testSetCamera; setRoll=testSetRoll;
#endif
                setCamera(reinterpret_cast<void*>(g_base+0xAC1020),&eye,&target,&up);
                // 19D340 keeps the supplied Up and existing roll. 19D3D0 writes
                // roll in XMM3, keeping Up intact; the renderer applies it once.
                setRoll(reinterpret_cast<void*>(g_base+0xAC1020),&eye,&target,heldRoll);
            }
            if (fovEnabled) {
                SetFovFn setFov=reinterpret_cast<SetFovFn>(g_base+0x19DDE0);
#ifdef KH2_WORLD_TESTS
                setFov=testSetFov;
#endif
                setFov(reinterpret_cast<void*>(g_base+0xAC1840),fovDegrees*0.017453292519943295f,0);
            }
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) { ClearCamera(); }
    // Exactly one normal call preserves previous-bank copying and renderer setup.
    TaskFn original=reinterpret_cast<TaskFn>(g_base+0x19CBA0);
#ifdef KH2_WORLD_TESTS
    original=testCameraFrame;
#endif
    original(task);
}
bool EnsureTimeHook() {
    timeHook = SetTaskHook(At<uintptr_t>(0x9BA888),g_base+0x1548E0,TimingFrame,true,true) != 0;
    return timeHook;
}
bool EnsureCameraHook() {
    cameraHook = SetTaskHook(At<uintptr_t>(0x716868),g_base+0x19CBA0,CameraFrame,true,false) != 0;
    return cameraHook;
}
void SetBit(unsigned index, bool enabled) {
    OwnedBit& b = bits[index];
    unsigned& value = At<unsigned>(b.rva);
    if (!b.owned) { b.before = (value & b.mask) != 0; b.owned = true; }
    b.desired = enabled;
    value = (value & ~b.mask) | (enabled ? b.mask : 0);
}
void RestoreBits() {
    for (auto& b : bits) {
        if (b.owned) {
            unsigned& value = At<unsigned>(b.rva);
            // Do not replace a different bit value subsequently written by a mod.
            if (((value & b.mask) != 0) == b.desired)
                value = (value & ~b.mask) | (b.before ? b.mask : 0);
            b.owned = false;
        }
    }
}
bool ValidDestination(const MapTarget& m) {
    if (m.world > 18 || m.area > 63) return false;
    const uintptr_t table = At<uintptr_t>(0x2A10558);
    if (!Readable(reinterpret_cast<void*>(table),8) ||
        m.world >= *reinterpret_cast<unsigned*>(table+4) ||
        !Readable(reinterpret_cast<void*>(table+8+4*m.world),4)) return false;
    const unsigned short* row = reinterpret_cast<unsigned short*>(table+8+4*m.world);
    return m.area < row[0] && Readable(reinterpret_cast<void*>(table+row[1]+64*m.area),64);
}
bool NativeCheckpoint(MapTarget& destination, const wchar_t*& reason) {
    constexpr uintptr_t backupRva=0x29FB580, targetRva=0x2A0C540;
    constexpr uint64_t saveHeader=0x0000003A4A32484Bull;
    if (!Readable(reinterpret_cast<void*>(g_base+backupRva),0x10FC0) ||
        !Readable(reinterpret_cast<void*>(g_base+targetRva),sizeof(MapTarget)) ||
        !Readable(reinterpret_cast<void*>(g_base+0x2A0C550),0x1060)) {
        reason=L"The native checkpoint buffers are unavailable."; return false;
    }
    // Live SaveData and checkpoint CRC fields are not recomputed after each
    // mutation. Only export2ED110 finalizes a checksum; do not call it here.
    if (At<uint64_t>(backupRva)!=saveHeader || At<uint64_t>(0x9A98B0)!=saveHeader) {
        reason=L"The live save or native checkpoint header is invalid."; return false;
    }
    destination=At<MapTarget>(targetRva);
    if (!ValidDestination(destination)) {
        reason=L"No native retry checkpoint with a valid destination is available."; return false;
    }
    if (At<BYTE>(backupRva+12)!=destination.world || At<BYTE>(backupRva+13)!=destination.area ||
        At<BYTE>(backupRva+14)!=destination.entrance) {
        reason=L"The native checkpoint location does not match its saved state."; return false;
    }
    // Spawn sets are copied exclusively from the native snapshot. Do not apply
    // the debug editor's0..50 limit: mission checkpoints may use larger values.
    return true;
}
void QueueNativeRetry(const MapTarget& destination) {
    RetryFn call=reinterpret_cast<RetryFn>(g_base+0x152990);
#ifdef KH2_WORLD_TESTS
    call=testRetryCall;
#endif
    // Native menu151000 uses these exact arguments. Restore byte1 makes152A90
    // call3A0580 AFTER tearing down scene actors/resources, then reload normally.
    call(&destination,1,0,1,0);
}
bool CaptureCamera() {
    if (!CameraAvailable() || !EnsureCameraHook()) return false;
    const Vec4 e = At<Vec4>(0xAC1020+72), t = At<Vec4>(0xAC1020+88), u = At<Vec4>(0xAC1020+104);
    const float roll=At<float>(0xAC1020+120);
    if (!VectorsValid(e,t,u) || !Range(roll,-3.141592741012574,3.141592741012574)) return false;
    eye=e; target=t; up=u;
    heldRoll=roll; CaptureCameraLease();
    freeCamera=true;
    return true;
}
float Yaw() { const Vec4 d=Sub(target,eye); return atan2f(d.x,d.z)*57.29577951308232f; }
float Pitch() { const Vec4 d=Sub(target,eye); return asinf(d.y/Length(d))*57.29577951308232f; }
bool Rotate(float yaw, float pitch) {
    const float distance=Length(Sub(target,eye)), yr=yaw*0.017453292519943295f, pr=pitch*0.017453292519943295f;
    const Vec4 next{eye.x+sinf(yr)*cosf(pr)*distance,eye.y+sinf(pr)*distance,eye.z+cosf(yr)*cosf(pr)*distance,1};
    if (!VectorsValid(eye,next,up)) return false;
    target=next;
    return true;
}
void ClearCamera() { freeCamera=false; fovEnabled=false; cameraScene=cameraHeap=0; cameraRoom={}; cameraSubmode=-1; heldRoll=0; }
}

bool WorldCameraExtraIsHeld() {
    using namespace world_features;
    return CallbackWritesAllowed() && freeCamera && CameraAvailable() && SameCameraScene() &&
           VectorsValid(eye,target,up) && Range(heldRoll,-3.141592741012574,3.141592741012574);
}
bool WorldCameraExtraSetRoll(float radians) {
    if (!WorldCameraExtraIsHeld() || !world_features::Range(radians,-3.141592741012574,3.141592741012574)) return false;
    world_features::heldRoll=radians; return true;
}
float WorldCameraExtraRoll() { return world_features::heldRoll; }

void WorldReset(const TrainerContext&) {
    using namespace world_features;
    ReleaseFieldPause(); speed=1.0f; ClearCamera(); RestoreBits(); RestoreActorFreeze();
    SetTaskHook(At<uintptr_t>(0x9BA888),g_base+0x1548E0,TimingFrame,false,true);
    SetTaskHook(At<uintptr_t>(0x716868),g_base+0x19CBA0,CameraFrame,false,false);
    timeHook=false; cameraHook=false;
}
void WorldTick(const TrainerContext& c) {
    using namespace world_features;
    if (pausePhase!=PausePhase::Off && (!c.sceneReady || !SamePauseScene() || NativePauseTakeover() || At<uintptr_t>(0x9BA928))) ReleaseFieldPause();
    if (actorFreezeOwned && (!(At<unsigned>(0x2A11400)&0x20) || !SameFreezeScene() || !c.sceneReady || !StableScene()))
        RestoreActorFreeze();
    if ((freeCamera || fovEnabled) && (!c.sceneReady || !CallbackWritesAllowed() || !CameraAvailable() || !SameCameraScene())) ClearCamera();
    if (speed != 1) EnsureTimeHook();
    if (c.sceneReady && (fovEnabled || freeCamera)) EnsureCameraHook();
}
bool WorldHandle(const TrainerContext& c, unsigned slot, const double a[8], TrainerResult& r) {
    using namespace world_features;
    if ((slot < 48 || slot > 79) && (slot<115 || slot>117)) return false;
    if ((slot >=66 && slot <=68) || slot==70 || slot==71 || slot==72 || (slot>=75 && slot<=77)) return false;
    r={1,L"A stable playable scene is required; close menus and wait for room transitions."};
    if ((freeCamera || fovEnabled) && (!CameraAvailable() || !SameCameraScene())) ClearCamera();
    if (slot==78) { WorldReset(c); r={0,L"World, camera, time and display overrides disabled."}; return true; }
    if (slot==74) { ClearCamera(); r={0,L"Camera control returned to the game."}; return true; }
    if (slot==116) {
        if (!IsInteger(a[0],0,1)) { r={2,L"Field pause must be zero or one."}; return true; }
        if (!a[0]) { ReleaseFieldPause(); r={0,L"Trainer field pause released; native menu/event ownership is preserved."}; return true; }
        if (pausePhase!=PausePhase::Off) { r={0,L"Trainer field pause is already enabled or queued."}; return true; }
        if (!c.sceneReady || !StableScene() || At<BYTE>(0xAC183C) || At<BYTE>(0xABADE0) ||
            At<unsigned>(0xABB854) || NativePauseTakeover() || !PauseTasksPresent() || !EnsureTimeHook()) {
            r={3,L"Field pause requires normal single-camera gameplay, unowned native pause state and the original outer tasks."}; return true;
        }
        pauseOuter=At<uintptr_t>(0x9BA888); pauseScheduler=At<uintptr_t>(0x716868); pauseHeap=At<uintptr_t>(0x9BA920);
        pauseRoom=At<MapTarget>(0x717008); pausePhase=PausePhase::Requested;
        RestoreActorFreeze(); freeCamera=false;
        r={0,L"Field pause queued after the next complete game update. The captured image remains visible; audio and play-time counters continue."}; return true;
    }
    if (slot==117) {
        if (pausePhase!=PausePhase::Held || !PauseSceneReady(2) || At<BYTE>(0xABADE0)!=1 ||
            At<unsigned>(0xABB854)!=pauseTimerMask || !PauseTasksPresent() || !EnsureTimeHook()) {
            r={3,L"A trainer-owned field pause with intact native tasks is required before stepping."}; return true;
        }
        pausePhase=PausePhase::Step; At<BYTE>(0xABADE0)=0; At<unsigned>(0xABB854)&=~pauseTimerMask; At<int>(0x716884)=1;
        r={0,L"One complete field update queued, then pause resumes with a fresh captured image."}; return true;
    }
    if (slot==79 && a[0]==0) {
        RestoreActorFreeze(); r={0,L"Trainer actor/effect freeze released; native freeze ownership is preserved."}; return true;
    }
    if (slot>=57 && slot<=59) {
        if (!IsInteger(a[0],0,1)) { r={2,L"Display setting must be zero or one."}; return true; }
        SetBit(slot-57,a[0]!=0); r={0,L"Display setting applied temporarily."}; return true;
    }
    if (slot==48 && a[0]==1) { speed=1; r={0,L"Normal game timing restored."}; return true; }
    if ((slot==50 || slot==51) && a[0]==0) {
        if (slot==50) fovEnabled=false; else freeCamera=false;
        r={0,L"Camera override disabled."}; return true;
    }
    if (!c.sceneReady || !StableScene()) return true;
    if (slot==115) {
        MapTarget destination{};
        const wchar_t* reason=nullptr;
        if (!NativeCheckpoint(destination,reason)) { r={3,reason}; return true; }
        RestoreActorFreeze(); freeCamera=false;
        QueueNativeRetry(destination);
        r={0,L"Native checkpoint reload queued. Inventory, experience, abilities and other saved progress revert to that checkpoint."};
        return true;
    }
    if (slot==79) {
        if (!IsInteger(a[0],0,1)) { r={2,L"Actor/effect freeze must be zero or one."}; return true; }
        if (actorFreezeOwned && SameFreezeScene() && (At<unsigned>(0x2A11400)&0x20)) {
            r={0,L"Trainer actor/effect freeze is already active."}; return true;
        }
        if (At<unsigned>(0x2A11400)&0x20) {
            r={3,L"The game or another mod already owns the native actor/effect freeze."}; return true;
        }
        actorFreezeScheduler=At<uintptr_t>(0x716868); actorFreezeHeap=At<uintptr_t>(0x9BA920);
        actorFreezeRoom=At<unsigned short>(0x717008); actorFreezeOwned=true;
        // Exactly the flag operation in the native 3ABDB0 setter. A direct bit
        // write permits compare-restoration without invoking code during teardown.
        At<unsigned>(0x2A11400)|=0x20u;
        r={0,L"Actors and most effects frozen. Scripts, mission timers, some effects and hit processing can continue."}; return true;
    }
    if (slot==48) {
        if (!Range(a[0],0.1,3)) r={2,L"Time multiplier must be between 0.1 and 3."};
        else if (!EnsureTimeHook()) r={3,L"Expected native timing task is unavailable or modified."};
        else { speed=static_cast<float>(a[0]); r={0,L"Time multiplier enabled; integer frame waits retain their native behavior."}; }
        return true;
    }
    if (slot==49 || slot==50) {
        if ((slot==49 && !Range(a[0],30,120)) || (slot==50 && !IsInteger(a[0],0,1)))
            r={2,L"Use a horizontal FOV of 30 to 120 degrees or an enable value of zero or one."};
        else if (!CameraAvailable() || !EnsureCameraHook()) r={3,L"Single-camera field rendering is unavailable or modified."};
        else { if (slot==49) fovDegrees=static_cast<float>(a[0]); CaptureCameraLease(); fovEnabled=true; r={0,L"Horizontal FOV override enabled for the current normal follow camera."}; }
        return true;
    }
    if (slot==51) {
        if (!IsInteger(a[0],0,1)) r={2,L"Free camera must be zero or one."};
        else if (!CaptureCamera()) r={3,L"A valid field camera task could not be captured."};
        else r={0,L"Camera held. Position, yaw, pitch and movement controls are now available."};
        return true;
    }
    if ((slot>=52 && slot<=56) || slot==73) {
        if (!freeCamera || !SameCameraScene() || !CameraAvailable()) { r={3,L"Enable free camera in the current room first."}; return true; }
        if (slot<=54) {
            if (!Range(a[0],-1000000,1000000)) { r={2,L"Camera coordinates must be between -1000000 and 1000000."}; return true; }
            float* e=&eye.x; float* t=&target.x; const unsigned axis=slot-52;
            t[axis]+=static_cast<float>(a[0])-e[axis]; e[axis]=static_cast<float>(a[0]);
        } else if (slot<=56) {
            if (!Range(a[0],slot==55?-180:-85,slot==55?180:85) ||
                !Rotate(slot==55?static_cast<float>(a[0]):Yaw(),slot==56?static_cast<float>(a[0]):Pitch())) {
                r={2,L"Use yaw -180..180 or pitch -85..85 degrees; the up vector must remain valid."}; return true;
            }
        } else {
            if (!Range(a[0],-10000,10000) || !Range(a[1],-10000,10000) || !Range(a[2],-10000,10000)) {
                r={2,L"Camera movement must be within -10000..10000 units per axis."}; return true;
            }
            Vec4 forward=Sub(target,eye), right=Cross(forward,up);
            const float fl=Length(forward), rl=Length(right), ul=Length(up);
            if (fl<0.01 || rl<0.001 || ul<0.01) { r={3,L"Camera basis is invalid."}; return true; }
            Vec4 delta{static_cast<float>(a[0])*right.x/rl+static_cast<float>(a[1])*up.x/ul+static_cast<float>(a[2])*forward.x/fl,
                       static_cast<float>(a[0])*right.y/rl+static_cast<float>(a[1])*up.y/ul+static_cast<float>(a[2])*forward.y/fl,
                       static_cast<float>(a[0])*right.z/rl+static_cast<float>(a[1])*up.z/ul+static_cast<float>(a[2])*forward.z/fl,0};
            eye.x+=delta.x; eye.y+=delta.y; eye.z+=delta.z;
            target.x+=delta.x; target.y+=delta.y; target.z+=delta.z;
        }
        r={0,L"Free camera adjusted."}; return true;
    }
    if (slot==60 || slot==61) {
        MapTarget destination{};
        if (slot==60) destination=At<MapTarget>(0x717008);
        else {
            if (!IsInteger(a[0],0,18) || !IsInteger(a[1],0,63) || !IsInteger(a[2],0,255) ||
                !IsInteger(a[3],-1,50) || !IsInteger(a[4],-1,50) || !IsInteger(a[5],-1,50)) {
                r={2,L"Use world 0..18, room 0..63, entrance 0..255, and spawn sets -1..50."}; return true;
            }
            destination={static_cast<BYTE>(a[0]),static_cast<BYTE>(a[1]),static_cast<BYTE>(a[2]),0,
                         static_cast<short>(a[3]),static_cast<short>(a[4]),static_cast<short>(a[5])};
        }
        if (!ValidDestination(destination)) { r={3,L"The requested room is not present in the loaded area table."}; return true; }
        freeCamera=false;
        using Travel = void (__fastcall *)(const MapTarget*);
        reinterpret_cast<Travel>(g_base+0x434CF0)(&destination);
        r={0,L"Room transition queued. Current position and selected party will be used by the next save."};
        return true;
    }
    if (slot>=62 && slot<=65) {
        if (!IsInteger(a[0],0,18) || (a[0]>3 && a[0]!=18)) { r={2,L"Select Sora, Donald, Goofy, world ally, or no entry."}; return true; }
        const BYTE world=At<BYTE>(0x717008);
        if (world>18) { r={3,L"Current world is invalid."}; return true; }
        BYTE* party=reinterpret_cast<BYTE*>(g_base+0x9ACDE4+4*world);
        if (!Writable(party,4)) { r={3,L"Current world party data is unavailable."}; return true; }
        using PartySet = void (__fastcall *)(BYTE*,int,BYTE);
        reinterpret_cast<PartySet>(g_base+0x3E38C0)(party,static_cast<int>(slot-62),static_cast<BYTE>(a[0]));
        r={0,L"World party preset changed. Reload the room to apply; this change can be saved."}; return true;
    }
    if (slot==69) {
        if (At<int>(0xABB878) || At<int>(0xABB3B0+264) || At<uintptr_t>(0x2A0D628) || At<BYTE>(0x9A8738)) {
            r={3,L"The game's native pause conditions are not satisfied."}; return true;
        }
        using PauseContext = void* (__fastcall *)();
        void* context=reinterpret_cast<PauseContext>(g_base+0x3AD540)();
        if (context && !Readable(context,64)) { r={3,L"Native pause context is unavailable."}; return true; }
        if (context) reinterpret_cast<void (__fastcall *)(void*,int)>(g_base+0x2E4C20)(context,0);
        else reinterpret_cast<void (__fastcall *)(int,int)>(g_base+0x2E4950)(0,-1);
        r={0,L"Native pause menu requested."}; return true;
    }
    return false;
}
void WorldSnapshot(const TrainerContext& c) {
    using namespace world_features;
    SnapshotValue(48,speed); SnapshotValue(49,fovDegrees); SnapshotValue(50,fovEnabled?1:0); SnapshotValue(51,freeCamera?1:0);
    SnapshotValue(79,actorFreezeOwned && SameFreezeScene() && (At<unsigned>(0x2A11400)&0x20)?1:0);
    SnapshotValue(116,pausePhase!=PausePhase::Off?1:0);
    for (unsigned i=0;i<_countof(bits);++i) SnapshotValue(57+i,(At<unsigned>(bits[i].rva)&bits[i].mask)?1:0);
    if (!c.sceneReady) return;
    const MapTarget room=At<MapTarget>(0x717008);
    if (room.world<=18) {
        SnapshotValue(66,room.world); SnapshotValue(67,room.area); SnapshotValue(68,room.entrance);
        SnapshotValue(75,room.map); SnapshotValue(76,room.battle); SnapshotValue(77,room.event);
        for (unsigned i=0;i<4;++i) SnapshotValue(62+i,At<BYTE>(0x9ACDE4+4*room.world+i));
    }
    if (Finite(At<float>(0x717424))) SnapshotValue(70,At<float>(0x717424));
    if (Finite(At<float>(0x717480))) SnapshotValue(71,At<float>(0x717480));
    if (CameraAvailable()) {
        const float angle=At<float>(0xAC1840+68)*57.29577951308232f;
        if (Range(angle,0.01,179.99)) SnapshotValue(72,angle);
        const Vec4 e=freeCamera?eye:At<Vec4>(0xAC1020+72);
        if (VFinite(e)) { SnapshotValue(52,e.x); SnapshotValue(53,e.y); SnapshotValue(54,e.z); }
        if (freeCamera && VectorsValid(eye,target,up)) { SnapshotValue(55,Yaw()); SnapshotValue(56,Pitch()); }
    }
}
void WorldCapabilities() {
    for (unsigned slot=48;slot<=79;++slot) SupportCapability(slot);
    SupportCapability(115);
    SupportCapability(116); SupportCapability(117);
}
