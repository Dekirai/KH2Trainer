# Color Chaos: paired conditional restoration

## Result

Color Chaos now restores only the color mode and strength that it replaced. It
does not call `display.restore_loaded`, change brightness, or write configuration.
A native compare-and-apply operation closes the race between the last host
snapshot and a restore command: an externally changed pair is preserved and
releases the effect's ownership.

The earlier readiness note said color readbacks were absent. That was inaccurate:
Render slots 193 and 194 already exposed the two fields separately. Their
unlocked diagnostic samples do not establish a coherent pair. They remain
unchanged. New slot 465 captures one pair under the existing display lease and
mutex and encodes it as `mode * 16 + severity` in a single exact integer value.

## Fresh evidence

The existing renderer IDA worker was adopted as session `ab850630`; its health
reported automatic analysis, Hex-Rays and string caches ready. No IDB mutation,
save, extra worker, game process or UI operation was performed.

`native_evidence.json` contains complete addressed ASM and IDA bytes for six
bodies. `native_full_pseudocode.json` contains full cursor-complete pseudocode;
the compact previews inside the former file are not claimed as full decompiles.
`verify_original.py` checks all body bytes against the installed retail executable
and checks instruction counts/cursors. All 662 instructions and 2,906 captured
bytes agree with the original image, SHA256
`9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed`.

| Native address | Finding |
| --- | --- |
| `0x140125D00` | Copies ECX and EDX to the singleton's DWORD fields +23364 and +23368. It writes neither brightness nor configuration and contains no locking. |
| `0x1405061F0` | Preview wrapper uses signed 16-bit CX/DX. Mode 0 becomes (0,0); enabled strength is clamped to 1..10. The bridge separately validates mode 0..3. |
| `0x140506240` | Loaded-color restore reads Settings+16/+18 and normalizes strength. These loaded settings are a different source from the current preview, so they cannot stand in for the effect's original pair. |
| `0x140505D00` | Applying all settings separately applies brightness, color, window/framerate, controller, and audio state. It is deliberately not used for ownership restoration. |
| `0x140111AE0` | The final pixel-constant block starts at GX+23300 and has 80 bytes. The mode and strength are offsets +64/+68 within that block; its memcmp/upload path notices changes without an extra dirty-flag or refresh call. |
| `0x14011C150` | Native singleton initialization is guarded by CRT/TLS state. The bridge preserves its existing initialized-lifetime gates; the TLS guard is not treated as a renderer generation counter. |

## Native contract

Existing `DisplayHandle`, `DisplayCapabilities`, and `DisplaySnapshot` cover the
new entries; no new CommonBridge dispatch call is needed.

- **464 / command 1464**, `display.color_compare_apply`: five integer arguments:
  operation (0 Apply, 1 Restore), expected mode, expected strength, new mode,
  new strength. A pair is canonical only when it is (0,0), or mode 1..3 and
  strength 1..10. Invalid numbers/pairs/null arguments are rejected before locking.
- **465**, `display.color_state`: read-only packed canonical pair. Zero is a valid
  disabled filter. Missing validity means unavailable, never disabled.

The operation reuses the original display application-thread, heartbeat, singleton,
device/root, app/timing-thread, code-byte and runtime-import guards. It captures
the existing GX+30848 mutex and verified runtime lock/unlock targets, acquires it,
then revalidates the lease. Comparison and the single native color call happen
inside that same critical section. The captured unlock is always used. Failed
unlock latches the existing shared display fault and prevents further operations.
The coherent snapshot is published only after successful unlock.

Apply mismatch returns refusal without a native setter call. The existing effect
engine may retry Start with a fresh observed original. Restore mismatch returns
success without a write: the external pair wins and the effect ends. Invalid
current native pairs are refused, rather than interpreted as normal disabled
state. Neither mismatch path calls brightness, a loaded-settings getter, or a
refresh helper.

## Twitch behavior

Start requires the coherent snapshot, then chooses a full-strength mode different
from the current filter. It captures ownership only after the native application
succeeds. End submits the matching applied pair and saved original. Native
unavailability or control loss leaves cleanup pending; an acknowledged mismatch
finishes it. Repeating a completed End is inert. The effect keeps its existing
role permissions and pause behavior. EffectEngine and EffectModel were not changed.

## Tests and limits

An independent read-only review by the PE/native agent found no remaining blocker
in the paired comparison, captured lease/unlock, coherent publication or Twitch
ownership settlement. It confirmed the source/test fingerprints and did not run
another build; the counts below are the author's runs.
The saved review is [drive-color-independent-review-20261007.json](../drive-color-independent-review-20261007.json).

- Native `DisplayGuardTests`: **21,140 checks, zero failures**; production branch
  compiled with `/W4` and no warnings. All 31 canonical originals × 31 destinations
  are covered for both operations, along with disabled zero, malformed arguments,
  current-pair corruption, races at lock acquisition, shutdown/lifetime/heartbeat
  failure, lock/unlock failure, and setter exception cleanup.
- Twitch suite: **1,096 checks, zero failures** at this checkpoint. New tests cover
  exact restoration, mode-only/strength-only external changes, stale host start
  and restore observations, missing readback, pause/retry, repeated End, unchanged
  brightness, and no loaded-restore call. See the saved logs; these are synthetic
  tests and not live visual confirmation.

This is conditional value ownership, not a native write observer. An external
writer that restores the identical pair before comparison is indistinguishable.
Likewise it is not a cross-process or renderer-generation token; existing lifetime
checks validate each operation. The mutex and application-thread contract cover
the supported original engine paths, not an arbitrary uncooperative mod writing
the same memory concurrently. No claim is made about unrelated renderer color
grading constants or frame-exact observation. These limits do not require a
blanket reset: observable pair changes are now preserved atomically.
