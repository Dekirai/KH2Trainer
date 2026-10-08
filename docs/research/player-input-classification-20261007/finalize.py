"""Reproducible local receipt; never changes product files or prior reports."""
from pathlib import Path
import hashlib,json,difflib
p=Path(__file__).resolve().parent;root=p.parents[2]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
files=['src/KH2Trainer.Bridge/GameplayStateSupport.inl',
       'tests/KH2Trainer.Bridge.Tests/GameplayStateGuardTests.cpp',
       'tests/KH2Trainer.Bridge.Tests/CombatGuardTests.cpp',
       'tests/KH2Trainer.Bridge.Tests/PlayerHealthGuardTests.cpp']
v=json.loads((p/'verification.json').read_text())
assert v['passed'] and v['functions']==68 and v['instructions']==3045 and v['runtimePins']==41
logs=[('gameplay-tests.txt',399,'GameplayStateGuardTests'),
      ('native-CombatGuardTests.txt',1870,'CombatGuardTests'),
      ('native-PlayerHealthGuardTests.txt',265,'PlayerHealthGuardTests')]
tests=[]
for name,count,suite in logs:
    data=(p/name).read_text(encoding='utf-8-sig')
    assert f'{suite}: {count} checks, 0 failures' in data
    assert 'warning C' not in data and 'error C' not in data
    tests.append({'suite':suite,'checks':count,'failures':0,'log':name,'sha256':sha(p/name),'runner':'author; synthetic memory only'})
patch=[]
for baseline,current in [('baseline-GameplayStateSupport.inl',files[0]),('baseline-GameplayStateGuardTests.cpp',files[1])]:
    patch.extend(difflib.unified_diff((p/baseline).read_text(encoding='utf-8-sig').splitlines(True),
                                    (root/current).read_text(encoding='utf-8-sig').splitlines(True),fromfile=baseline,tofile=current))
(p/'implementation-delta.patch').write_text(''.join(patch),encoding='utf-8')
research=['evidence.json','claims.json','xrefs-extra.json','verify.py','verification.json','report.md',
          'implementation-delta.patch','baseline-GameplayStateSupport.inl','baseline-GameplayStateGuardTests.cpp']
report={
 'schemaVersion':1,'date':'2026-10-07','status':'SOURCE_AND_AUTHOR_TESTS_FROZEN; independent review is a separate receipt if supplied',
 'decision':'Permit only mission-clock script owner2 without inventing input loss; require proved controller vtable and consumed update callbacks. Keep active-event and other owner gates conservative.',
 'baseline':{'kind':'authoritative repository source immediately before this task; not a release-binary proof',
             'sourceSha256':sha(p/'baseline-GameplayStateSupport.inl'),'testSha256':sha(p/'baseline-GameplayStateGuardTests.cpp')},
 'current':{'fileHashes':{f:sha(root/f) for f in files}},
 'verification':v,'tests':tests,'totalAuthorChecks':sum(x['checks'] for x in tests),
 'claims':'claims.json','details':'report.md',
 'integration':{'nativeApi':'Unchanged Inspect/GameplayStateSnapshot/GameplayStateCapabilities',
                'slots':'456..462 unchanged;463 remains the common publication tick',
                'coreTwitchChanges':'None; current decoder and role/paused-duration contracts consume the same published state.',
                'fixtureChanges':'CombatGuardTests/PlayerHealthGuardTests only initialize the newly required vtable/update pointers.'},
 'limitations':['All events remain Cutscene; event mode bit8 alone does not prove usable ordinary control.',
                'Object-specific raw-pad/minigame paths in3A8FA0 are observed but not generalized into an allowlist.',
                'Only timer owner2 is newly permitted. Other unclassified owner bits remain Unknown.',
                'Exact retail code and known callback identities are required; modified callback bodies fail closed.',
                'Sampling cannot prove every intervening frame or usefulness of every action button.',
                'Synthetic tests do not execute a game process; only the isolated leaf timer bodies execute in allocated fixture memory.'],
 'researchFileHashes':{f:sha(p/f) for f in research},
 'noLiveActions':True,'noFullBuild':True,'noIdbWrites':True}
(p/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':report['status'],'fileHashes':report['current']['fileHashes'],
                  'checks':report['totalAuthorChecks'],'reportSha256':sha(p/'report.json')},indent=2))
