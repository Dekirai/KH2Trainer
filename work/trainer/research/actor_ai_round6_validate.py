"""Validate captured static IDA bodies against the original PE; never attach to KH2."""
import hashlib, json, pathlib, struct, sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'work/pe/deps'))
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

original = pathlib.Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
raw = original.read_bytes()
digest = hashlib.sha256(raw).hexdigest()
assert digest == '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
pe = pefile.PE(data=raw, fast_load=True)
decoder = Cs(CS_ARCH_X86, CS_MODE_64)
evidence_path = HERE / 'actor_ai_round6_complete_evidence.json'
evidence = json.loads(evidence_path.read_text(encoding='utf-8-sig'))
checks = []
seen = set()
for f in evidence['functions']:
    address = int(f['addr'], 16)
    assert address not in seen
    seen.add(address)
    size = int(f['analysis']['size'], 16)
    saved = bytearray()
    for region in f['bytes']:
        assert int(region['addr'], 16) == address + len(saved)
        saved.extend(int(x, 16) for x in region['data'].split())
    actual = pe.get_data(address - pe.OPTIONAL_HEADER.ImageBase, size)
    assert len(saved) == size and saved == actual, f['addr']
    lines = []
    for page in f['pages']:
        assert page.get('offset', len(lines)) == len(lines)
        assert page['instruction_count'] == len(page['asm']['lines'])
        lines.extend(page['asm']['lines'])
        if page['cursor'].get('done'):
            assert page is f['pages'][-1] and page['cursor'].get('next') is None
        else:
            assert page['cursor']['next'] == len(lines)
        assert not page['cursor'].get('cancelled')
    assert f['pages'][-1]['cursor']['done']
    assert all(p['total_instructions'] == len(lines) for p in f['pages'])
    decoded = list(decoder.disasm(actual, address))
    assert len(decoded) >= len(lines)
    code = decoded[:len(lines)]
    assert [i.address for i in code] == [int(x['addr'], 16) for x in lines], f['addr']
    code_bytes = sum(i.size for i in code)
    trailing = actual[code_bytes:]
    table = None
    if trailing:
        # IDA's function span includes this switch's alignment and RVA table;
        # those bytes are data, not twelve additional x64 instructions.
        assert address == 0x1403BE2B0 and code[-1].mnemonic == 'ret'
        assert len(trailing) == 30 and trailing[:2] == bytes.fromhex('6690')
        table = list(struct.unpack('<7I', trailing[2:]))
        starts = {i.address for i in code}
        assert all(pe.OPTIONAL_HEADER.ImageBase+rva in starts for rva in table)
        assert any('jpt_' in x['instruction'] for x in lines)
    else:
        assert code_bytes == size and len(decoded) == len(lines)
    a = f['analysis']
    assert not a['callers_truncated'] and a['caller_count'] == len(a['callers'])
    assert not a['callees_truncated'] and a['callee_count'] == len(a['callees'])
    checks.append({'address': f['addr'], 'bytes': size, 'instructions': len(lines),
                   'sha256': hashlib.sha256(actual).hexdigest(), 'original_bytes_equal': True,
                   'independent_instruction_boundaries_equal': True,
                   'embedded_switch_rvas': table, 'code_bytes':code_bytes})
for row in evidence['vtableBytes']['result']:
    actual = pe.get_data(int(row['addr'], 16)-pe.OPTIONAL_HEADER.ImageBase, 256)
    assert actual == bytes(int(x,16) for x in row['data'].split())
    decoded = next(v for v in evidence['vtables'] if v['addr'] == row['addr'])
    assert [int(x,16) for x in decoded['slots']] == list(struct.unpack('<32Q', actual))

asset = original.parent / 'Modding/openkh/data/kh2/00battle.bin'
asset_bytes = asset.read_bytes()
assert asset_bytes[:4] == b'BAR\x01'
entries = struct.unpack_from('<I', asset_bytes, 4)[0]
assert 16 + 16*entries <= len(asset_bytes)
stop = None
for i in range(entries):
    kind, index, tag, offset, size = struct.unpack_from('<HH4sII', asset_bytes, 16+i*16)
    if kind == 2 and tag == b'stop':
        assert offset <= len(asset_bytes) and size <= len(asset_bytes)-offset
        stop = asset_bytes[offset:offset+size]
        break
assert stop is not None
version, count = struct.unpack_from('<II', stop)
assert len(stop) == 8 + count*4
rows = [{'id': key, 'mask': value} for key, value in struct.iter_unpack('<HH', stop[8:])]
assert len({r['id'] for r in rows}) == count
assert [r['id'] for r in rows] == sorted(r['id'] for r in rows)
report = {'original': str(original), 'original_sha256': digest,
          'evidence_sha256': hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
          'functions': checks, 'function_count':len(checks),
          'instructions':sum(c['instructions'] for c in checks),
          'bytes':sum(c['bytes'] for c in checks), 'vtable_blocks':3,
          'baseline_stop':{'path':str(asset), 'source_sha256':hashlib.sha256(asset_bytes).hexdigest(),
                           'entry_sha256':hashlib.sha256(stop).hexdigest(),
                           'version':version,'rows':rows,
                           'scope':'Existing extracted baseline asset; no runtime or modified-table assertion'},
          'failures':0,'live_game_access':False}
(HERE/'actor_ai_round6_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ['function_count','instructions','bytes','vtable_blocks','failures','live_game_access']}))
