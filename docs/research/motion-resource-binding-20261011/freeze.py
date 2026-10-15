"""Freeze only this study after successful verify.py --write."""
import hashlib,json,pathlib,subprocess,sys
HERE=pathlib.Path(__file__).resolve().parent
subprocess.run([sys.executable,'-B',str(HERE/'verify.py'),'--write'],check=True)
manifest=HERE/'manifest.json'
files=[{'path':p.relative_to(HERE).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
       for p in sorted(HERE.rglob('*')) if p.is_file() and p!=manifest]
manifest.write_text(json.dumps({'schemaVersion':1,'status':'FROZEN_STATIC_STUDY','scope':'Motion binding/cache spans; static evidence and limited implementation proposal; no product change.','files':files},indent=2)+'\n',encoding='utf-8')
subprocess.run([sys.executable,'-B',str(HERE/'verify.py')],check=True)
print('MANIFEST SHA256 '+hashlib.sha256(manifest.read_bytes()).hexdigest())
