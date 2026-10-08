"""Read-only manifest/source/original-PE integration verifier.
--check compares all recorded receipts without regenerating them. The optional
compiled probe is run separately by run-probe.ps1 and writes only outside here.
"""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'Directory.Build.props').is_file() and (p/'src/KH2Trainer.Core').is_dir())
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def require(condition,message):
 if not condition:raise AssertionError(message)
def verify_manifest(folder,document,exact=False):
 for rel,item in document['files'].items():
  path=folder/rel
  require(path.is_file(),str(path)+' missing')
  require(path.stat().st_size==item['bytes'] and sha(path)==item['sha256'],str(path)+' manifest mismatch')
 if exact:
  present={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file() and p.name!='manifest.json'}
  require(present==set(document['files']),'study manifest inventory mismatch')
  require(not any(p.name in ['bin','obj','__pycache__','artifacts'] for p in folder.rglob('*') if p.is_dir()),'build/cache directory in frozen study')
def derive():
 manifest=load(HERE/'manifest.json');verify_manifest(HERE,manifest,exact=True)
 implementation=load(HERE/'implementation.json')
 for rel,expected in implementation['sourceHashes'].items():require(sha(ROOT/rel)==expected,'source changed: '+rel)
 for rel,item in implementation['upstreamManifests'].items():
  path=ROOT/rel;require(sha(path)==item['sha256'],'upstream manifest changed: '+rel)
  upstream=load(path);require(len(upstream['files'])==item['files'],'upstream inventory count: '+rel);verify_manifest(path.parent,upstream)
 for script in ['build_catalog.py','check_catalog.py']:
  completed=subprocess.run([sys.executable,'-B',str(HERE/script),'--check'],cwd=ROOT,text=True,capture_output=True)
  require(completed.returncode==0,script+' failed: '+completed.stdout+completed.stderr)
 product=ROOT/'src/KH2Trainer.Core/Data/BdxNativeCalls.json'
 probe=load(HERE/'compiled-probe.json');ui=load(HERE/'ui-bdx-report.json');metadata=load(HERE/'metadata-checks.json')
 require(probe['success'] and probe['checks']==1692 and probe['existingCatalogChecks']==35,'compiled probe count')
 require(probe['resourceSha256']==sha(product),'compiled probe uses a different resource')
 require(probe==implementation['compiledProbe'],'implementation probe identity')
 require(ui['success'] and ui['checks']==79 and ui['renders']==6 and ui['bindingErrors']==ui['windowCount']==0,'UI receipt')
 require(ui==implementation['ui'],'implementation UI identity')
 require(len(ui['renderFiles'])==6 and all((HERE/f).read_bytes().startswith(b'\x89PNG\r\n\x1a\n') for f in ui['renderFiles']),'six stored UI PNGs')
 require(metadata['descriptors']==150 and metadata['annotated']==104 and metadata['oldAnnotatedRows']==44,'metadata counts')
 require(implementation['noGameActions'] is True,'scope')
 review=load(HERE/'independent-review.json');addendum=load(HERE/'review-addendum.json')
 require(review['status']=='ACCEPTED_OFFLINE_CATALOG_INTEGRATION' and not review['blockers'],'independent review status')
 require(addendum['status']=='ACCEPTED_REFERENCE_REFRESH','reference refresh')
 require(addendum['reviewedProductSha256']==sha(product)==review['sourceHashes']['src/KH2Trainer.Core/Data/BdxNativeCalls.json'],'review product identity')
 return {'success':True,'manifestFiles':len(manifest['files']),'sourceFiles':len(implementation['sourceHashes']),'upstreamManifests':len(implementation['upstreamManifests']),'originalDescriptorRows':150,'originalRegistrySlots':11,'annotations':104,'newAnnotations':60,'compiledProbeChecks':1692,'uiChecks':79,'uiRenders':6,'scope':'Read-only source/manifest/builder/original-PE metadata/text verification. Compiled and UI receipts are checked; run-probe.ps1 -Check separately recompiles the1692-check probe. No game or script execution.'}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
 result=derive()
 # The stored result intentionally omits manifestFiles to avoid recursive count coupling.
 comparison={k:v for k,v in result.items() if k!='manifestFiles'}
 require(load(HERE/'verification.json')==comparison,'stored verification receipt differs')
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
