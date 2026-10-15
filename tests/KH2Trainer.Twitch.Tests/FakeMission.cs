/// <summary>
/// The bridge's mission clock readouts. Slot 229 reports any owner in the native mask; slot 233 only the
/// trainer's own freeze bit, which the bridge drops (and never re-applies) when its mission ends.
/// </summary>
internal sealed partial class FakeGame
{
    private bool nativeClockPause;

    /// <summary>A native pause owner (for example script owner 2) in the mission clock mask.</summary>
    public bool NativeClockPause
    {
        get => nativeClockPause;
        set { nativeClockPause = value; PublishClockPause(); }
    }

    public void StartMission(double seconds, bool countdown = true)
    {
        Set("mission.phase", 1); Set("mission.timer.direction", countdown ? 1 : 0); Set("mission.timer.phase", 2);
        Set("mission.timer.seconds", seconds); Set("mission.timer.freeze", 0);
        PublishClockPause();
    }

    public void EndMission()
    {
        Set("mission.phase", 3); Set("mission.timer.freeze", 0);
        PublishClockPause();
    }

    private void PublishClockPause() => Set("mission.timer.paused", nativeClockPause || Get("mission.timer.freeze") == 1 ? 1 : 0);

    private void RejectMissionCommand(string feature, double[] args)
    {
        if (feature == "mission.timer.countdown" && (Get("mission.phase") != 1 || Get("mission.timer.paused") != 0))
            throw new InvalidOperationException("Restart needs an active mission timer and stable unpaused gameplay.");
        if (feature == "mission.timer.freeze" && args[0] == 1 && (Get("mission.phase") != 1 || Get("mission.timer.phase") is not (1 or 2)))
            throw new InvalidOperationException("Freezing needs an active mission clock.");
    }
}
