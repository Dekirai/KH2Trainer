# Stitch: initialized action records and a retail script witness

Two gaps from the preceding dispatch study are now narrower. Original initializer **RVA0096B0** fills the Stitch action table, and **obj/N_HB040_BTL.mdlx** contains the previously identified setup, reset and action-call descriptors in its stored BDX script. No game process was observed or executed.

## Action-table initialization

The 620-byte initializer is straight-line code. It writes these function fields into seven 72-byte records at **RVA724340**:

| Record | Function RVA | Callback selection |
|---:|---:|---:|
| 0 | 1C7F40 | Not assigned here |
| 1 | 1C8950 | Not assigned here |
| 2 | 1CA6E0 | Not assigned here |
| 3 | 1C8100 | Not assigned here |
| 4 | 1C8610 | 525 |
| 5 | 1C8700 | 526 |
| 6 | 1C8440 | 527 |

The compared key comprises the function QWORD at record+8 and three DWORDs at +16/+20/+24. All three DWORDs become zero. The existing constructor publishes this table and count7; the existing lookup therefore finds rows4/5/6 for the callback's three keys, provided the personality and initialized table remain valid and unchanged.

The initializer also copies an uninitialized high stack DWORD into **record+28** through MOVSD. That field lies outside the compared key. Replaying the original instructions with all256 uniform byte poisons confirms the key's stable values while +28 varies. This is not a complete-record-zeroing claim.

## Startup registration

The verified prefix of **4391D8** calls `_initterm_e` on its state-zero route. After a zero result it calls **471C64** with table bounds **57BCA8..584E18**. Original slot **57D230** contains the pointer to0096B0. The import resolves by name to `api-ms-win-crt-runtime-l1-1-0.dll!_initterm`.

The documented CRT contract traverses a function-pointer table and skips null entries. This supplies the external premise connecting registration to initialization. [Microsoft's `_initterm` documentation](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/initterm-initterm-e?view=msvc-170).

This route depends on reaching that startup block and earlier initialization completing. The loaded CRT implementation, process-entry chain and live table contents were not inspected.

**An IDA discrepancy is explicitly retained:** Original439317 is `8B C3` (`mov eax, ebx`), and an earlier branch targets439317. IDA omits the first byte and records `ret` at439318. The whole startup record is consequently **complete:false**. Claims reference only its independently checked136-byte initialization prefix. Original bytes for its main extent and discontiguous exception chunk are retained; the two genuine NOP gaps are separate. No database repair or autoanalysis was performed.

## Stored retail script

One selected original HED/PKG payload was decoded in memory and compared byte-for-byte with the loose **obj/N_HB040_BTL.mdlx**. The hashes and package coordinates are in `retail.json`. Its BAR type3 entry2, `n_hb`, contains a **7,744-byte** BDX script. The existing event-rooted decoder records **832 instructions** and these five relevant calls:

| Word PC | Descriptor | Immediately preceding operands |
|---:|---:|---|
| 87 | 7:26 | Selector2 address+80, action525 |
| 121 | 7:26 | Selector2 address+80, action526 |
| 155 | 7:26 | Selector2 address+80, action527 |
| 394 | 10:3 | Selector2 address+20 |
| 1041 | 10:4 | Selector2 address+20 |

Selector2 addresses an offset from the decoded pointer in the current frame's slot zero; the captured native address decoder is explicitly reused. It does not identify the +20 and +80 wrappers as the same Actor. The script has syntactic event paths to the three actions and setup from events23/22, and to reset from event22. Such paths include conditional branches and unknown native continuations. They are **stored-code witnesses**, not observed executions, feasibility proofs or matched call/return traces.

## Consequence for scale ownership

The table's original null function fields no longer leave initialization unexplained. The reset adapter also has a concrete stored retail-script caller. Under the previously proved Stitch-object premises, that route reaches the cached-Actor+60 store of1.0, even if the value is already1.0. A scalar comparison alone still cannot identify every native takeover.

The live personality, table contents, wrapper bindings, cached Actor identity, consumer ordering and resource lifetime remain separate prerequisites. This study does not authorize a Tiny/Giant feature, establish safety for arbitrary action calls or justify excluding all summons.

## Reproduction and scope

```powershell
py -3 -B artifacts/stitch-action-initialization-20261011/verify.py
py -3 -B artifacts/stitch-action-initialization-20261011/freeze.py --check
```

The verifier performs **11,300 checks**. Its narrow interpreter runs **2,307 cases / 142,573 original instructions** for the initializer and reused lookup; it does not execute native code. Every memory read in that model requires explicitly mapped synthetic bytes. This fixture rule is not a native bounds or lifetime proof.

Fresh captures contain209 reported IDA instructions and1,024 original bytes across three records. Only the initializer and import thunk are admitted as complete new bodies; the startup record is rejected as complete and contributes the separate136-byte checked range. Twelve bodies are explicitly reused and pinned. Fresh capture does not imply global novelty. The existing coverage parser is invoked only for read-only reference and metadata checks.

For an optional fresh retail comparison, build the isolated `Retail.csproj` and pass the game root and this folder's `retail.json` as the two application arguments. It decodes one selected original payload in memory and writes metadata only. Its four linked Core sources are pinned in `provenance.json`; no product build is needed. `scripts.py` reproduces the stored-script evidence after that comparison. Generated `bin`/`obj` trees are excluded from the research manifest.

Root supplied successful captures through session28e14b48/PID71984 after this agent's supervisor returned stale session2788299e/PID34084. Both tool views are recorded. No new worker, IDB mutation, game action, attachment, injection, save edit, Twitch call or product change was made.
