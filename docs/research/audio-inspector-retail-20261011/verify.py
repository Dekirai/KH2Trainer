import hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent
R=next(p for p in D.parents if (p/'Directory.Build.props').is_file())
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=load(D/'manifest.json');checks=0
for rel,pin in m['files'].items():
 p=D/rel
 assert p.resolve().is_relative_to(D.resolve()),rel
 assert sha(p)==pin['sha256'] and p.stat().st_size==pin['bytes'],rel
 checks+=1
d=load(D/'review.json')
assert d['status']=='PASS_BOUNDED_INSPECTOR_RETAIL_COMPARISON'
assert (d['checks'],d['scdReads'],d['originReads'])==(6005,26,6)
assert (d['fuzz']['Seed'],d['fuzz']['Cases'],d['fuzz']['Checks'])==(20261011,4096,32768)
assert sum(d['fuzz']['Outcomes'].values())==4096
assert len(d['samples'])==32
assert sha(R/'docs/research/audio-retail-witness-20261011/witness.json')==d['comparedWithFrozenWitnessSha256']
for path,pin in d['sourcePins'].items():assert sha(R/path)==pin,path
print(json.dumps(dict(status='PASS',manifestFiles=checks,currentSourcePins=len(d['sourcePins']),retailChecks=d['checks'],syntheticCases=d['fuzz']['Cases'],gameAccess=False)))
