# Actor-bound movement ownership

Status: native observer/journal and protocol-v4 host integration implemented;
isolated validation is complete and independent review is being finalized.
No live validation has been performed.

## Problem and evidence in the current host

The existing `OwnedValue` in `EffectModel.cs` stores a value, original and feature,
but no actor identity. Its approximate value comparison cannot distinguish a new
actor at the same address with the same value. The v0.12.3 MP and restore-range
checks improve usefulness and restorable values; they do not establish lifetime.

`BridgeConnection.ExecuteAsync` in `Core/BridgeProtocol.cs` serializes commands and
returns sequence/code/text. `ITwitchHost.Execute` and `IGameControl.ExecuteAsync`
discard that result. `TrainerFrame` publishes `responseSequence` before its later
feature ticks and snapshot. Consequently, reading slots344..347 after an awaited
command cannot identify either its original values or the actor it modified.

The new path must never reconstruct an applied receipt from a later snapshot.
It must not fall back to the four existing independent movement setters.

## Lifetime proof and its boundary

The native investigation found no existing generation in Descriptor, Ptr32 self
or status backlink. A journal alone does not make these addresses ABA-safe.

The implemented native observer watches the default ACTION vtable callback at
RVA5CCEC0, expected target409AB0, and counts only the exact constructor return
site3B396D from3B3200. Constructor/destructor paths, observer installation/loss and
the bounded native journal have separate evidence and test receipts in this folder.
The host tests model those proven native contracts; they do not execute game code.

After a proven, continuously installed observer, an already existing current
actor may be adopted as a baseline. A bounded watch table can track current and
journal-referenced addresses. Every new registration receives a fresh bridge-wide
64-bit serial; a constructor notification for a watched address invalidates its
old serial before it can denote the replacement. Never evict an unresolved watch.
Unreferenced observations may be evicted only if re-registration always gets a
new serial. Counter wrap, observer loss or missed-thread coverage must latch the
feature unavailable, not reuse old identities. A new bridge instance has a new
nonzero64-bit instance ID. No pointer is sent to the host as an identity.

The identity is `(BridgeInstance, ActorGeneration)`. Role/form is admission
metadata, not part of the lifetime proof. Changing current actor does not prove
the old one died: Sora can remain alive while Mickey is current.

## Coherent observation

Existing movement slots344..347 and control slots456..463 are read from one
`TrainerSnapshot`, never from several adapter getter calls that might refresh.
New reserved slots agreed with Root:

| Slot | Meaning |
|---|---|
|466|Typed movement capability; valid value1 denotes wire schema1|
|467 / 468|ActorGeneration low/high UInt32|
|469 / 470|BridgeInstance low/high UInt32|
|471|Observer state: unavailable0, installed1, fault2|

Require protocol4, support/valid bits, finite exact UInt32 halves, nonzero complete
identities, observer installed and the existing one-second publication freshness.
The four movement observations must be finite exact Float32 values; selected
fields must lie in their native edit policies. The typed view contains the
control state from this same snapshot. Missing or older metadata is unavailable.
There is no Sora-only legacy fallback for the new automatic ownership path.

## Binary transport

Use protocol4 without moving existing shared-state fields. The typed command is
1466 (capability466); its eight ordinary double arguments must be zero. The
generic host ExecuteAsync must refuse this command. All UInt64 fields remain
binary UInt64, never doubles. The existing command semaphore owns publication,
wait, response read and pending-result bookkeeping.

Request occupies128 bytes at shared offset1024. All offsets below are relative.

| Offset | Type | Field |
|---|---|---|
|0|UInt32|Magic0x31564F4D (`MOV1`)|
|4 / 6|UInt16 / UInt16|Schema1 / size128|
|8 / 16|UInt64 / UInt64|ClientId / OperationId|
|24 / 32|UInt64 / UInt64|BridgeInstance / ActorGeneration|
|40|UInt64|LeaseId|
|48 / 52|UInt32 / UInt32|Operation / field mask|
|56|4 × UInt32|Expected Float32 bits, walk/run/fall/jump order|
|72|4 × UInt32|Desired Float32 bits, same order|
|88 / 96|UInt64 / UInt64|Expected lease revision / effect owner ID|
|104 / 108|UInt32 / UInt32|Flags0 / reserved0|
|112|UInt64|TargetOperationId for query/ack|
|120|UInt64|Reserved0|

Response occupies192 bytes at shared offset1152; bytes1344..2047 remain reserved.

| Offset | Type | Field |
|---|---|---|
|0|UInt32|Magic0x31564F4D (`MOV1`)|
|4 / 6|UInt16 / UInt16|Schema1 / size192|
|8 / 16|UInt64 / UInt64|Echoed ClientId / OperationId of this request|
|24 / 32|UInt64 / UInt64|BridgeInstance / ActorGeneration|
|40 / 48 / 56|UInt64 ×3|LeaseId / lease revision / effect owner ID|
|64 / 68|UInt32 / UInt32|Outcome / selected mask|
|72 / 76 / 80|UInt32 ×3|Applied / restored / superseded masks|
|84|UInt32|Journal state|
|88 / 104 / 120|4 × UInt32 each|Original / applied / observed Float32 bits|
|136 / 140|Int32 / UInt32|Request sequence / reason|
|144 / 148|UInt32 / UInt32|Native tick / response flags|
|152|UInt64|ReceiptOperationId: originating mutation, or0 if none|
|160..191|bytes|Reserved0|

Response flags: IdentityKnown1, ObservedKnown2, HasReceipt4. Unknown bits/enums,
invalid lengths, incoherent masks and mismatched correlation fail closed. A valid
zero float is distinct from absent observation. Wire values use exact Float32
bits, including signed zero; do not reuse `EffectContext.Near` for ownership.

Normal1466 acknowledgements, including global expiry/heartbeat/validation
rejections, publish a correlated typed envelope before `responseSequence`.
Commit-write faults retain an uncertain result bound to the actual lease when
known. Unexpected read/observe exceptions outside the commit can enter the
engine's fault handling without a typed acknowledgement. The host keeps the
operation uncertain; an old reserved block cannot substitute for its receipt.

## Operations and outcomes

Operations: Acquire1, Reapply2, ReleaseIntent3, QueryOperation4, QueryLease5,
AcknowledgeReceipt6. Masks use walk1/run2/fall4/jump8; every nonempty mask1..15
accepts an atomic cohort of one through four fields. Current rewards use3 and12. Future
four-field rewards must claim both effect groups before product activation.

Outcomes: Invalid0, Applied1, Reapplied2, ReleaseAccepted3, LeaseObserved4,
ReceiptAcknowledged5, OperationUnknown6, Rejected7.

QueryOperation returns the original mutation's outcome1/2/3/7, identifies that
mutation with ReceiptOperationId, and echoes the query's own OperationId and
request sequence. OperationUnknown is not proof that an unresolved published
request never ran. QueryLease returns LeaseObserved plus the actual journal state.

Journal states: None0, Active1, ReleasePending2, Released3, Superseded4,
Destroyed5, Uncertain6. `ReleaseAccepted` means durable intent, not proof that the
old actor's fields have already been restored.

Reasons: None0, UnsupportedSchema1, InvalidRequest2, StaleBridge3,
ActorMismatch4, NotReady5, ExpectedMismatch6, InvalidValues7, JournalFull8,
LeaseNotFound9, LeaseConflict10, RevisionMismatch11, RequestIdConflict12,
ObserverUnavailable13, ObserverFault14, Expired15, HostExpired16, NoChange17,
WriteFault18, ReceiptNotFound19, NotOwner20, WrongThread21.

## Native mutation and journal rules

All field access is on the validated game thread, with a fresh current actor,
coherent supported role, current generation, control/readiness, policy and memory
checks. Compare the whole selected expected vector before the first write.
There must be no native callback or actor construction between compare, capture
and stores. This is atomic with respect to ordinary game-thread execution, not a
claim of CPU-atomic128-bit stores against arbitrary uncooperative external writes.
Preflight all destination spans; a partial write fault needs explicit uncertain
state and must not acknowledge a successful full cohort.

Acquire records native original and canonical applied bits in a lease and returns
them directly. A lease is keyed by client, effect owner, actor identity and mask.
Acquiring a different actor never uses the old actor's originals. A completely
unchanged acquisition may reject NoChange instead of claiming a useful effect.

Reapply requires its exact lease/revision and the same actor identity. For each
selected field still equal to its applied value, retain the existing original.
For a changed field, capture the new valid live original. Compare the full sampled
vector first; update all requested values and receipt revision together. This
preserves an unchanged field's original when only its partner was reset.

ReleaseIntent uses journal values, not caller-supplied originals. Marking intent
may occur while gameplay is unavailable because it changes only bridge metadata.
Actual restoration needs the same freshly validated current actor/generation.
For each still-matching applied field, restore its journal original; preserve
externally changed fields and report their superseded mask. Decide the entire
cohort together. Never resolve a stale pointer or restore into a replacement.

A different current actor leaves old cleanup pending. It is not destruction.
Drain matching pending releases before an acquisition and on later game-thread
ticks; when the old actor returns, cleanup can finish against its own identity.
Only proven destruction/reconstruction retires its old lease without writes.
On host expiry/disconnect/reset, mark that client's leases for release. Observer
failure leaves unknown lifetime unresolved and prohibits restoration based on
addresses. It must not fabricate a safe cleanup success.

Use fixed limits, initially32 leases and64 retained mutation results. Allocate
capacity before writes. Never evict live/unresolved ownership to make space;
return JournalFull. Queries and acknowledgements must remain available at capacity.
Mutation IDs are idempotent by client+operation plus exact request body. Reusing
an ID with a different request is RequestIdConflict. Query/read/ack need not consume
another retained mutation slot.

Ack6 with TargetOperationId>0 acknowledges a result the host has copied. It can
also include LeaseId, expected revision and effect owner to collect a terminal
lease. TargetOperationId0 is allowed only for that complete terminal-lease tuple.
Collect only Released/Superseded/Destroyed, exact owner/revision and no other
retained mutation receipt referencing the lease. Active/ReleasePending/Uncertain
never qualify. Already acknowledged operations are idempotent. If another receipt
still references the terminal lease, retain it for a later query/ack cycle.

## Host state machine

| State | Allowed transition |
|---|---|
|Waiting|Fresh typed view, controllable supported role, selected values restorable → publish one Acquire|
|Applying|Only its correlated reply can establish ownership; timeout/cancellation after publication → InDoubt|
|InDoubt|Resolve the same pending acknowledgement first; never publish a blind retry or infer failure from timeout|
|Acknowledged|Store immutable receipt before Ack6; useful only while fresh current identity and applied vector match|
|Suspended|Different identity, unavailable control, invalid observations or unconfirmed reapply pause paid duration|
|Rebinding|New actor requires its own expected vector, recipe computation and acknowledged Acquire receipt|
|Release pending|Record durable native release intent; never send old originals to a new identity|
|Terminal|Query proves released/superseded/destroyed; acknowledge result and terminal lease, then forget local ownership|

The connection keeps at most one published unresolved request. An ordinary or
typed command cannot overwrite it. Resolve reads the same sequence and typed
envelope under the command semaphore. Once its acknowledgement has been copied,
the transport can publish queries and acknowledgements for retained native results.
Cancellation before publication is harmless; cancellation afterward is an
uncertain outcome. Malformed or mismatched response bytes cannot become ownership.

Across reconnect, retain the process-local client/operation identity and an
unresolved operation handle where possible; query the same bridge instance's
journal. A new bridge instance invalidates all old receipts. If the host loses its
state completely, the native expiry release intent provides a separate cleanup
path. A query miss cannot override an outstanding original request's uncertainty.

Keep one effect-owner ledger with receipts per actor lifetime. Returning to a
still-owned actor must reuse its receipt, not recapture its applied values as the
original. New actors compute their own movement recipe from their own native
baseline. Float equality alone never transfers a lease between identities.

`ActiveCheck` stays read-only. The existing engine only sustains when ActiveCheck
is ready, so rebind/recovery needs a separate asynchronous maintenance phase that
may query/resolve while unusable and may acquire only under fresh control. It must
sample usefulness before that work: a successful late acquire cannot charge the
preceding unavailable interval. Cross-identity intervals also charge zero.
Extension admission requires the current actor's confirmed useful receipt.

Release processing and group availability must distinguish native accepted
cleanup responsibility from actual completion. Initially retain conservative
group blocking until the required current-actor cleanup is acknowledged. Do not
silently label ReleaseAccepted as all fields restored. Any relaxation for an old,
still-live off-current actor requires the native conflict check and journal drain
to prevent a new reward from inheriting those applied values.

## Minimal introduction steps

1. Add typed Core records, binary codec, coherent decoder and transport tests.
   The coordinated host/native bump to version4 is now applied. Connections are
   strict-v4; an older loaded bridge requires a game restart.
2. Root implements native journal/dispatch; native agent closes and implements the
   observer with tests for construction, adoption, destruction, loss and wrap.
3. Add adapter methods returning typed views/results. Extend the fake backend;
   no generic ExecuteAsync result is repurposed as a receipt.
4. Add dedicated movement effect ownership/maintenance to the engine. Existing
   scalar OwnedValue paths for unrelated effects remain unchanged.
5. Test late acknowledgements, timeout/cancel, same-address reconstruction, hidden
   Sora returning, changed one-of-two fields, valid reapply, capacity/GC, native
   faults, observer loss and role transitions. Only then allow FieldPlayers for
   super-speed/snail/moon-jump and activate protocol4 as a coordinated release.

## Conditional specification check

`artifacts/research/movement-ownership-20261007/ownership_model.py` is an isolated
Python model, with no game/process/network/UI access. It exercises2401 four-event
traces plus targeted receipts, reapply, query, capacity and two-/four-field cases.
Result:9625 checks,0 failures. It deliberately assumes a true birth identifier in
its safe mode. Its expected negative control demonstrates wrong-actor restoration
when only an address token is substituted, despite retaining a journal and receipts.
It does not prove that the proposed native observer meets that assumption, nor
does it implement the production transport, exact Float32 codec or partial-write
fault handling. Those remain separate implementation/tests.

## Implemented host details

`MovementClientSession` retains client identity, operation IDs, the command
semaphore, the last pending publication and an independent ambiguous mutation
origin across reconnect. A malformed/lost acknowledgement is recovered using
QueryOperation, never by replaying a write. QueryMiss and rejected queries do not
clear that origin. The transport verifies a recovered immutable receipt against
the retained original generation, owner, mask and desired bits. Uncertain receipts,
including unbound WriteFault, remain globally blocking. Only a real mutation
receipt or a StaleBridge reply corroborated by fresh independent instance metadata
can settle the old origin. A known uncertain QueryLease is a faulted lease, not
an outstanding command to resolve again.

`MovementEffectLease` maintains exact receipts per actor and performs bounded
asynchronous maintenance before ActiveCheck. Reapply preserves native per-field
originals; no scalar setter is used. Old living actors receive ReleaseIntent before
another generation is acquired. Their pending releases stay recorded; ending the
reward blocks its group until terminal cleanup is confirmed. Polling gives the
current actor priority and rotates older pending records to avoid starvation.
Uncertain ownership is never abandoned by the ordinary three-minute scalar retry
window. A fresh different bridge invalidates inaccessible old records without
replaying their originals into the new process. Actual cleanup in the former
process remains the former native bridge's responsibility.

Timers compare previous/current/pre-await/post-await actor identity as well as
usefulness. Unknown intervals and rebind intervals charge zero. An acknowledged
acquire establishes the effect; definitive no-write refusals remain unpaid and
retry only until the configured initial waiting limit. Scalar effect ownership
and all unrelated rewards retain their previous behavior.
