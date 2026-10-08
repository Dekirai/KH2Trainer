# Actor scale: native writers and restoration limits

**Result:** Actor+60 is a plausible positive uniform transform factor for a future Tiny/Giant effect. Actor+2732 must be excluded. Timed ownership still needs the independently verified Actor lifetime contract. This research adds no game writes or product feature.

## What the game actually writes

| Field | Initialization | Confirmed later use |
|---|---|---|
| float32 +48/+52/+56 | XYZ = 1 | Scene event opcode `0x28` writes an axis immediately or over time. Negative values control reflection parity. |
| float32 +60 | 1 | Multiplies all three basis scales in `3CCB90`. No additional writer was attributed in this round; this does not prove exclusive ownership. |
| float32 +2732/+2736 | value 1, rate 0 | Native normalized ramp. Reaching zero enters playable Actor cleanup. Unsuitable for Tiny/Giant. |

The event path is `2CB5D0 -> 2D1480 -> 2D0710` or a scheduled `2D05F0` task. The setter ABI is ECX axis, RDX Actor pointer, XMM2 float. Axis 0 sets Y (+52), 1 sets Z (+56), and 2 sets X (+48). It neither clamps the value nor checks the return of its Actor-list query.

The event record supplies float32 start/end at +8/+12, signed WORD duration at +16 multiplied by 2, and signed WORD axis at +18. The timed branch allocates a 12-byte value/rate/end interpolator. Task fields are Actor +24, interpolator +32 and axis +40. `2D05F0` checks live-list membership before a write; membership compares addresses. Cleanup `2D0680` frees the interpolation buffer and **does not restore the old scale**. A trainer must not overwrite a later scene result with a saved baseline.

## Why +2732 is dangerous

`3CC730` advances this value through `3B77C0`; the latter clamps its value/rate pair to 0/0 or 1/0. `3BFD30` tests the resulting value against zero and calls descriptor virtual slot +56.

The original descriptor and vtable data prove the playable paths:

- Sora/Roxas: `750300 -> 5CBA28`, slot +56 -> `404BB0`.
- Mickey: `7523B8 -> 5D15A0`, slot +56 -> `4151E0`.
- Both reach `3A8F30`, which clears the active Player global and cleans its controller/resources.
- The following `3D6770 -> 3D36D0 -> 3B4700` chain ends child/weapon Actors, performs status saveback through `3C2120`, and sets deletion flag Actor+288 bit `0x10000000`.

`3C2120` is HP/MP/Drive **saveback**, not status release. These are concrete side effects; +2732 is not a free display-only scale field.

## Collision does not resize proportionally

`3CCB90` builds a shared transform from XYZ, scalar +60 and ramp +2732. Joint lookup `3B50F0` and collision conversion `3C9C00` use those matrices. However, the conversion copies resource radius/height WORDs directly into float dimensions without applying scale. The shape center moves with its joint transform; its radius and height remain separate.

The downstream tests confirm this distinction:

- `3C94C0`, `3C9780` and `3C9890` compare centers with the dimensions already in their records. Their arguments are shape records, not Actors.
- `3C90B0` computes a separation correction from those same dimensions, with a native radial margin of 5. `40AD70` distributes corrections between Actors and moves record centers.
- The common constructor separately populates world-collision radius/height at Actor+1776/+1780 and another radius copy at +1784.
- `3B9090 -> 16FEC0 -> 1752E0` passes the collision-state subobject at Actor+1744. `1752E0` uses its +32 radius (= Actor+1776) for movement substeps. It receives no Actor-scale argument.

This evidence supports a transform-size effect with joint and collision-center consequences. It does not support the description "all collision volumes shrink/grow with the body."

## Proposed later implementation boundary

Use a small finite positive factor on scalar +60, leaving native XYZ and +2732 unchanged. The exact interval is a product policy requiring tests, not a safe range established by the binary. Reject invalid compounded transform values, attachments and native control/lifetime transitions.

Capture/apply/release must run in a native game-thread transaction tied to the independently verified Actor generation. Actor pointer, status pointer, form, room and live-list membership alone are not a generation token. A recycled address can pass them.

Restore only for the same proven lifetime and when the current scalar bits still equal the last owned value. On a different value or native takeover, relinquish ownership instead of forcing an old baseline. A same-value native write remains invisible to a simple value comparison. Observer failure is not proof of destruction. No implementation is approved solely by this report; the new ActorLifetimeSupport work needs its own integration review.

## Evidence and reproducibility

`evidence.json` contains 40 complete dedicated ASM exports, 4,462 instructions and 20,282 original function bytes. Ten additional original data spans total 80 bytes. `verification.json` records their equality to the unchanged retail EXE. The 40 address-specific claims in `report.json` are deliberately narrow; re-exported prior functions and complete exports are not new full-semantic reviews.

Run from any directory:

```text
py -3.13 path/to/actor-scale-writers-20261007/verify.py --exe "path/to/KINGDOM HEARTS II FINAL MIX.exe"
```

`search-evidence.json` and `additional-search-evidence.json` retain candidate searches. A broad numeric operand query missed a confirmed displacement; it is not used as absence proof. Direct displacement scans also match unrelated structures, and several scalar candidate scans are partial. VM/indirect writers and all possible scale consumers remain outside the established coverage.

No game execution, UI access, save operation, EXE patch, IDB change or product build was performed for this round.
