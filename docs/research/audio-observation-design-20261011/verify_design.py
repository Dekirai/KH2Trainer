"""Check the bounded audio-observation evidence and proposed scalar arithmetic."""
import hashlib,json,struct
from pathlib import Path
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_MEM,X86_REG_RIP
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'src/KH2Trainer.Core').is_dir())
SOURCE=HERE/'source-snapshots'
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
checks=0
def check(ok,label):
 global checks
 checks+=1
 if not ok:raise AssertionError(label)
target=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
raw=target.read_bytes();digest=hashlib.sha256(raw).hexdigest()
check(digest=='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed','original executable identity')
pe=struct.unpack_from('<I',raw,60)[0];base=struct.unpack_from('<Q',raw,pe+48)[0]
ns=struct.unpack_from('<H',raw,pe+6)[0];os=struct.unpack_from('<H',raw,pe+20)[0]
sections=[struct.unpack_from('<4I',raw,pe+24+os+40*i+8) for i in range(ns)]
def read(addr,size):
 rva=addr-base;hits=[(va,rp) for vs,va,rs,rp in sections if va<=rva and rva+size<=va+rs]
 check(len(hits)==1,('unique original bytes',addr));va,rp=hits[0];return raw[rp+rva-va:rp+rva-va+size]
c=load(HERE/'capture.json');m=Cs(CS_ARCH_X86,CS_MODE_64);m.detail=True
observed={int(x['addr'],0):bytes(int(t,16) for t in x['data'].split()) for x in c['bytes']['result']}
native=[];decoded={};instructions=0;bodybytes=0
for f in c['disassembly']:
 address=int(f['addr'],0);size=f['size'];b=read(address,size)
 check(b==observed[address],('fresh IDA/original byte equality',f['addr']))
 asm=f['asm'];check(asm['cursor']['done'] and asm['instruction_count']==asm['total_instructions'],'complete ASM pagination')
 ins=list(m.disasm(b,address));check(sum(x.size for x in ins)==size,'complete independent decode')
 lines=asm['asm']['lines'];check([x.address for x in ins]==[int(l['addr'],16) for l in lines],'IDA instruction boundaries')
 decoded.update({x.address:x for x in ins});instructions+=len(ins);bodybytes+=size
 native.append(dict(addr=f['addr'],bytes=size,instructions=len(ins),sha256=hashlib.sha256(b).hexdigest()))
# Positive direct scalar references and instruction access directions. This is
# an observed writer census, not a whole-executable alias/indirect-writer proof.
globals=[base+int(x,16) for x in ['AD9390','AD93C0','AD93C4']]
scalarRefs=[]
for ins in decoded.values():
 for operand in ins.operands:
  if operand.type==X86_OP_MEM and operand.mem.base==X86_REG_RIP:
   dest=ins.address+ins.size+operand.mem.disp
   if dest in globals:
    scalarRefs.append(dict(site=hex(ins.address),target=hex(dest),instruction=ins.mnemonic+' '+ins.op_str,size=operand.size,access=operand.access))
check(any(r['site']=='0x14000dba1' and r['target']=='0x140ad9390' and r['instruction'].endswith(', 0x50') for r in scalarRefs),'80-entry initial free count')
check(any(r['site']=='0x1401dd4e0' and r['instruction'].endswith(', 1') for r in scalarRefs),'explicit inhibit setter')
check(any(r['site']=='0x1401dd4f0' and r['instruction'].endswith(', 0') for r in scalarRefs),'explicit inhibit clearer')
for site,mnemonic in [('0x1401dd522','jle'),('0x1401dd52d','jg'),('0x1401ddf4b','jle'),('0x1401ddf5c','jg')]:
 check(decoded[int(site,0)].mnemonic==mnemonic,('signed gate branch',site))

upstream=ROOT/'docs/research/voice-request-lifecycle-20261008';e=load(upstream/'evidence.json')
selected=['0x1401de230','0x1401dd8d0','0x1401deb50','0x1401dc370']
for f in e['functions']:
 if f['addr'].lower() not in selected:continue
 b=bytes.fromhex(f['originalBytes']);check(read(int(f['addr'],0),len(b))==b,'prior study body matches original')
 check(hashlib.sha256(b).hexdigest()==f['sha256'],'prior body hash')
 native.append(dict(addr=f['addr'],bytes=len(b),sha256=f['sha256'],source='docs/research/voice-request-lifecycle-20261008/evidence.json'))

# Proposed diagnostic: copied globals only. No request-list traversal, native
# query, camera, Actor, bank or resource dereference.
def sample(before,after,ready=True,code_ok=True):
 if not ready or not code_ok or before!=after:return None
 free,interval,inhibit=after
 if not 0<=free<=80 or not 0<=interval<=25 or inhibit not in [0,1]:return None
 reasons=(1 if inhibit else 0)|(2 if free<=16 else 0)|(4 if interval>24 else 0)
 return (free,interval,reasons)
cases=0
for free in range(81):
 for interval in range(26):
  for inhibit in range(2):
   t=(free,interval,inhibit);r=sample(t,t);cases+=1
   check(r is not None and ((r[2]==0)==(not inhibit and free>16 and interval<=24)),'reason mask equals exact captured gate logic')
   for field in range(3):
    altered=list(t);altered[field]+=1
    check(sample(t,tuple(altered)) is None,'changed tuple rejected');cases+=1
for t in [(-1,0,0),(81,0,0),(80,-1,0),(80,26,0),(80,0,2)]:check(sample(t,t) is None,'invalid scalar range');cases+=1
check(sample((80,0,0),(80,0,0),ready=False) is None,'context guard')
check(sample((80,0,0),(80,0,0),code_ok=False) is None,'code guard')
check(sample((17,24,0),(17,24,0))==(17,24,0),'last reservation admitted')
check(sample((16,25,0),(16,25,0))==(16,25,6),'subsequent reservation blocked by two limits')

baseline=load(HERE/'baseline-source-pins.json')
for name,digest_expected in baseline['sourcePins'].items():
 assert sha(SOURCE/name)==digest_expected,('historical source identity',name)
features=load(SOURCE/'src/KH2Trainer/Data/features.json');used={x['CapabilitySlot'] for x in features}
check(not used.intersection(range(482,485)),'proposed slots free in historical v0.12.15 source')
sourceNames=['src/KH2Trainer.Bridge/AudioFeatures.inl','src/KH2Trainer.Bridge/SpatialAudioFeatures.inl','src/KH2Trainer.Bridge/TrainerBridge.cpp','src/KH2Trainer.Core/BridgeProtocol.cs','src/KH2Trainer.Core/Models.cs','src/KH2Trainer.Core/ProfileStore.cs','src/KH2Trainer/ViewModels/FeatureViewModel.cs','src/KH2Trainer/ViewModels/Navigation.cs','src/KH2Trainer/Data/features.json','tests/KH2Trainer.Bridge.Tests/AudioGuardTests.cpp']
out=dict(success=True,checks=checks,originalSha256=digest,freshBodies=6,freshInstructions=instructions,freshBodyBytes=bodybytes,modelCases=cases,nativeEvidence=native,positiveScalarReferences=scalarRefs,
 sourcePins={name:sha(SOURCE/name) for name in sourceNames},sourceBasis=baseline['basis'],baselinePinsSha256=sha(HERE/'baseline-source-pins.json'),upstreamPins={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in [upstream/'manifest.json',upstream/'evidence.json',upstream/'report.txt']},
 captureSha256=sha(HERE/'capture.json'),scriptSha256=sha(Path(__file__)),
 limits=['Only selected direct references were inventoried. Negative xref results and auto-analysis readiness do not close indirect/alias writers.',
 'Scalar model validates proposed guards and labels; no production snapshot, native instructions, resource, concurrency or audio playback executed.',
 'Repeated equal tuples cannot prove coherent atomic sampling or exclude ABA. This design reports sampled native admission counters, not success of future playback.'])
(HERE/'verification.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in out.items() if k in ['success','checks','freshBodies','freshInstructions','freshBodyBytes','modelCases']}))
