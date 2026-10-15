# New effects in v0.12.21

## Flashbang

Flashbang uses brightness **5000** for 8 seconds by default. Previously it used 50,
the top of the game's ordinary settings menu. Duration remains configurable.
The trainer's brightness control now supports −50 through 5000.

The native signed-short preview setter has no menu clamp. Its final RGB gamma
exponent is `2.2/(2.2+level/50)`: about 0.6875 at 50 and 0.0215264 at 5000.
The higher setting strongly lifts nonblack pixels; black pixels can remain black.
The effect uses the game's display preview.

The [static Flashbang study](research/flashbang-v01221-20261011/README.md)
includes the captured instructions, original shader, disassembly and verification
scripts used to choose the expanded range.

The renderer stores a float adjustment. Readback now reconstructs the exact
integer input so a value such as 17 does not become an unrestorable fractional
value through float rounding. All 5051 supported levels were checked through
set, readback and restoration in private tests. The loaded game settings keep
their original −50..50 validation; the preview does not write those settings.
Brightness ownership now compares exact integer levels: a later change from
5000 to 4999 is preserved when the effect ends. The existing sustain behavior
captures a changed level before reapplying the active effect, so that changed
level becomes the value restored later.

## Six new Twitch rewards

| Reward | Behavior |
| --- | --- |
| Cut Enemy HP / Gegner-HP reduzieren | Removes 25% of the current locked enemy's HP by default; configurable 1–99%. Rounds removed HP up, keeps at least 1 HP and respects a higher native HP minimum. |
| Calm the Enemy / Gegner beruhigen | Resets the locked enemy's current revenge value. An already started counterattack continues. |
| Refill Form or Summon Timer / Form- oder Beschwörungstimer auffüllen | Refills an active Drive Form or summon timer. Does not change forms or award timer-crossing EXP. |
| Heavy Jumps / Schwere Sprünge | Halves base jump height and doubles the falling-speed limit, up to 100, for 30 seconds by default. High Jump and special actions may select different heights. |
| Gummi Special Ammo / Gumi-Spezialmunition | Adds 100 base charge points by default, configurable 1–900. Loadout bonuses and stock limits apply. |
| Enemy Armor / Gegnerrüstung | Sets the selected enemy's general received-damage factor to 50%. The setting applies to that enemy until the game replaces it; other damage modifiers still apply. |

Rewards wait for their required scene, character and target. A refused native
command refunds the redemption. Already full timers, zero revenge and already
equal or stronger enemy armor are rejected instead of charging for no change.
The Gummi reward requires the corresponding ship/weapon readouts and capacity.

Heavy Jumps uses the existing native movement ownership mechanism and shares
the jump group with Moon Jump. Its cleanup follows the captured actor generation
and original values. It supports Sora, Roxas and rescue Mickey under the existing
movement checks. The manual version is a one-time runtime change.

These rewards can also be tried locally with each reward's **Test** button.
No Twitch connection is required for a local test.

## Manual controls

- **Combat > Practice > Reduce locked enemy HP by percent** calculates against
  the enemy selected when the native command runs. It reads that enemy's current
  HP and minimum in the same command; no old host HP snapshot is used for the write.
- **Sora > Movement > Heavy jumps** changes both current air-movement fields once.
  Another click applies the same relative changes again. Neither action is replayed
  by profiles or changes saved character stats.

## Validation and use

The release build runs the native, Core, Twitch and offscreen WPF suites, then
checks the packaged executable and its embedded bridge. Native fixtures cover
nonlethal target floors, current-target selection, invalid values and movement
context/role/write guards. Twitch tests use fake game and reward services.

No live KH2 or Twitch operation was performed for this release. Actual brightness
appearance and frame rate have not been measured in a running game. Restart KH2
before connecting this build so its new bridge replaces the old loaded component.
The dark interface, full world names and removed Asset Browser are retained.
