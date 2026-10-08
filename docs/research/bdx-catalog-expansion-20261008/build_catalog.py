"""Merge reviewed annotations without modifying the frozen first catalog."""
import argparse, hashlib, json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def encoded(x):return (json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode()
def derive():
 base=HERE.parent/'bdx-trap-catalog-20261008/catalog-data.json';data=load(base)
 rows={(r['bank'],r['index']):r for r in data['descriptors']};sources=[base]
 added=[]
 for study in ['bdx-system-calls-20261008','bdx-object-calls-20261008']:
  p=HERE.parent/study/'annotations.json';sources.append(p);document=load(p);annotations=document.get('annotations',document)
  for key,ann in annotations.items():
   bank,index=map(int,key.split(':'));row=rows[bank,index]
   assert row['handlerRva'] and not row['name'],key
   assert ann['declaredOperandCount']==row['flags']&65535 and ann['hasReturnSlot']==bool(row['flags']&0x40000000),key
   if 'handlerRva' in ann:assert ann['handlerRva']==row['handlerRva']
   for field in ['name','summary','notes','evidence']:row[field]=ann[field]
   added.append(key)
 # The new native constructor/retail Event27 evidence resolves one ABI ambiguity.
 motion=HERE.parent/'motion-event27-20261008/manifest.json';sources.append(motion)
 for index in [9,95]:
  row=rows[2,index]
  row['notes']+=' The native Actor constructor stores its encoded self pointer at Actor+4. An Actor with that self-link intact can itself satisfy the wrapper layout; a separate wrapper allocation is not universally required. The selected Event27 witness uses the same layout in 1:87; it does not prove an Event27 call to 2:9/95.'
  row['evidence']+=' + motion-event27-20261008'
 assert len(added)==60 and len(data['descriptors'])==150
 assert sum(bool(r['name']) for r in data['descriptors'])==104
 assert all(bool(r['name'])==bool(r['handlerRva']) for r in data['descriptors'] if r['bank']==0)
 provenance={'originalSha256':data['originalSha256'],'addedAnnotations':added,'sources':[{'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources],'scope':'All 100 nonnull descriptors in the recorded 105-entry Bank0 extent now have bounded annotations. This is not a complete native bank bound or complete transitive semantic analysis.'}
 return data,provenance
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();data,provenance=derive()
 for p,x in [(HERE/'catalog-data.json',data),(HERE/'catalog-sources.json',provenance),(ROOT/'src/KH2Trainer.Core/Data/BdxNativeCalls.json',data)]:
  b=encoded(x)
  if a.check:assert p.read_bytes()==b,p
  else:p.write_bytes(b)
 print(json.dumps({'success':True,'descriptors':150,'annotations':104,'newAnnotations':60}))
if __name__=='__main__':main()
