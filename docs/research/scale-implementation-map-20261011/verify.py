"""Read-only verification of the implementation map and existing test receipts."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'src/KH2Trainer.Core').is_dir())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
load = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
count = 0


def check(ok, reason):
    global count
    count += 1
    if not ok:
        raise AssertionError(reason)


data = load(HERE / 'inventory.json')
for row in data['sourcePins']:
    p = ROOT / row['path']
    check(len(p.read_bytes()) == row['bytes'] and sha(p) == row['sha256'], ('source pin', row['path']))
for row in data['anchors']:
    lines = (ROOT / row['path']).read_text(encoding='utf-8-sig').splitlines()
    actual = [i + 1 for i, line in enumerate(lines) if row['token'] in line]
    check(actual == row['lines'], ('exact source anchor', row['path'], row['token']))

bridge = (ROOT / 'src/KH2Trainer.Bridge/TrainerBridge.cpp').read_text(encoding='utf-8-sig')
for module in ('ActorLifetimeSupport.inl', 'MovementTransactionSupport.inl', 'GameplayStateSupport.inl'):
    check('#include "' + module + '"' in bridge, ('active native integration', module))
for module in ('StatusFieldTransactionSupport.h', 'StatusObservationRuntime.h', 'StatusRevisionLedger.h'):
    check('#include "' + module + '"' not in bridge, ('status module not installed by TrainerBridge', module))

# Source call-site inventory: definitions/Core-internal uses are expected. No
# claim is made that string search alone establishes absence of dynamic calls.
tokens = ('MotionPayloadReader', 'MotionRootEvaluator', 'AssetEffectiveByteReader', 'EffectiveAssetManifest')
for base in ('src/KH2Trainer', 'src/KH2Trainer.Twitch', 'src/KH2Trainer.Bridge'):
    for p in (ROOT / base).rglob('*'):
        if p.is_file() and p.suffix in ('.cs', '.cpp', '.inl', '.h') and not {'bin', 'obj'}.intersection(p.parts):
            text = p.read_text(encoding='utf-8-sig')
            check(not any(t in text for t in tokens), ('no existing scale/parser product call site', p.relative_to(ROOT).as_posix()))

with zipfile.ZipFile(ROOT / 'artifacts/packages/KH2_Trainer_v0.12.17/Source.zip') as z:
    for row in data['sourcePins']:
        if row['path'].startswith(('src/', 'tests/')):
            check(z.read(row['path']) == (ROOT / row['path']).read_bytes(), ('source matches delivered v17', row['path']))

for row in data['storedNativeTestRecords']:
    p = ROOT / row['path']
    check(sha(p) == row['sha256'], ('stored log identity', row['suite']))
    text = p.read_text(encoding='utf-8-sig')
    result = re.search(r'(\d+) (?:shortcut )?checks, (\d+) failures', text) or re.search(r'checks: (\d+); failures: (\d+)', text)
    check(result is not None and int(result[1]) == row['checks'] and int(result[2]) == row['failures'] == 0, ('stored native result', row['suite']))

row = data['storedCoreTestRecord']
p = ROOT / row['path']
check(sha(p) == row['sha256'], 'stored Core log identity')
text = p.read_text(encoding='utf-8-sig')
check(len(re.findall(r'^PASS motion: ', text, re.M)) == row['motion'] == 2275, '2275 stored motion checks')
check(len(re.findall(r'^PASS effective assets: ', text, re.M)) == row['effectiveAssets'] == 119, '119 stored effective-reader checks')

review = load(ROOT / 'docs/research/motion-payload-bounds-20261007/independent-review.json')
for name, pin in review['fileHashes'].items():
    check(sha(ROOT / name) == pin, ('prior accepted motion sources unchanged', name))

manifest_path = HERE / 'manifest.json'
if manifest_path.exists():
    manifest = load(manifest_path)
    check(set(manifest['files']) == {p.name for p in HERE.iterdir() if p.is_file() and p.name != 'manifest.json'}, 'exact map artifact membership')
    for name, pin in manifest['files'].items():
        check(sha(HERE / name) == pin['sha256'] and (HERE / name).stat().st_size == pin['bytes'], ('map artifact', name))

print(json.dumps({'success': True, 'checks': count, 'sourcePins': len(data['sourcePins']), 'anchors': len(data['anchors']),
    'sourceAndEvidenceUnchanged': True, 'productTestsRerun': False, 'gameOrIdaAccess': False}))
