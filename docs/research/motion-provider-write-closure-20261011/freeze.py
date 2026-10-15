"""Exact recursive study manifest; excludes only this directory's root manifest."""
import argparse,hashlib,json,pathlib
H=pathlib.Path(__file__).resolve().parent
def make():
 return {'schema':'study-manifest-v1','files':[{'path':p.relative_to(H).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(H.rglob('*')) if p.is_file() and p!=H/'manifest.json']}
ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
m=make();p=H/'manifest.json'
if args.check:assert json.loads(p.read_text(encoding='utf-8'))==m
else:p.write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
print('PASS',len(m['files']),'members',hashlib.sha256(p.read_bytes()).hexdigest())
