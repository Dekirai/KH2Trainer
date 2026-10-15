"""Reproduce only static original-byte and bounded synthetic checks, no live calls."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, struct
import discover as pe
from model import run_cases
import scripts
H=Path(__file__).resolve().parent;R=next(p for p in H.parents if (p/'Directory.Build.props').exists())
ap=argparse.ArgumentParser();ap.add_argument('--write',action='store_true');args=ap.parse_args()
def load(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
checks=0
def check(x,msg='check'):
 global checks
 checks+=1
 assert x,msg
def module(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
parser=module('unchanged_coverage_helpers',R/'scripts/update-analysis-coverage.py')
for pin in load(H/'provenance.json')['sourcePins']:check(sha(R/pin['path'])==pin['sha256'],pin['path'])
captured={}
for p in sorted(H.glob('root-ida-*-bytes.json')):
 for x in load(p)['result']:
  a=int(x['addr'],16);b=bytes(int(v,16)for v in x['data'].split());check(pe.raw(a-pe.base,len(b))==b,p.name)
  for i,v in enumerate(b):
   if a+i in captured:check(captured[a+i]==v,'overlap')
   captured[a+i]=v
e=load(H/'evidence.json');deps=load(H/'dependencies.json');counts=[]
for f in e['functions']+deps['functions']:
 spans=parser.original_spans(f);check(sum(len(b)for a,b in spans)==f['size'],'extent')
 for a,b in spans:
  check(pe.raw(a-pe.base,len(b))==b,'original span')
  if f['freshCapture']:check(all(captured.get(a+i)==v for i,v in enumerate(b)),'fresh IDA byte coverage')
 ok,addrs,reason=parser.body_assembly(f)
 if f['addr']=='0x1404391d8':check(not ok and 'incomplete'in reason,'startup rejected from complete body coverage')
 else:check(ok,reason)
 lines=f['disassembly']['asm']['lines'];check(f['pages'][0]['asm']['lines']==lines,'complete page join')
 for ins in f['instructions']:
  a=int(ins['addr'],16);x=next(pe.cs.disasm(pe.raw(a-pe.base,15),a,count=1))
  check(x.bytes.hex()==ins['bytes']);check(x.size==ins['size']);check(x.mnemonic==ins['mnemonic'])
 counts.append(dict(addr=f['addr'],fresh=f['freshCapture'],bytes=f['size'],idaInstructions=len(lines),completeBodyAccepted=ok))
f=e['functions'][1];check(f['uncoveredInstructionBytes'][0]['addr']=='0x140439317')
check(pe.raw(0x439317,2)==b'\x8b\xc3')
check([x['addr']for x in f['nonInstructionSpans']]==['0x140439340','0x140439348'])
block=e['code_ranges'][0];ok,addrs,reason=parser.body_assembly(block);check(ok,reason)
decoded=list(pe.cs.disasm(pe.raw(0x4391d8,136),pe.base+0x4391d8));check([x.address for x in decoded]==addrs,'prefix exact boundaries');check(sum(x.size for x in decoded)==136)
# Anchors express actual addresses/operands, rather than loose text labels.
def one(r):return next(pe.cs.disasm(pe.raw(r,15),pe.base+r,count=1))
def rip(x,o):return x.address+x.size+o.mem.disp
for r,target in [(0x439241,0x584e18),(0x439248,0x57bca8),(0x1c6d25,0x724340)]:
 x=one(r);check(x.mnemonic=='lea'and rip(x,x.operands[1])==pe.base+target)
x=one(0x43924f);check(x.mnemonic=='call'and x.operands[0].imm==pe.base+0x471c64)
x=one(0x471c64);check(x.mnemonic=='jmp'and rip(x,x.operands[0])==pe.base+0x57b988)
check(struct.unpack('<Q',pe.raw(0x57d230,8))[0]==pe.base+0x96b0)
check(0x57bca8<=0x57d230<0x584e18 and(0x57d230-0x57bca8)%8==0)
for x in e['data']:check(pe.raw(int(x['addr'],16)-pe.base,len(bytes.fromhex(x['originalBytes'])))==bytes.fromhex(x['originalBytes']))
# Parse the original import descriptors independently of IDA names.
ir,iz=struct.unpack_from('<II',pe.B,pe.opt+120);imports=[]
while True:
 ilt,ts,fwd,name,iat=struct.unpack('<5I',pe.raw(ir,20));ir+=20
 if not(ilt or name or iat):break
 dll=pe.raw(name,100).split(b'\0')[0].decode()
 for k in range(10000):
  q=struct.unpack('<Q',pe.raw((ilt or iat)+k*8,8))[0]
  if not q:break
  if q>>63:continue
  text=pe.raw(q+2,120).split(b'\0')[0].decode()
  if text in ('_initterm','_initterm_e'):imports.append(dict(dll=dll,name=text,iatRva=hex(iat+k*8),hintNameRva=hex(q)))
check(next(x for x in imports if x['name']=='_initterm')==dict(dll='api-ms-win-crt-runtime-l1-1-0.dll',name='_initterm',iatRva='0x57b988',hintNameRva='0x7116fa'))
imp=dict(originalSha256=pe.SHA,imports=imports,limits='Original import names and IAT slots, not resolved live pointers or loaded CRT implementation.')
if args.write:(H/'imports.json').write_text(json.dumps(imp,indent=2)+'\n')
model=run_cases();checks+=model['checks']
check(model==load(H/'model-results.json'),'model reproduction')
script=scripts.build();check(script==load(H/'script-evidence.json'),'stored-script reproduction')
doc=script['document'];check(len(doc['instructions'])==832)
data=scripts.P.read_bytes();off=script['barEntry']['offset'];length=script['barEntry']['length'];data=data[off:off+length]
for x in doc['instructions']:
 check(data[x['fileOffset']:x['fileOffset']+2*x['width']].hex()==x['raw'],'stored instruction span')
check([x['pc']for x in script['selectedSites']]==[87,121,155,394,1041])
for x,action in zip(script['selectedSites'][:3],[525,526,527]):
 a,b=x['precedingBlock'];check((a['group'],a['mode'],a['sub'],a['operands'])==(0,2,2,[80]));check((b['group'],b['mode'],b['operands'])==(0,0,[action,0]));check(a['pc']+a['width']==b['pc']and b['pc']+b['width']==x['pc'])
for x in script['selectedSites'][3:]:
 p=x['precedingBlock'][-1];check((p['group'],p['mode'],p['sub'],p['operands'])==(0,2,2,[20]));check(p['pc']+p['width']==x['pc'])
for x in script['selectedSites']:
 for witness in x['eventPaths']:
  path=witness['path'];check(bool(path),'nonempty witness')
# Parser reference resolution is read-only; no global inventory/coverage writes.
refs=[s for c in load(H/'report.json')['claims']for s in c['Evidence']]
for s in refs:check(parser.resolve_reference(H/'report.json',s)['status']=='exists',s)
result=dict(status='PASS',checks=checks,originalSha256=pe.SHA,functions=counts,freshRecordedBytes=1024,freshReportedIDAInstructions=209,freshCompleteAcceptedBodies=2,boundedStartupRangeBytes=136,startupDecodeMismatchExplicitlyRejected=True,scriptInstructions=832,selectedRetailScripts=1,selectedCallsites=5,modelCases=model['cases'],interpretedInstructions=model['interpretedInstructions'],references=len(refs),limits='Static Original PE and stored-script evidence; complete:false startup is not admitted as a fully decoded function. No game/live/native execution, full CRT implementation, event feasibility, binding identity, lifetime, race or feature-readiness proof.')
if args.write:
 (H/'imports.json').write_text(json.dumps(imp,indent=2)+'\n');(H/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
else:check(imp==load(H/'imports.json'));check(result==load(H/'verification.json'))
print(json.dumps(result))
