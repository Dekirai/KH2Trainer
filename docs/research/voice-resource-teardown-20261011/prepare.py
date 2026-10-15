"""Authoring helper: extract selected prior bodies; no product or IDB mutation."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'src/KH2Trainer.Core').is_dir())
def load(p):return json.loads(p.read_bytes())
def dump(p,j):p.write_text(json.dumps(j,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
groups={
 'voice-origin-resources-20261011':'3a6a10 12e460 12d8e0 129d30 1de5c0 1dfd70 1363b0 13c470 13b2e0 1de230',
 'voice-request-lifecycle-20261008':'4069c0 3cd8e0 1de500 1de320',
 'actor-lifetime-20261007':'3b3d60 3bfb70',
}
bodies=[];pins=[]
for study,addrs in groups.items():
 p=ROOT/'docs/research'/study/'evidence.json';j=load(p)
 pins.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)))
 for rva in addrs.split():
  a='0x140'+rva;f=next(x for x in j['functions'] if x.get('addr')==a)
  if 'idaBytes' in f:b=bytes(int(s,16) for s in f['idaBytes'].split())
  else:b=b''.join(bytes(int(s,16) for s in x['data'].split()) for x in f['original_bytes'])
  rows=f.get('disassembly',{}).get('asm',f.get('asm',{})).get('lines')
  assert rows and len(b)==f['size']
  assembly=f.get('disassembly') or {k:f[k] for k in ['addr','asm','instruction_count','total_instructions','cursor']}
  bodies.append(dict(addr=a,size=f['size'],originalBytes=b.hex(' '),sha256=hashlib.sha256(b).hexdigest(),asm=rows,source=p.relative_to(ROOT).as_posix(),freshCapture=False,disassembly=assembly,pages=f['pages'],pseudocode=f['pseudocode'],sourceMetadata=dict(evidenceFile=p.relative_to(ROOT).as_posix(),evidenceSha256=sha(p),document={k:j[k] for k in ['Domain','domain','imageBase','originalSha256'] if k in j})))
dump(HERE/'dependencies.json',dict(functions=bodies))
for study in groups:
 for name in (['report.json'] if study=='actor-lifetime-20261007' else ['report.json','manifest.json']):
  p=ROOT/'docs/research'/study/name;pins.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)))
for rel in ['docs/research/audio-bank-retirement-20261011/manifest.json','docs/research/audio-bank-retirement-20261011/report.json','docs/research/actor-free-closure-20261008/report.json','docs/research/drive-preconstructor-20261007/report.json','docs/research/actor-bulk-lifetime-20261008/report.json']:
 p=ROOT/rel;pins.append(dict(path=rel,sha256=sha(p)))
dump(HERE/'provenance.json',dict(originalSha256='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed',dependencies=pins,captureMethod='Read-only IDA MCP disasm/decompile/get_bytes; all cursors completed. Existing worker adopted without autoanalysis; no IDB mutation. Prior bodies explicitly extracted and pinned, not counted as fresh.',novelty='19 fresh capture operations; five functions already present in prior evidence (12EF30,12E100,39D400,39E690,3A6120). Remaining14 absent from the inspected prior evidence.json function lists; this is no global novelty claim. Callgraph output is discovery only because it labels some branches as calls.'))
print('prepared',len(bodies),'reused bodies',len(pins),'pins')
