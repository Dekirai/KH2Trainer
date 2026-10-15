"""Independent read-only PE/ASM and bounded semantic review; never executes KH2."""
import hashlib,itertools,json,struct,subprocess,sys
from pathlib import Path
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_MEM,X86_OP_IMM,X86_OP_REG,X86_REG_RIP,X86_REG_RAX,X86_REG_RDI,X86_REG_EDI
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
STUDY=ROOT/'artifacts/voice-origin-resources-20261011'
TARGET=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
BASE=0x140000000
ORIGINAL='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
checks=0
def check(value,label):
 global checks
 checks+=1
 if not value:raise AssertionError(label)
def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
raw=TARGET.read_bytes();check(hashlib.sha256(raw).hexdigest()==ORIGINAL,'original EXE identity')
pe=struct.unpack_from('<I',raw,60)[0];check(raw[pe:pe+4]==b'PE\0\0','signature')
opt=pe+24;n=struct.unpack_from('<H',raw,pe+6)[0];z=struct.unpack_from('<H',raw,pe+20)[0]
check(struct.unpack_from('<H',raw,opt)[0]==0x20b,'PE64')
check(struct.unpack_from('<Q',raw,opt+24)[0]==BASE,'image base')
sections=[struct.unpack_from('<III',raw,opt+z+40*i+12) for i in range(n)]
def read(a,size):
 for va,length,ptr in sections:
  if va<=a-BASE and a-BASE+size<=va+length:
   result=raw[ptr+a-BASE-va:ptr+a-BASE-va+size]
   check(len(result)==size,'original read length')
   return result
 raise AssertionError(('not file-backed',hex(a),size))
evidence=load(STUDY/'evidence.json');manifest=load(STUDY/'manifest.json')['files']
check(digest(STUDY/'manifest.json')=='694b3f0499140b05e73c07916fa535fc76198e8dfb6e6711a569d1a0c9f7e6de','reviewed manifest pin')
check(digest(STUDY/'evidence.json')=='55c04c57a068bc36dfd1fe2ebed7fc904719002c9e37184352290594d9aab361','reviewed evidence pin')
check(set(manifest)=={p.name for p in STUDY.iterdir() if p.is_file() and p.name not in ['manifest.json','checkpoint.json']},'manifest covers exact frozen file set')
for name,pin in manifest.items():check(digest(STUDY/name)==pin['sha256'] and (STUDY/name).stat().st_size==pin['bytes'],'manifest '+name)
cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
functions={};instructions={};bodyBytes=0;instructionBytes=0;gaps={}
for f in evidence['functions']:
 a=int(f['addr'],16);b=bytes.fromhex(f['originalBytes'])
 check(a not in functions,'unique body');functions[a]=f
 check(len(b)==f['size'] and read(a,len(b))==b,'body '+f['addr'])
 check(hashlib.sha256(b).hexdigest()==f['sha256'],'body digest')
 bodyBytes+=len(b);covered=set()
 check([r for p in f['pages'] for r in p['asm']['lines']]==f['disassembly']['asm']['lines'],'ASM pagination join')
 check(f['pages'][-1]['cursor']=={'done':True},'ASM final cursor')
 code='\n'.join(p['code'] for p in f['pseudocode']['pages'])
 check(code==f['pseudocode']['code'] and f['pseudocode']['pages'][-1]['cursor']=={'done':True},'pseudocode page join and terminal cursor')
 for row in f['decodedInstructions']:
  pc=int(row['addr'],16);i=next(cs.disasm(read(pc,min(15,a+len(b)-pc)),pc,count=1),None)
  check(i is not None and i.size==row['size'] and i.bytes.hex()==row['bytes'] and (i.mnemonic,i.op_str)==(row['mnemonic'],row['operands']),'independent decode '+row['addr'])
  span=set(range(pc,pc+i.size));check(not span&covered and a<=pc and pc+i.size<=a+len(b),'instruction span')
  check(pc not in instructions,'unique global instruction');instructions[pc]=i;covered|=span;instructionBytes+=i.size
 missing=set(range(a,a+len(b)))-covered
 if missing:gaps[a]=missing
for d in evidence['data']:
 a=int(d['addr'],16);b=bytes.fromhex(d['originalBytes'])
 check(len(b)==d['size'] and read(a,len(b))==b,'data span')
for g in evidence['trailingData']:
 a=int(g['addr'],16);start=int(g['start'],16);end=int(g['end'],16)
 check(gaps.pop(a)==set(range(start,end)) and end-start==g['count'],'explicit data gap')
 check(read(start,end-start).hex()==g['hex'],'gap original bytes')
check(not gaps,'all primary bytes classified')
for x in evidence['positiveXrefs']:
 a=int(x['site'],16);target=int(x['target'],16);i=next(cs.disasm(read(a,15),a,count=1))
 refs=[o.imm if o.type==X86_OP_IMM else a+i.size+o.mem.disp for o in i.operands if o.type==X86_OP_IMM or (o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP)]
 check(target in refs and i.bytes.hex()==x['bytes'],'positive xref encoding')
for pin in load(STUDY/'provenance.json')['files']:
 check(digest(ROOT/pin['path'])==pin['sha256'],'prior provenance '+pin['path'])
anchorCount=0
def anchor(rva,mn,ops):
 global anchorCount
 i=instructions[BASE+rva]
 check((i.mnemonic,i.op_str)==(mn,ops),'semantic anchor '+hex(i.address));anchorCount+=1
anchor(0x12cd0d,'mov','r10, r8');anchor(0x12cd5e,'mov','qword ptr [rcx + 0x60], r10')
anchor(0x129d49,'mov','rcx, qword ptr [rcx + 0x60]');anchor(0x129d52,'call','qword ptr [rip + 0x451a30]')
anchor(0x129d58,'mov','qword ptr [rbx + 0x60], 0')
anchor(0x1360f9,'cmp','dword ptr [rdi + 0x70], 2');anchor(0x1360fd,'je','0x140136113')
anchor(0x1360ff,'mov','rcx, qword ptr [rdi + 0x58]');anchor(0x136108,'call','qword ptr [rip + 0x44567a]')
anchor(0x13610f,'mov','qword ptr [rdi + 0x58], rbx');anchor(0x1360bf,'xor','ebx, ebx')
anchor(0x136098,'cmp','dword ptr [rcx + 0x6c], 0');anchor(0x1360af,'jne','0x1401360a0')
anchor(0x1360cb,'call','0x140078b50');anchor(0x1360e3,'call','0x14007d3f0')
anchor(0x1dfdc5,'mov','rdi, qword ptr [rbx + 0x20]');anchor(0x1dfdc9,'test','rdi, rdi');anchor(0x1dfdcc,'je','0x1401dfde9')
anchor(0x1dfdd2,'mov','dword ptr [rbx + 0xc], edi');anchor(0x1dfdd7,'call','0x1401363b0')
anchor(0x1dfe1f,'mov','r9d, 2');anchor(0x1dfe25,'mov','dword ptr [rsp + 0x20], 2');anchor(0x1dfe2d,'call','0x14013b2e0')
anchor(0x1dfe71,'call','0x1401391d0');anchor(0x1dfe88,'call','0x140139e50')
anchor(0x13c270,'movsxd','rcx, dword ptr [rcx + 0x54]');anchor(0x13c279,'call','qword ptr [rip + 0x43f521]')
anchor(0x13c27f,'mov','qword ptr [rsi + 0x58], rax');anchor(0x13c29d,'call','0x140471a60');anchor(0x13c2e8,'mov','dword ptr [rsi + 0x6c], 0')
anchor(0x09fbf3,'movzx','r14d, word ptr [rbp + 0xe]');anchor(0x09fc97,'mov','qword ptr [rbx + 0x28], rdi')
anchor(0x09fca1,'call','0x14008c1a0');anchor(0x09fca6,'test','byte ptr [rbx + 0x80], 8')
anchor(0x09fcc8,'call','qword ptr [rax + 0x18]');anchor(0x09fccd,'mov','byte ptr [rax + 0xf], 0xff')
anchor(0x09fcd8,'cmp','edi, eax');anchor(0x09fcda,'jl','0x14009fcc0')
anchor(0x09fd34,'cmp','edx, eax');anchor(0x09fd39,'cmovl','r8d, edx');anchor(0x09fd42,'movsxd','rdi, r8d')
anchor(0x09fd9a,'movsxd','rax, dword ptr [rcx + rdi*4]');anchor(0x09fd9e,'add','rax, qword ptr [rbx + 8]')
for vtable,fn in [(0x5aa090,0x129d30),(0x5aa190,0x12d8e0),(0x5ab938,0x136060),(0x61ca00,0x09fbd0),(0x61ca08,0x09fd20)]:
 check(struct.unpack('<Q',read(BASE+vtable,8))[0]==BASE+fn,'concrete virtual cell')
for r in evidence['rtti']:
 col=int(r['locator'],16);td=int(r['typeDescriptor'],16);fields=struct.unpack('<6I',read(col,24))
 check(fields[0]==1 and BASE+fields[3]==td and BASE+fields[5]==col,'RTTI locator linkage')
 check(read(td+16,len(r['name'])+1)==r['name'].encode()+b'\0','RTTI native class name')
modelCases=0
# Derive the initializer's writes from independently decoded instructions,
# without reading the author's asserted offset list or behavioral model.
anchor(0x0889ba,'xor','edi, edi')
anchor(0x0889f9,'lea','rax, [rip + 0x2af8950]')
anchor(0x088a13,'lea','rcx, [rip + 0x2af9136]')
anchor(0x088dd9,'add','rax, 0x400')
anchor(0x088ddf,'cmp','rax, rcx')
anchor(0x088de2,'jl','0x140088a30')
anchor(0x0913a6,'call','0x1400889b0')
def rip_target(rva):
 i=instructions[BASE+rva]
 return i.address+i.size+i.operands[1].mem.disp
start=rip_target(0x0889f9);end=rip_target(0x088a13)
check((start,end)==(BASE+0x2b81350,BASE+0x2b81b50),'initializer loop bounds')
loop=[i for a,i in sorted(instructions.items()) if BASE+0x088a30<=a<BASE+0x088dd9]
stores=[]
for i in loop:
 dst,src=i.operands
 check(i.mnemonic=='mov' and dst.type==X86_OP_MEM and dst.mem.base==X86_REG_RAX and dst.mem.index==0,'initializer loop only selected RAX stores')
 check(src.type==X86_OP_IMM or (src.type==X86_OP_REG and src.reg in [X86_REG_RDI,X86_REG_EDI]),'initializer source immediate or established zero')
 value=src.imm if src.type==X86_OP_IMM else 0
 stores.append((dst.mem.disp,dst.size,value))
check(len(stores)==128,'full unrolled loop captured')
check([(d,size,value) for d,size,value in stores if value]==[(8+32*k,8,104) for k in range(32)],'exact32 node-offset stores per pass')
memory={};pointer=start;passes=0
while True:
 for disp,size,value in stores:
  for n,b in enumerate(value.to_bytes(size,'little')):memory[pointer+disp+n]=b
 pointer+=instructions[BASE+0x088dd9].operands[1].imm;passes+=1
 if pointer>=end:break
 check(passes<3,'bounded initializer loop')
check(passes==2 and pointer==end,'exact two initializer passes')
def mem_value(a,size):return int.from_bytes(bytes(memory[a+n] for n in range(size)),'little')
for k in range(64):
 b=BASE+0x2b81340+32*k
 check(mem_value(b,8)==mem_value(b+8,8)==mem_value(b+16,4)==0,'bucket head tail count initialized')
 check(mem_value(b+24,8)==104,'each bucket node offset104')
 modelCases+=1
anchor(0x08c1e3,'mov','rcx, qword ptr [rdx + 0x18]')
anchor(0x08c1e7,'add','rcx, rbx')
anchor(0x08c1f4,'mov','qword ptr [rcx + 0x10], rdx')
anchor(0x08c1fd,'mov','qword ptr [rcx], rax')
anchor(0x08c202,'mov','qword ptr [rcx + 8], rax')
anchor(0x08c20e,'mov','qword ptr [rcx + rax + 8], rbx')
anchor(0x08c215,'mov','qword ptr [rcx + 8], rax')
anchor(0x08c219,'mov','qword ptr [rcx], rax')
protected=set(range(0,16))|set(range(40,48))|{128}|set(range(152,158))
for offset,hasPrevious in itertools.product([104,0,24],[False,True]):
 current=set(range(offset,offset+24));previous=set(range(offset+8,offset+16)) if hasPrevious else set()
 check(bool((current|previous)&protected)==(offset!=104),'initialized offset preserves protected fields; negative controls fail')
 if offset==104:check(current==set(range(104,128)) and previous<=set(range(112,120)),'exact current and previous object write spans')
 modelCases+=1
before=load(STUDY/'review-amendment-before.json')
check(before['beforeFiles']['manifest.json']=='3a28afb4b4da570c15cb940af54eed02141db92004fdf33b73ba38f613336d74','prior review manifest pin retained')
check(len(before['beforeEvidenceFunctionHashes'])==40,'prior snapshot40 functions')
for a,pin in before['beforeEvidenceFunctionHashes'].items():check(functions[int(a,16)]['sha256']==pin,'unchanged prior body '+a)
check(set(functions)-{int(a,16) for a in before['beforeEvidenceFunctionHashes']}=={BASE+0x0889b0,BASE+0x091250},'only two added bodies')
for pointer in [0,1,0xffffffff,0x100000000,0x10000ffff,0x140123400,0x240123400,0xffffffffffffffff]:
 wrapper=bytearray(48);struct.pack_into('<Q',wrapper,32,pointer);struct.pack_into('<I',wrapper,12,7)
 # Machine MOV EDI to wrapper DWORD, selected after TEST RDI.
 if pointer:wrapper[12:16]=struct.pack('<Q',pointer)[:4]
 key=struct.unpack_from('<I',wrapper,12)[0]
 check(key==(pointer%2**32 if pointer else 7),'non-null payload/low32 key')
 check((pointer!=0 and key==0)==(pointer==0x100000000),'zero key can pass 64-bit pointer gate')
 modelCases+=1
for mode,payload in itertools.product([-1,0,1,2,3,0x7fffffff],[0,1,0x140123400]):
 mem=bytearray(120);struct.pack_into('<I',mem,112,mode&0xffffffff);struct.pack_into('<Q',mem,88,payload)
 # Independent branch trace over the frozen destructor free/clear region.
 pc=BASE+0x1360f9;equal=False;freed=[]
 for step in range(12):
  if pc==BASE+0x136113:break
  i=instructions[pc];nextpc=pc+i.size
  if pc==BASE+0x1360f9:equal=struct.unpack_from('<I',mem,112)[0]==2
  elif i.mnemonic=='je':
   if equal:nextpc=int(i.op_str,16)
  elif pc==BASE+0x1360ff:value=struct.unpack_from('<Q',mem,88)[0]
  elif pc==BASE+0x136103:equal=value==0
  elif pc==BASE+0x136108:freed.append(value)
  elif pc==BASE+0x13610f:struct.pack_into('<Q',mem,88,0)
  else:check(i.mnemonic=='nop','destructor interpreter instruction')
  pc=nextpc
 check(pc==BASE+0x136113,'destructor trace terminates after precondition waits returned')
 check(freed==([payload] if mode!=2 and payload else []),'mode2 never frees payload')
 check(struct.unpack_from('<Q',mem,88)[0]==(payload if mode==2 else 0),'mode2 preserves borrowed pointer field')
 modelCases+=1
for count,index in itertools.product([0,1,2,65535],[-2147483648,-1,0,1,65534,65535,2147483647]):
 edx=index&0xffffffff;signed=int.from_bytes(edx.to_bytes(4,'little'),'little',signed=True)
 chosen=signed if signed<count else 0
 check(chosen==(index if index<count else 0),'signed CMOVL index selection')
 check(index>=0 or chosen<0,'negative index is retained by helper')
 modelCases+=1
for rawOffset in [0,1,0x7fffffff,0x80000000,0xffffffff]:
 value=int.from_bytes(rawOffset.to_bytes(4,'little'),'little',signed=True)
 check(value==(rawOffset if rawOffset<2**31 else rawOffset-2**32),'signed sequence offset')
 modelCases+=1
for kind in range(1,49):
 prep=BASE+struct.unpack('<I',read(BASE+0x3a67fc+4*read(BASE+0x3a680c+kind-1,1)[0],4))[0]
 release=BASE+struct.unpack('<I',read(BASE+0x3a6be8+4*read(BASE+0x3a6c08+kind-1,1)[0],4))[0]
 check((prep==BASE+0x3a6674)==(kind in [31,34,48]),'prepare sound switch membership')
 check((release==BASE+0x3a6b2b)==(kind in [34,48]),'release sound switch membership')
 modelCases+=1
reproduction=subprocess.run([sys.executable,'-B',str(STUDY/'verify.py'),'--check'],cwd=ROOT,capture_output=True,text=True)
check(reproduction.returncode==0,'author reproduction '+reproduction.stderr)
authorResult=json.loads(reproduction.stdout);check(authorResult['status']=='PASS' and not authorResult['gameExecution'],'author verifier result')
claims=load(STUDY/'claims.json');check(len({c['addr'] for c in claims})==len(claims),'unique claimed function addresses')
for c in claims:check(int(c['addr'],16) in functions and c['Limitations'],'claim has selected body and boundary')
result=dict(status='INDEPENDENT_BYTES_AND_SELECTED_SEMANTICS_PASS_REVIEW_PENDING',checks=checks,modelCases=modelCases,ownSemanticAnchors=anchorCount,
 functions=len(functions),instructions=len(instructions),primaryBytes=bodyBytes,instructionBytes=instructionBytes,claims=len(claims),
 sourcePins={p.name:digest(p) for p in STUDY.iterdir() if p.is_file()},reviewScriptSha256=digest(Path(__file__)),authorReproduction=authorResult,
 gameExecution=False,productOrStudyChanged=False,limits='Own PE/Capstone, RTTI, branch and low32 arithmetic checks plus manual claims review. No live binding, resource lease, all-writers, global synchronization or original-code execution proof.')
(HERE/'checks.json').write_text(json.dumps(result,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=True))
