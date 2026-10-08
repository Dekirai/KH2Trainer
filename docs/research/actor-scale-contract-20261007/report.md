# Actor uniform-scale contract

**Result:** a bounded positive write to Actor+60 is a credible basis for a future Tiny/Giant effect on coherent Sora, Roxas and Mickey. This round implements no effect. The generation journal can supply Actor lifetime identity; attachment and native transform changes still need explicit product handling.

## What changed from the previous investigation

The previous round found the constructor and transform reader. This round identifies a concrete **indirect writer mechanism**. BDX bank1/trap3 (`42B230 -> 3B3E80`) returns the current Actor as a packed `@ADR`. The interpreter `41B400` can add a signed byte offset to an address, re-encode it and store a raw DWORD or block through that pointer. Helpers `41C6C0/41C840/41C900` manage VM tags/ranges; they do not protect native Actor fields. Consequently a script can address Actor+60 without a named scale setter.

This is proof of native capability, **not proof that a particular shipped script writes +60**. Retail scripts were not exhaustively searched or executed. The additional displacement scan covers only its recorded interval and cannot establish exclusive ownership. The related vector setters `3B64D0/3B6510` write position+1648, not scale.

## Exact transform and collision behavior

At `3CCD46..3CCD8C`, the game computes `float32(ramp2732 * scalar60)`, multiplies the four-float vector at+48 by it, overwrites the copied W with1, and uses `1AA7D0` to multiply three basis rows by the XYZ results. The temporary W contains scalar*(ramp*scalar), but it is discarded before basis scaling. Matrix multiplication `13F900/13F850` later uses all four lanes and ordered float32 products/sums. Finite inputs alone cannot prove finite results. Normalization `142080` also squares and sums its inputs without a NaN/Inf guard.

The common path publishes Actor+64 and+2056. Motion evaluation receives the latter; `1A4D40` copies it into model+696 before native motion/model work. These are shared transforms. Attached weapons and other children can inherit the parent/joint transform. A custom transform callback flag (+1736 bit0x08000000) introduces another consumer and should be excluded from the initial feature.

The earlier collision evidence remains decisive: joint-derived centers change, while resource radius/height and world-collision radii remain separate. New full evidence for `3CD220` shows that floor alignment derives a basis from transformed collision/contact information and then reapplies the same scale factors. Thus the label should be **transform size with joint and collision-center effects**, not a promise of proportionally resized collision volumes. Neither +2732 nor any radius is proposed for writing.

## Real synchronization boundary

Motion rebuilds can run on native workers. `3BEEC0` queues `3BF4E0 -> 3BFAB0` via `12FDB0`. Worker `130030` drains its callbacks, then signals its completion semaphore. `130130` waits all six completion wrappers and returns their tokens; `3BEEC0` calls it before ending the batch and returning. This closes the normal-return worker-lifetime gap in the earlier scale analysis.

The Actor task is installed by `3BF810` and dispatched through `3BF550/14FC20/14FD60`. The application update dispatches its outer manager before returning. Current TrainerBridge calls its frame work after the selected original update. A future commit belongs at that existing boundary, with the original code/callback contract intact. It must not invoke motion evaluation to refresh a display or write during a queued job. Native wait failures are not explicitly checked by this code, and third-party worker replacements are not covered.

## Proposed bounded feature

The machine-readable [contract](contract.json) records the proposed policy and required tests. A conservative first subset uses absolute scalar0.5 for Tiny and2 for Giant, with original/candidate restricted to a small positive interval such as0.25..4, native XYZ and ramp still at unit values, no parent attachment, valid normal control, coherent role and exact observed Actor generation. Those numbers are a proposed product policy, not a clamp or proven gameplay-safe range from the binary.

Validate original and proposed projection in native float32 order immediately before a four-byte commit. Do not modify XYZ, ramp, position, flags, collision radii or saved progression. Let the next natural motion update consume the value. Sora/Roxas/Mickey eligibility follows the existing coherent role proof plus their common Actor-transform path, not a bare character ID.

## Ownership and transitions

`3D9FE0` attaches an Actor by changing its parent/joint/flags, local position/orientation, descriptor mode and render-child links. `3DA250` removes that relation, restores world-space state, can run an optional BDX callback, and rebuilds the transform. **Both preserve scalar+60.** A current Actor can therefore keep its lifetime identity while its projection context changes.

A future timed effect must capture the original once, pin the generation, preserve mutation receipts through ACK recovery, and never transfer originals to a replacement Actor. Scalar mismatch relinquishes ownership. Actor retirement means no write; observer failure means uncertainty. Field/current/role/attachment/XYZ/ramp changes stop normal application and require fresh cleanup validation. In particular, an old original must not be restored blindly under a new parent or native scale tuple.

Frame-only checks cannot detect every attach/detach interval or a same-value native scalar write. The generation observer does not solve those distinct cases. The implementation must document deferred cleanup or relinquishment when current context cannot safely support a restore; unconditional restoration is not established. No new attachment hook is introduced here.

## Evidence and limits

[report.json](report.json) contains59 narrow address claims. [evidence.json](evidence.json) contains59 complete dedicated ASM bodies,4,370 instructions,18,300 original function bytes, and3 original data spans totaling48 bytes. [verification.json](verification.json) confirms equality with the unchanged retail EXE. [verifier-tests.json](verifier-tests.json) records76 checks and0 failures, including malformed-evidence rejection. Repeated prior bodies are not new full semantic reviews; exported code is not a claim of whole-program understanding.

Run `py -3.13 verify.py --exe "path/to/KINGDOM HEARTS II FINAL MIX.exe"` and `py -3.13 test_verify.py` from this folder or by absolute script path. Only these static evidence checks ran. No product change, complete build, live game, UI, save or IDB mutation occurred.

