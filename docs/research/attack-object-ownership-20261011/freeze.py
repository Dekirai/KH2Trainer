import hashlib,json,pathlib
H=pathlib.Path(__file__).resolve().parent
files=sorted(p for p in H.rglob('*') if p.is_file() and p!=H/'manifest.json')
m={'schema':'exact-recursive-study-manifest-v1','status':'frozen-for-independent-review','files':[{'path':p.relative_to(H).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]}
(H/'manifest.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
print(hashlib.sha256((H/'manifest.json').read_bytes()).hexdigest(),len(files))
