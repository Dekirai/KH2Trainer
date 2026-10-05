#pragma once
#include <windows.h>
#include <stddef.h>
#include <stdint.h>

// Local\\KH2Trainer_<decimal PID>. All integers are little-endian 32-bit.
namespace kh2dev {
constexpr LONG kMagic = 0x4B483254;
constexpr LONG kVersion = 3;
constexpr unsigned kValueCount = 512;
constexpr unsigned kMaskWordCount = kValueCount / 64;
constexpr SIZE_T kMappingSize = 16384;
constexpr DWORD kTimestamp = 0x669E384A;
constexpr DWORD kImageSize = 0x02C2B000;
constexpr DWORD kEntryPoint = 0x005669CE;
constexpr uintptr_t kUpdateRva = 0x0014EB70;
constexpr uintptr_t kUpdateSlotRva = 0x005B11B0;
constexpr uintptr_t kAppVtableRva = 0x005B1190;
constexpr uintptr_t kRootInitRva = 0x0041FCD0;
constexpr uintptr_t kPopupRva = 0x00420BE0;
constexpr uintptr_t kRootFrameRva = 0x0041FB90;
constexpr uintptr_t kStatusClearRva = 0x00533200;
constexpr uintptr_t kAppGlobalRva = 0x0079CF00;
constexpr uintptr_t kTaskManagerRva = 0x009BA888;
constexpr uintptr_t kRendererRva = 0x008AEEF8;
constexpr uintptr_t kRootRva = 0x02AF3028;
constexpr uintptr_t kDesktopRva = 0x02AF7938;
constexpr uintptr_t kStatusWidgetRva = 0x02AF7940;
constexpr uintptr_t kPopupGlobalRva = 0x02AF7948;
constexpr uintptr_t kVisibleStateRva = 0x02AF2A00;
constexpr uintptr_t kItemTableRva = 0x02A25370;
constexpr uintptr_t kGameSchedulerRva = 0x00716868;
constexpr uintptr_t kSceneReadyRva = 0x009BA8D0;
constexpr uintptr_t kRootVtableRva = 0x005D4E20;
constexpr uintptr_t kDesktopVtableRva = 0x00601000;
constexpr uintptr_t kStatusVtableRva = 0x00601030;
constexpr DWORD kPanaceaTimestamp = 0x68ADE463;
constexpr DWORD kPanaceaImageSize = 0x68000;
constexpr DWORD kPanaceaEntryPoint = 0x19A60;
constexpr uintptr_t kPanaceaVtableRva = 0x5FE30;
constexpr uintptr_t kPanaceaUpdateSlotRva = 0x5FE50;
constexpr uintptr_t kPanaceaUpdateRva = 0xD330;
constexpr uintptr_t kPanaceaOriginalUpdateRva = 0x5FDF8;

enum Command : LONG { None = 0, Show = 1, Hide = 2, Toggle = 3 };
enum Status : LONG { Starting = 0, HookedWaiting = 1, ReadyHidden = 2, Visible = 3, Failed = -1 };
enum Error : LONG {
    Ok = 0, WrongArchitecture = 1, WrongPeHeader = 2, WrongBuild = 3,
    WrongCode = 4, ChangedUpdateSlot = 5, InaccessibleMemory = 6,
    MappingFailure = 7, ExistingMapping = 8, PinFailure = 9,
    ProtectFailure = 10, ConflictingHook = 11, PartialDebugRoot = 12,
    InitDidNotComplete = 13, InvalidCommand = 14, GameException = 15,
    RestoreProtectionFailure = 16, WrongAppInstance = 17, DebugTaskGuardFailure = 18,
    AppNotReady = 19, UnsupportedActiveVtable = 20, WrongModPath = 21,
    WrongModBuild = 22, WrongModChain = 23, ActiveVtableChanged = 24
};
enum Flags : LONG {
    HookInstalled = 1, InitAttempted = 2, InitCompleted = 4,
    ModulePinned = 8, GameForeground = 16, UsingExistingRoot = 32,
    DebugTaskGuardInstalled = 64, PanaceaChain = 128
};

struct SharedState {
    volatile LONG magic;       // 0: written last during mapping setup
    volatile LONG version;     // 4
    volatile LONG command;     // 8: host InterlockedExchange, payload consumes
    volatile LONG status;      // 12
    volatile LONG errorCode;   // 16: Error enum; underlying API detail in message
    volatile LONG frameCount;  // 20: hooked Update calls
    volatile LONG flags;       // 24
    volatile LONG reserved;    // 28: message generation; odd while writing
    wchar_t message[256];      // 32: diagnostic, NUL terminated
    volatile LONG requestSequence; // 544
    volatile LONG responseSequence; // 548
    volatile LONG commandId; // 552
    volatile LONG resultCode; // 556
    double arguments[8]; // 560
    volatile DWORD hostHeartbeat; // 624: GetTickCount-compatible host clock
    DWORD commandIssuedAt; // 628: command expires after 8 seconds, even after reconnect
    BYTE reservedRequest[8];
    wchar_t resultText[192]; // 640
    BYTE reservedBeforeSnapshot[1024];
    volatile LONG snapshotSequence; // 2048
    LONG sceneReady; // 2052
    uint64_t validValues[kMaskWordCount]; // 2056
    uint64_t supportedCapabilities[kMaskWordCount]; // 2120
    double values[kValueCount]; // 2184
    BYTE reservedTail[1912];
};
static_assert(sizeof(wchar_t) == 2, "Windows UTF-16 protocol");
static_assert(offsetof(SharedState, message) == 32, "Protocol layout");
static_assert(offsetof(SharedState, requestSequence) == 544, "Request offset");
static_assert(offsetof(SharedState, hostHeartbeat) == 624, "Heartbeat offset");
static_assert(offsetof(SharedState, commandIssuedAt) == 628, "Command timestamp offset");
static_assert(offsetof(SharedState, resultText) == 640, "Result offset");
static_assert(offsetof(SharedState, snapshotSequence) == 2048, "Snapshot offset");
static_assert(offsetof(SharedState, validValues) == 2056, "Valid mask offset");
static_assert(offsetof(SharedState, supportedCapabilities) == 2120, "Supported mask offset");
static_assert(offsetof(SharedState, values) == 2184, "Values offset");
static_assert(sizeof(SharedState) == 8192, "Protocol layout");
}

// Test-only validation entry point. `mappedImage` must be a mapped PE image,
// not raw file bytes; the vtable entry must be relocated to that buffer's base.
// It performs no hook installation, state writes, or game function calls.
extern "C" __declspec(dllexport) LONG WINAPI TestValidateBuild(const void* mappedImage, SIZE_T length);
