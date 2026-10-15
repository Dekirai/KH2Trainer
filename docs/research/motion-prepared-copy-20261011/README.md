# Prepared Motion copy storage

The current source allocates its Motion copy buffers before entering the source
scope. `PreparedCopy::Copy` neither allocates nor frees memory. This removes one
possible heap/engine lock inversion from a future resource gate; it does not
implement that gate or establish ownership of game resources.

## Calling order

1. Call `Prepare(Limits)` with the source scope released.
2. Acquire a valid, serialized `ReadScope` and call `Copy`.
3. Release the source scope before `TakeResult`, another `Prepare`, or destruction.
4. Parse the owned payload after the scope is released.

Every Copy clears the previous publication metadata. A failed Copy therefore
cannot publish an earlier successful payload. A failed TakeResult returns an
empty error result and retains the prepared buffers for a later Copy. A successful
TakeResult transfers ownership once; another Copy then requires Prepare again.
The workspace belongs to one caller and is not shared by concurrent or nested
copies.

The `TryCopy` convenience API remains for privately owned sources without a
heap/engine lock inversion risk. It allocates internally and must not be used
under the proposed resource gate. The default payload budget is 64 MiB; this is
a byte bound, not a frame-time guarantee. A future live provider needs a measured
working budget and must avoid heap, engine, loader and blocking calls in its
Capture/Current/Read callbacks.

## Sora resource profile

The source also accepts ordinary BAR headers whose class bit is 0x80. The native
request worker sets this bit for the `obj/P_EX100` prefix. The ordinary fixup path
still builds the Type9 runtime prefix. Supported header bytes are 01/11/21/31 and
81/91/A1/B1; bit 0x40, including the combined 0xC0 class, remains unsupported.
The separate [cache and worker study](../motion-cache-read-scope-20261011/contract.md)
records the native evidence and remaining admission requirements. This updates
the earlier conservative profile restriction without rewriting its frozen record.

## Verification and release boundary

The targeted native suite passed **432 checks in 99 cases**. All 19 instrumented
PreparedCopy calls made zero `operator new` and zero `operator delete` calls,
including the fixture callbacks and rejection paths. The production interface was
also compiled without the fixture allocator replacement. The checks cover partial
read failure after a successful copy, late revocation, both allocation failures,
budget limits, repeated failed TakeResult, retry and successful ownership transfer.

The [test report](test-report.json.txt), [test output](native-tests.txt) and
[manifest](test-manifest.json.txt) pin the exact source and test results. These are
private virtual-address tests with no OS lock, installed hooks, worker coordination
or native resource-lifetime provider. Their measurements cover the synchronous
Copy call only. The earlier Core handoff probe remains evidence for the prior
copier version; it was not rerun or relabeled as a test of this refactor.

These changes follow the immutable v0.12.20 package and are currently source only.
That released EXE contains the requested full world names. This work adds no live
consumer, Asset Browser, game/save writes or gameplay guarantee.

## Remaining binding coverage

The held scope still needs complete coverage of relevant binding writes. The
existing captured `3C88C0` body calls `3C8CD0` at `3C8A08`, then, on success,
writes the logical ID at controller+40 at `3C8A11`. An After callback for
`3C8CD0` alone therefore precedes this caller's last selection write. The earlier
resource-binding study's candidate list was explicitly incomplete; the current
normal-entry observer must not be treated as a full writer barrier.

The copier also witnesses all 440 controller bytes. A production provider must
establish serialization for those reads, including frame updates, or narrow the
witness under a separately proved contract. Pointer equality and a later metadata
comparison cannot make an unprotected earlier read safe.

The cache study also leaves a concrete provider requirement open: writes by the
selected reader and its registered handlers must finish before reader return,
with no retained writer alias. An empty request queue proves neither condition.
The future scope therefore remains closed until this provider contract and the
binding/retirement coverage are established.
