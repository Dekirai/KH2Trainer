"""Read-only verifier for the normalized frozen study. Requires Capstone."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, struct, zipfile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = 0x140000000
SHA = '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
PINS = {'study': '88493aa0b4b8ad402421a24d696fd71a51249d74eeb29af0e141412b9f4da2c7',
        'review': 'b9f7acc4cc390d210588d67e5b5198c8a6b3effcbb0e536cc1f49ef4da03d263'}
sha = lambda b: hashlib.sha256(b).hexdigest()
load = lambda p: json.loads(p.read_bytes())

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Read-only verification (also the default).')
    parser.add_argument('--binary', type=Path, default=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe'))
    args = parser.parse_args()
    manifest = load(HERE / 'manifest.json')
    assert {p.name for p in HERE.iterdir() if p.is_file()} == {r['path'] for r in manifest['files']} | {'manifest.json'}
    for r in manifest['files']:
        data = (HERE / r['path']).read_bytes()
        assert len(data) == r['size'] and sha(data) == r['sha256'], r['path']
    provenance = load(HERE / 'provenance.json')
    assert provenance['authorManifestSha256'] == PINS['study'] and provenance['reviewManifestSha256'] == PINS['review']
    archive_path = HERE / 'evidence.zip'
    assert sha(archive_path.read_bytes()) == provenance['archive']['sha256']
    with zipfile.ZipFile(archive_path) as z:
        assert len(z.namelist()) == len(set(z.namelist())) == 53
        assert set(z.namelist()) == {r['path'] for r in provenance['archive']['members']}
        for r in provenance['archive']['members']:
            data = z.read(r['path'])
            assert len(data) == r['size'] and sha(data) == r['sha256']
        for prefix, pin in PINS.items():
            manifest_data = z.read(f'{prefix}/manifest.json')
            assert sha(manifest_data) == pin
            source_manifest = json.loads(manifest_data)
            assert {n for n in z.namelist() if n.startswith(prefix + '/')} == {prefix + '/' + r['path'] for r in source_manifest['files']} | {prefix + '/manifest.json'}
            for r in source_manifest['files']:
                data = z.read(prefix + '/' + r['path'])
                assert len(data) == r['size'] and sha(data) == r['sha256']
        raw = json.loads(z.read('study/evidence.json'))
        reviewed = json.loads(z.read('review/review.json'))
        assert reviewed['status'] == 'PASS' and reviewed['unresolvedFindings'] == []
        assert reviewed['authorManifestSha256'] == PINS['study']
        captures = {n: z.read(n) for n in z.namelist() if n.startswith('study/root-capture/')}
    pe_bytes = args.binary.read_bytes()
    assert sha(pe_bytes) == SHA == raw['originalSha256'] == provenance['originalSha256']
    pe = struct.unpack_from('<I', pe_bytes, 0x3c)[0]
    assert pe_bytes[pe:pe+4] == b'PE\0\0'
    opt = pe + 24
    assert struct.unpack_from('<H', pe_bytes, opt)[0] == 0x20b
    assert struct.unpack_from('<Q', pe_bytes, opt + 24)[0] == BASE
    sections_at = opt + struct.unpack_from('<H', pe_bytes, pe + 20)[0]
    sections = [struct.unpack_from('<IIII', pe_bytes, sections_at + 40*i + 8) for i in range(struct.unpack_from('<H', pe_bytes, pe + 6)[0])]
    def read(addr, size):
        rva = addr - BASE
        for _, start, length, offset in sections:
            if start <= rva and rva + size <= start + length:
                return pe_bytes[offset + rva - start:offset + rva - start + size]
        raise AssertionError((hex(addr), size))
    spec = importlib.util.spec_from_file_location('coverage_rules', ROOT / 'scripts/update-analysis-coverage.py')
    rules = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rules)
    normalized = load(HERE / 'evidence.json')
    assert len(normalized['functions']) == len(raw['functions']) == 30
    assert normalized['dependencies'] == raw['dependencies'] and normalized['anchors'] == raw['anchors']
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    totals = {'fresh': {'functions': 0, 'instructions': 0, 'bodyBytes': 0}, 'reused': {'functions': 0, 'instructions': 0, 'bodyBytes': 0}}
    for n, f in zip(normalized['functions'], raw['functions']):
        addr = int(f['addr'], 16)
        data = read(addr, f['size'])
        assert data == bytes.fromhex(f['originalBytes']) == bytes.fromhex(n['originalBytes'])
        assert sha(data) == n['sha256'] == f['sha256']
        assert n['addr'] == f['addr'] and n['size'] == f['size']
        assert n['captureKind'] == f['captureKind'] and n['origin'] == f['origin']
        assert n['complete'] and not f['noncode']
        decoded = list(decoder.disasm(data, addr))
        assert sum(i.size for i in decoded) == len(data)
        assert [i.address for i in decoded] == [int(i['addr'], 16) for i in f['instructions']]
        assert [i.bytes.hex() for i in decoded] == [i['bytes'] for i in f['instructions']]
        assert [i.mnemonic + ' ' + i.op_str for i in decoded] == [i['instruction'] for i in f['instructions']]
        expected_lines = [{'addr': i['addr'], 'instruction': i['ida']} for i in f['instructions']]
        assert n['disassembly']['asm']['lines'] == expected_lines and n['pages'] == [n['disassembly']]
        complete, heads, _ = rules.body_assembly(n)
        assert complete and heads == [i.address for i in decoded]
        assert rules.original_spans(n) == [(addr, data)]
        if f['captureKind'] == 'fresh':
            query = json.loads(captures['study/' + f['origin'].replace('\\', '/')])['result'][0]
            assert query['cursor'] == {'done': True} and not query.get('truncated') and not query.get('error')
            assert query['count'] == query['scanned'] == len(decoded)
            assert [int(i['addr'], 16) for i in query['matches']] == heads
            assert query['ranges'] == [{'start': hex(addr), 'end': hex(addr + len(data))}]
        g = totals[f['captureKind']]
        g['functions'] += 1; g['instructions'] += len(decoded); g['bodyBytes'] += len(data)
    assert totals == {'fresh': {'functions': 14, 'instructions': 433, 'bodyBytes': 1828}, 'reused': {'functions': 16, 'instructions': 1086, 'bodyBytes': 4331}}
    assert len(normalized['data']) == len(raw['tables']) == 5
    for n, t in zip(normalized['data'], raw['tables']):
        addr = BASE + int(t['rva'], 16)
        data = read(addr, t['size'])
        assert n['addr'] == hex(addr) and n['size'] == t['size']
        assert data == bytes.fromhex(t['bytes']) == bytes.fromhex(n['originalBytes'])
        assert sha(data) == n['sha256'] and n['cells'] == t['cells']
    assert sum(t['size'] for t in normalized['data']) == 360
    for dep in raw['dependencies']:
        assert sha((ROOT / dep['path']).read_bytes()) == dep['sha256']
    claims = load(HERE / 'report.json')['claims']
    assert len(claims) == len({c['addr'] for c in claims}) == 24
    body_addresses = {n['addr'] for n in normalized['functions']}
    for c in claims:
        assert c['addr'] in body_addresses and c['Finding'] and c['Limitations']
        assert f"evidence.json#functions[addr={c['addr']}]" in c['Evidence']
        for ref in c['Evidence']:
            result = rules.resolve_reference(HERE / 'report.json', ref)
            assert result['status'] == 'exists', result
    print(json.dumps({'status': 'PASS', 'frozenArchiveMembers': 53, 'functionClaims': 24,
        'functions': 30, 'instructions': 1519, 'bodyBytes': 6159, 'dataBytes': 360,
        'fresh': totals['fresh'], 'reused': totals['reused'], 'byteFailures': 0,
        'scope': 'Static archive/normalization/PE/instruction checks; no native execution or semantic VM.'}))

if __name__ == '__main__':
    main()
