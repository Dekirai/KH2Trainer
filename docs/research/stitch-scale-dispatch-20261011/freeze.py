"""Author-only manifest. Verification never refreezes."""
from pathlib import Path
import json,hashlib
H=Path(__file__).resolve().parent
members={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(H.iterdir()) if p.is_file() and p.name!='manifest.json'}
(H/'manifest.json').write_text(json.dumps({'schema':1,'scope':'Bounded Stitch scalar reset dispatch and callback lifecycle. Independent review pending; no product change.','files':members},indent=2)+'\n',encoding='utf-8')
print(hashlib.sha256((H/'manifest.json').read_bytes()).hexdigest())
