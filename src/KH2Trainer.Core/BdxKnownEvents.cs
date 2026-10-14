namespace KH2Trainer.Core;

/// <summary>A captured native caller convention for one event ID. The ID alone does not prove which native path loads a script.</summary>
public sealed record BdxKnownEvent(int Id, string Title, string Summary, string Evidence)
{
    public string Details => $"Event {Id} · {Title}\n{Summary}\nEvidence: {Evidence}\n\n{BdxKnownEvents.Scope}";
}

/// <summary>Read-only event roles from static research; independent of the structural BDX decoder.</summary>
public static class BdxKnownEvents
{
    public const string Scope = "A known event ID describes a native call convention, not proof this handler runs. Its meaning depends on which native path loads the script; another loader can use the same ID differently or never call it.";
    public static IReadOnlyList<BdxKnownEvent> All { get; } = Array.AsReadOnly(new BdxKnownEvent[]
    {
        new(0, "Actor setup, if Actor-bound",
            "When an Actor binds this script from its BAR type 3 entry, RVA 0x3B44D0 creates a VM owned by that Actor and runs Event 0 with the encoded Actor as its @ADR operand. Actors whose class flag +1736 bit 0x20 is set skip this binding.",
            "app-timer-dispatch-20261008 (RVA 0x3B44D0)"),
        new(1, "Actor start, if Actor-bound",
            "The same Actor binding (RVA 0x3B44D0) starts Event 1 after invoking Event 0. Its operands are not established.",
            "app-timer-dispatch-20261008 (RVA 0x3B44D0)"),
        new(2, "Registry setup, if registry-loaded",
            "When the eight-slot script registry (RVA 0x3F4A20) loads this script, it creates a VM without an owner Actor and runs Event 2 synchronously.",
            "timer-message74-handlers-20261008 (RVA 0x3F4A20)"),
        new(3, "Registry start, if registry-loaded",
            "The same registry (RVA 0x3F4A20) starts Event 3 after Event 2.",
            "timer-message74-handlers-20261008 (RVA 0x3F4A20)"),
        new(4, "Registry exit, if registry-loaded",
            "The same registry (RVA 0x3F4A20) installs the Event 4 PC as the VM exit PC. VM teardown can run it.",
            "timer-message74-handlers-20261008 (RVA 0x3F4A20); app-timer-dispatch-20261008 (RVA 0x3E1C80)"),
        new(10, "Native message, if delivered",
            "RVA 0x3E1840 runs Event 10 with two operands: message (@INT) and parameter (@INT). Actor scripts receive it through the Actor broadcast (RVA 0x3B4C90); registry scripts receive it through RVA 0x3F4980. Captured messages: 74 when the global App timer used by mission clocks expires or reaches its count-up limit (parameter 0); 14 and 123 when a mission counter crosses zero or its maximum; 136 and 137 when a mission gauge crosses zero or its maximum. Counter and gauge messages pass the widget ID as the parameter. A handler can receive other messages.",
            "app-timer-dispatch-20261008 (RVA 0x3E1840); timer-message74-handlers-20261008 (RVA 0x3F4980); bdx-bank4-calls-20261008 (RVA 0x3FA230, RVA 0x3FA310)"),
        new(27, "Contact hit, if delivered",
            "RVA 0x3B5E80 runs Event 27 with three operands: Actor (@ADR), joint ID (@INT) and the 32-byte runtime contact record (@ADR). The script pops them as record, ID, Actor. Contacts come from BAR type 23 type 10/11 definitions and the current motion; only IDs absent from the previous pass are delivered.",
            "motion-event27-20261008 (RVA 0x3B5E80, RVA 0x3C6AA0)"),
    });

    public static BdxKnownEvent? Find(int id) => All.FirstOrDefault(e => e.Id == id);
}
