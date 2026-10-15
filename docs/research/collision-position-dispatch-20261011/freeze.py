"""Freeze exact recursive own-folder membership, excluding this root manifest."""
from pathlib import Path
import hashlib,json
H=Path(__file__).resolve().parent
files=[]
for p in sorted(H.rglob('*')):
    if not p.is_file() or p==H/'manifest.json':continue
    b=p.read_bytes()
    files.append(dict(path=p.relative_to(H).as_posix(),length=len(b),sha256=hashlib.sha256(b).hexdigest()))
out=dict(schema=1,status='frozen-for-independent-review',scope='Selected ATTACK_OBJ contact dispatch and original descriptor callbacks; no live-placement or full-ownership approval.',files=files)
(H/'manifest.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(len(files),'members; manifest SHA256',hashlib.sha256((H/'manifest.json').read_bytes()).hexdigest())
