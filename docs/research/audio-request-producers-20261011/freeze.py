"""Freeze this artifact study only, after deterministic read-only verification."""
import hashlib, json, subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
subprocess.run(['py','-3','-B',str(HERE/'verify.py'),'--check'],check=True)
files={p.relative_to(HERE).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(HERE.rglob('*')) if p.is_file() and p!=HERE/'manifest.json' and '__pycache__' not in p.parts}
manifest=dict(status='BOUNDED_STATIC_STUDY_PENDING_INDEPENDENT_REVIEW',productChanged=False,files=files)
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(success=True,files=len(files),manifestSha256=sha(HERE/'manifest.json'))))
