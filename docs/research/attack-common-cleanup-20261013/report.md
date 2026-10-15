# Attack common cleanup and allocator boundary

## Result

When contact+8 mask `0x400` is clear, the selected destruction path clears collision references and recycles its ID. With deletion mask `1` set and mask `4` clear, a matching regular allocator then destroys the old allocation. The inspected local bodies do not repair the external manager cell or publish its replacement. The alternate size-728 release target is a three-byte `RET 0` function.

This extends the earlier slot-reuse result with four fresh complete IDA bodies: `3BF4F0`, `3D2E50`, `3CF3A0`, and `031DD0`. Seventeen complete bodies are reused and checked again against the same original executable. None of the reused bodies is presented as a newly discovered function.

## Concrete chain

1. `40F4C0` loads `QWORD attack+720` and writes zero through it, then calls base cleanup `3CFB10`. That external-cell store has already happened before any cleanup described below.
2. Base cleanup decrements the two nonnull Actor references, unlinks the contact from the `2A24B40/48` list using packed next at contact+196, and clears that next field.
3. Unless contact+8 mask `0x400` is set, it sweeps selected Actors. `3BF4F0` starts at head `2A171C8` or advances through packed Actor+2704. It excludes Actors whose +288 field intersects `0x10080000`. `3D2E50` additionally requires +1736 mask `0x2`. This is a filtered sweep, not proof of cleanup for every Actor.
4. For those Actors it clears the contact's ID bit in the bitmap passed at Actor+3224. It clears Actor+3320 only when that QWORD equals the dying contact. It also clears the ID bit in other contacts' tables. This pointer-identity check concerns Actor+3320, not the external manager cell already cleared by the derived destructor.
5. `3CF3A0` clears `1u << (id & 31)` in the DWORD at `2A24AD0 + 4*(uint32(id)>>5)`. Both this helper and `3CF7F0` lack local ID bounds checks.
6. Base cleanup always removes its embedded node at contact+60 from the separate `2A24AC0/8` list through `3CF190`. The latter's packed next at node+80 is contact+140.
7. Only if deletion flags include mask `1`, the derived destructor selects a release branch. Without mask `4`, `152570` dispatches through the current allocator's virtual slot+16. With mask `4`, it calls `031DD0(this,728)`, which only returns. Mask `4` alone enters neither branch.

## Regular allocator: what is reclaimed

The original table at `5B2BB0`, installed by `19C3A0`, binds allocation slot+8 to `19C2B0` and free slot+16 to `19C470`. Both forwarders use the allocator currently in global `9BA920`; the free forwarder does not recover it from the block header. These findings apply when allocation and release use the corresponding valid allocator instance.

The selected manager requests 728 bytes at `3D26A0`/`3D26AE`. `19C2B0` rounds that to 736 bytes, adds 48 bytes of block overhead, and returns header+32. The resulting block size is 784 bytes. `19C470` unlinks the block, updates accounting, fills the entire 784-byte block with DWORD `0xEFACCAFE`, and then zeros header+8. The old object's +720 pointer lies inside that fill range. This destroys the old pointer storage; it does not repair the separate owner cell previously cleared through it.

The pre-unlink helper `3A08F0(header,end)` does not use its two incoming bounds. It walks head `2A0D628` through each node's first packed DWORD until null. Its body neither compares those bounds nor invokes a per-node callback or writes a traversed node. The decoder may initialize the global pointer-region table; its CRT guard calls are explicitly outside this study. Semaphore calls around allocation/free are also outside this local ownership result.

## Limits and next boundary

- This is static analysis of selected complete original bodies. There was no native execution, semantic emulator, game test or modification of game state.
- Valid allocation headers, list membership, IDs, pointer encodings and nonoverlapping allocations are required. Unchecked bitmap indices are not safe for arbitrary input values. Neither list remover is established as idempotent.
- The allocator binding is conditional on the current global allocator and unchanged original table. Other implementations and global changes are not covered.
- The stored manager cell lives outside the old attack allocation. Whether and when its owning Actor is destroyed is a separate lifecycle question being studied by the parent agent. This report does not claim a universal dangling-pointer failure or a real game crash.
- Complete local bodies do not imply closure over all transitive CRT/OS helpers, all callers, or all writers. A lack of a cell-repair sequence here is not proof that none exists elsewhere.

## Verification and provenance

`verify.py --check` compares complete bodies and the original allocator-table bytes against PE SHA256 `9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed`. It independently decodes each captured instruction head with Capstone, checks sizes and mnemonic aliases, retains the four unlisted padding bytes in the reused pointer initializer, and verifies all structured claim references. This is byte/boundary verification; the field and control-flow claims were read manually.

Exact counts are in `verification.json`: 4 fresh bodies / 44 instructions / 142 bytes; 17 reused bodies / 550 instructions / 2,068 bytes, including 4 unlisted padding bytes. Total: 21 bodies / 594 instructions / 2,210 bytes, plus 24 data bytes and 39 instruction anchors. The eleven semantic claims do not imply eleven newly analyzed functions in global coverage.

Root captures remain in `root-capture/`. `evidence.json` records each reused source and its whole-file SHA256. The companion `report.json` contains bounded per-function claims and resolvable evidence references. No product source, docs, coverage or release package was changed.


## Documentation import and independent review

The frozen source study and review are preserved byte-for-byte in `evidence.zip`, including their manifests. `provenance.json` pins every archive member and maps every normalized body to its archived original record. Stored IDA lines are wrapped as one complete page and original bytes are spaced for the existing coverage parser. No new capture, runtime behavior or complete-semantics claim is added.

This document contributes 11 bounded per-function claim records and 0 separate range findings, backed by 21 complete bodies. Global coverage deduplicates function addresses against prior work; these record counts are not counts of newly understood functions. Run this folder's `verify.py --check` for read-only archive, original-byte, normalization and reference checks. The archived author scripts retain their original paths.
