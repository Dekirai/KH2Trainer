"""Verify fresh IDA captures, original code, bounded semantic anchors and models."""
import argparse, hashlib, json, random, runpy, struct
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_REG, X86_OP_IMM, X86_OP_MEM

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'src/KH2Trainer.Core').is_dir())
load = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
checks = 0
def check(ok, label):
    global checks
    checks += 1
    if not ok:
        raise AssertionError(label)

original = Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
raw = original.read_bytes()
original_sha = hashlib.sha256(raw).hexdigest()
check(original_sha == '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed', 'original executable identity')
pe = struct.unpack_from('<I', raw, 60)[0]
base = struct.unpack_from('<Q', raw, pe + 48)[0]
count = struct.unpack_from('<H', raw, pe + 6)[0]
opt = struct.unpack_from('<H', raw, pe + 20)[0]
sections = [struct.unpack_from('<4I', raw, pe + 24 + opt + 40*i + 8) for i in range(count)]
def original_bytes(addr, size):
    rva = addr - base
    hits = [(va, rp) for vs, va, rs, rp in sections if va <= rva and rva + size <= va + rs]
    check(len(hits) == 1, ('unique original span', hex(addr), size))
    va, rp = hits[0]
    return raw[rp+rva-va:rp+rva-va+size]

c = load(HERE / 'capture.json')
decoder = Cs(CS_ARCH_X86, CS_MODE_64)
decoder.detail = True
captured = {int(r['addr'], 0): bytes(int(t, 16) for t in r['data'].split()) for r in c['bytes']['result']}
decoded = {}
for addr, blob in captured.items():
    check(blob == original_bytes(addr, len(blob)), ('IDA bytes equal original', hex(addr)))
    ins = list(decoder.disasm(blob, addr))
    check(sum(i.size for i in ins) == len(blob), ('full independent decode', hex(addr)))
    decoded.update({i.address: i for i in ins})

# Prior Voice/Audio work is an explicit dependency, never counted as new discovery.
dependencies = {
    'docs/research/voice-request-lifecycle-20261008': [0x1DEB50, 0x1DD8D0, 0x1DD560, 0x1DE320, 0x1DE500, 0x1DE840, 0x1DDD60, 0x1DC770],
    'docs/research/audio-observation-design-20261011': [0x1DD510, 0x1DE7C0, 0x1DD4F0],
}
dep_pins = {}
dep_bodies = []
dependency_decoded = {}
for name, selected in dependencies.items():
    folder = ROOT / name
    for member in ['manifest.json', 'evidence.json' if (folder/'evidence.json').exists() else 'capture.json']:
        dep_pins[name + '/' + member] = sha(folder/member)
    if (folder/'evidence.json').exists():
        old = load(folder/'evidence.json')
        bodies = {int(f['addr'], 0): bytes.fromhex(f['originalBytes']) for f in old['functions']}
    else:
        old = load(folder/'capture.json')
        bodies = {int(f['addr'], 0): bytes(int(t,16) for t in f['data'].split()) for f in old['bytes']['result']}
    for rva in selected:
        addr = base + rva
        blob = bodies[addr]
        check(blob == original_bytes(addr,len(blob)), ('dependency still original', hex(addr)))
        dep_bodies.append(dict(addr=hex(addr), bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest(), study=name))
        dependency_decoded.update({i.address:i for i in decoder.disasm(blob,addr)})

coverage = runpy.run_path(str(ROOT/'scripts/update-analysis-coverage.py'))
functions = []
normal_bodies = 0
for f in c['functions']:
    addr = int(f['addr'],0)
    asm = f['disassembly']
    check(asm['cursor'].get('done') is True and not asm['cursor'].get('cancelled',False) and not asm['cursor'].get('next'), ('complete captured cursor', f['addr']))
    lines = asm['asm']['lines']
    check(len(lines) == asm['instruction_count'] == asm['total_instructions'], ('complete instruction count', f['addr']))
    chunks = [(addr,captured[addr])]
    if addr == base + 0x1DC5B0:
        chunks.append((base+0x1E0880,captured[base+0x1E0880]))
    addresses = [i.address for a,b in chunks for i in decoder.disasm(b,a)]
    check(addresses == [int(l['addr'],16) for l in lines], ('IDA boundaries across captured chunks', f['addr']))
    row = dict(addr=f['addr'], name=f['name'], size=f['size'], disassembly=asm, pseudocode=f['pseudocode'],
               originalBytes=[dict(addr=hex(a),data=b.hex(' ')) for a,b in chunks],
               primarySha256=hashlib.sha256(chunks[0][1]).hexdigest(),
               sourceCapture='capture.json', previousStudy='docs/research/voice-request-lifecycle-20261008' if addr == base+0x1DC770 else None)
    valid, _, reason = coverage['body_assembly'](row)
    check(valid, ('existing strict ASM metadata parser', f['addr'], reason))
    if len(chunks) == 1:
        check(all(addr <= a < addr+f['size'] for a in addresses), ('contiguous primary extent', f['addr']))
        normal_bodies += 1
    else:
        row['note'] = 'IDA lists a 14-byte primary extent and a disjoint 62-byte shared tail. Complete captured chunks, not a contiguous inventory-sized body; tail separately recorded as a code_range.'
    functions.append(row)

ranges = []
for batch in c['rangeQueries']:
    q = batch['result'][0]
    check(q['cursor'].get('done') is True and not q.get('truncated') and not q.get('error'), 'bounded instruction-range capture complete')
    addr = int(q['ranges'][0]['start'],0)
    end = int(q['ranges'][0]['end'],0)
    blob = captured[addr]
    check(len(blob) == end-addr and [i.address for i in decoder.disasm(blob,addr)] == [int(m['addr'],0) for m in q['matches']], 'range bytes/instruction boundaries')
    ranges.append(dict(addr=hex(addr), end_exclusive=hex(end), originalBytes=blob.hex(' '), sha256=hashlib.sha256(blob).hexdigest(),
                       observed_line_count=q['count'], asm=dict(lines=[dict(addr=m['addr'],instruction=m['disasm']) for m in q['matches']]),
                       note='Bounded code range only; no new function added to IDA. Shared resolver tail.' if addr==base+0x1E0880 else 'Unowned positive-ID gate ending in tail-jump to the allocator; no function identity or active caller inferred.'))

# Independently decoded anchors tie the semantic models to the captured code.
anchors = {
 0x1DDE06:('xor','edx, edx'),0x1DDE10:('lea','r8d, [rdx + 2]'),0x1DDE44:('mov','qword ptr [rdi + 0x18], rbp'),
 0x1DDE9E:('mov','edx, 1'),0x1DDEAB:('lea','r8d, [rdx + 2]'),0x1DDED4:('movsxd','rcx, eax'),
 0x1DE03F:('xor','edx, edx'),0x1DE049:('lea','r8d, [rdx + 4]'),0x1DE07D:('mov','qword ptr [rdi + 0x18], r14'),0x1DE081:('mov','word ptr [rdi + 0x32], bp'),
 0x1DE0DE:('mov','edx, 1'),0x1DE0E8:('mov','r8d, edx'),0x1DE113:('movsxd','rcx, eax'),
 0x1DE17E:('xor','r8d, r8d'),0x1DE189:('lea','edx, [r8 + 1]'),0x1DE1EB:('movsxd','rcx, eax'),0x1DE1C6:('mov','dword ptr [rdi + 0xc], 0x3f800000'),
 0x1DDE53:('mov','byte ptr [rdi + 0x34], 3'),0x1DDEF1:('mov','byte ptr [rdi + 0x34], 3'),
 0x1DE090:('mov','byte ptr [rdi + 0x34], 3'),0x1DE130:('mov','byte ptr [rdi + 0x34], 3'),0x1DE203:('mov','byte ptr [rdi + 0x34], 3'),
 0x1DDC43:('mov','byte ptr [rbx + 0x34], 2'),0x1DC5B9:('jmp','0x1401e0880'),
 0x1E089E:('cmp','r8, 0x1b'),0x1E08B1:('cmp','dword ptr [r10 + rcx*4 + 8], 1'),
 0x1DD500:('test','ecx, ecx'),0x1DD502:('jg','0x1401dd507'),0x1DD507:('jmp','0x1401dd510'),
 0x1DF9F0:('jmp','0x14013a4a0'),0x13A4D0:('or','edx, dword ptr [rcx + 0x6c]'),
}
anchor_receipts = []
for rva,(mnemonic,operands) in anchors.items():
    ins = decoded[base+rva]
    check((ins.mnemonic,ins.op_str)==(mnemonic,operands), ('semantic anchor',hex(base+rva)))
    anchor_receipts.append(dict(addr=hex(base+rva),instruction=ins.mnemonic+' '+ins.op_str))
for rva in [0x1DFFF0,0x1DF4B0,0x1DF440]:
    check(captured[base+rva] == bytes.fromhex('33 c0 c3'), ('zero-return stub',hex(base+rva)))

producer_rows = [dict(rva=0x1DDDE0,kind=2,flag=0,explicit=True),dict(rva=0x1DDE80,kind=3,flag=1,explicit=False),
                 dict(rva=0x1DE010,kind=4,flag=0,explicit=True),dict(rva=0x1DE0C0,kind=1,flag=1,explicit=False),dict(rva=0x1DE150,kind=0,flag=1,explicit=False)]
call_sequences = {}
for f in functions:
    addr=int(f['addr'],0)
    seq=[]
    for ins in decoder.disasm(captured[addr],addr):
        if ins.mnemonic in ('call','jmp') and ins.operands[0].type==X86_OP_IMM:
            target=ins.operands[0].imm
            if not addr<=target<addr+f['size']:seq.append(hex(target))
    call_sequences[f['addr']]=seq
for row in producer_rows:
    addr=base+row['rva'];ins=list(decoder.disasm(captured[addr],addr));seq=call_sequences[hex(addr)]
    check(seq.index('0x1401dd510') < seq.index('0x1401deb50') < seq.index('0x1401dc5b0'), ('allocation/setup/resolver order',hex(addr)))
    check(any(i.mnemonic=='cmp' and i.op_str=='ecx, 1' for i in ins) and any(i.mnemonic=='jl' for i in ins), ('signed input rejection',hex(addr)))
    check(any(i.mnemonic=='mov' and i.op_str=='eax, 0x10624dd3' for i in ins) and any(i.mnemonic=='sar' and i.op_str=='ebx, 6' for i in ins), ('division native constant/shift',hex(addr)))
    check(any(i.mnemonic=='mov' and i.op_str=='eax, dword ptr [rdi + 0x14]' for i in ins), ('handle return retained after state3',hex(addr)))
check(call_sequences['0x1401dd120']==['0x1401df4b0','0x1401de650','0x1401de7c0','0x1401dc8d0'], 'runtime reset sequence')
for addr in ['0x1401dc190','0x1401dc650']:
    seq=call_sequences[addr]
    check(seq[-1]=='0x1401dd8d0' and seq.index('0x1401dd4f0') < seq.index('0x1401de550') < seq.index('0x1401de4a0'), ('clear inhibit/selective cancellation/final full processor',addr))
init=call_sequences['0x1401dc770']
check(init[:4]==['0x1401df4b0','0x1401de7c0','0x1401e00d0','0x1401dc8d0'], 'startup reset prefix')
check(init.count('0x1401df7b0')==2 and init.count('0x1401df9f0')==4 and init.count('0x1401df440')==2, 'two startup loads, each with initial and repeated poll sites')

# Execute ONLY the independently decoded resolver instructions in a tiny Python
# integer machine. Tables are synthetic DWORD arrays; no original/native code runs.
tail = {i.address:i for i in decoder.disasm(captured[base+0x1E0880],base+0x1E0880)}
aliases={n:(r,32) for n,r in [('eax','rax'),('ecx','rcx'),('edx','rdx'),('r8d','r8'),('r9d','r9'),('r10d','r10')]}
def signed(x,bits):
    x &= (1<<bits)-1
    return x-(1<<bits) if x&(1<<(bits-1)) else x
def resolver_trace(table,key):
    regs={'rcx':0x100000,'rdx':key&0xffffffff};memory={0x100000+12*i+4*j:value&0xffffffff for i,row in enumerate(table) for j,value in enumerate(row)}
    def reginfo(name):return aliases.get(name,(name,64))
    def regread(name):
        root,bits=reginfo(name);return regs.get(root,0)&((1<<bits)-1)
    def regwrite(name,value):
        root,bits=reginfo(name);regs[root]=value&((1<<bits)-1)
    def ea(ins,operand):
        m=operand.mem
        return (regread(ins.reg_name(m.base)) if m.base else 0)+(regread(ins.reg_name(m.index))*m.scale if m.index else 0)+m.disp
    def read(ins,o):
        if o.type==X86_OP_REG:return regread(ins.reg_name(o.reg))
        if o.type==X86_OP_IMM:return o.imm
        assert o.type==X86_OP_MEM and o.size==4
        return memory[ea(ins,o)]
    pc=base+0x1E0880;last=(0,0,32);steps=0
    while True:
        ins=tail[pc];steps+=1;assert steps<400
        op=ins.operands;mn=ins.mnemonic;pc+=ins.size
        if mn=='ret':return signed(regread('eax'),32),steps
        if mn=='nop':continue
        if mn in ('je','jne','jl'):
            a,b,bits=last
            take=(a==b if mn=='je' else a!=b if mn=='jne' else signed(a,bits)<signed(b,bits))
            if take:pc=op[0].imm
            continue
        if mn=='cmp':last=(read(ins,op[0]),read(ins,op[1]),op[0].size*8);continue
        assert op[0].type==X86_OP_REG
        name=ins.reg_name(op[0].reg)
        if mn=='xor':value=read(ins,op[0])^read(ins,op[1])
        elif mn=='mov':value=read(ins,op[1])
        elif mn=='movsxd':value=signed(read(ins,op[1]),op[1].size*8)
        elif mn=='lea':value=ea(ins,op[1])
        elif mn=='inc':value=read(ins,op[0])+1
        elif mn=='add':value=read(ins,op[0])+read(ins,op[1])
        else:raise AssertionError(('unmodeled native instruction',mn))
        regwrite(name,value)

resolver_cases=0;resolver_steps=0
for match in range(27):
    for state in [0,1,2,3,0xffffffff]:
        for bank in [-2,-1,0,1,0x7fffffff]:
            table=[[i+50,-1000-i,1] for i in range(27)];table[match]=[bank,123,state]
            answer,steps=resolver_trace(table,123)
            check(answer==(bank if state==1 else -1),'decoded resolver exact match/state/bank')
            resolver_cases+=1;resolver_steps+=steps
for first_state in [0,1,2,0xffffffff]:
    for second_state in [0,1,2]:
        table=[[i+50,-1000-i,1] for i in range(27)];table[3]=[71,123,first_state];table[22]=[72,123,second_state]
        answer,steps=resolver_trace(table,123)
        check(answer==(71 if first_state==1 else -1),'first duplicate match stops search, including not-ready first entry')
        resolver_cases+=1;resolver_steps+=steps
for key in [-1,0,1,123,2147483]:
    answer,steps=resolver_trace([[i+50,-1000-i,1] for i in range(27)],key)
    check(answer==-1,'absent key rejected after bounded full table')
    resolver_cases+=1;resolver_steps+=steps

rng=random.Random(20261011)
ids=[-0x80000000,-1001,-1000,-999,-1,0,1,999,1000,1001,0x7fffffff]+[rng.randrange(-0x80000000,0x80000000) for _ in range(10000)]
for value in ids:
    high=signed((signed(value,32)*0x10624dd3)>>32,32)
    shifted=high>>6
    quotient=shifted+((shifted&0xffffffff)>>31)
    expected=abs(value)//1000*(1 if value>=0 else -1)
    check(quotient==expected and value-quotient*1000==value-expected*1000,'native magic division/remainder agrees with truncating division')

# Constructor branch/store anchors complement the decoded resolver test. No
# constructor/backend execution or synthetic self-assertion loop is counted.
for rva, register in [(0x1DDE4D,'rbp'),(0x1DDEEB,'rcx'),(0x1DE08A,'r14'),(0x1DE12A,'rcx'),(0x1DE1FD,'rcx')]:
    ins=decoded[base+rva]
    check(ins.mnemonic=='cmp' and ins.op_str==register+', -1',('exact chosen-bank sentinel comparison',hex(base+rva)))
for rva in [0x1DC8D0,0x1DF1A0]:
    for ins in decoder.disasm(captured[base+rva],base+rva):
        for operand in ins.operands:
            if operand.type==X86_OP_MEM and ins.reg_name(operand.mem.base)=='rip':
                check(ins.address+ins.size+operand.mem.disp != base+0xAD9390,('no direct FreeCount reference in captured reset helper',hex(ins.address)))
report=load(HERE/'report.json')
function_addresses={f['addr'] for f in functions};range_addresses={r['addr'] for r in ranges}
for row in report['claims']:
    addr=row['addr'];kind='functions' if addr in function_addresses else 'code_ranges'
    check(addr in function_addresses or addr in range_addresses,('claim has freshly captured body/range',addr))
    check(row['Evidence'][0]==f'evidence.json#{kind}[addr={addr}]',('strict parser compatible claim evidence',addr))

for batch in c['xrefs']:
    for row in batch['result']:
        check(row.get('more') is False and len(row.get('xrefs',[]))==row['xref_count'], 'complete recorded positive xrefs')
evidence=dict(schema=1,Domain='native',originalSha256=original_sha,imageBase=hex(base),functions=functions,code_ranges=ranges,
              dependencies=dep_bodies,sourceCaptureSha256=sha(HERE/'capture.json'))
result=dict(success=True,status='BOUNDED_STATIC_STUDY_VERIFIED',checks=checks,originalSha256=original_sha,
            capturedFunctions=len(functions),contiguousFunctions=normal_bodies,disjointChunkFunctions=1,
            recapturedDependencyFunctions=['0x1401dc770'],newToSelectedDependencySetFunctions=len(functions)-1,
            uniqueInstructions=len(decoded),uniqueOriginalBytes=sum(len(b) for b in captured.values()),primaryFunctionBytes=sum(f['size'] for f in functions),
            separateCodeRanges=len(ranges),semanticAnchors=anchor_receipts,callSequences=call_sequences,
            models=dict(decodedResolverCases=resolver_cases,decodedResolverSteps=resolver_steps,signedDivisionCases=len(ids)),
            dependencyPins=dep_pins,reportSha256=sha(HERE/'report.json'),captureSha256=sha(HERE/'capture.json'),scriptSha256=sha(Path(__file__)),
            limitations=['Original instructions decoded and selected resolver instructions interpreted over synthetic integers only; no native code, game or backend executed.',
                        'Recorded positive xrefs are bounded observations; auto_analysis_ready=false and negative xrefs do not exclude indirect callers or aliases.',
                        'One prior Voice function was freshly recaptured for ordering context and is not counted as a new discovery.',
                        'The 1DC5B0 primary extent is disjoint from its shared tail; no contiguous full-function or new tail-function claim.',
                        'The decoded resolver and arithmetic models have explicit limited scope; they are not constructor/backend execution, concurrency, resource lifetime, success or audible-output proofs.'])
args=argparse.ArgumentParser();args.add_argument('--check',action='store_true');checking=args.parse_args().check
for name,value in [('evidence.json',evidence),('verification.json',result)]:
    blob=(json.dumps(value,indent=2)+'\n').encode();p=HERE/name
    if checking:check(p.read_bytes()==blob,('reproducible output',name))
    else:p.write_bytes(blob)
print(json.dumps({k:result[k] for k in ['success','checks','capturedFunctions','contiguousFunctions','uniqueInstructions','uniqueOriginalBytes','models']}))
