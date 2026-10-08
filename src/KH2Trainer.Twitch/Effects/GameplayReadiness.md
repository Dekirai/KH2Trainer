# Crowd Control gameplay readiness

`IGameControl.Gameplay` supplies the Core decoder's fresh `GameplayState`.
`SceneReady` still means that scene resources exist. A field reward also needs
a known supported player role and no external control blockers. Missing or stale
control metadata waits; it does not silently fall back to `SceneReady`.

## Roles

Unreviewed reward paths remain Sora-only. HP heal/set, full restore, regeneration,
MP restore/unlimited MP, music/voice levels, caption visibility and display previews
admit Sora, Roxas and rescue Mickey. HP/MP admission follows the separately audited
native role, control, HUD and animation-resource guards. MP-only rewards reject a
known zero maximum and wait for a missing or invalid maximum. The usable range is
an integer from 1 through 255, matching the native `PlayerLiving` bounds on
`STATUS+388`. Full restore can still heal HP
when there is no MP gauge, but refunds if all available gauges are already full.
The owned damage guard admits all three field roles through the separately
verified Sora/Roxas and rescue-Mickey damage callbacks and actor identity.
Drive and animation rewards remain Sora-only.
Gummi repair/bullet removal retain their separate native context checks.

The `super-speed`, `snail` and `moon-jump` rewards now admit Sora, Roxas and rescue
Mickey through the protocol-v4 movement journal. They do not use scalar
`OwnedValue` restores. One coherent snapshot supplies the bridge instance, actor
generation, control state and exact Float32 movement values. Every selected
original must be finite and within the native policy before the entire cohort is
compared and changed on the game thread. A changed second field or actor rejects
the whole request before its first write.

An immutable native receipt supplies originals for that exact actor lifetime.
Changing actor, even to the same role/address/values, needs another confirmed
acquire. The old living actor receives release intent and keeps its own originals
until it returns; proven retired generations need no pointer write. Reapply keeps
an unchanged sibling's original and captures a valid changed sibling separately.
Changed external values survive cleanup. Same-value external writes remain
indistinguishable within one lifetime; this does not transfer ownership across
lifetimes. Moon Jump changes base jump height and a falling-speed cap, not gravity;
growth abilities and special actions may use other values.

`MovementEffectLease` runs bounded asynchronous maintenance before ActiveCheck.
Absent/out-of-policy values, control loss, unknown acknowledgements or unconfirmed
ownership pause duration and extensions. The clock also checks actor identity
before and after awaited operations and against the previous tick. A rebind never
charges the preceding interval. Initial definitive no-write refusals retry until
the configured waiting limit, then refund. Native observer/write faults never
justify pointer-based restoration.

Lease IDs, bridge nonces and generations use binary UInt64 fields. An interrupted
publication keeps a pending handle and blocks new command publication, including
unrelated manual writes. QueryMiss or QueryRejected cannot clear the uncertainty.
Only a matching original receipt or a separately confirmed different bridge can
resolve it. Version3 bridges fail closed; restart the game after updating.

## Time and restoration

The script-owned mission-clock pause bit (`ABB854 & 2`) does not by itself pause
reward time: native field and player-input updates still run. Actual menu,
cutscene, transition, controller and actor-freeze gates remain independent.
Other unclassified mission-clock owners still produce an unknown observation.
The expected FIELD_COMMAND vtable/callbacks and role-specific controller-update
adapter must also match before the bridge reports control as available.

With timer pausing enabled, duration is charged only when the effect was already
established and both successive control observations are usable. An interval
longer than the native freshness limit (currently one second) is unobserved and
charges zero. The host normally ticks every 250 ms. This is conservative sampled
accounting, not a frame-exact clock: a short pause entirely between observations
cannot be reconstructed. A backward wall-clock adjustment does not charge time
again when the clock catches up. Disabling timer pausing retains wall-time expiry
for control pauses.

Unlimited MP additionally checks current MP availability throughout its lifetime.
A missing, nonfinite, fractional, negative, out-of-range or zero maximum pauses
its timer, sustain and established monitor, as does losing a required MP
capability. This usefulness check applies even if control-based timer pausing is
disabled. Both interval endpoints must be usable, and intervals longer than one
second remain unobserved; gauge recovery never retroactively charges a pause.
An extension stays queued and unpaid until the effect can be useful again.
Returning availability triggers immediate sustain through the existing ownership
logic. This is sampled gauge availability, not proof that every native refill ran:
native dispatch still validates its own current resources and may refuse a write.

`EffectDefinition.ActiveCheck` expresses this read-only ongoing condition. It is
separate from the start check (which rejects an already enabled MP toggle) and
from cleanup. Losing an MP gauge never prevents disabling the effect's owned
toggle. Cleanup still requires player control, the supported role and a finite
toggle readback; rejected writes remain queued under the existing retry rules.

The two freeze rewards ignore only their own successfully applied and currently
observed trainer pause bit. Other blockers still stop the clock. Replacing one
freeze first releases its owned bit; a rejected release blocks the replacement.
Neither admission previews nor this exemption bypass the native command guards.

Sustain, monitors for established effects, and restoration wait for control.
Native acknowledgements for a not-yet-established Drive request may still be
observed while it loads. A stopped unsuccessful request is refunded once; slot
126 may cancel its trainer-owned queued steps while loading. That cancellation
does not change the active actor or interrupt a native transition already running.

Owned values need a current finite readback before restoration. Failed sustain
writes do not replace the saved original. Restores preserve reverse ordering and
retry for up to three minutes of observed available time; menus, unknown periods
and long unobserved gaps do not use that budget. Deferred custom end steps keep
their group reserved and cannot settle a deferred-payment reward as successful.
They use the same available-time retry bound. Scalar pending cleanup remains in
memory and needs future engine ticks. Movement cleanup is separately recorded in
the native journal: release intents are allowed without player control, while
restoring fields still requires native lifetime/control checks. The effect group
remains reserved until terminal cleanup is acknowledged. Movement ownership is
not dropped after the scalar three-minute limit. Host shutdown/heartbeat expiry
requests native cleanup; an old off-current actor may still need to return or be
proven retired. A fresh different bridge discards inaccessible local records
without restoring their values into the new process.

FOV restoration requires both current camera observations and respects changed
values. Rejected cleanup is retried, rather than treated as completed. Brightness
restores its exact owned original through the brightness-only setter. Color Chaos
uses one coherent packed color observation and a native paired comparison under
the presentation mutex. Its end restores only the original mode and strength,
and only if both native values still match its applied filter. Changed filters
are preserved, including changes after the host snapshot. Brightness and loaded
configuration are untouched. This is value-based ownership: an external writer
that reapplies the identical pair cannot be distinguished without observing that
writer. Custom end actions do not share a blanket ownership guarantee.

## Regression suite

`GameplayReadinessTests` uses the real feature catalog and an in-memory game.
It covers every blocker, role admissions, MP without a usable maximum, interval
boundaries, backward clocks, both self-freezes and reciprocal replacement,
paused sustain/cleanup, missing readbacks, failed sustain ownership, FOV retries,
brightness isolation, mid-end pauses and one-time Drive cancellation/refunds.
Existing engine, catalog, API, service and local overlay tests run with it.
`MpAvailabilityTests` adds supported-role/gauge changes, every invalid maximum,
capability loss, queued extensions, recovery boundaries, timer opt-out, long gaps,
backward clocks, deferred cleanup and preservation of external toggle changes.
`MovementRewardTests` covers three roles, policy boundaries, atomic cohort
rejection, equal-value actor replacement, same-role reconstruction, old actors
returning, awaited changes, late acknowledgements, control loss, terminal garbage
collection, no-write refusal limits and fresh-bridge recovery. Core
`MovementProtocolTests` separately covers binary layout/correlation, malformed
packets, large UInt64 values, freshness, cancellation, lost ACKs, QueryMiss/rejected
queries, reconnect, unbound uncertainty and replacement-instance proof. Fake
journal tests validate host decisions; separate native suites validate the native
boundaries. No live-game validation is implied.
