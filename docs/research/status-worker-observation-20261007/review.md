# Independent motion-worker report check

No concrete correction found in the checked call-graph claims. This was a limited comparison of the report against twelve saved full assembly bodies, listed with hashes in `review.json`.

The queue and worker bodies support synchronous callback execution within the worker. The path through `3BF4E0 -> 3BFAB0 -> 3C6AA0 -> 3B5E80 -> 3E1840 -> 3E1C80` contains no intervening transfer back to the main thread. The motion evaluator receives the embedded motion component at Actor+344. Event bit 0, a newly present ID, Actor+1456 and a positive BDX event entry remain necessary conditions. The operand pointer is passed in 64-bit R8.

`3BEEC0` reaches the six-worker completion barrier on normal return. That supports the report's ordinary motion-join claim but does not alone prove a complete future hook-installation barrier.

The native graph makes a game-thread-only notification assumption insufficient. Neither this review nor the report establishes a retail event asset that actually invokes the STATUS setter on a worker. The process-global VM context accesses and native reachability remain distinct from proof of a concrete asset's behavior.

No exhaustive second audit of all 21 bodies or new original-byte verification was performed. No source, existing evidence/report, test or package was changed, and no live action or build was run.
