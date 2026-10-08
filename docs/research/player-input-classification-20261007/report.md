# Player input and mission-clock classification

## Implemented correction

`GameplayStateSupport.inl` now permits the native mission-clock pause owner **2**
when every actual player/control gate passes. Previously this owner alone forced
`Unknown`, so a stopped mission clock could unnecessarily pause a Crowd Control
reward while the player remained controllable.

The change is limited to that owner bit. An active event still produces
`Cutscene`; menus, field suspension, actor/input locks and unsupported roles remain
blocked. Other unexplained clock owners remain `Unknown`. The pre-existing
trainer-owned field-pause and actor-freeze distinction is preserved.

This is a read-only classification change. It neither pauses nor resumes the
mission timer, changes controls, nor calls the native game from production code.

## Native proof

- `4335D0` loads ECX=2 and tail-jumps to `157130`. That leaf only ORs the argument
  into `ABB854`, the mission-clock owner mask.
- `1570F0` advances mission-clock count `ABB850` only with a zero owner mask.
  `1571B0` uses the same mask to suspend the mission countdown/count-up state.
- Field-frame `154700` ignores `1570F0`'s return, increments independent field
  counters `ABAC00` and `ABAC04`, and continues its frame work.
- Sora/Roxas descriptor slot24 (`404A30`) and Mickey slot24 (`4150D0`) forward the
  Actor to `3A8980`, which reads its configured controller and calls `3FD690`.
  This calls `3B2340`, the shared FIELD_COMMAND update.
- `3B2340` gates ordinary input on descriptor slot120, controller flag1 and
  input bitmap `2A10500`. The common player predicate also checks mission-ended
  state, category locks, the tutorial flag, transition and actor update flags.
  None of these bodies consults the mission-clock pause mask.

Full original bodies and caller references are in `evidence.json` and
`xrefs-extra.json`; `claims.json` gives one bounded statement per captured body.
Addresses are preferred-base native VAs, not CIL addresses.

## Controller identity hardening

The classifier additionally checks the actual controller vptr at `2A10620` is
FIELD_COMMAND (`5C4C68`), its consumed virtual slots16/24 are `3F29E0`/`3F2470`,
and the current role's descriptor slot24 is the proved update wrapper. Matching
Actor/pad pointers alone no longer establish the known input pipeline.

Twelve added complete code pins protect the newly used interpretation. Together
with existing pins there are41 original-matching spans,6301 bytes. Replaced,
unreadable or mismatched relevant callbacks fail closed. This remains an exact
retail-code contract; it does not promise compatibility with arbitrary mods that
replace these callbacks while preserving their intended behavior.

## Why no event/minigame allowlist was added

The old event-helper names did not identify the real input consumer:

- `3AC230` is read by an event/fiber waiter `2D8FE0`.
- `3AC260` contributes to Actor boolean predicates `3D5310`/`3D65A0` and does not
  read the pad or the FIELD_COMMAND gate.
- `3ABC80` is used by trigger/timer and special motion-state consumers, not the
  verified FIELD_COMMAND input gate.

Event start/resume (`3AC350`/`3AD2D0`) disables Actor categories0/1 only when mode
byte2 bit8 is clear; it always adds clock owner4 and has separate camera, sound
and VM actions. A set bit8 therefore means one disabling action was skipped,
not that the whole event leaves the player in ordinary control. The current
conservative event block is retained.

Movement helper `3A8FA0` also has raw-pad and object-type2/24/53 branches. The
verified ordinary FIELD_COMMAND route does not settle all minigames, scripted
controllers, special actions or event camera ownership. A future exception needs
a bounded event-mode/resource witness and its complete relevant update path.

## Verification

The offline verifier checks68 full IDA bodies,3045 instruction rows and12146
captured body bytes against the exact original retail PE SHA256. It separately
verifies316 data/leaf bytes. The only non-instruction range inside a function is
the explicit48-byte switch-RVA table after `4060E0`'s final RET; all12 targets
must point to captured instruction boundaries. Cursor/count consistency and
independent Capstone decoding are enforced; incomplete captures are rejected.

Synthetic native tests passed:

- GameplayStateGuardTests:399 checks,0 failures.
- CombatGuardTests:1870 checks,0 failures.
- PlayerHealthGuardTests:265 checks,0 failures.

The gameplay suite covers all three supported roles, every owner bit combined
with owner2, trainer/external pause combinations, active events, menu and real
input locks, foreign vtables/callbacks, code-pin/read failures and snapshot
read-only behavior. It also executes the unchanged `4335D0`/`157130`/`1570F0`
leaf machine code in synthetic allocated memory to confirm that the mission
counter stops while the classifier retains player control. No live game code
or game process was accessed. The two dependent fixtures only add known vtable
values; their health/damage expectations are unchanged.

## Integration and limits

No Core, Twitch, UI, version or protocol fields change. Existing slots456..463
and their freshness/role/blocker semantics remain intact. Core and Twitch do not
derive controllability from the mission-clock owner; their existing tests and
sampled-duration logic remain applicable. A known unrestricted player now
continues consuming reward duration during a clock-only script pause. Other
blockers still pause the effect under the existing settings and ownership rules.

The native observation is sampled, not a proof of every frame between snapshots.
This work does not turn a clock bit into an event permission, guarantee an action
button is useful in every animation, or bypass per-feature native guards.

`baseline-GameplayStateSupport.inl` and the baseline test file preserve the
pre-change source. `implementation-delta.patch` compares those with the current
owned files; final hashes and test logs are recorded by `report.json`.
