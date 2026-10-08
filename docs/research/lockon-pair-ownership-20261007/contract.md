# Paired lock-on value ownership

This change fixes F04 from the reward ownership audit for Eagle Eye and Short-Sighted. Both rewards remain Sora-only. The settings are global Float32 values, not Actor fields.

## Native evidence

Fresh read-only IDA capture contains nine full functions, 280 instructions and 1,248 body bytes, plus eight constant bytes. `verify.py` matches them against retail SHA256 `9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed`, independently checks instruction boundaries with Capstone, and compares the two complete runtime setter pins.

- `1403ABD60(float XMM0)` writes scale at RVA `2A1141C`, then writes `Float32(scale * parameters[80])` at `2A11420`.
- `1403ABD80(float XMM0)` changes only the break distance. The two getters return the independent globals in XMM0.
- `1403ABAB0` initializes scale=1 and break=parameters[80].
- `14038CF20` deliberately sets scale=4, then sets break to `Float32(4 * parameters[76] + 500)`. Restoring only the scale therefore loses a legitimate independent original break value.
- `1404308D0` forwards the first Float32 VM argument to the scale setter.
- `1403BEA30` uses scale times parameters[76] for acquisition. `1403DD280` uses the separate break distance for retention. Both have an exemption for target Actor+1736 bit0x400 when scale>=1; this is not a promise of universal lock-on reach.

## Command and snapshot

Command1475/capability475 has six integral arguments, all carried exactly as UInt32 values in the existing double argument array:

1. Operation:0 apply,1 conditional restore.
2. Expected scale Float32 bits.
3. Expected break-distance Float32 bits.
4. Desired scale Float32 bits.
5. Desired break-distance Float32 bits.
6. Expected native retention-default Float32 bits.

Both expected and desired pairs must have scale0.05f..10f and break>0..10,000,000f. Both scale*current acquisition-default products must be finite. The upper break bound covers scale10 times the accepted retention default1,000,000; independent break values within the bound are valid originals. The host waits on un-restorable originals instead of guessing or clipping them.

Apply additionally requires exact current retention-default bits and an exact Float32 desiredScale*retain product. Restore does not require the old default and never recalculates the original distance.

The existing Sora Ready, full live Actor/status checks, parameter BAR ownership, setter pins, current game thread, fresh host heartbeat, and contiguous eight-byte writability are required. The handler compares both exact current UInt32 values. On apply mismatch it returns4 without writing. On restore mismatch it returns0 without writing either value. Matched commit writes the two exact originals or desired values without calling native code or yielding between comparison and stores. Invalid input returns2, unavailable context returns3, all before either store.

These globals start at a four-byte-aligned address. This is serialized game-thread compare/apply, **not** an aligned hardware64-bit compare/exchange. It excludes uncooperative concurrent external memory writers and page-protection changes.

The same snapshot call publishes scale bits in475 and break bits in476, or neither when the pair is invalid. Existing373 supplies the exact Float32 default. Host `LockOnPairSnapshot.FromSnapshot` requires fresh protocol4, scene readiness, valid/capability bits for all three, finite and representable default and bounded pair values. The adapter evaluates one `Current` publication; it does not combine independent `TryRead` calls.

## Host lifecycle

The two rewards capture both original values and register cleanup intent before awaiting paired apply. They never use scalar OwnedValue, approximate equality, or scalar Sustain for these globals. A fresh changed pair ends the reward and is preserved as a whole. Missing observations and lost control pause useful time, including with timer pause opt-out. The monitor can observe a foreign pair only when control is ready, and ends it before that interval charges duration.

A timeout, disconnect, unknown native fault or general transport error does not prove no write. Cleanup intent remains until a conditional restore is acknowledged. A lost restore ACK stays pending even if the original pair is visible; the next acknowledged mismatch is a terminal no-op. Existing ordinary transport serialization prevents a later restore from overtaking a still pending apply.

`BridgeCommandRejectedException` preserves an actual received native rejection code. **Only** this pair handler's codes2/3/4 prove a rejected apply made no writes, so they clear its cleanup intent. In particular, a foreign pair already equal to the desired reward pair must not be restored after an acknowledged apply mismatch. A synchronous local control refusal also precedes publication. No other effect gains a generic no-write inference from exception codes.

EffectContext includes the pair in RestoreAsync and HasPendingRestores, so failed starts also retain cleanup. `HasDurableCleanup` exempts that pending pair only from the existing180-second cleanup cutoff. Retry control gates, group serialization and all Actor-lease behavior remain intact. Once cleanup starts, the pair helper cannot apply again.

## Limits

- Value ownership cannot detect a foreign writer that leaves both bit patterns identical, including a later identical pair after a scene or process lifetime change. There is no global-settings generation token or MOV1 mutation receipt here. This is the stated same-value/ABA boundary, not Actor ownership.
- A host snapshot can become stale before dispatch; the native compare/default checks handle different values. Snapshot absence alone never settles an uncertain command.
- Shutdown of the trainer process loses its in-memory pending intent. Within a running host, prolonged rejection does not discard it.
- Native scripts and target exemption flags can bypass or replace the requested targeting range. This task does not widen role support, patch native callers, allocate targets, or run native developer tools.
- Validation is static plus synthetic native/host tests. No live game, UI or Twitch account action was performed.
