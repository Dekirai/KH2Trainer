# Collision resource construction and lifetime

The static map collider borrows its geometry from a type-6 entry in the map BAR.
Creating its 248-byte context also changes activation bytes in that resource.
Two contexts constructed from the same payload can therefore affect one another
even though their wrapper allocations are separate.

## Geometry binding

`1613C0 â†’ map+104 â†’ 161320 â†’ 16FFA0 â†’ 1722F0` is the captured binding path.
The context stores the original payload pointer and seven table pointers. The
header supplies signed 32-bit relative offsets and byte lengths. Native count
conversion sign-extends each length, performs an unsigned division, then stores
the low 32 bits. Negative lengths therefore do not behave like a checked
nonnegative size. There is no input-size argument at this boundary.

For the 20-byte leaf table, a narrowed count that is positive as signed32
enables initialization of byte 16 for the entries in that count. It clears
those bytes, then sets that byte when leaf byte 17 matches a selected group in the 64-bit
mask. The captured scene caller `1E7D30` supplies only 32 set bits through a
write to R9D. The moving-node constructors supply all 64 bits. Neither mask
enables leaf group IDs above 63.

These writes operate on borrowed table memory. A later wrapper can replace the
activation state observed through an earlier wrapper. That is a conditional
aliasing result, not a claim that the retail game normally creates conflicting
contexts. Attributes, bounds and the two context matrices remain distinct
validation requirements. The preceding collision-query study documents their
consumers and the shared query filters.

## Moving collider nodes

The pool initializer reserves 80 records of 24 bytes and a separate stack of
free indices. The pool allocator decrements its count before allocating the
context, and still appends the selected node if that allocation fails. A second
constructor appends a caller-supplied node to the same list. Consequently list
membership alone does not establish pool ownership.

Removal expects a current linked pool node: it unlinks the node, frees its
context, calculates the pool index and returns it to the stack. The function
does not validate arbitrary pointers, repeated removal, pool bounds or cycles.
The pool destructor itself frees the pool without traversing the list or
clearing its head and tail. Correct surrounding lifecycle order is required.
These observations do not claim that normal gameplay violates that order.

The moving segment query initially clears its result node and polygon. It then
changes shared context filters and overwrites the mutable segment endpoint
with each accepted returned point. This does not establish a shorter segment
or the complete hit contract of the called helper. The returned node remains borrowed. Caching it for a later frame would
need an ownership and lifetime contract beyond a successful query result.

## Scene teardown and the original BAR

The selected `1E7CA0` path tears down collision wrappers before calling the map
release helper. The latter immediately releases the auxiliary BAR at map+72,
but sends the original BAR at map+64 through the resource-cache decrement
helper. That helper changes a 16-bit reference count; it does not free the BAR
in this body. An unknown BAR reaches a null-relative write rather than a clean
failure return. A future mod must use the existing owner rather than treating
this helper as a general-purpose memory release API.

## Consequences for mods

Placement and collision-aware movement need bounded geometry and current
resource ownership. A temporary context is not isolated if it borrows mutable
tables. A size effect must also account for the earlier finding that joint
centers change with the transform while collision radii are separate. This
study supplies concrete resource/lifetime dependencies; it does not introduce
another Asset Browser or claim a finished Tiny/Giant feature.

## Evidence and limits

Twenty fresh complete captures contain 6,896 original bytes and 1,671
instructions. Eighteen narrow address claims cover construction, borrowing,
activation, list ownership and teardown. Several revisit earlier findings;
fresh capture counts are not new unique-function counts.

`verify.py` checks the unchanged original executable, complete ASM and
pseudocode page inventories, and every captured instruction boundary. Its
small interpreter runs the actual decoded header-binding instruction sequence
on 15 synthetic headers. Four further contract models examine leaf activation
and shared-buffer effects. They do not execute game code or establish complete
constructor, allocator, geometry, synchronization or gameplay semantics.

The existing IDB was idle, with full auto-analysis readiness unestablished.
No IDB mutation, automatic analysis, game attachment or game/save/mod write was
performed. Run `py -3 -B verify.py --check` from this study folder to reproduce
the stored verification using the original executable at its recorded path.
