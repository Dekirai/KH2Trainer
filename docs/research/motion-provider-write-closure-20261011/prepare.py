"""Normalize pinned complete historical bodies and fresh Root-proxy captures, offline only."""
import hashlib,json,pathlib
H=pathlib.Path(__file__).resolve().parent
ROOT=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir())
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def put(n,v):(H/n).write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def a(s):return int(s,16)
def bs(s):return bytes(int(x,16) for x in s.split())
def un(d):return d.get('structuredContent',d)
SOURCES={
'drive-provider-binding-20261007':[0x3F9850,0x106700,0x106940,0x12F070,0x12E5C0,0x12CD80,0x12D8E0,0x12E460,0x12D5A0,0x14F1E0],
'drive-effective-bytes-20261007':[0x107620,0x1062B0,0x4696F0],
'actor-free-closure-20261008':[0x12EE70,0x12DBB0,0x12E100],
'voice-resource-teardown-20261011':[0x12EF30,0x12EEA0,0x12EF80],
'drive-preconstructor-20261007':[0x3A64F0],
'motion-resource-binding-20261011':[0x39E690,0x3A6840,0x3A6A10],
}
def norm(f,source,fresh=False):
 va=a(f['addr']);size=f.get('size');size=int(size,0) if isinstance(size,str) else size
 raw=f.get('originalBytes',f.get('bytes'))
 if raw is None:
  chunks=f['original_bytes'];chunks=[chunks] if isinstance(chunks,dict) else chunks;raw=b'';pos=va
  for c in sorted(chunks,key=lambda c:a(c['addr'])):
   assert a(c['addr'])==pos;b=bs(c['data']);raw+=b;pos+=len(b)
 else:raw=bs(raw)
 if size is None:size=len(raw)
 assert len(raw)==size
 asm=f.get('disassembly',{}).get('asm',f.get('asm'));asm={'lines':asm} if isinstance(asm,list) else asm
 pages=f.get('pages') or [f['disassembly']]
 pc=f.get('pseudocode',f.get('pc'));pp=pc if isinstance(pc,list) else pc.get('pages',[pc])
 return {'addr':hex(va),'size':size,'source':source,'freshCapture':fresh,'complete':True,'originalBytes':raw.hex(' '),'sha256':hashlib.sha256(raw).hexdigest(),'asm':asm,'pages':pages,'disassembly':{'addr':hex(va),'asm':asm,'instruction_count':len(asm['lines']),'total_instructions':len(asm['lines']),'cursor':{'done':True}},'pseudocode':{'pages':pp,'code':'\n'.join(p['code'] for p in pp),'complete':True}}
fs=[];deps=[]
for n,rv in SOURCES.items():
 path='docs/research/'+n+'/evidence.json';d=read(ROOT/path);deps.append({'path':path,'sha256':sha(ROOT/path),'addresses':[hex(0x140000000+r) for r in rv]})
 for r in rv:
  f=next(f for f in d['functions'] if a(f['addr'])==0x140000000+r)
  fs.append(norm(f,path+'#functions[addr='+f['addr']+']'))
# Root can use several byte/lookup envelopes; all captured function identities must agree.
lookups={};rawbytes={}
for p in H.glob('root-lookup*.json'):
 for f in un(read(p))['result']:
  if f.get('fn'):lookups[a(f['fn']['addr'])]=f['fn']
for p in H.glob('root-bytes*.json'):
 for b in un(read(p))['result']:rawbytes[a(b['addr'])]=b['data']
for p in H.glob('root-disasm-*.json'):
 d=un(read(p));va=a(d['addr']);tag=hex(va);pc=un(read(H/('root-decompile-'+tag+'.json')))
 f={'addr':tag,'size':lookups[va]['size'],'originalBytes':rawbytes[va],'asm':d['asm'],'pages':[d],'pseudocode':pc}
 fs.append(norm(f,p.name,True))
fs.sort(key=lambda f:a(f['addr']));assert len({f['addr'] for f in fs})==len(fs)
put('evidence.json',{'schema':'bounded-native-evidence-v1','originalSha256':'9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed','functions':fs})
context=['docs/research/motion-cache-read-scope-20261011/manifest.json','docs/research/motion-cache-read-scope-20261011/contract.md','docs/research/motion-cache-read-scope-20261011/root-session-health.json','docs/research/drive-provider-binding-20261007/report.md']
put('dependencies.json',{'bodies':deps,'context':[{'path':p,'sha256':sha(ROOT/p)} for p in context],'policy':'Explicit complete-body reuse, not newly discovered function coverage.'})
print('Normalized',len(fs),'bodies;',sum(f['freshCapture'] for f in fs),'fresh')
