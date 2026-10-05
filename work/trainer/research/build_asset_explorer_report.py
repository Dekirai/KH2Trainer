import hashlib
import json
import pathlib

root = pathlib.Path(__file__).resolve().parents[3]
research = root / 'work/trainer/research'
sources = ['trainer/KH2Trainer.Core/AssetArchiveReader.cs',
           'trainer/KH2Trainer.Core/AssetExplorerModels.cs',
           'trainer/KH2Trainer.Core/AssetPackageCodec.cs',
           'trainer/KH2Trainer.Core/AssetFileAccess.cs',
           'trainer/KH2Trainer.Tests/AssetExplorerTests.cs',
           'work/trainer/tests/AssetExplorerHarness/AssetExplorerHarness.csproj',
           'work/trainer/tests/AssetExplorerHarness/Program.cs']
hashes = {p: hashlib.sha256((root / p).read_bytes()).hexdigest().upper() for p in sources}
log = (research / 'asset_explorer_test_run.txt').read_text(encoding='utf-8-sig')
passed = [line for line in log.splitlines() if line.startswith('PASS ')]
assert not any(line.startswith(('FAIL ', 'UNHANDLED ')) for line in log.splitlines())
assert '213 passed, 0 failed.' in log
report = json.loads((research / 'asset_explorer_deep.json').read_text())
report['scope'] = 'Offline asset explorer Core implementation and format research for v0.7. Existing v0.6 packages and files were not modified.'
report['status'] = 'Core complete; 105 synthetic checks plus 108 private retail checks pass. Root owns WPF integration and final release verification.'
report['source_hashes'] = hashes
report['api'] = 'asset_explorer_api.txt'
report['tests'] = {'total': len(passed), 'synthetic': 105, 'retail_indices': 6,
                   'retail_original_payloads': 23, 'retail_remaster_payloads': 79,
                   'failed': 0, 'log': 'asset_explorer_test_run.txt',
                   'log_sha256': hashlib.sha256((research / 'asset_explorer_test_run.txt').read_bytes()).hexdigest(),
                   'notes': ['Real assets were read from the local installation; they are not bundled as fixtures.',
                             'Raw remaster comparisons validate logical bytes and permitted loose alignment padding separately.']}
report['limitations'] = [
    'Structural BAR validation and descriptive type labels do not fully decode models, textures, scripts or audio.',
    'Retail payload comparisons are selected real fixtures, not exhaustive decompression of every record.',
    'Version1 disk BARs with unrelocated base0 and observed package modes -2/-1/positive are supported; unknown modes fail explicitly.',
    'Package payloads decode into a bounded memory buffer before exposure; prefix preview of a package still validates the selected complete payload.',
    'No source writes, package rebuilding, script execution, process hooks or native game function calls occur in the Core.',
    'Identity and metadata guards prevent stale locators; raw payload bytes are not cryptographically authenticated against an adversary who can rewrite content and restore metadata.',
    'UI render checks and final package integration are owned by Root; this subagent performed no UI/live action.'
]
report['implementation_facts'] = [
    'Signed negative counts/lengths, overflow and out-of-source spans are rejected before allocations and extraction.',
    'BAR children carry exact parent metadata digests; HED and package metadata are revalidated before decoding.',
    'Windows volume/file ID, creation/write times and size are captured and checked under read-only source handles.',
    'Export keeps existing directories open against replacement, creates a new temporary file, and atomically moves without overwrite.',
    'Destination checks reject Windows aliases, device/ADS names, reparse paths, protected folders and source game root.',
    'Zlib decoder enforces exact output length, verified Adler checksum and at most15 padding bytes; cancellation reaches reads, inflate and checksum work.',
    'Opaque immutable descriptors and bounded owning streams preserve lifetime across nested containers.'
]
(research / 'asset_explorer_deep.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
text = '''OFFLINE ASSET EXPLORER — v0.7 CORE COMPLETE

Four new Core files implement read-only disk BAR and retail HED/PKG browsing,
nested payload locators, signatures/prefix inspection and selected extraction to
an explicitly chosen new file. There is no bridge or game-process dependency.
The English dark WPF integration is owned and independently tested by Root.

VALIDATION
213 checks passed,0 failures:105 synthetic,6 retail indexes,23 exact original
payload comparisons and79 remaster comparisons. Uncompressed remaster fixtures
from OpenKh can include16-byte alignment padding; logical bytes and allowed tail
padding are checked separately. No copyrighted fixtures are distributed.
Core and isolated test harness built with0 compiler warnings/errors.
Full log: asset_explorer_test_run.txt. API: asset_explorer_api.txt.

Meaningful cases include nested relative offsets, aliases/empty entries, arbitrary
tag bytes, malformed/negative/oversized metadata, >4GiB offsets, native prefix
transform tails, checksum/trailer/output-length corruption, stale metadata and
same-length/timestamp file replacement, handle release, existing target protection,
Windows path aliases, protected roots and in-flight cancellation cleanup.

FORMAT EVIDENCE
17 complete native functions /1698 ASM instructions support the BAR, HED/PKG and
prefix-transform contracts. Fresh evidence is retained in the three
asset_explorer_deep_*evidence.json files; per-address findings remain in the JSON.
The structural loose corpus census found90400 files,51109 BARs (14257 nested),
463441 entries and3222 shared spans. All46076 records in the six installed HED
indexes were read at metadata level; the local exact name dictionary resolves38245.
These census counts are not claims of semantic decoding for every contained asset.

PRACTICAL USE AND LIMITS
Locate named or unknown-hash retail resources, inspect exact BAR tags/types/links,
open nested containers and export original/remastered payloads for external tools.
The implementation preserves the logical length; it does not append alignment
padding to exported raw remasters. No package rebuilding, game-file mutation,
3D renderer, texture converter or script execution is included.
Observed disk BAR version1 and package modes-2/-1/positive are supported. Unknown
formats and size limits fail explicitly. Package decode uses one bounded decoded
buffer; selecting a preview validates the complete selected compressed payload.
Source identity and metadata hashes prevent stale offsets. They do not turn raw
game assets into authenticated content against arbitrary hostile filesystem actors.

SOURCE OWNERSHIP
Only the four new Core files, one new test file and own new research/harness files
were edited. MainViewModel, XAML, shared build scripts and Program.cs were not
edited by this subagent. Existing v0.6 packages/reports remain unchanged. Historical
incomplete drafts stay outside product projects under work/trainer/drafts.

SOURCE HASHES
'''
text += '\n'.join(f'{value}  {key}' for key, value in hashes.items()) + '\n'
(research / 'asset_explorer_deep.txt').write_text(text, encoding='utf-8')
print(json.dumps({'tests': report['tests'], 'source_hashes': hashes}, indent=2))
