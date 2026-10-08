# KH2 Trainer

A training and inspection tool for **KINGDOM HEARTS II FINAL MIX** (Steam build 1.0.0.2, x64).
A WPF desktop application talks to a small native bridge that runs on the game thread. The
bridge applies trainer features and publishes live values through shared memory.

The trainer is tied to one verified game executable. It checks the executable and the supported
Panacea loader before it loads the bridge, and it refuses to run against anything else.

## Repository layout

```
KH2Trainer.sln                 Visual Studio solution (all .NET projects, native sources as solution items)
build.ps1                      Full build: native bridge, all tests, single-file package
Directory.Build.props          Shared C# settings (C# latest, nullable, x64)
scripts/
  setup-toolchain.cmd          Finds the MSVC toolchain with vswhere
  generate-manual.py           Writes the HTML user guide from the feature catalog
src/
  KH2Trainer/                  WPF application (KH2_Trainer.exe)
    Data/                      Feature catalog and item, ability, character and message tables (embedded)
    Infrastructure/            Commands, settings, layout panel, embedded resources, package check
    Themes/                    Colors, control styles and feature templates
    ViewModels/                Shell, navigation, feature rows and pages
    Views/                     Main window and pages
  KH2Trainer.Core/             Game session, bridge protocol, profiles, save backups, asset reader
  KH2Trainer.Twitch/           Twitch channel point rewards: Twitch API, EventSub, effect catalog and queue, OBS overlay
  KH2Trainer.Bridge/           Native C++ bridge (KH2Trainer.Bridge.dll) and build.cmd
tests/
  KH2Trainer.Core.Tests/       Core library and catalog tests (console runner)
  KH2Trainer.Twitch.Tests/     Effect catalog, queue rules, Twitch API, EventSub and overlay tests (fakes, no network)
  KH2Trainer.UiTests/          Offscreen WPF rendering and binding checks
  KH2Trainer.Bridge.Tests/     Native guard tests against synthetic memory, run-tests.ps1
```

`src/KH2Trainer/Data/features.json` is the source of truth for all 358 features: their
command and value slots, ranges and implementation evidence. The bridge sources and this
catalog must change together.

## Requirements

- Windows 10 or 11, x64
- .NET SDK 8 or newer
- Visual Studio 2022 (or Build Tools) with the **Desktop development with C++** workload and a Windows SDK
- Python 3 (only for the user guide in `build.ps1`)

No NuGet packages, test frameworks or third-party libraries are used.

The offline BDX view includes a partial native-call catalog: 1,063 recorded descriptors and
256 behavioral annotations for the pinned executable across all eleven recorded bank slots.
The latest notes cover Gummi object creation, movement and deferred deletion,
mission counters, timers and result transitions, plus the shared state changed by
Actor collision queries. The resolved audience Voice request is described with
its resource and priority conditions. These are offline inspection notes.
Names and side effects are searchable. Recorded table extents do not establish native bounds
or complete behavior of the handlers and their callees.
Details distinguish NULL handlers, uncatalogued entries and context-dependent registration.
Declared operand counts are metadata; they do not validate native accesses or object lifetimes.
Evidence and original-byte verification are linked from the catalog and collected under
`docs/research/bdx-bank-inventory-implementation-20261008`. Descriptions cover effects,
timers, resource and child-VM lifetime, character/form equipment, abilities, camera settings,
object groups and vector operations. Query descriptions identify shared output buffers and
conditions that can leave an earlier result in place. The existing Drive weapon fallback
validates dual-form equipment before requesting the transformation.

## Building

**Visual Studio:** open `KH2Trainer.sln`, set `KH2Trainer` as the startup project and build.
The application project compiles the native bridge automatically (through
`src/KH2Trainer.Bridge/build.cmd`) whenever a bridge source is newer than the DLL, and embeds it.

**Command line:**

```powershell
dotnet build KH2Trainer.sln -c Release
```

For `dotnet build` or Visual Studio, pass `-p:SkipNativeBridgeBuild=true` to use an existing
`src\KH2Trainer.Bridge\bin\KH2Trainer.Bridge.dll` without recompiling it.

**Release package:** from PowerShell in the repository root:

```powershell
.\build.ps1
```

This compiles the bridge, runs the native, core, Twitch and offscreen UI tests, publishes a self-contained
single-file x64 executable and writes the package, user guide, validation logs and a source archive
to `artifacts\packages\<timestamp>`.

The Research folder preserves reports, evidence and verification scripts. Local IDA databases,
analysis working folders and compiled test outputs stay outside the package. Options:

| Option | Effect |
| --- | --- |
| `-FrameworkDependent` | Publish without the .NET runtime (the target needs the .NET 8 Desktop Runtime). |
| `-OutputDirectory <path>` | Write the package to a new folder of your choice. |
| `-AssetGameDirectory <KH collection folder>` | The game installation folder that contains `Image\dt` and an OpenKh extraction in `Modding\openkh`; adds a read-only comparison of decoded retail packages. |

## Tests

| Suite | Run it with |
| --- | --- |
| Native bridge guards (40 suites) | `.\tests\KH2Trainer.Bridge.Tests\run-tests.ps1` (optionally `-Suite LootGuardTests`) |
| Core library and catalog | `dotnet run --project tests\KH2Trainer.Core.Tests -- src\KH2Trainer\Data\features.json` |
| Twitch rewards | `dotnet run --project tests\KH2Trainer.Twitch.Tests -- src\KH2Trainer\Data\features.json` |
| Offscreen UI | `dotnet run --project tests\KH2Trainer.UiTests -- --fixture artifacts\ui` |

Tests use isolated memory and fixtures. Some execute short verified native leaf-function copies
inside a synthetic image or call Windows unwind APIs on private generated code. They do not attach
to the game, change its executable or mod configuration, or touch real save files, and they do not replace visual and
gameplay testing. The offscreen UI checks render every feature tab, the Asset Explorer and Game
Messages without opening a window, and verify that every catalog feature is reachable from a
sidebar section.

## Using the trainer

The sidebar groups the catalog into eight sections (Sora, Combat, Progression, World,
Camera & Display, Gummi Ship, Audio, Advanced), each with tabs. Every tab lists its controls first
and its live values below them. Typed values apply on **Enter** or **Apply**; switches apply as
soon as they are flipped. Search everything with **Ctrl+F**, and pin frequently used features to
**Home** with their star. Features marked **SAVE DATA** change the loaded game; saving in the game
makes them permanent. The generated user guide describes every feature.

Profiles, backups and preferences are stored in `%LOCALAPPDATA%\KH2Trainer`.

### Inspect game scripts offline

In **Asset Explorer**, open a `.bdx` file or a type-3 entry inside a BAR container.
The **Script** tab shows its events, stored instructions, branch and call targets,
and native calls. Choose an event to jump to its entry, or search for an operation,
PC or native call such as `2:95`. For an unnamed script payload, select it and use
**Inspect BDX**. Inspection works while disconnected and reads the selected file.

The decoder follows declared event entries with bounded reads. Diagnostics identify
invalid targets, overlapping instructions and inspection limits. Calls and yields
have conditional continuations; dynamic returns and native callback effects require
runtime state. Undecoded bytes may contain data or other code. This view helps locate
script behavior and compare potential mod targets; it does not execute or modify scripts.

To add a catalog category to a section, edit `src/KH2Trainer/ViewModels/Navigation.cs`. A category
missing there still appears, in a "More" section.

## Twitch channel points

The **Twitch** page (sidebar group STREAM) lets viewers spend channel points to help or hinder
Sora. It needs Twitch Affiliate or Partner status, because only those channels have channel points.

### Setup

1. **Create a Twitch app (once).** In the [Twitch developer console](https://dev.twitch.tv/console/apps/create)
   register an application: any name, OAuth Redirect URL `http://localhost`, category
   *Application Integration*, client type **Public**. Paste its Client ID on the Setup tab.
   (A build can ship with its own Client ID: set `TwitchApp.ClientId` in
   `src/KH2Trainer.Twitch/TwitchSettings.cs`, and streamers skip this step.)
2. **Connect.** Twitch opens in the browser with a short code; confirm it. The trainer only asks for
   `channel:manage:redemptions`. The login is stored encrypted for the Windows user (DPAPI) in
   `%LOCALAPPDATA%\KH2Trainer\twitch-login.bin`.
3. **Switch rewards on.** On the Rewards tab every effect has a switch. On creates the reward on
   your channel right away, off deletes it again. **Edit** changes cost, duration, amount, cooldown,
   limits, title, description and behaviour; changes reach Twitch a moment after you leave the
   field. **Test** runs an effect in the game without Twitch.

Images: click a reward's picture to choose a PNG, JPG, GIF, BMP or WebP file (or leave it empty for
the category colour). The trainer keeps a copy in `%LOCALAPPDATA%\KH2Trainer\TwitchImages` and uses
it in the trainer and the stream overlay. Twitch does not let apps upload reward icons; upload the
same file in your reward dashboard (**Reward dashboard** button) to use it on Twitch too.

### How redemptions run

- An effect runs once the game is in a playable scene. During loading, menus and cutscenes
  redemptions wait and effect timers pause (switchable). A redemption that cannot run within the
  waiting time (default 10 minutes) is refunded.
- Points are only kept once an effect has really happened. Anything that cannot work (full HP,
  nothing to steal, a Gummi effect outside a Gummi mission, an unsupported situation) is refunded
  automatically. Redemptions made while the trainer was closed are refunded at the next connect.
- **Queue:** effects that change the same thing never run at the same time. With the default
  setting, a second Drive Form waits: if Final Form runs and someone redeems Valor Form, Valor Form
  starts as soon as Final Form ends. Alternatives: replace the running effect, or refund.
- **Redeemed again while running:** add the time to the running effect (capped by the longest
  effect setting), refund, or queue it. Both choices can be set globally and per reward.
- Values an effect changed are restored when it ends, but only while the game still shows the
  value the effect set, so a scene change or the streamer's own edit is never overwritten.
- The Live tab shows running effects with their timer, the queue (with a refund button per
  redemption) and recent results. **Stop all** ends everything and refunds what still waits;
  disconnecting from the game and **Disable all effects** do the same.
- Closing the trainer pauses the rewards on Twitch (switchable), so nobody redeems while it is off.

### Rewards

| Category | Rewards |
| --- | --- |
| Help | Heal Player, Refill MP, Full Restore, Refill Drive Gauge, Potion Care Package, Gift a Megalixir, Mystery Gift, Munny Donation, EXP Gift, Strength +1, Regeneration, Unlimited MP, Invincibility, Lucky Streak, Orb Magnet, Super Speed, Eagle Eye, Weaken the Enemy, Valor/Wisdom/Limit/Master/Final Form, Repair Gummi Ship, Clear Enemy Bullets |
| Harm | One HP Left, Drain Drive Gauge, Pickpocket, Potion Thief, Reload Room, Kick Out of Drive Form, Heal the Enemy, Enrage the Enemy, Glass Cannon, Tax Collector, Snail Mode, Fast Forward, Short-Sighted, Antiform |
| Funny | Drive Roulette, Moon Jump, Slow Motion, Fisheye, Tunnel Vision, Upside-Down Camera, Slowpoke Animations, Hyperactive Sora, Color Chaos, Silence!, Ghost Walk, Hacker Mode |
| Annoying | Time Stop, Freeze Frame, Pause!, Lights Out, Flashbang, Déjà Vu, Who Said That?, No Subtitles |

Reward texts can be English or German. Twitch allows 50 custom rewards per channel, so not all
59 can be on at once.

### Stream overlay

The Setup tab starts a small local web page (default `http://127.0.0.1:17290/`, reachable only from
this PC) for an OBS **Browser Source**: running effects with their remaining time, the queue and a
note for each new redemption. Add `?side=left`, `?queue=0` or `?scale=1.5` to the URL to change it.

The effects use the same bridge features as the rest of the trainer; they are covered by synthetic
tests against the real feature catalog, not yet by live gameplay. The Twitch API is tested against
an in-memory fake of Twitch.

## Bridge protocol

Protocol version 3 carries 512 value and capability slots and stamps each command with the
host's `GetTickCount`-compatible timestamp. Unstarted commands expire after eight seconds; the
five-second host timeout uses the timestamp's age, including after the game was suspended.

The bridge stays loaded until the game exits. Restart the game before testing a different trainer
build: the trainer rejects a mismatched resident bridge instead of mixing old native code with a
new feature catalog.

## Research archive

### Current analysis and Crowd Control checks (0.12.10)

`docs/research/` contains the new IDA evidence and review notes. Packages include these files
under `Research/`. The read-only **Advanced > Player control** tab exposes verified character
identity, field state and the reasons input is blocked. The bridge publishes these observations
on the game thread; the host rejects missing, malformed or more than one-second-old observations.

Crowd Control now distinguishes loaded resources from actual player control. Menus, native
events, transitions, dead/missing players, input locks and unsupported character contexts hold
pending effects. With timer pausing enabled, returning control does not charge the preceding
paused interval. A freeze reward can count through its own verified freeze; external blockers
still pause it. The Live tab labels paused effects and shows the reason in the timer tooltip.

Script-owned mission-clock pause bit 2 now remains compatible with player control:
the native script can stop the mission counter while ordinary input still runs.
Other unknown clock owners remain conservative. The bridge also checks the actual
FIELD_COMMAND vtable and role-specific update callbacks before publishing control.
See `docs/research/player-input-classification-20261007` for the original-byte
evidence and isolated checks; this does not broadly enable input during events.

| Player | Current reward policy |
| --- | --- |
| Sora, including supported forms | Each reward keeps its individual native resource and state checks. |
| Roxas, including dual-wield Roxas | Healing, full restore, one HP, regeneration, unlimited MP, MP refill, damage guard, Super Speed, Snail Mode, Moon Jump and the explicitly shared audio/display/caption rewards are permitted when their own checks pass. Drive, animation and other unverified rewards wait. |
| Rescue Mickey | Same conservative shared-reward list. Drive transitions remain unavailable. |
| Unknown or another actor class | Player-dependent rewards wait; no inferred Sora layout is used. |

This is a static compatibility policy, not a claim that every reward has been playtested with
each character. Gummi rewards retain their separate mission checks. Native events may allow
some player input; this build conservatively waits through those events. The observations do
not yet classify every minigame or every individual combat animation.

The existing second-Keyblade fix was rechecked: Valor, Master and Final keep a valid form weapon
or assign the validated main Keyblade before starting the native loader. A switch first reverts
and then revalidates the new Sora actor and its equipment. Forms do not require an unlock, Drive
bars or the usual party composition. Roxas/Mickey and mismatched target model identities are
rejected before a transition. The assigned form weapon can be included in a normal in-game save.
The reported Final Form crash has not been reproduced in a live game with this exact build;
the regression checks use isolated memory and a simulated native weapon consumer.
Before every native form start or revert, the bridge also checks the bounded `sklt`
attachment table for each hand that the engine will actually attach. It uses the
selected form model's skeleton key, preserves native skip branches, and repeats
the check after Revert before beginning the next form. The additional loader
analysis in `docs/research/drive-preconstructor-20261007` shows that BAR parsing
already occurs before the form constructor. The native cancellation path does
not restore all earlier form and partner state, so a late resource rejection
hook has not been added. Effective MDLX/MSET validation needs an earlier staging
point and a proven failure path; later native allocations remain separate work.
The raw staging investigation in `docs/research/drive-raw-staging-20261007`
also found that the native loader can discard overlapping resource entries and
invoke a resource handler before returning. Its returned size does not prove a
complete read or successful decompression. Calling that loader as a validation
probe would already have side effects; effective bytes need independent bounded
validation first.

The effective-file investigation in `docs/research/drive-effective-bytes-20261007`
also traces the supported Panacea loader: its `raw` override is a packaged record,
and loose-file providers have their own priority. A failed selected override must
be reported as invalid; validating a lower-priority retail file would not describe
the bytes the game tries to load. The independent Core reader now checks an explicit,
verified offline provider manifest and returns owned primary bytes with their source
and hashes. It checks raw/dev/mod/extract/package priority, bounds decoding and
rejects a corrupt selected override. See `docs/research/effective-asset-reader-20261007`.
This reader is not yet bound to a running game's provider/cache state and is not used
to authorize Drive construction.
The follow-up in `docs/research/drive-provider-binding-20261007` traces separate
primary and remaster reads. A future live handoff must bind both to the same owned
resource set; validating only the primary file cannot cover later remaster selection.

HP and MP commands now check native player control immediately before dispatch,
including continuous refill ticks. HP also checks the HUD and any selected HP-bar
animation rows/tracks. Native scripted minimum HP remains effective. Full restore
checks both HP and MP prerequisites before either is changed. MP-only rewards refund
at admission when the controlled character has no MP gauge; full restore can still heal HP.
An already running Unlimited MP reward pauses its timer, sustain and extensions
while the MP gauge is absent or invalid. This resource pause also applies when
general control-based timer pausing is disabled. Cleanup can still release the
owned toggle. Time resumes only after consecutive usable observations.

The four manual **Sora > Movement** controls now also accept verified prologue
Roxas and rescue Mickey actors. They write the current actor once. Collision and
targeting retain their Sora-only checks.

Eagle Eye and Short-Sighted now capture search scale and lock-on break distance
together. Native callers can change break distance independently, so cleanup restores
the exact original pair only while both values still match the reward. A later change
ends the reward and is preserved. No scalar sustain rewrites the new settings.
Missing acknowledgements retain conditional cleanup, including beyond the normal
restore retry window. Definite pre-write native rejection is kept distinct from a
timeout. These rewards require fresh control and a complete pair for paid time even
when general timer pausing is disabled. Same-value native changes remain invisible
to value comparison. See `docs/research/lockon-pair-ownership-20261007`.

Super Speed, Snail Mode and Moon Jump use a native movement journal. A constructor and
destructor observer assigns an identity to each supported actor lifetime, including
when an address is reused. The bridge checks all selected values before applying
the pair and returns its captured originals in a correlated receipt. Each actor
gets its own originals. Missing acknowledgements remain unresolved until recovered;
the host does not infer a successful change from a later snapshot.

These three rewards can follow Sora, Roxas and rescue Mickey. Their timers pause
while values, identity, control or application acknowledgement are unavailable.
A character change does not charge the preceding interval. If Sora remains alive
while Mickey is controlled, Sora's cleanup stays pending until that same actor
can safely be restored. Later script values are preserved unless the effect
explicitly captures them as a new valid baseline before reapplying. Lost lifetime
observation or a partial write leaves ownership uncertain and prevents automatic
restoration. The journal has bounded capacity and refuses new work when unresolved
records fill it. See `docs/research/actor-lifetime-20261007` and
`docs/research/movement-ownership-20261007` for the contract and synthetic checks.

Disconnect cleanup for these movement rewards now checks native player control
independently of the trainer heartbeat. Previously an expired heartbeat also
blocked restoration, leaving effects pending until reconnection. Menus, events,
transitions, unavailable identity and external value changes still govern cleanup;
new effects and reapplication still require a fresh host. The joint regression
uses the real bridge, movement journal, gameplay and identity checks against
private synthetic memory. See `docs/research/movement-cleanup-20261008`.

Position bookmarks now use the same actor lifetime observer. Reusing an actor's
address cannot make an old bookmark valid again. Collision bypass also pins its
original actor: release waits while that actor cannot be verified, blocks another
activation, and runs when the same actor returns. A proven destruction discards
the lease without writes. Pending cleanup continues after host-heartbeat expiry.
Ghost Walk ends with the native bookmark return and reports a refused return in
the activity log. Its coordinate-write and room-reload fallbacks were removed.
See `docs/research/player-position-ownership-20261007` for tests and limits,
including the shared manual bookmark and unresolved cleanup after observer failure.

The audit in `docs/research/reward-ownership-audit-20261007` maps all 59 rewards to
their actual native state. Several temporary STATUS values still need ownership
that also accounts for native status rebuilds on the same actor.
The follow-up `docs/research/status-rebuild-ownership-20261007` identifies status
initialization, rebuild, script writes, pool reset and release as distinct ownership
boundaries. Actor lifetime alone cannot cover them. Those temporary STATUS rewards
have not been given a blanket Roxas/Mickey compatibility expansion.
`docs/research/status-entry-observation-20261007` adds a fixed-build entry planner
and real Windows unwind tests on private synthetic code. A plain indirect jump
tail incorrectly triggered Windows epilog handling; the checked plan uses a
volatile-register jump with matching unwind records. No entry hooks are installed.
`StatusRevisionLedger.h` implements the separate pool/allocation/field revisions.
The worker follow-up in `docs/research/status-worker-observation-20261007` proves
a motion-worker path into synchronous BDX event 27. Metadata therefore admits
overlapping threads while retaining per-thread callback order.

The STATUS prerequisites now include exact native code/import checks, registered
original-call trampolines, typed native wrappers, a conservative complete-stack
check for pre-existing writers, and a coordinator that binds those components in
order. Failed resumes remain pending before any metadata lock is entered. Typed
field transactions retain exact values and writer revisions, so a native rebuild
or intervening manual write prevents stale cleanup, even when the value is equal.
See the `status-*-20261008` research folders for tests and explicit limits.

These components are not installed in TrainerBridge. Actor binding and lifetime
must remain stable throughout a field transaction; the existing metadata pin
alone does not establish that. Fresh native evidence identifies additional STATUS
rebind stores, parked/restored current-player pointers, earlier task frees and
separate arena return paths. The field load task also yields through fibers.
A complete lifetime and execution contract is still needed before a real Actor
provider and typed STATUS IPC can be connected. See the three
`actor-*-20261008` research folders. These prerequisites remain uninstalled in
v0.12.12. The earlier movement disconnect-cleanup correction is retained. The
offline BDX inspector's decoder agrees with the independent
native-derived parser for all 4,480 instructions in two selected original scripts,
including their branch and call edges. The bounded asset scan identifies actual
stored STATUS rebind calls in those scripts. The follow-up `bdx-rebind-operands-20261008`
traces their selected Event0 setup prefixes and wrapper writes under stated normal
execution assumptions. `motion-event27-20261008` identifies contact/IK data as the
source of Event27, verifies a B_LK120 retail witness, and shows that an intact
Actor+4 self pointer can satisfy the wrapper layout. It does not establish a
worker-thread STATUS rebind. `app-timer-dispatch-20261008` traces timer message74
through the active Actor list and concrete descriptors into synchronous BDX Event10;
selected message74 script effects remain open. See the individual reports for
original-byte evidence, reproduction and lifetime limits.

The HP damage guard now uses the actual Sora/Roxas and rescue Mickey callbacks.
It binds protection to the observed actor lifetime, role and scene. Only negative
main-HP changes through those callbacks are blocked; healing is forwarded unchanged.
A blocked callback also skips its damage-dependent Drive/MP gains, HUD update and
zero-HP dispatch. Hit reactions and direct script writes still apply.

The Crowd Control reward owns its activation explicitly. Its timer requires fresh
confirmed protection on the current controllable character; changing characters
or rearming does not charge the preceding interval. Input-blocked hit reactions
may still be protected while paid time is paused. Ending the reward releases only
its own activation, preserving a later manual activation. A lost acknowledgement
keeps cleanup pending until a conditional release is acknowledged or a fresh new
bridge identity proves the old activation unreachable. This uses the ordinary
serialized command channel; it does not supply movement-journal receipts.

Disabling the guard releases the actor reference. Transparent forwarding callbacks
remain installed, with their module pinned until the game exits, so an already
dispatched callback always retains its original function. Foreign callback slots
are preserved and changed native code disables protection. See
`docs/research/player-damage-guard-20261007` for evidence, tests and limits.

Further static evidence is recorded in `docs/research/actor-scale-20261007`:
actor scaling feeds both the model transform and collision-shape centers, while
the inspected shape converter copies radii separately. The follow-up in
`docs/research/actor-scale-writers-20261007` traces scripted axis changes and
unscaled collision radii. Another apparent scale field is a disappearance ramp;
reaching zero can initiate player cleanup and save back HP/MP/Drive. A shrink/grow
reward therefore still needs collision and ownership work before implementation.
The next contract in `docs/research/actor-scale-contract-20261007` traces the BDX
VM's indirect writes, actor attachments and the motion-worker completion barrier.
A positive visual factor at Actor+60 is a candidate for a future size reward;
collision radii would need a separate explicit policy.
The projection follow-up in `docs/research/actor-scale-projection-20261007` resolves
both native type9 motion formats and their root-motion callbacks, including Float32
arguments omitted by the saved decompiler prototypes. The new Core
`MotionPayloadReader` and `MotionRootEvaluator` bound the copied root paths for
both formats, preserve Float32 arithmetic order, and reject invalid spans,
nonfinite intermediates and nonprogressing wrap loops. Their outputs explicitly
remain `OfflineMotionProjection`; they do not validate all skeletal/IK structures
or bind native resource lifetimes. The read-only sample covered 215 retail type9
entries and 1,075 frames. Native integration and per-actor cleanup remain required
before a timed Tiny/Giant reward is released. See
`docs/research/motion-payload-bounds-20261007`.

Color Chaos captures the original color mode and strength as one coherent value.
Its native restore compares the current pair and applies the original pair under
the presentation mutex only if the effect's pair still matches. Later different
filter settings are preserved, and brightness is untouched. An external writer
that sets the exact same pair is indistinguishable from the effect's own value.
The paired readout and conditional action are under **Advanced > Graphics**.

Restart KH2 before connecting this build so the new embedded bridge can load. An older resident
bridge cannot supply the required protocol-4 movement journal.

### Coverage and preserved baseline

The analysis is **not complete**. The preserved audit (4 October 2026) inventoried 36,451 native
functions and recorded specific static claims for 1,712 of them. The current reconciliation in
`docs/research/coverage/summary.json` adds the new addressed findings without counting overlapping
functions twice. Its address inventories and source manifest separate exported text, complete
assembly, specific findings and unproven semantic completeness. A claim about a function does
not prove every branch, caller or runtime state. No complete-analysis percentage is asserted.

`scripts/update-analysis-coverage.py` rebuilds the inventories from a hash-pinned portable
baseline and current evidence; its parser/deduplication tests and deterministic replay receipt
are included in `docs/research/coverage/`. The original baseline's per-address records were
recovered from the matching old audit because the earlier source archive omitted them.

`docs/legacy/audit-summary-v011.json` preserves that audit. The immutable
`docs/legacy/KH2_Trainer_v0.11_Source.zip` preserves the earlier source, tests and research
(SHA-256 `35e3cb99435e447af21c321799ad8d50145372827410d9f11bd5eb21289c2d5d`). It is historical
evidence; `src/` remains the current implementation. Remaining work includes broader character
compatibility, event/minigame classification, resource-content validation and live gameplay
validation. Synthetic success does not establish a crash-free game session.

### Earlier evidence in Git history

The reverse-engineering evidence behind the catalog (IDA exports, contracts, validation reports
and the per-domain catalog sources) was removed from the working tree to keep the repository
small. Source comments that cite `research archive (see README)` refer to it. To look at it, restore
it into the working tree only (nothing is staged; `work/` is ignored, so it is not committed again):

```powershell
git restore --source=ffac525 --worktree -- work/trainer/research
```

Commit `ffac525` is on `main` of [Dekirai/KH2Trainer](https://github.com/Dekirai/KH2Trainer).
