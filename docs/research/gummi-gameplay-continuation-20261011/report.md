# Gummi special-weapon request

The useful next control is **Request special-weapon strike**: one normal input request for the current installed combo, preserving stock and combo timing. A request acknowledgement cannot promise that an attack or projectile appears. The precise implementation proposal and refusal cases are in `contract.md`.

## Findings

The live input branch in `1FE860` checks installation plus input mask `0x1000` and calls `2312B0`. That helper only ORs request mask `0x2` into combo+68. The phase-2 player update calls the combo consumer later in the same update. This is a grounded entry point for a trainer action; duplicate fragments such as `1FF260` have no observed code callers and are not proposed as entry points.

The consumer handles a pulse differently according to state. Phase0 spends one stock and enters phase2; the actual main dispatch occurs on a later update. Phase3 accepts another pulse only at elapsed10..50 inclusive, with no additional stock cost. Every installed update clears the pulse, including too-early requests. A full sequence therefore requires separate accepted continuation requests. Native wait thresholds are `[0,0,10,10,20]`, companion dispatch waits until4, recovery until40; these are native step units. The proposed command rejects other phases, already-pending requests and invalid state instead of changing phase, stock or timers.

The downstream chain selects main parts by stage ID and companion parts by native type3, then iterates their weapon instances. Its endpoint `1F26A0` only sets another request latch for matching instance mode0. It can also clear a byte when mask4 is set. This study does not establish the later resource consumer or guarantee a projectile or hit.

## What is newly established versus reused

The original v0.11 Gummi study already covered installation, charge, stock and broad combo phases. It remains a hash-pinned historical dependency. This continuation freshly captures the whole request-to-consumer chain, resolves real update order and input gating, verifies pulse expiry/inclusive timing boundaries and the distinction between stock consumption, part dispatch and weapon-instance request. Initialization findings are explicitly reconfirmations. Full body capture does not mean every unrelated branch or lifetime is now understood.

The study has 19 complete pseudocode bodies and 25 completed ASM pages containing 1,097 instructions. All 4,583 bytes of IDA function extents and 36 constant bytes match both the original retail executable and the analysis copy SHA256 `9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed`. There are 4,532 instruction bytes and 51 separately retained jump-table/alignment bytes. The 24-byte jump table after `230D20` and the 3-byte alignment plus 24-byte table after `1FD1E0` are not counted as instructions or separate functions.

Capstone independently decodes every captured instruction address. A deliberately limited interpreter executes original bytes for the combo update, request setter and instance latch in synthetic memory, comparing against a separate phase model. It covers exact float32 boundaries, stock/full-latch behavior, sparse stage counts, companion-only state5→6 handling, no-installation early return, native-step accumulation, pulse expiry, a complete five-stage sequence, and deliberately early followups. No retail code is executed. The dispatch-call hooks only record arguments; they do not emulate list/resource ownership.

## Limits and review

The current Gummi context gates establish the current module/player and the setter's inline storage. They do not prove every future companion/part/weapon-instance pointer or its resources. The proposed action is therefore a scalar request under the normal native update, with explicit future-consumption uncertainty. A stronger guarantee of successful downstream execution requires fresh allocation/list-writer/lifetime analysis. No native dispatcher is proposed as a shortcut.

The decompiler omits companion RCX arguments and invents extra parameters for the combo update/timer getter. Actual ASM loads and callsites are authoritative. All ten canonical claims are deliberately narrow and have resolvable `functions[addr=...]` witnesses. Supporting captures and duplicate fragments do not create additional claims.

No product files, IDB state, game process, saved game, package or release were changed. This is a reviewable research/proposal artifact, not a built trainer feature.

## Reproduce

With Python3 and Capstone5 installed: `py -B artifacts/gummi-gameplay-continuation-20261011/verify.py`.

Outputs: `evidence.json`, `verification.json`, `model-results.json`; raw unmodified tool result objects are under `raw/`. The verifier compares deterministic outputs and the exact recursive manifest. The original game and analysis copy are read only. `dependencies.json` identifies unchanged historical inputs; `context.json` records the product snapshot and currently unused slot485 at proposal time.
