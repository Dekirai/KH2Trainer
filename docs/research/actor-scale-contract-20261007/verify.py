"""Verify recorded IDA pagination, unique instruction addresses and retail PE bytes.

This is a static evidence verifier. It neither executes nor changes the game or IDB.
The original EXE can be supplied with --exe; all other paths are relative to this file.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_EXE = Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')

def require(ok, message):
    if not ok:
        raise ValueError(message)

def integer(value, label, minimum=0):
    require(type(value) is int and value >= minimum, label + ': invalid integer')
    return value

def address(value):
    require(isinstance(value, str) and bool(value), 'missing address')
    result = int(value, 16)
    require(result > 0, 'invalid address')
    return result

def octets(value):
    require(isinstance(value, str) and bool(value), 'missing original bytes')
    return bytes(int(x, 16) for x in value.split())

def complete_cursor(cursor):
    require(isinstance(cursor, dict), 'missing cursor')
    require(cursor.get('done') is True and cursor.get('next') is None,
            'incomplete final cursor')
    require(cursor.get('cancelled', False) is False, 'cancelled export')

def validate_body(f):
    start = address(f['addr'])
    size = integer(f['size'], 'size', 1)
    require(f['analysis']['size'] == size, 'analysis size mismatch')
    total = integer(f['total_instructions'], 'total', 1)
    require(integer(f['instruction_count'], 'count', 1) == total, 'aggregate count mismatch')
    complete_cursor(f['cursor'])
    pages = f['pages']
    require(isinstance(pages, list) and bool(pages), 'missing pages')
    merged = []
    for index, page in enumerate(pages):
        require(address(page['addr']) == start, 'page function mismatch')
        asm = page['asm']
        require(address(asm['start_ea']) == start, 'page start mismatch')
        rows = asm['lines']
        require(isinstance(rows, list) and bool(rows), 'missing page instructions')
        require(integer(page['instruction_count'], 'page count', 1) == len(rows),
                'truncated page array')
        require(integer(page['total_instructions'], 'page total', 1) == total,
                'inconsistent page totals')
        if 'offset' in page:
            require(integer(page['offset'], 'offset') == len(merged), 'offset mismatch')
        require(page.get('complete', True) is not False, 'page marked incomplete')
        merged.extend(rows)
        cursor = page['cursor']
        require(isinstance(cursor, dict) and cursor.get('cancelled', False) is False,
                'invalid or cancelled page cursor')
        if index + 1 == len(pages):
            complete_cursor(cursor)
        else:
            require(cursor.get('done', False) is False, 'early final cursor')
            require(integer(cursor.get('next'), 'next', 1) == len(merged), 'pagination gap')
    require(len(merged) == total, 'incomplete body')
    require(f['asm']['lines'] == merged and address(f['asm']['start_ea']) == start,
            'aggregate differs from pages')
    addresses = []
    for row in merged:
        require(isinstance(row, dict) and isinstance(row.get('instruction'), str)
                and bool(row['instruction'].strip()), 'invalid instruction row')
        addresses.append(address(row['addr']))
    require(addresses[0] == start and addresses == sorted(set(addresses)),
            'duplicate, unordered or wrong-start instructions')
    require(all(start <= a < start + size for a in addresses), 'instruction outside body')
    body = octets(f['originalBytes'])
    require(len(body) == size, 'body byte count mismatch')
    return start, body, total

def original_reader(raw, base):
    require(raw[:2] == b'MZ', 'not MZ')
    pe = struct.unpack_from('<I', raw, 0x3c)[0]
    require(raw[pe:pe+4] == b'PE\0\0', 'not PE')
    require(struct.unpack_from('<H', raw, pe+4)[0] == 0x8664, 'not AMD64')
    optional = pe + 24
    require(struct.unpack_from('<H', raw, optional)[0] == 0x20b, 'not PE32+')
    require(struct.unpack_from('<Q', raw, optional+24)[0] == base, 'image base mismatch')
    table = optional + struct.unpack_from('<H', raw, pe+20)[0]
    count = struct.unpack_from('<H', raw, pe+6)[0]
    sections = [struct.unpack_from('<4I', raw, table+40*i+8) for i in range(count)]
    def read(addr, size):
        rva = addr-base
        matches = []
        for _, va, raw_size, raw_offset in sections:
            if va <= rva and rva-va+size <= raw_size:
                offset = raw_offset+rva-va
                require(offset+size <= len(raw), 'truncated original file')
                matches.append(raw[offset:offset+size])
        require(len(matches) == 1, 'unbacked or ambiguous original span')
        return matches[0]
    return read

def validate(ev, raw):
    actual = hashlib.sha256(raw).hexdigest()
    require(actual == ev['originalSha256'].lower(), 'original SHA256 mismatch')
    original_at = original_reader(raw, address(ev['imageBase']))
    rows = []
    starts = set()
    for f in ev['functions']:
        addr, body, count = validate_body(f)
        require(addr not in starts, 'duplicate function')
        starts.add(addr)
        require(body == original_at(addr, len(body)), 'original function bytes differ: ' + f['addr'])
        rows.append(dict(addr=f['addr'], instructions=count, originalBytes=len(body),
                         sha256=hashlib.sha256(body).hexdigest(), completeAsm=True))
    data = []
    for entry in ev.get('data', []):
        addr, size = address(entry['addr']), integer(entry['size'], 'data size', 1)
        body = octets(entry['originalBytes'])
        require(len(body) == size and body == original_at(addr, size), 'original data differs')
        data.append(dict(addr=entry['addr'], originalBytes=size, sha256=hashlib.sha256(body).hexdigest()))
    return dict(success=True, functions=len(rows), instructions=sum(x['instructions'] for x in rows),
                originalFunctionBytes=sum(x['originalBytes'] for x in rows),
                dataSpans=len(data), originalDataBytes=sum(x['originalBytes'] for x in data),
                originalSha256=actual, bodies=rows, data=data,
                scope='Complete saved ASM pagination and original file bytes. This does not prove every semantic branch or live gameplay behavior.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, default=DEFAULT_EXE)
    parser.add_argument('--output', type=Path, default=HERE/'verification.json')
    args = parser.parse_args()
    source = (HERE/'evidence.json').read_bytes()
    report = validate(json.loads(source), args.exe.read_bytes())
    report['evidenceSha256'] = hashlib.sha256(source).hexdigest()
    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('bodies','data')}))

if __name__ == '__main__':
    main()
