"""Bind current Ghost-Walk patch separately from immutable v0.12.4 audit sources."""
from pathlib import Path
from zipfile import ZipFile
import difflib, hashlib, json
folder=Path(__file__).resolve().parent; root=folder.parents[2]
paths=['src/KH2Trainer.Twitch/Effects/EffectCatalog.cs','src/KH2Trainer.Twitch/Effects/EffectEngine.cs',
       'tests/KH2Trainer.Twitch.Tests/Program.cs','tests/KH2Trainer.Twitch.Tests/GhostOwnershipTests.cs']
archive=root/'artifacts/packages/KH2_Trainer_v0.12.4/Source.zip'
with ZipFile(archive) as z:
    diff=''
    for p in paths:
        before=[line+'\n' for line in z.read(p).decode('utf-8-sig').splitlines()] if p in z.namelist() else []
        after=[line+'\n' for line in (root/p).read_text(encoding='utf-8-sig').splitlines()]
        diff+=''.join(difflib.unified_diff(before,after,fromfile='v0.12.4/'+p,tofile='current/'+p))
(folder/'ghost-host-delta.patch').write_text(diff,encoding='utf-8')
log=folder/'twitch-tests.txt'; text=log.read_text(encoding='utf-8-sig')
assert '1779 passed, 0 failed' in text and not any(x.startswith('FAIL ') for x in text.splitlines())
assert sum(x.startswith('PASS ghost:') for x in text.splitlines())==24
receipt={
 'schemaVersion':1,'date':'2026-10-07','status':'HOST_SOURCE_AND_TESTS_FROZEN',
 'scope':'Current host Ghost Walk follow-up. rewards.json remains the separate v0.12.4 baseline audit.',
 'changes':['Removed raw X/Y/Z and room-reload fallback branches and feature dependencies.',
            'Only native bookmark return can reposition; failure still allows collision cleanup/deferred retry.',
            'Ended activity uses explicit reason first, otherwise the effect detail, including refused return.',
            'No role allowlist, native handler, shared protocol, version, UI or build pipeline edit.'],
 'sources':[{'path':p,'sha256':hashlib.sha256((root/p).read_bytes()).hexdigest()} for p in paths],
 'test':{'command':'dotnet run --project tests/KH2Trainer.Twitch.Tests/KH2Trainer.Twitch.Tests.csproj -c Release -- src/KH2Trainer/Data/features.json',
         'passed':1779,'failed':0,'focusedGhostChecks':24,'log':'twitch-tests.txt','logSha256':hashlib.sha256(log.read_bytes()).hexdigest(),
         'scope':'Fake game/commands and synthetic local service tests only; no live game/Twitch/UI.'},
 'baselineDiff':{'path':'ghost-host-delta.patch','sha256':hashlib.sha256((folder/'ghost-host-delta.patch').read_bytes()).hexdigest()},
 'nativeFollowup':'../player-position-ownership-20261007/report.json (separate Root-owned implementation and native tests)',
 'remainingLimits':['The native bookmark remains shared with manual capture; ActorGeneration does not prove a per-reward bookmark revision.',
                    'The host rejection tests simulate native refusal; they do not execute or independently validate native generation hooks.',
                    'Combat descriptor fix, timed STATUS transaction and lock-on pair compare are research candidates, not part of this patch.'],
 'cases':['normal native return ordering','rejected return with same/different room and present/missing XYZ',
          'rejected return plus deferred collision release','menu before cleanup','transition during return acknowledgement',
          'natural end exposes refusal','explicit stop reason takes precedence']}
(folder/'ghost-fix-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
files=[p for p in folder.iterdir() if p.is_file() and p.name!='manifest.json']
manifest={'status':'FROZEN','date':'2026-10-07','files':[{'path':p.name,'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files)]}
(folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'receiptSha256':hashlib.sha256((folder/'ghost-fix-receipt.json').read_bytes()).hexdigest(),'manifestSha256':hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest(),'sources':receipt['sources']}))
