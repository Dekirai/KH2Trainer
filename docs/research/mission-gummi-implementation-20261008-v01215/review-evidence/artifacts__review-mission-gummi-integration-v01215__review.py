"""Independent integration review; writes only its own artifact receipt."""
import hashlib,json,struct,zipfile,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
STUDY=ROOT/'docs/research/mission-gummi-implementation-20261008-v01215'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
checks=0
def check(ok,label):
 global checks
 checks+=1
 if not ok:raise AssertionError(label)

archive=ROOT/'artifacts/packages/KH2_Trainer_v0.12.14/Source.zip'
with zipfile.ZipFile(archive) as z:old={n:z.read(n) for n in z.namelist() if n.startswith(('src/','tests/'))}
pins={};changed=[];unchanged=[]
for name,before in old.items():
 p=ROOT/name;check(p.is_file(),('prior source retained',name));pins[name]=sha(p)
 (changed if p.read_bytes()!=before else unchanged).append(name)
expectedChanged={
 'src/KH2Trainer/Data/features.json','src/KH2Trainer/KH2Trainer.csproj',
 'src/KH2Trainer.Bridge/MissionEventFeatures.inl','src/KH2Trainer.Bridge/MissionFeatures.inl',
 'src/KH2Trainer.Core/Data/BdxNativeCalls.json',
 'tests/KH2Trainer.Bridge.Tests/MissionEventGuardTests.cpp','tests/KH2Trainer.Bridge.Tests/MissionGuardTests.cpp',
 'tests/KH2Trainer.Bridge.Tests/PlayerBridgeTests.cpp','tests/KH2Trainer.Core.Tests/BdxNativeCallCatalogTests.cs',
 'tests/KH2Trainer.Core.Tests/MissionRescueCatalogTests.cs','tests/KH2Trainer.UiTests/Program.cs'}
check(set(changed)==expectedChanged,('exact release source change set',changed))
added=[];local=[]
for base in ['src','tests']:
 for p in (ROOT/base).rglob('*'):
  if not p.is_file() or any(x in p.parts for x in ['bin','obj']):continue
  name=p.relative_to(ROOT).as_posix()
  if name in old:continue
  if p.name.endswith(('.user','.log','.pubxml')):local.append(name);continue
  added.append(name);pins[name]=sha(p)
check(set(added)=={'src/KH2Trainer.Bridge/MissionCounterSupport.h','tests/KH2Trainer.UiTests/MissionCounterUiChecks.cs'},('only two new implementation/test files',added))
version=(ROOT/'src/KH2Trainer/KH2Trainer.csproj').read_text(encoding='utf-8-sig')
check('<Version>0.12.15</Version>' in version,'current version15')
check(old['src/KH2Trainer/KH2Trainer.csproj'].decode('utf-8-sig').replace('\r\n','\n').replace('0.12.14','0.12.15')==version,'version-only project change apart from line endings')

nativeReceipt=ROOT/'artifacts/review-mission-counter-implementation-20261008/review.json'
native=load(nativeReceipt);check(native['status']=='ACCEPTED_BOUNDED_NATIVE_IMPLEMENTATION' and not native['blockers'],'native peer acceptance')
for name,pin in native['sourcePins'].items():check(sha(ROOT/name)==pin['sha256'],('native reviewed source pin',name))

manifestPins={}
for study in ['mission-counter-implementation-20261008','bdx-bank3-extended-20261008','voice-request-lifecycle-20261008']:
 path=ROOT/'docs/research'/study/'manifest.json';m=load(path);files=m['files']
 entries=files.items() if isinstance(files,dict) else ((x.get('file',x.get('path')),x) for x in files)
 for name,pin in entries:
  p=path.parent/name;check(sha(p)==(pin if isinstance(pin,str) else pin['sha256']),('study manifest file',study,name))
  if isinstance(pin,dict) and 'bytes' in pin:check(p.stat().st_size==pin['bytes'],('study manifest size',study,name))
 manifestPins[study]=sha(path)
check(manifestPins['mission-counter-implementation-20261008']==native['studyManifestSha256'],'native final manifest')
bank3=load(ROOT/'artifacts/review-bdx-bank3-extended-20261008.json')
check(bank3['success'] and not bank3['blockers'] and bank3['sourceHashes']['manifest.json']==manifestPins['bdx-bank3-extended-20261008'],'Bank3 independently accepted final manifest')
voiceReview=load(ROOT/'artifacts/review-voice-lifecycle-v01215/review.json')
check(voiceReview['success'] and not voiceReview['blockers'] and voiceReview['status']=='ACCEPTED_BOUNDED_STATIC_RESEARCH','Voice independent acceptance')
for name,digest in voiceReview['pins'].items():check(sha(ROOT/name)==digest,('Voice review pin',name))

data=load(ROOT/'src/KH2Trainer.Core/Data/BdxNativeCalls.json')
baseline=json.loads(old['src/KH2Trainer.Core/Data/BdxNativeCalls.json'].decode('utf-8-sig'))
check(data==load(STUDY/'catalog-data.json'),'product/research catalog identity')
check({k:v for k,v in data.items() if k!='descriptors'}=={k:v for k,v in baseline.items() if k!='descriptors'},'catalog top-level and bank metadata unchanged')
newRows={(r['bank'],r['index']):r for r in data['descriptors']};oldRows={(r['bank'],r['index']):r for r in baseline['descriptors']}
check(len(newRows)==len(oldRows)==len(data['descriptors'])==1063,'1063 unique descriptors')
check(list(newRows)==sorted(newRows) and newRows.keys()==oldRows.keys(),'ordered keys retained')
check(sum(bool(r['name']) for r in oldRows.values())==239,'239 baseline annotations')
check(sum(bool(r['name']) for r in newRows.values())==256,'256 current annotations')
check(sum(r['handlerRva']==0 for r in newRows.values())==15,'15 NULL holes')

# Independent PE mapper, not the production or study verifier.
target=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe');raw=target.read_bytes()
check(hashlib.sha256(raw).hexdigest()==data['originalSha256']=='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed','original EXE identity')
pe=struct.unpack_from('<I',raw,60)[0];check(raw[pe:pe+4]==b'PE\0\0','PE signature')
nsec,opt=struct.unpack_from('<H',raw,pe+6)[0],struct.unpack_from('<H',raw,pe+20)[0]
check(struct.unpack_from('<H',raw,pe+24)[0]==0x20b,'PE32+')
base=struct.unpack_from('<Q',raw,pe+48)[0];check(base==0x140000000,'original base')
sections=[struct.unpack_from('<4I',raw,pe+24+opt+40*i+8) for i in range(nsec)]
def read(rva,size):
 hits=[(va,rs,rp) for vs,va,rs,rp in sections if va<=rva and rva+size<=va+rs]
 check(len(hits)==1,('unique raw section',rva));va,rs,rp=hits[0];return raw[rp+rva-va:rp+rva-va+size]
numeric=['bank','index','descriptorRva','handlerRva','flags'];textfields=['name','summary','notes','evidence'];changedRows=[]
banks={b['bank']:b for b in data['banks']}
for key,row in newRows.items():
 before=oldRows[key]
 check(set(row)==set(before)==set(numeric+textfields),('descriptor schema',key))
 check(all(row[n]==before[n] for n in numeric),('numeric metadata retained',key))
 check(all(isinstance(row[n],str) for n in textfields),('text fields',key))
 check(row['descriptorRva']==banks[key[0]]['tableRva']+16*key[1],('row offset',key))
 check(struct.unpack('<QII',read(row['descriptorRva'],16))==(base+row['handlerRva'] if row['handlerRva'] else 0,row['flags'],0),('original descriptor bytes',key))
 if row!=before:changedRows.append(key)
annotations=load(ROOT/'docs/research/bdx-bank3-extended-20261008/annotations.json')['annotations']
expected={tuple(map(int,key.split(':'))) for key in annotations}
check(len(expected)==17 and set(changedRows)==expected|{(1,262)},'exact17new and1expanded rows')
for key,a in annotations.items():
 pair=tuple(map(int,key.split(':')));row=newRows[pair]
 check(not oldRows[pair]['name'],'new annotation previously unannotated')
 for field in textfields:check(row[field]==a[field],('exact source annotation',key,field))
 check(row['handlerRva']==int(a['handlerRva'],0) and row['flags']&65535==a['declaredOperandCount'] and bool(row['flags']&0x40000000)==a['hasReturnSlot'],('source ABI contract',key))
for key,row in newRows.items():
 if key not in changedRows:check(row==oldRows[key],('untouched structured row',key))
voice=newRows[1,262];before=oldRows[1,262]
check(voice['name']==before['name'] and voice['summary']==before['summary'],'voice general ABI/title preserved')
check(voice['notes'].startswith(before['notes']+' ') and voice['evidence'].startswith(before['evidence']+'; '),'previous voice limits retained')
for text in ['selected Voice update consumes its pending ID before request admission','does not retain it for an automatic retry','nonzero handle can still identify a queued request','does not prove playback','missing-ORIGIN-bank return path','resource-derived key, Voice ID and group 2','does not establish exclusive backend ownership','conditional paths','not a live audio observation']:
 check(text in voice['notes'],('bounded voice synthesis',text))

features=load(ROOT/'src/KH2Trainer/Data/features.json');priorFeatures=json.loads(old['src/KH2Trainer/Data/features.json'].decode('utf-8-sig'))
byId={f['Id']:f for f in features};priorById={f['Id']:f for f in priorFeatures}
check(len(features)==len(byId)==358 and len(priorFeatures)==353,'feature counts')
for key,before in priorById.items():check(byId[key]==before,('old feature unchanged',key))
newIds=['mission.counter.add','mission.counter.digit','mission.combo.current','mission.combo.peak','mission.combo.allowance']
check(set(byId)-set(priorById)==set(newIds),'exact five new features')
for index,name in enumerate(newIds):
 f=byId[name];slot=477+index
 check(f['CapabilitySlot']==slot and sum(g['CapabilitySlot']==slot for g in features)==1,('unique slot',name))
 check(f['RequiresScene'] and not f['CanSaveInProfile'] and f['Category']=='Missions',('scene/profile/category',name))
 check('Live gameplay not tested' in f['Evidence'][0]['Level'],('evidence scope',name))
 if index<2:
  check(f['CommandId']==1000+slot and f['Kind']=='Action' and f['ValueSlot']==-1 and f['ChangesProgression'],('one-time command contract',name))
  check('events remain enabled' in f['Description'] and 'No undo' in f['RestoreBehavior'] and 'automatic retry' in f['RestoreBehavior'],('effects and retry disclosure',name))
  a=f['Arguments'];check(a[0]['Minimum']==0 and a[0]['Maximum']==2 and [c['Value'] for c in a[0]['Choices']]==[0,1,2],('counter selector',name))
 else:
  check(f['CommandId']==0 and f['Kind']=='ReadOnly' and f['ValueSlot']==slot and not f['ChangesProgression'] and not f.get('Arguments'),('read-only combo contract',name))
check([(a['Minimum'],a['Maximum']) for a in byId[newIds[0]]['Arguments']]==[(0,2),(-2147483648,2147483647)],'full signed delta range')
check([(a['Minimum'],a['Maximum']) for a in byId[newIds[1]]['Arguments']]==[(0,2),(0,9),(0,9)],'bounded digit arguments')
for a in byId[newIds[1]]['Arguments'][1:]:check([c['Value'] for c in a['Choices']]==list(range(10)),'digit/position complete choices')
check(byId[newIds[4]]['Minimum']<0 and byId[newIds[4]]['Unit']=='native units','signed native allowance with no seconds claim')

# Reproduction runs in check mode only; no producer receipt is accepted alone.
reproduce=subprocess.run(['py','-3','-B',str(STUDY/'build_catalog.py'),'--check'],cwd=ROOT,check=True,capture_output=True,text=True)
(HERE/'catalog-reproduce.txt').write_text(reproduce.stdout,encoding='utf-8')
probe=load(HERE/'probe-result.json');bdx=load(HERE/'bdx-probe/result.json')
check(probe['success'] and probe['checks']==3840 and probe['wireArgumentChecks']==2520,'independent compiled UI/transport probe')
check(probe['featureSha256']==sha(ROOT/'src/KH2Trainer/Data/features.json'),'tested feature bytes')
check(bdx['success'] and bdx['checks']==13884 and bdx['resourceSha256']==sha(ROOT/'src/KH2Trainer.Core/Data/BdxNativeCalls.json'),'independently rebuilt BDX probe')
for p in [*STUDY.glob('*.py'),*STUDY.glob('*.cs'),STUDY/'Probe.csproj',STUDY/'run-probe.ps1',STUDY/'metadata-checks.json',nativeReceipt,ROOT/'artifacts/review-bdx-bank3-extended-20261008.json',ROOT/'artifacts/review-voice-lifecycle-v01215/review.json',ROOT/'build.ps1',HERE/'Program.cs',HERE/'Probe.csproj',HERE/'probe-result.json',HERE/'bdx-probe/result.json',HERE/'review.py']:
 pins[p.relative_to(ROOT).as_posix()]=sha(p)
out=dict(status='ACCEPTED_OFFLINE_PRODUCT_INTEGRATION',success=True,blockers=[],checks=checks,compiledManagedChecks=probe['checks'],wireArgumentChecks=2520,compiledBdxChecks=13884,
 baselineSourceZipSha256=sha(archive),unchangedSourceFiles=len(unchanged),changedSources=sorted(changed),addedImplementationSources=sorted(added),localFilesOutsideReview=sorted(local),
 originalSha256=hashlib.sha256(raw).hexdigest(),descriptors=1063,originalDescriptorBytes=17008,unchangedNumericRows=1063,changedTextRows=18,newAnnotations=17,expandedAnnotations=1,unchangedRows=1045,totalAnnotations=256,
 totalFeatures=358,newFeatures=newIds,productSha256=sha(ROOT/'src/KH2Trainer.Core/Data/BdxNativeCalls.json'),featureSha256=sha(ROOT/'src/KH2Trainer/Data/features.json'),manifestPins=manifestPins,sourcePins=pins,
 semanticReview=[
 'All prior353 feature records remain exactly unchanged. The two new actions preserve full signed32 delta values and decimal position/digit0..9 after counter index0..2. Native integer/range preflight rejects fractional doubles; the generic numeric editor itself accepts fractions.',
 'Actual production FeatureVm and Core were compiled in an isolated review project. All300 digit selector combinations, signed delta endpoints, failure/no-retry behavior, unsupported bridge/scene/busy gates and missing/read-only combo samples were exercised with synthetic hosts.315 requests used actual BridgeConnection against a newly created negative-pseudo-PID mapping; all eight wire fields and results were checked.',
 'New controls issue one-time commands and are excluded from profiles. UI descriptions retain native threshold/reward/transition effects and tested scope. Readouts preserve signed native allowance rather than claiming a wall-clock seconds unit.',
 'Native mission files match the accepted implementation review pins. Current TrainerBridge route and Core/UI/transport/profile implementations remain byte-identical to14. No native implementation re-review or original target execution is claimed here.',
 '17 Bank3 text rows transfer exactly from the independently accepted extended study. All1063 descriptors match original PE pointer/flags/reserved bytes; numeric and bank metadata are unchanged.1045 entire rows are unchanged.',
 'The Voice extension remains conditional on selected descriptor dispatch. Pending consumption, failed admission with no local retry, queued-handle distinction and shared resource/ID/group backend identity match the bounded lifecycle report; no audible playback or complete lifetime proof is asserted.'
 ],limits=[
 'No game process, injection, attach, game/save/mod writes, live GUI or Twitch actions. Synthetic mappings cannot address a live PID.',
 'This review does not repeat full transitive native semantics or close runtime resource/callback/ABA/lifetime boundaries. Native implementation relies on its separately pinned review.',
 'Final frozen integration manifest, release packaging, embedded production DLL and full build/UI-render evidence remain parent responsibilities; the unfinished producer freeze script was not assumed verified.',
 'Extra .user/.pubxml/.log files in the workspace are enumerated without modification and are outside the implementation source comparison.'
 ])
dest=ROOT/'artifacts/review-mission-gummi-integration-v01215.json';dest.write_text(json.dumps(out,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')
print(json.dumps(dict(success=True,checks=checks,receipt=str(dest.relative_to(ROOT)),receiptSha256=sha(dest),sourcePins=len(pins))))
