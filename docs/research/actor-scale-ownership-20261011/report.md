# Actor uniform scale: ownership and attachment boundaries

## Result

A later native path directly overwrites Actor+60 with 1.0. This is the Stitch vtable +80 body at RVA 1C7E00, using the Actor returned by cached-player accessor 1B4B70(0). The store occurs at 1C7E49 even when the prior value was already 1.0. The cache has concrete writers from CurrentPlayer, but its identity and freshness at every later use remain unproved.

Two additional concrete boundaries matter for a future Tiny/Giant feature:

- BDX trap bank1/index18 calls native attachment and can install a stored VM context, callback ID and argument. Bank1/index102 calls native detach. The reused detach body can run that callback after clearing the parent field.
- Native paths 402FE0 and 403CC0 can add a child to an Actor without locally checking whether that Actor has a parent. An unparented Actor can therefore still have attachment-dependent behavior.

These findings do not approve a runtime scale write. They identify transitions that an ownership policy must handle.

## What was captured

The study contains 16 fresh complete IDA captures: 4,233 bytes and 942 instructions. The predicate 3DA520 is an explicit repeat from earlier evidence. The other 15 addresses were absent from the exact prior evidence function arrays recorded in priorwork-inventory.json; this is a bounded inventory check, not a global novelty claim.

The earlier complete bodies 3D9FE0 and 3DA250 are reused with their source hash and original-byte verification. Together the evidence covers 18 bodies, 5,419 bytes and 1,204 instructions. Fourteen canonical claims are in report.json.

The constructor/vtable/COL/type-name chain identifies kn::Stitch. Its slot +72 configures the cached player and two child slots; slot +80 performs the scalar reset and local cleanup sequence. The first vtable cell is a separate destructor-like body. **The actual virtual callsite invoking +80 is not yet identified.** The study does not turn this table association into a proven retail invocation or timing claim.

## Verification

Run from either an artifacts or future docs/research location:

```powershell
py -3 -B artifacts/actor-scale-ownership-20261011/verify.py --check
py -3 -B artifacts/actor-scale-ownership-20261011/parser-check.py
```

The author verifier checks the exact original executable SHA256, all captured IDA bytes against the PE, contiguous Capstone instruction boundaries, complete ASM pagination, pseudocode pagination, reused source pins, 70 selected instruction anchors, 333 positive encoded references, trap descriptors and the Stitch RTTI chain.

It also interprets 1,171 synthetic cases through original decoded instructions, totaling 63,850 executed instructions. Cases cover the complete local Stitch reset body, BDX adapters, reparent wrapper, cache updater/accessor, parent predicate, conditional detach and two native child-attachment paths. They include scalar bit patterns, distinct context/cache Actors, child-slot masks, saved flags, tagged operand high DWORDs, callback enable values, and cache pointer transitions.

**The interpreter uses explicit helper stubs and synthetic memory that returns zero for unspecified bytes.** It is not a memory-safety, pointer-validity or full native-call simulation. Arithmetic flags are partial: every executed condition is separately audited. All 4,968 Jcc/CMOV/SETcc consumers have a valid modeled local flag producer; calls, INC/DEC, shifts and IMUL invalidate unmodeled flags for this audit. No branch relies on those unmodeled flags in these cases. The VM was copied from the separately reviewed header study (source SHA256 588c40202fa54391fe8eb6c989b681ff9e7137caea2e8d3324e2d32635f80ba4) with local MOVAPS/MOVSD, CMOVE/CMOVNE and trace support.

Result: **17,094 checks passed**. The unchanged coverage parser separately resolves all 45 claim references and accepts all 18 complete ASM/original-byte bodies. This is author validation pending independent review.

## What remains for Tiny/Giant

The existing numeric scale contract, post-original update boundary and offline motion parser/evaluator are already established in earlier studies and are not repeated here. This study adds native writers and context transitions; it does not solve these remaining handoffs:

1. Locate the actual Stitch +80 invocation and its execution context before using a Summon exclusion rule as proof.
2. Provide a runtime snapshot of the effective motion bytes, length and binding/context revision. A valid offline parser alone does not establish native resource lifetime.
3. Define attachment/child context changes and stored BDX callbacks in the ownership policy. Actor+1696 being null is insufficient by itself.
4. End a future scale journal's ownership when native code takes over. Reusing movement_tx's external-value recapture as a new original would not meet that rule.
5. Handle same-value native writes through a verified context policy. Comparing the scalar alone cannot reveal the unconditional unit write.

Collision geometry and Gummi/mission work belong to separate studies. No all-writers, all-threads, lifetime, race-freedom, visual-result or live-playability guarantee is made. No game, GUI, injection, IDB mutation, product or package change was performed.

## Files

- capture.json and capture-xrefs.json: fresh read-only IDA results using adopted session 2788299e.
- data-capture.json: original vtable, RTTI and trap-table data.
- evidence.json and dependencies.json: normalized complete bodies.
- report.json: canonical bounded claims and limitations.
- verify.py, vm.py, model-results.json and verification.json: original-byte and synthetic validation.
- parser-check.py/json: compatibility with the existing coverage parser.
- exploration.json and original-slot80-candidates.json: exploratory observations, not additional complete-body or absence claims.
- manifest.json: frozen study file pins, excluding itself.

