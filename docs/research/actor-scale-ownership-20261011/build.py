"""Normalize the bounded read-only capture; no product or IDB changes."""
from pathlib import Path
import json,hashlib,copy
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
H=Path(__file__).resolve().parent;R=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir())
def load(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,j):(H/n).write_text(json.dumps(j,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def raw(s):return bytes(int(x,16) for x in s.split())
cap=load(H/'capture.json');cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
fresh=[]
for o in cap['functions']:
 f=copy.deepcopy(o);f['originalBytes']=raw(f.pop('idaBytes')).hex(' ');f['freshCapture']=True
 f['sourceMetadata']={'captureFile':'capture.json','captureSha256':sha(H/'capture.json')};fresh.append(f)
path=R/'docs/research/actor-scale-contract-20261007/evidence.json';old=load(path);deps=[]
for a in ['0x1403d9fe0','0x1403da250']:
 o=next(f for f in old['functions'] if f['addr']==a)
 f={k:copy.deepcopy(o[k]) for k in ['addr','name','size','pages']}
 f['disassembly']={k:copy.deepcopy(o[k]) for k in ['addr','asm','instruction_count','total_instructions','cursor']}
 f['pseudocode']={'code':o['analysis']['decompile'],'source':'Reused complete source analysis.decompile; no new decompile-page claim.'}
 f['originalBytes']=raw(o['originalBytes']).hex(' ');f['freshCapture']=False
 f['sourceMetadata']={'evidenceFile':path.relative_to(R).as_posix(),'evidenceSha256':sha(path)};deps.append(f)
refs=[]
for f in fresh+deps:
 a=int(f['addr'],16);b=bytes.fromhex(f['originalBytes']);f['sha256']=hashlib.sha256(b).hexdigest()
 rows=f['disassembly']['asm']['lines'];cursor=a;decoded=[];gaps=[]
 for row in rows:
  pc=int(row['addr'],16);assert pc>=cursor
  if pc>cursor:gaps.append({'addr':hex(cursor),'bytes':b[cursor-a:pc-a].hex(' '),'length':pc-cursor})
  i=next(cs.disasm(b[pc-a:],pc,count=1));cursor=pc+i.size
  decoded.append({'addr':hex(pc),'size':i.size,'bytes':i.bytes.hex(),'mnemonic':i.mnemonic,'operands':i.op_str})
  for o in i.operands:
   t=o.imm if o.type==X86_OP_IMM and o.imm>=0x140000000 else i.address+i.size+o.mem.disp if o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP else None
   if t is not None:refs.append({'site':hex(i.address),'target':hex(t),'mnemonic':i.mnemonic})
 if cursor<a+len(b):gaps.append({'addr':hex(cursor),'bytes':b[cursor-a:].hex(' '),'length':a+len(b)-cursor})
 f['instructions']=decoded;f['nonInstructionSpans']=gaps
data=[{'addr':x['addr'].lower(),'originalBytes':raw(x['data']).hex(' ')} for x in load(H/'data-capture.json')['regions']]
dump('evidence.json',{'schema':1,'Domain':'native','imageBase':'0x140000000','originalSha256':cap['originalSha256'],'functions':fresh,'dependencies':deps,'data':data,'positiveRefs':refs})
dump('dependencies.json',{'functions':deps})
pins=[{'path':path.relative_to(R).as_posix(),'sha256':sha(path)}]
for name in ['actor-scale-contract-20261007/report.md','actor-scale-contract-20261007/contract.json','actor-scale-projection-20261007/report.md','motion-payload-bounds-20261007/report.md']:
 p=R/'docs/research'/name
 if p.is_file():pins.append({'path':p.relative_to(R).as_posix(),'sha256':sha(p)})
dump('provenance.json',{'originalSha256':cap['originalSha256'],'dependencies':pins,'method':'Read-only explicit session2788299e on adopted lifetime.i64, fresh IDA disasm/decompile/get_bytes and xrefs. No autoanalysis, IDB mutation, game or native execution. Exact original PE comparison and Capstone decoding performed offline.','scope':'16 selected complete functions; two explicitly reused attachment helpers. No all-writers or global ownership census.'})
sources=[]
for p in sorted((R/'docs/research').glob('*/evidence.json')):
 j=load(p);matches=sorted({f['addr'] for f in fresh}&{str(f.get('addr','')).lower() for f in j.get('functions',[])})
 sources.append({'path':p.relative_to(R).as_posix(),'sha256':sha(p),'matchingFunctionAddresses':matches})
dump('priorwork-inventory.json',{'scope':'Only exact direct docs/research/*/evidence.json function arrays at authoring. Capture freshness is distinct from novelty; other files/claims not globally searched.','sources':sources})
print(json.dumps({'fresh':len(fresh),'reused':len(deps),'bytes':sum(f['size'] for f in fresh),'instructions':sum(len(f['instructions']) for f in fresh),'gaps':[(f['addr'],f['nonInstructionSpans']) for f in fresh+deps if f['nonInstructionSpans']],'matchingPrior':[x for x in sources if x['matchingFunctionAddresses']]}))

