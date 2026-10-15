"""Independent, read-only PE/capture/signature review; writes only this review directory."""
from pathlib import Path
import hashlib,json,re,struct
from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_WRITE
from capstone.x86_const import X86_OP_MEM,X86_OP_IMM,X86_OP_REG,X86_REG_RIP
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
DESIGN=ROOT/'artifacts/audio-observation-design-20261011'
ORIGINAL=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
SHA='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
checks=0
def ck(value,why):
 global checks
 checks+=1
 if not value: raise AssertionError(why)
def sha(data): return hashlib.sha256(data).hexdigest()
def readj(p): return json.loads(p.read_text(encoding='utf-8-sig'))
ck(sha((DESIGN/'manifest.json').read_bytes())=='0fdfdde07ceacb75c6326043959401c5ce4051145d44a2a3355f8d10f88537a6','final portable design manifest')
ck(sha((DESIGN/'capture.json').read_bytes())=='ae5c844019706c50736445126a93f3368c75ce4e3612026846b8286d01925455','capture unchanged from original reviewed design')
ck(sha((DESIGN/'design.txt').read_bytes())=='eff779485158cb93f82eac1d938f24671ba984feed3e18c92dcf3b6884958f8d','design text unchanged from original reviewed design')
for name,pin in readj(DESIGN/'manifest.json')['files'].items():
 b=(DESIGN/name).read_bytes();ck(len(b)==pin['bytes'] and sha(b)==pin['sha256'],name)
raw=ORIGINAL.read_bytes();ck(sha(raw)==SHA,'original SHA256')
pe=struct.unpack_from('<I',raw,60)[0]
ck(raw[pe:pe+4]==b'PE\0\0','PE signature')
nsec=struct.unpack_from('<H',raw,pe+6)[0];optsz=struct.unpack_from('<H',raw,pe+20)[0]
base=struct.unpack_from('<Q',raw,pe+48)[0];ck(base==0x140000000,'image base')
sections=[]
for n in range(nsec):
 off=pe+24+optsz+40*n
 vs,va,sz,ptr=struct.unpack_from('<IIII',raw,off+8)
 sections.append((va,sz,ptr))
def bytes_at(rva,count):
 matches=[ptr+rva-va for va,sz,ptr in sections if va<=rva and rva+count<=va+sz]
 ck(len(matches)==1,f'unique raw mapping {rva:x}')
 return raw[matches[0]:matches[0]+count]
def hexbytes(s): return bytes(int(w,16) for w in s.split())
decoder=Cs(CS_ARCH_X86,CS_MODE_64);decoder.detail=True
capture=readj(DESIGN/'capture.json')
captured={int(b['addr'],16):hexbytes(b['data']) for b in capture['bytes']['result']}
records=[];allins={}
def inspect(addr,data,pages):
 ck(bytes_at(addr-base,len(data))==data,f'original capture {addr:x}')
 decoded=list(decoder.disasm(data,addr))
 ck(sum(i.size for i in decoded)==len(data),'complete instruction decode')
 expected=addr
 for ins in decoded:
  ck(ins.address==expected,'instruction continuity');expected+=ins.size;allins[ins.address]=ins
 rows=[]
 for page in pages:
  ck(page['offset']==len(rows),'page offset')
  rows.extend(page['asm']['lines'])
 ck(pages[-1]['cursor'].get('done') is True,'terminal page')
 ck([int(row['addr'],16) for row in rows]==[i.address for i in decoded],'complete IDA instruction address sequence')
 records.append({'rva':hex(addr-base),'size':len(data),'instructions':len(decoded),'sha256':sha(data)})
for f in capture['disassembly']:
 a=int(f['addr'],16);p=dict(f['asm']);p['offset']=0
 ck(f['size']==len(captured[a]),'fresh declared size');inspect(a,captured[a],[p])
normalized=readj(ROOT/'artifacts/audio-request-implementation-20261011/evidence.json')
ck(len(normalized['functions'])==6,'normalized evidence has exactly six fresh bodies')
for f in normalized['functions']:
 a=int(f['addr'],16);original=next(x for x in capture['disassembly'] if int(x['addr'],16)==a)
 ck(f['disassembly']==original['asm'],'normalized disassembly preserves complete capture')
 ck(bytes.fromhex(f['originalBytes'])==captured[a] and f['size']==len(captured[a]) and f['sha256']==sha(captured[a]),'normalized evidence original bytes and hash')
prior=readj(ROOT/'docs/research/voice-request-lifecycle-20261008/evidence.json')
for f in prior['functions']:
 if int(f['addr'],16)-base in (0x1de230,0x1dd8d0,0x1deb50,0x1dc370):
  inspect(int(f['addr'],16),hexbytes(f['idaBytes']),f['pages'])
ck(len(records)==10,'ten independent PE body checks')
sigtext=(ROOT/'src/KH2Trainer.Bridge/AudioRequestSignatures.h').read_text()
arrays={name:bytes(int(v,16) for v in re.findall(r'0x([0-9a-fA-F]{2})',body)) for name,body in re.findall(r'constexpr BYTE (Body\d+)\[\]=\{(.*?)\};',sigtext,re.S)}
signatures=[]
for rva,name in re.findall(r'\{(0x[0-9a-f]+),(Body\d+),sizeof\(\2\)\}',sigtext):
 rva=int(rva,16);b=arrays[name];ck(bytes_at(rva,len(b))==b,'production signature bytes')
 rec=next(x for x in records if int(x['rva'],16)==rva)
 ck(len(b)==rec['size'],'whole body signature extent')
 signatures.append({'rva':hex(rva),'size':len(b),'sha256':sha(b)})
ck({int(x['rva'],16) for x in signatures}=={0xda30,0x1dd4e0,0x1dd4f0,0x1dd510,0x1dd8d0,0x1ddf10,0x1de230,0x1de7c0},'eight signature targets')
scalars={base+0xad9390:4,base+0xad93c0:1,base+0xad93c4:4}
refs=[]
for i in allins.values():
 for op in i.operands:
  if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
   target=i.address+i.size+op.mem.disp
   if target in scalars:
    ck(op.size==scalars[target],'scalar access width')
    refs.append({'site':hex(i.address-base),'target':hex(target-base),'instruction':i.mnemonic+' '+i.op_str,'width':op.size,'write':bool(op.access&CS_AC_WRITE)})
def ins(rva,mnemonic):
 i=allins[base+rva];ck(i.mnemonic==mnemonic,f'anchor mnemonic {rva:x}');return i
ck(ins(0xdba1,'mov').operands[1].imm==80,'free pool initial capacity')
ck(ins(0xda30,'mov').operands[1].imm==80,'initializer record count')
ck(ins(0xda50,'lea').operands[1].mem.disp==56,'initializer record stride')
# Follow the initializer's SIMD constants to its 320-byte free-index table.
# This confirms actual initial indices, beyond the nearby capacity assignment.
xmm={};index_bytes={}
for a in sorted(allins):
 if not base+0xda30<=a<base+0xdbb0:continue
 i=allins[a]
 if i.mnemonic!='movdqa':continue
 dst,src=i.operands
 if dst.type==X86_OP_REG and src.type==X86_OP_MEM and src.mem.base==X86_REG_RIP:
  xmm[dst.reg]=bytes_at(i.address+i.size+src.mem.disp-base,16)
 elif dst.type==X86_OP_MEM and dst.mem.base==X86_REG_RIP and src.type==X86_OP_REG:
  target=i.address+i.size+dst.mem.disp-base
  for off,value in enumerate(xmm[src.reg]):index_bytes[target+off]=value
ck(sorted(index_bytes)==list(range(0xad9250,0xad9390)),'complete 80 DWORD index table initialization')
indices=struct.unpack('<80i',bytes(index_bytes[r] for r in range(0xad9250,0xad9390)))
ck(indices==tuple(range(80)),'all initialized free indices are exactly 0 through 79')
ck(ins(0x1dd4e0,'mov').operands[1].imm==1,'inhibit enabled')
ck(ins(0x1dd4f0,'mov').operands[1].imm==0,'inhibit disabled')
ins(0x1dda3e,'inc');ins(0x1dda6e,'mov')
# Derive acceptance predicates independently from actual cmp/conditional branch
# instructions before the first counter store, rather than translating Gates().
native=[]
for start,stop in ((0x1dd510,0x1dd533),(0x1ddf10,0x1ddf6b),(0x1de230,0x1de28b)):
 body=[allins[a] for a in sorted(allins) if base+start<=a<base+stop]
 cmps=[i for i in body if i.mnemonic=='cmp']
 branches=[i for i in body if i.mnemonic in ('jne','jle','jg')]
 ck([i.mnemonic for i in branches]==['jne','jle','jg'],'native signed admission branch sequence')
 ck([i.operands[1].imm for i in cmps]==[0,16,24],'native admission comparison constants')
 ck(all(i.operands[0].imm>=base+stop for i in branches),'failure destinations follow admission counter stores')
 native.append((start,[i.operands[1].imm for i in cmps]))
cases=0;maskcoverage=set()
for free in range(81):
 for interval in range(26):
  for inhibit in range(2):
   limitnames=set()
   if inhibit:limitnames.add('inhibit')
   if free<17:limitnames.add('reserve')
   if interval==25:limitnames.add('interval')
   mask=sum({'inhibit':1,'reserve':2,'interval':4}[name] for name in limitnames)
   maskcoverage.add(mask)
   for start,(zero,reserve,cap) in native:
    admitted=(inhibit==zero and free>reserve and interval<=cap)
    ck(admitted==(not limitnames),f'branch trace {start:x}')
   cases+=1
ck(maskcoverage==set(range(8)),'all reason combinations')
out={'status':'PASS_BOUNDED_DESIGN_AND_SIGNATURE_REVIEW','checks':checks,'originalSha256':SHA,'designManifestSha256':sha((DESIGN/'manifest.json').read_bytes()),'bodies':records,'signatures':signatures,'scalarReferences':refs,'branchModelCases':cases,'limits':['Independent Capstone disassembly and branch predicates from the original PE; no native game instructions executed.','Ten selected bodies and positive references do not establish a complete writer or alias census.','Repeated equal samples are not atomic and do not exclude ABA; mask zero predicts only absence of the three sampled native gates, not playback.']}
(HERE/'design-review.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:out[k] for k in ('status','checks','branchModelCases')}))
