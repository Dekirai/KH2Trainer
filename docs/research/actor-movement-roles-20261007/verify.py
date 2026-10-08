"""Verify saved read-only IDA evidence against the original on-disk EXE.

No game access, native execution, build, IDB write, or coverage regeneration.
"""
import argparse
import hashlib
import json
import pathlib
import re
import struct

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--exe', type=pathlib.Path, default=pathlib.Path(
    r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe'))
args = parser.parse_args()
evidence = json.loads((HERE / 'evidence.json').read_text(encoding='utf-8'))
binary = args.exe.read_bytes()
digest = lambda b: hashlib.sha256(b).hexdigest()
assert digest(binary) == evidence['inputSha256']
assert binary[:2] == b'MZ'
pe = struct.unpack_from('<I', binary, 60)[0]
assert binary[pe:pe+4] == b'PE\0\0'
sections = []
count = struct.unpack_from('<H', binary, pe+6)[0]
optional = struct.unpack_from('<H', binary, pe+20)[0]
image_base = struct.unpack_from('<Q', binary, pe+48)[0]
for i in range(count):
    offset = pe+24+optional+40*i
    _, rva, size, raw = struct.unpack_from('<IIII', binary, offset+8)
    sections.append((rva, size, raw))

def original(address, size):
    rva = address-image_base
    section = next(s for s in sections if s[0] <= rva and rva+size <= s[0]+s[1])
    offset = section[2]+rva-section[0]
    value = binary[offset:offset+size]
    assert len(value) == size
    return value

results = []
by_address = {}
for row in evidence['functions']:
    address = int(row['addr'], 16)
    assert address not in by_address
    body = bytes(int(b, 16) for b in row['originalBytes'].split())
    assert len(body) == row['size'] and body == original(address, len(body))
    lines = row['asm']['lines']
    assert row['instruction_count'] == row['total_instructions'] == len(lines)
    assert row['cursor'].get('done') is True and row['cursor'].get('next') is None
    offsets = [int(x['addr'], 16) for x in lines]
    assert offsets and offsets[0] == address and offsets == sorted(set(offsets))
    assert all(address <= x < address+len(body) for x in offsets)
    assert row['pages'][-1]['cursor'].get('done') is True
    assert row['pseudocodePages'][-1]['cursor'].get('done') is True
    assert all(page.get('code') for page in row['pseudocodePages'])
    by_address[address] = body
    results.append(dict(addr=row['addr'], bytes=len(body), instructions=len(lines), sha256=digest(body)))
data_results = []
for row in evidence['data']:
    address = int(row['addr'], 16)
    body = bytes(int(b, 16) for b in row['data'].split())
    assert body == original(address, len(body))
    data_results.append(dict(addr=row['addr'], bytes=len(body), sha256=digest(body)))
wrappers = []
for wrapper, vtable in [(0x404FB0, 0x5CBA28), (0x4154E0, 0x5D15A0)]:
    body = by_address[image_base+wrapper]
    assert body[:4] == bytes.fromhex('48 8B CA E9') and len(body) == 8
    target = image_base+wrapper+8+struct.unpack_from('<i', body, 4)[0]
    assert target == image_base+0x3A8FA0
    assert struct.unpack('<Q', original(image_base+vtable+296, 8))[0] == image_base+wrapper
    wrappers.append(dict(rva=hex(wrapper), target=hex(target), bytes=body.hex()))

source = ROOT / 'src/KH2Trainer.Bridge/ActorMovementFeatures.inl'
code = source.read_text(encoding='utf-8')
for name, rva in [('normalCode', 0x404FB0), ('mickeyCode', 0x4154E0)]:
    initializer = re.search(r'\b'+name+r'\[\]\s*=\s*\{([^}]+)\}', code)[1]
    pin = bytes(int(x,16) for x in re.findall(r'0x([0-9A-Fa-f]{2})', initializer))
    assert pin == original(image_base+rva, len(pin))
files = ['src/KH2Trainer.Bridge/ActorMovementFeatures.inl',
         'tests/KH2Trainer.Bridge.Tests/ActorMovementGuardTests.cpp',
         'src/KH2Trainer.Bridge/PlayerRoleSupport.inl']
report = dict(status='pass', sourceSha256=evidence['inputSha256'],
    scope='Static original-byte and saved-complete-evidence validation only; native tests were not built or executed in this task.',
    functions=results, functionCount=len(results),
    instructionCount=sum(r['instructions'] for r in results),
    originalFunctionBytes=sum(r['bytes'] for r in results),
    data=data_results, originalDataBytes=sum(r['bytes'] for r in data_results),
    exactWrapperTargets=wrappers, runtimePinCount=2, runtimePinBytes=16,
    files={p:digest((ROOT/p).read_bytes()) for p in files})
(HERE/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ['status','functionCount','instructionCount','originalFunctionBytes','originalDataBytes','runtimePinCount','runtimePinBytes']},indent=2))
