# Effective asset byte reader

The Core now resolves and reads owned primary asset bytes from an explicitly verified **offline** provider manifest. It does not load assets into the game or authorize a Drive transformation.

## API

`EffectiveAssetManifest.VerifyAsync` checks the exact supported retail EXE and, when overrides are declared, Panacea DLL SHA256. The caller supplies already resolved absolute UTF-16 roots ending in `kh2`, ordered HED/PKG descriptors and each package's decode flag. Optional configuration evidence contains explicit expected file hashes. The factory copies input lists before its first await and exposes read-only collections. It neither discovers a running process nor assumes that settings files describe current native state.

```csharp
var manifest = await EffectiveAssetManifest.VerifyAsync(new() {
    RetailExecutablePath = executablePath,
    PanaceaLibraryPath = supportedPanaceaPath,
    ModRoot = resolvedModKh2Root,
    DevRoot = resolvedDevKh2Root, // null or empty disables this source
    ExtractRoot = resolvedExtractKh2Root,
    Packages = orderedPackages, // explicit (HeaderPath, PackagePath, DecodeEnabled)
    PlatformTransformEnabled = true
}, cancellationToken: cancellationToken);

OwnedAssetBytes asset = await new AssetEffectiveByteReader(manifest)
    .ReadAsync("obj/P_EX100.mdlx", cancellationToken);
// asset.BindingStrength is always OfflineManifestBinding.
```

The immutable manifest hash includes verified file identities/hashes, roots, provider order, decode/transform flags and limits. It is an identity for these declared offline inputs, not evidence of runtime adoption. The result reports selected source identity, provider and HED ordinals, record offset, exact matched name bytes, metadata/content SHA256 and manifest SHA256. Returned data remains owned after source handles close. Loose data has no record metadata; its metadata digest is SHA256 of an empty byte sequence.

## Selection and decoding

1. `modRoot/raw/<name>`: standalone PKG record.
2. `devRoot/<name>`: plain original bytes, if configured.
3. `modRoot/<name>`: plain original bytes.
4. `extractRoot/<name>`: plain original bytes, if configured.
5. Ordered retail packages: exact MD5 name lookup, then ASCII lowercase of only the final slash component within that same provider.

Only absent files or directory candidates advance priority. An existing unreadable, empty, corrupt, ambiguous or oversized selected source fails. It cannot silently select valid bytes from a lower provider. Duplicate matching HED rows are rejected rather than claiming an unambiguous native selection. MD5 reproduces name lookup; it is not the integrity hash.

`AssetPackageCodec.InspectRecord` is shared by the existing archive explorer and the new standalone raw-record path. Both use the same bounded metadata/remaster parser and `DecodeBoundedAsync`; no synthetic HED is created. Existing explorer behavior, record locators, HED revalidation and remaster extraction are retained. The small `AssetSliceStream` change adds an optional `leaveOpen` parameter whose default preserves previous ownership.

Loose overrides never enter the transform/decoder. Raw records decode with the manifest's independent platform-transform flag. Retail uses each provider's decode flag: disabled decoding reads the declared original length unchanged and suppresses both transform and inflation. Enabled decoding bypasses these operations for lengths up to 16; positive modes above that length use the bounded stored length and zlib, `-1` uses the prefix transform, and `-2` is plain. Unsupported modes and zero-size selected assets are rejected. Legacy explorer zero-size handling remains unchanged.

All metadata/remaster physical spans are checked even when only primary bytes are requested. Zlib output must have exactly the declared length, valid checksum/trailer and supported alignment padding. This checks container integrity, not model, bone, animation, texture or BAR semantics.

## Limits and consistency

The manifest accepts at most 32 package providers and 32 extra evidence files. Enumeration is bounded independently of a caller's reported list count. Fingerprinted evidence files have a 1 GiB limit. HED metadata is bounded in aggregate; entry, record metadata, remaster count and decoded allocations use `AssetReadLimits`. The reader does not recurse into BARs; the existing archive API retains its bounded recursive inspection.

Names require 1–1024 strict ASCII characters with forward slashes. Absolute local UTF-16 roots are supported. Traversal, alternate streams, device names, UNC, reparse paths and ambiguous Windows suffixes are rejected. No locale-dependent name conversion or relative-root guessing occurs.

Each read revalidates provider/configuration and HED hashes, file identities and lengths. It holds ordinary read handles and ancestor-directory handles until final checks, rechecks selected metadata, and checks previously absent higher sources again. All declared manifest providers are revalidated, so a stale lower provider can conservatively invalidate a read even when an override would win.

These checks are not an atomic filesystem snapshot: a new override can appear after the final check. PKGs carry identity/size/timestamps rather than full multi-gigabyte content hashes. The returned selected metadata and decoded copy have their own SHA256. No claim is made against all memory-mapped or privileged writers, nor about later native reads.

## Verification

The Core runner passed **867 checks, 0 failures**, including **119 new reader checks** and 748 existing checks, using the real feature catalog. No compiler warnings were emitted. Tests use temporary synthetic files and independently fixed decoder vectors; no game, mod or save files are written. There was no complete application build or live-game test.

```powershell
dotnet run --project tests/KH2Trainer.Core.Tests/KH2Trainer.Core.Tests.csproj -c Release -- src/KH2Trainer/Data/features.json
py -3.13 -X utf8 docs/research/effective-asset-reader-20261007/verify.py
```

The production factory rejects unknown binaries. Positive synthetic tests use the same internal verifier with fixture hashes through the test friend assembly. A second internal seam injects changes at the pre-publication boundary. Neither seam appears in the public reader API.

See `report.json` for test categories, limits and machine-readable provenance. The independent review is recorded in `independent-review.json`/`.md`. It found one pre-normalization UNC path gap; this was fixed and covered by seven direct path regressions. The reviewer then found no remaining blocker in the inspected code. Test execution is the author's run, while the independent review was static.

## Research boundary

This implementation reuses the preceding `drive-effective-bytes-20261007` research: 31 complete functions, 6,348 instructions, 26,813 original code bytes and 4,057 original data bytes. It introduces **no new native function claims**. Source and evidence fingerprints are separate from native semantic coverage.

`OfflineManifestBinding` remains the only result strength. Successful reading does not establish native fake-package metadata ownership, cached lookup state, loaded hooks, allocation success, deep asset validity or the bytes that an asynchronous loader will later consume. Closing those conditions requires a separate runtime contract.
