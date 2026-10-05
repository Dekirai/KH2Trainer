// Gummi mission state is independent of Sora's field scene. Included inside
// TrainerBridge's namespace after its shared memory/access helpers.
namespace gummi {
constexpr uintptr_t ModuleRva = 0x716C10;
constexpr uintptr_t ModuleVtableRva = 0x5B14B8;
constexpr uintptr_t ModeListRva = 0x8EC5D8;
constexpr uintptr_t ModuleHeapRva = 0x9A8780;
constexpr uintptr_t HeapRva = 0xAE94F0;
constexpr uintptr_t SchedulerRva = 0xAD9478;
constexpr uintptr_t MissionPhaseRva = 0xAD9474;
constexpr uintptr_t PlayerRva = 0xAF0540;
constexpr uintptr_t DescriptorRva = 0x72A860;
constexpr uintptr_t DescriptorVtableRva = 0x5B52B0;
constexpr uintptr_t StateVtableRva = 0x5B5E70;
constexpr uintptr_t HealRva = 0x2265E0;
constexpr uintptr_t AddScoreRva = 0x207A50;
constexpr uintptr_t ScoreRva = 0x72B130;
constexpr uintptr_t ScoreLockRva = 0x72B134;
constexpr uint32_t MaximumScore = 99999999;
constexpr int MaximumPointAddition = 99999990;
constexpr BYTE HealCode[] = {
    0x0f,0x57,0xc0,0x0f,0x2f,0xc1,0x72,0x08,0xf3,0x0f,0x10,0x0d,0x90,0xd4,0x3f,0x00,
    0xf3,0x0f,0x58,0x49,0x08,0x66,0x0f,0x6e,0x41,0x0c,0x0f,0x5b,0xc0,0xc7,0x41,0x50,
    0x01,0x00,0x00,0x00,0xf3,0x0f,0x5d,0xc8,0xf3,0x0f,0x11,0x49,0x08,0xc3};
constexpr BYTE ScoreCode[] = {
    0x80,0x3d,0xdd,0x36,0x52,0x00,0x00,0x75,0x31,0x03,0x0d,0xd1,0x36,0x52,0x00,
    0x89,0x0d,0xcb,0x36,0x52,0x00,0x81,0xf9,0xf6,0xe0,0xf5,0x05,0x76,0x1d,0xb8,
    0xcd,0xcc,0xcc,0xcc,0xf7,0xe1,0xc1,0xea,0x03,0x8d,0x04,0x92,0x03,0xc0,0x2b,0xc8,
    0x81,0xc1,0xf6,0xe0,0xf5,0x05,0x89,0x0d,0xa6,0x36,0x52,0x00,0xc3};
using HealFn = void (__fastcall*)(void*, float);
using AddScoreFn = void (__fastcall*)(int);
#ifdef KH2_GUMMI_TESTS
// The isolated harness supplies mock callouts; production has no callout seam.
HealFn testHeal = nullptr;
AddScoreFn testAddScore = nullptr;
#endif

template<class T> bool Read(uintptr_t address, T& value) {
    if (!Readable(reinterpret_cast<const void*>(address), sizeof(T))) return false;
    value = *reinterpret_cast<const T*>(address);
    return true;
}
template<class T> bool Global(uintptr_t rva, T& value) {
    return g_base && rva <= UINTPTR_MAX - g_base && Read(g_base + rva, value);
}
bool CodeMatches(uintptr_t rva, const BYTE* expected, size_t length) {
    return g_base && rva <= UINTPTR_MAX - g_base &&
        Readable(reinterpret_cast<const void*>(g_base + rva), length) &&
        memcmp(reinterpret_cast<const void*>(g_base + rva), expected, length) == 0;
}
bool HostAndThreadReady() {
    return !g_disabled && g_shared && g_gameThread &&
        GetCurrentThreadId() == g_gameThread && g_shared->hostHeartbeat != 0 &&
        static_cast<DWORD>(GetTickCount() - g_shared->hostHeartbeat) <= 5000;
}
bool ModuleListed() {
    uintptr_t node = 0;
    if (!Global(ModeListRva, node)) return false;
    uintptr_t visited[64]{};
    unsigned count = 0, matches = 0;
    while (node) {
        if (count == 64 || !Readable(reinterpret_cast<const void*>(node), 40)) return false;
        for (unsigned i = 0; i < count; ++i) if (visited[i] == node) return false;
        visited[count++] = node;
        if (node == g_base + ModuleRva) ++matches;
        const uint32_t next = *reinterpret_cast<const uint32_t*>(node + 20);
        node = DecodePacked(next);
    }
    return matches == 1;
}
struct Context {
    uintptr_t player = 0, state = 0, heap = 0, scheduler = 0;
    int moduleState = 0, missionPhase = 0, playerPhase = 0, maxHp = 0;
    float hp = 0;
    uint32_t flags = 0, route = 0, variant = 0;
};
bool BuildContext(Context& result) {
    result = {};
    Context c{};
    uintptr_t moduleVtable = 0, moduleScheduler = 0, moduleHeap = 0;
    if (!Global(ModuleRva, moduleVtable) || moduleVtable != g_base + ModuleVtableRva ||
        !Global(ModuleRva + 8, moduleScheduler) ||
        !Global(ModuleRva + 36, c.moduleState) ||
        (c.moduleState != 1 && c.moduleState != 2) || !ModuleListed() ||
        !Global(HeapRva, c.heap) || !c.heap || !Global(ModuleHeapRva, moduleHeap) || c.heap != moduleHeap ||
        !Readable(reinterpret_cast<const void*>(c.heap), 16) ||
        !Global(SchedulerRva, c.scheduler) || !c.scheduler || c.scheduler != moduleScheduler ||
        !Readable(reinterpret_cast<const void*>(c.scheduler), 72) ||
        !Global(MissionPhaseRva, c.missionPhase) || c.missionPhase < 0 || c.missionPhase > 19 ||
        !Global(PlayerRva, c.player) || !Readable(reinterpret_cast<const void*>(c.player), 0x1410)) return false;
    c.state = c.player + 0x570;
    uintptr_t descriptorVtable = 0;
    if (DecodePacked(*reinterpret_cast<const uint32_t*>(c.player)) != g_base + DescriptorRva ||
        !Global(DescriptorRva, descriptorVtable) || descriptorVtable != g_base + DescriptorVtableRva ||
        *reinterpret_cast<const uintptr_t*>(c.state) != g_base + StateVtableRva ||
        *reinterpret_cast<const uintptr_t*>(c.player + 0x550) != c.state) return false;
    c.playerPhase = *reinterpret_cast<const int*>(c.player + 0x5D8);
    c.hp = *reinterpret_cast<const float*>(c.state + 8);
    c.maxHp = *reinterpret_cast<const int*>(c.state + 12);
    c.flags = *reinterpret_cast<const uint32_t*>(c.player + 0x140C);
    if (c.playerPhase < 0 || c.playerPhase > 5 || !isfinite(c.hp) || c.maxHp <= 0 ||
        c.hp < 0 || c.hp > static_cast<float>(c.maxHp) ||
        !Global(0x9A8788, c.route) || !Global(0x716C04, c.variant)) return false;
    result = c;
    return true;
}
bool ActionReady(const Context& c) {
    return HostAndThreadReady() && c.moduleState == 1 && c.missionPhase == 8 &&
        c.playerPhase == 2 && c.hp > 0 && !(c.flags & 0x40010);
}
bool SameLifetime(const Context& a, const Context& b) {
    return a.player == b.player && a.state == b.state && a.heap == b.heap && a.scheduler == b.scheduler &&
        a.route == b.route && a.variant == b.variant;
}
bool HealthWritable(const Context& c) {
    return Writable(reinterpret_cast<void*>(c.state + 8), sizeof(float)) &&
        Writable(reinterpret_cast<void*>(c.state + 80), sizeof(int));
}
bool ScoreReady(uint32_t& score) {
    BYTE locked = 0;
    return Global(ScoreRva, score) && score <= MaximumScore && Global(ScoreLockRva, locked) && !locked &&
        Writable(reinterpret_cast<void*>(g_base + ScoreRva), sizeof(uint32_t));
}
void CallHeal(const Context& c, float amount) {
#ifdef KH2_GUMMI_TESTS
    testHeal(reinterpret_cast<void*>(c.state), amount);
#else
    reinterpret_cast<HealFn>(g_base + HealRva)(reinterpret_cast<void*>(c.state), amount);
#endif
}
void CallAddScore(int amount) {
#ifdef KH2_GUMMI_TESTS
    testAddScore(amount);
#else
    reinterpret_cast<AddScoreFn>(g_base + AddScoreRva)(amount);
#endif
}
} // namespace gummi

bool GummiHandle(const TrainerContext& host, unsigned slot, const double* args, TrainerResult& result) {
    if (slot != 130 && slot != 131 && slot != 133) return false;
    result = {1, L"Enter a running Gummi mission with a living ship and close the pause menu."};
    gummi::Context c{}, fresh{};
    if (host.base != g_base || !gummi::BuildContext(c) || !gummi::ActionReady(c)) return true;
    if (!args) { result = {2, L"Command arguments are missing."}; return true; }
    for (unsigned i = 0; i < 8; ++i)
        if (!isfinite(args[i])) { result = {2, L"Every argument must be finite."}; return true; }
    if (slot == 130 && (args[0] <= 0 || args[0] > c.maxHp || static_cast<float>(args[0]) <= 0)) {
        result = {2, L"Healing must be positive and no greater than the current ship maximum HP."}; return true;
    }
    if (slot == 133 && (!IsInteger(args[0], 10, gummi::MaximumPointAddition) ||
                       static_cast<int>(args[0]) % 10 != 0)) {
        result = {2, L"Add points in whole multiples of 10, from 10 to 99,999,990."}; return true;
    }
    // The outer engine update has returned. Rebuild immediately before mutation;
    // never retain a ship through a restart, menu handoff or module transition.
    if (!gummi::BuildContext(fresh) || !gummi::SameLifetime(c, fresh) || !gummi::ActionReady(fresh)) return true;
    if (slot == 133) {
        uint32_t score = 0;
        if (!gummi::ScoreReady(score)) {
            result = {3, L"The mission score is locked, unavailable or invalid."}; return true;
        }
        if (!gummi::CodeMatches(gummi::AddScoreRva, gummi::ScoreCode, sizeof(gummi::ScoreCode))) {
            result = {4, L"The native Gummi score function changed; no points were added."}; return true;
        }
        gummi::CallAddScore(static_cast<int>(args[0]));
        result = {0, L"Mission points added. Later mission rewards and saves can reflect this change."};
        return true;
    }
    if (slot == 130 && args[0] > fresh.maxHp) {
        result = {2, L"The ship maximum HP changed; retry with an amount within the current maximum."}; return true;
    }
    const float amount = slot == 131 ? static_cast<float>(fresh.maxHp) - fresh.hp : static_cast<float>(args[0]);
    if (amount <= 0) { result = {0, L"The Gummi ship already has full HP."}; return true; }
    if (!gummi::HealthWritable(fresh) || !gummi::CodeMatches(gummi::HealRva, gummi::HealCode, sizeof(gummi::HealCode))) {
        result = {4, L"The ship HP fields or native healing function changed; no healing was applied."}; return true;
    }
    gummi::CallHeal(fresh, amount);
    result = {0, L"Gummi ship healed through its native HP recovery function."};
    return true;
}
void GummiCapabilities() {
    // IPC capabilities describe implementation; snapshot validity and handlers
    // describe availability in the current module.
    for (unsigned slot = 128; slot <= 143; ++slot) SupportCapability(slot);
}
void GummiSnapshot(const TrainerContext& host) {
    gummi::Context c{};
    if (host.base != g_base || !gummi::BuildContext(c)) return;
    SnapshotValue(128, c.hp); SnapshotValue(129, c.maxHp);
    SnapshotValue(138, c.missionPhase); SnapshotValue(139, c.playerPhase);
    SnapshotValue(140, c.route); SnapshotValue(141, c.variant ? c.variant : 1);
    uint32_t score = 0; BYTE locked = 0;
    if (gummi::Global(gummi::ScoreRva, score) && score <= gummi::MaximumScore) {
        SnapshotValue(132, score); SnapshotValue(134, score % 10);
    }
    if (gummi::Global(gummi::ScoreLockRva, locked)) SnapshotValue(143, locked ? 1 : 0);
    int medal = 0, progress = 0, best = 0;
    if (gummi::Global(0x72B2C4, medal) && medal >= 0 && medal <= 30) SnapshotValue(135, medal);
    if (gummi::Global(0x72B2C0, progress) && progress >= 0 && progress <= 9) SnapshotValue(136, progress);
    if (gummi::Global(0x72B2C8, best) && best >= 0 && best <= 30) SnapshotValue(137, best);
    uintptr_t row = 0; int rank = 0, rankPhase = 0;
    if (gummi::Global(0xAF4258, row) && Readable(reinterpret_cast<const void*>(row), 128) &&
        c.route <= 255 && c.variant <= 255 &&
        *reinterpret_cast<const BYTE*>(row) == c.route &&
        *reinterpret_cast<const BYTE*>(row + 1) == (c.variant ? c.variant : 1) &&
        gummi::Global(0xAF4204, rank) && rank >= 0 && rank <= 16 &&
        gummi::Global(0xAF4260, rankPhase) && rankPhase >= 0 && rankPhase <= 2) SnapshotValue(142, rank);
}
void GummiReset(const TrainerContext&) { /* One-shot changes are not rolled back. */ }
void GummiTick(const TrainerContext&) { /* No persistent effects or cached ship pointers. */ }
