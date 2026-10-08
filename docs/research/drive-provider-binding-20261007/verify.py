"""Verify this static IDA capture against disk PEs; no process or loader access."""
import sys
sys.dont_write_bytecode = True
import argparse
import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent

def sha(data):
    return hashlib.sha256(data).hexdigest()

def integer(value):
    return type(value) is int and value >= 0

def unhex(value):
    return bytes(int(token, 16) for token in value.split())

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--retail', type=Path)
    ap.add_argument('--panacea', type=Path)
    args = ap.parse_args()
    ev = json.loads((HERE / 'evidence.json').read_text(encoding='utf-8'))
    modules = {}
    for entry in ev['modules']:
        path = getattr(args, entry['id']) or Path(entry['originalPath'])
        raw = path.read_bytes()
        assert sha(raw) == entry['originalSha256'], ('original identity', entry['id'])
        pe = struct.unpack_from('<I', raw, 0x3c)[0]
        assert raw[:2] == b'MZ' and raw[pe:pe+4] == b'PE\0\0'
        assert struct.unpack_from('<H', raw, pe+4)[0] == 0x8664
        optional = pe + 24
        assert struct.unpack_from('<H', raw, optional)[0] == 0x20b
        base = struct.unpack_from('<Q', raw, optional+24)[0]
        assert base == int(entry['imageBase'], 16)
        start = optional + struct.unpack_from('<H', raw, pe+20)[0]
        count = struct.unpack_from('<H', raw, pe+6)[0]
        sections = [struct.unpack_from('<4I', raw, start+40*i+8) for i in range(count)]
        modules[entry['id']] = dict(raw=raw, base=base, sections=sections, functions=0,
            instructions=0, originalCodeBytes=0, originalDataBytes=0,
            originalSha256=entry['originalSha256'])

    def disk(module, address, size):
        m = modules[module]
        rva = address - m['base']
        for _, va, raw_size, offset in m['sections']:
            if va <= rva and rva-va+size <= raw_size:
                start = offset+rva-va
                assert start+size <= len(m['raw'])
                return m['raw'][start:start+size]
        raise AssertionError(('Unbacked PE span', module, hex(address), size))

    seen = set()
    for f in ev['functions']:
        module, address = f['module'], int(f['addr'], 16)
        identity = (module, address)
        assert identity not in seen
        seen.add(identity)
        assert address-modules[module]['base'] == int(f['rva'], 16)
        size = f['size']
        assert integer(size) and size > 0 and size == int(f['analysis']['size'], 16)
        body = unhex(f['bytes'])
        assert len(body) == size and body == disk(module, address, size), identity
        rows, next_offset = [], 0
        assert f['pages'] and integer(f['total_instructions'])
        for i, page in enumerate(f['pages']):
            lines, cursor = page['asm']['lines'], page['cursor']
            assert type(lines) is list and lines
            assert page['offset'] == next_offset and integer(page['offset'])
            assert page['instruction_count'] == len(lines) and integer(page['instruction_count'])
            assert page['total_instructions'] == f['total_instructions']
            assert cursor.get('cancelled', False) is False
            assert int(page['asm']['start_ea'], 16) == address
            rows += lines
            next_offset += len(lines)
            if i+1 < len(f['pages']):
                assert cursor.get('done', False) is False and cursor.get('next') == next_offset
            else:
                assert cursor.get('done') is True and cursor.get('next') is None
        assert f['asm']['lines'] == rows
        assert f['instruction_count'] == f['total_instructions'] == len(rows)
        assert f['cursor'] == {'done': True}
        addresses = [int(row['addr'], 16) for row in rows]
        assert addresses == sorted(set(addresses)) and addresses[0] == address
        assert all(address <= a < address+size for a in addresses)
        assert all(isinstance(row.get('instruction'), str) and row['instruction'].strip() for row in rows)
        pseudo = f['pseudocode']
        next_line = 0
        assert pseudo['pages']
        for i, page in enumerate(pseudo['pages']):
            assert page['offset'] == next_line and page['code'] and not page.get('error')
            assert page['cursor'].get('cancelled', False) is False
            assert page['line_count'] == len(page['code'].splitlines())
            assert page['total_lines'] == pseudo['total_lines']
            next_line += page['line_count']
            if i+1 < len(pseudo['pages']):
                assert page['cursor'].get('done', False) is False and page['cursor']['next'] == next_line
            else:
                assert page['cursor'].get('done') is True and page['cursor'].get('next') is None
        assert next_line == pseudo['line_count'] == pseudo['total_lines']
        assert pseudo['code'] == '\n'.join(page['code'] for page in pseudo['pages'])
        m = modules[module]
        m['functions'] += 1
        m['instructions'] += len(rows)
        m['originalCodeBytes'] += size

    for d in ev['data']:
        body = unhex(d['bytes'])
        assert len(body) == d['size'] and body == disk(d['module'], int(d['addr'], 16), d['size'])
        modules[d['module']]['originalDataBytes'] += len(body)

    claims_verified = 0
    report_path = HERE / 'report.json'
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding='utf-8'))
        identities = {(f['module'], f['addr']) for f in ev['functions']}
        claimed = set()
        for claim in report['claims']:
            key = (claim['module'], claim['addr'])
            assert key in identities and key not in claimed, key
            claimed.add(key)
            assert claim['Domain'] == ('native' if key[0] == 'retail' else 'panacea')
            assert f"evidence.json#functions[addr={key[1]}]" in claim['Evidence']
            claims_verified += 1

    result = dict(success=True, functions=len(seen), instructions=sum(m['instructions'] for m in modules.values()),
        originalCodeBytes=sum(m['originalCodeBytes'] for m in modules.values()),
        originalDataBytes=sum(m['originalDataBytes'] for m in modules.values()), claimsVerified=claims_verified,
        modules={k: {a:b for a,b in v.items() if a not in ('raw','base','sections')} for k,v in modules.items()},
        evidenceSha256=sha((HERE/'evidence.json').read_bytes()),
        verifierSha256=sha(Path(__file__).read_bytes()),
        limits='Original disk identity, complete reported ASM/pseudocode pagination, address spans and bytes checked. No live hook/cache state, handoff implementation, rollback or comprehensive semantic proof.')
    (HERE/'verification.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
