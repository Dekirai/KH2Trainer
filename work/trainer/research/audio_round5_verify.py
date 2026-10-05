"""Compare the complete spatial-audio captures with the original retail PE.

Read-only toward the game and IDBs; outputs a reproducible research receipt.
"""
from pathlib import Path
import hashlib, json, struct, sys
ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'work/trainer/research'
sys.path.insert(0, str(ROOT / 'work/pe/deps'))
import pefile, capstone
from capstone.x86 import X86_OP_MEM, X86_REG_RIP
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
inventory = read(ROOT / 'work/pe/inventory.json')
raw = Path(inventory['path']).read_bytes()
digest = hashlib.sha256(raw).hexdigest()
assert digest == '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
pe = pefile.PE(data=raw)
base = pe.OPTIONAL_HEADER.ImageBase
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
captures = read(OUT / 'audio_round5_full_asm.json') + read(OUT / 'audio_round5_extra_asm.json')
byte_rows = read(OUT / 'audio_round5_code_bytes.json') + read(OUT / 'audio_round5_extra_asm.json')
by_address = {int(r['addr'], 16): r for r in byte_rows}
assert len(by_address) == len(captures) == 88
checks, ranges = 0, []
for capture in captures:
    addr = int(capture['addr'], 16)
    row = by_address[addr]
    data = bytes.fromhex(row['hex'])
    assert len(data) == int(row['size'])
    assert pe.get_data(addr-base, len(data)) == data
    checks += 2
    pages = capture['pages']
    total = pages[0]['total_instructions']
    offset = 0
    for n, page in enumerate(pages):
        lines = page['asm']['lines']
        assert page['instruction_count'] == len(lines)
        assert page['total_instructions'] == total
        assert not page['cursor'].get('cancelled')
        offset += len(lines)
        if n == len(pages)-1:
            assert page['cursor'].get('done') and 'next' not in page['cursor']
        else:
            assert not page['cursor'].get('done') and page['cursor']['next'] == offset
        checks += 4
        for line in lines:
            ea = int(line['addr'], 16)
            assert addr <= ea < addr+len(data)
            assert list(md.disasm(pe.get_data(ea-base, 15), ea, count=1))
            checks += 2
    assert offset == total
    checks += 1
    ranges.append({'address': hex(addr), 'bytes': len(data), 'instructions': total,
                   'sha256': hashlib.sha256(data).hexdigest()})
aux = read(OUT / 'audio_round5_aux_bytes.json')['result']
constants, anonymous = [], []
for row in aux:
    addr = int(row['addr'], 16)
    data = bytes(int(v,16) for v in row['data'].split())
    assert pe.get_data(addr-base,len(data)) == data
    checks += 1
    if len(data) == 4:
        constants.append({'address':hex(addr), 'float32':struct.unpack('<f',data)[0]})
    else:
        anonymous.append({'address':hex(addr), 'context_only':True,
                          'instructions':[{'addr':hex(i.address),'text':i.mnemonic+' '+i.op_str}
                                          for i in md.disasm(data,addr)]})
root_refs = read(OUT / 'audio_round5_global_xrefs.json')['result'][0]
assert root_refs['addr'] == '0x142B81DF8' and not root_refs['more']
assert len(root_refs['xrefs']) == root_refs['xref_count']
refs = []
for xref in root_refs['xrefs']:
    addr = int(xref['addr'],16)
    ins = next(md.disasm(pe.get_data(addr-base,15),addr,count=1))
    operations = [op for op in ins.operands if op.type == X86_OP_MEM and
                  op.mem.base == X86_REG_RIP and ins.address+ins.size+op.mem.disp == 0x142B81DF8]
    assert operations
    checks += 1
    refs.append({'address':hex(addr),'function':xref['fn'], 'text':ins.mnemonic+' '+ins.op_str,
                 'writes_root':any(op.access & capstone.CS_AC_WRITE for op in operations)})
receipt = {'target_sha256':digest,'scope':'Static original-PE comparison. No game process access or native execution.',
           'checks':checks,'failures':0,'functions':len(ranges),'bytes':sum(r['bytes'] for r in ranges),
           'instructions':sum(r['instructions'] for r in ranges),'ranges':ranges,
           'float_constants':constants,'root_references':refs,'anonymous_context':anonymous,
           'limitations':'No proof against computed references or external mods. Anonymous snippets are context, not invented function boundaries or semantic claims.'}
(OUT/'audio_round5_original_verification.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:receipt[k] for k in ['target_sha256','checks','failures','functions','bytes','instructions']}))
print(json.dumps({'root_writes':[r for r in refs if r['writes_root']], 'float_constants':constants,'anonymous_context':anonymous},indent=2))
