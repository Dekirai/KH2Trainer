"""Maintainer-only study materialization. Writes only this new study directory.
Does not change product sources, frozen studies or execute game instructions.
"""
import hashlib,json,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=ROOT/'docs/research/bdx-bank4-calls-20261008'
SHA='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def hashfile(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,v):(HERE/name).write_bytes((json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode('utf-8'))

def main():
 assert hashfile(BASE/'manifest.json')=='97057b0fd176c11c929178ae1ed1f1d5d8fcf80b55892961d9e10373ca3679e5'
 assert hashfile(BASE/'evidence.json')=='e5b4b0ae754982ba6d99b3b8fd94768ae0c8987140d5500890f3440f6a287230'
 old=load(BASE/'evidence.json')
 wanted={0x3A2C30,0x3A35C0,0x3FC150,0x3FA610,0x3FA0D0,0x3FA440,0x3FA790,0x3FA820,0x3FA860,0x3FA8B0,0x3FB600,0x3FB750,0x3FBAE0,0x3FA230,0x3FBB30,0x3FB2B0}
 bodies=[f for f in old['functions'] if int(f['addr'],16)-0x140000000 in wanted]
 assert len(bodies)==16
 write('imported-evidence.json',{'schema':1,'Domain':'native','originalSha256':SHA,'imageBase':'0x140000000',
  'source':'../bdx-bank4-calls-20261008/evidence.json','sourceSha256':hashfile(BASE/'evidence.json'),
  'sourceManifestSha256':hashfile(BASE/'manifest.json'),
  'captureScope':'Exact copies of 16 complete previously reviewed IDA bodies, including all original pagination, pseudocode, original bytes and IDA bytes. No new IDA capture, database change or target execution in this implementation study.',
  'functions':bodies})
 sources=['src/KH2Trainer.Bridge/MissionFeatures.inl','src/KH2Trainer.Bridge/MissionEventFeatures.inl',
  'src/KH2Trainer.Bridge/MissionCounterSupport.h','src/KH2Trainer.Bridge/TrainerBridge.cpp',
  'tests/KH2Trainer.Bridge.Tests/MissionGuardTests.cpp','tests/KH2Trainer.Bridge.Tests/MissionEventGuardTests.cpp',
  'tests/KH2Trainer.Bridge.Tests/PlayerBridgeTests.cpp','tests/KH2Trainer.Bridge.Tests/run-tests.ps1']
 pins={}
 for source in sources:
  target=HERE/'source'/source;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/source,target)
  pins[source]={'snapshot':target.relative_to(HERE).as_posix(),'bytes':target.stat().st_size,'sha256':hashfile(target)}
 write('source-snapshots.json',pins)
 results={}
 for suite,checks in [('MissionEventGuardTests',13637),('MissionGuardTests',1159),('PlayerBridgeTests',655)]:
  target=HERE/'test-logs'/f'native-{suite}.txt';target.parent.mkdir(exist_ok=True)
  shutil.copyfile(ROOT/'artifacts/mission-counter-implementation-20261008'/target.name,target)
  results[suite]={'checks':checks,'failures':0,'log':target.relative_to(HERE).as_posix()}
 write('test-results.json',{'suites':results,'totalChecks':15451,'failures':0,
  'execution':'MSVC x64 C++17 /O2 /W4 /MT /EHsc. Isolated synthetic memory only; native callbacks in Mission suites are controlled models. PlayerBridgeTests compiles the production Mission branches without KH2_MISSION_TESTS/KH2_MISSIONEVENT_TESTS and tests guarded command rejection/routing; it never calls the target entries.',
  'command':'& tests/KH2Trainer.Bridge.Tests/run-tests.ps1 -Suite MissionEventGuardTests,MissionGuardTests,PlayerBridgeTests -LogDirectory artifacts/mission-counter-implementation-20261008'})
 claims=[]
 def claim(addr,finding,refs):
  claims.append({'addr':hex(0x140000000+addr),'Domain':'native','Finding':finding,
   'Evidence':['imported-evidence.json#functions[addr='+hex(0x140000000+x)+']' for x in refs]})
 claim(0x3FBAE0,'The existing absolute mission-counter wrapper reaches the native class setter. The added trainer commands calculate a checked absolute target and reuse this call once, preserving native boundary dispatch and threshold handling.',[0x3FBAE0,0x3FA230])
 claim(0x3FB2B0,'The raw relative adapter uses DWORD arithmetic. Its wrap-before-native-clamp behavior is not the new checked int64 trainer contract.',[0x3FB2B0,0x3FA230])
 claim(0x3FBB30,'The raw digit helper constructs a DWORD decimal divisor and uses signed division; unconstrained positions can produce divisor zero. The trainer uses positions 0..9, digits 0..9 and bounded int64 replacement instead of invoking this helper.',[0x3FBB30])
 claim(0x3A2C30,'The mission storage contains one embedded COMBOCOUNTER at +880. Registry membership and ID validation distinguish a configured object from constructor-initialized storage.',[0x3A2C30,0x3FA610,0x3FC150,0x3FA0D0])
 claim(0x3FA790,'Combo current is signed integer +56, peak +80 and allowance float +84. Native delta/clamp and peak update are distinct; configuration/reset and the peak-only setter do not establish peak>=current or peak<=maximum as universal invariants.',[0x3FA790,0x3FA440,0x3FA860,0x3FA8B0,0x3FB600,0x3FB750])
 claim(0x3FA820,'A positive finite combo allowance is reduced by the native float update step at 717480. At expiry current becomes min(maximum,0), allowance becomes zero and the completion bit is cleared, while peak is retained. Thus current becomes zero for the nonnegative maximum accepted by the trainer snapshot. Finite allowance<=0 bypasses the countdown; this study establishes no seconds conversion.',[0x3FA820,0x3A35C0,0x3FA860])
 write('claims.json',{'schema':1,'Domain':'native','claims':claims})
 limitations=[
  'ReadView/SameView and SameWidget are fresh metadata comparisons on the existing game-thread command path, not a global lock, reference-counted lifetime lease or proof that all workers/bulk teardown are serialized. Static mission storage can be reconstructed identically; no general ABA/generation guarantee is added.',
  'EventsReady checks the existing immediate allocator, event pool, Actor/controller/script, resource-cache and handler structures. It is not a proof of all transitive native callback/script behavior. Boundary callbacks retain rewards, progression and transition effects.',
  'A command calls the native absolute setter at most once after validation and does not inspect old pointers afterward. Native AL is unspecified. An acknowledgement means dispatch; there is no undo, delayed retry or durable request journal added by these commands.',
  'Combo values are conservative read-only snapshots of an active configured mission object; invalid/unavailable groups publish no values. Current must be nonnegative and <=nonnegative maximum, peak nonnegative, allowance finite. These acceptance checks do not claim all other bit patterns are impossible in retail scripts.',
  'Two matching snapshots do not prove global atomicity against every concurrent writer. Finite float-to-double publication preserves native float value and signed zero; NaN/Inf are unavailable. Native update units are deliberately not relabeled seconds.',
  'The tests exercise synthetic fixtures and controlled callback models. No live game, injection, GUI, mod/save write or original-code execution occurred. The tests do not validate live installation or retail mission coverage.'
 ]
 report={'schema':1,'status':'IMPLEMENTED_AND_SYNTHETICALLY_TESTED','originalSha256':SHA,
  'sourceStudy':{'path':'../bdx-bank4-calls-20261008','manifestSha256':hashfile(BASE/'manifest.json')},
  'commands':[
   {'slot':477,'commandId':1477,'id':'mission.counter.add','arguments':['counter index: integer 0..2','delta: signed int32'],'operation':'int64(current)+delta; reject target outside 0..configured maximum / INT32_MAX; no clamp/wrap'},
   {'slot':478,'commandId':1478,'id':'mission.counter.digit','arguments':['counter index: integer 0..2','decimal position: integer 0..9; 0=units','digit: integer 0..9'],'operation':'Replace the selected decimal digit using int64 power/product/subtraction/addition; reject out-of-bounds target'}],
  'snapshot':[{'slot':479,'offset':56,'type':'int32','meaning':'configured current combo'},
   {'slot':480,'offset':80,'type':'int32','meaning':'stored native peak, independent of current/maximum'},
   {'slot':481,'offset':84,'type':'float32 widened to double','meaning':'allowance in native update units; finite <=0 has no active countdown'}],
  'mutationGates':'All 8 arguments finite; exact index/domain checks; ReadView + Stable living-player/scene/menu/transition/progression guards; exact counter registry/class/ID/HUD validation; full original byte signatures; EventsReady always for both new actions, including interior/no-change targets; fresh ReadView/SameView/Stable/ReadWidget/SameWidget and EventsReady; final Allowed. Exactly Native(230, ...) once; no post-call game-pointer reads.',
  'snapshotGates':'Existing allowed game thread/host/module-base context and ReadView; active mission phase 1, flags initialized and not finishing; Range 88, registered COMBOCOUNTER vtable 5C9DF8 and ID 0. Two matching View/Combo captures including exact allowance bits before grouped publication. Paused field is permitted for read-only data; active HUD flag is not required.',
  'dispatcher':'Existing commandId=1000+slot dispatcher and 512-value protocol already carry all five slots. No dispatcher or protocol source change; capabilities added only by the two owned mission modules.',
  'testing':'15,451 checks, 0 failures in three targeted MSVC suites; decimal arithmetic uses an independent fixed-width string replacement oracle. Synthetic tests cover extremes, bounds, all indices/positions/digits, old-value drift, metadata/host/event gates, callback teardown, exact one-call dispatch, no post-call reads, negative/zero/large finite allowances, independent peaks and bitwise -0 freshness.',
  'nativeFindings':claims,'limitations':limitations,
  'reproduction':[
   'py -3 -B docs/research/mission-counter-implementation-20261008/verify.py --check --repo .',
   '& tests/KH2Trainer.Bridge.Tests/run-tests.ps1 -Suite MissionEventGuardTests,MissionGuardTests,PlayerBridgeTests -LogDirectory artifacts/mission-counter-implementation-20261008'],
  'reproductionNote':'Run from the repository root. Verifier can run portably without --repo against the study snapshots and --exe PATH. Compiled suites use the normal repository bridge dependencies; their pinned changed sources and runner are included here.'}
 write('report.json',report)
 text='Mission counter implementation / validated read-only combo snapshot\n\n'
 text+='477 / 1477: add signed int32 delta to counter 0..2 with int64 arithmetic.\n478 / 1478: replace decimal digit at position 0..9 (0=units) with digit 0..9.\nBoth reject invalid/current/max/out-of-range targets, then invoke only the existing absolute native setter once after fresh checks and complete EventsReady preflight. Native boundaries/rewards/transitions remain enabled.\n\n'
 text+='479..481: current, stored peak and native float allowance from the single registered COMBOCOUNTER (+880). The group requires stable matching metadata/field captures. Peak is independent of current/maximum. Finite negative and signed-zero allowances are retained; units are native update units, not seconds. No snapshot callback or write.\n\n'
 text+='Validation: MissionEventGuardTests 13,637; MissionGuardTests 1,159; PlayerBridgeTests 655. Total 15,451, zero failures. Production mission callsites compile in the full bridge fixture, whose new wire tests stop at guards. No original target instructions were called.\n\nLimits:\n'+'\n'.join('- '+x for x in limitations)+'\n\nReproduce from repo root:\n'+'\n'.join(report['reproduction'])+'\n'
 (HERE/'report.txt').write_text(text,encoding='utf-8',newline='\n')
if __name__=='__main__':main()
