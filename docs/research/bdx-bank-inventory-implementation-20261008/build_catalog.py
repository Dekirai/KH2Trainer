"""Merge verified bank records and behavioral notes into the offline catalog.
The frozen v0.12.12 catalog remains intact. --check performs no writes.
"""
import argparse,hashlib,json,struct,importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def enc(x):return (json.dumps(x,indent=2,ensure_ascii=False)+'\n').encode()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
FIELDS=['bank','index','descriptorRva','handlerRva','flags','name','summary','notes','evidence']

def derive():
 base=HERE.parent/'bdx-catalog-expansion-20261008/catalog-data.json';data=load(base);sources=[base]
 rows={(r['bank'],r['index']):dict(r) for r in data['descriptors']}
 for study in ['bdx-bank-other-inventory-20261008','bdx-bank12-inventory-20261008']:
  p=HERE.parent/study/'descriptors.json';sources.append(p)
  for record in load(p)['descriptors']:
   row={k:record[k] for k in FIELDS};key=row['bank'],row['index']
   if key in rows:
    assert all(rows[key][k]==row[k] for k in FIELDS[:5]),('existing numeric descriptor changed',key)
   else:
    row['evidence']=row['evidence'] or study+'/evidence.json';rows[key]=row
 for study in ['bdx-bank9-calls-20261008','timer-message74-handlers-20261008','bdx-actor-query-20261008']:
  p=HERE.parent/study/'annotations.json';sources.append(p)
  for key,annotation in load(p)['annotations'].items():
   bank,index=map(int,key.split(':'));row=rows[bank,index];assert not row['name'],key
   if 'handlerRva' in annotation:assert annotation['handlerRva']==row['handlerRva'],key
   if 'bank' in annotation:assert (annotation['bank'],annotation['index'])==(bank,index),key
   assert annotation['declaredOperandCount']==row['flags']&65535 and annotation['hasReturnSlot']==bool(row['flags']&0x40000000),key
   for field in ['name','summary','notes','evidence']:row[field]=annotation[field]
 extra=HERE/'additional-annotations.json';sources.append(extra)
 for key,annotation in load(extra)['annotations'].items():
  bank,index=map(int,key.split(':'));row=rows[bank,index];assert not row['name'],key
  assert annotation['handlerRva']==row['handlerRva'] and annotation['declaredOperandCount']==row['flags']&65535 and annotation['hasReturnSlot']==bool(row['flags']&0x40000000),key
  for field in ['name','summary','notes','evidence']:row[field]=annotation[field]
 data['descriptors']=[rows[k] for k in sorted(rows)]
 # Independently reconcile every stored numeric record with the pinned PE.
 p=HERE.parent/'bdx-trap-registry-20261008/verify.py';sources.append(p)
 spec=importlib.util.spec_from_file_location('inventory_catalog_original_pe',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);pe=m.PE(m.TARGET)
 banks={b['bank']:b for b in data['banks']};counts={b:0 for b in banks}
 for row in data['descriptors']:
  assert row['descriptorRva']==banks[row['bank']]['tableRva']+16*row['index']
  raw,z=pe.read(pe.base+row['descriptorRva'],16);assert z==0;pointer,flags,pad=struct.unpack('<QII',raw)
  assert (pointer,flags,pad)==(pe.base+row['handlerRva'] if row['handlerRva'] else 0,row['flags'],0),(row['bank'],row['index'])
  assert row['handlerRva'] or not row['name'];counts[row['bank']]+=1
 expected={0:105,1:368,2:98,3:179,4:59,5:35,6:72,7:37,8:9,9:41,10:60}
 assert counts==expected and len(rows)==1063
 for bank,count in counts.items():assert all((bank,index) in rows for index in range(count))
 assert sum(bool(r['name']) for r in rows.values())==158
 assert sum(r['handlerRva']==0 for r in rows.values())==15
 provenance=dict(originalSha256=data['originalSha256'],descriptors=1063,annotations=158,addedDescriptors=913,addedAnnotations=54,nullHandlers=15,bankExtents=counts,sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sources],scope='Observed descriptor clusters for all11 recorded bank slots. Native bounds and complete transitive handler semantics remain unproved; new entries preserve the existing catalog API.')
 return data,provenance

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();data,provenance=derive()
 for p,x in [(HERE/'catalog-data.json',data),(HERE/'catalog-sources.json',provenance),(ROOT/'src/KH2Trainer.Core/Data/BdxNativeCalls.json',data)]:
  if a.check:assert p.read_bytes()==enc(x),p
  else:p.write_bytes(enc(x))
 print(json.dumps({k:v for k,v in provenance.items() if k not in ['sources','scope']}))
