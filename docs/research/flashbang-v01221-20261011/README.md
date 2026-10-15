# Flashbang preview range for v0.12.21

The self-contained [evidence archive](flashbang-evidence.zip) preserves the
19 files in the original study manifest plus the manifest itself. Extract it
before running `freeze.py --check` to check member hashes or `verify.py --check` to compare its
native instructions and shader bytes with the supported retail executable.
The verifier requires Python and Capstone; see its command-line options.

The original study manifest SHA-256 is
`44d1b9d011cf7a49dfceb1fc169c89425c8f9c058c90a69017b6835d01b9bb53`.
The reviewed executable SHA-256 is
`9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed`.

The native preview setter accepts a signed 16-bit level and passes `level/50`
without a menu clamp. The final RGB exponent is `2.2/(2.2+level/50)`. At level
5000 this strongly brightens nonzero channels; exact black remains black and
optional color correction follows. This establishes the scalar and shader
behavior, without claiming a measured live image or physical display luminance.

The accepted evidence consists of four complete native function bodies
(576 instructions, 2638 bytes), two complete instruction ranges in shader setup
(28 instructions, 131 bytes), and the original 9988-byte DXBC shader disassembled
with Windows D3DDisassemble. The attempted whole-function IDA export is kept as
an incomplete capture: it returned only ten actual lines despite metadata saying
1903. It is not counted as a complete function body.

The bridge tests exercise all 5051 integer levels from -50 through 5000 through
set, snapshot and restoration. Snapshot reconstruction preserves exact integer
inputs despite float storage. Loaded game settings still use their original
-50 through 50 bounds. The release's normal native test runner includes these
checks; no game process or GPU shader was executed for this study.
