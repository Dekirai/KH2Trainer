# Independent offline motion review

No blocking finding remains in the reviewed source. The JSON receipt binds the
three Core files and focused tests to their final SHA256 hashes.

The review covered widened bounds/count arithmetic, immutable copied data,
allocation and iteration limits, Prototype key/time searches and extrapolation,
and RAW frame selection and matrix interpolation. Eight complete native ASM
bodies were compared, including all six RAW cross-product branches, four-component
operations, normalization tolerance and the scale-bit fast path. Prototype root
and curve pseudocode supplied the additional structural comparison.

The final second-table correction also matches the newly captured `1DAD10`:
signed counts at payload52/60 bound both declared tables; their widened sum
bounds every root curve index. Readable bytes outside that declaration no longer
become an eligible curve. The new negative/truncated/index-at-count regressions
cover this change.

The implementation author reports2275 passing checks and215 retail entries with
1075 samples. These were not independently executed by this reviewer. Retail
sampling covered Prototype data; RAW coverage is synthetic. No product files
were changed and no game process was accessed during the review.

The API's `OfflineMotionProjection` label is appropriate. Root-only finite output
does not establish invertibility, every future frame, bit-identical CRT behavior,
complete skeletal/IK validity, a live resource identity or native motion safety.
