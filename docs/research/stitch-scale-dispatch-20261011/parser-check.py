"""Read-only transport check with existing coverage-parser helpers."""
from pathlib import Path
import json,hashlib,importlib.util,sys,argparse
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;R=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir())
p=R/'scripts/update-analysis-coverage.py'
s=importlib.util.spec_from_file_location('existing_coverage_parser',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
e=json.loads((H/'evidence.json').read_bytes());r=json.loads((H/'report.json').read_bytes());refs=[x for c in r['claims'] for x in c['Evidence']]
resolved=[m.resolve_reference(H/'report.json',x) for x in refs];assert all(x['status']=='exists' for x in resolved)
compare=m.pe_comparer(m.DEFAULT_BINARY);rows=[]
for f in e['functions']+json.loads((H/'dependencies.json').read_bytes())['functions']:
 ok,addrs,reason=m.body_assembly(f);spans=m.original_spans(f)
 assert ok,(f['addr'],reason)
 assert len(spans)==1 and len(spans[0][1])==f['size'] and all(compare(a,b) for a,b in spans)
 rows.append({'addr':f['addr'],'completeASM':ok,'instructions':len(addrs),'originalBytes':sum(len(b) for a,b in spans)})
j={'status':'PASS','parserSha256':hashlib.sha256(p.read_bytes()).hexdigest(),'referenceCount':len(refs),'allReferencesExist':True,'functions':rows,'limits':'Only original parser helpers called; no parser mutation or coverage generation.'}
a=argparse.ArgumentParser();a.add_argument('--write',action='store_true');args=a.parse_args()
if args.write:(H/'parser-check.json').write_text(json.dumps(j,indent=2)+'\n')
else:assert json.loads((H/'parser-check.json').read_bytes())==j
print(json.dumps({'status':j['status'],'references':len(refs),'bodies':len(rows),'bytes':sum(x['originalBytes'] for x in rows)}))

