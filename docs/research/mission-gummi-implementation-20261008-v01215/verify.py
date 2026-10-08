"""Check frozen integration evidence and the current source snapshot, without game access."""
import argparse,hashlib,json
from pathlib import Path
import build_catalog

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
data,metadata=build_catalog.derive()
for name,value in [('catalog-data.json',data),('metadata-checks.json',metadata)]:
    assert (HERE/name).read_bytes()==build_catalog.enc(value),name
assert (ROOT/'src/KH2Trainer.Core/Data/BdxNativeCalls.json').read_bytes()==build_catalog.enc(data)
implementation=load(HERE/'implementation.json')
assert implementation['success'] and implementation['features']==358 and implementation['annotations']==256
for row in implementation['sourcePins']:
    assert sha(ROOT/row['path'])==row['sha256'],row['path']
for row in implementation['upstreamManifests']:
    assert sha(ROOT/row['path'])==row['sha256'],row['path']
    build_catalog.manifest(ROOT/row['path'])
for name,row in load(HERE/'manifest.json')['files'].items():
    assert sha(HERE/name)==row['sha256'] and (HERE/name).stat().st_size==row['bytes'],name
probe=load(HERE/'compiled-probe.json')
assert probe['success'] and probe['resourceSha256']==sha(HERE/'catalog-data.json') and probe['annotatedRows']==256
ui=load(HERE/'ui-report.json')
assert ui['success'] and ui['windowCount']==0 and ui['bindingErrors']==0 and ui['missionCounters']['checks']==31
assert ui['featurePages']['features']==358
reviews=[load(HERE/name) for name in ['review-voice.json','review-mission.json','review-bank3.json']]
assert all(r.get('success',True) and not r.get('blockers',[]) for r in reviews)
print(json.dumps(dict(success=True,features=358,descriptors=1063,annotations=256,sourceFiles=len(implementation['sourcePins']),compiledCatalogChecks=probe['checks'],missionUiChecks=31,scope='Frozen source/metadata/review evidence. Native execution uses synthetic tests; no live game or full-executable completeness claim.')))
