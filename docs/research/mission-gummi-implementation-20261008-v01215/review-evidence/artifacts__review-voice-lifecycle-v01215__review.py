import importlib.util,json,hashlib
from itertools import product
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
STUDY=ROOT/'docs/research/voice-request-lifecycle-20261008'
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
v=module('voice_independent_bytes',HERE/'review_bytes.py')
check=v.check
for rel,digest in load(STUDY/'manifest.json')['files'].items():check(sha(STUDY/rel)==digest,('frozen manifest',rel))
check(len(v.functions)==59 and not any(f['gaps'] for f in v.functions),'59 contiguous complete captured bodies')
e=load(STUDY/'evidence.json')
for f in e['functions']:
    check(v.read(int(f['addr'],16),f['size'])==bytes.fromhex(f['originalBytes']),('normalized evidence original bytes',f['addr']))
anchors={
 0x1403ce291:('mov','dword ptr [rdi + 0xc], 0xffffffff'),
 0x1403ce2a3:('call','0x1403b5b40'),
 0x1403ce2ab:('mov','edx, esi'),
 0x1403ce2b0:('call','qword ptr [rbx + 8]'),
 0x1403ce2b8:('mov','dword ptr [rdi + 0x14], eax'),
 0x1403ce319:('mov','dword ptr [rdi + 0x14], 0'),
 0x1403ce550:('cmp','dword ptr [rcx + 0x14], 0'),
 0x1401de870:('cmp','byte ptr [rbx + 0x34], 1'),
 0x1401de874:('jne','0x1401de87e'),0x1401de876:('mov','al, 1'),
 0x1401dd65c:('movsx','r8d, word ptr [rbx + 0x2c]'),
 0x1401dd661:('mov','edx, dword ptr [rbx + 0x10]'),
 0x1401dd664:('mov','rcx, qword ptr [rbx + 0x18]'),
 0x1401dd668:('mov','qword ptr [rsp + 0x20], rbx'),
 0x1401dd66d:('call','0x1401dfd70'),
 0x1401dd672:('mov','byte ptr [rbx + 0x34], 2'),
 0x1401dfdc5:('mov','rdi, qword ptr [rbx + 0x20]'),
 0x1401dfdc9:('test','rdi, rdi'),0x1401dfdcc:('je','0x1401dfde9'),
 0x1401dfde9:('xor','eax, eax'),0x1401dfdeb:('jmp','0x1401dfe92'),
 0x1401dfdd2:('mov','dword ptr [rbx + 0xc], edi'),0x1401dfdd7:('call','0x1401363b0'),
 0x1401dfd25:('mov','ecx, dword ptr [rcx + 0xc]'),
 0x1401dfd45:('mov','r8d, 2'),0x1401dfd66:('call','0x140139470'),
 0x1401395c9:('cmp','dword ptr [rbx + 0x30], ebp'),
 0x1401395d2:('cmp','dword ptr [rbx + 0x34], esi'),
 0x1401395db:('cmp','dword ptr [rbx + 0x38], r15d'),
 0x1401395e5:('cmp','word ptr [rbx + 0x3e], 2'),
 0x1403da99d:('mov','dword ptr [rdi + 0xbb4], eax'),
 0x1403daac4:('mov','qword ptr [r14 + 0x20], rax'),
 0x1403daad5:('mov','dword ptr [rdi + 0xbb4], eax'),
 0x1403cd908:('mov','dword ptr [rbx + 0xc], 0xffffffff'),
 0x1401de378:('mov','byte ptr [rbx + 0x34], 4'),
 0x1401dd912:('call','0x1401dd560'),0x1401dc374:('call','0x1401dd8d0')}
for addr,pair in anchors.items():check((v.ins[addr].mnemonic,v.ins[addr].op_str)==pair,('selected semantic anchor',hex(addr)))
check(v.ins[0x1401dd66d].address+v.ins[0x1401dd66d].size==0x1401dd672,'backend return directly followed by unconditional state store')
m=module('voice_author_model',STUDY/'model.py');cases=0
def sx(x):return int.from_bytes((x&0xffffffff).to_bytes(4,'little'),'little',signed=True)
for pending,handle,old,new in product([0,8,0x7fffffff,0x80000000,0xffffffff],[0,19],[0,3,0x7fffffff,0x80000000,0xffffffff],[0,2,3,0x7fffffff,0x80000000,0xffffffff]):
    state=(pending,handle,old,'old actor')
    accept=(sx(pending)<0 and handle==0) or sx(new)>=sx(old)
    check(m.submit(state,9,new,'new actor')==((9,handle,new,'new actor') if accept else state),'signed priority replacement');cases+=1
for disabled,free,count in product([0,1],[0,16,17,80,0x80000000,0xffffffff],[0,24,25,0x7fffffff,0x80000000,0xffffffff]):
    check(m.admissible(disabled,free,count)==(disabled==0 and sx(free)>16 and sx(count)<25),'signed admission boundary');cases+=1
for handle in [0,5]:
    out,effects=m.poll((8,handle,3,'actor'),0,False,True,True)
    check(out==(-1,0,3,'actor') and effects.index(('pending',-1))<effects.index(('admit',8)),'failed admission consumes pending first');cases+=1
    again,effects2=m.poll(out,100,True,True,True)
    check(again==out and effects2==[],'no local automatic readmission');cases+=1
for state,active in product(range(256),[False,True]):
    expected=2 if state==1 or state==2 and active else 4 if state in [2,3] else state
    check(m.consume(state,active)[0]==expected,'selected EE state transitions');cases+=1
claims=load(STUDY/'claims.json');report=(STUDY/'report.txt').read_text(encoding='utf-8-sig')
check('that scan is not membership validation' in report and 'membership is not validated by that scan' in report,'pointer membership caveat retained')
pins={p.relative_to(ROOT).as_posix():sha(p) for p in [STUDY/'manifest.json',STUDY/'evidence.json',STUDY/'claims.json',STUDY/'report.txt',STUDY/'model.py',HERE/'review_bytes.py',HERE/'review.py']}
result=dict(success=True,status='ACCEPTED_BOUNDED_STATIC_RESEARCH',blockers=[],checks=v.checks,independentModelCases=cases,independentSemanticAnchors=len(anchors),nativeFunctions=59,nativeInstructions=2873,nativeBytes=10883,dataSpans=15,pins=pins,manualReview=['Read all addressed claims and normal-return boundaries; checked pending consumption and failed admission, queued state versus backend state, stop/retirement, distinct PARTY binding, task registration limits and EE key aliasing.', 'Requested and verified clarification: internal request scans do not themselves establish pointer membership; wrapper lookup is separate.', 'Kept prior original-archive identity as a pinned dependency; no new decompression or audio observation claimed.'],limits=['No live game, audible playback, original-code execution or all-writers census.', 'Only bounded selected native paths; no general allocation, exception, thread, resource lifetime or malformed-list correctness proof.'])
(HERE/'review.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:x for k,x in result.items() if k not in ['pins','manualReview','limits']}))
