from pathlib import Path
import json,hashlib
H=Path(__file__).resolve().parent;R=H.parents[1]
targets={int(x['fn']['addr'],16) for group in json.loads((H/'xrefs.json').read_text())['result'] for x in group['data'] if x.get('fn')}
targets.update([0x1403d9fe0,0x1403da250,0x14041b400])
prior={a:[] for a in targets}
pins=[]
for p in sorted((R/'docs/research').glob('*/evidence.json')):
 d=json.loads(p.read_text(encoding='utf-8-sig'));rows=d.get('functions',[])
 if not isinstance(rows,list):continue
 pins.append({'path':p.relative_to(R).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 for f in rows:
  if not isinstance(f,dict):continue
  a=f.get('addr')
  try:n=int(a,16)
  except:continue
  if n in prior:prior[n].append(p.parent.name)
out={'method':'Exact numeric addr membership of direct docs/research/*/evidence.json functions arrays. Absence is only absence from this set.','priorEvidence':pins,'targets':[{'addr':hex(a),'prior':v} for a,v in sorted(prior.items())]}
(H/'prior-inventory.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out['targets'],indent=2))
for name in ['actor-scale-writers-20261007/search-evidence.json','actor-scale-writers-20261007/additional-search-evidence.json','actor-scale-contract-20261007/displacement-search.json']:
 d=json.loads((R/'docs/research'/name).read_text(encoding='utf-8-sig'))
 print(name, list(d.keys()) if isinstance(d,dict) else 'list '+str(len(d)))
