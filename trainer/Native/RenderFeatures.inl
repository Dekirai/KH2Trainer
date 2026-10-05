// Read-only GX diagnostics. Renderer workers can update these fields between
// samples; none of these values describes a coherent completed render frame.
namespace renderstats {
constexpr uintptr_t ObjectRva = 0x8A0970;
constexpr uintptr_t VtableRva = 0x5A9028;
bool Ready(const TrainerContext& c) {
    if (!c.sceneReady || c.base != g_base || !g_gameThread ||
        GetCurrentThreadId() != g_gameThread || !g_base) return false;
    const uintptr_t object = c.base + ObjectRva;
    return Readable(reinterpret_cast<const void*>(object), 58248) &&
        *reinterpret_cast<const uintptr_t*>(object) == c.base + VtableRva &&
        *reinterpret_cast<const uintptr_t*>(object + 736) != 0 &&
        *reinterpret_cast<const uintptr_t*>(object + 1144) != 0;
}
template<class T> T Sample(uintptr_t object, size_t offset) {
    return *reinterpret_cast<const volatile T*>(object + offset);
}
void Bounded(unsigned slot, double value, double minimum, double maximum) {
    if (isfinite(value) && value >= minimum && value <= maximum) SnapshotValue(slot, value);
}
}
void RenderCapabilities() {
    for (unsigned slot = 184; slot <= 194; ++slot) SupportCapability(slot);
}
void RenderSnapshot(const TrainerContext& c) {
    if (!renderstats::Ready(c)) return;
    const uintptr_t object = c.base + renderstats::ObjectRva;
    SnapshotValue(184, renderstats::Sample<uint32_t>(object, 816));
    renderstats::Bounded(185, renderstats::Sample<int32_t>(object, 96), 0, 47);
    renderstats::Bounded(186, renderstats::Sample<int32_t>(object, 108), 0, 5);
    SnapshotValue(187, renderstats::Sample<uint32_t>(object, 58244));
    SnapshotValue(188, renderstats::Sample<uint32_t>(object, 58232));
    SnapshotValue(189, renderstats::Sample<uint32_t>(object, 58236));
    renderstats::Bounded(190, renderstats::Sample<int32_t>(object, 22944), 0, 1);
    renderstats::Bounded(191, renderstats::Sample<BYTE>(object, 640), 0, 1);
    renderstats::Bounded(192, renderstats::Sample<float>(object, 23360), 0.0001f, 10000);
    renderstats::Bounded(193, renderstats::Sample<uint32_t>(object, 23364), 0, 3);
    renderstats::Bounded(194, renderstats::Sample<uint32_t>(object, 23368), 0, 10);
}
