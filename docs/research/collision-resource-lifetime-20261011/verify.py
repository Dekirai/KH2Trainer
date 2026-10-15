"""Verify complete captured bodies and selected resource-binding instructions offline."""
import copy, hashlib, json, struct, sys
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86_const import X86_OP_REG, X86_OP_IMM, X86_OP_MEM

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p/'src/KH2Trainer.Core').is_dir())
EXE = Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
EXPECTED = '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
load = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
digest = lambda b: hashlib.sha256(b).hexdigest()
checks = 0
def need(condition, label):
    global checks
    checks += 1
    if not condition: raise AssertionError(label)
def encode(value): return (json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode('utf-8')

blob = EXE.read_bytes()
need(digest(blob)==EXPECTED, 'original executable identity')
pe = struct.unpack_from('<I',blob,60)[0]
need(blob[pe:pe+4]==b'PE\0\0', 'PE')
n, optional_size = struct.unpack_from('<H',blob,pe+6)[0], struct.unpack_from('<H',blob,pe+20)[0]
base = struct.unpack_from('<Q',blob,pe+24+24)[0]
sections = [struct.unpack_from('<8sIIII',blob,pe+24+optional_size+i*40) for i in range(n)]
def original(addr,size):
    rva=addr-base
    for _,virtual_size,start,raw_size,offset in sections:
        if start<=rva and rva+size<=start+raw_size:
            return blob[offset+rva-start:offset+rva-start+size]
    raise AssertionError(('unmapped original bytes',hex(addr),size))

cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
functions=[];decoded={};source_pins={}
for name in ['capture.json','capture-2.json','capture-3.json']:
    path=HERE/name;source_pins[name]=digest(path.read_bytes())
    for saved in load(path)['functions']:
        f=copy.deepcopy(saved);addr=int(f['addr'],16);size=f['size']
        data=bytes(int(v,16) for v in f['idaBytes'].split())
        need(data==original(addr,size) and len(data)==size,('original function',f['addr']))
        pages=f['pages'];dis=f['disassembly'];rows=dis['asm']['lines']
        need(dis['cursor'].get('done') and dis['instruction_count']==dis['total_instructions']==len(rows),('ASM complete',f['addr']))
        need(rows==[row for page in pages for row in page['asm']['lines']], 'ASM concatenation')
        offset=0
        for page in pages:
            need(page['instruction_count']==len(page['asm']['lines']), 'ASM page length')
            offset+=page['instruction_count']
            need(page['cursor'].get('done') or page['cursor'].get('next')==offset,'ASM page cursor')
        need(pages[-1]['cursor'].get('done'), 'terminal ASM cursor')
        dp=f['decompilePages'];count=0
        for page in dp:
            count+=page['line_count']
            need(page['cursor'].get('done') or page['cursor'].get('next')==count,'decompiler page cursor')
        need(dp[-1]['cursor'].get('done') and count==dp[0]['total_lines'],'complete pseudocode line inventory')
        need(f['pseudocode']=='\n'.join(p['code'] for p in dp),'pseudocode concatenation')
        ins=list(cs.disasm(data,addr))
        need(sum(i.size for i in ins)==size,'contiguous decoded body bytes')
        need([i.address for i in ins]==[int(r['addr'],16) for r in rows],('original disassembly boundaries',f['addr']))
        need(addr not in {int(v['addr'],16) for v in functions},'unique body')
        decoded.update({i.address:i for i in ins})
        f['originalBytes']=data.hex(' ');f['sha256']=digest(data)
        f['decompile']={'code':f['pseudocode'],'line_count':count,'total_lines':count,'cursor':{'done':True}}
        f['instructions']=[{'addr':hex(i.address),'size':i.size,'bytes':i.bytes.hex(),'mnemonic':i.mnemonic,'operands':i.op_str} for i in ins]
        functions.append(f)

# Execute only the decoded straight-line header-binding slice in a small Python
# instruction model. Memory is synthetic, checked and separate from the game.
start,end=0x14017236a,0x140172428
program=[decoded[a] for a in sorted(decoded) if start<=a<end]
need(program[0].address==start and program[-1].address+program[-1].size==end,'binding slice boundaries')
u64=lambda x:x&((1<<64)-1)
s32=lambda x: x-(1<<32) if x&(1<<31) else x
def execute(header):
    memory={0x100000+i:b for i,b in enumerate(header)}
    memory.update({0x200000+i:0 for i in range(248)})
    registers={'rbx':0x100000,'rdi':0x200000}
    def register(op):
        name=cs.reg_name(op.reg)
        alias={'eax':'rax','ebx':'rbx','ecx':'rcx','edx':'rdx','edi':'rdi','esi':'rsi'}
        return alias.get(name,name[:-1] if name.startswith('r') and name.endswith('d') else name)
    def address(op):
        need(op.mem.index==0 and op.mem.segment==0,'slice simple memory addressing')
        return u64(registers[cs.reg_name(op.mem.base)]+op.mem.disp)
    def value(op):
        if op.type==X86_OP_IMM:return op.imm & ((1<<(op.size*8))-1)
        if op.type==X86_OP_REG:return registers.get(register(op),0)&((1<<(op.size*8))-1)
        if op.type==X86_OP_MEM:
            a=address(op);need(all(a+i in memory for i in range(op.size)),'bounded synthetic read')
            return int.from_bytes(bytes(memory[a+i] for i in range(op.size)),'little')
        raise AssertionError('operand')
    def write(op,v):
        v&=(1<<(op.size*8))-1
        if op.type==X86_OP_REG:registers[register(op)]=v
        else:
            a=address(op);need(all(a+i in memory for i in range(op.size)),'bounded synthetic write')
            for i,b in enumerate(v.to_bytes(op.size,'little')):memory[a+i]=b
    for i in program:
        ops=i.operands
        if i.mnemonic in ('mov','movabs'):write(ops[0],value(ops[1]))
        elif i.mnemonic=='movsxd':write(ops[0],s32(value(ops[1])))
        elif i.mnemonic=='add':write(ops[0],value(ops[0])+value(ops[1]))
        elif i.mnemonic=='shr':write(ops[0],value(ops[0])>>(value(ops[1])&63))
        elif i.mnemonic=='mul':
            result=registers['rax']*value(ops[0]);registers['rax']=u64(result);registers['rdx']=u64(result>>64)
        else:raise AssertionError(('unmodeled instruction',hex(i.address),i.mnemonic))
    return bytes(memory[0x200000+i] for i in range(248))

bindings=[(24,28,8,64,32),(32,36,16,68,20),(40,44,24,72,16),
          (48,52,32,76,16),(56,60,48,84,16),(64,68,56,88,12),(72,76,40,80,4)]
values=[0,1,3,4,11,12,15,16,19,20,31,32,0x7fffffff,0x80000000,0xffffffff]
cases=[]
for number,raw in enumerate(values):
    header=bytearray(80)
    for index,(off,length,_,_,stride) in enumerate(bindings):
        struct.pack_into('<I',header,off,values[(number+index)%len(values)])
        struct.pack_into('<I',header,length,raw)
    result=execute(header)
    need(struct.unpack_from('<Q',result)[0]==0x100000,'borrowed resource pointer')
    row=[]
    for off,length,pointer,count,stride in bindings:
        stored_offset=struct.unpack_from('<I',header,off)[0]
        expected_pointer=u64(0x100000+s32(stored_offset))
        expected_count=(u64(s32(raw))//stride)&0xffffffff
        need(struct.unpack_from('<Q',result,pointer)[0]==expected_pointer,'signed relative offset')
        need(struct.unpack_from('<I',result,count)[0]==expected_count,'native length conversion/count narrowing')
        row.append({'contextPointerOffset':pointer,'count':expected_count})
    cases.append({'rawLength':raw,'counts':row})

# A small contract model for writes established by 17242b..172496. This is not
# native execution and does not cover the constructor's matrix helpers.
def initialize_leaf_flags(shared_leaves,mask):
    for leaf in shared_leaves:leaf[0]=0
    for group in range(64):
        if mask&(1<<group):
            for leaf in shared_leaves:
                if leaf[1]==group:leaf[0]=1
leaves=[[99,g] for g in [0,1,31,32,63,64,255]]
initialize_leaf_flags(leaves,0xffffffff)
need([v[0] for v in leaves]==[1,1,1,0,0,0,0],'scene mask only enables lower32 group IDs')
initialize_leaf_flags(leaves,0xffffffffffffffff)
need([v[0] for v in leaves]==[1,1,1,1,1,0,0],'all64 mask still rejects IDs outside0..63')
first_context=leaves;second_context=leaves
initialize_leaf_flags(first_context,1);initialize_leaf_flags(second_context,2)
need(first_context is second_context and [v[0] for v in first_context]==[0,1,0,0,0,0,0],'two wrappers can share overwritten activation bytes')
initialize_leaf_flags(leaves,0)
need(all(v[0]==0 for v in leaves),'zero mask clears previous flags')

evidence={'schema':1,'Domain':'native','originalSha256':EXPECTED,'imageBase':hex(base),'functions':functions}
report={'status':'PASS','checks':checks,'completeBodies':len(functions),
        'originalBytes':sum(f['size'] for f in functions),
        'instructions':sum(len(f['instructions']) for f in functions),
        'sourcePins':source_pins,'modeledBindingCases':len(cases),'bindingResults':cases,
        'leafModelCases':4,'originalGameExecuted':False,
        'scope':'Original PE/ASM/decompiler-page verification, 15 synthetic original-instruction binding cases and four limited activation models. No complete geometry, lifetime, allocator, synchronization or gameplay proof.'}
for name,value in [('evidence.json',evidence),('verification.json',report)]:
    data=encode(value);path=HERE/name
    if '--check' in sys.argv:need(path.read_bytes()==data,('reproducible output',name))
    else:path.write_bytes(data)
print(json.dumps({k:v for k,v in report.items() if k not in ('bindingResults','sourcePins')},ensure_ascii=False))
