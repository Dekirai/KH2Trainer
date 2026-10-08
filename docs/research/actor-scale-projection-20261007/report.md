# Actor scale: animation projection

The uniform scalar remains a useful basis for Tiny/Giant, but its projection also depends on animation data. This round resolves the concrete motion callbacks instead of assuming that the current Actor matrices prove the next result is finite.

## Concrete motion path

BAR fixup `3A6840` sends type9 to `1C5F20`. The latter uses a 144-byte runtime prefix and selects payload kind0 or1. Their constructors install `MotionPrototype0` vtable `5B4958` and `MotionRAW` vtable `5B4A38`; slot+40 resolves to `1DA6A0` and `1DB470`. Common initialization stores payload=type9+144 at Motion+8. Animation binding `3C8A40` stores this object at MotionStruct+24, which is Actor+368.

**ABI correction:** `3C7B20` takes a third Float32 frame argument in XMM2. The exported pseudocode omits it. A negative argument selects current frame MotionStruct+68 (Actor+412); `3CCB90` supplies -1. The actual virtual call forwards that frame. RAW interpolation similarly passes a fraction in XMM3. A wrapper based only on the decompiler signature would be wrong. No native call wrapper was added.

Prototype root motion samples channel curves. RAW motion selects and interpolates two 64-byte matrices. Their no-root branches return identity and AL=1; the caller then uses zero displacement. The live blend value and animation resource can change while Actor identity remains unchanged.

The native compare does not reject every nonfinite value: unordered blend values pass the `COMISS`/`JA` skip test, and an explicit NaN frame is forwarded. A future validator must require finite values before reproducing the ordinary branch conditions.

## Remaining validation

A finite scalar, axes and current matrix are insufficient to validate a new projection. RAW needs positive frame count, valid loop indices and bounded matrix spans. Prototype needs bounded descriptor/key/time/value/tangent tables and progress checks: a zero time span can make its native wrapping loop fail to advance. Neither routine receives a payload-size parameter. These are requirements for a bounded parser, not a claim that ordinary retail animation assets are broken.

The initial scale policy still excludes parent attachment, nonunit native axes/ramp and custom-transform callbacks. Euler/direction and floor-alignment branches need the stated projection checks. Model/joint and collision-center consequences remain as described in the earlier [contract](../actor-scale-contract-20261007/report.md); world-collision radii are separate.

No Tiny/Giant reward was added in this round. The next implementation must combine bounded motion projection with the retained per-Actor cleanup journal, including resource/attachment changes and uncertain acknowledgements. The synthetic counterexamples in `verify.py` test why finite-input-only checks are insufficient; they do not simulate gameplay.

## Evidence

23 complete bodies, 2,542 instructions and 10,738 original code bytes; four data spans total120 bytes. `verification.json` compares every span with the unchanged retail executable and checks saved ASM pagination. [report.json](report.json) limits each address claim. No live game, save, mod or IDB mutation occurred.
