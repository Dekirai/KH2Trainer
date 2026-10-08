"""Verify complete IDA bodies and all runtime pins against the original retail PE."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct

parser = argparse.ArgumentParser()
parser.add_argument('--original', type=Path, default=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe'))
args = parser.parse_args()
folder = Path(__file__).resolve().parent
root = folder.parents[2]
ev = json.loads((folder/'evidence.json').read_text(encoding='utf-8-sig'))
raw = args.original.read_bytes()
sha = hashlib.sha256(raw).hexdigest()
assert sha == ev['originalSha256'], 'Different original executable'
pe = struct.unpack_from('<I', raw, 0x3c)[0]
assert raw[:2] == b'MZ' and raw[pe:pe+4] == b'PE\0\0'
sections = pe+24+struct.unpack_from('<H', raw, pe+20)[0]
count = struct.unpack_from('<H', raw, pe+6)[0]
image_base = int(ev['imageBase'], 16)
def original_at(addr, length):
    rva = addr-image_base
    for i in range(count):
        size, va, raw_size, offset = struct.unpack_from('<4I', raw, sections+40*i+8)
        if va <= rva and rva-va+length <= raw_size:
            start = offset+rva-va
            assert start+length <= len(raw)
            return raw[start:start+length]
    raise AssertionError(f'Unbacked original span {addr:#x}+{length}')

by_rva = {}
total_instructions = total_bytes = 0
for function in ev['functions']:
    addr = int(function['addr'], 16)
    analysis = function['analysis']
    size = int(analysis['size'], 16)
    body = bytes(int(b, 16) for b in function['bytes'].split())
    assert len(body) == size and body == original_at(addr, size)
    asm = analysis['disasm']
    assert not asm['truncated'] and asm['instruction_count'] == len(asm['lines'])
    addresses = [int(line.split()[0], 16) for line in asm['lines']]
    assert addresses and addresses[0] == addr and all(addr <= a < addr+size for a in addresses)
    assert addresses == sorted(set(addresses))
    assert function['cursor']['done'] and not function['cursor'].get('cancelled',False)
    assert function['total_instructions'] == len(addresses)
    dedicated=[int(row['addr'],16) for row in function['asm']['lines']]
    assert dedicated == addresses
    assert len(function['pages'])==1 and function['pages'][0]['total_instructions']==len(addresses)
    assert function['pages'][0]['cursor']['done']
    assert addr-image_base not in by_rva
    by_rva[addr-image_base] = body
    total_instructions += len(addresses)
    total_bytes += size

source = root/'src/KH2Trainer.Bridge/PlayerHealthPins.inl'
pin_count = 0
pin_bytes = 0
pin_status = 'source unavailable in this standalone research copy'
if source.is_file():
    text = source.read_text(encoding='utf-8-sig')
    pins = re.findall(r'static const BYTE pin_([0-9a-f]+)\[\] = \{(.*?)\};', text, re.S)
    for name, contents in pins:
        data = bytes(int(b,16) for b in re.findall(r'0x([0-9a-f]{2})', contents))
        assert data == by_rva[int(name,16)], f'Runtime pin differs: {name}'
        pin_bytes += len(data)
    pin_count = len(pins)
    assert pin_count == 17
    pin_status = 'all runtime pins exactly match complete original bodies'

report = {'success':True, 'originalSha256':sha, 'functions':len(by_rva),
          'instructions':total_instructions, 'originalBytes':total_bytes,
          'runtimePins':pin_count, 'runtimePinBytes':pin_bytes, 'runtimePinStatus':pin_status,
          'scope':'Original-byte/complete captured ASM verification, not live gameplay or semantic proof of the entire program.'}
(folder/'verification.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print(json.dumps(report))
