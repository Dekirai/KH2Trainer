"""Normalize complete read-only Root IDA captures without modifying those captures."""
from pathlib import Path
import copy, hashlib, json
from discover import base, raw, cs, SHA
H=Path(__file__).resolve().parent;R=next(p for p in H.parents if (p/'Directory.Build.props').exists())
def load(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):(H/n).write_text(json.dumps(x,indent=2)+'\n')
def pin(p):return dict(path=p.relative_to(R).as_posix(),sha256=sha(p))
def normalized(tag,rva,regions,decode=None):
 p=H/f'root-ida-{tag}-disasm.json';asm=load(p);assert asm['cursor']=={'done':True}
 spans=[dict(addr=hex(base+a),data=raw(a,n).hex(' '))for a,n in regions]
 instr=[];used=set()
 for row in asm['asm']['lines']:
  a=int(row['addr'],16);b=next(bytes.fromhex(s['data'])[a-int(s['addr'],16):]for s in spans if int(s['addr'],16)<=a<int(s['addr'],16)+len(bytes.fromhex(s['data'])))
  x=next(cs.disasm(b,a,count=1));instr.append(dict(addr=hex(a),size=x.size,bytes=x.bytes.hex(),mnemonic=x.mnemonic,operands=x.op_str));used.update(range(a,a+x.size))
 gaps=[]
 for a,n in regions:
  left=[q for q in range(base+a,base+a+n)if q not in used]
  for q in left:gaps.append(dict(addr=hex(q),bytes=raw(q-base,1).hex()))
 discrepancies=[]
 if rva==0x4391d8:
  assert dict(addr='0x140439317',bytes='8b')in gaps
  gaps.remove(dict(addr='0x140439317',bytes='8b'))
  discrepancies=[dict(addr='0x140439317',originalBytes='8b c3',originalDecode='mov eax, ebx',ida='Byte439317 omitted; RET recorded at439318, the second byte of the original instruction. Branch439310 targets439317.',scope='Raw IDA aggregate retained unchanged. Startup claim uses only earlier initialization block; no claim of correct whole-startup disassembly. No IDB repair.')]
 row=dict(addr=hex(base+rva),name=asm['asm']['name'],size=sum(n for a,n in regions),freshCapture=True,disassembly=asm,pages=[asm],originalBytes=spans,instructions=instr,nonInstructionSpans=gaps,knownDisassemblyDiscrepancies=discrepancies,sourceMetadata=pin(p))
 if discrepancies:
  row['complete']=False
  row['uncoveredInstructionBytes']=[dict(addr='0x140439317',bytes='8b',reason='First byte of MOV EAX,EBX omitted by IDA; second byte incorrectly decoded as RET.')]
 if decode:row['pseudocode']=load(H/decode)
 return row
fresh=[normalized('initializer',0x96b0,[(0x96b0,620)],'root-ida-initializer-decompile.json'),normalized('startup',0x4391d8,[(0x4391d8,369),(0x5705aa,29)],'root-ida-startup-decompile.json'),normalized('startup-initterm',0x471c64,[(0x471c64,6)])]
deps=[];pins=[]
for name,targets in [('evidence.json',['0x140536480','0x1405364b0','0x1401b4b80','0x1401c7bf0','0x1401b2870','0x14053fa00','0x1401cd150','0x1401b7d20']),('dependencies.json',['0x1401c6d00','0x1401c7e00','0x1401c9d60'])]:
 p=R/'docs/research/stitch-scale-dispatch-20261011'/name;old=load(p);pins.append(pin(p))
 for a in targets:
  f=copy.deepcopy(next(x for x in old['functions']if x['addr']==a));f['freshCapture']=False;f['sourceMetadata']=pin(p);deps.append(f)
data=[dict(addr=hex(base+a),originalBytes=raw(a,n).hex(' '))for a,n in [(0x57bca8,8),(0x57d230,8),(0x584e18,8),(0x724340,504),(0x57b988,8)]]
prefix=copy.deepcopy(fresh[1]['disassembly']);prefix['asm']['lines']=[x for x in prefix['asm']['lines']if int(x['addr'],16)<base+0x439260];prefix['instruction_count']=prefix['total_instructions']=len(prefix['asm']['lines'])
block=dict(addr='0x1404391d8',size=136,disassembly=prefix,pages=[prefix],originalBytes=raw(0x4391d8,136).hex(' '),note='Bounded startup initialization prefix ending after JMP at43925E. Branch/call targets can leave the range. Original and recorded IDA instruction boundaries agree here; whole startup function explicitly complete:false due later decode discrepancy.',sourceMetadata=fresh[1]['sourceMetadata'])
dump('evidence.json',dict(schema=1,Domain='native',imageBase=hex(base),originalSha256=SHA,functions=fresh,code_ranges=[block],data=data))
dump('dependencies.json',dict(schema=1,Domain='native',imageBase=hex(base),originalSha256=SHA,functions=deps))
p=R/'docs/research/bdx-inspection-20261008/evidence.json';pins.append(pin(p));old=load(p)
f=copy.deepcopy(next(x for x in old['functions']if x['addr'].lower()=='0x14041c900'));f['addr']=f['addr'].lower();f['freshCapture']=False;f['sourceMetadata']=pin(p);f['instructions']=[]
for row in f['disassembly']['asm']['lines']:
 a=int(row['addr'],16);x=next(cs.disasm(raw(a-base,15),a,count=1));f['instructions'].append(dict(addr=hex(a),size=x.size,bytes=x.bytes.hex(),mnemonic=x.mnemonic,operands=x.op_str))
deps.append(f)
dump('dependencies.json',dict(schema=1,Domain='native',imageBase=hex(base),originalSha256=SHA,functions=deps))
for p in [R/'docs/research/stitch-scale-dispatch-20261011/manifest.json',R/'docs/research/stitch-scale-dispatch-20261011/report.json',R/'docs/research/bdx-inspection-20261008/bdx_inspect.py',R/'scripts/update-analysis-coverage.py']+[R/'src/KH2Trainer.Core'/n for n in ['AssetArchiveReader.cs','AssetPackageCodec.cs','AssetExplorerModels.cs','AssetFileAccess.cs']]:pins.append(pin(p))
dump('provenance.json',dict(originalSha256=SHA,sourcePins=pins,idaAuthority={'localList':'2788299e, stale PID34084; first read failed worker not reachable. Local supervisor did not know28e14b48. No restart/open/mutation attempted.','captures':'Root successfully used existing28e14b48/PID71984 and wrote root-ida-*.json directly into this folder. Complete finished pages preserved. No autoanalysis requested.','limits':'Current readiness is not a completeness guarantee; every recorded byte is checked independently against Original PE.'},method='Raw PE seeds selected0096B0; new Root IDA capture plus exact original bytes; imported_initterm contract is external documented premise, not locally executed or captured implementation.',startupExtent='IDA aggregate includes discontiguous439341..439348 and5705AA..5705C7 chunks. Original spans retain two non-ASM NOPs439340/439348 explicitly. Lookup-reported0x168 alone was insufficient. One known decode mismatch at439317/439318 is preserved and bounded; complete IDA pages do not imply correct whole-body disassembly.',freshBodies=len(fresh),reusedBodies=len(deps)))
matches=[]
for p in sorted((R/'docs/research').glob('*/evidence.json')):
 j=load(p);hits=sorted({f['addr']for f in fresh}&{str(x.get('addr','')).lower()for x in j.get('functions',[])})
 if hits:matches.append(dict(**pin(p),addresses=hits))
dump('priorwork-overlap.json',dict(scope='Exact functions arrays in docs/research/*/evidence.json only. Fresh capture is not a global novelty guarantee.',matches=matches))
print(json.dumps(dict(fresh=len(fresh),reused=len(deps),freshInstructions=sum(len(f['instructions'])for f in fresh),freshBytes=sum(f['size']for f in fresh),nonInstructionBytes=sum(len(f['nonInstructionSpans'])for f in fresh))))
