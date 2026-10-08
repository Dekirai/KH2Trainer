# HP and MP for Sora, Roxas and rescue Mickey

The native HP and full-MP routines share the required status layout across these
three verified field-player classes. The bridge now rechecks actual input control
for each command and every continuous healing/MP tick. Menus, events, transitions
and unavailable identity therefore suspend the native writes as well as the host timer.

HP changes also require a live HUD controller. Its native helper reads that global
before deciding whether the selected widget belongs to this player. If selected,
the bridge validates the bounded player HP widget and the exact sequence/animation
rows and track spans used by clips41,44 or46. The decompiler's one-argument signature
for193280 hid an inherited EDX argument; full assembly confirms the original clip
ID survives through both wrappers. No-op HP never calls the native damage/HUD path.

Native HP minimums remain effective. Requested1HP may clamp above1 in scripted
situations. This keeps the result positive and excludes the native death virtual call.
Full MP clears a positive recharge before adding a bounded nonnegative maximum;
effects0 avoids recovery animation. Full restore validates both HP and MP before
either is changed. It has no general rollback for foreign reentrant mutation.

Seventeen complete native bodies are pinned at runtime. verify.py separately checks
all19 captured bodies,608 instructions and2302 bytes against the original retail
EXE SHA256, and confirms all2183 bytes of the17 runtime pins. It needs no old workspace.

The integrated synthetic fixture runs the actual role classifier, gameplay observer,
PlayerHandle and PlayerTick, replacing only native HP/MP dispatch with callbacks.
Its initial run passed265 checks with no failures. It covers all seven Sora form
states, both Roxas states, rescue Mickey, unrecognized roles, blocked input, HUD
branch selection, clip/track bounds, code changes, recharge, no-ops and read-only
preflight. MSVC initially hit an optimizer internal error for a large aggregate
fixture reset; the equivalent ZeroMemory reset and non-inlined fixture encoder
compile cleanly at the unchanged production optimization level.

These checks do not prove every loaded resource is semantically valid and are not
a live-game reproduction. Runtime roles with unknown/modded layouts remain rejected.
Detailed address-specific claims and limitations are in report.json.
