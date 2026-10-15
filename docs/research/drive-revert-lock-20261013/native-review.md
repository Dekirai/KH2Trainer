# Native Drive Revert lock review

**Accepted for the supported original build, with no remaining actionable native findings.** This is a review of the native lock and its integration. It is not a live-game test, a managed reward-engine review, or a claim of unconditional cleanup in a modified game.

## Evidence and source binding

- `source-and-pin-audit.json` records exact SHA256 hashes and byte lengths for eight reviewed source files. The `sources/` tree contains those byte-exact sources.
- The four production code pins, totaling 1,068 bytes, match the original executable directly. Original SHA256: `9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed`.
- The earlier independent original-PE/IDA evidence verifier was rerun successfully. Its four function bodies contain 342 instructions and 1,385 code bytes. The availability checker tests root-row WORD+44 using the actor's form index; command kind5 reaches that check. Mask0x7E therefore blocks forms1 through6. The direct native type5 dispatch still calls `40CE60(actor,0)`.
- Reproduce this source/pin binding without changing artifacts: `py -3 -B artifacts/review-drive-revert-native-20261013/audit.py --check`.

## Implementation assessment

1. **Bounded current binding.** Every scan uses the currently published System BAR and command-table global. The BAR allocation is restricted to the original image arena. Its allocation header, BAR header, first command entry and installed pointer must agree. The command table has a positive bounded count of 48-byte rows, strictly increasing IDs, and a terminal id5/kind5 row. The retained binding includes addresses and relevant header/entry/root bytes, with only the mask excluded from the row comparison.
2. **Ownership and writes.** Acquire changes only the aligned two-byte form mask. It stores which bits it actually added and requires a nonzero exact owner token and independent bridge nonce, encoded as uint32 halves. New acquisition requires the genuine update thread, fresh host, stable normal Sora scene and all code pins. A different owner cannot acquire. Its release is an acknowledged no-op. Another bridge nonce is rejected. Compare-exchange prevents overwriting a racing mask change between reading and writing that mask.
3. **Cleanup.** Release revalidates the current binding before reading or writing the row. It never follows the retained old row pointer on its own. Only an unchanged expected mask in the same binding may be restored, and only the added bits are removed. Unreadable, missing or read-only bindings retain state2 and the owner for retry. A verified foreign binding or mask is left untouched and the old lease is forgotten. Cleanup does not depend on an actor, usable scene or a fresh heartbeat.
4. **Frame integration.** `TrainerFrame` calls `DriveTick` outside its fresh-host block and before snapshot throttling. Thus later expired-host frames continue trying pending cleanup. Reset/DisableAll and the existing best-effort failure-reset path call `DriveReset`. Snapshot publication exposes state and owner/bridge halves coherently through the existing protocol. An idle lock performs no table scan.
5. **Drive behavior.** The lock survives the ordinary actor replacement caused by transformation. The trainer's direct native Revert and form-switch paths bypass this command-menu availability mask. The mask also blocks examined timer-zero automatic paths using the same native availability validator; it must not be called a manual-menu-only patch.

## Tests inspected

The final compiler/test logs under `artifacts/drive-revert-native-20261013/logs/` report no warnings or failures:

| Suite | Checks | Failures | Relevant scope |
| --- | ---: | ---: | --- |
| DriveGuardTests | 1,746 | 0 | Acquire/release, exact arguments, code pins, preserved original bits, actor replacement, foreign changes, unavailable/read-only data, missing player, host and thread gates, direct Revert |
| DriveRevertBridgeTests | 20 | 0 | Actual production TrainerFrame and command dispatch, coherent pending snapshot, read-only to writable cleanup after host expiry, missing binding recovery, foreign owner/nonce and idempotent release |
| PlayerBridgeTests | 671 | 0 | Broader bridge routing and capability regression checks |
| GummiRequestBridgeTests | 15 | 0 | Broader bridge routing and capability regression checks |

These are private-memory tests. The permanent integration suite uses the production packed-pointer decoder with a populated region table. Its lease is explicitly seeded to test teardown/dispatch without constructing Sora or calling game code. Acquisition is separately exercised by DriveGuardTests. The earlier invalid artifact-harness draft is not used as passing evidence.

## Resolved findings

- `DriveReset` now names its context parameter before passing it to cleanup.
- A release from another owner now succeeds without changing the current lease, matching the cleanup protocol.
- The additional permanent integration test verifies repeated expired-host frames, rather than relying only on direct calls to `DriveTick`.

## Limits

The image-arena restriction and binding checks do not prove absence of an undetected in-place ABA replacement or arbitrary concurrent mod writes. Conservative foreign-change handling may leave mask bits behind; there is no release guarantee for a modified table. On permanent bridge disable, `OnFrame` returns early: only the immediate best-effort failure reset runs, so no later retry is promised if that reset cannot write the table. A direct scripted/native Revert or an action already past availability can bypass this mask. No live game, GUI, injection, Twitch service or save mutation was used by this review.
