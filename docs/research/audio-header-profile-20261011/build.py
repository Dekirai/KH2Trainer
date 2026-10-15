"""Offline authoring: normalize pinned IDA captures and original bytes only."""
from pathlib import Path
import json,hashlib,struct,copy
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
H=Path(__file__).resolve().parent;R=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir())
def load(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,j):(H/n).write_text(json.dumps(j,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def idabytes(f):return bytes(int(x,16) for x in f['idaBytes'].split()) if 'idaBytes' in f else bytes.fromhex(f['originalBytes'])
cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
fresh=[]
for name in ['capture.json','capture-2.json']:
 cap=load(H/name)
 for original in cap['functions']:
  f=copy.deepcopy(original);f['originalBytes']=idabytes(f).hex(' ');f['sha256']=hashlib.sha256(idabytes(f)).hexdigest();f['freshCapture']=True
  f['sourceMetadata']={'captureFile':name,'captureSha256':sha(H/name),'document':{k:v for k,v in cap.items() if k!='functions'}}
  fresh.append(f)
deps=[];pins=[]
for study,addrs in [('voice-origin-resources-20261011',['0x14009fbd0','0x14009fd20']),('audio-bank-retirement-20261011',['0x140089390'])]:
 path=R/'docs/research'/study/'evidence.json';j=load(path);pins.append({'path':path.relative_to(R).as_posix(),'sha256':sha(path)})
 for a in addrs:
  orig=next(x for x in j['functions'] if x['addr']==a);f=copy.deepcopy(orig)
  f['originalBytes']=idabytes(f).hex(' ');f['sha256']=hashlib.sha256(idabytes(f)).hexdigest();f['freshCapture']=False
  f['sourceMetadata']={'evidenceFile':path.relative_to(R).as_posix(),'evidenceSha256':sha(path)};deps.append(f)
for f in fresh+deps:
 a=int(f['addr'],16);b=bytes.fromhex(f['originalBytes']);rows=f['disassembly']['asm']['lines'];decoded=[];gaps=[];cursor=a
 for row in rows:
  pc=int(row['addr'],16)
  assert pc>=cursor
  if pc>cursor:gaps.append({'addr':hex(cursor),'bytes':b[cursor-a:pc-a].hex(' '),'length':pc-cursor})
  i=next(cs.disasm(b[pc-a:],pc,count=1));decoded.append({'addr':hex(pc),'size':i.size,'bytes':i.bytes.hex(),'mnemonic':i.mnemonic,'operands':i.op_str});cursor=pc+i.size
 if cursor<a+len(b):gaps.append({'addr':hex(cursor),'bytes':b[cursor-a:].hex(' '),'length':a+len(b)-cursor})
 f['instructions']=decoded;f['nonInstructionSpans']=gaps
data=[]
for x in load(H/'data-capture.json')['regions']:
 data.append({'addr':x['addr'],'originalBytes':bytes(int(v,16) for v in x['data'].split()).hex(' ')})
refs=[]
for f in fresh+deps:
 for row in f['instructions']:
  i=next(cs.disasm(bytes.fromhex(row['bytes']),int(row['addr'],16),count=1))
  for o in i.operands:
   target=o.imm if o.type==X86_OP_IMM and o.imm>=0x140000000 else i.address+i.size+o.mem.disp if o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP else None
   if target is not None:refs.append({'site':hex(i.address),'target':hex(target),'mnemonic':i.mnemonic})
dump('evidence.json',{'schema':1,'Domain':'native','imageBase':'0x140000000','originalSha256':cap['originalSha256'],'functions':fresh,'dependencies':deps,'data':data,'positiveRefs':refs})
dump('dependencies.json',{'functions':deps})
dump('provenance.json',{'originalSha256':cap['originalSha256'],'dependencies':pins,'method':'Read-only MCP disasm/decompile/get_bytes from existing adopted session2788299e; complete page cursors. No autoanalysis or IDB mutation. Capstone normalization is offline; no native execution.','autoAnalysisReady':False})
inventory=[]
targets={x['addr'] for x in fresh}
for p in sorted((R/'docs/research').glob('*/evidence.json')):
 j=load(p);matches=sorted(targets & {f.get('addr') for f in j.get('functions',[])})
 inventory.append({'path':p.relative_to(R).as_posix(),'sha256':sha(p),'matchingFunctionAddresses':matches})
dump('priorwork-inventory.json',{'scope':'Only function arrays of these exact evidence.json files observed at authoring time, not a global novelty guarantee.','sources':inventory,'freshCapturedAddresses':sorted(targets)})
print(json.dumps({'fresh':len(fresh),'reused':len(deps),'freshBytes':sum(f['size'] for f in fresh),'freshInstructions':sum(len(f['instructions']) for f in fresh),'gaps':[{ 'addr':f['addr'],'spans':f['nonInstructionSpans']} for f in fresh if f['nonInstructionSpans']],'alreadySeen':[x for x in inventory if x['matchingFunctionAddresses']]}))
