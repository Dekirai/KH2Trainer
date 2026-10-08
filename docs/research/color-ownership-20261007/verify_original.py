"""Read-only reproduction: match every captured IDA body against the retail PE."""
from pathlib import Path
import hashlib
import json
import struct
import sys

HERE = Path(__file__).resolve().parent
target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
blob = target.read_bytes()
pe = struct.unpack_from('<I', blob, 60)[0]
assert blob[:2] == b'MZ' and blob[pe:pe + 4] == b'PE\0\0'
machine, count = struct.unpack_from('<HH', blob, pe + 4)
assert machine == 0x8664
optional_size = struct.unpack_from('<H', blob, pe + 20)[0]
optional = pe + 24
assert struct.unpack_from('<H', blob, optional)[0] == 0x20b
base = struct.unpack_from('<Q', blob, optional + 24)[0]
sections = []
for index in range(count):
    start = optional + optional_size + index * 40
    virtual_size, rva, raw_size, raw = struct.unpack_from('<IIII', blob, start + 8)
    sections.append((rva, raw_size, raw))

def original(addr, size):
    rva = int(addr, 16) - base
    for section_rva, raw_size, raw in sections:
        if section_rva <= rva and size <= raw_size - (rva - section_rva):
            start = raw + rva - section_rva
            return start, blob[start:start + size]
    raise ValueError(f'No complete file-backed span at {addr} + {size}')

evidence = json.loads((HERE / 'native_evidence.json').read_text(encoding='utf-8'))
pseudocode = {item['addr'].lower(): item for item in json.loads((HERE / 'native_full_pseudocode.json').read_text(encoding='utf-8'))}
functions = []
for item in evidence:
    asm = item['asm']
    lines = asm['asm']['lines']
    assert asm['cursor'] == {'done': True}
    assert len(lines) == asm['instruction_count'] == asm['total_instructions']
    assert len({line['addr'] for line in lines}) == len(lines)
    code = pseudocode[item['addr'].lower()]
    assert code['cursor'] == {'done': True} and code['line_count'] == code['total_lines']
    captured = bytes(int(part, 16) for part in item['bytes']['result'][0]['data'].split())
    assert len(captured) == item['info']['size']
    offset, retail = original(item['addr'], len(captured))
    assert retail == captured, item['addr']
    functions.append({'addr': item['addr'], 'file_offset': offset, 'bytes': len(retail),
                      'instructions': len(lines), 'sha256': hashlib.sha256(retail).hexdigest(), 'original_equal': True})
report = {'target': str(target), 'sha256': hashlib.sha256(blob).hexdigest(), 'imagebase': hex(base),
          'source': 'native_evidence.json', 'functions': functions,
          'total_bytes': sum(f['bytes'] for f in functions),
          'total_instructions': sum(f['instructions'] for f in functions)}
(HERE / 'original_verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, indent=2))
