using KH2Trainer.Core;

internal static class GameplayStateTests
{
    internal static void Run(Action<bool, string> check)
    {
        TrainerSnapshot Sample(uint tick = 5000, PlayerRole role = PlayerRole.Sora,
            GameplayBlockers blockers = GameplayBlockers.None, bool known = true)
        {
            var snapshot = new TrainerSnapshot { Connected = true, SceneReady = true, Status = 1 };
            void Set(int slot, double value)
            {
                snapshot.Values[slot] = value;
                snapshot.Valid[slot / 64] |= 1UL << (slot % 64);
                snapshot.Supported[slot / 64] |= 1UL << (slot % 64);
            }
            Set(GameplayState.KnownSlot, known ? 1 : 0);
            Set(GameplayState.RoleSlot, (int)role);
            Set(GameplayState.BlockersSlot, (uint)blockers);
            Set(GameplayState.ControllableSlot, new GameplayState(known, role, blockers).IsControllable ? 1 : 0);
            Set(GameplayState.PublicationTickSlot, tick);
            return snapshot;
        }

        foreach (var role in Enum.GetValues<PlayerRole>())
        foreach (var blocker in Enum.GetValues<GameplayBlockers>())
        {
            var observed = GameplayState.FromSnapshot(Sample(role: role, blockers: blocker), 5000);
            check(observed.Known && observed.Role == role && observed.Blockers == blocker &&
                observed.IsControllable == (role is PlayerRole.Sora or PlayerRole.Roxas or PlayerRole.Mickey && blocker == GameplayBlockers.None),
                $"gameplay observation preserves {role}/{blocker}");
        }
        check(GameplayState.FromSnapshot(Sample(), 6000).IsControllable &&
            !GameplayState.FromSnapshot(Sample(), 6001).Known, "gameplay publication expires after one second");
        check(!GameplayState.FromSnapshot(Sample(), 4999).Known, "future publication timestamp is rejected");
        check(GameplayState.FromSnapshot(Sample(uint.MaxValue - 99), 50).IsControllable,
            "gameplay freshness survives Windows 32-bit uptime wrap");
        check(GameplayState.FromSnapshot(Sample(0), 0).IsControllable, "zero uptime is valid at clock wrap");
        check(!GameplayState.FromSnapshot(Sample() with { Connected = false }, 5000).Known &&
            !GameplayState.FromSnapshot(Sample() with { Status = -1 }, 5000).Known &&
            !GameplayState.FromSnapshot(Sample() with { ErrorCode = 15 }, 5000).Known,
            "disconnected or failed bridge cannot report a controllable player");
        check(!GameplayState.FromSnapshot(Sample() with { SceneReady = false }, 5000).IsControllable,
            "field resources remain mandatory even with a ready observation");
        foreach (int slot in new[] { 456, 457, 458, 459, 463 })
        {
            var missing = Sample(); missing.Valid[slot / 64] &= ~(1UL << (slot % 64));
            check(!GameplayState.FromSnapshot(missing, 5000).Known, $"missing gameplay slot {slot} fails closed");
            var unsupported = Sample(); unsupported.Supported[slot / 64] &= ~(1UL << (slot % 64));
            check(!GameplayState.FromSnapshot(unsupported, 5000).Known, $"unsupported gameplay slot {slot} fails closed");
            foreach (double bad in new[] { double.NaN, double.PositiveInfinity, -1, .5, (double)uint.MaxValue + 1 })
            {
                var malformed = Sample(); malformed.Values[slot] = bad;
                check(!GameplayState.FromSnapshot(malformed, 5000).Known, $"malformed gameplay slot {slot}/{bad} fails closed");
            }
        }
        foreach (var (slot, value) in new[] { (456, 2), (457, 5), (458, 1024), (459, 2) })
        {
            var unknown = Sample(); unknown.Values[slot] = value;
            check(!GameplayState.FromSnapshot(unknown, 5000).Known, $"unknown gameplay enum at {slot} fails closed");
        }
        var contradictory = Sample(blockers: GameplayBlockers.Menu); contradictory.Values[459] = 1;
        check(!GameplayState.FromSnapshot(contradictory, 5000).Known, "contradictory controllability fields fail closed");
        check(!GameplayState.FromSnapshot(Sample(known: false), 5000).IsControllable,
            "unverified native interpretation cannot admit effects");
        check(!GameplayState.FromSnapshot(TrainerSnapshot.Disconnected, 5000).Known,
            "legacy snapshots without gameplay observation fail closed");
    }
}
