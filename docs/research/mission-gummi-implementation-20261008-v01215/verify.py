"""Check frozen integration evidence and the current source snapshot, without game access."""
import argparse,hashlib,json,re
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
own_files=load(HERE/'manifest.json')['files']
assert set(own_files)=={p.relative_to(HERE).as_posix() for p in HERE.rglob('*') if p.is_file() and p!=HERE/'manifest.json'}
for name,row in own_files.items():
    assert sha(HERE/name)==row['sha256'] and (HERE/name).stat().st_size==row['bytes'],name
probe=load(HERE/'compiled-probe.json')
assert probe['success'] and probe['resourceSha256']==sha(HERE/'catalog-data.json') and probe['annotatedRows']==256
ui=load(HERE/'ui-report.json')
assert ui['success'] and ui['windowCount']==0 and ui['bindingErrors']==0 and ui['missionCounters']['checks']==31
assert ui['featurePages']['features']==358 and ui['featurePages']['success']
assert ui['missionCounters']['success'] and ui['missionCounters']['gameAccess'] is False
core=re.search(r'(\d+) passed, (\d+) failed',(HERE/'core-tests.txt').read_text(encoding='utf-8-sig'))
assert core and int(core[1])==3294 and int(core[2])==0
arithmetic=load(HERE/'arithmetic-review.json')
assert arithmetic['success'] and arithmetic['failures']==0 and arithmetic['cases']==457368 and arithmetic['liveGame'] is False
expected_statuses={
    'review-voice.json':'ACCEPTED_BOUNDED_STATIC_RESEARCH',
    'review-mission.json':'ACCEPTED_BOUNDED_NATIVE_IMPLEMENTATION',
    'review-bank3.json':'ACCEPTED_BOUNDED_STATIC_RESEARCH',
    'review-integration.json':'ACCEPTED_OFFLINE_PRODUCT_INTEGRATION'}
reviews={name:load(HERE/name) for name in expected_statuses}
for name,review in reviews.items():
    assert review['status']==expected_statuses[name] and review['blockers']==[],name
    assert 'success' not in review or review['success'] is True,name
    for path,value in review.get('pins',review.get('sourcePins',review.get('sourceHashes',{}))).items():
        expected=value if isinstance(value,str) else value['sha256']
        if name=='review-bank3.json':target=ROOT/'docs/research/bdx-bank3-extended-20261008'/path
        elif path.startswith('artifacts/'):target=HERE/'review-evidence'/path.replace('/','__')
        else:target=ROOT/path
        assert sha(target)==expected,(name,path)
mission=reviews['review-mission.json']
assert mission['studyManifestSha256']==sha(ROOT/'docs/research/mission-counter-implementation-20261008/manifest.json')
integration=reviews['review-integration.json']
for study,expected in integration['manifestPins'].items():
    assert sha(ROOT/'docs/research'/study/'manifest.json')==expected,study
assert integration['compiledManagedChecks']==3840 and integration['compiledBdxChecks']==13884
print(json.dumps(dict(success=True,features=358,descriptors=1063,annotations=256,sourceFiles=len(implementation['sourcePins']),compiledCatalogChecks=probe['checks'],missionUiChecks=31,scope='Frozen source/metadata/review evidence. Native execution uses synthetic tests; no live game or full-executable completeness claim.')))
