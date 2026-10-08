# Drive provider binding — 2026-10-07

## Result

The missing link is a binding between the complete validated resource graph and the exact bytes consumed by the native loader. The shipped reader remains **OfflineManifestBinding**. This round identifies a concrete handoff design and the remaining implementation conditions; it does not add a runtime guard.

Fresh evidence contains **56 complete bodies, 4,386 instructions, 17,692 original code bytes and 24 vtable bytes**, divided into retail and the supported Panacea module. There are **36 retail and 13 Panacea address-specific claims**. These overlap earlier work and must be deduplicated. Complete exports do not imply complete semantic review.

## What changed our understanding

### Primary bytes are only part of the load

Panacea `FEB0` reads the selected primary raw or loose asset and closes its file before calling retail `12F070`. The resulting `ResourceEntry` constructor `12CD80` then loads replacement payloads, names and IDs. Panacea `114A0` independently selects and opens those files again.

In the raw path, `114A0` combines **cached row offsets, sizes and modes** with a **freshly read raw header and fresh file content**. A file can therefore change between primary and replacement reads. A primary hash cannot bind this later data. Loose replacement paths are also selected and reopened separately.

### Cache identity is a filename

Panacea's map uses the selected PackageFile's cached name at +344. Each 72-byte map node holds a string at +16 and a vector at +48/+56/+64. Rows are 48 bytes. Cache hits can skip discovery; assignments can overwrite or reallocate rows while preserving the same filename and node.

`11260` returns borrowed row pointers. Neither that pointer nor the node address carries a content generation. Cache accessors allocate temporary strings and some fallback paths temporarily restore/reapply detour bytes, so they are unsuitable as casually invoked read-only probes.

### Serialization is narrower than a resource lease

Retail `107180` creates a named semaphore with initial/max count 1. It does **not** start the resource worker, despite its inherited IDB comment. `FDDC0/FDCB0` wait/release this nonrecursive semaphore.

`3F9850` holds it around the primary loader and package-mode registration. Its overlap retirement runs before the wait; its BAR association update runs after release. The semaphore does not freeze the filesystem. Acquiring it before calling the same loader would cause a second wait.

The actual worker is established by `3A09C0 → 15EC70 → 16C9D0(CreateThread) → 16C9B0 → 15ED20 → 3A0C60`. A separate priority-400000 scheduler task `3A0790` handles completion. Timing `15EE10` wakes the worker. The waiter count represents scheduling, not ownership or generation.

CFileMan cleanup closes handles without joining this worker. Package teardown frees providers before AppInterface destruction clears the app global. These inspected paths do not establish a general safe shutdown/quiescence API.

### Native registration owns data and has side effects

Full ASM confirms `12F070(name RCX, length EDX, payload R8)`; its old one-argument pseudocode is incomplete. `12E5C0` constructs and publishes a resource entry and can invoke registered handlers.

A retained replacement buffer becomes `ReplaceEntry+96`; destructor `129D30` releases it through the retail aligned allocator. Region filtering can free it earlier. ResourceEntry destruction can invoke a conditional name-table writer. Primary storage has a different owner and is not freed by that destructor itself.

The earlier preconstructor report remains applicable: worker BAR preparation and game-thread fixups occur before the final Drive checkpoint. NativeBegin has already changed transition state. Late rejection and null constructor returns are not safe rollback mechanisms.

## Tractable future implementation

Use an **owned complete resource ticket graph**, validated before NativeBegin. It must contain primary bytes and the full ordered replacement set with names, IDs, sizes, digests and explicit allocation ownership.

The normal loader handoff before Panacea cache preparation/native registration is the concrete intervention point. A scoped ticket must supply the primary and replacement callbacks throughout registration, avoiding later disk/cache reselection. Registration still runs once in its native context. Generated request/provider/resource identities must bind publication, relocation and retirement to the ticket.

This is a design proposal. Safe hook-chain installation, observer bootstrap for already-loaded assets, complete typed validation, exceptional allocation ownership and any post-Begin rollback remain unimplemented. Merely holding the semaphore, repeating a disk hash, requiring an already-loaded form or checking after loading does not close those gaps. The exact requirements and failure matrix are in [contract.json](contract.json).

## Verification

Run:

```powershell
py -3.13 -X utf8 docs/research/drive-provider-binding-20261007/verify.py
```

Optional `--retail` and `--panacea` supply local copies of the exact original modules. Verification checks module SHA256, PE-backed bytes, full dedicated ASM and pseudocode pagination/counts, canonical spans and claim references. It opens no process and invokes no loader.

No product, tests, package, coverage, IDB, live-game or save changes were made. See [verification.json](verification.json), [report.json](report.json) and [evidence.json](evidence.json).
