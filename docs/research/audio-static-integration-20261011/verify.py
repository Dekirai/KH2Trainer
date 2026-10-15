"""Read-only validation of frozen audio integration; no game code is executed."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

D = Path(__file__).resolve().parent
R = next(p for p in D.parents if (p / 'scripts/update-analysis-coverage.py').is_file())
ACCEPTED = {
    'audio-bank-retirement-20261011': 'ACCEPTED_BOUNDED_STATIC_STUDY',
    'audio-request-producers-20261011': 'PASS',
    'voice-resource-teardown-20261011': 'ACCEPTED_BOUNDED_INDEPENDENT_REVIEW',
    'audio-bank-format-20261011': 'ACCEPTED_BOUNDED_AUDIO_BANK_FORMAT_STUDY',
}


def load(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def sha(b):
    return hashlib.sha256(b).hexdigest()


checks = 0


def check(ok, label):
    global checks
    checks += 1
    if not ok:
        raise AssertionError(label)


def file_pin(p, pin):
    b = p.read_bytes()
    check(sha(b) == pin['sha256'] and len(b) == pin['bytes'], str(p))


def manifest(folder):
    m = load(folder / 'manifest.json')
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*')
              if p.is_file() and p != folder / 'manifest.json'}
    check(actual == set(m['files']), f'Exact manifest members: {folder.name}')
    for rel, pin in m['files'].items():
        p = folder / rel
        check(p.resolve().is_relative_to(folder.resolve()), 'Manifest path stays within study')
        file_pin(p, pin)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check-current-product', action='store_true')
    args = ap.parse_args()
    manifest(D)
    integration = load(D / 'integration.json')
    check(integration['productChanged'] is False and integration['gameExecution'] is False,
          'Research-only integration')
    check(integration['productVersion'] == '0.12.16', 'Historical release')
    parser = R / 'scripts/update-analysis-coverage.py'
    check(sha(parser.read_bytes()) == '546d0defdacd8857d7f2461283516348ca28776d13e253d8d954ad43622cc1b2',
          'Unchanged coverage parser')
    spec = importlib.util.spec_from_file_location('audio_integration_coverage', parser)
    coverage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(coverage)
    studies = {}
    for entry in integration['studies']:
        folder = R / entry['folder']
        check(sha((folder / 'manifest.json').read_bytes()) == entry['manifestSha256'], entry['folder'])
        sm = manifest(folder)
        check(len(sm['files']) == entry['files'], 'Study member count')
        studies[folder.name] = entry
    check(len(studies) == 5, 'Five bounded studies')
    for receipt in integration['reviewReceipts']:
        p = D / receipt['receipt']
        check(sha(p.read_bytes()) == receipt['receiptSha256'], 'Review receipt pin')
        data = load(p)
        key = 'authorManifestSha256' if receipt['study'] == 'audio-bank-format-20261011' else 'studyManifestSha256'
        expected = studies[receipt['study']]['manifestSha256']
        check(data[key] == receipt['acceptedManifestSha256'] == expected, 'Final reviewed manifest')
        check(data['status'] == ACCEPTED[receipt['study']], 'Exact accepted review status')
        check(not data.get('openBlockers', data.get('issues', [])), 'No review blockers')
    check(len(integration['reviewReceipts']) == 4, 'Four independent function reviews')
    for item in integration['reviewSnapshotMap']:
        file_pin(D / item['snapshot'], item)
        check(item['snapshot'].endswith('.txt'), 'Historical review not parsed as current evidence')
    actual_claims = load(D / 'claims.json')['claims']
    expected_claims = []
    expected_map = []
    refs = 0
    direct = 0
    for study in integration['studies']:
        folder = R / study['folder']
        report = folder / 'report.json'
        if not report.exists():
            continue
        for index, claim in enumerate(load(report).get('claims', [])):
            if 'Finding' in claim:
                check(folder.name == 'audio-request-producers-20261011', 'Direct claim source')
                direct += 1
                continue
            qualified = []
            for ref in claim['evidence']:
                name, sep, fragment = ref.partition('#')
                p = R / name if (R / name).is_file() else folder / name
                qualified.append(p.relative_to(R).as_posix() + sep + fragment)
            expected_claims.append(dict(addr=claim['address'], Finding=claim['finding'],
                Limitations=claim.get('limitations', claim.get('limits')), Evidence=qualified))
            expected_map.append(dict(source=report.relative_to(R).as_posix(), sourceClaimIndex=index,
                                     normalizedClaimIndex=len(expected_claims) - 1))
    check(actual_claims == expected_claims, 'Exact claim text, address, limitations and qualified references')
    check(expected_map == integration['claimNormalization'], 'Exact source-to-normalized mapping')
    check(len(actual_claims) == 58 and direct == 23, '58 normalized and 23 original claims')
    for claim in actual_claims:
        check(bool(claim['Limitations']), 'Explicit claim limitations')
        for ref in claim['Evidence']:
            resolved = coverage.resolve_reference(D / 'claims.json', ref)
            check(resolved['status'] == 'exists', f'Reference: {ref}')
            refs += 1
    product_files = integration['productSourcePins']
    check(len(product_files) == 240 and len({p['path'] for p in product_files}) == 240,
          '240 distinct historical source pins')
    if args.check_current_product:
        package = R / 'artifacts/packages/KH2_Trainer_v0.12.16'
        with zipfile.ZipFile(package / 'Source.zip') as z:
            names = {n for n in z.namelist() if not n.endswith('/') and n.startswith(('src/', 'tests/'))}
            check(names == {p['path'] for p in product_files}, 'Exact historical archive source set')
            for p in product_files:
                file_pin(R / p['path'], p)
                check((R / p['path']).read_bytes() == z.read(p['path']), 'Exact source/archive bytes')
        check(sha((package / 'KH2_Trainer.exe').read_bytes()) == integration['productExeSha256'],
              'Unchanged delivered executable')
    print(json.dumps(dict(status='PASS', checks=checks, studies=len(studies),
        normalizedClaims=len(actual_claims), directClaims=direct, resolvedReferences=refs,
        currentProductChecked=args.check_current_product, gameExecution=False)))


if __name__ == '__main__':
    main()
