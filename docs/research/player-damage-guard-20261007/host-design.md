# Damage guard reward ownership and timing

## Baseline and scope

The v0.12.5 `invincible` reward used the ordinary scalar `OwnedValue` toggle at slot106. That value comparison was not an actor-lifetime proof. Its timer could also run without a confirmed effective guard, and a later scalar cleanup could disable protection belonging to a different actor or manual action.

This host change uses the native generation-bound guard contract supplied by the root implementation. It does not alter the MOV1 movement transport or claim that the ordinary command channel supplies retained typed receipts.

## Native interface

- Command1472 / capability472: seven exact unsigned32-bit values `[operation, ownerLow, ownerHigh, bridgeLow, bridgeHigh, generationLow, generationHigh]`.
- Operation1 ensures protection only for the expected current generation and expected bridge. An active foreign/manual guard must be refused. The same owner may ensure again idempotently.
- Operation0 releases only the matching owner and bridge. Generation0 releases that owner across generations; it never means all owners. Owner0 is reserved for manual operation.
- Snapshot106 means currently effective protection, not just a remembered enabled request. Slots473/474 contain its owner. They must be copied in the same publication as generation467/468, bridge469/470 and observer471.
- Manual slot106 activation claims owner0 even if the native guard was already active. This makes same-value manual takeover visible.

## Host state machine

A new reward has a random nonzero64-bit owner, no original scalar value and no established protection. Before publishing Ensure, it records the target bridge as a cleanup intent. A successful acknowledgement alone does not settle the redemption: fresh effective protection with this exact owner and current actor identity must be observed. Such a readback may also confirm an applied Ensure whose acknowledgement was lost.

Maintenance precedes the ongoing usefulness check. A loss of protection therefore pauses the timer and can trigger a new expected-generation Ensure when the player is controllable. It cannot deadlock behind an ActiveCheck that itself requires the missing protection. Foreign/manual protection pauses the reward and prevents reapplication.

Cleanup is an irreversible state. Once entered, the lease never issues Ensure again. It retains its owner intent until conditional Release has an acknowledged successful result, or a fresh coherent publication proves a different bridge-instance nonce. An off snapshot, zero effective owner, disconnection, observer fault or a rejected/timed-out command is not a no-write proof. This conservative rule also preserves an Ensure still pending in the native command queue.

Ordinary BridgeConnection.ExecuteAsync holds the command semaphore and refuses a new publication while requestSequence differs from responseSequence. Therefore a cleanup Release cannot overtake a still-unacknowledged Ensure. If the Ensure finally runs, the later conditional Release removes it; if its request expires, the later Release is an acknowledged no-op. Exceptions are retained conservatively, including refusals that may in fact have been definite. This is weaker than a retained native receipt and is deliberately described as such.

Cleanup is allowed without player control and retained beyond the ordinary scalar restore timeout. Native conditional cleanup performs the ownership check and may refuse temporarily. The effect group remains blocked until cleanup resolves. A reward that never establishes protection refunds at its waiting limit while preserving any uncertain cleanup intent.

## Timer proof and limits

Paid time requires previous, pre-maintenance and post-maintenance usefulness plus the same known actor identity at all three observations. The actor key combines a native-observed construction generation and a bridge-instance nonce; it is not just a role, pointer or scalar value. Actor replacement, including Sora-to-Sora, charges zero for the crossing interval. ActiveCheck remains mandatory even when the streamer opts out of general readiness timer pausing. Gaps longer than the one-second native freshness budget are not charged.

These are bounded observation rules, not frame-exact accounting. Changes that start and finish between snapshots can remain unobserved. There is no cumulative native protected-time counter.

The guard handles negative HP damage through the verified actor callback with bar0. It does not promise to block direct script HP writes, hit reactions, every death condition or all game mechanics. Role admission is changed only after the native Sora/Roxas/Mickey callback, lifetime and fixture tests are confirmed by the native owner.

## Integration

`DamageGuardSnapshot.FromSnapshot(TrainerSnapshot, uint now)` is a pure strict decoder in the Twitch assembly. `IGameControl.DamageGuard` defaults to unavailable for legacy adapters. The real adapter decodes one cached TrainerSnapshot, avoiding separate reads crossing its cache-refresh boundary. Split unsigned32-bit words preserve all64 identity/owner bits.

`DamageGuardEffectLease` is independent of scalar OwnedValue and native MOV1 receipt state. EffectContext exposes generalized actor-lease maintenance/identity/retained cleanup for movement and guard effects; existing movement operations remain unchanged.

Focused fixture tests cover strict decoder bounds/staleness, acknowledgement versus readback, actor/role changes including an awaited dispatch race, manual/foreign takeover, pending Ensure execution after reward stop, lost release ACK, control loss, timer opt-out, cleanup retention and independently observed replacement bridge.
