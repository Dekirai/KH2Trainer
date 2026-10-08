# STATUS observer wrappers

## Result

`StatusObserverSupport.h` implements the five typed Win64 wrappers that connect an installed entry observer to `StatusRevisionLedger.h`. `StatusObserverTests.cpp` executed 2,740 isolated checks with zero failures using MSVC x64 `/O2 /W4 /MT /EHsc`; the compiler emitted no warnings. Tests execute synthetic callbacks and Windows synchronization/SEH APIs. They never load or attach to KH2.

This component does not install an entry patch, register a live trampoline, publish a runtime capability, or change timed-reward cleanup in the trainer. The root installer must still establish the admission barrier and drain preexisting unobserved writers.

## Native ABI and pool validation

The previously captured complete bodies in `status-entry-observation-20261007/evidence.json` establish these signatures. Four wrappers preserve all 64 bits of RAX, even where retail callers ignore the native result.

| RVA | Entry | Arguments | Preserved result |
| --- | --- | --- | --- |
| `3C0010` | Initialize | RCX = STATUS | RAX |
| `3C1D90` | Rebuild | RCX = STATUS; RDX = optional character-save pointer | RAX |
| `3C2650` | Coefficient | RCX = STATUS; EDX = signed index; R8D = signed percentage | RAX |
| `3C1880` | Pool reset | RCX = pool | void |
| `3C07E0` | Release | RCX = STATUS | RAX |

`Entrypoints<Owner>` supplies actual static entry signatures with no implicit `this` argument. The compile-time reference binds a stable `Observer` instance. The installer selects relays targeting those entries and retains the instance, module, original trampolines and unwind metadata for all potential entrants, including after observation faults.

The pool contains 80 entries of 632 bytes. The free-index array begins at offset 50560, followed by the free-count DWORD at 50880. `PoolView::Owns` requires an exact aligned slot, readable STATUS/free-list spans, a count in 0..80, unique in-range free indices, absence of the requested slot from the free list, and a positive signed refcount at STATUS+612. Release uses this pre-call refcount when invalidating the ledger. It never infers lifetime from leftover scalar bytes.

Init has a different precondition. Startup function `025310`, captured in `status-rebuild-ownership-20261007/evidence.json`, invokes `3C0010` for all 80 slots before building the free list. Init therefore checks the exact slot and readable span without requiring an existing allocation, valid old free list, or positive old refcount. A subsequently captured lease still needs current pool ownership. Reset checks the exact configured pool address independently of its old contents. An unexpected pointer faults observation while preserving original forwarding.

`verify.py` checks all six reused full-body captures against the original PE, including every instruction boundary. These are reused evidence records, not six newly analyzed functions.

## Lifecycle and lock contract

1. A new object is Dormant. `Bind` validates and stores the five original pointers, pool address, nonzero bridge instance, and owning game-thread ID. No published entry may reach the object before successful binding.
2. Binding enters Bootstrap. Wrappers track calls and forward originals, but cannot issue field receipts. A normally completed native call does not automatically establish readiness.
3. After proving all entry publication, lifetime/unwind requirements, and the barrier that drains preexisting unobserved writers, the installer calls `ArmAfterProvenBarrier` on the registered game thread. The method also requires the matching instance and zero current wrapper calls. The method name is a caller contract; the method itself does not prove the external barrier.
4. Fault is permanent. Rebinding or arming cannot clear lost confidence. Original pointers remain unchanged, so subsequent native callbacks continue to forward.

Before each original, the observer serializes allocation validation and `Ledger::Enter` with an SRW lock. The entire original call executes outside this lock. `__finally` reacquires the lock and calls `Exit(frame, !AbnormalTermination())`, then drains its independent wrapper counter. Same-thread nested callbacks use the ledger's per-thread LIFO rule; workers may return in either order. Captures and field writes remain unavailable while any wrapper call is in flight.

LastError is restored to the incoming value immediately before forwarding. The value left by the original is restored after the finally handler, including on native SEH propagation.

## Field transactions

`WithMetadata` invokes a trusted callback under one lock acquisition, on the bound game thread and with no wrapper call active. `TransactionContext` exposes the ledger and read-only pool view. A typed caller can therefore validate the current pool/backlink, compare a revision stamp and exact scalar bits, notify a manual write, and write the field inside the same serialization boundary.

The callback must additionally validate Actor generation, role/context, and destination writability. It must not call a native original, reenter the observer, wait for another callback, or allow a C++ exception to escape. Merely splitting `Compare` and a later write across two transactions is insufficient. This API does not prevent callers from violating those contracts.

## Failure behavior and limits

- Observer-owned pool dereferences have an SEH handler. A changed or unreadable mapping loses confidence and does not suppress the original call. Readable-span checks reject PAGE_GUARD without consuming its exception.
- A metadata transaction's SEH exception faults observation and is not retried, because a write could already have happened.
- Native originals have a finally handler but no catch handler. Their SEH code propagates unchanged. An abnormal return faults observation, including when Release had already invalidated the metadata but the native refcount was never changed.
- Ledger capacity and wrapper-counter overflow fault confidence while preserving forwarding. Existing nested or cross-thread frames still drain.
- These guarantees assume a valid, bound, retained Observer and valid immutable original pointers. They do not cover a destroyed object, corrupted lock, bad trampoline, process termination, or an installer publishing unbound entries.
- The metadata lock serializes observer notifications and trainer field transactions. It does not lock the retail engine's pool; an inconsistent concurrent pool read faults confidence.
- Coverage is the five selected native entries and the known writer graph. Arbitrary mod writes, unknown computed native writes, Actor lifetimes and all-event scheduling are not proven by these wrappers.

## Isolated test coverage

Tests cover actual static entry types; exact first/optional/signed arguments and 64-bit returns; LastError; all 80 pool slots; before-call invalidation; nested callbacks; bootstrap callbacks; explicit arming; wrong instance/thread; immutable binding; all five native SEH families; bad count/free-list/refcount/alignment; free-slot startup Init; reset of invalid old data; last-reference Release; same-value manual writes; metadata SEH; guard pages; 40 nested callbacks across the 32-frame limit; wrapper-counter overflow; two active workers returning in the older-first order; and one worker throwing while another remains in flight.

These tests prove wrapper behavior with synthetic originals. They do not prove live installation or a game's observed behavior.
