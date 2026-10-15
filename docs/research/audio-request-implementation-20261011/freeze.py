"""Freeze bounded implementation/source/test evidence; no game access."""
import hashlib,json,re,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'src/KH2Trainer.Core').is_dir())
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')
subprocess.run(['py','-3','-B',str(HERE/'build_signatures.py'),'--check'],cwd=ROOT,check=True)
subprocess.run(['py','-3','-B',str(HERE/'build_evidence.py'),'--check'],cwd=ROOT,check=True)
names=['src/KH2Trainer.Bridge/AudioRequestFeatures.inl','src/KH2Trainer.Bridge/AudioRequestSignatures.h','src/KH2Trainer.Bridge/TrainerBridge.cpp','tests/KH2Trainer.Bridge.Tests/AudioRequestGuardTests.cpp','tests/KH2Trainer.Bridge.Tests/PlayerBridgeTests.cpp','tests/KH2Trainer.Bridge.Tests/run-tests.ps1']
pins={}
for name in names:
 p=ROOT/name;dest=HERE/'source'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
 pins[name]=dict(bytes=p.stat().st_size,sha256=sha(p),snapshot=dest.relative_to(HERE).as_posix())
baseline={k.replace('\\','/'):v for k,v in load(HERE/'baseline.json').items()};mixer='src/KH2Trainer.Bridge/AudioFeatures.inl'
assert sha(ROOT/mixer)==baseline[mixer]
suiteChecks={};logs={}
for name,expected in [('AudioRequestGuardTests',21097),('AudioGuardTests',618),('PlayerBridgeTests',665)]:
 p=HERE/'test-logs'/f'native-{name}.txt';text=p.read_text(encoding='utf-8-sig');match=re.search(r'(\d+) checks, (\d+) failures',text)
 assert match and int(match[1])==expected and int(match[2])==0,name
 assert not re.search(r'\b(?:warning|error) C\d+',text),name
 suiteChecks[name]=expected;logs[p.relative_to(HERE).as_posix()]=sha(p)
prod=HERE/'test-bin/AudioRequestGuardTests.Production.obj';assert prod.is_file() and prod.stat().st_size>0
assert 'TrainerBridge.cpp' in (HERE/'test-logs/native-AudioRequestGuardTests.txt').read_text(encoding='utf-8-sig')
body=(ROOT/names[0]).read_text(encoding='utf-8-sig');bridge=(ROOT/names[2]).read_text(encoding='utf-8-sig')
for forbidden in ['TryEnterCriticalSection','EnterCriticalSection','LeaveCriticalSection','DecodePacked','At<','KH2_AUDIO_REQUEST_TESTS']:
 assert forbidden not in body,forbidden
assert '!AudioRequestHandle(c, slot, args, result) && !AudioHandle(c, slot, args, result)' in bridge
assert 'AudioRequestCapabilities();' in bridge and 'AudioRequestSnapshot(c);' in bridge
facts=dict(success=True,status='IMPLEMENTED_PENDING_INDEPENDENT_REVIEW',slots=[482,483,484],readOnly=True,rejectedCommands=[1482,1483,1484],features=['free request slots','reservations since audio pass/reset','observed admission gate mask'],
 sourcePins=pins,unchangedMixer=dict(path=mixer,sha256=sha(ROOT/mixer)),nativeSignatures=dict(writers=8,bytes=1520,receipt='signature-evidence.json',sha256=sha(HERE/'signature-evidence.json')),
 nativeTestChecks=suiteChecks,totalNativeTestChecks=sum(suiteChecks.values()),testLogPins=logs,productionCompile=dict(source='src/KH2Trainer.Bridge/TrainerBridge.cpp',testDefines=False,objectSha256=sha(prod),bytes=prod.stat().st_size,linked=False,compiler='cl.exe',arguments=['/nologo','/std:c++17','/O2','/W4','/MT','/EHsc','/DUNICODE','/D_UNICODE','/c','src/KH2Trainer.Bridge/TrainerBridge.cpp','/Fo<isolated output>/AudioRequestGuardTests.Production.obj'],commandSource='tests/KH2Trainer.Bridge.Tests/run-tests.ps1',outputLog='test-logs/native-AudioRequestGuardTests.txt'),
 directSnapshotReads=[dict(rva='0xAD9390',size=4,signed=True,range=[0,80]),dict(rva='0xAD93C0',size=1,signed=False,range=[0,1]),dict(rva='0xAD93C4',size=4,signed=True,range=[0,25])],
 guardContract=['Validated existing post-Update route; matching base/game thread, enabled bridge and fresh nonzero host heartbeat.',
 'All eight exact native writer-body signatures match before sampling; each of the three scalar spans is readable.',
 'Two independently loaded volatile samples must be in range and equal; context, host heartbeat and shared mapping identity are checked again before publication.',
 'Only then publish all three values within TrainerFrame snapshot sequence; otherwise its cleared valid bits stay invalid. Explicit read-only commands are rejected before generic fallback.'],
 boundaries=['Snapshot observes shared admission counters, not active/queued/audible voice counts or future playback success.',
 'Equal consecutive scalar values are not an atomic multi-field sample, global writer census, lock or ABA guarantee. The existing Sound critical section is not acquired or claimed to protect this pool.',
 'Interval count resets can hide all activity between two UI samples. No dropped count, rate, history or wall-clock unit is inferred.',
 'No new hook, native audio/resource call, request-list traversal, Actor/bank/resource pointer dereference, game/save/config write or native counter write.',
 'Only static original-file reads and synthetic tests; no live game, injection, attach, GUI or audio observation.'],
 nativeFindings=dict(receipt='report.json',sha256=sha(HERE/'report.json')),reproduction='Run tests/KH2Trainer.Bridge.Tests/run-tests.ps1 -Suite AudioRequestGuardTests,AudioGuardTests,PlayerBridgeTests -OutputDirectory <isolated artifact folder> -LogDirectory <isolated log folder>; build_signatures.py --check compares original evidence and header.')
write(HERE/'implementation.json',facts)
selected=[p for p in HERE.rglob('*') if p.is_file() and 'test-bin' not in p.parts and '__pycache__' not in p.parts and p!=HERE/'manifest.json']
write(HERE/'manifest.json',dict(files={p.relative_to(HERE).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(selected)}))
print(json.dumps(dict(success=True,sourceFiles=len(pins),checks=sum(suiteChecks.values()),manifestSha256=sha(HERE/'manifest.json'))))
