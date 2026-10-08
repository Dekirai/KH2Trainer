"""Read-only source/manifest/original-PE and transfer verifier.
The compiled catalog probe is separately reproducible with run-probe.ps1 -Check.
"""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'Directory.Build.props').is_file() and (p/'src/KH2Trainer.Core').is_dir())
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def require(condition,message):
 if not condition:raise AssertionError(message)
def verify_manifest(folder,doc,exact=False):
 entries=doc['files'].items() if isinstance(doc['files'],dict) else ((item['file'],item) for item in doc['files'])
 for rel,item in entries:
  p=folder/rel;require(p.is_file(),str(p)+' missing')
  expected=item['sha256'] if isinstance(item,dict) else item
  require(sha(p)==expected,str(p)+' hash mismatch')
  if isinstance(item,dict) and 'bytes' in item:require(p.stat().st_size==item['bytes'],str(p)+' size mismatch')
 if exact:
  observed={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file() and p.name!='manifest.json'}
  require(observed==set(doc['files']),'study manifest inventory mismatch')
  require(not any(p.name in ['bin','obj','artifacts','__pycache__'] for p in folder.rglob('*') if p.is_dir()),'build/cache directory in study')
def derive(check_manifest=True):
 if check_manifest:verify_manifest(HERE,load(HERE/'manifest.json'),exact=True)
 info=load(HERE/'implementation.json')
 for rel,expected in info['sourceHashes'].items():require(sha(ROOT/rel)==expected,'source changed: '+rel)
 for rel,item in info['sourceSnapshots'].items():
  require(sha(HERE/item['copy'])==item['sha256']==sha(ROOT/rel),'source snapshot mismatch: '+rel)
 for rel,item in info['upstreamManifests'].items():
  p=ROOT/rel;require(sha(p)==item['sha256'],'upstream manifest changed: '+rel)
  doc=load(p);require(len(doc['files'])==item['files'],'upstream count: '+rel);verify_manifest(p.parent,doc)
 for script in ['build_catalog.py','check_catalog.py']:
  process=subprocess.run([sys.executable,'-B',str(HERE/script),'--check'],cwd=ROOT,capture_output=True,text=True)
  require(process.returncode==0,script+' failed: '+process.stdout+process.stderr)
 product=ROOT/'src/KH2Trainer.Core/Data/BdxNativeCalls.json'
 probe=load(HERE/'compiled-probe.json');metadata=load(HERE/'metadata-checks.json');ui=load(HERE/'ui-bdx-report.json')
 require(probe['success'] and probe['checks']==13884 and probe['descriptorRows']==1063 and probe['annotatedRows']==158 and probe['nullRows']==15,'compiled probe counts')
 require(probe['resourceSha256']==sha(product) and probe==info['compiledProbe'],'compiled product resource identity')
 require(metadata['success'] and metadata['descriptors']==1063 and metadata['annotations']==158 and metadata['unchangedOldAnnotatedRows']==104,'metadata totals')
 require(ui==info['ui'] and ui['success'] and ui['checks']==94 and ui['renders']==8 and ui['bindingErrors']==ui['windowCount']==0,'UI receipt')
 require(len(ui['renderFiles'])==8 and all((HERE/f).read_bytes().startswith(b'\x89PNG\r\n\x1a\n') for f in ui['renderFiles']),'stored UI PNGs')
 core=(HERE/'core-tests.txt').read_text(encoding='utf-8-sig');require('3287 passed, 0 failed.' in core,'Core test receipt')
 review=load(HERE/'independent-review.json');require(review['status']=='ACCEPTED_OFFLINE_CATALOG_INTEGRATION' and not review['blockers'],'review acceptance')
 require(review['productSha256']==sha(product) and review['compiledProbe']==probe,'review resource/probe identity')
 refresh=load(HERE/'reference-refresh-review.json')
 require(refresh['status']=='ACCEPTED_REFERENCE_REFRESH' and refresh['productSha256']==sha(product),'reference refresh resource')
 require(refresh['newTimerManifest']==info['upstreamManifests']['docs/research/timer-message74-handlers-20261008/manifest.json']['sha256'],'reference refresh Timer pin')
 require(refresh['sourceRepairReceiptSha256']==sha(HERE/'timer-reference-repair.json') and refresh['bodyCopiesExactlyEqual']==3,'reference repair receipt')
 for name,item in info['supportingReviews'].items():
  require(sha(HERE/name)==item['sha256'],'supporting review changed: '+name)
 require(info['noGameActions'] is True,'execution scope')
 return {'success':True,'sourceFiles':len(info['sourceHashes']),'sourceSnapshots':len(info['sourceSnapshots']),'upstreamManifests':len(info['upstreamManifests']),'originalDescriptorRows':1063,'originalRegistrySlots':11,'nullHoles':15,'annotations':158,'addedDescriptors':913,'addedAnnotations':54,'unchangedOldAnnotatedRows':104,'unchangedImplementationFiles':58,'compiledProbeChecks':13884,'coreChecks':3287,'uiChecks':94,'uiRenders':8,'scope':'Read-only original-PE/builder/transfer/source/manifest checks. Stored compiled/Core/UI receipts are checked; run-probe.ps1 -Check independently rebuilds the compiled catalog probe. No game, native instruction or script execution.'}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');ap.parse_args()
 result=derive();require(load(HERE/'verification.json')==result,'stored verification receipt differs')
 print(json.dumps(dict(result,manifestFiles=len(load(HERE/'manifest.json')['files'])),indent=2))
