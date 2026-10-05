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
  KH2Trainer.Bridge/           Native C++ bridge (KH2Trainer.Bridge.dll) and build.cmd
tests/
  KH2Trainer.Core.Tests/       Core library and catalog tests (console runner)
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

**Release package:** from PowerShell in the repository root:

```powershell
.\build.ps1
```

This compiles the bridge, runs the native, core and offscreen UI tests, publishes a self-contained
single-file x64 executable and writes the package, user guide, validation logs and a source archive
to `artifacts\packages\<timestamp>`. Options:

| Option | Effect |
| --- | --- |
| `-FrameworkDependent` | Publish without the .NET runtime (the target needs the .NET 8 Desktop Runtime). |
| `-OutputDirectory <path>` | Write the package to a new folder of your choice. |
| `-AssetGameDirectory <path>` | Also compare decoded retail packages with an existing OpenKh extraction (read-only). |

To build with an existing bridge DLL without recompiling it, pass `-p:SkipNativeBridgeBuild=true`.

## Tests

| Suite | Run it with |
| --- | --- |
| Native bridge guards (27 suites) | `.\tests\KH2Trainer.Bridge.Tests\run-tests.ps1` (optionally `-Suite LootGuardTests`) |
| Core library and catalog | `dotnet run --project tests\KH2Trainer.Core.Tests -- src\KH2Trainer\Data\features.json` |
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
small. Source comments that cite `research archive (see README)` refer to it. Restore it with:

```powershell
git checkout 672ac3f -- work/trainer/research
```
