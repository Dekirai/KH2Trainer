# Independent F04 pair review

No blocking finding was found in the reviewed source and test delta. The current file hashes are bound in `independent-review.json`; the producer report hash is intentionally omitted to avoid a receipt cycle.

The native command compares both exact Float32 values before writing, validates the apply default/product, and restores the independent original break value without recalculation. Existing Sora, status-pool, parameter-owner, thread and heartbeat gates remain. The pair is serialized on the game thread; no aligned 64-bit hardware CAS is claimed.

The host records cleanup intent before awaiting apply. Only this handler's received pre-write statuses 2/3/4 or a local prepublication deferral remove that intent. The regression where a foreign pair already equals the desired reward pair is covered. Timeouts and lost restore ACKs retain intent until a successful conditional restore or acknowledged mismatch. Pending intent survives the ordinary 180-second cleanup cutoff. Missing pair/control pauses useful time; takeover is observed before charging a new interval.

Reviewed test sources cover both rewards, all seven Sora forms, precise Float32 originals, changed defaults, one-ULP conflicts, malformed inputs, missing readback, role gates, lost ACKs and prolonged cleanup. Author logs record **876 native checks / 0 failures** and **2,074 Twitch checks / 0 failures**. The reviewer did not run builds or tests.

The documented same-value/ABA boundary remains: no Actor or global-setting generation token exists for this pair, including identical values after a scene/process change. Foreign concurrent memory writers and host-process termination are outside the conditional value-ownership guarantee. No live action was performed.
