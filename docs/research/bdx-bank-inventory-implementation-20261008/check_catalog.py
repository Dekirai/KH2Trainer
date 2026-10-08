"""Independent original-PE and exact-transfer review. No target execution.
Default prints a deterministic receipt; --check compares a local stored receipt.
"""
import argparse, collections, hashlib, json, struct, xml.etree.ElementTree as ET
from pathlib import Path
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'Directory.Build.props').is_file() and (p/'src/KH2Trainer.Core').is_dir())
RESEARCH=ROOT/'docs/research'
STUDY=RESEARCH/'bdx-bank-inventory-implementation-20261008'
ORIGINAL=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
SHA='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
BASE=0x140000000
FIELDS=['bank','index','descriptorRva','handlerRva','flags']
TEXT=['name','summary','notes','evidence']
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def derive():
 raw=ORIGINAL.read_bytes();assert hashlib.sha256(raw).hexdigest()==SHA
 peoff=struct.unpack_from('<I',raw,0x3c)[0];assert raw[:2]==b'MZ' and raw[peoff:peoff+4]==b'PE\0\0'
 optional=peoff+24;assert struct.unpack_from('<H',raw,optional)[0]==0x20b
 assert struct.unpack_from('<Q',raw,optional+24)[0]==BASE
 sections=optional+struct.unpack_from('<H',raw,peoff+20)[0]
 nsec=struct.unpack_from('<H',raw,peoff+6)[0]
 def read(rva,n):
  for j in range(nsec):
   off=sections+40*j;vs,va,stored,ptr=struct.unpack_from('<IIII',raw,off+8)
   if va<=rva and rva+n<=va+stored:
    b=raw[ptr+rva-va:ptr+rva-va+n];assert len(b)==n;return b
  raise AssertionError(('not stored PE bytes',hex(rva),n))
 product=ROOT/'src/KH2Trainer.Core/Data/BdxNativeCalls.json'
 baseline=RESEARCH/'bdx-catalog-expansion-20261008/catalog-data.json'
 data=load(product);old=load(baseline)
 assert sha(baseline)=='e7fa9106c0112e3e4f07281536f609dfd0929b8180b34854fae4e69437bc8010'
 assert data['schema']==old['schema']==1 and data['originalSha256']==old['originalSha256']==SHA
 assert data['banks']==old['banks'] and product.read_bytes()==(STUDY/'catalog-data.json').read_bytes()
 banks={b['bank']:b for b in data['banks']}
 rows={(r['bank'],r['index']):r for r in data['descriptors']}
 oldrows={(r['bank'],r['index']):r for r in old['descriptors']}
 assert len(rows)==len(data['descriptors'])==1063 and list(rows)==sorted(rows)
 counts=collections.Counter(b for b,i in rows)
 assert dict(counts)=={0:105,1:368,2:98,3:179,4:59,5:35,6:72,7:37,8:9,9:41,10:60}
 registry=load(RESEARCH/'bdx-trap-registry-20261008/registry-snapshot.json')
 bank_checks=[]
 for b in data['banks']:
  r=next(r for r in registry['entries'] if r['bank']==b['bank'])
  ptr=struct.unpack('<Q',read(int(r['slot'],16)-BASE,8))[0]
  assert ptr==(int(r['originalTable'],16) if r['originalTable'] else 0)
  assert b['state']==(1 if ptr else 2)
  assert b['tableRva']==int(r['originalTable'] or r['installedVariant'],16)-BASE
  assert all((b['bank'],i) in rows for i in range(counts[b['bank']]))
  bank_checks.append({'bank':b['bank'],'slotRva':int(r['slot'],16)-BASE,'originalPointer':ptr,'state':b['state'],'tableRva':b['tableRva']})
 descriptor_checks=[]
 for key,row in rows.items():
  assert set(row)==set(FIELDS+TEXT)
  assert row['descriptorRva']==banks[key[0]]['tableRva']+16*key[1]
  r=read(row['descriptorRva'],16);ptr,flags,pad=struct.unpack('<QII',r)
  assert (ptr,flags,pad)==(BASE+row['handlerRva'] if row['handlerRva'] else 0,row['flags'],0)
  assert not flags&~0x4000ffff
  assert row['handlerRva'] or not row['name']
  descriptor_checks.append({'bank':key[0],'index':key[1],'bytes':r.hex()})
 nulls={f'{b}:{i}' for (b,i),r in rows.items() if not r['handlerRva']}
 assert nulls=={'0:10','0:33','0:34','0:71','0:72','1:16','1:116','1:215','1:216','1:282','4:0','4:1','7:20','7:22','7:23'}
 # Derive the exact structural union independently of the product builder.
 structural=dict(oldrows);sources=[baseline,product,STUDY/'catalog-data.json',STUDY/'catalog-sources.json',STUDY/'build_catalog.py',STUDY/'additional-annotations.json']
 for study,count in [('bdx-bank12-inventory-20261008',466),('bdx-bank-other-inventory-20261008',451)]:
  p=RESEARCH/study/'descriptors.json';source=load(p)['descriptors'];assert len(source)==count;sources.append(p)
  for row in source:
   key=row['bank'],row['index']
   assert all(rows[key][f]==row[f] for f in FIELDS)
   if key in structural:assert all(structural[key][f]==row[f] for f in FIELDS)
   else:structural[key]={f:row[f] for f in FIELDS+TEXT}
 assert set(structural)==set(rows) and len(set(rows)-set(oldrows))==913
 annotation_sources=[('bdx-bank9-calls-20261008',41),('timer-message74-handlers-20261008',4),('bdx-actor-query-20261008',2),('bdx-bank-inventory-implementation-20261008',7)]
 transferred={}
 for study,count in annotation_sources:
  p=RESEARCH/study/('additional-annotations.json' if study=='bdx-bank-inventory-implementation-20261008' else 'annotations.json')
  annotations=load(p)['annotations'];assert len(annotations)==count;sources.append(p)
  for name,a in annotations.items():
   key=tuple(map(int,name.split(':')));r=rows[key]
   assert key not in transferred and not structural[key]['name']
   assert all(r[f]==a[f] for f in TEXT),(name,'text transfer')
   if 'handlerRva' in a:assert r['handlerRva']==a['handlerRva']
   if 'bank' in a:assert (a['bank'],a['index'])==key
   assert r['flags']&0xffff==a['declaredOperandCount'] and bool(r['flags']&0x40000000)==a['hasReturnSlot']
   transferred[key]=study
 assert len(transferred)==54 and sum(bool(r['name']) for r in rows.values())==158
 # All old annotated rows and all numeric metadata remain byte-for-byte equivalent as JSON values.
 assert sum(bool(r['name']) for r in oldrows.values())==104
 for key,r in oldrows.items():
  assert all(rows[key][f]==r[f] for f in FIELDS)
  if key not in transferred:assert rows[key]==r
  else:assert key[0]==9 and not r['name']
 # Every unannotated new row preserves empty semantic fields and the structural source evidence.
 for key,r in rows.items():
  if key in oldrows or key in transferred:continue
  s=structural[key]
  assert r['name']==r['summary']==r['notes']==''
  expected=s['evidence'] or ('bdx-bank12-inventory-20261008/evidence.json' if key[0] in [1,2] else 'bdx-bank-other-inventory-20261008/evidence.json')
  assert r['evidence']==expected
 # Extra descriptions are individually checked against raw code and captured instructions.
 retkeys=[(1,103),(1,122),(1,163),(1,240),(1,246),(2,36)]
 for key in retkeys:
  r=rows[key];assert read(r['handlerRva'],3)==bytes.fromhex('c20000')
  assert r['handlerRva'] and not r['flags']&0x40000000 and r['name']=='Empty native handler'
 bank12_evidence=RESEARCH/'bdx-bank12-inventory-20261008/evidence.json';sources.append(bank12_evidence)
 captured=load(bank12_evidence);cs=Cs(CS_ARCH_X86,CS_MODE_64);decoded={};target_link_bodies=[]
 for f in captured['functions']:
  address=int(f['addr'],16)
  if address-BASE not in [0x431ec0,0x411300,0x3ba720,0x3bfb70]:continue
  code=bytes(int(b,16) for b in f['originalBytes'].split());assert read(address-BASE,len(code))==code
  instructions=list(cs.disasm(code,address));assert sum(i.size for i in instructions)==len(code)
  assert [i.address for i in instructions]==[int(l['addr'],16) for l in f['disassembly']['asm']['lines']]
  decoded.update({i.address-BASE:i for i in instructions});target_link_bodies.append({'addr':hex(address),'bytes':len(code),'instructions':len(instructions)})
 assert len(target_link_bodies)==4
 anchors={0x431ed5:('mov','ecx, dword ptr [rax + 4]'),0x431ee7:('mov','ecx, dword ptr [rax + 4]'),0x431eff:('jmp','0x140411300'),0x41131b:('mov','dword ptr [rdi + 0xd38], eax'),0x411321:('call','0x1403ba720'),0x411328:('je','0x140411341'),0x41132a:('cmp','dword ptr [rbx + 0x4dc], 1'),0x411331:('jne','0x140411341'),0x41133b:('mov','dword ptr [rdi + 0xd40], eax'),0x3ba729:('call','0x1403bfb70'),0x3ba732:('test','dword ptr [rbx + 0x120], 0x10080000'),0x3ba73c:('jne','0x1403ba746')}
 for address,want in anchors.items():assert (decoded[address].mnemonic,decoded[address].op_str)==want
 assert rows[1,157]['handlerRva']==rows[1,219]['handlerRva']==0x42e070
 branch_stubs=[]
 for r in rows.values():
  if r['handlerRva'] in [0x433510,0x433520,0x433830]:
   assert not r['name'] and r['handlerRva'] and r['bank']==4
   branch_stubs.append({'bank':r['bank'],'index':r['index'],'handlerRva':r['handlerRva']})
 assert len(branch_stubs)==3
 # Production implementation unchanged relative to frozen v0.12.12 review.
 baseline_sources=load(RESEARCH/'bdx-catalog-expansion-20261008/implementation.json')['sourceHashes']
 immutable=[p for p in baseline_sources if p.startswith('src/KH2Trainer.Bridge/')]
 immutable+=['src/KH2Trainer.Core/BdxNativeCallCatalog.cs','src/KH2Trainer.Core/BdxInspection.cs','src/KH2Trainer.Core/KH2Trainer.Core.csproj','src/KH2Trainer/ViewModels/AssetScriptViewModel.cs','src/KH2Trainer/Views/AssetExplorerView.xaml','src/KH2Trainer/Views/AssetExplorerView.xaml.cs']
 unchanged={p:sha(ROOT/p) for p in immutable}
 assert all(value==baseline_sources[p] for p,value in unchanged.items())
 project=ET.parse(ROOT/'src/KH2Trainer.Core/KH2Trainer.Core.csproj')
 resources=project.findall('.//EmbeddedResource');assert len(resources)==1
 assert resources[0].attrib=={'Include':r'Data\BdxNativeCalls.json','LogicalName':'KH2Trainer.Core.BdxNativeCalls.json'}
 provenance=load(STUDY/'catalog-sources.json')
 for p in provenance['sources']:assert sha(ROOT/p['path'])==p['sha256']
 manifests={}
 for study in ['bdx-catalog-expansion-20261008','bdx-bank12-inventory-20261008','bdx-bank-other-inventory-20261008','bdx-bank9-calls-20261008','timer-message74-handlers-20261008','bdx-actor-query-20261008']:
  p=RESEARCH/study/'manifest.json';doc=load(p)
  for name,entry in doc['files'].items():
   q=p.parent/name
   expected=entry['sha256'] if isinstance(entry,dict) else entry
   assert sha(q)==expected,(study,name)
  manifests[study]={'sha256':sha(p),'files':len(doc['files'])}
 return {'success':True,'originalSha256':SHA,'descriptors':1063,'annotations':158,'addedDescriptors':913,'addedAnnotations':54,'unchangedOldAnnotatedRows':104,'bankExtents':{str(k):v for k,v in counts.items()},'nullDescriptors':sorted(nulls),'annotationSources':{s:c for s,c in annotation_sources},'descriptorChecks':descriptor_checks,'registryChecks':bank_checks,'nonnullRetOnlyHandlers':[f'{b}:{i}' for b,i in retkeys],'targetLinkBodies':target_link_bodies,'targetLinkAnchors':len(anchors),'branchStubs':branch_stubs,'unchangedProductionSourceHashes':unchanged,'upstreamManifests':manifests,'sourceHashes':{p.relative_to(ROOT).as_posix():sha(p) for p in dict.fromkeys(sources)},'scope':'Original stored descriptors/registry and exact transfer verified independently. Context-table installation and semantic annotation conclusions inherit the frozen source reviews; seven extra texts separately read against Bank1/2 evidence. No target execution, native bounds claim or complete transitive semantics.'}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');options=ap.parse_args();result=derive()
 if options.check:assert load(HERE/'metadata-checks.json')==result,'stored metadata receipt differs'
 print(json.dumps(result,indent=2,ensure_ascii=False))
