# STATUS bootstrap: update return and older writers

## Decision

Returning from `HookedUpdate` is not a proven barrier for all STATUS writers. Keep STATUS ownership unavailable until old calls have drained. A permanent one-byte entry gate makes a conservative audit of pre-existing thread stacks a concrete option: newer supported calls must pass through the tracked wrappers, while older calls keep their original code bytes and stack frames.

The evidence supports this design under a bounded native contract. It does not implement the stack audit or prove that the observer is ready for game use.

## What the engine actually waits for

`14EB70 → 14FC20 → 14FD60` traverses the scheduler. The scheduler can call tasks directly or switch to cooperative fibers. It does not join all OS threads before returning.

The six motion-job workers are narrower. `3BEEC0` waits through `130130` before its ordinary return. The other two observed `12FDB0` callers, `411B90` and `411F30`, also wait for their batches. `130030` signals completion only after queued callbacks finish. This supports a motion-job barrier, including the previously established possible motion→BDX path. It does not identify a shipped event asset that actually writes STATUS on a worker.

The resource worker `3A0C60` is separate and can still be loading while the update callback returns. `3A0790` processes phase2 requests and skips phase0/1. No concrete STATUS-writing resource callback was found here. The absence of a join is a reason to audit all older threads; it is not evidence that every loader writes STATUS.

## Can an old writer hide in a parked fiber?

The normal native closure of the five STATUS entries contains **25 functions**. It has no call to the engine fiber-switch paths. All five root functions keep their own frame until they return, so interruption inside a deeper helper leaves a root return address for a complete native unwind.

Two easily missed dependencies matter:

- `DecodeNullable` tail-jumps to `4AD3F0`, which can enter the pointer-table lazy initializer. Its CRT guard can block in a critical section or a condition-variable/event wait. A call-only graph misses this route. Init's five calls to `EncodeNullable` are separately proved to pass null and return immediately.
- Equipment lookup tail-jumps to `41E8F0`, which calls imported `bsearch`. Its fifth argument is the fixed four-instruction comparator `41E8E0`.

The indirect branch inside `401730` is a local switch. Its 27 targets and 152 selector bytes were verified against the original binary. The other indirect native branches in the closure are explicit import/CFG boundaries. CRT initialization resolves the encoded callback slots to `SleepConditionVariableCS` and `WakeAllConditionVariable`.

Normal synchronization blocks the calling thread; it does not invoke the engine fiber scheduler. The Windows API behavior is documented in [SleepConditionVariableCS](https://learn.microsoft.com/windows/win32/api/synchapi/nf-synchapi-sleepconditionvariablecs). The lookup's callback contract is documented in [bsearch](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/bsearch).

This conclusion requires intact native code and imports, correct dynamic callback bindings and valid native parameters. Arbitrary exception handlers, invalid-parameter handlers or replacement code can execute other behavior. They are not covered by a normal-call closure and must not be silently accepted by the bootstrap audit.

## Required implementation behavior

After every gate and cache flush succeeds, retain handles for the pre-existing process threads. Inspect their complete stacks with prebuilt static unwind metadata under short suspensions. A thread with an older writer must resume and drain naturally. Any uncertain stack remains unresolved. Checking only its current instruction pointer, waiting a frame, or seeing an empty observer counter is insufficient.

Do not allocate, acquire loader locks, call dynamic function-table callbacks or hold the observer metadata lock while suspending another thread. Retained handles distinguish thread lifetime from reusable IDs. The calling game thread needs its own captured-context check. Only after the old-thread set is discharged and no tracked writer is active may acquisition validate and adopt a STATUS allocation. The full phase contract is in [contract.json](contract.json).

## Evidence

Fresh IDA capture: **46 complete bodies, 2,731 instructions, 11,889 original body bytes and 78 string bytes**. The bodies include 267 bytes of checked embedded switch/padding data. `verify.py` checks original PE SHA, each body and instruction boundary, import identities, null-encoder call sites, the fixed comparator, root-frame preservation and the bounded control-flow closure.

```powershell
py -3 -B docs/research/status-bootstrap-20261007/verify.py
```

No live KH2 operation, save change, observer installation or runtime bootstrap test was performed. This report does not establish a whole-program proof excluding arbitrary computed or external STATUS writes.
