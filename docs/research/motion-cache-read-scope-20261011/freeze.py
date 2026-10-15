import argparse,hashlib,json,pathlib
H=pathlib.Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
files=[{'path':x.relative_to(H).as_posix(),'bytes':x.stat().st_size,'sha256':hashlib.sha256(x.read_bytes()).hexdigest()} for x in sorted(H.rglob('*')) if x.is_file() and x!=H/'manifest.json']
m={'schema':'exact-recursive-study-manifest-v1','files':files}
if a.check:assert json.loads((H/'manifest.json').read_text(encoding='utf-8'))==m,'Manifest mismatch'
else:(H/'manifest.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
print('PASS',len(files),'members; manifest',hashlib.sha256((H/'manifest.json').read_bytes()).hexdigest())
