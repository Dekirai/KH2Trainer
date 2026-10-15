"""Read-only verification of source pins and the stored isolated test result."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'src/KH2Trainer.Core').is_dir())

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

pins = read(HERE / 'sources.json')
for name, entry in pins['files'].items():
    assert sha(ROOT / name) == entry['sha256'], f'changed repository source: {name}'
    if 'snapshot' in entry:
        assert sha(HERE / entry['snapshot']) == entry['sha256'], f'changed snapshot: {name}'
manifest = read(HERE / 'manifest.json')['files']
for name, entry in manifest.items():
    path = HERE / name
    assert path.stat().st_size == entry['bytes'] and sha(path) == entry['sha256'], f'manifest mismatch: {name}'
result = read(HERE / 'test-output/result.json')
assert result['passed'] == 172 and result['failed'] == 0
assert len(result['checks']) == 172 and all(row['ok'] for row in result['checks'])
assert '172 passed, 0 failed' in (HERE / 'test-output.txt').read_text(encoding='utf-8-sig')
print(f"PASS: {len(pins['files'])} current source/study pins; {len(manifest)} manifest files; 172 stored synthetic checks. Tests not rerun by this verifier.")
