"""Recheck reused complete ABI/startup captures against the original PE."""
import hashlib
import json
from pathlib import Path
import sys
import struct

sys.dont_write_bytecode = True
import capstone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ENTRY = ROOT / 'docs/research/status-entry-observation-20261007/evidence.json'
WRITERS = ROOT / 'docs/research/status-rebuild-ownership-20261007/evidence.json'
entry = json.loads(ENTRY.read_text(encoding='utf-8-sig'))
writers = json.loads(WRITERS.read_text(encoding='utf-8-sig'))
original = Path(entry['originalPath']).read_bytes()
assert hashlib.sha256(original).hexdigest() == entry['originalSha256'] == writers['originalSha256']
nt = struct.unpack_from('<I', original, 60)[0]
assert original[nt:nt+4] == b'PE\0\0'
optional = nt + 24
assert struct.unpack_from('<H', original, optional)[0] == 0x20b
image_base = struct.unpack_from('<Q', original, optional+24)[0]
section_table = optional + struct.unpack_from('<H', original, nt+20)[0]
sections = [struct.unpack_from('<4I', original, section_table+40*i+8)
            for i in range(struct.unpack_from('<H', original, nt+6)[0])]
def disk(address, size):
    rva = address - image_base
    for _, virtual_address, raw_size, file_offset in sections:
        if virtual_address <= rva and rva-virtual_address+size <= raw_size:
            return original[file_offset+rva-virtual_address:file_offset+rva-virtual_address+size]
    raise AssertionError((address, size))
decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
records = list(entry['functions'])
records.append(next(x for x in writers['functions'] if int(x['addr'], 16) == 0x140025310))
assert len(records) == 6
total_bytes = total_instructions = 0
for function in records:
    address = int(function['addr'], 16)
    size = int(function['size'], 0) if isinstance(function['size'], str) else function['size']
    saved = bytes(int(x, 16) for x in function['original_bytes'].split())
    assert len(saved) == size
    assert disk(address, size) == saved
    decoded = list(decoder.disasm(saved, address))
    assert decoded and decoded[-1].address + decoded[-1].size == address + size
    lines = function['asm']['lines']
    assert function['cursor']['done'] and not function['cursor'].get('next')
    assert len(lines) == function['instruction_count'] == function['total_instructions'] == len(decoded)
    assert [int(x['addr'], 16) for x in lines] == [x.address for x in decoded]
    total_bytes += size
    total_instructions += len(decoded)
receipt = {
    'success': True,
    'scope': 'Reused complete ABI and startup bodies only; no new IDA capture or live installation.',
    'reusedFunctions': len(records),
    'instructions': total_instructions,
    'originalBytes': total_bytes,
    'originalSha256': entry['originalSha256'],
    'evidenceSha256': {
        str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [ENTRY, WRITERS]
    },
    'sourceSha256': {
        str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [ROOT / 'src/KH2Trainer.Bridge/StatusObserverSupport.h',
                  ROOT / 'tests/KH2Trainer.Bridge.Tests/StatusObserverTests.cpp']
    },
}
(HERE / 'verification.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
print(json.dumps(receipt, indent=2))
