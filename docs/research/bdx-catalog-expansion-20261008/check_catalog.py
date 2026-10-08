"""Independent metadata review; reads retail PE without executing target code."""
import argparse,hashlib,json,struct,xml.etree.ElementTree as ET
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'Directory.Build.props').is_file() and (p/'src/KH2Trainer.Core').is_dir())
ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');options=ap.parse_args()
ORIGINAL=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
raw=ORIGINAL.read_bytes(); original=hashlib.sha256(raw).hexdigest()
assert original=='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
peoff=struct.unpack_from('<I',raw,0x3c)[0];assert raw[:2]==b'MZ' and raw[peoff:peoff+4]==b'PE\0\0'
nsec=struct.unpack_from('<H',raw,peoff+6)[0];optional=peoff+24;assert struct.unpack_from('<H',raw,optional)[0]==0x20b
base=struct.unpack_from('<Q',raw,optional+24)[0];assert base==0x140000000
sections=optional+struct.unpack_from('<H',raw,peoff+20)[0]
def read(rva,size):
 for n in range(nsec):
  off=sections+n*40;virtual,va,stored,ptr=struct.unpack_from('<IIII',raw,off+8)
  if va<=rva and rva+size<=va+stored:
   data=raw[ptr+rva-va:ptr+rva-va+size];assert len(data)==size;return data
 raise AssertionError(('not stored PE bytes',hex(rva),size))
basepath=ROOT/'docs/research/bdx-trap-catalog-20261008/catalog-data.json'
product=ROOT/'src/KH2Trainer.Core/Data/BdxNativeCalls.json'
expansion=ROOT/'docs/research/bdx-catalog-expansion-20261008'
data=load(product);old=load(basepath);assert data['schema']==old['schema']==1 and data['originalSha256']==old['originalSha256']==original
assert data['banks']==old['banks'] and len(data['descriptors'])==150
assert product.read_bytes()==(expansion/'catalog-data.json').read_bytes()
registry=load(ROOT/'docs/research/bdx-trap-registry-20261008/registry-snapshot.json')
banks={b['bank']:b for b in data['banks']}
registry_checks=[]
for b in data['banks']:
 entry=next(e for e in registry['entries'] if e['bank']==b['bank'])
 actual=struct.unpack('<Q',read(int(entry['slot'],16)-base,8))[0]
 assert actual==(int(entry['originalTable'],16) if entry['originalTable'] else 0)
 assert b['state']==(1 if actual else 2)
 assert b['tableRva']==int(entry['originalTable'] or entry['installedVariant'],16)-base
 registry_checks.append({'bank':b['bank'],'slotRva':int(entry['slot'],16)-base,'originalPointer':actual,'state':b['state']})
rows={(r['bank'],r['index']):r for r in data['descriptors']};oldrows={(r['bank'],r['index']):r for r in old['descriptors']}
assert list(rows)==list(oldrows) and len(rows)==150
checks=[]
for key,row in rows.items():
 assert row['descriptorRva']==banks[row['bank']]['tableRva']+16*row['index']
 content=read(row['descriptorRva'],16);pointer,flags,pad=struct.unpack('<QII',content)
 assert pointer==(base+row['handlerRva'] if row['handlerRva'] else 0) and flags==row['flags']
 for field in ['bank','index','descriptorRva','handlerRva','flags']:assert row[field]==oldrows[key][field]
 checks.append({'bank':key[0],'index':key[1],'descriptorRva':row['descriptorRva'],'bytes':content.hex(),'padding':pad})
assert {i for (b,i),r in rows.items() if b==0 and not r['handlerRva']}=={10,33,34,71,72}
assert sum(bool(r['name']) for r in rows.values())==104
assert all(bool(r['name'])==bool(r['handlerRva']) for (b,i),r in rows.items() if b==0)
added={};sourcecounts={};sources=[basepath,product,expansion/'catalog-data.json',expansion/'catalog-sources.json',expansion/'build_catalog.py']
for study,count in [('bdx-system-calls-20261008',33),('bdx-object-calls-20261008',27)]:
 path=ROOT/'docs/research'/study/'annotations.json';document=load(path);annotations=document.get('annotations',document);assert len(annotations)==count;sources.append(path)
 for key,ann in annotations.items():
  b,i=map(int,key.split(':'));row=rows[b,i];assert not oldrows[b,i]['name'];assert (b,i) not in added
  assert row['flags']&0xffff==ann['declaredOperandCount'] and bool(row['flags']&0x40000000)==ann['hasReturnSlot']
  if 'handlerRva' in ann:assert row['handlerRva']==ann['handlerRva']
  for field in ['name','summary','notes','evidence']:assert row[field]==ann[field],(key,field)
  added[b,i]=study
 sourcecounts[study]=count
assert len(added)==60
oldnotes=' The native Actor constructor stores its encoded self pointer at Actor+4. An Actor with that self-link intact can itself satisfy the wrapper layout; a separate wrapper allocation is not universally required. The selected Event27 witness uses the same layout in 1:87; it does not prove an Event27 call to 2:9/95.'
old_count=0;unchanged=0
for key,row in rows.items():
 if key in added:continue
 before=oldrows[key]
 if before['name']:old_count+=1
 if key in [(2,9),(2,95)]:
  assert row==dict(before,notes=before['notes']+oldnotes,evidence=before['evidence']+' + motion-event27-20261008')
 else:assert row==before;unchanged+=1
assert old_count==44
provenance=load(expansion/'catalog-sources.json');assert set(provenance['addedAnnotations'])=={f'{b}:{i}' for b,i in added}
for p in provenance['sources']:assert sha(ROOT/p['path'])==p['sha256'],p['path']
# The independent review checked archive/base identity. Reproduction pins the
# frozen base directly, so no previous release archive is needed at runtime.
assert sha(basepath)=='4dbaa172a91195c6b3c98253ab3cfa6e1e37e5c74ab00d38ef48789e633a22a3'
project=ET.parse(ROOT/'src/KH2Trainer.Core/KH2Trainer.Core.csproj')
resources=project.findall('.//EmbeddedResource');assert len(resources)==1
assert resources[0].attrib=={'Include':r'Data\BdxNativeCalls.json','LogicalName':'KH2Trainer.Core.BdxNativeCalls.json'}
for rel in ['src/KH2Trainer.Core/BdxNativeCallCatalog.cs','src/KH2Trainer.Core/BdxInspection.cs','src/KH2Trainer.Core/KH2Trainer.Core.csproj','src/KH2Trainer/ViewModels/AssetScriptViewModel.cs','src/KH2Trainer/Views/AssetExplorerView.xaml','tests/KH2Trainer.Core.Tests/BdxNativeCallCatalogTests.cs','tests/KH2Trainer.UiTests/BdxInspectionUiChecks.cs','docs/research/motion-event27-20261008/manifest.json']:
 sources.append(ROOT/rel)
result={'success':True,'originalSha256':original,'descriptors':len(checks),'annotated':104,'newAnnotations':sourcecounts,'oldAnnotatedRows':old_count,'unchangedRowsExcludingAddedAndRebindNotes':unchanged,'permittedOldTextChanges':['2:9 notes/evidence','2:95 notes/evidence'],'originalRegistryChecks':registry_checks,'descriptorChecks':checks,'sourceHashes':{p.relative_to(ROOT).as_posix():sha(p) for p in sources},'scope':'Original PE descriptor pointers/flags/RVAs and original bank slots verified; context-installed table identities inherited from reviewed registry evidence. All annotation strings compared exactly with reviewed source texts. This is an offline data/API integration review, not script execution or complete semantic reanalysis.'}
if options.check:
 assert load(HERE/'metadata-checks.json')==result,'stored metadata receipt differs'
else:(HERE/'metadata-checks.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ['descriptorChecks','originalRegistryChecks','sourceHashes']},indent=2))
