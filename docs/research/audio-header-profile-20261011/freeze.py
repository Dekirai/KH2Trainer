"""Author-only manifest creation; verification never refreezes."""
from pathlib import Path
import json,hashlib
H=Path(__file__).resolve().parent
files={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(H.iterdir()) if p.is_file() and p.name!='manifest.json'}
(H/'manifest.json').write_text(json.dumps({'schema':1,'scope':'Bounded static SCD header profile study, independent peer review pending; no product changes.','files':files},indent=2)+'\n')
print(hashlib.sha256((H/'manifest.json').read_bytes()).hexdigest())
