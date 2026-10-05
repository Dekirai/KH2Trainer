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

`src/KH2Trainer/Data/features.json` is the source of truth for all 340 features: their
command and value slots, ranges and implementation evidence. The bridge sources and this
catalog must change together.

## Requirements

- Windows 10 or 11, x64
- .NET SDK 8 or newer
- Visual Studio 2022 (or Build Tools) with the **Desktop development with C++** workload and a Windows SDK
- Python 3 (only for the user guide in `build.ps1`)

No NuGet packages, test frameworks or third-party libraries are used.

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
to `artifacts\packages\<timestamp>`. Options:

| Option | Effect |
| --- | --- |
| `-FrameworkDependent` | Publish without the .NET runtime (the target needs the .NET 8 Desktop Runtime). |
| `-OutputDirectory <path>` | Write the package to a new folder of your choice. |
| `-AssetGameDirectory <KH collection folder>` | The game installation folder that contains `Image\dt` and an OpenKh extraction in `Modding\openkh`; adds a read-only comparison of decoded retail packages. |

## Tests

| Suite | Run it with |
| --- | --- |
| Native bridge guards (27 suites) | `.\tests\KH2Trainer.Bridge.Tests\run-tests.ps1` (optionally `-Suite LootGuardTests`) |
| Core library and catalog | `dotnet run --project tests\KH2Trainer.Core.Tests -- src\KH2Trainer\Data\features.json` |
| Twitch rewards | `dotnet run --project tests\KH2Trainer.Twitch.Tests -- src\KH2Trainer\Data\features.json` |
| Offscreen UI | `dotnet run --project tests\KH2Trainer.UiTests -- --fixture artifacts\ui` |

All tests use synthetic memory and fixtures. They never run the game's code, change the game
executable or mod configuration, or touch real save files, and they do not replace visual and
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
| Help | Heal Sora, Refill MP, Full Restore, Refill Drive Gauge, Potion Care Package, Gift a Megalixir, Mystery Gift, Munny Donation, EXP Gift, Strength +1, Regeneration, Unlimited MP, Invincibility, Lucky Streak, Orb Magnet, Super Speed, Eagle Eye, Weaken the Enemy, Valor/Wisdom/Limit/Master/Final Form, Repair Gummi Ship, Clear Enemy Bullets |
| Harm | One HP Left, Drain Drive Gauge, Pickpocket, Potion Thief, Reload Room, Kick Out of Drive Form, Heal the Enemy, Enrage the Enemy, Glass Cannon, Tax Collector, Snail Mode, Fast Forward, Short-Sighted, Antiform |
| Funny | Drive Roulette, Moon Jump, Slow Motion, Fisheye, Tunnel Vision, Upside-Down Camera, Slowpoke Animations, Hyperactive Sora, Color Chaos, Silence!, Ghost Walk, Hacker Mode |
| Annoying | Time Stop, Freeze Frame, Pause!, Lights Out, Flashbang, Déjà Vu, Who Said That?, No Subtitles |

Reward texts can be English or German. Twitch allows 50 custom rewards per channel, so not all
59 can be on at once.

### Stream overlay

The Setup tab starts a small local web page (default `http://localhost:17290/`, reachable only from
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

The reverse-engineering evidence behind the catalog (IDA exports, contracts, validation reports
and the per-domain catalog sources) was removed from the working tree to keep the repository
small. Source comments that cite `research archive (see README)` refer to it. To look at it, restore
it into the working tree only (nothing is staged; `work/` is ignored, so it is not committed again):

```powershell
git restore --source=ffac525 --worktree -- work/trainer/research
```

Commit `ffac525` is on `main` of [Dekirai/KH2Trainer](https://github.com/Dekirai/KH2Trainer).
