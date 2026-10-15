"""Normalize fresh captures and explicitly reused bodies; own artifact folder only."""
from pathlib import Path
import json,hashlib,copy
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
H=Path(__file__).resolve().parent;R=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir())
def load(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,v):(H/n).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
def raw(s):return bytes(int(x,16) for x in s.split())
c=load(H/'capture.json');cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True;fresh=[];deps=[]
for row in c['functions']:
 f=copy.deepcopy(row);f['originalBytes']=raw(f.pop('idaBytes')).hex(' ');f['freshCapture']=True
 f['sourceMetadata']={'path':'capture.json','sha256':sha(H/'capture.json')};fresh.append(f)
p=R/'docs/research/actor-scale-ownership-20261011/evidence.json';old=load(p)
for addr in ['0x1401c6d00','0x1401c7e00','0x1401c9d60','0x1401c7440','0x1401b4b70']:
 f=copy.deepcopy(next(x for x in old['functions'] if x['addr']==addr));f['freshCapture']=False
 f['sourceMetadata']={'path':p.relative_to(R).as_posix(),'sha256':sha(p)};deps.append(f)
for f in fresh+deps:
 a=int(f['addr'],16);b=bytes.fromhex(f['originalBytes']);decoded=[];cursor=a;gaps=[]
 for row in f['disassembly']['asm']['lines']:
  pc=int(row['addr'],16);assert pc>=cursor
  if pc>cursor:gaps.append({'addr':hex(cursor),'bytes':b[cursor-a:pc-a].hex(' ')})
  i=next(cs.disasm(b[pc-a:],pc,count=1));cursor=pc+i.size
  decoded.append({'addr':hex(pc),'size':i.size,'bytes':i.bytes.hex(),'mnemonic':i.mnemonic,'operands':i.op_str})
 if cursor<a+len(b):gaps.append({'addr':hex(cursor),'bytes':b[cursor-a:].hex(' ')})
 f['instructions']=decoded;f['nonInstructionSpans']=gaps;f['sha256']=hashlib.sha256(b).hexdigest()
data=[{'addr':x['addr'].lower(),'originalBytes':raw(x['data']).hex(' ')} for x in load(H/'data-capture.json')['regions']]
dump('evidence.json',{'schema':1,'Domain':'native','imageBase':'0x140000000','originalSha256':c['originalSha256'],'functions':fresh,'data':data})
dump('dependencies.json',{'schema':1,'Domain':'native','imageBase':'0x140000000','originalSha256':c['originalSha256'],'functions':deps})
pins=[{'path':p.relative_to(R).as_posix(),'sha256':sha(p)}]
for name in ['bdx-trap-registry-20261008/evidence.json','bdx-trap-registry-20261008/report.json','bdx-bank-other-inventory-20261008/descriptors.json','actor-scale-ownership-20261011/manifest.json','actor-scale-ownership-20261011/vm.py']:
 p=R/'docs/research'/name;pins.append({'path':p.relative_to(R).as_posix(),'sha256':sha(p)})
dump('provenance.json',{'originalSha256':c['originalSha256'],'sourcePins':pins,'method':c['method'],'session':'2788299e','analysisState':'idb_list: is_analyzing=false; server_health: auto_analysis_ready=false. No autoanalysis requested. All claimed bytes independently compared to original PE.','freshBodies':len(fresh),'explicitlyReusedBodies':len(deps),'limits':'Fresh capture is not global novelty. Reused dispatcher findings are inherited and pinned, not newly captured here.'})
inventory=[]
for p in sorted((R/'docs/research').glob('*/evidence.json')):
 j=load(p);hits=sorted({f['addr'] for f in fresh}&{str(x.get('addr','')).lower() for x in j.get('functions',[])})
 if hits:inventory.append({'path':p.relative_to(R).as_posix(),'sha256':sha(p),'matchingAddresses':hits})
dump('priorwork-overlap.json',{'scope':'Exact direct functions arrays in docs/research/*/evidence.json only; no broad novelty or absence guarantee.','matches':inventory})
vm=(R/'docs/research/actor-scale-ownership-20261011/vm.py').read_text()
vm=vm.replace("elif m=='lea':", "elif m=='cdqe':self.setreg('rax',signed(self.getreg('eax'),32))\n   elif m=='lea':")
(H/'vm.py').write_text(vm,encoding='utf-8')
print(json.dumps({'fresh':len(fresh),'reused':len(deps),'freshBytes':sum(f['size'] for f in fresh),'freshInstructions':sum(len(f['instructions']) for f in fresh),'nonInstructionSpans':[(f['addr'],[(g['addr'],len(bytes.fromhex(g['bytes']))) for g in f['nonInstructionSpans']]) for f in fresh+deps if f['nonInstructionSpans']],'overlap':inventory}))
