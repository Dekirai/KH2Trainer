"""Read-only archive, original-PE and normalized-evidence verification."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, struct, zipfile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'src/KH2Trainer').is_dir())
BASE = 0x140000000
SHA = '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
PINS = {'study': 'b177d643b68a40b169cec8f85dcb5215e6fa102080b607baf7403de0162ef71b',
        'review': '6bca80bebe52cee0b82964f8a6d60e526325fb54322b401291fb6bee13eec29e'}
sha = lambda b: hashlib.sha256(b).hexdigest()
load = lambda p: json.loads(p.read_bytes())

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Read-only check; also the default.')
    parser.add_argument('--binary', type=Path, default=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe'))
    args = parser.parse_args()
    manifest = load(HERE / 'manifest.json')
    assert {p.name for p in HERE.iterdir() if p.is_file()} == {r['path'] for r in manifest['files']} | {'manifest.json'}
    for r in manifest['files']:
        data = (HERE / r['path']).read_bytes()
        assert len(data) == r['size'] and sha(data) == r['sha256']
    provenance = load(HERE / 'provenance.json')
    assert provenance['manifestPins'] == PINS
    archive_file = HERE / 'evidence.zip'
    assert sha(archive_file.read_bytes()) == provenance['archive']['sha256']
    with zipfile.ZipFile(archive_file) as z:
        assert len(z.namelist()) == len(set(z.namelist())) == 27
        assert set(z.namelist()) == {r['path'] for r in provenance['archive']['members']}
        for r in provenance['archive']['members']:
            data = z.read(r['path'])
            assert len(data) == r['size'] and sha(data) == r['sha256']
        for prefix, pin in PINS.items():
            source_manifest = z.read(prefix + '/manifest.json')
            assert sha(source_manifest) == pin
            rows = json.loads(source_manifest)['files']
            assert {n for n in z.namelist() if n.startswith(prefix + '/')} == {prefix + '/' + r['path'] for r in rows} | {prefix + '/manifest.json'}
            for r in rows:
                data = z.read(prefix + '/' + r['path'])
                assert len(data) == r.get('size', r.get('bytes')) and sha(data) == r['sha256']
        raw = json.loads(z.read('study/evidence.json'))
        raw_report = json.loads(z.read('study/report.json'))
        reviewed = json.loads(z.read('review/review.json'))
        assert reviewed['status'] == 'PASS' and reviewed['unresolvedFindings'] == []
        assert reviewed['sourceManifestSha256'] == PINS['study']
        captures = {n: z.read(n) for n in z.namelist() if n.startswith('study/') and n.endswith('-insns.json')}
    pe_bytes = args.binary.read_bytes()
    assert sha(pe_bytes) == SHA == raw['originalSha256']
    pe = struct.unpack_from('<I', pe_bytes, 0x3c)[0]
    assert pe_bytes[pe:pe+4] == b'PE\0\0' and struct.unpack_from('<H', pe_bytes, pe+24)[0] == 0x20b
    assert struct.unpack_from('<Q', pe_bytes, pe+48)[0] == BASE
    table = pe+24+struct.unpack_from('<H', pe_bytes, pe+20)[0]
    sections = [struct.unpack_from('<IIII', pe_bytes, table+i*40+8) for i in range(struct.unpack_from('<H', pe_bytes, pe+6)[0])]
    def read(addr, size):
        for _, start, length, offset in sections:
            if start <= addr-BASE and addr-BASE+size <= start+length:
                return pe_bytes[offset+addr-BASE-start:offset+addr-BASE-start+size]
        raise AssertionError(hex(addr))
    spec = importlib.util.spec_from_file_location('coverage_rules', ROOT / 'scripts/update-analysis-coverage.py')
    rules = importlib.util.module_from_spec(spec); spec.loader.exec_module(rules)
    inventory = {int(f['address'], 16): f for line in (ROOT / 'docs/research/coverage/function_status.jsonl').read_text('utf8').splitlines() if (f := json.loads(line))['domain'] == 'native'}
    normalized = load(HERE / 'evidence.json')
    assert len(normalized['functions']) == len(raw['functions']) == 11
    assert normalized['dependencies'] == raw['dependencies'] and normalized['anchors'] == raw['anchors']
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    groups = {}
    for n, f in zip(normalized['functions'], raw['functions']):
        addr = int(f['addr'], 16); data = read(addr, f['size'])
        assert data == bytes.fromhex(f['originalBytes']) == bytes.fromhex(n['originalBytes'])
        assert n['addr'] == f['addr'] and n['size'] == f['size'] == inventory[addr]['size']
        assert sha(data) == n['sha256'] == f['sha256']
        assert n['sourceMetadata'] == f['sourceMetadata'] and n['complete'] and not f['nonInstructionSpans']
        ins = list(decoder.disasm(data, addr))
        assert sum(i.size for i in ins) == len(data)
        assert [i.address for i in ins] == [int(i['addr'], 16) for i in f['instructions']]
        assert [i.bytes.hex() for i in ins] == [i['bytes'] for i in f['instructions']]
        assert [i.mnemonic + ' ' + i.op_str for i in ins] == [i['instruction'] for i in f['instructions']]
        assert n['disassembly']['asm']['lines'] == [{'addr': i['addr'], 'instruction': i['ida']} for i in f['instructions']]
        assert n['pages'] == [n['disassembly']]
        complete, heads, _ = rules.body_assembly(n)
        assert complete and heads == [i.address for i in ins] and rules.original_spans(n) == [(addr, data)]
        fresh = f['sourceMetadata']['freshCapture']
        if fresh:
            query = json.loads(captures['study/' + f['sourceMetadata']['source']])['result'][0]
            assert query['cursor'] == {'done': True} and not query.get('truncated') and not query.get('error')
            assert query['count'] == query['scanned'] == len(ins)
            assert [int(i['addr'], 16) for i in query['matches']] == heads
            assert query['ranges'] == [{'start': hex(addr), 'end': hex(addr+len(data))}]
        group = groups.setdefault('fresh' if fresh else 'reused', {'functions': 0, 'instructions': 0, 'bodyBytes': 0})
        group['functions'] += 1; group['instructions'] += len(ins); group['bodyBytes'] += len(data)
    assert groups == {'fresh': {'functions': 6, 'instructions': 409, 'bodyBytes': 1487}, 'reused': {'functions': 5, 'instructions': 306, 'bodyBytes': 1284}}
    for dependency in raw['dependencies']:
        assert sha((ROOT / dependency['path']).read_bytes()) == dependency['sha256']
    assert read(BASE+0x5c6b00, 5) == b'comd\0'
    claims = load(HERE / 'report.json')['claims']
    assert claims == raw_report['claims'] and len(claims) == len({c['addr'] for c in claims}) == 7
    body_addresses = {f['addr'] for f in normalized['functions']}
    ref_count = 0
    for c in claims:
        assert c['addr'] in body_addresses and c['Finding'] and c['Limitations']
        assert f"evidence.json#functions[addr={c['addr']}]" in c['Evidence']
        for ref in c['Evidence']:
            assert rules.resolve_reference(HERE / 'report.json', ref)['status'] == 'exists', ref
            ref_count += 1
    assert ref_count == 20
    print(json.dumps({'status': 'PASS', 'archiveMembers': 27, 'claims': 7, 'references': ref_count,
        'functions': 11, 'instructions': 715, 'bodyBytes': 2771, 'groups': groups,
        'byteFailures': 0, 'additionalOriginalLiteralBytes': 5,
        'scope': 'Static original/archive/normalization checks; no semantic VM, native execution or all-writer claim.'}))

if __name__ == '__main__':
    main()
