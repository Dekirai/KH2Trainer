"""Freeze this study only; no product/build/package/IDA writes."""
import hashlib, json, pathlib, subprocess, sys
HERE=pathlib.Path(__file__).resolve().parent
subprocess.run([sys.executable,'-B',str(HERE/'verify.py'),'--write'],check=True)
files=[{'path':p.relative_to(HERE).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(HERE.rglob('*')) if p.is_file() and p!=HERE/'manifest.json']
manifest={'schema':1,'scope':'Gummi special-weapon scalar request study; own artifacts only','files':files}
data=(json.dumps(manifest,indent=2)+'\n').encode();(HERE/'manifest.json').write_bytes(data)
subprocess.run([sys.executable,'-B',str(HERE/'verify.py')],check=True)
print('Manifest SHA256:',hashlib.sha256(data).hexdigest())
