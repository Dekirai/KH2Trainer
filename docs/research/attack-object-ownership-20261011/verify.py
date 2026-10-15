"""Reproduce bounded original-byte, capture, model and reference checks."""
import argparse,hashlib,json,pathlib,re,runpy
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from prepare import derive,PE,read,sha,ROOT,H,BASE,PIN
import machine_delta,models
checks=0
def need(v,label):
 global checks
 checks+=1
 if not v:raise AssertionError(label)
def emit(n,v,write):
 p=H/n
 if write:p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 else:need(read(p)==v,n+' reproduces')
def main(write=False):
 ev,deps,parserpin=derive();need(read(H/'evidence.json')==ev,'evidence reproduces from complete raw captures and pinned reuse')
 need(read(H/'dependencies.json')=={'dependencies':deps,'coverageParserSha256':parserpin},'dependency pins reproduce')
 need(sha(machine_delta.SOURCE.read_bytes())=='efcc53af5127c55a6f4357632e63811a7234b2f8a8f71b2dab21c8785f3b14d0','prior interpreter pin')
 need((H/'machine.py').read_text(encoding='utf-8-sig')==machine_delta.derived(),'interpreter only documented NOT/BTS delta')
 pe=PE();cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
 ins={};bodies=ev['functions']+ev['code_ranges'];rows=[]
 aliases={'jz':'je','jnz':'jne','retn':'ret','cmovz':'cmove','cmovnz':'cmovne','jnb':'jae','jnae':'jb','sal':'shl','movabs':'mov'}
 for f in bodies:
  start=int(f['addr'],16);raw=bytes.fromhex(f['originalBytes']);need(raw==pe.raw(start,f['size']),'complete original extent '+f['addr'])
  lines=f['disassembly']['asm']['lines'];covered=set()
  need([l for p in f['pages'] for l in p['asm']['lines']]==lines and f['pages'][-1]['cursor']['done'],'full page join')
  for l in lines:
   at=int(l['addr'],16);i=next(cs.disasm(raw[at-start:],at,count=1));ins[at]=i
   asm=l['instruction'].split(';')[0].strip().lower();mn=asm.split()[0]
   if asm=='xchg ax, ax':mn='nop'
   need(aliases.get(mn,mn)==aliases.get(i.mnemonic,i.mnemonic),'mnemonic '+hex(at))
   span=set(range(at,at+i.size));need(not span&covered and min(span)>=start and max(span)<start+len(raw),'instruction span');covered|=span
  need(len(covered)==len(raw),'entire byte extent accounted by recorded instructions')
  rows.append({'addr':f['addr'],'fresh':f['sourceMetadata']['freshCapture'],'size':len(raw),'instructions':len(lines)})
 for p in H.glob('root-xrefs*.json'):
  for r in read(p)['result']:need(not r.get('more',False),p.name+' not truncated')
 selected=[0x3CF870,0x3CF87B,0x3CF88C,0x3CF9BE,0x3CFA60,0x3CFA7B,0x3CFA8C,0x3CFAB6,0x3CFA27,
  0x3CFB41,0x3CFB5C,0x3CFBD1,0x3CFBE7,0x3CFBF3,0x3CFC2A,0x3CFC38,0x3CFC78,0x3CFC82,0x3CFC9A,
  0x3CFCE8,0x3CFD03,0x40F4B1,0x40F4B8,0x40F4E0,0x40F4E7,0x40F4FB,0x40F513,0x3CF810,0x3CF1F8,0x3CF20B,0x3CF21C]
 anchors=[]
 for r in selected:
  i=ins[BASE+r];anchors.append({'addr':hex(i.address),'bytes':bytes(i.bytes).hex(' '),'instruction':i.mnemonic+' '+i.op_str})
 emit('anchors.json',{'anchors':anchors,'scope':'Selected original instruction addresses; claims cite complete bodies'},write)
 result=models.run(ins,pe.raw,need);emit('model-results.json',result,write)
 refs=0
 parser=runpy.run_path(str(ROOT/'scripts/update-analysis-coverage.py'),run_name='bounded_reference_check')
 if (H/'report.json').exists():
  claims=read(H/'report.json')['claims']
  for c in claims:
   need({'addr','Finding','Evidence','Limitations'}<=c.keys(),'canonical claim')
   for reference in c['Evidence']:
    resolved=parser['resolve_reference'](H/'report.json',reference)
    need(resolved.get('status')=='exists','reference '+reference);refs+=1
 else:claims=[];need(write,'report required for final check')
 out={'status':'PASS','originalSha256':PIN,'functions':len(ev['functions']),'codeRanges':len(ev['code_ranges']),'freshBodies':sum(x['fresh'] for x in rows),'explicitReuseBodies':sum(not x['fresh'] for x in rows),'extentBytes':sum(x['size'] for x in rows),'instructions':len(ins),'dataBytes':sum(x['size'] for x in ev['data']),'anchors':len(anchors),'claims':len(claims),'resolvedEvidenceReferences':refs,'modelCases':result['caseCount'],'modelSteps':result['steps'],'modelDistinctInstructions':result['distinctExecutedInstructions'],'checksBeforeResultComparison':checks,'bodies':rows,'limits':result['limits']}
 # Count excludes equality comparisons of generated artifacts, so --write and
 # --check produce identical recorded output. Detailed assertions still run.
 out.pop('checksBeforeResultComparison')
 emit('verification.json',out,write)
 if not write and (H/'manifest.json').exists():
  members=read(H/'manifest.json')['files'];actual={p.relative_to(H).as_posix() for p in H.rglob('*') if p.is_file() and p!=H/'manifest.json'}
  need(actual=={x['path'] for x in members},'exact recursive manifest')
  for x in members:
   p=H/x['path'];need(p.stat().st_size==x['bytes'] and sha(p.read_bytes())==x['sha256'],x['path'])
 print(json.dumps({k:v for k,v in out.items() if k not in ['bodies','limits']}|{'assertionsThisRun':checks}))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--write',action='store_true');a.add_argument('--check',action='store_true');main(a.parse_args().write)
