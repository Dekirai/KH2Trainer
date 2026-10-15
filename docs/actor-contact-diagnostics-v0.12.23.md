# Actor reference diagnostics — v0.12.23

**Advanced > Actor references** shows three values for Sora and three for the current
lock-on enemy:

| Readout | Meaning |
| --- | --- |
| Actor references | The game's unsigned native reference counter. Scripts, commands and attacks can contribute. One attack can contribute multiple references, including two references to the same Actor. |
| Retirement requested | Whether the game has requested the Actor's removal. |
| Marked for retirement | Whether the Actor has been marked to leave the active list. |

These values help investigate an Actor that remains present while the game
finishes cleanup. They describe the current verified Actor; they do not retain
or track a previous Actor after a Drive transformation or target change. A zero
counter alone does not establish that an Actor can be freed. The native path
also has other conditions and class-specific callbacks.

## Implementation

The six entries are read-only, with command 0 and snapshot/capability slots 493–498.
The counter is DWORD+1464. The two sampled flags are DWORD+288 bits 0x10000000
and 0x80000. The original functions and descriptor path are documented in
[the contact retirement study](research/actor-contact-retirement-20261013/report.md).
The [script and command reference study](research/actor-reference-counter-20261013/report.md)
documents additional contributions to the same counter.

Sora's readouts reuse the existing completed gameplay identity inspection. The
target values reuse the existing complete bounded active-list validation,
current lock-on binding, enemy category and status back-pointer checks.
The target must still be in that active list. Removal flags and zero HP can be
observed there; actions retain their previous stricter living-target conditions.

No native counter predicate is called: those predicates can execute VM work.
No Actor pointer is retained for a later frame. The ordinary 100 ms diagnostic
cadence remains in place, and there is no extra list traversal for these fields.
Unavailable observations clear normally instead of preserving an old value.

## Verification

The new production-bridge fixture exercises all six fields, independent flags,
the unsigned 32-bit maximum, target replacement, invalid bindings, complete-list
validation and unavailable values. A read-only, non-executable fixture image
with invalid VM pointers verifies that the observation path performs no game
write or native getter call. It also counts the existing list traversals.

The existing combat and performance checks pass. The latter retain 20 diagnostic
publications over two simulated seconds at 60, 120 and 144 Hz. This is a private
fixture result, not a measurement of live game FPS. Core and offscreen WPF tests
cover the six catalog entries, exact unsigned values and their navigation.
See the [implementation receipt](validation/actor-contact-20261013/report.json)
and [independent native review](validation/actor-contact-20261013/review.json).
The [label review](validation/actor-contact-20261013/label-amendment.json) records
the broader counter name. Earlier targeted Core/UI results predate that rename;
the packaged `Validation` directory records the final build's checks.

Restart KH2 before connecting the new build to replace the previous bridge.
The release verification does not launch or modify a live game, save or Twitch
account. The Twitch Revert lock from v0.12.22 remains included.
