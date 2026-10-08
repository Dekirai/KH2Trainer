"""Validate local report links and record reproducible evidence fingerprints.

Only files in this new research folder are written. Product sources are read
solely to identify the context inspected by this static research.
"""
from pathlib import Path
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
report = json.loads((HERE/'report.json').read_text(encoding='utf-8'))
evidence = json.loads((HERE/'evidence.json').read_text(encoding='utf-8'))
verification = json.loads((HERE/'verification.json').read_text(encoding='utf-8'))
tests = json.loads((HERE/'verifier-tests.json').read_text(encoding='utf-8'))
body = {r['addr']: r for r in evidence['functions']}
assert len(body) == len(evidence['functions']) == verification['functions'] == 59
assert verification['success'] and tests['success'] and tests['failures'] == 0
assert verification['evidenceSha256'] == hashlib.sha256((HERE/'evidence.json').read_bytes()).hexdigest()
for claim in report['claims']:
    assert claim['addr'] in body
    for reference in claim['Evidence']:
        file, sep, fragment = reference.partition('#')
        assert (HERE/file).is_file(), reference
        if sep:
            match = re.fullmatch(r'functions\[addr=(0x[0-9a-f]+)\]', fragment)
            assert match and match[1] == claim['addr'], reference
assert len({r['addr'] for r in report['claims']}) == len(report['claims']) == 59
context = [
    'src/KH2Trainer.Bridge/TrainerBridge.cpp',
    'src/KH2Trainer.Bridge/ActorLifetimeSupport.inl',
    'src/KH2Trainer.Bridge/PlayerRoleSupport.inl',
    'docs/research/actor-scale-writers-20261007/report.json',
    'docs/research/player_roles_drive_20261007/report.json',
    'docs/research/actor-lifetime-20261007/report.json',
    'docs/research/movement-ownership-20261007/design.md',
]
def fingerprint(path, label):
    raw = path.read_bytes()
    return {'path': label, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
files = [fingerprint(p, p.name) for p in sorted(HERE.iterdir())
         if p.is_file() and p.name != 'fingerprints.json']
result = {
    'status': 'research_complete_product_unchanged',
    'claims': len(report['claims']),
    'fullSemanticReview': 'not_established',
    'files': files,
    'readOnlyContext': [fingerprint(REPO/p, p) for p in context],
    'contextNote': 'Hashes identify the inspected context at recording time. They do not freeze files owned by other agents or attest a future product build.',
    'validation': {'success': True, 'functions': verification['functions'],
                   'instructions': verification['instructions'],
                   'originalFunctionBytes': verification['originalFunctionBytes'],
                   'originalDataBytes': verification['originalDataBytes'],
                   'verifierChecks': tests['checks'], 'failures': tests['failures']},
    'limitations': ['No live gameplay validation.', 'No named retail BDX scale writer identified.',
                    'No scale reward, slot, hook or product write introduced.',
                    'Scalar value equality cannot observe same-value native writes.',
                    'Actor generation does not prove unchanged attachment/transform ownership.'],
}
(HERE/'fingerprints.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result['validation']))
