"""Verify the frozen implementation receipts and their exact source inputs."""
from pathlib import Path
import argparse
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_file(base, item):
    path = (base / item['path']).resolve()
    assert path.is_relative_to(base.resolve()), item['path']
    assert path.stat().st_size == item['bytes'], path
    assert digest(path) == item['sha256'], path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.parse_args()
    manifest = read(HERE / 'manifest.json')
    for item in manifest['files']:
        check_file(HERE, item)
    for item in manifest['sources']:
        check_file(ROOT, item)
    retail = read(HERE / 'retail-comparison.json')
    assert retail['passed'] and retail['checks'] == 8995
    assert sum(r['instructionCount'] for r in retail['results']) == 4480
    assert all(r['allInstructionPcsWidthsAndEdgesMatch'] and r['diagnostics'] == 0 for r in retail['results'])
    expected = ROOT / 'docs/research/bdx-inspection-20261008/selected-structure.json'
    assert digest(expected) == retail['expectedStructureSha256']
    review = read(HERE / 'decoder-review/review.json')
    assert review['status'] == 'ACCEPTED_BOUNDED_OFFLINE_INSPECTION'
    assert not review['blockingFindings']
    assert review['actualProductSourceProbe']['checks'] == 233581
    for item in review['sourceHashes']:
        check_file(ROOT, item)
    oracle = read(HERE / 'decoder-review/oracle-review.json')
    assert oracle['status'] == 'PASS' and oracle['opcodeCases'] == 65536
    assert digest(HERE / 'decoder-review/oracle.bin') == oracle['oracleSha256']
    ui = read(HERE / 'ui-checks.json')
    assert ui['success'] and ui['bindingErrors'] == 0 and ui['windowCount'] == 0
    ui_review = read(HERE / 'ui-review.json')
    assert ui_review['status'] == 'ACCEPTED_BOUNDED_UI_INTEGRATION' and not ui_review['blockingFindings']
    for name, value in ui_review['sourceHashes'].items():
        assert digest(ROOT/name) == value, name
    report = read(HERE / 'report.json')
    assert report['coreChecks'] == 3215 and report['coreFailures'] == 0
    assert report['liveGame'] is False and report['gameOrSaveWrites'] is False
    print(json.dumps({'passed': True, 'files': len(manifest['files']),
                      'sources': len(manifest['sources']), 'coreChecks': 3215,
                      'opcodeCases': 65536, 'opcodeChecks': 233581,
                      'retailChecks': 8995, 'retailInstructions': 4480,
                      'offscreenUi': True, 'liveGame': False}))


if __name__ == '__main__':
    main()
