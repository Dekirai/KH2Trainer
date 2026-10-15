# Gummi requests, scale ownership and collision resources

This continuation follows the delivery of v0.12.17, which removed the Asset
Browser at the user's request. It focuses on trainer actions and the native
conditions needed for future mods.

## Gummi special-weapon request

The captured normal input path reaches `2312B0`, a five-byte helper that sets
request mask 2 at combo+68. The subsequent native update consumes that pulse
when stock and phase permit. A later weapon-instance call sets another request
latch; this evidence does not establish projectile creation or a hit.

The action in v0.12.18 uses capability 485 and command 1485 in the existing
Gummi Ship / Flight page. Starting needs stock. Continuation uses the native
10..50 elapsed-unit window. The bridge samples the current ship, counts, phase,
flags, stock, progress, timer and step twice, checks original code, and calls
the setter once. It retains no request for automatic replay or restoration.

The static study is [gummi-gameplay-continuation-20261011](../gummi-gameplay-continuation-20261011/report.md).
Its manifest SHA256 is `2995ef76f490cdca02bb11c24baf0ffc52fe8ea2c9ae5bf9385a2b30ae94892d`.
Independent static review: [gummi-static-review.json.txt](gummi-static-review.json.txt).
Independent source and targeted native acceptance is recorded in
[gummi-implementation-review.json.txt](gummi-implementation-review.json.txt).
Full managed, UI and package validation is recorded with the delivered EXE.
The frozen [native implementation record](../gummi-special-request-implementation-20261011/report.md)
pins the two native source changes, original signature comparison and isolated
tests. Its manifest is `fe05fde841cdf36bfad5b52fe240080d7d95189c3872c2555ba9055d66a57884`.

## Scale ownership

The Stitch-associated virtual body at `1C7E00` resets the cached player's
Actor+60 scalar to 1.0, including when its previous value was already 1.0.
The actual invocation of that virtual slot is still unresolved. Attachment
adapters can retain a BDX callback that runs during detach. A figure without
a parent can still gain children, so its parent field alone does not establish
an unchanged transform context.

These findings constrain a future Tiny/Giant effect. Native takeover must end
the trainer's ownership; a later reset must not restore an obsolete value.
The existing offline motion evaluator and actor-generation observer are useful
components, but the native motion resource and attachment context still need
a verified binding. No new scale control is released by this round.

See [actor-scale-ownership-20261011](../actor-scale-ownership-20261011/report.md)
and the [v0.12.17 implementation map](../scale-implementation-map-20261011/map.md).
The scale study manifest is `27b285104ba2042c9223fa2e47ef04302800c086326b02768e5e003ab0c7a2d8`;
the map manifest is `36893038cd2df3bd05c55680ceb8af4b22c31cfba1d982569fe090d6d3230343`.
Independent review: [scale-review.json.txt](scale-review.json.txt).

## Collision resources

Collision wrappers borrow table pointers from the map BAR. Constructing a
wrapper can change activation bytes in those shared tables. Separate wrapper
allocations therefore do not imply isolated geometry. Moving-list membership
also does not establish pool ownership: one constructor accepts caller-owned
nodes. Query results retain borrowed node pointers.

See [collision-resource-lifetime-20261011](../collision-resource-lifetime-20261011/report.md).
Its final author manifest is `6d6d8c2f71ab42297ec19e7156c5352a610d0c96468f549bd6a9646b9761cff6`.
Independent review: [collision-review.json.txt](collision-review.json.txt).
The selected teardown path removes collision wrappers before releasing the
map cache reference. It does not establish that every external borrower has
finished. Geometry bounds and resource lifetime remain requirements for future
placement or collision-aware movement controls.

## Scope

Fresh body captures include repeated addresses and are not a count of newly
understood functions. The global coverage report counts narrow documented
claims; it does not measure complete program semantics. Original PE comparisons,
synthetic instruction models, isolated native tests and offscreen UI tests do
not establish live gameplay behavior. No KH2 process was launched or attached,
and no game, save or mod files were changed in this continuation.
