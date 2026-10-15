"""Offline verification of fresh selected IDA bodies against the original KH2 PE.
No game calls, process access, IDB mutation or writes outside this study.
--check reproduces and compares all generated artifacts without writing.
"""
import argparse, copy, hashlib, json, struct
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_IMM, X86_REG_RIP, X86_REG_RAX
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'src/KH2Trainer.Core').exists())
TARGET=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
SHA='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
def digest(b): return hashlib.sha256(b).hexdigest()
def encoded(x): return (json.dumps(x,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
def load(p): return json.loads(p.read_bytes())
def num(s): return int(s,16) if isinstance(s,str) else s
def octets(s): return bytes(int(b,16) for b in s.split())
class PE:
 def __init__(self,path):
  self.raw=path.read_bytes();assert digest(self.raw)==SHA
  p=struct.unpack_from('<I',self.raw,0x3c)[0];assert self.raw[p:p+4]==b'PE\0\0'
  n=struct.unpack_from('<H',self.raw,p+6)[0];z=struct.unpack_from('<H',self.raw,p+20)[0]
  self.opt=p+24;assert struct.unpack_from('<H',self.raw,self.opt)[0]==0x20b
  self.base=struct.unpack_from('<Q',self.raw,self.opt+24)[0];self.sections=[]
  for i in range(n):
   s=self.opt+z+i*40;vs,va,rs,rp=struct.unpack_from('<IIII',self.raw,s+8)
   self.sections.append((va,vs,rs,rp))
 def read(self,a,n):
  r=a-self.base
  for va,vs,rs,rp in self.sections:
   if va<=r and r+n<=va+rs:return self.raw[rp+r-va:rp+r-va+n]
  raise AssertionError(('not fully PE-backed',hex(a),n))
 def q(self,a):return struct.unpack('<Q',self.read(a,8))[0]
 def d(self,a):return struct.unpack('<I',self.read(a,4))[0]
 def cstr(self,a):
  value=bytearray()
  for j in range(1000):
   b=self.read(a+j,1)[0]
   if not b:return value.decode('ascii')
   value.append(b)
  raise AssertionError('unterminated PE string')
 def imports(self):
  rva,size=struct.unpack_from('<II',self.raw,self.opt+120);result={};offset=0
  while True:
   fields=struct.unpack('<5I',self.read(self.base+rva+offset,20));offset+=20
   if not any(fields):break
   oft,_,_,name,iat=fields;dll=self.cstr(self.base+name);index=0
   while True:
    value=self.q(self.base+(oft or iat)+8*index)
    if not value:break
    symbol='#'+str(value&0xffff) if value>>63 else self.cstr(self.base+value+2)
    result[self.base+iat+8*index]=(dll,symbol);index+=1
  return result

def build():
 pe=PE(TARGET);cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
 functions=[];data=[];instructions={};listing=[];gaps=[]
 aliases={'retn':'ret','jz':'je','jnz':'jne','jnb':'jae','jbe':'jbe','cmovz':'cmove','cmovnz':'cmovne','setz':'sete','setnz':'setne','setnb':'setae','sal':'shl'}
 for filename in ('capture.json','additional-capture.json','bucket-offset-capture.json'):
  cap=load(HERE/filename);assert cap['Domain']=='native' and cap['originalSha256']==SHA and num(cap['imageBase'])==pe.base
  for f0 in cap['functions']:
   f=copy.deepcopy(f0);a=num(f['addr']);raw=pe.read(a,f['size']);assert raw==octets(f['idaBytes'])
   d=f['disassembly'];rows=d['asm']['lines'];assert num(d['addr'])==num(d['asm']['start_ea'])==a
   assert d['instruction_count']==d['total_instructions']==len(rows)>0 and d['cursor']=={'done':True}
   offset=0;allrows=[]
   for idx,p in enumerate(f['pages']):
    assert p['offset']==offset and num(p['addr'])==num(p['asm']['start_ea'])==a
    assert not p.get('truncated') and not p['cursor'].get('cancelled')
    assert p['total_instructions']==len(rows) and p['instruction_count']==len(p['asm']['lines'])
    offset+=p['instruction_count'];allrows+=p['asm']['lines']
    assert p['cursor']==({'done':True} if idx==len(f['pages'])-1 else {'next':offset})
   assert allrows==rows
   count=0
   for idx,p in enumerate(f['pseudocode']['pages']):
    assert p['offset']==count and p['line_count']==len(p['code'].splitlines())
    count+=p['line_count'];assert not p['cursor'].get('cancelled')
    assert p['cursor']==({'done':True} if idx==len(f['pseudocode']['pages'])-1 else {'next':count})
   assert count==p['total_lines'] and f['pseudocode']['cursor']=={'done':True}
   covered=set();decoded=[];pcs=[num(r['addr']) for r in rows];assert pcs==sorted(set(pcs)) and pcs[0]==a
   listing.append('\n'+f['addr']+' '+f['name'])
   for row in rows:
    pc=num(row['addr']);assert a<=pc<a+len(raw)
    ins=next(cs.disasm(raw[pc-a:pc-a+15],pc,count=1),None);assert ins
    span=set(range(pc-a,pc-a+ins.size));assert not span&covered and max(span)<len(raw);covered|=span
    mn=row['instruction'].split()[0].lower()
    assert mn==ins.mnemonic or aliases.get(mn)==ins.mnemonic or (mn=='mov' and ins.mnemonic=='movabs') or (mn=='xchg' and ins.bytes==b'\x66\x90' and ins.mnemonic=='nop'),(hex(pc),mn,ins.mnemonic)
    assert pc not in instructions;instructions[pc]=ins
    decoded.append(dict(addr=hex(pc),bytes=ins.bytes.hex(),size=ins.size,mnemonic=ins.mnemonic,operands=ins.op_str))
    listing.append(f'{pc:016x} {ins.bytes.hex():<30} {ins.mnemonic} {ins.op_str}')
   uncovered=sorted(set(range(len(raw)))-covered)
   if uncovered:gaps.append(dict(addr=hex(a),start=hex(a+uncovered[0]),end=hex(a+uncovered[-1]+1),count=len(uncovered),hex=raw[uncovered[0]:uncovered[-1]+1].hex()))
   f.update(originalBytes=raw.hex(' '),sha256=digest(raw),decodedInstructions=decoded,sourceCapture=filename)
   functions.append(f)
 for filename in ('data-capture.json','additional-data.json'):
  cap=load(HERE/filename)
  for d in cap['data']:
   raw=pe.read(num(d['addr']),d['size']);assert raw==octets(d['idaBytes'])
   data.append(dict(**d,originalBytes=raw.hex(' '),sha256=digest(raw)))
 return pe,functions,data,instructions,'\n'.join(listing)+'\n',gaps

def verify_derived():
 import model
 pe,functions,data,instructions,listing,gaps=build()
 expected=[(0x1403a64f0,0x1403a67fa,0x1403a683c),(0x1403a6a10,0x1403a6be6,0x1403a6c38),(0x140078be0,0x140078d10,0x140078d11),(0x140078810,0x14007889c,0x14007889d),(0x140089390,0x1400896ed,0x1400896ee)]
 assert len(gaps)==len(expected)
 for gap,(fn,a,b) in zip(gaps,expected):
  assert (num(gap['addr']),num(gap['start']),num(gap['end']),gap['count'])==(fn,a,b,b-a)
  if b-a==1:assert pe.read(a,1)==b'\xcc'
  else:assert pe.read(a,2)==b'\x66\x90'
 # Both switch trailers are raw data after RET, not omitted executable pages.
 switches=[]
 for fn,table,selector,count,default,special in (
  (0x1403a64f0,0x1403a67fc,0x1403a680c,4,0x1403a6790,{1:0x1403a6610,17:0x1403a6610,20:0x1403a6610,30:0x1403a6610,46:0x1403a6610,4:0x1403a661d,31:0x1403a6674,34:0x1403a6674,48:0x1403a6674}),
  (0x1403a6a10,0x1403a6be8,0x1403a6c08,8,0x1403a6b57,{1:0x1403a6ae5,17:0x1403a6ae5,20:0x1403a6ae5,30:0x1403a6ae5,46:0x1403a6ae5,4:0x1403a6af2,7:0x1403a6b03,18:0x1403a6b0d,24:0x1403a6b17,29:0x1403a6b21,34:0x1403a6b2b,48:0x1403a6b2b})):
  targets=[pe.base+pe.d(table+4*i) for i in range(count)];indices=pe.read(selector,48)
  assert all(x in instructions for x in targets) and max(indices)<count
  cases=[]
  for kind,index in enumerate(indices,1):
   actual=targets[index];assert actual==special.get(kind,default)
   cases.append(dict(kind=kind,target=hex(actual)))
  switches.append(dict(function=hex(fn),table=hex(table),selector=hex(selector),cases=cases))
 for anchor in load(HERE/'anchors.json'):
  i=instructions[num(anchor['addr'])]
  assert (i.bytes.hex(),i.mnemonic,i.op_str)==(anchor['bytes'],anchor['mnemonic'],anchor['operands'])
 # Independent review amendment: derive all64 concrete bucket offsets from ASM.
 start_ins=instructions[0x1400889f9];end_ins=instructions[0x140088a13]
 assert start_ins.mnemonic==end_ins.mnemonic=='lea'
 assert start_ins.operands[1].type==end_ins.operands[1].type==X86_OP_MEM
 assert start_ins.operands[1].mem.base==end_ins.operands[1].mem.base==X86_REG_RIP
 start=start_ins.address+start_ins.size+start_ins.operands[1].mem.disp
 end=end_ins.address+end_ins.size+end_ins.operands[1].mem.disp
 assert (start,end)==(0x142b81350,0x142b81b50)
 writes=[]
 for a,i in sorted(instructions.items()):
  if not 0x140088a30<=a<0x140088dd9 or i.mnemonic!='mov' or len(i.operands)!=2:continue
  dst,src=i.operands
  if dst.type==X86_OP_MEM and src.type==X86_OP_IMM:
   assert dst.size==8 and dst.mem.base==X86_REG_RAX and not dst.mem.index and src.imm==104
   writes.append(dict(site=hex(a),displacement=dst.mem.disp,value=src.imm,bytes=i.bytes.hex()))
 assert [w['displacement'] for w in writes]==[8+32*n for n in range(32)]
 assert instructions[0x140088dd9].mnemonic=='add' and instructions[0x140088dd9].op_str=='rax, 0x400'
 assert instructions[0x140088ddf].op_str=='rax, rcx' and instructions[0x140088de2].mnemonic=='jl' and instructions[0x140088de2].operands[0].imm==0x140088a30
 assigned={};cursor=start
 while cursor<end:
  for w in writes:assigned[cursor+w['displacement']]=w['value']
  cursor+=1024
 assert cursor==end and assigned=={0x142b81340+32*n+24:104 for n in range(64)}
 assert instructions[0x1400913a6].mnemonic=='call' and instructions[0x1400913a6].operands[0].imm==0x1400889b0
 protected=set(range(0,16))|set(range(40,48))|{128}|set(range(152,154))
 assert not set(range(104,128))&protected
 amendment_before=load(HERE/'review-amendment-before.json')
 current_hashes={f['addr']:f['sha256'] for f in functions}
 assert all(current_hashes[a]==h for a,h in amendment_before['beforeEvidenceFunctionHashes'].items())
 assert set(current_hashes)-set(amendment_before['beforeEvidenceFunctionHashes'])=={'0x1400889b0','0x140091250'}
 bucket_proof=dict(initializer='0x1400889b0',caller='0x140091250',loopStartPointer=hex(start),loopEndPointer=hex(end),unrolledStores=writes,bucketCount=len(assigned),bucketStride=32,nodeOffset=104,bankWriteSpan=dict(start=104,end_exclusive=128),previousValidBankWriteSpan=dict(start=112,end_exclusive=120),protectedFields=[0,8,40,128,152],conditions=['0889B0 completed before the selected insertion','Selected bucket+24 still equals104','Current/previous bank objects and bucket storage are intact and nonoverlapping','No intervening or concurrent writer changes the relevant bank fields or list metadata'],limitations='Initializer evidence does not establish an all-writers exclusion or universal runtime preservation. Offset0 or24 would invalidate the payload/alternate-storage preservation premise; explicit negative model controls retain this distinction.')
 # Resolve concrete destructor and ActualBank initialization/accessor slots.
 for a,v in ((0x1405aa090,0x140129d30),(0x1405aa190,0x14012d8e0),(0x1405ab938,0x140136060),(0x14061ca00,0x14009fbd0),(0x14061ca08,0x14009fd20)):
  assert pe.q(a)==v
 rtti=[]
 for col,typ,name in ((0x14066af30,0x78fb48,b'.?AUReplaceEntry@Axa@@'),(0x14066b028,0x78fbb0,b'.?AUResourceEntry@Axa@@'),(0x14066c2a8,0x7909f0,b'.?AUBankEntry@Axa@@'),(0x140688e48,0x79b5c0,b'.?AVActualBank@Driver@Sd@Engine@CDev@SQEX@@')):
  fields=struct.unpack('<6I',pe.read(col,24));assert fields[0]==1 and fields[3]==typ and fields[5]==col-pe.base
  raw=pe.read(pe.base+typ+16,len(name)+1);assert raw==name+b'\0'
  rtti.append(dict(locator=hex(col),typeDescriptor=hex(pe.base+typ),name=name.decode(),originalBytes=raw.hex()))
 positive=[];cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
 for target in load(HERE/'data-capture.json')['xrefs']['result']:
  to=num(target['addr'])
  for x in target.get('xrefs',[]):
   if x.get('fn') is None:continue
   a=num(x['addr']);i=next(cs.disasm(pe.read(a,15),a,count=1))
   refs=[]
   for op in i.operands:
    if op.type==X86_OP_IMM:refs.append(op.imm)
    elif op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:refs.append(a+i.size+op.mem.disp)
   assert to in refs,(hex(a),hex(to),i.mnemonic,i.op_str)
   positive.append(dict(site=hex(a),target=hex(to),bytes=i.bytes.hex(),mnemonic=i.mnemonic,operands=i.op_str))
 claims=load(HERE/'claims.json');addresses={num(f['addr']) for f in functions}
 for c in claims:
  assert num(c['addr']) in addresses and c['Limitations'] and c['Finding']
  assert isinstance(c['Evidence'],list)
  for ref in c['Evidence']:
   if ref.startswith('evidence.json#functions[addr='):assert num(ref.split('=',1)[1][:-1]) in addresses
   else:assert ref=='verification.json'
 pins=load(HERE/'provenance.json')
 for pin in pins['files']:assert digest((ROOT/pin['path']).read_bytes())==pin['sha256']
 imports=pe.imports();selected_imports=[]
 for a,name in ((0x14057b788,'_aligned_free'),(0x14057b7a0,'_aligned_malloc'),(0x14057ba68,'fwrite'),(0x14057ba88,'fopen'),(0x14057bab0,'strncpy')):
  dll,actual=imports[a];assert actual==name
  selected_imports.append(dict(iat=hex(a),dll=dll,name=name))
 result=model.run()
 counts=dict(functions=len(functions),instructions=len(instructions),primaryBytes=sum(f['size'] for f in functions),instructionBytes=sum(i.size for i in instructions.values()),trailingDataAndPaddingBytes=sum(g['count'] for g in gaps),dataSpans=len(data),semanticAnchors=len(load(HERE/'anchors.json')),positiveXrefs=len(positive),claims=len(claims),distinctClaimAddresses=len({num(c['addr']) for c in claims}),switchCases=sum(len(s['cases']) for s in switches),modelCases=result['cases'],rttiTypes=len(rtti),verifiedBucketOffsets=len(assigned))
 evidence=dict(schema=1,Domain='native',originalSha256=SHA,imageBase=hex(pe.base),functions=functions,data=data,switches=switches,trailingData=gaps,semanticAnchors=load(HERE/'anchors.json'),positiveXrefs=positive,rtti=rtti,imports=selected_imports,limits='Fresh selected complete IDA bodies, original PE bytes and branch models. No native game execution. Auto-analysis readiness was false; returned xrefs are positive evidence only. No all-writers/lifetime/concurrency/audio-output guarantee.')
 report=dict(title='ORIGIN Voice resources: producers, borrowed payload and retirement',Domain='native',date='2026-10-11',status='BOUNDED_STATIC_STUDY_PENDING_INDEPENDENT_REVIEW',counts=counts,claims=claims,originalSha256=SHA,nextTargets=['Resolve actual SoundDriver bank destruction and upper/lower bank references through078B50 virtual slot+56 and09D460.','Close teardown order between Actor Voice, resource callbacks, requests and ResourceEntry retirement.','Identify original type34 BAR+matching replacement witnesses for a BTLNPC that actually binds VOICE_EE.','Inventory additional ORIGIN+12/+32 writers and alias paths with robust instruction-level search.','Implement diagnostics only after independent review and validated read boundaries; no hot reload or forced resource free from these findings.'],limits=evidence['limits'])
 verification=dict(status='PASS',originalSha256=SHA,checks=counts,allCapturedBodiesMatchOriginal=True,allASMPagesComplete=True,allPseudocodePagesComplete=True,independentReviewComplete=False,gameExecution=False,scope=evidence['limits'])
 amendment=dict(status='ORIGINAL_BYTES_VERIFIED_CLAIM_CONDITIONED',beforeManifestSha256=amendment_before['beforeFiles']['manifest.json'],beforeEvidenceSha256=amendment_before['beforeFiles']['evidence.json'],original40FunctionBytesUnchanged=True,newCapture='bucket-offset-capture.json',newCompleteFunctionBodies=2,newPrimaryBytes=sum(f['size'] for f in functions if f['addr'] in ('0x1400889b0','0x140091250')),producerClarification='Serializer uses an existing matching replacement-list record; it does not create that list record.',bucketProof=bucket_proof,independentReviewComplete=False)
 return {'evidence.json':encoded(evidence),'native-asm.txt':listing.encode(),'model.json':encoded(result),'report.json':encoded(report),'verification.json':encoded(verification),'review-amendment.json':encoded(amendment)}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
 outputs=verify_derived()
 for name,value in outputs.items():
  if args.check:assert (HERE/name).read_bytes()==value,name
  else:(HERE/name).write_bytes(value)
 excluded={'manifest.json','checkpoint.json'}
 manifest={p.name:dict(bytes=p.stat().st_size,sha256=digest(p.read_bytes())) for p in sorted(HERE.iterdir()) if p.is_file() and p.name not in excluded}
 content=encoded(dict(schema=1,files=manifest))
 if args.check:assert (HERE/'manifest.json').read_bytes()==content,'manifest'
 else:(HERE/'manifest.json').write_bytes(content)
 print(json.dumps(load(HERE/'verification.json'),ensure_ascii=True))

if __name__=='__main__':main()
