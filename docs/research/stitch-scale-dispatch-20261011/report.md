# Stitch scale reset: a concrete dispatch route

The previously open virtual-slot caller is now identified. BDX bank **10:4** reaches `5364B0`, which double-decodes its Actor operand, reads the Actor's personality at `+3576`, and tail-jumps through virtual `+80` at **5364D5**. For the original Stitch vtable this selects `1C7E00`, the already established cached-Actor scalar reset. Bank **10:3** selects virtual `+72`, the Stitch setup path.

The captured factory supplies the object provenance: type **200** selects the Stitch constructor, passes the Actor/resource arguments, and publishes the personality at Actor+3576. Original RTTI and vtable bytes independently support the Stitch identification. These are conditional static routes; no retail script execution was observed.

## Callback lifecycle

Setup installs `1C7BF0` in the context Actor's `+4000` field. Reset clears that field. A second concrete BDX route, **7:26 → 53FA00 → 1B2870**, tail-dispatches this callback with the low32 action argument. The ASM shows that second argument even though the decompiler omits it from the call expression.

The callback selects member-descriptor keys for actions 525–527, clears the current-record pair at Actor+3816/+3824, and then dereferences the selected record without a local null rejection. The original image has zero function pointers in the seven recorded Stitch action rows. **Their runtime initialization remains open.** This study therefore does not claim that these actions can safely be triggered.

## What this changes for Tiny/Giant

The native reset writes `1.0` even if the scalar already holds `1.0`. A value-comparison journal alone cannot detect every occurrence of this native takeover. The dispatched Actor's context and the cached Actor receiving the scalar store can differ. Any future ownership rule needs the relevant context/cache identity and a boundary before the next consumer; this study does not establish that boundary or authorize a scale feature. It does not justify excluding every summon.

The inspected cleanup routes select virtual slot0 or slot+8. The original Stitch entries are the separate destructor and a RET0 body. This is a local distinction, not a guarantee about all transitive teardown behavior or reset-before-free ordering.

## Evidence and reproducibility

- 15 fresh complete IDA bodies: **590 instructions / 3,058 recorded bytes**.
- Five clearly marked reused bodies: the Stitch constructor, setup, reset, destructor and cached-Actor accessor.
- Original bytes independently compared against SHA256 `9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed`.
- The factory's recorded extent includes **281 noninstruction bytes**: a NOP alignment byte and two switch tables. Complete ASM pages cover its executable instructions; the full original span also retains the tables.
- **6,083 checks**, **513 synthetic cases**, **14,887 interpreted original instructions**, and **1,366 audited flag consumers** pass.
- `priorwork-overlap.json` records overlap in the exact inventoried evidence arrays. Fresh capture does not imply global novelty.
- `parser-check.py` uses the existing coverage parser only for reference resolution, complete-ASM validation and original-PE comparison. It does not update coverage.

Run from any directory within this repository layout:

```powershell
py -3 -B artifacts/stitch-scale-dispatch-20261011/verify.py --check
py -3 -B artifacts/stitch-scale-dispatch-20261011/parser-check.py
py -3 -B artifacts/stitch-scale-dispatch-20261011/check-manifest.py
```

The model executes decoded original instructions with explicit helper stubs. Synthetic memory returns zero for unspecified bytes; this is not a memory-safety model. Factory tests start at its type-selection block, with captured-prologue register premises; allocation and constructors are stubs, and resource-table contents are not validated by those cases. Callback selection tests stop before the unchecked record dereference. The lookup and pre-cleanup claims are static ASM checks. Flag consumers along executed paths are checked against modeled producers; this is not a general x64 emulator.

Exploration files are candidate discovery only. Raw opcode matches and linear disassembly do not prove object identity, callsite completeness or absence of other callers. The initial ModelMulti virtual-slot candidate was not identified as Stitch and contributes no claim.

The existing lifetime IDB was adopted explicitly without autoanalysis or mutation. Its readiness flag was false, so all claimed spans additionally rely on complete captured pages and exact original-PE checks. No game process or native game function was run. The study changes no product, docs or package files.

Remaining work is bounded: locate actual script users and action-record initialization, then combine the dispatch/context evidence with the independent scheduling and resource-binding studies. No all-writer, allocation-lifetime, concurrency, playback or live-feature guarantee is asserted.
