"""Build a source-bound receipt without touching immutable releases or product files."""
from pathlib import Path
import json,hashlib,zipfile,difflib
p=Path(__file__).resolve().parent;r=p.parents[2]
files=['src/KH2Trainer.Bridge/TargetingFeatures.inl','tests/KH2Trainer.Bridge.Tests/TargetingGuardTests.cpp',
 'src/KH2Trainer.Core/BridgeCommandRejectedException.cs','src/KH2Trainer/ViewModels/MainViewModel.cs',
 'src/KH2Trainer.Twitch/Effects/EffectCatalog.cs','src/KH2Trainer.Twitch/Effects/EffectModel.cs','src/KH2Trainer.Twitch/Effects/EffectEngine.cs',
 'src/KH2Trainer.Twitch/Effects/LockOnPairSnapshot.cs','src/KH2Trainer.Twitch/Effects/LockOnPairEffectLease.cs',
 'tests/KH2Trainer.Twitch.Tests/Fakes.cs','tests/KH2Trainer.Twitch.Tests/FakeLockOnPair.cs',
 'tests/KH2Trainer.Twitch.Tests/LockOnPairOwnershipTests.cs','tests/KH2Trainer.Twitch.Tests/Program.cs']
sha=lambda b:hashlib.sha256(b).hexdigest()
zpath=r/'artifacts/packages/KH2_Trainer_v0.12.6/Source.zip'
baseline={};patch=[]
with zipfile.ZipFile(zpath) as z:
    for name in files:
        candidates=[n for n in z.namelist() if n.replace('\\','/').endswith(name)]
        assert len(candidates)<=1,(name,candidates)
        old=z.read(candidates[0]) if candidates else b'';new=(r/name).read_bytes()
        baseline[name]=sha(old) if candidates else None
        patch.extend(difflib.unified_diff(old.decode('utf-8-sig').splitlines(True),new.decode('utf-8-sig').splitlines(True),fromfile='v0.12.6/'+name,tofile='current/'+name))
(p/'implementation-delta.patch').write_text(''.join(patch),encoding='utf-8')
claims=[
 ('0x1403abd60','Receives scale in XMM0, writes global2A1141C, multiplies Float32 by current parameters+80, writes separate2A11420; returned RAX is incidental parameter address.'),
 ('0x1403abd80','Receives Float32 in XMM0 and writes only2A11420, permitting an independent break distance.'),
 ('0x1403aba10','No-argument getter returns global scale2A1141C in XMM0.'),
 ('0x1403aba20','No-argument getter returns global break distance2A11420 in XMM0.'),
 ('0x1403abab0','Initializes scale1 and break from native parameters+80, alongside targeting globals.'),
 ('0x14038cf20','Calls scale setter with4, then direct distance setter with Float32(4*parameters+76+500), demonstrating the pair need not be scale*retention-default.'),
 ('0x1404308d0','VM wrapper loads the first Float32 at RCX into XMM0 then tail-jumps to3ABD60.'),
 ('0x1403bea30','Target acquisition derives distance from scale*parameters+76, with target Actor+1736 bit0x400 exemption when scale>=1 and further native target eligibility checks.'),
 ('0x1403dd280','Manual target retention uses separate break-distance getter; target Actor+1736 bit0x400 with scale>=1 can bypass this distance test. Invalid targets are cleared through3DD510.')]
verification=json.loads((p/'verification.json').read_text())
native=(p/'native-TargetingGuardTests.txt').read_text(encoding='utf-8-sig');twitch=(p/'twitch-tests.txt').read_text(encoding='utf-8-sig')
assert '876 checks, 0 failures' in native and '2074 passed, 0 failed' in twitch
receipt={'schema':1,'date':'2026-10-07','status':'implemented_focused_tests_passed_pending_independent_review_and_central_build',
 'scope':'F04 paired global targeting ownership for eagle-eye/short-sighted; Sora-only; no live actions or whole build.',
 'baseline':{'release':'v0.12.6','sourceZip':str(zpath.relative_to(r)),'sha256':sha(zpath.read_bytes()),'fileHashes':baseline},
 'current':{'fileHashes':{n:sha((r/n).read_bytes()) for n in files},'sharedOwnership':'MainViewModel receipt covers its complete current file; this task changes only received native rejection conversion. Root owns other shared integration.'},
 'verification':verification,
 'claims':[{'addr':a,'Domain':'native','Finding':f,'Evidence':['docs/research/lockon-pair-ownership-20261007/evidence.json#functions[addr='+a+']'],
 'Limitations':'Complete body read and original bytes verified; claim is scoped to these globals/call paths, not general target eligibility or role compatibility.'} for a,f in claims],
 'api':{'command':1475,'capabilities':[475,476],'arguments':['operation0Apply1Restore','expectedScaleFloat32Bits','expectedBreakFloat32Bits','desiredScaleFloat32Bits','desiredBreakFloat32Bits','expectedRetainFloat32Bits'],
 'snapshot':{'475':'exactUInt32ScaleBits','476':'exactUInt32BreakBits','373':'exactFloat32NativeRetentionDefault'},'runtimePins':[{'rva':'0x3ABD60','bytes':29},{'rva':'0x3ABD80','bytes':9}]},
 'tests':{'native':{'checks':876,'failures':0,'warningFree':True,'log':'native-TargetingGuardTests.txt'},'twitch':{'passed':2074,'failed':0,'log':'twitch-tests.txt'},'attribution':'These are author-executed isolated suite results; Root owns later whole-build/UI/package verification.'},
 'behaviorCases':['custom original independent break restored exactly','one-ULP edit to either field preserves whole foreign pair','native-default change before apply rejects without write','changed native default does not alter exact restore','invalid inputs/roles/guards/readonly pages do not write','coherent raw-bit decoding rejects stale/missing/fractional/nonfinite/out-of-range data','failed start and lost apply ACK retain cleanup intent','lost restore ACK requires subsequent acknowledged conditional restore','cleanup retained beyond180second cutoff','matching and foreign pairs pause with blocked control even timer opt-out','no scalar sustain or fallback restore','foreign pair already equal desired preserved after definite mismatch ACK','only received prewrite codes2/3/4 clear failed-apply intent'],
 'limits':['value equality does not detect identical foreign writes or identical pairs reused across scene/process lifetimes','game-thread serialization is not hardware atomicity against foreign concurrent writers','ordinary command ACKs are not a retained MOV1 journal','host-process exit loses in-memory intent','native target exemptions and scripts still apply','no live game/UI/Twitch action'],
 'evidenceHashes':{n:sha((p/n).read_bytes()) for n in ['evidence.json','verification.json','verify.py','contract.md','native-TargetingGuardTests.txt','twitch-tests.txt','implementation-delta.patch']}}
(p/'report.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
(p/'report.txt').write_text('F04 paired lock-on ownership implemented.\n\n'+
 'Fresh retail evidence:9 complete functions,280 instructions,1248 body bytes,8 data bytes; complete setter pins38 bytes.\n'+
 'Native Targeting876/0; Twitch2074/0 (author runs). No live actions or fullbuild.\n'+
 'Both rewards use one exact pair apply plus conditional exact pair restore, Sora-only. Later edits to either field preserve the whole pair. Scalar sustain removed.\n'+
 'Ambiguous ACKs retain cleanup beyond180 seconds. Definite apply reject2/3/4 and local unpublished refusal create no ownership. Current commands stay serialized; no native receipt journal is claimed.\n'+
 'See contract.md for game-thread, same-value ABA, missing snapshot and shutdown limits. Original v0.12.6 baseline and current source hashes are separate in report.json.\n'+
 'Independent review and central build are separate later receipts, not claimed by this report.\n',encoding='utf-8')
print(json.dumps({'reportSha256':sha((p/'report.json').read_bytes()),'files':len(files),'native':876,'twitch':2074},indent=2))
