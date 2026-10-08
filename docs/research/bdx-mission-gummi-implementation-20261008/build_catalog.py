"""Add reviewed behavioral metadata; preserve every original numeric descriptor."""
import argparse, hashlib, importlib.util, json, struct
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
enc=lambda x:(json.dumps(x,indent=2,ensure_ascii=False)+'\n').encode()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def verify_manifest(p):
 d=load(p)
 items=d['files'].items() if isinstance(d['files'],dict) else ((r.get('file',r.get('path')),r) for r in d['files'])
 count=0
 for rel,row in items:
  f=p.parent/rel;digest=row if isinstance(row,str) else row['sha256']
  assert sha(f)==digest,(p,rel)
  if isinstance(row,dict) and 'bytes' in row:assert f.stat().st_size==row['bytes']
  count+=1
 return dict(sha256=sha(p),files=count)

def derive():
 baseline=HERE.parent/'bdx-bank-inventory-implementation-20261008/catalog-data.json'
 data=load(baseline);rows={(r['bank'],r['index']):dict(r) for r in data['descriptors']}
 original={k:dict(v) for k,v in rows.items()};sources=[baseline];manifests={};changes=[]
 studies=['bdx-bank3-calls-20261008','bdx-bank4-calls-20261008','actor-query-collision-20261008']
 for study in studies+['timer-audience-operation-20261008']:
  p=HERE.parent/study/'manifest.json';manifests[p.relative_to(ROOT).as_posix()]=verify_manifest(p)
 for study in studies:
  p=HERE.parent/study/'annotations.json';sources.append(p)
  for key,a in load(p)['annotations'].items():
   bank,index=map(int,key.split(':'));r=rows[bank,index]
   assert (bank,index)==(1,367) or not r['name'],('unexpected replacement',key)
   if 'handlerRva' in a:assert a['handlerRva']==r['handlerRva'],key
   if 'bank' in a:assert (a['bank'],a['index'])==(bank,index)
   assert a['declaredOperandCount']==(r['flags']&65535) and a['hasReturnSlot']==bool(r['flags']&0x40000000),key
   for field in ['name','summary','notes','evidence']:r[field]=a[field]
   changes.append(dict(bank=bank,index=index,kind='expanded' if original[bank,index]['name'] else 'new',source=p.relative_to(ROOT).as_posix()))
 # Keep this descriptor's polymorphic meaning. Only the resolved BTLNPC branch
 # acquires a Voice description; the name and adapter contract remain generic.
 r=rows[1,262]
 r['notes']='The actual virtual target depends on the Actor descriptor. For the selected BTLNPC descriptor, the target requests a Voice ID with a signed priority; the audience script supplies ID 8 and priority 3. Equal priority replaces, while a fully idle request accepts any priority. This is a deferred request, not guaranteed playback. The original N_EX650_BTL10 row has flags+72 bit0 set: the captured resource/binding path supplies no Voice component; if Actor+2996 remains NULL at the call, it returns without action. Runtime row selection, later writers, pointer validity and lifetime remain prerequisites.'
 r['evidence']+='; timer-audience-operation-20261008/evidence.json; timer-audience-operation-20261008/retail-witnesses.json; timer-audience-operation-20261008/report.txt'
 changes.append(dict(bank=1,index=262,kind='expanded',source='docs/research/timer-audience-operation-20261008/report.txt'))
 data['descriptors']=[rows[k] for k in sorted(rows)]
 pe_source=HERE.parent/'bdx-trap-registry-20261008/verify.py';sources.append(pe_source)
 spec=importlib.util.spec_from_file_location('mission_gummi_original_pe',pe_source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);pe=m.PE(m.TARGET)
 banks={b['bank']:b for b in data['banks']}
 for k,r in rows.items():
  assert all(r[f]==original[k][f] for f in ['bank','index','descriptorRva','handlerRva','flags']),k
  assert r['descriptorRva']==banks[k[0]]['tableRva']+16*k[1]
  b,z=pe.read(pe.base+r['descriptorRva'],16);assert not z
  assert struct.unpack('<QII',b)==(pe.base+r['handlerRva'] if r['handlerRva'] else 0,r['flags'],0),k
 changed={(c['bank'],c['index']) for c in changes}
 assert len(changed)==len(changes)==83 and sum(c['kind']=='new' for c in changes)==81
 assert len(rows)==1063 and sum(bool(r['name']) for r in rows.values())==239
 assert sum(r['handlerRva']==0 for r in rows.values())==15
 assert all(r==original[k] for k,r in rows.items() if k not in changed)
 assert rows[4,21]==original[4,21]
 receipt=dict(success=True,descriptors=1063,annotations=239,nullHoles=15,newAnnotations=81,expandedAnnotations=2,unchangedRows=len(rows)-len(changed),unchangedNumericRows=len(rows),changes=changes,upstreamManifests=manifests,sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sources],scope='Offline descriptive metadata only. No native behavior, game data, BDX bytes or descriptor numbers changed.')
 return data,receipt

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
 data,receipt=derive()
 for p,x in [(HERE/'catalog-data.json',data),(HERE/'metadata-checks.json',receipt),(ROOT/'src/KH2Trainer.Core/Data/BdxNativeCalls.json',data)]:
  if args.check:assert p.read_bytes()==enc(x),p
  else:p.write_bytes(enc(x))
 print(json.dumps({k:v for k,v in receipt.items() if k not in ['changes','sources','upstreamManifests','scope']}))
