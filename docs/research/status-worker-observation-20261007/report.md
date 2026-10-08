# STATUS observation across native worker calls

The motion job can synchronously enter a BDX script. A STATUS observer must therefore handle overlapping native calls from different threads; checking only `g_gameThread` is insufficient for this call graph.

## Evidence and limits

The verified path is `3BEEC0 → 12FDB0/130030 → 3BF4E0 → 3BFAB0 → 3C6AA0 → 3B5E80 → 3E1840 → 3E1C80 → 41B400`. `3B5E80` passes event **27**, with the actor, event ID and event pointer as tagged arguments. `3E1840` constructs and executes its VM context synchronously.

This path requires an actor in the batched motion pass, a newly present flagged motion event and a BDX context containing event 27. Actors with a nonnull `Actor+2496` geometry object take an earlier synchronous path. No retail event-27 script that invokes the General coefficient trap has been identified here. The registered trap and the worker-to-VM path are evidence of a requirement, not a claim that every animation rebuilds STATUS.

`3E1840` and `3E1C80` also save/set process-wide current-VM globals. The inspected bodies do not turn those globals into thread-local storage. Further asset and scheduling analysis must establish how shipped scripts use this path.

The report contains 21 complete bodies, 2,485 instructions and 10,237 original body bytes, plus 40 table bytes. The VM body's final 231 bytes are a three-byte NOP and 57 switch-table DWORDs. The verifier separately validates those targets. Original SHA, pagination and each instruction boundary were checked with Capstone.

## Implemented prerequisite

`StatusRevisionLedger.h` tracks all 80 pool slots without reading or writing native memory. It records a pool epoch, allocation tokens and separate revisions for General, Draw, Jackpot, Lucky and retention. Rebuilds and manual writes invalidate old ownership even if the resulting bits are identical. A reset/reuse cannot inherit an old allocation token.

There are 32 bounded callback records. Calls must return in stack order within one thread; different threads may return in either order. Metadata notifications require a caller-held lock that is released before native code runs. Acquiring or comparing ownership is unavailable while any native writer remains active.

Wrappers must call `Exit(frame, !AbnormalTermination())` in their finally path. A native release/reset that throws before completing must leave ownership uncertain, rather than falsely proving that an allocation ended. Overflow, corrupt signed indices and missing lifecycle notifications also invalidate confidence.

The isolated suite has **930 checks, no failures**. It covers same-value rebuilds, all slots, disjoint fields, pool reset, address reuse, thread interleavings, nested calls and failed native bodies. The header is not installed in the game and does not yet fix the existing scalar loot rewards. Installation, typed receipts and host integration remain the next required steps.

The complementary entry-plan implementation and real Windows unwind tests are in [status-entry-observation-20261007](../status-entry-observation-20261007/). Windows requires unwind metadata for generated code that changes the stack or nonvolatile registers: [x64 exception handling](https://learn.microsoft.com/en-us/cpp/build/exception-handling-x64) and [RtlAddFunctionTable](https://learn.microsoft.com/en-us/windows/win32/api/winnt/nf-winnt-rtladdfunctiontable).
