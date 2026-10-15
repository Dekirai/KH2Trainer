# SCD header profile study

## Result

The twelve new complete bodies provide additional header-reader, streaming and copy-path evidence. None establishes a meaning for file bytes `+12` and `+13`. The observed retail pair `0/4` should remain an explicitly supported profile for the offline inspector. A missing local check does not demonstrate support for other values.

- `07AD30` computes an ID using the header offset, fixed table displacement `+32`, a signed index and a signed file-relative sequence offset. It checks only `SEDB`. `07ADA0` similarly obtains the sequence count.
- `0A13B0` and `0A4020` return header size 16 for version 1 and 32 for versions 2–4. Other values invoke the diagnostic callback and return zero if it returns. This differs from the prior registration gate that permits version zero.
- `0A3590` state 0 has a concrete 80-byte progress threshold, checks both magic DWORDs and requires the three counts at absolute offsets 48, 50 and 52 to equal one. It copies the raw version and length before accepting those counts. It uses fixed offsets in this branch.
- `0A2840` only delegates sequence index zero when flag mask `0x02` is set. The adjacent captured virtual-table cells identify its connection to the prior initializer.
- `0A09A0` sign-extends the declared DWORD length before allocator and memcpy calls. It contains no local null/length rejection. `0A0B00` calls the old-payload cleanup helper before copying a replacement and has no local source-alias rejection.
- `0896F0` and `0918D0` connect provider virtual calls and exact provider-pointer bank reuse to the prior registration routine. A matching bank returns before this wrapper's explicit provider virtual `+64` call.

These are body-local statements with readable input and normal call-return premises. They do not establish valid files, successful playback, safe live modification, every writer or every consumer.

## Capture and verification

The existing adopted IDA worker `2788299e` was selected from a fresh session inventory. `auto_analysis_ready=false` remains recorded; no automatic analysis was forced and no IDB was changed. The input copy is cross-checked against the original retail executable through all selected function bytes.

Twelve fresh complete bodies contain 4,242 bytes and 1,053 instructions. Three prior bodies are separately reused and pinned. The twelve addresses were absent from the function arrays of the 60 exact prior evidence files inventoried at authoring time; this is a bounded inventory, not a global novelty claim.

Every ASM and pseudocode page is preserved. Their offsets, totals and terminal cursors are checked. The MCP pseudocode `truncated` flag also appears on final pages with a nonzero offset, so completion is based on continuous offsets, the total line count and the terminal cursor. The only fresh non-instruction tail is a three-byte NOP followed by the six original DWORD switch targets at `0A3F24`.

The author verifier passes 8,570 checks and 2,382 synthetic original-instruction cases:

| Group | Cases |
|---|---:|
| Header-size partition | 24 |
| Metadata profile-byte sweeps | 1,022 |
| Metadata magic/index/offset cases | 60 |
| Stream sequence wrapper | 1,024 |
| Selected streaming header gate | 240 |
| ToolBank signed length/copy suffix | 12 |

The existing coverage parser resolves all 26 claim references and accepts all 15 complete ASM/original-byte objects. These compatibility checks reuse that parser; independent peer review remains separate.

## Reproduction and limits

```
py -3 -B artifacts/audio-header-profile-20261011/verify.py --check
py -3 -B artifacts/audio-header-profile-20261011/integration_check.py
```

Paths derive the repository root dynamically and also work from a future `docs/research` snapshot. `build.py` and `freeze.py` are authoring helpers; do not run them to check a frozen study.

The interpreter is copied from the earlier independent Upper review (source SHA256 `379fff9925a7898ef9f61af3ef0e5e315b9278fadd3b43c14f7df1a96b0ca52a`) with explicit three-operand IMUL and conditional tail-branch stubs added. It executes selected decoded instructions over synthetic memory, with modeled helper results. Unknown instructions/calls fail. It is a bounded model, not a general x64 emulator or an independent review of this study. No actual allocation, copy, invalid pointer access or native game function runs. The selected paths do not rely on unmodeled INC/DEC arithmetic flags.

The large streaming function is captured completely, but only its stated header/state branches are claimed. Remaining codec states, provider implementation, callback behavior and copy-source alias contracts remain open. Additional ORIGIN payload writers were not pursued because the new header and ToolBank findings already form a useful bounded study.
