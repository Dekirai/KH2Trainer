# Native special-weapon request implementation

The new Gummi action handles capability485/command1485 and calls the original five-byte request setter once. It acknowledges only the queued request. Stock use, stage selection and subsequent weapon traversal remain in the native update.

The handler checks the existing live Gummi/player context and an action-specific snapshot of main identity, companions, all five counts, phase/index, progress/stock, flags, elapsed float bits and current native step. It accepts a coherent start with stock or a phase3 continuation at10..50 inclusive. A second matching snapshot, writable flag DWORD, exact code/constants and fresh host/base/game-thread/disable checks precede the call. There is no retained pointer, post-call read, retry, profile replay or direct dispatcher call.

The only owned product edits are `src/KH2Trainer.Bridge/GummiExtraFeatures.inl` and `tests/KH2Trainer.Bridge.Tests/GummiExtraGuardTests.cpp`. The verifier strips exactly the new request block/route/capability and requires the remaining Gummi charge and snapshot code to equal its frozen v17 snapshot byte-for-byte after newline normalization.

All16 signature spans are independently compared with the original retail executable: the setter, actual input/update bodies, combo consumer, installed predicate, timer getter, downstream dispatch/latch bodies and five constant ranges. These are build/semantic guards, not proof of future object lifetime.

## Tests and what they establish

The dedicated Hook-Harness passed **1,087 assertions /0 failures**. The previous v17 suite had492 assertions, leaving595 added assertions for this request and its validation. New cases include all start stages, companion-only starts without dereferencing companion pointers, continuation endpoints and their adjacent float32 values, empty stock/pending bits, every phase, invalid or incoherent flags/counts/index, finite scalar and timer-overflow checks, every new signature and scalar read span, unchanged memory on refusal, context loss, scalar/count/timer/step drift, final host loss, and no post-call reads. Successful calls change only OR2 in the entire synthetic player buffer.

Root independently compiled and ran **GummiRequestBridgeTests:15/0** through the actual `TrainerFrame` dispatch and shipping Gummi route. It uses no Gummi callout hook. The only executed native leaf is the five original setter bytes copied into private synthetic memory; later consumer/dispatch pages are non-executable. That confirms command routing, ABI, byte footprint, capability, endpoint acceptance, refused requests and wire non-replay. Its source and log are copied as context with separate provenance. Root retains ownership of that test and broader managed integration.

These synthetic runs do not demonstrate a rendered attack or sound. The later native object/resource graph remains outside the scalar request's guarantee. Tests deliberately show that the handler does not follow unreadable companion pointers; this is the reviewed scope, not a claim those pointers are safe for deferred consumers.

## Reproduce integrity

`py -B artifacts/gummi-special-request-implementation-20261011/verify.py --check-current-product`

This checks original signature bytes, immutable source snapshots, the unchanged older Gummi route, recorded test logs and the exact manifest. It does not rebuild or rerun tests. The isolated compile/run command is recorded in `implementation.json`; compiler outputs were retained separately under `artifacts/gummi-special-request-build-20261011` after the run, and their hashes are recorded in `compiler-output-pins.json`. No original EXE, IDB, game state, package or version was changed by this subtask.
