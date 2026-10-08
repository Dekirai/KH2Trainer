"""Regenerate only this study's file manifest after deliberate review changes."""
import hashlib,json
from pathlib import Path
here=Path(__file__).resolve().parent
files={p.relative_to(here).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
       for p in sorted(here.rglob('*')) if p.is_file() and p.name!='manifest.json'}
manifest={'schema':1,'originalSha256':'9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed',
 'scope':'Checked mission-counter delta/digit commands and validated read-only combo snapshot; static original-byte evidence and isolated synthetic tests, no game execution.','files':files}
(here/'manifest.json').write_bytes((json.dumps(manifest,indent=2,ensure_ascii=False)+'\n').encode('utf-8'))
