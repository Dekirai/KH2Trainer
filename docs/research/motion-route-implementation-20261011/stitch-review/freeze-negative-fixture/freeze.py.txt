"""Pin exact study members; isolated generated build trees are outside the study."""
from pathlib import Path
import argparse, hashlib, json
H=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def files():return [p for p in sorted(H.rglob('*'))if p.is_file()and p!=H/'manifest.json'and not any(x in ('bin','obj','__pycache__')for x in p.relative_to(H).parts)]
doc=dict(schema=1,scope='Exact research members; generated bin/obj/__pycache__ excluded. No product/package files changed by this study.',files=[dict(path=p.relative_to(H).as_posix(),length=p.stat().st_size,sha256=sha(p))for p in files()])
ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args()
if a.check:assert json.loads((H/'manifest.json').read_bytes())==doc
else:(H/'manifest.json').write_text(json.dumps(doc,indent=2)+'\n')
print(json.dumps(dict(status='PASS',members=len(doc['files']),manifestSha256=sha(H/'manifest.json'))))
