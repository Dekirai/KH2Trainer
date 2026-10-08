#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "DevToolsProtocol.h"
#include <strsafe.h>
#include <string.h>
#include <wchar.h>
#include <stdlib.h>
#include <math.h>
#include <initializer_list>
#include <limits.h>
#include <intrin.h>

#if !defined(_M_X64)
#error This payload requires the native Windows x64 ABI.
#endif

namespace {
using namespace kh2dev;
using UpdateFn = intptr_t (__fastcall *)(void*);
using InitFn = void (__fastcall *)();
using PopupFn = intptr_t (__fastcall *)(int, int);
using DebugFrameFn = void (__fastcall *)(void*);

uintptr_t g_base = 0;
uintptr_t g_selectedVtable = 0;
UpdateFn g_original = nullptr;
HANDLE g_mapping = nullptr;
SharedState* g_shared = nullptr;
volatile LONG g_disabled = 0;
volatile LONG g_hookReady = 0;
bool g_initAttempted = false;
bool g_initialized = false;
bool g_desiredVisible = false;
bool g_pendingVisibility = false;
bool g_keyObserved = false;
bool g_previousF10 = false;
bool g_waitingForScene = false;
bool g_debugTaskGuardInstalled = false;
DWORD g_gameThread = 0;
#ifdef KH2DEV_PAYLOAD_TESTS
// Test callbacks are compiled only into the isolated harness, never the DLL.
DebugFrameFn g_testNativeFrame = nullptr;
DebugFrameFn g_testStatusClear = nullptr;
UpdateFn g_testOriginalCallout = nullptr;
#endif

constexpr BYTE kUpdateBytes[] = {
    0x48,0x89,0x5c,0x24,0x08,0x48,0x89,0x6c,0x24,0x10,0x48,0x89,
    0x74,0x24,0x18,0x57,0x48,0x83,0xec,0x40,0x33,0xf6,0x48,0x8b};
constexpr BYTE kInitBytes[] = {
    0x48,0x89,0x5c,0x24,0x08,0x48,0x89,0x6c,0x24,0x10,0x48,0x89,
    0x74,0x24,0x18,0x48,0x89,0x7c,0x24,0x20,0x41,0x54,0x41,0x56};
constexpr BYTE kPopupBytes[] = {
    0x48,0x89,0x74,0x24,0x18,0x57,0x48,0x83,0xec,0x30,0x8b,0xf1,
    0x8b,0xfa,0x48,0x8b,0x0d,0x53,0x6d,0x6d,0x02,0x48,0x85,0xc9};
constexpr BYTE kFrameBytes[] = {
    0x48,0x83,0xec,0x28,0x48,0x8d,0x0d,0x9d,0x30,0x6d,0x02,0xe8,
    0x90,0x32,0x11,0x00,0x8b,0x0d,0x5a,0x2e,0x6d,0x02,0x85,0xc9};
constexpr BYTE kStatusClearBytes[] = {
    0x48,0x8b,0x41,0x70,0x48,0x89,0x41,0x78,0xc6,0x00,0x00,0xc3};
constexpr BYTE kPanaceaUpdateBytes[] = {
    0x48,0x89,0x5c,0x24,0x08,0x48,0x89,0x74,0x24,0x10,0x57,0x48,0x83,0xec,0x20,
    0x48,0x8b,0x1d,0x5a,0x2c,0x05,0x00,0x48,0x8b,0xf1,0x48,0x8b,0x3d,0x58,0x2c,0x05,0x00,
    0x48,0x3b,0xdf,0x74,0x0b,0xff,0x13,0x48,0x83,0xc3,0x08,0x48,0x3b,0xdf,0x75,0xf5,
    0x48,0x8b,0x05,0x91,0x2a,0x05,0x00,0x48,0x8b,0xce,0x48,0x8b,0x5c,0x24,0x30,
    0x48,0x8b,0x74,0x24,0x38,0x48,0x83,0xc4,0x20,0x5f,0x48,0xff,0xe0};

struct UpdateTarget {
    uintptr_t vtable;
    uintptr_t slot;
    uintptr_t original;
    bool panacea;
};
void BestEffortTrainerFailureReset();

void Publish(Status status, Error error, const wchar_t* message) {
    if (!g_shared) return;
    // The worker finishes its status writes before g_hookReady is published.
    // Afterwards the game thread is the only status/message writer.
    InterlockedIncrement(&g_shared->reserved);
    StringCchCopyW(g_shared->message, _countof(g_shared->message), message);
    InterlockedExchange(&g_shared->errorCode, error);
    InterlockedExchange(&g_shared->status, status);
    InterlockedIncrement(&g_shared->reserved);
}

void Fail(Error error, const wchar_t* message) {
    InterlockedExchange(&g_disabled, 1);
    BestEffortTrainerFailureReset();
    Publish(Failed, error, message);
}

bool Readable(const void* address, SIZE_T count) {
    uintptr_t cursor = reinterpret_cast<uintptr_t>(address);
    if (!cursor || count > UINTPTR_MAX - cursor) return false;
    const uintptr_t end = cursor + count;
    while (cursor < end) {
        MEMORY_BASIC_INFORMATION info{};
        if (!VirtualQuery(reinterpret_cast<void*>(cursor), &info, sizeof(info)) ||
            info.State != MEM_COMMIT || (info.Protect & (PAGE_GUARD | PAGE_NOACCESS))) return false;
        const DWORD protection = info.Protect & 0xff;
        if (protection != PAGE_READONLY && protection != PAGE_READWRITE &&
            protection != PAGE_WRITECOPY && protection != PAGE_EXECUTE_READ &&
            protection != PAGE_EXECUTE_READWRITE && protection != PAGE_EXECUTE_WRITECOPY) return false;
        const uintptr_t next = reinterpret_cast<uintptr_t>(info.BaseAddress) + info.RegionSize;
        if (next <= cursor) return false;
        cursor = next < end ? next : end;
    }
    return true;
}

LONG Validate(const void* mappedImage, SIZE_T length) {
    if (!mappedImage || length < sizeof(IMAGE_NT_HEADERS64)) return WrongPeHeader;
    const BYTE* base = static_cast<const BYTE*>(mappedImage);
    const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew < 0 ||
        static_cast<SIZE_T>(dos->e_lfanew) > length - sizeof(IMAGE_NT_HEADERS64)) return WrongPeHeader;
    const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE) return WrongPeHeader;
    if (nt->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64 ||
        nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC) return WrongArchitecture;
    if (nt->FileHeader.TimeDateStamp != kTimestamp ||
        nt->FileHeader.NumberOfSections != 9 ||
        nt->FileHeader.SizeOfOptionalHeader != sizeof(IMAGE_OPTIONAL_HEADER64) ||
        nt->OptionalHeader.SizeOfImage != kImageSize ||
        nt->OptionalHeader.AddressOfEntryPoint != kEntryPoint || length < kImageSize) return WrongBuild;
    if (memcmp(base + kUpdateRva, kUpdateBytes, sizeof(kUpdateBytes)) ||
        memcmp(base + kRootInitRva, kInitBytes, sizeof(kInitBytes)) ||
        memcmp(base + kPopupRva, kPopupBytes, sizeof(kPopupBytes)) ||
        memcmp(base + kRootFrameRva, kFrameBytes, sizeof(kFrameBytes)) ||
        memcmp(base + kStatusClearRva, kStatusClearBytes, sizeof(kStatusClearBytes))) return WrongCode;
    if (*reinterpret_cast<const uintptr_t*>(base + kUpdateSlotRva) !=
        reinterpret_cast<uintptr_t>(base) + kUpdateRva) return ChangedUpdateSlot;
    return Ok;
}

template<class T> T& At(uintptr_t rva) { return *reinterpret_cast<T*>(g_base + rva); }

LONG ValidatePanacea(const BYTE* base, SIZE_T length) {
    if (!base || length < sizeof(IMAGE_NT_HEADERS64)) return WrongModBuild;
    const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew < 0 ||
        static_cast<SIZE_T>(dos->e_lfanew) > length - sizeof(IMAGE_NT_HEADERS64)) return WrongModBuild;
    const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE || nt->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64 ||
        nt->FileHeader.NumberOfSections != 7 || nt->FileHeader.TimeDateStamp != kPanaceaTimestamp ||
        nt->FileHeader.SizeOfOptionalHeader != sizeof(IMAGE_OPTIONAL_HEADER64) ||
        nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC ||
        nt->OptionalHeader.SizeOfImage != kPanaceaImageSize ||
        nt->OptionalHeader.AddressOfEntryPoint != kPanaceaEntryPoint || length < kPanaceaImageSize)
        return WrongModBuild;
    if (memcmp(base + kPanaceaUpdateRva, kPanaceaUpdateBytes, sizeof(kPanaceaUpdateBytes))) return WrongModBuild;
    if (*reinterpret_cast<const uintptr_t*>(base + kPanaceaOriginalUpdateRva) != g_base + kUpdateRva)
        return WrongModChain;
    const uintptr_t modBase = reinterpret_cast<uintptr_t>(base);
    const auto* copied = reinterpret_cast<const uintptr_t*>(base + kPanaceaVtableRva);
    const auto* original = reinterpret_cast<const uintptr_t*>(g_base + kAppVtableRva);
    for (unsigned i = 0; i < 11; ++i) {
        const uintptr_t expected = i == 4 ? modBase + kPanaceaUpdateRva : original[i];
        if (copied[i] != expected) return WrongModChain;
    }
    return Ok;
}

LONG SelectUpdateTarget(void* app, const BYTE* ownerBase, SIZE_T ownerLength, UpdateTarget* target) {
    if (!Readable(app, 5320)) return AppNotReady;
    const uintptr_t vtable = *static_cast<const uintptr_t*>(app);
    if (vtable == g_base + kAppVtableRva) {
        if (At<uintptr_t>(kUpdateSlotRva) != g_base + kUpdateRva) return ChangedUpdateSlot;
        *target = {vtable, g_base + kUpdateSlotRva, g_base + kUpdateRva, false};
        return Ok;
    }
    const uintptr_t modBase = reinterpret_cast<uintptr_t>(ownerBase);
    if (!ownerBase || vtable != modBase + kPanaceaVtableRva) return UnsupportedActiveVtable;
    const LONG validation = ValidatePanacea(ownerBase, ownerLength);
    if (validation != Ok) return validation;
    *target = {vtable, modBase + kPanaceaUpdateSlotRva, modBase + kPanaceaUpdateRva, true};
    return Ok;
}

bool ExpectedPanaceaPath(const wchar_t* exePath, const wchar_t* modulePath) {
    wchar_t expected[32768]{};
    if (FAILED(StringCchCopyW(expected, _countof(expected), exePath))) return false;
    wchar_t* basename = wcsrchr(expected, L'\\');
    if (!basename) return false;
    ++basename;
    if (FAILED(StringCchCopyW(basename, _countof(expected) - (basename - expected), L"dbghelp.dll"))) return false;
    return CompareStringOrdinal(expected, -1, modulePath, -1, TRUE) == CSTR_EQUAL;
}

bool PanaceaPathMatches(HMODULE owner) {
    wchar_t exePath[32768]{};
    wchar_t modulePath[32768]{};
    const DWORD exeLength = GetModuleFileNameW(nullptr, exePath, _countof(exePath));
    const DWORD moduleLength = GetModuleFileNameW(owner, modulePath, _countof(modulePath));
    return exeLength && exeLength < _countof(exePath) && moduleLength &&
           moduleLength < _countof(modulePath) && ExpectedPanaceaPath(exePath, modulePath);
}

LONG ResolveActiveTarget(void* app, UpdateTarget* target, HMODULE* owner) {
    __try {
        if (!Readable(app, 5320)) return AppNotReady;
        const uintptr_t vtable = *static_cast<const uintptr_t*>(app);
        if (vtable == g_base + kAppVtableRva) return SelectUpdateTarget(app, nullptr, 0, target);
        if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                               reinterpret_cast<LPCWSTR>(vtable), owner)) return UnsupportedActiveVtable;
        // The launcher's SHA256 check covers exactly this loaded local module.
        if (!PanaceaPathMatches(*owner)) return WrongModPath;
        return SelectUpdateTarget(app, reinterpret_cast<const BYTE*>(*owner), kPanaceaImageSize, target);
    }
    __except (EXCEPTION_EXECUTE_HANDLER) { return InaccessibleMemory; }
}

bool SwapSelectedUpdate(const UpdateTarget& target, void* replacement) {
    return InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(target.slot), replacement,
        reinterpret_cast<void*>(target.original)) == reinterpret_cast<void*>(target.original);
}

bool ActiveAppMatches(void* app, uintptr_t vtable) {
    __try {
        return At<void*>(kAppGlobalRva) == app && Readable(app, sizeof(void*)) &&
               *static_cast<const uintptr_t*>(app) == vtable;
    }
    __except (EXCEPTION_EXECUTE_HANDLER) { return false; }
}

bool SceneDataReady() {
    return At<BYTE>(kSceneReadyRva) &&
           Readable(At<void*>(kItemTableRva), sizeof(void*)) &&
           Readable(At<void*>(kGameSchedulerRva), sizeof(void*));
}

struct TrainerContext { uintptr_t base, player, status; bool sceneReady; };
struct TrainerResult { LONG code; const wchar_t* text; };

bool Writable(const void* address, SIZE_T count) {
    uintptr_t cursor = reinterpret_cast<uintptr_t>(address);
    if (!cursor || count > UINTPTR_MAX - cursor) return false;
    const uintptr_t end = cursor + count;
    while (cursor < end) {
        MEMORY_BASIC_INFORMATION info{};
        if (!VirtualQuery(reinterpret_cast<void*>(cursor), &info, sizeof(info)) ||
            info.State != MEM_COMMIT || (info.Protect & (PAGE_GUARD | PAGE_NOACCESS))) return false;
        const DWORD p = info.Protect & 0xff;
        if (p != PAGE_READWRITE && p != PAGE_WRITECOPY &&
            p != PAGE_EXECUTE_READWRITE && p != PAGE_EXECUTE_WRITECOPY) return false;
        const uintptr_t next = reinterpret_cast<uintptr_t>(info.BaseAddress) + info.RegionSize;
        if (next <= cursor) return false;
        cursor = next < end ? next : end;
    }
    return true;
}

uintptr_t DecodePacked(uint32_t value) {
    if (!value) return 0;
    return At<uintptr_t>(0x2B0D720 + ((value & 0x7fffffffu) >> 25) * sizeof(uintptr_t)) |
           (value & 0x1ffffffu);
}
bool IsInteger(double value, double minimum, double maximum) {
    return isfinite(value) && value >= minimum && value <= maximum && floor(value) == value;
}
void SnapshotValue(unsigned slot, double value) {
    if (slot >= kValueCount || !isfinite(value)) return;
    g_shared->values[slot] = value;
    g_shared->validValues[slot / 64] |= uint64_t(1) << (slot % 64);
}
void SupportCapability(unsigned slot) {
    if (slot < kValueCount) g_shared->supportedCapabilities[slot / 64] |= uint64_t(1) << (slot % 64);
}
TrainerContext MakeTrainerContext() {
    TrainerContext c{g_base, 0, 0, SceneDataReady()};
    if (!c.sceneReady) return c;
    const uintptr_t actor = At<uintptr_t>(0x2A105D0);
    if (!Readable(reinterpret_cast<void*>(actor), 0xDE4)) return c;
    const uintptr_t status = *reinterpret_cast<const uintptr_t*>(actor + 0x5C0);
    if (!Readable(reinterpret_cast<void*>(status), 632) ||
        DecodePacked(*reinterpret_cast<const uint32_t*>(status + 616)) != actor) return c;
    const int character = *reinterpret_cast<const int*>(status + 608);
    if (character < 1 || character > 15 ||
        !(*reinterpret_cast<const uint32_t*>(actor + 0x6C8) & 0x80)) return c;
    c.player = actor;
    c.status = status;
    return c;
}

#include "PlayerRoleSupport.inl"
#include "ActorLifetimeSupport.inl"
#include "ProgressionFeatures.inl"
bool PlayerHealthControlReady(const TrainerContext& c);
#include "PlayerFeatures.inl"
#include "WorldFeatures.inl"
#include "CombatFeatures.inl"
#include "DamageTuningFeatures.inl"
#include "ActorMovementFeatures.inl"
#include "TargetingFeatures.inl"
#include "CollisionFeatures.inl"
#include "LootFeatures.inl"
#include "ShortcutFeatures.inl"
#include "DriveFeatures.inl"
#include "GummiFeatures.inl"
#include "GummiExtraFeatures.inl"
#include "GummiProjectileFeatures.inl"
#include "GummiEditorFeatures.inl"
#include "RenderFeatures.inl"
#include "DisplayFeatures.inl"
#include "RendererDiagnostics.inl"
#include "WindowDisplayFeatures.inl"
#include "RendererAaFeatures.inl"
#include "AudioFeatures.inl"
#include "SpatialAudioFeatures.inl"
#include "MotionFeatures.inl"
#include "RescueFeatures.inl"
#include "MissionFeatures.inl"
#include "MissionEventFeatures.inl"
#include "CameraExtraFeatures.inl"
#include "GameplayStateSupport.inl"
#include "MovementTransactionSupport.inl"
static_assert(offsetof(SharedState,reservedBeforeSnapshot)==movement_tx::RequestOffset,"Typed movement IPC base");
static_assert(movement_tx::ResponseOffset+sizeof(movement_tx::Response)<=offsetof(SharedState,snapshotSequence),"Typed movement IPC extent");
bool PlayerHealthControlReady(const TrainerContext& c) { return gameplay_state::Inspect(c).controllable; }

bool g_hostExpired = false;
bool HostHeartbeatFresh(DWORD now, DWORD heartbeat) {
    // Both processes use the same GetTickCount clock, including 32-bit wrap.
    // A newly observed timestamp may still be old after background suspension.
    return heartbeat != 0 && static_cast<DWORD>(now - heartbeat) <= 5000;
}

void ResetTrainerEffects(const TrainerContext& c) {
    movement_tx::Tick(c,true);
    shortcuts::Reset();
    PlayerReset(c);
    WorldReset(c);
    CameraExtraReset(c);
    ProgressionReset(c);
    CombatReset(c);
    CollisionReset(c);
    DriveReset(c);
    GummiReset(c);
    MotionReset(c);
    RendererDiagnosticsReset(c);
    WindowDisplayReset(c);
    RendererAaReset(c);
    g_desiredVisible = false;
    g_pendingVisibility = true;
}

void BestEffortTrainerFailureReset() {
    shortcuts::Reset();
    // Worker validation failures have no effects to restore. Once hooks are live,
    // only the engine thread may release owned gameplay fields/task callbacks.
    if (!g_base || !g_gameThread || g_gameThread != GetCurrentThreadId()) return;
    const TrainerContext c{g_base, 0, 0, false};
    __try { movement_tx::Tick(c,true); } __except (EXCEPTION_EXECUTE_HANDLER) {}
    __try { PlayerReset(c); } __except (EXCEPTION_EXECUTE_HANDLER) {}
    __try { WorldReset(c); } __except (EXCEPTION_EXECUTE_HANDLER) {}
    __try { CameraExtraReset(c); } __except (EXCEPTION_EXECUTE_HANDLER) {}
    __try { ProgressionReset(c); } __except (EXCEPTION_EXECUTE_HANDLER) {}
    __try { CombatReset(c); } __except (EXCEPTION_EXECUTE_HANDLER) {}
    __try { CollisionReset(c); } __except (EXCEPTION_EXECUTE_HANDLER) {}
    __try { DriveReset(c); } __except (EXCEPTION_EXECUTE_HANDLER) {}
    __try { GummiReset(c); } __except (EXCEPTION_EXECUTE_HANDLER) {}
    __try { MotionReset(c); } __except (EXCEPTION_EXECUTE_HANDLER) {}
    __try { RendererDiagnosticsFailureReset(c); } __except (EXCEPTION_EXECUTE_HANDLER) {}
    __try { WindowDisplayFailureReset(c); } __except (EXCEPTION_EXECUTE_HANDLER) {}
    __try { RendererAaFailureReset(c); } __except (EXCEPTION_EXECUTE_HANDLER) {}
    g_desiredVisible = false;
    g_pendingVisibility = false;
    __try { if (g_initialized) At<LONG>(kVisibleStateRva) = 1; }
    __except (EXCEPTION_EXECUTE_HANDLER) {}
}

void TrainerFrame() {
    TrainerContext c = MakeTrainerContext();
    const DWORD now = GetTickCount();
    const DWORD heartbeat = g_shared->hostHeartbeat;
    const bool hostFresh = HostHeartbeatFresh(now, heartbeat);
    if (!hostFresh && !g_hostExpired) {
        ResetTrainerEffects(c);
    }
    g_hostExpired = !hostFresh;
    // Install on the update thread after a supported player is fully formed.
    // Observation continues through host disconnects so a construction gap can
    // never silently turn a previous actor token into a new actor's identity.
    if(actor_lifetime::Status()==actor_lifetime::Uninstalled && actor_movement::MovementReady(c,true))
        actor_lifetime::Install(c);
    actor_lifetime::ObserveCurrent(c);
    PlayerMaintainCollision();
    movement_tx::Tick(c,g_hostExpired);
    const LONG request = InterlockedCompareExchange(&g_shared->requestSequence, 0, 0);
    if (request != InterlockedCompareExchange(&g_shared->responseSequence, 0, 0)) {
        MemoryBarrier();
        const LONG commandId = g_shared->commandId;
        double args[8];
        memcpy(args, g_shared->arguments, sizeof(args));
        const bool typedMovement=commandId==movement_tx::Command;
        movement_tx::Request movementRequest{};
        if(typedMovement)memcpy(&movementRequest,reinterpret_cast<const BYTE*>(g_shared)+movement_tx::RequestOffset,sizeof(movementRequest));
        TrainerResult result{1, L"Unsupported command."};
        bool finite = true;
        for (double value : args) if (!isfinite(value)) finite = false;
        if(typedMovement) {
            movement_tx::Reason rejected=movement_tx::Reason::None;
            bool emptyArguments=true;for(double value:args)if(value!=0)emptyArguments=false;
            if(!finite || !emptyArguments)rejected=movement_tx::Reason::InvalidRequest;
            else if(g_hostExpired)rejected=movement_tx::Reason::HostExpired;
            else if(!g_shared->commandIssuedAt || static_cast<DWORD>(now-g_shared->commandIssuedAt)>=8000)rejected=movement_tx::Reason::Expired;
            const auto response=movement_tx::Execute(c,movementRequest,static_cast<uint32_t>(request),rejected);
            memcpy(reinterpret_cast<BYTE*>(g_shared)+movement_tx::ResponseOffset,&response,sizeof(response));
            result={response.outcome==movement_tx::Outcome::Rejected?3:0,L"Movement transaction acknowledged. Its typed receipt records the exact outcome."};
        }
        else if (!finite) result = {2, L"Every argument must be a finite number."};
        else if (g_hostExpired) result = {3, L"The trainer heartbeat expired. Reconnect before sending commands."};
        else if (!g_shared->commandIssuedAt || static_cast<DWORD>(now - g_shared->commandIssuedAt) >= 8000)
            result = {4, L"The command expired before the game could execute it. No action was applied."};
        else if (commandId == 1114) {
            ResetTrainerEffects(c);
            result = {0, L"Continuous effects disabled. Completed one-time changes remain applied."};
        } else if (commandId == 1112 || commandId == 1113) {
            InterlockedExchange(&g_shared->command, commandId == 1112 ? Show : Hide);
            result = {0, commandId == 1112 ? L"Developer menu requested; waiting for a playable scene if needed." : L"Developer menu hidden."};
        } else if (commandId >= 1000 && commandId < 1000 + static_cast<LONG>(kValueCount)) {
            const unsigned slot = static_cast<unsigned>(commandId - 1000);
            if (!ShortcutHandle(slot, args, result) && !PlayerHandle(c, slot, args, result) && !WorldHandle(c, slot, args, result) && !CombatHandle(c, slot, args, result) && !DamageTuningHandle(c, slot, args, result) && !ActorMovementHandle(c, slot, args, result) && !TargetingHandle(c, slot, args, result) && !CollisionHandle(c, slot, args, result) && !GummiProjectileHandle(c, slot, args, result) && !LootHandle(c, slot, args, result) && !DriveHandle(c, slot, args, result) && !GummiHandle(c, slot, args, result) && !GummiExtraHandle(c, slot, args, result) && !GummiEditorHandle(c, slot, args, result) && !DisplayHandle(c, slot, args, result) && !WindowDisplayHandle(c, slot, args, result) && !RendererAaHandle(c, slot, args, result) && !AudioHandle(c, slot, args, result) && !MotionHandle(c, slot, args, result) && !RescueHandle(c, slot, args, result) && !MissionHandle(c, slot, args, result) && !MissionEventHandle(c, slot, args, result) && !CameraExtraHandle(c, slot, args, result))
                ProgressionHandle(c, slot, args, result);
        }
        StringCchCopyW(g_shared->resultText, _countof(g_shared->resultText), result.text);
        g_shared->resultCode = result.code;
        MemoryBarrier();
        InterlockedExchange(&g_shared->responseSequence, request);
        // Commands may replace scene/player objects; never reuse the old context.
        c = MakeTrainerContext();
    }
    if (!g_hostExpired) {
        PlayerTick(c);
        WorldTick(c);
        ProgressionTick(c);
        CombatTick(c);
        CollisionTick(c);
        DriveTick(c);
        // A queued switch may start its second native transition in this tick.
        c = MakeTrainerContext();
        GummiTick(c);
        MotionTick(c);
        RendererAaTick(c);
        CameraExtraTick(c);
    }
    c=MakeTrainerContext();
    movement_tx::Tick(c,g_hostExpired);
    InterlockedIncrement(&g_shared->snapshotSequence);
    g_shared->sceneReady = c.sceneReady ? 1 : 0;
    ZeroMemory(g_shared->validValues, sizeof(g_shared->validValues));
    ZeroMemory(g_shared->supportedCapabilities, sizeof(g_shared->supportedCapabilities));
    ZeroMemory(g_shared->values, sizeof(g_shared->values));
    PlayerCapabilities(); WorldCapabilities(); ProgressionCapabilities(); CombatCapabilities();
    DriveCapabilities(); GummiCapabilities(); RenderCapabilities();
    AudioCapabilities(); MotionCapabilities();
    RescueCapabilities();
    MissionCapabilities(); MissionEventCapabilities(); CameraExtraCapabilities();
    DamageTuningCapabilities(); DisplayCapabilities();
    ActorMovementCapabilities(); LootCapabilities(); GummiExtraCapabilities();
    TargetingCapabilities(); CollisionCapabilities(); GummiProjectileCapabilities();
    RendererDiagnosticsCapabilities(); SpatialAudioCapabilities(); GummiEditorCapabilities();
    WindowDisplayCapabilities();
    RendererAaCapabilities();
    GameplayStateCapabilities();
    SupportCapability(112); SupportCapability(113); SupportCapability(114); SupportCapability(118);
    PlayerSnapshot(c); WorldSnapshot(c); ProgressionSnapshot(c); CombatSnapshot(c);
    DriveSnapshot(c); GummiSnapshot(c); RenderSnapshot(c);
    AudioSnapshot(c); MotionSnapshot(c);
    RescueSnapshot(c);
    MissionSnapshot(c); CameraExtraSnapshot(c);
    DamageTuningSnapshot(c); DisplaySnapshot(c);
    ActorMovementSnapshot(c); LootSnapshot(c); GummiExtraSnapshot(c);
    TargetingSnapshot(c); CollisionSnapshot(c); GummiProjectileSnapshot(c);
    RendererDiagnosticsSnapshot(c); SpatialAudioSnapshot(c); GummiEditorSnapshot(c);
    WindowDisplaySnapshot(c);
    RendererAaSnapshot(c);
    GameplayStateSnapshot(c);
    movement_tx::Snapshot(c);
    ShortcutSnapshot();
    // The host must not spend reward time using a snapshot left by a stalled game.
    SupportCapability(463);
    SnapshotValue(463, GetTickCount());
    MemoryBarrier();
    InterlockedIncrement(&g_shared->snapshotSequence);
}

bool DependenciesReady(void* app) {
    if (At<void*>(kAppGlobalRva) != app || !Readable(app, 5320)) return false;
    if (*static_cast<uintptr_t*>(app) != g_selectedVtable) return false;
    const uintptr_t manager = At<uintptr_t>(kTaskManagerRva);
    const uintptr_t renderer = At<uintptr_t>(kRendererRva);
    if (!Readable(reinterpret_cast<void*>(manager), 72) ||
        !Readable(reinterpret_cast<void*>(renderer), sizeof(void*))) return false;
    if (!SceneDataReady()) return false;
    // TASK_MANAGER+32 is its currently executing task. Post-Update must be idle.
    return *reinterpret_cast<const uintptr_t*>(manager + 32) == 0 &&
           *reinterpret_cast<const uintptr_t*>(manager + 16) != 0;
}

bool RootsValid() {
    return Readable(At<void*>(kRootRva), 0xA0) &&
           Readable(At<void*>(kDesktopRva), 0xB8) &&
           Readable(At<void*>(kStatusWidgetRva), 0x88) &&
           *At<uintptr_t*>(kRootRva) == g_base + kRootVtableRva &&
           *At<uintptr_t*>(kDesktopRva) == g_base + kDesktopVtableRva &&
           *At<uintptr_t*>(kStatusWidgetRva) == g_base + kStatusVtableRva;
}

bool Foreground() {
    DWORD pid = 0;
    HWND window = GetForegroundWindow();
    if (window) GetWindowThreadProcessId(window, &pid);
    return pid == GetCurrentProcessId();
}

void ClearDebugStatus() {
    const uintptr_t status = At<uintptr_t>(kStatusWidgetRva);
    if (!Readable(reinterpret_cast<void*>(status), 0x88) ||
        *reinterpret_cast<const uintptr_t*>(status) != g_base + kStatusVtableRva) return;
    const void* buffer = *reinterpret_cast<void* const*>(status + 112);
    if (Readable(buffer, 1)) {
#ifdef KH2DEV_PAYLOAD_TESTS
        g_testStatusClear(reinterpret_cast<void*>(status));
#else
        reinterpret_cast<DebugFrameFn>(g_base + kStatusClearRva)(reinterpret_cast<void*>(status));
#endif
    }
}

void __fastcall GuardedDebugFrame(void* node) {
    if (InterlockedCompareExchange(&g_disabled, 0, 0) ||
        GetCurrentThreadId() != g_gameThread) return;
    // This check runs at priority 700000, after any earlier scene tasks have
    // changed their data. It also suppresses the native hidden reset shortcut.
    if (!SceneDataReady()) {
        At<LONG>(kVisibleStateRva) = 1;
        if (!g_pendingVisibility) g_desiredVisible = false;
        ClearDebugStatus();
        return;
    }
    if (!g_desiredVisible) {
        At<LONG>(kVisibleStateRva) = 1;
        ClearDebugStatus();
        return;
    }
    if (g_pendingVisibility) {
        // A Show requested during loading is committed only by post-Update.
        // Its still-hidden native state must not cancel that pending request.
        ClearDebugStatus();
        return;
    }
    const LONG state = At<LONG>(kVisibleStateRva);
    if (state == 0 || state == 1) {
        // A native "hide debug" action also becomes persistent until Show/F10.
        g_desiredVisible = false;
        ClearDebugStatus();
        return;
    }
    if (state == 2 || state == 3) {
#ifdef KH2DEV_PAYLOAD_TESTS
        g_testNativeFrame(node);
#else
        reinterpret_cast<DebugFrameFn>(g_base + kRootFrameRva)(node);
#endif
    }
    else ClearDebugStatus();
}

bool InstallDebugTaskGuard() {
    const uintptr_t manager = At<uintptr_t>(kTaskManagerRva);
    if (!Readable(reinterpret_cast<void*>(manager), 72) ||
        *reinterpret_cast<const uintptr_t*>(manager + 32)) return false;
    uintptr_t node = *reinterpret_cast<const uintptr_t*>(manager + 16);
    uintptr_t candidate = 0;
    unsigned matches = 0;
    // A bounded full scan rejects corrupt/cyclic lists and ambiguous callbacks.
    for (unsigned count = 0; node && count < 4096; ++count) {
        if ((node & 7) || !Readable(reinterpret_cast<void*>(node), 152)) return false;
        if (*reinterpret_cast<const uintptr_t*>(node) == g_base + kRootFrameRva &&
            *reinterpret_cast<const uintptr_t*>(node + 88) == manager &&
            *reinterpret_cast<const DWORD*>(node + 100) == 700000 &&
            *reinterpret_cast<const uintptr_t*>(node + 112) == 0) {
            candidate = node;
            ++matches;
        }
        node = *reinterpret_cast<const uintptr_t*>(node + 120);
    }
    if (node || matches != 1) return false;
    MEMORY_BASIC_INFORMATION info{};
    if (!VirtualQuery(reinterpret_cast<void*>(candidate), &info, sizeof(info))) return false;
    const DWORD access = info.Protect & 0xff;
    if (access != PAGE_READWRITE && access != PAGE_WRITECOPY &&
        access != PAGE_EXECUTE_READWRITE && access != PAGE_EXECUTE_WRITECOPY) return false;
    void* original = reinterpret_cast<void*>(g_base + kRootFrameRva);
    if (InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(candidate),
            reinterpret_cast<void*>(&GuardedDebugFrame), original) != original) return false;
    g_debugTaskGuardInstalled = true;
    InterlockedOr(&g_shared->flags, DebugTaskGuardInstalled);
    return true;
}

void OnFrame(void* app, intptr_t result) {
    if (InterlockedCompareExchange(&g_disabled, 0, 0)) return;
    InterlockedIncrement(&g_shared->frameCount);
    // Only the successful, non-shutdown MyApp Update frame is eligible.
    if (result != 0) return;
    if (At<void*>(kAppGlobalRva) != app || !Readable(app, sizeof(void*)) ||
        *static_cast<const uintptr_t*>(app) != g_selectedVtable) {
        Fail(ActiveVtableChanged, L"The active App vtable changed. Trainer stopped; restart the game.");
        return;
    }
    if (!g_gameThread) g_gameThread = GetCurrentThreadId();
    if (g_gameThread != GetCurrentThreadId()) {
        Fail(WrongAppInstance, L"Update changed its game thread; activation stopped.");
        return;
    }
    TrainerFrame();
    const bool foreground = Foreground();
    if (foreground) InterlockedOr(&g_shared->flags, GameForeground);
    else InterlockedAnd(&g_shared->flags, ~GameForeground);
    const bool down = (GetAsyncKeyState(VK_F10) & 0x8000) != 0;
    const bool keyEdge = g_keyObserved && down && !g_previousF10 && foreground && !g_hostExpired;
    g_keyObserved = true;
    g_previousF10 = down; // Track outside the foreground too; focus is not a key press.

    unsigned shortcutKeys = 0;
    for (unsigned i = 0; i < 8; ++i)
        if (GetAsyncKeyState(VK_F5 + i) & 0x8000) shortcutKeys |= 1u << i;
    const unsigned shortcut = shortcuts::Select(shortcutKeys,
        (GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0 &&
        !(GetAsyncKeyState(VK_MENU) & 0x8000) && !(GetAsyncKeyState(VK_SHIFT) & 0x8000),
        foreground, !g_hostExpired, GetTickCount());
    if (shortcut) {
        TrainerContext c = MakeTrainerContext();
        TrainerResult shortcutResult{1, L"Unsupported training shortcut."};
        double args[8]{};
        if (shortcut == 1114) {
            ResetTrainerEffects(c);
            shortcutResult = {0, L"Training effects and shortcuts disabled. Completed progression changes remain."};
        } else if (shortcut == 1079 || shortcut == 1116) {
            const unsigned slot = shortcut - 1000;
            const bool wasFrozen = (g_shared->validValues[slot / 64] & (uint64_t(1) << (slot % 64))) && g_shared->values[slot] != 0;
            args[0] = wasFrozen ? 0 : 1;
            WorldHandle(c, slot, args, shortcutResult);
        } else if (shortcut == 1117) {
            WorldHandle(c, 117, args, shortcutResult);
        } else PlayerHandle(c, shortcut - 1000, args, shortcutResult);
        ++shortcuts::eventSequence;
        shortcuts::lastCommand = shortcut;
        shortcuts::lastResult = shortcutResult.code;
        Publish(static_cast<Status>(g_shared->status), static_cast<Error>(g_shared->errorCode), shortcutResult.text);
    }

    LONG command = InterlockedExchange(&g_shared->command, None);
    if (command == None && keyEdge) command = Toggle;
    if (command < None || command > Toggle) {
        const LONG state = g_initialized ? At<LONG>(kVisibleStateRva) : 0;
        Publish(g_initialized ? ((state == 2 || state == 3) ? Visible : ReadyHidden) : HookedWaiting,
                InvalidCommand, L"Unknown developer-menu command ignored.");
        return;
    }
    if (command != None) {
        const LONG state = g_initialized ? At<LONG>(kVisibleStateRva) : 0;
        const bool currentlyVisible = g_pendingVisibility ? g_desiredVisible :
            (g_initialized && (state == 2 || state == 3));
        g_desiredVisible = command == Show || (command == Toggle && !currentlyVisible);
        g_pendingVisibility = true;
    }
    // Hiding must remain possible while a scene is unloading.
    if (g_initialized && g_pendingVisibility && !g_desiredVisible) {
        At<LONG>(kVisibleStateRva) = 1;
        g_pendingVisibility = false;
        Publish(ReadyHidden, Ok, L"Developer menu hidden. Press F10 to show it.");
    }
    if (!DependenciesReady(app)) {
        if (g_pendingVisibility && g_desiredVisible && !g_waitingForScene) {
            Publish(HookedWaiting, Ok,
                    L"Load a save and enter a playable scene; the developer menu is waiting for game data.");
            g_waitingForScene = true;
        }
        return;
    }
    g_waitingForScene = false;

    if (!g_initialized && g_pendingVisibility && g_desiredVisible) {
        const bool anyRoot = At<uintptr_t>(kRootRva) || At<uintptr_t>(kDesktopRva) ||
                             At<uintptr_t>(kStatusWidgetRva);
        if (anyRoot) {
            // A root created by another component is never reinitialized.
            if (!RootsValid()) {
                Fail(PartialDebugRoot, L"An incomplete or invalid debug root already exists; activation stopped.");
                return;
            }
            g_initialized = true;
            InterlockedOr(&g_shared->flags, InitCompleted | UsingExistingRoot);
        } else {
            if (g_initAttempted) {
                Fail(InitDidNotComplete, L"Debug initialization has already been attempted; no retry.");
                return;
            }
            g_initAttempted = true;
            InterlockedOr(&g_shared->flags, InitAttempted);
            // No game function is called from DllMain or the worker thread.
            reinterpret_cast<InitFn>(g_base + kRootInitRva)();
            if (!RootsValid()) {
                Fail(InitDidNotComplete, L"Debug initialization did not produce all three expected widgets.");
                return;
            }
            g_initialized = true;
            InterlockedOr(&g_shared->flags, InitCompleted);
        }
    }

    if (g_initialized) {
        if (!RootsValid()) {
            Fail(PartialDebugRoot, L"Debug root lifetime changed; activation stopped without reinitialization.");
            return;
        }
        if (!g_debugTaskGuardInstalled && !InstallDebugTaskGuard()) {
            At<LONG>(kVisibleStateRva) = 1;
            Fail(DebugTaskGuardFailure,
                 L"Could not guard the unique debug task. Trainer stopped; restart the game.");
            return;
        }
        if (g_pendingVisibility) {
            if (g_desiredVisible) {
                // The native frame task now owns input, layout, rendering and its state machine.
                At<LONG>(kVisibleStateRva) = 2;
                // Calling this with a non-null popup would destroy it.
                if (!At<uintptr_t>(kPopupGlobalRva))
                    reinterpret_cast<PopupFn>(g_base + kPopupRva)(24, 24);
            } else {
                // Native hide waits for button release before entering hidden state 0.
                At<LONG>(kVisibleStateRva) = 1;
            }
            g_pendingVisibility = false;
        }
        const LONG visibleState = At<LONG>(kVisibleStateRva);
        const Status status = (visibleState == 2 || visibleState == 3) ? Visible : ReadyHidden;
        if (g_shared->status != status || g_shared->errorCode != Ok) {
            Publish(status, Ok, status == Visible ?
                L"Developer menu visible. F10 hides it; hold Right Ctrl to use the mouse." :
                L"Developer menu hidden. Press F10 to show it.");
        }
    } else if (g_pendingVisibility && !g_desiredVisible) {
        g_pendingVisibility = false;
        Publish(HookedWaiting, Ok, L"Trainer ready. Show or F10 opens the developer menu.");
    }
}

LONG LogFault(DWORD code) {
    wchar_t message[256]{};
    StringCchPrintfW(message, _countof(message),
                    L"Exception 0x%08lX in activation callback. No retry; normal exception handling continues.", code);
    Fail(GameException, message);
    // Do not continue a frame with partially initialized engine objects.
    return EXCEPTION_CONTINUE_SEARCH;
}

intptr_t __fastcall HookedUpdate(void* app) {
    __try {
        if (InterlockedCompareExchange(&g_hookReady, 0, 0) &&
            !InterlockedCompareExchange(&g_disabled, 0, 0) &&
            g_initialized && g_gameThread == GetCurrentThreadId() &&
            (!At<BYTE>(kSceneReadyRva) || !At<uintptr_t>(kItemTableRva) ||
             !At<uintptr_t>(kGameSchedulerRva))) {
            // Keep the native input state machine in its hide/wait-release state
            // throughout a scene teardown. Opening requires a new Show request.
            At<LONG>(kVisibleStateRva) = 1;
            if (!g_pendingVisibility) g_desiredVisible = false;
            if (g_shared->status == Visible)
                Publish(ReadyHidden, Ok, L"Scene changed: developer menu hidden.");
        }
    }
    __except (LogFault(GetExceptionCode())) { /* Do not mask engine faults. */ }
#ifdef KH2DEV_PAYLOAD_TESTS
    const intptr_t result = g_testOriginalCallout(app);
#else
    const intptr_t result = g_original(app);
#endif
    __try { if (InterlockedCompareExchange(&g_hookReady, 0, 0)) OnFrame(app, result); }
    __except (LogFault(GetExceptionCode())) { /* Filter always continues search. */ }
    return result;
}

bool IsTargetProcess() {
    wchar_t path[32768]{};
    const DWORD pathLength = GetModuleFileNameW(nullptr, path, _countof(path));
    if (!pathLength || pathLength >= _countof(path)) return false;
    const wchar_t* namePart = wcsrchr(path, L'\\');
    namePart = namePart ? namePart + 1 : path;
    return _wcsicmp(namePart, L"KINGDOM HEARTS II FINAL MIX.exe") == 0;
}

DWORD WINAPI Worker(void*) {
    g_base = reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));

    wchar_t name[80]{};
    StringCchPrintfW(name, _countof(name), L"Local\\KH2Trainer_%lu", GetCurrentProcessId());
    g_mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0,
                                   static_cast<DWORD>(kMappingSize), name);
    if (!g_mapping) return MappingFailure;
    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        CloseHandle(g_mapping); g_mapping = nullptr;
        return ExistingMapping; // Never overwrite another payload's command/status block.
    }
    g_shared = static_cast<SharedState*>(MapViewOfFile(g_mapping, FILE_MAP_ALL_ACCESS, 0, 0, kMappingSize));
    if (!g_shared) { CloseHandle(g_mapping); g_mapping = nullptr; return MappingFailure; }
    ZeroMemory(g_shared, kMappingSize);
    g_shared->version = kVersion;
    Publish(Starting, Ok, L"Trainer: checking the game build and update hook.");
    InterlockedExchange(&g_shared->magic, kMagic);

    const LONG validation = TestValidateBuild(reinterpret_cast<void*>(g_base), kImageSize);
    if (validation != Ok) {
        Fail(static_cast<Error>(validation), L"The loaded executable does not match the supported PE, code, or original Update slot.");
        return static_cast<DWORD>(validation);
    }

    // Select the active object's vtable after startup has created its services.
    // Panacea replaces the vptr during AppMain startup, before this point.
    void* app = nullptr;
    for (unsigned attempt = 0; attempt < 300; ++attempt) {
        app = At<void*>(kAppGlobalRva);
        if (Readable(app, 5320) && At<uintptr_t>(kTaskManagerRva) && At<uintptr_t>(kRendererRva)) break;
        app = nullptr;
        Sleep(100);
    }
    if (!app) {
        Fail(AppNotReady, L"The game App was not ready after 30 seconds. Restart the game and connect after startup.");
        return AppNotReady;
    }
    UpdateTarget target{};
    HMODULE targetOwner = nullptr;
    const LONG selected = ResolveActiveTarget(app, &target, &targetOwner);
    if (selected != Ok) {
        Fail(static_cast<Error>(selected),
             L"The active App vtable or mod chain is unsupported. No hook was installed.");
        return static_cast<DWORD>(selected);
    }
    if (target.panacea) {
        HMODULE pinnedMod = nullptr;
        if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
                               reinterpret_cast<LPCWSTR>(target.original), &pinnedMod) || pinnedMod != targetOwner) {
            Fail(PinFailure, L"Could not pin the verified Panacea module for the game lifetime.");
            return PinFailure;
        }
        InterlockedOr(&g_shared->flags, PanaceaChain);
    }

    HMODULE pinned = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
                           reinterpret_cast<LPCWSTR>(&Worker), &pinned)) {
        Fail(PinFailure, L"Could not pin the payload for the lifetime of the game.");
        return PinFailure;
    }
    InterlockedOr(&g_shared->flags, ModulePinned);
    g_selectedVtable = target.vtable;
    g_original = reinterpret_cast<UpdateFn>(target.original);
    if (!ActiveAppMatches(app, target.vtable)) {
        Fail(ActiveVtableChanged, L"The active App vtable changed during validation. No hook was installed.");
        return ActiveVtableChanged;
    }
    auto* slot = reinterpret_cast<void* volatile*>(target.slot);
    DWORD oldProtection = 0;
    if (!VirtualProtect(const_cast<void**>(slot), sizeof(void*), PAGE_READWRITE, &oldProtection)) {
        Fail(ProtectFailure, L"Could not make the MyApp Update vtable slot writable.");
        return ProtectFailure;
    }

    // Frames entering during installation call only the original Update.
    const bool installed = ActiveAppMatches(app, target.vtable) &&
                          SwapSelectedUpdate(target, reinterpret_cast<void*>(&HookedUpdate));
    DWORD unused = 0;
    const BOOL restored = VirtualProtect(const_cast<void**>(slot), sizeof(void*), oldProtection, &unused);
    if (!installed) {
        Fail(ConflictingHook, L"The MyApp Update slot changed concurrently; no hook was installed.");
        return ConflictingHook;
    }
    InterlockedOr(&g_shared->flags, HookInstalled);
    if (!restored) {
        // No unhook: an engine thread may already be inside HookedUpdate.
        Fail(RestoreProtectionFailure, L"Hook is resident, but restoring vtable protection failed; activation disabled.");
        return RestoreProtectionFailure;
    }
    if (!ActiveAppMatches(app, target.vtable)) {
        Fail(ActiveVtableChanged, L"The active App vtable changed after installation. The hook remains inactive; restart the game.");
        return ActiveVtableChanged;
    }
    Publish(HookedWaiting, Ok, target.panacea ?
        L"Trainer ready through the verified Panacea update chain." :
        L"Trainer ready through the original update chain.");
    InterlockedExchange(&g_hookReady, 1);
    // Handle, view and module deliberately remain resident until process exit.
    return Ok;
}
}

extern "C" __declspec(dllexport) LONG WINAPI TestValidateBuild(const void* mappedImage, SIZE_T length) {
    __try { return Validate(mappedImage, length); }
    __except (EXCEPTION_EXECUTE_HANDLER) { return kh2dev::InaccessibleMemory; }
}

#ifndef KH2DEV_PAYLOAD_TESTS
BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        // Keep thread notifications enabled for the statically linked /MT CRT.
        // Test hosts do not start a worker, so LoadLibrary/FreeLibrary is inert.
        // Calling exports with DONT_RESOLVE_DLL_REFERENCES is unsupported.
        if (!IsTargetProcess()) return TRUE;
        HANDLE thread = CreateThread(nullptr, 0, Worker, nullptr, 0, nullptr);
        if (thread) CloseHandle(thread);
        else return FALSE;
    }
    return TRUE;
}
#endif
