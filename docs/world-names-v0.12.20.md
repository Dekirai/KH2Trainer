# World names in v0.12.20

The World selector under **World > Travel & Party > Travel to room** now shows
full English names. The previous labels contained internal two-letter codes and
misdecoded separator characters. Long labels receive a wider input so that
**The World That Never Was** fits in the selected-value field.

The destination IDs, order, default Twilight Town selection, and command payload
are unchanged. The mapping follows the [OpenKH world index](https://openkh.dev/kh2/worlds.html),
whose indices are hexadecimal. The UI uses the familiar plural spellings
Destiny Islands and Pride Lands. World ZZ, End of Sea and World Map retain their
separate entries; no ordinary world name is invented for these destinations.

The performance changes from v0.12.19 remain in this release. Asset Browser stays
removed. The native Motion copy component in the accompanying source has no
live admission provider or TrainerBridge consumer yet.

Validation uses the embedded catalog, the real WPF templates and synthetic
command dispatch. No game was launched or connected for this UI change.
