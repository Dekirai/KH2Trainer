"""Original coverage helper compatibility, source pins and portable roots."""
from pathlib import Path
import json,hashlib,importlib.util,sys,argparse
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;R=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir())
def load(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run():
 path=R/'scripts/update-analysis-coverage.py';spec=importlib.util.spec_from_file_location('existing_coverage',path);p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
 report=load(H/'report.json');e=load(H/'evidence.json');refs=[r for c in report['claims'] for r in c['Evidence']]
 assert all(p.address(c.get('addr')) is not None and isinstance(c.get('Finding'),str) and c['Finding'].strip() and isinstance(c.get('Limitations'),str) and c['Limitations'].strip() for c in report['claims'])
 results=[p.resolve_reference(H/'report.json',r) for r in refs];assert all(x['status']=='exists' for x in results)
 rows=[];compare=p.pe_comparer(p.DEFAULT_BINARY)
 for f in e['functions']+e['dependencies']:
  ok,a,why=p.body_assembly(f);spans=p.original_spans(f)
  assert ok and a and spans and all(compare(a,b) for a,b in spans),(f['addr'],why)
  rows.append({'addr':f['addr'],'bytes':sum(len(b) for a,b in spans),'completeAssembly':ok})
 inventory=load(H/'priorwork-inventory.json')
 for item in inventory['sources']:
  source=R/item['path'];assert sha(source)==item['sha256'];addresses={f.get('addr') for f in load(source).get('functions',[])}
  assert sorted(addresses&set(inventory['freshCapturedAddresses']))==item['matchingFunctionAddresses']
 ns={'__name__':'portable_probe','__file__':str(R/'docs/research/audio-header-profile-20261011/verify.py')}
 exec(compile((H/'verify.py').read_text(encoding='utf-8'),'portable-probe','exec'),ns);assert ns['ROOT']==R
 return {'status':'PASS','parserSha256':sha(path),'canonicalClaimRows':len(report['claims']),'resolvedReferences':len(refs),'completeOriginalBodies':rows,'priorSourcesChecked':len(inventory['sources']),'portableRoot':True,'limitations':'Unchanged existing parser reused for compatibility only; no coverage regeneration, docs change or independent-review claim.'}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--write',action='store_true');a=ap.parse_args();j=run()
 if a.write:(H/'integration-check.json').write_text(json.dumps(j,indent=2)+'\n')
 else:assert load(H/'integration-check.json')==j
 print(json.dumps(j))
