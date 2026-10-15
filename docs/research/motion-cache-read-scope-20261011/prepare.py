"""Normalize existing evidence and Root-proxy captures; never opens IDA or changes source."""
import json,hashlib,pathlib
H=pathlib.Path(__file__).resolve().parent
ROOT=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir())
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def put(n,v): (H/n).write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def unwrap(d): return d.get('structuredContent',d)
def bs(s): return bytes(int(x,16) for x in s.split())
def addr(a): return int(a,16)
SOURCES={
'motion-resource-binding-20261011':[0x39CC40,0x39D460,0x39D590,0x39DA10,0x39DEE0,0x39E000,0x39E1E0,0x39E2A0,0x39E690,0x39E900,0x3A6840,0x3A6A10,0x1C5F20,0x1C3840,0x1D2610,0x1DAFB0],
'drive-preconstructor-20261007':[0x39CCA0,0x39E340,0x3A0BD0,0x3A0790,0x3A0C60,0x3A64F0,0x3A6120],
'drive-provider-binding-20261007':[0x15EC70,0x15ED20,0x16C9B0,0x16C9D0,0x0FDD90,0x3F9850,0x106700,0x12F070,0x12E5C0],
'actor-task-context-20261008':[0x14F770,0x150060,0x135470],
'bdx-system-calls-20261008':[0x3A0A30],
'drive-skeleton-guard-20261007':[0x39DBB0],
}
fs=[]; dependencies=[]
def norm(f,source,fresh=False):
 a=addr(f['addr']); size=int(f['size'],0) if isinstance(f['size'],str) else f['size']
 raw=f.get('originalBytes',f.get('bytes'))
 if raw is None:
  chunks=f['original_bytes']; chunks=sorted(chunks,key=lambda x:addr(x['addr'])); raw=b''; pos=a
  for c in chunks:
   assert addr(c['addr'])==pos
   b=bs(c['data']);raw+=b;pos+=len(b)
 else:raw=bs(raw)
 assert len(raw)==size,(f['addr'],len(raw),size)
 asm=f.get('disassembly',{}).get('asm',f.get('asm')); asm={'lines':asm} if isinstance(asm,list) else asm
 pages=f.get('pages')
 if pages is None: pages=[{'addr':hex(a),'asm':asm,'instruction_count':len(asm['lines']),'total_instructions':len(asm['lines']),'cursor':{'done':True},'normalization':'source stores complete ASM lines without page envelope'}]
 pseudo=f['pseudocode']; pp=pseudo if isinstance(pseudo,list) else pseudo.get('pages',[pseudo])
 return {'addr':hex(a),'size':size,'name':asm.get('name',f.get('name','sub_'+format(a,'X'))),'source':source,'freshCapture':fresh,'complete':True,'originalBytes':raw.hex(' '),'sha256':hashlib.sha256(raw).hexdigest(),'pages':pages,'disassembly':{'addr':hex(a),'asm':asm,'instruction_count':len(asm['lines']),'total_instructions':len(asm['lines']),'cursor':{'done':True}},'pseudocode':{'pages':pp,'code':'\n'.join(x['code'] for x in pp),'complete':True}}
for n,rs in SOURCES.items():
 p=ROOT/'docs/research'/n/'evidence.json';d=read(p);dependencies.append({'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'functions':[hex(0x140000000+r) for r in rs]})
 for r in rs:
  f=next(x for x in d['functions'] if addr(x['addr'])==0x140000000+r)
  fs.append(norm(f,p.relative_to(ROOT).as_posix()+'#functions[addr='+f['addr'].lower()+']'))
rawbytes={}
for n in ['root-bytes.json','root-bytes-worker.json','root-bytes-scheduling.json']:
 for b in unwrap(read(H/n))['result']:rawbytes[addr(b['addr'])]=b['data']
lookups={}
for n in ['root-lookup.json','root-lookup-worker.json','root-lookup-scheduling.json']:
 for f in unwrap(read(H/n))['result']:lookups[addr(f['fn']['addr'])]=f['fn']
for a,look in lookups.items():
 tag=hex(a);dis=unwrap(read(H/('root-disasm-'+tag+'.json')));dec=unwrap(read(H/('root-decompile-'+tag+'.json')))
 f={'addr':tag,'size':look['size'],'originalBytes':rawbytes[a],'asm':dis['asm'],'pages':[dis],'pseudocode':dec}
 fs.append(norm(f,'root-disasm-'+tag+'.json',True))
fs.sort(key=lambda f:addr(f['addr'])); assert len({f['addr'] for f in fs})==len(fs)
contextPaths=['docs/research/drive-provider-binding-20261007/report.md','docs/research/motion-resource-binding-20261011/report.md','docs/research/motion-resource-binding-20261011/raw/disasm-0x1403C88C0-0.json']
contextDependencies=[{'path':p,'sha256':sha(ROOT/p)} for p in contextPaths]
put('dependencies.json',{'dependencies':dependencies,'contextDependencies':contextDependencies,'reusePolicy':'Existing complete bodies are reused dependencies, not newly discovered functions. Fresh cross-captures are identified separately.'})
ranges=[f for f in fs if addr(f['addr'])==0x14039dee0]
assert len(ranges)==1
ranges[0]['asm']=ranges[0]['disassembly']['asm']
ranges[0]['observed_line_count']=len(ranges[0]['asm']['lines'])
ranges[0].update({'end_exclusive':hex(addr(ranges[0]['addr'])+ranges[0]['size']),'classification':'separate_code_range_not_inventory_function','note':'Complete19-byte/six-instruction completion callback; preserved as a separate code range, never counted as an inventory function.'})
put('evidence.json',{'schema':'bounded-native-evidence-v2','originalSha256':'9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed','functions':[f for f in fs if f not in ranges],'code_ranges':ranges})
print('Normalized',len(fs),'bodies;',sum(x['freshCapture'] for x in fs),'fresh captures, remainder explicit reuse')
