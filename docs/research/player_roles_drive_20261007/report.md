# Player identity and Drive safety review — 7 October 2026

## Result

The reported case is a **not-yet-unlocked Final Form with an empty offhand**.
The current source already contains the second-Keyblade repair introduced in
the earlier Drive hotfix. Existing regressions cover locked forms1/4/5 with empty
offhands and a valid primary Keyblade. An additional regression checks unlocked
Final with the same empty offhand, so both unlock states are covered. In both
cases the fallback is assigned before the native transition, and the simulated
native weapon consumer receives a non-null weapon. These tests passed.
It would be inaccurate to claim that the reported live crash has been reproduced
or that this source was previously missing that fallback.

This change adds a shared read-only player classifier and strengthens the Drive
boundary. Drive requires coherent Sora identity; a selected model must also be
a Sora model for the requested form. A completed native Revert that yields Roxas,
Mickey or inconsistent player data cancels the remaining trainer step. The game’s
already-running transition is never cancelled or freed by the trainer.

## Native identity

The fresh IDA evidence contains 17 complete native bodies, 776 instructions and
3,168 original PE bytes. `verify_evidence.py` checked all bytes against the exact
EXE SHA256 in `verification.json`. The retail object table was decoded read-only
from its installed HED/PKG entry and exactly matches the local object reference.
The verifier includes its exact MIT-licensed reference under `reference/`, checks
that file's SHA256 and parses only the constant table as data. It executes no
reference-source code and needs no old workspace. Pass `--game-root` on another
installation; the optional OpenKH loose-file comparison is skipped if absent.

| Supported role | Object character ID | Descriptor RVA | Current form |
|---|---:|---:|---|
| Sora | 1 | `750300` | 0 through 6 |
| Roxas | 14 | `750300` | 0 or 10 |
| Mickey rescue | 4 | `7523B8` | 11 |

`3B5B20` reads the actual character ID from the current object entry WORD+76.
`3A7A40` passes it to the status allocator/lookup, then sets the status backlink.
`3A7CB0` routes ordinary player construction to `405030`; it sets descriptor
`750300` for the normal player controller. The descriptor alone cannot distinguish
Sora from Roxas. `3E60C0` maps character14 to saved character slot1, so the shared
save pointer cannot distinguish them either. `3AA960` explicitly treats ID14
separately, and `3AA4F0` recognizes a Drive Form only for character1/form1..6.

The retail rows independently provide the corresponding model metadata:
object84 `P_EX100` is character1/form0; object90 `P_EX110` is character14/form0;
object803 `P_EX110_BTLF` is character14/form10; object91 `P_EX200` is
character4/form11. The distinct rescue constructor `415670` installs descriptor
`7523B8`, initializes the rescue gauge and increments both Mickey rescue counters.
The classifier describes the current actor, not the chapter, elapsed prologue
state or all actors that merely use a Mickey/Roxas model.

## Shared helper contract

`PlayerRoleSupport.inl` must be included at shared scope after `TrainerContext`,
`At`, `Readable` and `DecodePacked`, and before consumers. It has an include guard
through `#pragma once`. `DriveFeatures.inl` also includes it for standalone tests.

`player_role::Inspect(const TrainerContext&)` returns `Info` containing:

- `role`: Unknown0, Sora1, Roxas2, Mickey3 or Other4.
- `characterId`, `form`, `descriptor`, `object`.

The helper performs only reads. It requires the exact current global player,
actor/status backlinks, an allocated 632-byte status record in the 80-slot pool,
a valid complete free-index list and positive bounded reference count. It checks
the entire active actor list for cycles/unreadable links, then checks that the
object record belongs to the current loaded 96-byte object tables. Object
character ID and status+608 must agree. Known roles additionally require the
expected descriptor/vtable, constructor flags and matching object/current form.

Unknown means incomplete/inconsistent identity. Other means a coherent current
common player/status pair outside the supported descriptor/form combinations.
Other is not permission to access a role-specific extension. The caller must run
on the engine thread and apply its own scene, transition, input and feature gates.
The classifier intentionally remains usable during field pause and does not
claim that role recognition means gameplay is controllable.

## Drive and offhand behavior

All six requested forms remain available for supported Sora regardless of unlock
bits, Drive stock or active allies. All 49 current/requested combinations0..6,
including every same-form request, retain the native Revert-then-target sequence.
The suspended-partner array must be empty before the second step because native
cleanup owns that array; this is not a requirement for party members to exist.

For dual forms1/4/5, `PlanFormWeapon` preserves an existing valid offhand. Otherwise
it uses the equipped primary Keyblade only if the item, target Sora object, `went`
model lookup and slot1 `wmst` name all validate. Both tables must be the installed
entries in the actual loaded system BAR allocation, with bounded entry spans.
The plan is read-only; the caller commits exactly the two-byte form weapon field
immediately before native Begin. No item stock, unlock, Drive or main-weapon field
is changed. If no native context was queued, the unchanged owned assignment is
rolled back. A live unexpected native context keeps the valid assignment for
engine cleanup. Successful assignments can persist when the game next saves.

Fresh `3E0CC0` confirms that weapon slot1 for character1/14 reads the form-record
weapon and returns zero when it is empty. `3A7A40` skips offhand construction for
modelID0. `3D7600` passes actor weapon slot+3424+8*slot to `3B5D40`, which dereferences
weapon+2744 without a null-weapon check. The fallback addresses this dependency.
The new source narrows target form identity to character1; merely being a shared
Roxas/Sora save owner no longer makes an arbitrary mapped target admissible.

## Other feature scope

Existing Motion and ActorMovement modules already require status+608==1 and
descriptor750300; coherent Roxas14 and Mickey4 were excluded before this change.
They remain Sora-only. This review does not silently expand their resource or
restore contracts. A generic HP/MP, position, guard, targeting or camera command
must retain its own native data guards; the role helper alone is not proof of
that feature’s compatibility. Root’s separate status-path and GameplayState
reviews own those decisions.

## Validation and limits

`DriveGuardTests` passed **955 checks, zero failures**, compiled with `/W4` and no
warnings. The log is `artifacts/player-role-validation/native-DriveGuardTests.txt`.
The tests execute production role/Drive guards against synthetic memory and fake
native callbacks. They cover all six forms, all49 transition pairs, no unlock/
gauge/party prerequisite, locked and unlocked Final with an empty offhand, exact save-write
bounds, both non-Sora roles, pool/list/object failures, and role replacement after
Revert. The null-offhand probe dereferences the same initial native field and
catches the access violation in the test harness. No game code is executed.

An independent read-only review by `native_debug` found no concrete defect in
the classifier’s allocation, object membership, backlink or role separation.
Root owns the final integration and complete build validation.

No live game or UI test was performed. Metadata checks do not prove that every
external modded model/MSET exists or that all its internal motion/effect records
are valid. A later external writer can replace a validated form record; complete
address reuse between observations has no generation token. No fresh crash dump,
loaded bridge fingerprint or failing live asset state was available in this
review. The latest reported crash remains unconfirmed against this source.
The unlock flag itself does not select or suppress this fallback.
