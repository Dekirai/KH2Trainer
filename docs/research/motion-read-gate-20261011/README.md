# Motion read gate: local exclusion mechanism

`src/KH2Trainer.Bridge/MotionReadGate.h` adds a Windows SRW lock around a
prepared payload copy. Participating native wrappers register before their
original call and finish afterward. The original runs outside the lock; a
reader returns Busy while any such invocation remains active.

The held read excludes entry of participating mutators. It keeps the lock
through all source reads, never allocates copy storage inside the interval,
and releases it during structured exception unwinding. Same-thread reentry
faults the gate before recursive acquisition. `CopyJob` also suppresses an
older successful result when a later attempt is busy, rejected or unwinds.

The tests use real private Windows threads, SRW locks, event coordination,
typed observer callbacks and a private inaccessible page. These exercise
the mechanism; they do not observe the game's threads or prove live admission.

## Integration boundary

The component is source only. No TrainerBridge route installs it, and no live
ReadScope exists. The trusted provider still has to establish source ownership,
complete writer coverage, prior-call drainage, pending-worker completion,
Actor/cache retirement and binding/decoder stability. In particular, zero
active wrappers does not prove those conditions. Ordinary controller frame
updates and the trailing C40 store in3C88C0 need coverage too.

The provider study closes only the captured synchronous reader and the
unchanged retail handler-table initialization. A ResourceEntry can retain
primary aliases after being unlinked; empty lists are not a lifetime proof.

The packaged v0.12.20 EXE, world labels and historical release tests are
unchanged. No FPS improvement or live-game result is asserted for this work.

Exact source, author-test and independent-review receipts are in
`implementation.json`. The gate callbacks and their context must remain alive
for as long as any future native router can reach them, including after fault.
