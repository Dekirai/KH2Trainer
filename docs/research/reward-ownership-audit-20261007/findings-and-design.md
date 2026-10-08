# Reward ownership audit — 2026-10-07

## Scope and baseline

The shipped v0.12.4 catalog has **59 rewards total**, including the three movement rewards already using the MOV1 generation journal. Therefore the remaining set contains **56**, not 59. `rewards.json` covers all 59 and identifies the three reference rows. It binds every row to feature command/value/capability slots, actual native source files, host policy, storage scope and remaining limits. It is a classification of those paths, not a claim that every downstream native function was freshly reviewed.

The baseline is the immutable v0.12.4 `Source.zip` identified by hash in `rewards.json`. This avoids mixing this turn's concurrent native bookmark/collision fixes into the old behavior. `baseline-source-excerpts.json` preserves the relevant old host and native excerpts. The small approved host fix is recorded separately in `ghost-fix-receipt.json`.

Fresh IDA evidence uses the existing lifetime database, adopted as read-only session `81d9501c`; its health says auto-analysis and Hex-Rays ready. `native-evidence-full.json` contains 13 complete bodies. `verify_native.py` checks cursor completion, instruction counts, full body sizes, original retail PE bytes, independent Capstone instruction boundaries, and six descriptor/vtable cells. Result: **352 instructions, 1,490 function bytes and 48 data bytes**, matching retail SHA256 `9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed`. No game functions were executed.

## Concrete findings

### F01 — Invincibility currently selects the wrong descriptor and callback

`CombatFeatures.inl::StartGuard` requires decoded Actor+0 to equal imagebase+`74A518`, vtable `5C4A80`, damage slot `5C4B68` (+0xE8) containing `3A75F0`. `MayBlock` and `CombatTick` repeat that restriction. The proven playable-role descriptors instead contain:

| Role | Descriptor RVA | Vtable RVA | +0xE8 slot RVA | Original callback RVA |
|---|---:|---:|---:|---:|
| Sora / Roxas | 750300 | 5CBA28 | 5CBB10 | 404EE0 |
| Rescue Mickey | 7523B8 | 5D15A0 | 5D1688 | 415410 |
| Current guard's descriptor | 74A518 | 5C4A80 | 5C4B68 | 3A75F0 |

The two player callbacks are each seven instructions. Their ABI is RCX descriptor, RDX Actor, R8D signed HP delta, R9D bar, fifth stack BYTE effects. They rearrange arguments and tail-jump to `3A85F0`. That helper performs negative-hit Drive-gain bookkeeping then delegates to `3D5E50`; the latter handles MP-on-damage and calls `3D2EB0`. The current base-class function `3A75F0` is a separate function, not the selected player's vtable target. The supported descriptors cannot pass the current guard's equality test. This is a confirmed availability defect, not a claim of a live crash.

**Implementation candidate 1:** repair the selected descriptor's actual slot and preserve its immutable original exactly once on pass-through. Sora/Roxas share one slot; Mickey has another. Bind the active policy to the verified role and `actor_lifetime` generation, current actor/status, scene lease, thread/heartbeat and exact hook ownership. Do not infer safety from changing just `ControllerRva`. Validate actual consumer call sites, returned HP semantics, and every variant's full code before publication. Block only negative bar0 callbacks; direct scripted HP assignments and hit reactions are not covered. Synthetic tests should use the actual proven role descriptors and slot bytes, cover new Sora at the same address, alternate roles, hook takeover and missing observer. The present fake reward test merely accepts feature106 and could not reveal the wrong descriptor.

### F02 — Ghost Walk bypassed a rejected native return

The baseline stores host world/room and X/Y/Z; if native bookmark return fails it sends three individual position writes whenever just the two world/room values match. If that also fails, it reloads the room. The native bookmark checks more identity data than these two bytes. A fresh Sora in the same room can therefore receive the old Sora's coordinates after a correctly rejected bookmark. Each axis command invokes native `3B6100`, which changes flags and collision/position state; this is not a harmless UI fallback.

**Approved immediate fix:** remove both fallback branches and their declared capabilities. Only native bookmark return can move the player. Rejection produces a visible end detail and still attempts/defer-retries collision cleanup. `ghost-fix-receipt.json` records the host changes and fake tests. Root independently owns generation binding for native bookmark and collision release; this report does not substitute host tests for those native tests.

**Implementation candidate 2:** finish generation-bound native bookmark/collision leases. Pin generations while retained; never treat pointer/map equality as lifetime. Off-current collision ownership must remain pending without following stale pointers; a retired generation permits a no-write retirement. Restore only the exact owned collision profile when the same verified generation becomes current. Bookmark return must not fall back to generic coordinate setters.

**Remaining shared-bookmark limitation:** manual UI actions and both position rewards share one native bookmark. Another manual capture on the same still-valid actor can replace the reward's saved origin, even with ActorGeneration. A capture receipt/revision and expected-revision return command are needed to distinguish owners. The current `EffectContext` exposes actor identity only through an active movement lease, so this narrow fix does not add a misleading host-only identity test. Native current-generation validation is still the decisive guard.

### F03 — Four timed status rewards retain originals without an actor or rebuild identity

`lucky-streak` changes Float32 STATUS+568/+572, `magnet` changes +520, `tax-collector` changes +580 (UI percent mapped to a float factor), and `glass-cannon` changes BYTE+430. This is four reward rows but five scalar fields. `OwnedValue` captures a host read before an awaited generic command; it stores no native receipt. Restore checks `Near(live, applied)` and writes the original to whichever player is current. A same-valued replacement can receive a stale original even when both actors are Sora.

Fresh `3D7470` proves the ability subobject is Actor.status+464. Fresh `4016B0` resets its Draw/Jackpot/Lucky to0 and retention to1. Fresh `3C1D90` invokes that initializer on the same STATUS, then sets damage coefficients+424..430 to100 before applying equipment/abilities. Thus **ActorGeneration alone does not prove that a STATUS rebuild has preserved modification ownership**. A status address, refcount and backlink identify current allocation/use, not every rebuild or same-value writer.

`LootFeatures::Ready` uses the generic `damage_tuning::Ready` plus STATUS+504 selfpointer. `damage_tuning::Ready` verifies pool/free-list membership, actor list/current/backlinks and field readiness, without a char1 condition. This makes an eventual FieldPlayers extension plausible, but not a safe host-role-only edit. The peer source review agrees on this distinction.

**Implementation candidate 3:** a separate typed STATUS-cohort transaction using the existing actor observer/journal patterns. Use explicit field masks and wire types: Draw/Jackpot/Lucky/Retention Float32, general damage coefficient BYTE. Acquire must resolve the coherent role, current generation and allocated status under one game-thread command, validate *all* originals and desired values before any write, and return exact original/applied bits plus status binding in an immutable receipt. Reapply/Release must compare that binding and the entire owned cohort before writing; no stale host scalar fallback. Keep unknown acknowledgements globally unresolved, as MOV1 already does.

For a full same-actor rebuild guarantee, first prove and instrument every relevant status construction/rebuild edge or add a justified native STATUS-revision observer. A revision for `3C1D90` alone is insufficient unless alternate rebuild paths are excluded. Without that proof, explicitly scope the first transaction to actor-lifetime safety and external-value comparisons, leaving same-value rebuild takeover as a stated limitation. Do not call it complete ownership. Active duration should count only while an acknowledged lease is usable for the current generation; missing/native-rejected data must stop sustain and timing, while cleanup remains possible.

### F04 — Lock-on scale restores a coupled global through a single-value check

Fresh `3ABD60` writes global scale `2A1141C` and recalculates break distance `2A11420` as scale×parameter+80. `3ABD80` can write break distance independently. `eagle-eye` and `short-sighted` observe only the scale, so end can overwrite an independent break-distance edit while scale still matches. These are global parameters, not actor-owned fields. A small native exact pair compare/apply command under the existing game-thread/parameter-span guards would close this specific gap. Current TargetingReady intentionally inherits the legacy Sora-only movement guard; widening role admission needs separate lock-on-context evidence.

### F05 — Motion's existing native lease is stronger than a scalar, but not generation-bound

`slowpoke` and `hyper` use global desired speed plus `motion.override`. The native lease compares actor/status/form/scene/model resources and exact Float32; it observes the VM writer before the write, even for the same float. Those protections are real. It has no ActorGeneration, however, and the host sustains the override toggle: native script revocation can therefore be followed by host re-enabling a new lease on a later tick. This is a policy interaction to decide explicitly, not proof that every script write must permanently cancel the viewer reward. Role expansion also needs alternate-role motion/controller/resource proof; current Motion ActorReady is Sora-only. Bind generation and report lease status to the host before treating this as solved.

### F06 — Other restoration mechanisms have different ownership domains

- HP/MP/target/save/menu actions are one-shot; they do not retain old actor originals. Their races concern command-time target or save read-modify-set, not delayed actor restore.
- Regeneration and full MP restore bridge booleans and resolve the current actor on native ticks. FieldPlayers health support already has dedicated proofs. Manual same-value policy ownership remains distinct from actor lifetime.
- Time multiplier, audio targets, brightness, subtitle bits and desktop visibility are global or bridge settings. Value-only comparison can race a manual writer; actor generation would not fix that domain. ColorChaos already compares its full native pair atomically under GX lock.
- FOV/free-camera use native scene leases, but host setting/restore is still a separate read and command. A new same-valued manual camera override can be confused with the reward. Free-camera boolean restore does not capture an entire prior eye/target/up pose.
- Drive rewards have native context/source/task binding for queued transitions, but their host completion/revert decision is not bound to a per-redemption transition receipt. Drive remains Sora-only by design; do not extend through shared save fields.
- Hacker Mode unconditionally hides a shared developer desktop at end; it does not capture prior visibility or a show-owner token.

## Role candidates, in practical order

1. **Global time multiplier (`fast-forward`, `slow-mo`)**: no character-specific native body; existing scene/timing/own-pause controls are the main gates. This is a small FieldPlayers admission candidate with role/transition/deferred-cleanup tests. A shared policy token would be a separate ownership improvement.
2. **Status modifiers** after candidate3's actor/status ownership contract; generic native paths already exist, but role policy must not be expanded before the lease is correct.
3. **Invincibility** after candidate1 repairs the real callback routing and adds generation binding; the identical seven-instruction adapters support a clear three-role design, but call-site and failure-path validation remain required.

Health/MP, movement, color/audio/brightness/subtitles already have FieldPlayers rows. Shared inventory/munny could be useful during Roxas, but they intentionally change the global save and need explicit semantics plus native side-effect review. Drive is not a candidate. No product role allowlist was changed by this audit.

## Verification limits

Only the focused Ghost Walk host fix was built/tested here, in the isolated Twitch fake suite. Native evidence verification reads the original disk PE and IDA exports, not a game process. The broader audit does not claim every native body or every modded resource is understood. No new hook, game mutation, package build, UI action, or live redemption was performed.
