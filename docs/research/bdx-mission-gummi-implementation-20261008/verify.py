"""Read-only release-study verification. Rebuild the probe separately if desired."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def derive():
 manifest=load(HERE/'manifest.json')['files']
 actual={p.relative_to(HERE).as_posix() for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json'}
 assert actual==set(manifest)
 for name,row in manifest.items():
  p=HERE/name;assert sha(p)==row['sha256'] and p.stat().st_size==row['bytes'],name
 info=load(HERE/'implementation.json')
 for rel,digest in info['sourceHashes'].items():assert sha(ROOT/rel)==digest,rel
 for rel,row in info['sourceSnapshots'].items():assert sha(HERE/row['copy'])==row['sha256']==sha(ROOT/rel),rel
 result=subprocess.run([sys.executable,'-B',str(HERE/'build_catalog.py'),'--check'],cwd=ROOT,capture_output=True,text=True)
 assert result.returncode==0,result.stdout+result.stderr
 probe=load(HERE/'compiled-probe.json');meta=load(HERE/'metadata-checks.json')
 assert probe['success'] and probe['checks']==13884 and probe['descriptorRows']==1063 and probe['annotatedRows']==239 and probe['nullRows']==15
 assert probe['resourceSha256']==sha(ROOT/'src/KH2Trainer.Core/Data/BdxNativeCalls.json')
 assert meta['success'] and meta['newAnnotations']==81 and meta['expandedAnnotations']==2 and meta['unchangedNumericRows']==1063 and meta['unchangedRows']==980
 assert '3287 passed, 0 failed.' in (HERE/'core-tests.txt').read_text(encoding='utf-8-sig')
 ui=load(HERE/'ui-bdx-report.json');assert ui['success'] and ui['checks']==94 and ui['renders']==8 and ui['bindingErrors']==ui['windowCount']==0
 assert all((HERE/f).read_bytes().startswith(b'\x89PNG\r\n\x1a\n') for f in ui['renderFiles'])
 review=load(HERE/'independent-review.json')
 assert review['status']=='ACCEPTED_OFFLINE_CATALOG_INTEGRATION' and not review['blockers']
 assert review['productSha256']==probe['resourceSha256']
 return dict(success=True,descriptors=1063,annotations=239,newAnnotations=81,expandedAnnotations=2,unchangedNumericRows=1063,unchangedRows=980,compiledProbeChecks=13884,coreChecks=3287,uiChecks=94,uiRenders=8,sourcePins=len(info['sourceHashes']),scope='Original-file metadata and frozen source/receipt checks. Probe rebuilding is separately available. No game, original native instructions or script execution.')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');p.parse_args()
 print(json.dumps(derive(),indent=2))
