"""Reproduce exploratory displacement scans from the frozen historical inventory.
Not an all-writers proof; includes stack stores and unrelated object types.
"""
import argparse,json
import capstone
from capstone.x86 import X86_OP_MEM
from verify import HERE,PE,ORIGINAL,encoded,read

def run():
    pe=PE(ORIGINAL);md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);md.detail=True;md.skipdata=True
    tables=[];context=[]
    for row in read(HERE/'candidate-inventory.json'):
        a=int(row['address'],16)
        if not 0x1403c6100<=a<0x1403c9200:continue
        for i in md.disasm(pe.bytes(a,row['size']),a):
            if not i.id or not i.operands or i.operands[0].type!=X86_OP_MEM:continue
            op=i.operands[0]
            if i.mnemonic=='mov' and op.size==8 and op.mem.disp in (0,8) and i.reg_name(op.mem.base)!='rsp':
                tables.append({'function':hex(a),'addr':hex(i.address),'instruction':i.mnemonic+' '+i.op_str})
            if op.mem.disp in (24,328,344,352,432) and i.mnemonic in ('mov','and','or','xor','add','sub'):
                context.append({'function':hex(a),'addr':hex(i.address),'asm':i.mnemonic+' '+i.op_str})
    return {'original-table-write-candidates.json':{'scope':'Original instruction candidates in RVA3C6100..3C9200 only, no type or completeness claim.','matches':tables},'original-context-write-candidates.json':context}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--write',action='store_true');args=ap.parse_args()
    for name,obj in run().items():
        if args.write:(HERE/name).write_bytes(encoded(obj))
        else:assert read(HERE/name)==obj,name
    print('Two exploratory scans reproduced; candidates only.')
