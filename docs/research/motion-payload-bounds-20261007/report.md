# Bounded offline root-motion parser

The Core now has a typed parser and Float32 evaluator for the two native type9 root-motion formats. This is useful groundwork for evaluating a proposed Tiny/Giant transform against actual animation bytes. It does not establish native resource ownership or enable a reward.

## What is implemented

`MotionPayloadReader.ReadType9Entry` accepts one bounded entry with its 144-byte runtime prefix. `ReadPayload` explicitly accepts the payload without that prefix. Both return an immutable root-only model. `Evaluate(frame)` returns the root matrix, root presence, effective frame and RAW selection details. The result is labelled `OfflineMotionProjection` and always reports `EstablishesNativeMotionSafety=false`.

Prototype0 decodes the root descriptor, its nine channel references and referenced six-byte curve records/eight-byte keys. It evaluates constant, linear and Hermite interpolation, pre/post extrapolation, native wrapping and the short rotation discontinuity guard. Channels are scale, Euler rotation and translation in that order. Construction rotates X/Y/Z, adds translation, then scales all four components of each basis row.

RAW decodes a bounded 64-byte matrix array and mirrors the real frame conversion and interpolation. It is not a sixteen-float lerp: normalization, dot comparisons and six ordered cross-product branches reconstruct the basis. Translation and scales are interpolated separately. Native zero-length normalization leaves the vector unchanged, so a finite output is not a claim of invertibility.

The general channel evaluator `1DAD10` confirms that payload+60 is the second curve-table count. Both declared tables are bounded, and every root reference must belong to their combined count, even when an out-of-table record would still lie inside the payload.

All byte spans use widened arithmetic before slicing. Counts, signed curve references, individual value/tangent indices, decoded-element totals and evaluation steps are bounded. Arithmetic checks each Float32 intermediate. Wrapping and angle normalization reject nonprogress, including finite values so large that adding/subtracting a finite step leaves the same Float32 value. Public collections cannot mutate the parsed backing arrays.

`MotionRootEvaluator.Multiply(left,right)` and `ScaleBasis(matrix,positiveScale)` validate the corresponding numerical operations. They deliberately require the caller to choose the applicable Actor transforms and matrix order. They do not decide attachment, floor-alignment, custom-callback or motion-resource ownership.

## Fresh native evidence and ABI corrections

`evidence.json` contains 31 complete bodies, 1,834 instructions and 7,688 code bytes. Eighteen constant/vtable spans add 220 bytes. `verify.py` checks all instruction pagination and every recorded byte against the unchanged retail SHA256. It has no dependency on the old workspace or another verification script.

The Prototype root callback takes Motion in RCX, output in RDX and frame in XMM2. Its curve evaluator receives a fifth Float32 frame on the stack; the seven-float Hermite call uses four float registers and three stack arguments. RAW passes its interpolation factor in XMM3. The normalization helper returns its original XYZ length in XMM0 despite the decompiler's void annotation; W is retained. These facts are checked against full assembly, not pseudocode signatures alone.

RAW clamps also change the scaled frame: negative truncated indices zero it, and an upper clamp replaces it with the last index. However a scaled value between -1 and 0 truncates to 0 and retains a negative factor. The implementation preserves that distinction. It rejects invalid CVTTSS2SI conversions rather than reproducing an out-of-bounds negative matrix access.

## Verification and actual asset sampling

The isolated C# suite covers valid channels/interpolation, all six RAW branch orderings, normalization and W behavior, limits, signed offsets/counts, no-root branches, immutable copies, projection overflow and 2,048 deterministic structural mutations. Test execution and source hashes are recorded separately in `implementation.json`.

The read-only retail probe decoded 215 type9 entries from four MSETs: P_EX100, P_EX110, P_EX100_BTLF and P_EX020. They contain 168 unique entry byte sequences, 36 unique root-present sequences and 39 root-present entries. All 1,075 chosen frame samples completed; 195 samples actually evaluated root-present data. All observed entries were Prototype0. RAW is covered by synthetic tests in this round; these results do not assert retail RAW coverage or all-frame correctness.

One P_EX110 entry contains duplicate global time 58. The native searches tolerate equal global times. The parser therefore allows nondecreasing global tables while requiring positive spans between the keys referenced by a root curve. This was validated with a specific regression and the actual entry. Its identity and the individual sample results are preserved in the compact retail receipt.

## Limits and integration

The parser excludes skeletal and IK data, other constructor fixups, whole-motion safety, provider/runtime binding and all resource/Actor/attachment lifetimes. Samples use Float32 operation order, but MathF trigonometric/square-root behavior and floating-point environment are not claimed bit-identical to the game's CRT. No next-frame or all-time safety follows from one finite sample.

The next runtime step still needs the previously documented effective-byte handoff and resource-generation contract, followed by fresh Actor branch inputs and the retained cleanup journal. No Drive guard, Tiny/Giant control, bridge command or live game action was added here.

Root integration is one test-runner call: `MotionPayloadTests.Run(Check)`. The Core SDK includes the three new `Motion*.cs` files automatically. No shared project, version, catalog, coverage or package file was changed by this implementation.

## Final review

The isolated suite finished with 2,275 checks and zero failures; evidence regressions finished with 49 and zero. The independent static review found no blocking issue in the reviewed parser/evaluator scope. It bound all four source/test hashes, including the second-table-count correction. No independent game run or native differential execution is implied. See `independent-review.json`.
