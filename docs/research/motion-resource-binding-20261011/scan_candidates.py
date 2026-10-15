"""Bounded candidate discovery in original bytes, not an all-writers claim."""
import capstone,json,pathlib,struct,hashlib
from capstone.x86 import X86_OP_MEM
ROOT=next(p for p in pathlib.Path(__file__).resolve().parents if (p/'src/KH2Trainer.Core').is_dir())
HERE=pathlib.Path(__file__).resolve().parent
data=pathlib.Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe').read_bytes()
assert hashlib.sha256(data).hexdigest()=='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
p=struct.unpack_from('<I',data,0x3c)[0];n=struct.unpack_from('<H',data,p+6)[0];z=struct.unpack_from('<H',data,p+20)[0]
sections=[struct.unpack_from('<8sIIII',data,p+24+z+40*i) for i in range(n)]
def b(a,n):
    rva=a-0x140000000
    for _,vs,rv,rs,fo in sections:
        if rv<=rva and rva+n<=rv+rs:return data[fo+rva-rv:fo+rva-rv+n]
    raise ValueError(a)
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);md.detail=True;md.skipdata=True
out=[];bodies=0
for row in json.loads((HERE/'candidate-inventory.json').read_text()):
    a=int(row.get('address','0'),16)
    if not 0x1403a0000<=a<0x140410000:continue
    bodies+=1
    for ins in md.disasm(b(a,row['size']),a):
        if not ins.id or not ins.operands:continue
        op=ins.operands[0]
        if op.type==X86_OP_MEM and op.mem.disp in (344,352,1464) and ins.mnemonic in ('mov','inc','dec','add','sub','and','or','xor'):
            out.append({'function':hex(a),'addr':hex(ins.address),'instruction':ins.mnemonic+' '+ins.op_str,'bytes':ins.bytes.hex(' ')})
result={'scope':'Original-body linear decode in RVA3A0000..410000 with Capstone skipdata; candidates only, no completeness/all-writers claim. Fresh IDA bodies required before semantic attribution.','bodiesConsidered':bodies,'matches':out}
(HERE/'original-store-candidates.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
