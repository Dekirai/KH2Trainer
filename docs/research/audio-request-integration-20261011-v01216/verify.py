"""Verify the frozen v16 integration receipts, sources and reviewed studies."""
import hashlib,json
from pathlib import Path
H=Path(__file__).resolve().parent
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=load(H/'manifest.json')['files']
actual={p.relative_to(H).as_posix() for p in H.rglob('*') if p.is_file() and p!=H/'manifest.json'}
assert actual==set(manifest)
for name,pin in manifest.items():assert sha(H/name)==pin['sha256'] and (H/name).stat().st_size==pin['bytes'],name
info=load(H/'implementation.json');audio=load(H/'review-audio.json');origin=load(H/'review-origin.json')
assert info['success'] and info['version']=='0.12.16' and info['featureCount']==361 and not info['liveGame']
assert audio['status']=='ACCEPTED_BOUNDED_AUDIO_SCALAR_IMPLEMENTATION' and not audio['openBlockers']
assert origin['accepted'] and origin['status']=='ACCEPTED_BOUNDED_STATIC_RESEARCH'
for name,item in info['studies'].items():
 folder=H.parent/name
 assert sha(folder/'manifest.json')==item['manifestSha256'],name
 files=load(folder/'manifest.json')['files']
 assert len(files)==item['files']
 assert {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file() and p!=folder/'manifest.json'}==set(files)
 for relative,pin in files.items():assert sha(folder/relative)==pin['sha256'],relative
for name in info['changedSourceFiles']+info['newSourceFiles']:
 assert sha(H/'source-snapshots'/name)==info['sourcePins'][name],name
 for review in (audio,):
  if name in review['sourcePins']:assert info['sourcePins'][name]==review['sourcePins'][name]
for path,pin in info['reviewEvidence'].items():assert sha(H/pin['snapshot'])==pin['sha256'],path
ui=load(H/'ui-report.json')
assert ui['success'] and ui['bindingErrors']==0 and ui['windowCount']==0 and ui['sourceIsSynthetic']
assert ui['featurePages']['features']==361 and ui['audioRequests']['success'] and ui['audioRequests']['checks']==49
assert len(ui['audioRequests']['renders'])==8
for name,pin in audio['rootUiArtifactPins'].items():assert sha(H/('ui-report.json' if name=='report.json' else name))==pin
assert '3299 passed, 0 failed' in (H/'core-tests.txt').read_text(encoding='utf-8-sig')
assert audio['checks']['independentProductionFixture']==22380 and audio['checks']['actualTrainerFrameCalls']==15
assert audio['checks']['independentManagedFixture']==89
assert load(H/'review-drive.json')['accepted']
print(json.dumps(dict(success=True,files=len(manifest),sourceFiles=len(info['sourcePins']),studies=len(info['studies']),coreChecks=3299,audioUiChecks=49,liveGame=False)))
