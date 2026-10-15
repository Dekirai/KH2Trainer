# Native Motion payload copy

This page records the initial copier packaged as source with v0.12.20. The
[subsequent PreparedCopy refactor](../motion-prepared-copy-20261011/README.md)
separates allocation from the held read interval and admits Sora's ordinary
0x80 BAR profile. Its tests and source pins are separate from the historical
receipts below.

`src/KH2Trainer.Bridge/MotionPayloadCopy.h` implements the bounded reader described
in [the native selection contract](../motion-native-copy-contract-20261011/contract.md).
It reads exactly two resident BAR levels, uses the already-bound physical outer
index and first inner Type9, verifies containing spans and runtime-prefix fields,
and returns privately owned payload bytes. It calls no native engine function.

The caller must supply an already-held `ReadScope` that keeps the actor, ordinary
cache reservation, bindings, pointer decoder and payload alive and serialized for
the entire operation. Its revisions must be monotonic and reject unknown history.
The component validates retained decoder and metadata witnesses before and after
the copy, and checks admission again immediately before returning success.
These checks cannot substitute for the scope's actual lifetime guarantee.

Failure returns no bytes or identity. Payload and table budgets precede allocation
and iteration. Initial policy excludes overrides, links, borrowed contexts,
special BAR classes and external/child-cache targets. This is a deliberately
limited supported profile, not a claim that the native engine rejects those paths.

The compiled tests exercise the real header through a private virtual-address
provider. They cover both kind/vtable pairs, mixed outer entry types and tags,
first-invalid-Type9 rejection, parent/table endpoints, packed pointers, context
rules, read/allocation errors, private output lifetime and late revocation.
The payload fixtures are not assertions of valid full Motion or skeleton data.

The targeted run passed **292 checks in 74 cases** and separately compiled the
production interface. An independent source/test review accepted the component
within this scope. The [test receipt](test-report.json.txt), [native output](native-tests.txt)
and [review](independent-review.json.txt) pin their sources and limits. These
downstream receipts were added after packaging v0.12.20; that immutable package
contains the implementation, tests and full release validation logs.

A separate [handoff probe](core-handoff.json.txt) ran this native copier on a
private RAW fixture, wrote its actual 256 copied bytes, and passed that file to
the existing Core DLL's `ReadPayload`. Evaluating frame 0.25 produced X translation
2.5 between the fixture's translations 0 and 10. A second successful copy containing
only four kind bytes was rejected by the parser. This checks the payload-only
interface and its limits; it does not install a consumer. Sources, binaries and
commands are pinned in the [provenance](core-handoff-provenance.json.txt) and
[artifact manifest](core-handoff-manifest.json.txt).

## Integration still required

There is no installed production `ReadScope` and no call from `TrainerBridge`.
The normal Motion-entry observer alone does not establish complete cache and
binding history. Implement the required pre-mutation admission and revocation
routes, then connect the copied bytes to the existing Core
`MotionPayloadReader.ReadPayload` (not `ReadType9Entry`, because the prefix is
already removed). A validated copy alone cannot authorize Scale or native playback.

No game execution or game/save writes were performed. The v0.12.20 application
change concerns world labels; this support component is included in source only.
