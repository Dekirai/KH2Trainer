"""Offline IDA/PE/header validation; no game or IDB access."""
from pathlib import Path
import json,struct,hashlib,re
from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_OP_MEM,CS_GRP_JUMP,CS_GRP_CALL
from capstone.x86_const import X86_REG_RIP,X86_REG_R11
p=Path(__file__).resolve().parent;root=p.parents[2]
e=json.loads((p/'evidence.json').read_text(encoding='utf-8'));raw=Path(e['originalPath']).read_bytes()
assert hashlib.sha256(raw).hexdigest()==e['originalSha256']
nt=struct.unpack_from('<I',raw,60)[0];opt=nt+24;base=int(e['imageBase'],16)
sh=opt+struct.unpack_from('<H',raw,nt+20)[0]
sections=[struct.unpack_from('<4I',raw,sh+40*i+8) for i in range(struct.unpack_from('<H',raw,nt+6)[0])]
def disk(addr,n):
 rva=addr-base
 for _,va,rs,off in sections:
  if va<=rva and rva-va+n<=rs:return raw[off+rva-va:off+rva-va+n]
 raise AssertionError((hex(addr),n))
def unhex(s):return bytes(int(x,16) for x in s.split())
header=(root/'src/KH2Trainer.Bridge/StatusEntryPlan.h').read_text(encoding='utf-8')
pins={int('140'+name,16):bytes(int(x,16) for x in re.findall(r'0x([0-9a-fA-F]+)',body))
 for name,body in re.findall(r'Body([0-9A-F]+)\[\]\s*=\s*\{(.*?)\};',header,re.S)}
prefixes={0x1403c0010:5,0x1403c1d90:7,0x1403c2650:5,0x1403c1880:10,0x1403c07e0:6}
md=Cs(CS_ARCH_X86,CS_MODE_64);md.detail=True
counts=0;bytecount=0;plans=[]
for f in e['functions']:
 a=int(f['addr'],16);body=unhex(f['original_bytes']);assert len(body)==f['size']
 assert body==disk(a,len(body))==pins[a]
 joined=[];offset=0
 for i,page in enumerate(f['pages']):
  rows=page['asm']['lines'];c=page['cursor'];assert page['offset']==offset and rows
  assert not c.get('cancelled',False) and page['instruction_count']==len(rows)
  assert page['total_instructions']==f['total_instructions']
  joined+=rows;offset+=len(rows)
  assert (i+1<len(f['pages']) and c.get('next')==offset and not c.get('done',False)) or (i+1==len(f['pages']) and c.get('done') is True and 'next' not in c)
 assert joined==f['asm']['lines'] and len(joined)==f['instruction_count']==f['total_instructions']
 assert f['cursor'].get('done') is True and not f['cursor'].get('cancelled',False)
 assert f['analysis']['cursor'].get('done') is True and not f['analysis'].get('truncated',False)
 ips=[int(x['addr'],16) for x in joined];assert ips==sorted(set(ips)) and ips[0]==a
 for index,line in enumerate(joined):
  ip=int(line['addr'],16);assert a<=ip<a+len(body)
  dec=list(md.disasm(body[ip-a:],ip,count=1));assert len(dec)==1
  ins=dec[0];assert ip+ins.size<=a+len(body)
  if index+1<len(ips):assert ip+ins.size<=ips[index+1]
  # No whole-body explicit operand uses R11. Calls follow the ordinary Win64 ABI.
  reads,writes=ins.regs_access();assert X86_REG_R11 not in reads and X86_REG_R11 not in writes
 pre=list(md.disasm(body[:prefixes[a]],a));assert sum(x.size for x in pre)==prefixes[a]
 for ins in pre:
  assert not ins.group(CS_GRP_JUMP) and not ins.group(CS_GRP_CALL)
  assert all(op.type!=CS_OP_MEM or op.mem.base!=X86_REG_RIP for op in ins.operands)
 plans.append({'addr':f['addr'],'prefixBytes':body[:prefixes[a]].hex(' '),'prefixSize':prefixes[a],
  'boundaries':[x.address-a for x in pre]+[prefixes[a]],'relocationOperands':0})
 counts+=len(joined);bytecount+=len(body)
pe=json.loads((p/'pe-unwind.json').read_text(encoding='utf-8'));dataBytes=0
for entry in pe['entries']:
 a=int(entry['addr'],16);assert unhex(entry['preceding16'])==disk(a-16,16)
 for row in entry['records']:
  rt=unhex(row['runtimeBytes']);uw=unhex(row['unwindBytes'])
  assert rt==disk(base+int(row['tableRva'],16),12)
  assert uw==disk(base+int(row['unwindRva'],16),len(uw))
  assert struct.unpack('<III',rt)==tuple(int(row[k],16) for k in ['begin','end','unwindRva'])
  dataBytes+=12+len(uw)
assert len(pins)==len(e['functions'])==5
result={'success':True,'functions':len(e['functions']),'instructions':counts,'originalBytes':bytecount,
 'unwindRecordBytes':dataBytes,'prefixes':plans,'headerSha256':hashlib.sha256((root/'src/KH2Trainer.Bridge/StatusEntryPlan.h').read_bytes()).hexdigest(),
 'limitations':'Exact-build relocation and saved bodies only; does not prove live installation quiescence or arbitrary mod-writer coverage.'}
(p/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))
