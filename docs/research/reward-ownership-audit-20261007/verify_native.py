"""Read-only original-PE/complete-ASM verification; writes only this research receipt."""
from pathlib import Path
import hashlib, json, struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

folder = Path(__file__).resolve().parent
source = folder / 'native-evidence-full.json'
ev = json.loads(source.read_text(encoding='utf-8'))
original = Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
raw = original.read_bytes()
pe = struct.unpack_from('<I', raw, 0x3c)[0]
assert raw[:2] == b'MZ' and raw[pe:pe+4] == b'PE\0\0'
base = struct.unpack_from('<Q', raw, pe+48)[0]
section = pe+24+struct.unpack_from('<H', raw, pe+20)[0]
count = struct.unpack_from('<H', raw, pe+6)[0]
def at(addr, size):
    rva = addr-base
    for i in range(count):
        _, va, length, off = struct.unpack_from('<4I', raw, section+40*i+8)
        if va <= rva and rva-va+size <= length:
            return raw[off+rva-va:off+rva-va+size]
    raise AssertionError(f'Unbacked RVA {rva:x}')
def decode(s): return bytes(int(x,16) for x in s.split())
rows = []
md = Cs(CS_ARCH_X86, CS_MODE_64)
for fn in ev['functions']:
    addr = int(fn['addr'],16); size = int(fn['lookup']['fn']['size'],16)
    body = decode(fn['bytes']['data'])
    assert len(body) == size and at(addr,size) == body
    asm = fn['asm']; lines = asm['asm']['lines']; pc = fn['pc']
    assert asm['cursor']['done'] is True and not asm['cursor'].get('cancelled')
    assert len(lines) == asm['instruction_count'] == asm['total_instructions']
    assert pc['cursor']['done'] is True and pc['line_count'] == pc['total_lines'] and not pc['truncated']
    instructions = list(md.disasm(body,addr))
    assert [x.address for x in instructions] == [int(x['addr'],16) for x in lines]
    assert sum(x.size for x in instructions) == size
    rows.append({'addr':hex(addr),'rva':hex(addr-base),'size':size,'instructions':len(lines),
                 'sha256':hashlib.sha256(body).hexdigest(),'originalEqual':True,'capstoneBoundariesEqual':True})
tables = []
for record in ev['tables']['result']:
    addr=int(record['addr'],16); data=decode(record['data'])
    assert data==at(addr,len(data))
    tables.append({'addr':hex(addr),'size':len(data),'value':hex(int.from_bytes(data,'little')),'originalEqual':True})
receipt={'status':'PASS','original':str(original),'originalSha256':hashlib.sha256(raw).hexdigest(),
         'evidenceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'imageBase':hex(base),
         'functionCount':len(rows),'instructionCount':sum(r['instructions'] for r in rows),
         'functionBytes':sum(r['size'] for r in rows),'tableBytes':sum(r['size'] for r in tables),
         'functions':rows,'tables':tables,'limitation':'Static verification. No native execution or game write.'}
(folder/'native-validation.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:receipt[k] for k in ['status','functionCount','instructionCount','functionBytes','tableBytes','originalSha256']}))
