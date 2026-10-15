#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstdio>
#include <cstdint>

namespace {
DWORD fixtureTick = 100000;
uint64_t queryCalls = 0;
DWORD WINAPI FixtureTick() { return fixtureTick; }
SIZE_T WINAPI CountedQuery(LPCVOID p, PMEMORY_BASIC_INFORMATION m, SIZE_T n) {
    ++queryCalls;
    return ::VirtualQuery(p, m, n);
}
}
#define GetTickCount FixtureTick
#define VirtualQuery CountedQuery
#define KH2DEV_PAYLOAD_TESTS
#define KH2_ACTOR_LIFETIME_TESTS
#include "../../src/KH2Trainer.Bridge/TrainerBridge.cpp"
#undef GetTickCount
#undef VirtualQuery

namespace {
unsigned checks = 0, failures = 0;
SharedState fixtureShared{};
void Check(bool good, const char* message) {
    ++checks;
    if (!good) { ++failures; printf("FAIL: %s\n", message); }
}
bool Valid(unsigned slot) {
    return (fixtureShared.validValues[slot / 64] & (uint64_t(1) << (slot % 64))) != 0;
}
void Frame(DWORD tick) {
    fixtureTick = tick;
    fixtureShared.hostHeartbeat = tick;
    TrainerFrame();
}
void Queue(LONG command) {
    fixtureShared.commandId = command;
    fixtureShared.commandIssuedAt = fixtureTick;
    ZeroMemory(fixtureShared.arguments, sizeof(fixtureShared.arguments));
    InterlockedIncrement(&fixtureShared.requestSequence);
}
void BuildPlayer() {
    const uintptr_t actor = g_base + 0x200000, status = g_base + 0x201000;
    At<BYTE>(kSceneReadyRva) = 1;
    At<uintptr_t>(kItemTableRva) = g_base + 0x202000;
    At<uintptr_t>(kGameSchedulerRva) = g_base + 0x203000;
    At<int>(0x716884) = 1;
    At<uintptr_t>(0x2A105D0) = actor;
    PlayerField<uintptr_t>(actor, 0x5C0) = status;
    PlayerField<uint32_t>(actor, 0x6C8) = 0x80;
    At<uintptr_t>(0x2B0D720 + 8) = actor & ~uintptr_t(0x1ffffff);
    PlayerField<uint32_t>(status, 616) = 0x82000000u | static_cast<uint32_t>(actor & 0x1ffffff);
    PlayerField<int>(status, 608) = 1;
    PlayerField<int>(status, 0) = PlayerField<int>(status, 4) = 100;
    PlayerField<int>(status, 384) = PlayerField<int>(status, 388) = 100;
    PlayerField<BYTE>(status, 431) = 1;
    PlayerField<BYTE>(status, 434) = 5;
}
struct Measurement { LONG publications; uint64_t queries; double microsecondsPerFrame; };
Measurement Measure(unsigned fps, bool everyFrame) {
    g_snapshotSchedule = {};
    const auto queriesBefore = queryCalls;
    const LONG before = fixtureShared.snapshotSequence;
    LARGE_INTEGER frequency{}, start{}, end{};
    QueryPerformanceFrequency(&frequency);
    QueryPerformanceCounter(&start);
    for (unsigned frame = 0; frame < fps * 2; ++frame) {
        // Reproduce the old full-snapshot cadence with the same current code,
        // private fixture and safeguards. This does not measure live game FPS.
        if (everyFrame) g_snapshotSchedule = {};
        Frame(200000 + frame * 1000 / fps);
    }
    QueryPerformanceCounter(&end);
    return {(fixtureShared.snapshotSequence - before) / 2, queryCalls - queriesBefore,
        double(end.QuadPart - start.QuadPart) * 1000000 / double(frequency.QuadPart) / (fps * 2)};
}
}

int main() {
    g_base = reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr, kImageSize,
        MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
    if (!g_base) return 2;
    g_shared = &fixtureShared;
    g_gameThread = GetCurrentThreadId();
    // No native game callback or observer installation is permitted by this fixture.
    actor_lifetime::observerStatus = actor_lifetime::Fault;
    for (const auto& code : audio_request_signatures::Writers)
        memcpy(reinterpret_cast<void*>(g_base + code.rva), code.bytes, code.size);
    At<int32_t>(audio_requests::FreeRva) = 17;

    Frame(100000);
    Check(fixtureShared.snapshotSequence == 2 && Valid(482) && fixtureShared.values[482] == 17,
        "first attached update publishes a complete snapshot immediately");
    const auto publicationTick = fixtureShared.values[463];
    constexpr size_t snapshotOffset = offsetof(SharedState, snapshotSequence);
    constexpr size_t snapshotBytes = offsetof(SharedState, reservedTail) - snapshotOffset;
    BYTE savedSnapshot[snapshotBytes];
    memcpy(savedSnapshot, reinterpret_cast<const BYTE*>(&fixtureShared) + snapshotOffset, snapshotBytes);
    At<int32_t>(audio_requests::FreeRva) = 16;
    Frame(100099);
    Check(fixtureShared.snapshotSequence == 2 && fixtureShared.values[482] == 17 &&
        fixtureShared.values[463] == publicationTick,
        "intermediate frame retains coherent values and their original timestamp");
    Check(!memcmp(savedSnapshot, reinterpret_cast<const BYTE*>(&fixtureShared) + snapshotOffset, snapshotBytes),
        "skip leaves the complete sequence, context, masks and value bytes unchanged");
    Frame(100100);
    Check(fixtureShared.snapshotSequence == 4 && fixtureShared.values[482] == 16 &&
        fixtureShared.values[463] == 100100,
        "100 ms boundary samples fresh values and advances publication time");

    Frame(100101); Queue(9999); TrainerFrame();
    Check(fixtureShared.responseSequence == fixtureShared.requestSequence && fixtureShared.resultCode != 0 &&
        fixtureShared.snapshotSequence == 6 && fixtureShared.values[463] == 100101,
        "command dispatch and acknowledgement do not wait for the sampling interval");
    Frame(100102);
    Check(fixtureShared.snapshotSequence == 6,
        "an acknowledged command cannot force another sample or execute again");

    BuildPlayer(); Frame(100103);
    Check(fixtureShared.snapshotSequence == 8 && fixtureShared.sceneReady && MakeTrainerContext().player,
        "scene and player arrival invalidate the old sample immediately");
    const uintptr_t status = g_base + 0x201000;
    g_playerEffects[2] = true;
    PlayerField<BYTE>(status, 433) = 1; Frame(100104);
    Check(PlayerField<BYTE>(status, 433) == 5 && fixtureShared.snapshotSequence == 8,
        "continuous Drive effect still executes on a frame without a snapshot");
    PlayerField<BYTE>(status, 433) = 2; Frame(100105);
    Check(PlayerField<BYTE>(status, 433) == 5 && fixtureShared.snapshotSequence == 8,
        "continuous effect maintenance is not limited to display sampling");

    fixtureTick = 100106; fixtureShared.hostHeartbeat = fixtureTick - 5001; TrainerFrame();
    Check(g_hostExpired && !g_playerEffects[2] && fixtureShared.snapshotSequence == 10,
        "heartbeat expiry resets effects and publishes immediately between samples");
    Frame(100107);
    Check(!g_hostExpired && fixtureShared.snapshotSequence == 12,
        "fresh host recovery is visible without waiting for a sample");
    At<uintptr_t>(0x2A105D0) = 0; Frame(100108);
    Check(fixtureShared.snapshotSequence == 14 && !Valid(0),
        "player removal immediately discards the previous player's readouts");
    At<BYTE>(kSceneReadyRva) = 0; Frame(100109);
    Check(fixtureShared.snapshotSequence == 16 && !fixtureShared.sceneReady,
        "scene teardown is not delayed by diagnostic sampling");

    BuildPlayer(); Frame(100110);
    const LONG beforeStatusChange = fixtureShared.snapshotSequence;
    const uintptr_t replacementStatus = g_base + 0x201800;
    memcpy(reinterpret_cast<void*>(replacementStatus), reinterpret_cast<const void*>(status), 632);
    PlayerField<uintptr_t>(g_base + 0x200000, 0x5C0) = replacementStatus;
    Frame(100111);
    Check(MakeTrainerContext().status == replacementStatus &&
        fixtureShared.snapshotSequence == beforeStatusChange + 2,
        "a status replacement for the same player and scene immediately refreshes the snapshot");

    shortcuts::Reset(); shortcuts::enabled = true;
    shortcuts::Select(0, true, true, true, 100112);
    const unsigned firstEdge = shortcuts::Select(16, true, true, true, 100113);
    ExecuteTrainerShortcut(firstEdge);
    Check(firstEdge == 1079 && world_features::actorFreezeOwned &&
        (At<unsigned>(0x2A11400) & 0x20) && !g_snapshotSchedule.published,
        "first shortcut edge enables freeze and requests a new publication");
    shortcuts::Select(0, true, true, true, 100114);
    const unsigned secondEdge = shortcuts::Select(16, true, true, true, 100115);
    ExecuteTrainerShortcut(secondEdge);
    Check(secondEdge == 1079 && !world_features::actorFreezeOwned &&
        !(At<unsigned>(0x2A11400) & 0x20) && fixtureShared.values[79] == 0,
        "second edge before another sample disables freeze using current state");
    const LONG beforeShortcutSample = fixtureShared.snapshotSequence;
    Frame(100116);
    Check(fixtureShared.snapshotSequence == beforeShortcutSample + 2 &&
        fixtureShared.values[121] == 2 && fixtureShared.values[79] == 0,
        "next update immediately publishes shortcut results within the normal sample interval");
    world_features::pausePhase = world_features::PausePhase::Requested;
    ExecuteTrainerShortcut(1116);
    Check(world_features::pausePhase == world_features::PausePhase::Off && !g_snapshotSchedule.published,
        "field-pause shortcut disables a pending pause despite a stale inactive readout");

    g_snapshotSchedule = {}; Frame(0xfffffff0u);
    const LONG wrappedSequence = fixtureShared.snapshotSequence;
    Frame(0x53u);
    Check(fixtureShared.snapshotSequence == wrappedSequence,
        "99 ms spanning the uptime wrap still suppresses a redundant sample");
    Frame(0x54u);
    Check(fixtureShared.snapshotSequence == wrappedSequence + 2,
        "100 ms spanning the uptime wrap publishes normally");

    BuildPlayer();
    for (unsigned fps : {60u, 120u, 144u}) {
        const auto before = Measure(fps, true);
        const auto after = Measure(fps, false);
        Check(before.publications == static_cast<LONG>(fps * 2) &&
            after.publications >= 18 && after.publications <= 20,
            "full snapshots stay at about ten per second independently of game update rate");
        Check(after.queries < before.queries,
            "actual bridge makes fewer VirtualQuery calls at the reduced sample rate");
        Check(!(fixtureShared.snapshotSequence & 1) && Valid(463),
            "cadence comparison leaves a complete seqlock publication");
        printf("Cadence %u Hz: publications %ld -> %ld, VirtualQuery %llu -> %llu, "
            "private frame us %.3f -> %.3f\n", fps, before.publications, after.publications,
            static_cast<unsigned long long>(before.queries), static_cast<unsigned long long>(after.queries),
            before.microsecondsPerFrame, after.microsecondsPerFrame);
    }
    VirtualFree(reinterpret_cast<void*>(g_base), 0, MEM_RELEASE);
    printf("TrainerPerformanceTests: %u checks, %u failures\n", checks, failures);
    return failures ? 1 : 0;
}
