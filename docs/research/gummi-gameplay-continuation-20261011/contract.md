# Gummi special-weapon request: proposed implementation contract

## User function

Add one action, **Request special-weapon strike**, in the existing **Gummi controls** category. It sends one normal special-weapon input request to the current installed combo. A start spends one stock in the subsequent native update. During a combo, a further click can request the next stage in its native continuation window. It does not replenish stock or repeat clicks automatically. Existing stock, progress and phase readouts are sufficient; this proposal adds no browser or new diagnostics page.

Proposed feature ID `gummi.request_special_attack`, capability slot **485**, command **1485**, `ValueSlot=-1`, `Kind=Action`, no arguments, `RequiresScene=false` (Gummi uses its own scene gates), `ChangesProgression=false`, `CanSaveInProfile=false`. The captured v17 catalog has 361 features, maximum capability 484, and no 485/1485 use. Reserve/check the slot again at implementation time. Protocol v4 already has 512 values, so no protocol-size change is required.

Success text: **“Special-weapon request queued once. The next native ship update decides whether to use it.”** This is a request acknowledgement, not confirmation of an attack, projectile, hit or audible effect. UI descriptions should explain the stock/start and continuation-window rules. No saved profile, automatic retry, replay, toggle or restoration behavior.

## Native entry and its footprint

- RVA `0x2312B0`: `83 49 44 02 C3` — `or dword ptr [rcx+44h],2; ret`.
- x64 ABI: `using RequestFn = void (__fastcall*)(uintptr_t combo);`. RCX is `player+0x1308`; no argument in RDX, no useful return value. The helper has no calls and touches only the four flag bytes at `combo+0x44`.
- Call this setter once on the existing game-thread command route. Do not call the state machine, stage dispatchers, initialization, duplicate extracted blocks, or weapon-instance requests directly.
- Inline combo occupies 72 bytes. The current main ship must equal `player+1160`, have vtable `base+0x5B5238`, and link through main+200 to the same validated `state=player+0x570`.
- Do not change the current state, counts, stock, charge progress, timer, ship pointers, input object or resources. Do not dereference cached objects after dispatch.

## Existing gates and additional validation

Reuse `gummi::HostAndThreadReady`, `BuildContext`, `ActionReady`, and `SameLifetime`: the current base, fresh host heartbeat (at most 5,000 ms), bridge enabled, correct game thread, listed module/vtable, matching module and Gummi heap/scheduler, current player descriptor/state identity/backlink, active module state 1, mission phase 8, player phase 2, finite positive HP and no `playerFlags&0x40010` must all hold. Host command expiry remains the existing 8,000 ms rule.

Do not treat the existing `gummi_extra::ComboReady`/`SameCombo` pair as sufficient for this action. Make an action-specific snapshot that also captures all five counts and the exact float timer bits. Validate each span before reading, including overflow checks for computed addresses. Require:

1. The main identity/backlink above; installed flag `flags&0x1`; no pending request `flags&0x2`. Reject unknown bits outside `0xF` as a conservative trainer policy, not a proven native rejection rule.
2. Stock `0..9`, progress `0..100`, five signed counts `0..1000`, finite nonnegative elapsed time. These are conservative existing trainer bounds, not a newly discovered native capacity. Native timer step at RVA `0x717480` must be readable, finite and nonnegative, and adding it must remain finite.
3. Main-count presence agrees with `flags&0x8`. At least one main stage or one nonnull companion exists. The action must not invent an installation by setting flags/counts.
4. **Start:** phase 0, stock greater than zero, index exactly the first positive main count (or 5 when all main counts are zero). If saturated flag `0x4` is set, require the known full state stock 9/progress 100 before accepting. The normal consumer clears that latch and progress when spending the stock.
5. **Continue:** phase 3, index in `1..4`, count[index] positive, timer **10 through 50 inclusive**. Stock may be zero; continuation does not spend another unit. Do not require saturated stock here. All other phases and inconsistent indices reject immediately.
6. Writable exactly `combo+68..71`; an unreadable/wrong signature or unwritable span must prevent dispatch. No writes during validation.

Capture context/combo/step, verify code, rebuild context/combo/step and compare identity, phase, index, all counts, flags, stock, progress, timer bits and companion pointers. Recheck writable flag span and signatures, then freshly recheck host/base/game-thread/disable before the single native call. A changed sample rejects; no automatic retry. The action's equality should not silently inherit `SameCombo`, which presently omits timer/counts. No pointer is retained across trainer frames.

These guards prove the scope of a scalar request on the current inline combo. They **do not prove the later ownership of every companion, part or weapon-instance pointer**, nor the validity of its resources. The setter itself never dereferences them. The normal update retains responsibility for its ordinary installed-loadout traversal, just as after the normal input branch at `1FEB3D..1FEB6D`. Never claim that readable/non-null companion pointers or matching installation counts prove that whole graph safe. If review requires a guarantee of downstream execution/resource ownership, this study alone is insufficient: capture the `231150` callsite/layout ownership and allocation/removal paths for the lists consumed by `1FBC50`, `1FBCB0`, `22AB00` before broadening the contract. Direct dispatcher calls remain outside this proposal.

## Native consumption and timing

The actual player update `1FD1E0` invokes `1FE860` in player phase 2, then later `230D20(player+0x1308)` in the same branch. `1FE860` requires the installed predicate and input bit `0x1000` before it calls the exact same setter. `1FF260` is a captured duplicate fragment with only pdata xrefs in this IDB, not evidence of an independent live callsite.

| Existing phase | Native response to a request |
|---|---|
| 0, stock > 0 | Spend one stock; if full-latched, clear `0x4` and progress; enter phase 2. No main dispatch in that same update. |
| 0, stock <= 0 | Drop pulse without starting. |
| 1 | Wait for stage-specific timer threshold `[0,0,10,10,20]`; enter phase 2 when reached. A new pulse has no extra effect. |
| 2 | Main stages 0..4 dispatch part IDs `[621,605,606,607,608]`; skip subsequent absent counts; enter phase 3 or 4. Index 5 skips main dispatch and advances to 6/phase 4 (companion-only installation). |
| 3, timer < 10 | Drop pulse. |
| 3, timer 10..50 | A pulse enters phase 1, preserving elapsed time. No extra stock decrement. |
| 3, timer > 50 | Enter phase 5/recovery; no continuation. |
| 4 | Once timer >= 4, call companion dispatch for each nonnull pointer separately; enter phase 5. |
| 5 | Once timer >= 40, reset to phase 0 and first positive main stage or 5. |

With installation bit set, each update adds the native global float step and clears request mask `0x2`. With installation absent it returns without either operation. Threshold units are the native step units; this study does not establish seconds or milliseconds. Changes between the trainer request and the next native update can discard the pulse. The action therefore rejects obvious unavailable states now but cannot promise future consumption.

`1FBC50` traverses all matching main-ship parts by native ID; `1FBCB0` traverses all companion parts whose +1224 field is 3. Both call `22AB00`, which traverses weapon instances and calls `1F26A0(instance,0)`. That endpoint only sets instance+156 mask 1 when instance+144 matches mode 0; if mask 4 is also set it clears instance+148. This is a further request latch; projectile creation/hits are not proven here.

## Mandatory implementation tests

Use a dedicated native guard harness and the actual production translation unit without test hooks. Existing charge tests are historical dependencies, not proof of this action.

- Happy paths: phase 0 with stock 1/9, normal and full-latched state; phase 3 exactly 10/50 and interior times, stock 0 accepted; main and companion-only start. Verify one call, RCX=current combo, only flags OR2 after the call; byte-for-byte unchanged rest of player memory. No post-call pointer access.
- Reject phase 0 empty stock; phase 3 just below 10/above 50; phases 1,2,4,5; invalid phase/index/count relation, unknown flags, bad full latch, already pending bit, invalid ranges, NaN/Inf, overflow from step. Assert zero calls and zero writes.
- Exercise every existing Gummi/host gate, absent/unreadable context and each scalar span, bad main vtable/backlink, writable flags failure, every signature mismatch, second-sample field/context/step change, final host/base/thread/disable loss. No validation may write or call engine functions.
- Prove a request never invokes `230D20`/`1FBC50`/`1FBCB0`/`22AB00` directly or repairs a resource graph. The production route must handle only 1485, advertise capability 485, and never fall through to generic progression writes for a rejected 1485.
- Managed/UI: exactly one action in Gummi controls; empty arguments; transport uses 1485; profile save/load excludes it; no retry/tick; text accurately says request. Existing 324/325/326 readouts and category/navigation stay unchanged.
- Reuse the isolated original-instruction interpreter as static semantic evidence, not as live action acceptance. Add no inflated Cartesian test count for unrelated arithmetic.

## Reproduction

`py -B artifacts/gummi-gameplay-continuation-20261011/verify.py`

The verifier reads the original retail EXE and the matching analysis copy, checks every captured function extent and constant, decodes every captured instruction independently with Capstone, replays a deliberately limited instruction interpreter, and compares frozen outputs and the exact recursive manifest. It never executes original code or touches the game/IDB. Synthetic call hooks record downstream dispatches without pretending to emulate their resource lifetime.
