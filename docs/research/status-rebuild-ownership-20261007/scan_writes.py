"""Bounded offline candidate scan; offsets are candidates, never pointer-type proof."""
from pathlib import Path
import json,struct,hashlib,bisect
from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_WRITE
from capstone.x86 import X86_OP_MEM,X86_REG_RIP,X86_REG_RSP,X86_REG_RBP
folder=Path(__file__).resolve().parent
ev=json.loads((folder/'evidence.json').read_text())
raw=Path(ev['originalPath']).read_bytes();assert hashlib.sha256(raw).hexdigest()==ev['originalSha256']
base=int(ev['imageBase'],16);pe=struct.unpack_from('<I',raw,0x3c)[0]
ss=pe+24+struct.unpack_from('<H',raw,pe+20)[0]
sections={raw[ss+40*i:ss+40*i+8].rstrip(b'\0').decode():struct.unpack_from('<4I',raw,ss+40*i+8) for i in range(struct.unpack_from('<H',raw,pe+6)[0])}
def disk(rva,n):
    for vs,va,size,offset in sections.values():
        if va<=rva and rva+n<=va+size:return raw[offset+rva-va:offset+rva-va+n]
    raise AssertionError(hex(rva))
pv,pva,ps,po=sections['.pdata'];runtime=[]
for off in range(po,po+pv-11,12):
    start,end,unwind=struct.unpack_from('<III',raw,off)
    if start and start<end:runtime.append((start,end))
runtime.sort();starts=[x[0] for x in runtime]
def owner(rva):
    idx=bisect.bisect_right(starts,rva)-1
    return hex(base+runtime[idx][0]) if idx>=0 and rva<runtime[idx][1] else None
md=Cs(CS_ARCH_X86,CS_MODE_64);md.detail=True;md.skipdata=True
first,last=0x3A0000,0x435000
absolute=(430,520,568,572,580);ability=(56,104,108,116)
rows=[];decoded=0;skipped=0
for ins in md.disasm(disk(first,last-first),base+first):
    if ins.id==0:skipped+=ins.size;continue
    decoded+=1
    for op in ins.operands:
        if op.type!=X86_OP_MEM or not op.access&CS_AC_WRITE or op.mem.base in (X86_REG_RIP,X86_REG_RSP):continue
        offsets=[x for x in absolute if op.mem.disp<=x<op.mem.disp+op.size]
        relative=[x for x in ability if op.mem.disp<=x<op.mem.disp+op.size]
        # The relative ability search is restricted to its proven helper family;
        # wider direct-STATUS displacement candidates remain listed separately.
        indexed_coefficient=bool(op.mem.index and op.mem.disp==424)
        if offsets or indexed_coefficient or (relative and base+0x401000<=ins.address<base+0x401B00):
            rows.append({'addr':hex(ins.address),'pdataOwner':owner(ins.address-base),'instruction':ins.mnemonic+' '+ins.op_str,
                         'bytes':ins.bytes.hex(' '),'baseRegister':ins.reg_name(op.mem.base),'indexRegister':ins.reg_name(op.mem.index),
                         'displacement':op.mem.disp,'writeBytes':op.size,'absoluteCandidates':offsets,'abilityCandidates':relative,
                         'indexedCoefficientCandidate':indexed_coefficient})
result={'originalSha256':ev['originalSha256'],'scope':[hex(base+first),hex(base+last)],'decodedInstructions':decoded,
        'skippedDataBytes':skipped,'matches':rows,'limitation':'Linear offline scan finds displacement-overlap candidates only. It neither identifies STATUS pointer aliases nor proves absence of computed-address/bulk/foreign writes. Pdata owners may differ from IDA function boundaries.'}
(folder/'write-census.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'decoded':decoded,'matches':len(rows),'skippedBytes':skipped,'candidates':rows},indent=2))
