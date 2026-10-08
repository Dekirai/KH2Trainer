from pathlib import Path
import argparse,hashlib,json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
p=argparse.ArgumentParser();p.add_argument('--source',action='store_true');args=p.parse_args()
for name,info in load(HERE/'manifest.json')['files'].items():
    f=HERE/name;assert f.stat().st_size==info['bytes'] and sha(f)==info['sha256'],name
d=load(HERE/'implementation.json')
assert d['descriptorCount']==150 and d['annotationCount']==44 and d['bdxUi']['checks']==70
assert not d['gameStarted'] and not d['liveGameTested']
if args.source:
    for path,expected in d['sources'].items():assert sha(ROOT/path)==expected,path
print(json.dumps({'status':'PASS','files':len(load(HERE/'manifest.json')['files']),'sourceChecked':args.source,'bdxUiChecks':70}))
