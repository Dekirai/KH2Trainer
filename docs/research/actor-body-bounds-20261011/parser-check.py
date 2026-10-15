"""Check evidence transport using the unchanged coverage parser, without regenerating it."""
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent
R=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir())
p=R/'scripts/update-analysis-coverage.py'
s=importlib.util.spec_from_file_location('existing_coverage_parser',p)
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
e=json.loads((H/'evidence.json').read_bytes()); claims=json.loads((H/'claims.json').read_bytes())['claims']
refs=[ref for c in claims for ref in c['Evidence']]
assert all(m.resolve_reference(H/'claims.json',ref)['status']=='exists' for ref in refs)
compare=m.pe_comparer(m.DEFAULT_BINARY); rows=[]
for f in e['functions']:
    ok,addrs,reason=m.body_assembly(f); spans=m.original_spans(f)
    assert ok,(f['addr'],reason)
    assert len(spans)==1 and len(spans[0][1])==f['size'] and all(compare(a,b) for a,b in spans)
    rows.append({'addr':f['addr'],'completeASM':ok,'instructions':len(addrs),'originalBytes':sum(len(b) for a,b in spans)})
out={'status':'PASS','parserSha256':hashlib.sha256(p.read_bytes()).hexdigest(),'referenceCount':len(refs),'allReferencesExist':True,'functions':rows,'limits':'Existing parser helpers only; no parser mutation, global coverage generation or semantic completeness claim.'}
ap=argparse.ArgumentParser(); ap.add_argument('--write',action='store_true'); args=ap.parse_args()
if args.write: (H/'parser-check.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
else: assert json.loads((H/'parser-check.json').read_bytes())==out
print(json.dumps({'status':'PASS','references':len(refs),'bodies':len(rows)}))
