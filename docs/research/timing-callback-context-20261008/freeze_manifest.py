"""Hash this study's concrete evidence; does not write outside this directory."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
files=[]
for p in sorted(HERE.iterdir()):
    if p.is_file() and p.name!='manifest.json':
        b=p.read_bytes();files.append({'file':p.name,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
receipt=json.loads((HERE/'verification.json').read_text())
manifest={'schemaVersion':1,'date':'2026-10-08','frozen':True,'staticOnly':True,'originalSha256':receipt['originalSha256'],'scope':'32 fresh full primary bodies, 9 source-hash-pinned reused App bodies and 8-instruction shared callback tail; bounded immediate callback closure.','counts':{k:receipt[k] for k in ['functions','freshFunctions','reusedFunctions','allInstructions','allCodeBytes','machineInstructionBytes','embeddedDataBytes','dataSpans','originalDataBytes','incomingReferences','claims','claimReferences']},'files':files}
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
for name in ['manifest.json','report.json','evidence.json','verification.json']:
    print(name+' '+hashlib.sha256((HERE/name).read_bytes()).hexdigest())
