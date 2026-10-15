# Revert command mask: independent native evidence

Accepted for the narrow command-availability claim. The review does not approve a retained row pointer or its ownership/restore implementation.

## What the original instructions establish

- `3B6CB0` follows command WORD+2 until WORD+0 equals WORD+2. It then zero-extends the root WORD+44, tests the form-index bit with register `BT ECX,EBX`, and returns the result in AL. The native loop has no null or cycle guard.
- `3B68B0` looks up 48-byte rows at table+8 using the signed count at table+4. The table pointer comes from RVA2A161E8. Both indirect calls target IAT57BB80; IDA names that import `bsearch`. Type2 aliases have a separate remapping path. The original first lookup result is dereferenced without a null check.
- At `401FF4`, the availability function reads Actor+3552 and passes it to `3B6CB0`. A true result immediately selects return5. The original switch entry for kind5 resolves to401F3D and joins this ending path.
- The type5 dispatch branch in `405440` calls `40CE60(actor,0)` and then ORs Actor+288 with0x100. That dispatch branch does not recheck the availability mask.

Thus ORing the validated root command 5 WORD+44 with 0x7E makes the availability test true for forms 1 through 6. It does not block form 0, 7 or 12 by itself. It also cannot prevent a direct revert call or an action that already passed availability.

**The mask must not be described as manual-menu-only.** Existing context decompiles of `405320` and `404A40` show paths with Status+436 <= 0 that obtain command 5 and call `3A9EA0`. The latter requires `401D60 < 4` before the caller reaches the revert call. The same mask can therefore reject this automatic path too. These three context bodies are saved separately and have not undergone this review's full ASM comparison. Root and the owner implementer were informed; the natural-expiry policy needs an explicit decision.

## Completeness and method

The original executable SHA256 is `9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed`. Root supplied fresh full IDA queries from existing worker28e14b48/PID71984 because the reviewer's separately enumerated worker was unreachable. No session was reopened. All four full IDA extents match original PE bytes. Each actual code head is independently decoded with Capstone and compared with IDA.

The four bodies contain **342 instructions /1,385 code bytes**, within **1,551 extent bytes**. `401D60` has183 code instructions and166 bytes of alignment/switch data. Its IDA query count186 includes three data directives; these are not counted as instructions. `405440` spans three PE runtime-function records, all covered by its491-byte IDA extent.

The report also checks32 specific instruction anchors, RIP-relative table/IAT addresses and the original kind5 switch entry. Fifteen explicitly synthetic arithmetic cases document WORD zero-extension and modulo32 register-bit indexing. They are not executions of game code or an ownership model.

## Remaining product requirements

Validate a bounded table and the intended row identity5/kind5. Prove the lifetime and native-writer behavior separately before retaining or restoring the row. Preserve unrelated bits and use the separately reviewed ownership/token rules. Reading this mask is not a lifetime guarantee.

Reproduce without modifying artifacts: `py -3 -B artifacts/review-drive-revert-lock-20261011/review.py --check`. The verifier reads the original file, checks all full bytes, code heads, anchors, recorded results and the exact recursive manifest. No product sources, game state or IDA database are changed.
