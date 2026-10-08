"""Bounded read-only original-PE verifier. No target instruction or BDX execution.
Requires Python 3 and capstone. --check checks deterministic receipts and manifest.
"""
import argparse, hashlib, json, struct
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

HERE=Path(__file__).resolve().parent
BASE=0x140000000
SHA='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
DEFAULT_EXE=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def encoded(v): return (json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
def blob(s): return bytes(int(t,16) for t in s.split())
class PE:
 def __init__(self,path):
  self.raw=path.read_bytes();assert hashlib.sha256(self.raw).hexdigest()==SHA
  off=struct.unpack_from('<I',self.raw,0x3c)[0];assert self.raw[:2]==b'MZ' and self.raw[off:off+4]==b'PE\0\0'
  n=struct.unpack_from('<H',self.raw,off+6)[0];sz=struct.unpack_from('<H',self.raw,off+20)[0];opt=off+24
  assert struct.unpack_from('<H',self.raw,opt)[0]==0x20b and struct.unpack_from('<Q',self.raw,opt+24)[0]==BASE
  self.exceptionRva,self.exceptionSize=struct.unpack_from('<II',self.raw,opt+112+8*3)
  self.sections=[]
  for i in range(n):
   p=opt+sz+i*40;vs,va,size,ptr=struct.unpack_from('<IIII',self.raw,p+8);flags=struct.unpack_from('<I',self.raw,p+36)[0]
   self.sections.append((va,size,ptr,flags))
 def read(self,a,n):
  r=a-BASE
  for va,size,ptr,flags in self.sections:
   if va<=r and r+n<=va+size:return self.raw[ptr+r-va:ptr+r-va+n]
  raise AssertionError(('not file-backed',hex(a),n))

def derive(exe):
 pe=PE(exe);e=load(HERE/'evidence.json');cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
 assert e['Domain']=='native' and e['originalSha256']==SHA
 regions={int(r['addr'],16):blob(r['data']) for r in e['dataRegions']}
 for a,raw in regions.items(): assert pe.read(a,len(raw))==raw,hex(a)
 allins={};bodies=[];inline_data=[]
 for f in e['functions']:
  a=int(f['addr'],16);raw=blob(f['originalBytes']);assert len(raw)==f['size'] and pe.read(a,len(raw))==raw,f['addr']
  lines=f['disassembly']['asm']['lines'];pages=f['pages']
  assert f['disassembly']['cursor'].get('done') and len(lines)==f['disassembly']['instruction_count']==f['disassembly']['total_instructions']
  assert pages[-1]['cursor'].get('done') and [l for p in pages for l in p['asm']['lines']]==lines
  for i,p in enumerate(pages):
   assert p['instruction_count']==len(p['asm']['lines'])
   if i<len(pages)-1:assert p['cursor']['next']==sum(x['instruction_count'] for x in pages[:i+1])
  dec=f['decompile'];assert isinstance(dec,dict) and dec['cursor'].get('done') and not dec.get('truncated')
  ranges=[]
  for line in lines:
   addr=int(line['addr'],16);assert a<=addr<a+len(raw)
   ins=next(cs.disasm(raw[addr-a:],addr,count=1),None);assert ins is not None
   assert addr+ins.size<=a+len(raw);ranges.append((addr,addr+ins.size));allins[addr]=ins
  assert len(set(x[0] for x in ranges))==len(lines)
  end=a
  for start,stop in sorted(ranges):
   assert start>=end
   if start>end:inline_data.append({'body':f['addr'],'addr':hex(end),'bytes':pe.read(end,start-end).hex()})
   end=stop
  if end<a+len(raw):inline_data.append({'body':f['addr'],'addr':hex(end),'bytes':pe.read(end,a+len(raw)-end).hex()})
  bodies.append({'addr':f['addr'],'bytes':len(raw),'instructions':len(lines)})
 # The only bytes outside IDA instruction lines are switch tables/trailing data in these two bodies.
 assert {r['body'] for r in inline_data}=={'0x1403a31a0','0x1403aabe0'}
 stubs=[]
 for r in e['code_ranges']:
  a=int(r['addr'],16);raw=blob(r['originalBytes']);assert pe.read(a,len(raw))==raw
  ins=list(cs.disasm(raw,a));assert sum(i.size for i in ins)==len(raw)
  assert int(r['end_exclusive'],16)==a+len(raw) and r['observed_line_count']==len(ins)
  assert [{'addr':hex(i.address),'instruction':i.mnemonic+' '+i.op_str} for i in ins]==r['asm']['lines']
  assert ins[-1].mnemonic=='jmp' and ins[-1].operands[0].imm==int(r['tailTarget'],16)
  allins.update({i.address:i for i in ins});stubs.append({'addr':r['addr'],'bytes':len(raw),'instructions':len(ins)})
 assert [(x['addr'],x['bytes']) for x in stubs]==[('0x140433510',5),('0x140433520',5),('0x140433830',16)]
 rows=e['rows'];assert len(rows)==59
 for row in rows:
  a=BASE+row['descriptorRva'];ptr,flags,padding=struct.unpack('<QII',pe.read(a,16))
  assert row['bank']==4 and a==BASE+0x757250+16*row['index']
  assert ptr==(BASE+row['handlerRva'] if row['handlerRva'] else 0) and flags==row['flags'] and padding==0
  if ptr:assert ptr in allins
 assert [r['index'] for r in rows if not r['handlerRva']]==[0,1]
 assert struct.unpack('<Q',pe.read(BASE+0x7534b0,8))[0]==BASE+0x757250
 # Positive xrefs, not a negative census: both absolute pointers and RVA exception metadata occur.
 xrefs=[]
 for query in e['queries']:
  for result in query['result']['result']:
   assert not result['more'] and result['xref_count']==len(result['xrefs'])
   target=int(result['addr'],16)
   for x in result['xrefs']:
    a=int(x['addr'],16);matched=False
    if x['fn'] is None:
     raw=pe.read(a,8);matched=struct.unpack('<Q',raw)[0]==target or struct.unpack('<I',raw[:4])[0]==target-BASE
     if pe.exceptionRva<=a-BASE<pe.exceptionRva+pe.exceptionSize and (a-BASE-pe.exceptionRva)%12==0:
      # IDA attaches field xrefs to the start of the RUNTIME_FUNCTION item.
      matched=target-BASE in struct.unpack('<III',pe.read(a,12))
    else:
     ins=next(cs.disasm(pe.read(a,15),a,count=1));matched=any(o.type==X86_OP_IMM and o.imm==target or o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and a+ins.size+o.mem.disp==target for o in ins.operands)
    assert matched,(hex(a),hex(target));xrefs.append({'from':hex(a),'to':hex(target)})
 rtti=[]
 for vt,name in [(0x5c4208,'MISSION_TIMER'),(0x5c4248,'MISSION_COUNT'),(0x5c4288,'MISSION_GAUGE'),(0x5c42c8,'MISSION_WATCH'),(0x5c9df8,'COMBOCOUNTER'),(0x5c9e38,'MISSION_SCORE')]:
  col=struct.unpack('<Q',pe.read(BASE+vt-8,8))[0];sig,off,cd,td,ch,selfr=struct.unpack('<IIIIII',pe.read(col,24));assert sig==1 and off==cd==0 and col==BASE+selfr
  typename=pe.read(BASE+td+16,24).split(b'\0')[0].decode();assert typename in ['.?AU'+name+'@YS@@','.?AV'+name+'@YS@@']
  rtti.append({'vtableRva':vt,'completeObjectLocatorRva':col-BASE,'typeDescriptorRva':td,'name':typename,'slots':[hex(x) for x in struct.unpack('<7Q',pe.read(BASE+vt,56))]})
 assert struct.unpack('<Q',pe.read(BASE+0x750740,8))[0]==BASE+0x9ad874
 assert [struct.unpack('<f',pe.read(BASE+rva,4))[0] for rva in [0x623b18,0x623a4c,0x623c80]]==[2.0,0.5,-5.0]
 anchors={
  0x3fbb90:('lea','r8d, [r8 + r8*4]'),0x3fbb94:('add','r8d, r8d'),0x3fbba1:('idiv','r8d'),0x3fbbcf:('call','0x1403fa230'),
  0x3fa7a4:('add','ecx, edx'),0x3fa7a1:('movaps','xmm6, xmm2'),0x3fb25f:('mov','edi, ecx'),0x3fb261:('movaps','xmm6, xmm1'),
  0x3fb289:('movaps','xmm2, xmm6'),0x3fa838:('movss','dword ptr [rcx + 0x54], xmm0'),
  0x433784:('mov','dword ptr [rbx + 4], 0x544c4640'),0x3fa293:('call','0x1403aabe0'),0x3fa269:('call','0x1403aabe0'),
  0x3fa34f:('call','0x1403aabe0'),0x3fa387:('call','0x1403aabe0'),0x3fa2f3:('mov','dword ptr [rbx + 0x38], edi'),
  0x3fa3e1:('movss','dword ptr [rbx + 0x38], xmm6'),0x3fc1d6:('inc','dword ptr [rbx + 0x418]'),
  0x406c37:('mov','edx, 0x93'),0x406c3c:('call','0x1400fee50'),0x406c6b:('cmp','al, 0x63'),
  0x3a3526:('mov',None),0x3a4620:('and','dword ptr [rcx + 0x18], 0xfffffff7'),
  0x157207:('jmp','0x1403aabe0'),0x3aad6c:('call','0x1403f4980'),0x3aad76:('call','0x1403b4270'),0x3aad87:('jmp','0x1403f60d0'),
  0x3fb81d:('lea','ecx, [rax + 0x3b]'),0x3fb820:('mov','eax, 0x88888889'),0x3fb825:('mul','ecx'),0x3fb827:('shr','edx, 5')}
 for rva,(mn,op) in anchors.items():
  ins=allins[BASE+rva];assert ins.mnemonic==mn and (op is None or ins.op_str==op),(hex(ins.address),ins.mnemonic,ins.op_str)
 # The default switch arm really receives these messages, rather than relying only on decompilation.
 jump=list(struct.unpack('<3I',pe.read(BASE+0x3aad8c,12)));switch=pe.read(BASE+0x3aad98,120)
 for message in [14,74,123,136,137]:
  assert message<19 or jump[switch[message-19]]==0x3aad47
 cases=[]
 for n in range(-2,35):
  power=pow(10,max(n,0),1<<32);signed=power if power<1<<31 else power-(1<<32)
  cases.append({'position':n,'powerBits':f'{power:08x}','signedDivisor':signed,'divisionByZero':power==0})
 assert cases[33]['position']==31 and cases[33]['powerBits']=='80000000'
 assert all(c['divisionByZero'] for c in cases if c['position']>=32)
 assert all(not c['divisionByZero'] for c in cases if c['position']<32)
 assert (0x7fffffff+1)&0xffffffff==0x80000000
 model={'scope':'Only DWORD power/add arithmetic from the captured instructions. No original execution, memory access, exception delivery or retail script reachability test. Signed IDIV has divisor0 at every positive position >=32 if the counted loop completes; negative positions bypass the loop.','cases':cases,'relativeCounterOverflowExample':{'current':2147483647,'delta':1,'sumBits':'80000000','signedSum':-2147483648}}
 timer_cases=[]
 for ticks in [-2147483648,-120,-61,-60,-59,-58,-1,0,1,59,60,61,119,120,215999,2147483588,2147483647,4294967236,4294967237,4294967295]:
  numerator=(ticks+59)&0xffffffff;native=((numerator*0x88888889)>>32)>>5
  assert native==numerator//60
  timer_cases.append({'ticks':ticks,'wrappedNumerator':f'{numerator:08x}','unsignedQuotient':native})
 assert next(x for x in timer_cases if x['ticks']==-60)['unsignedQuotient']==71582788
 model['roundedTimer']={'formula':'uint32(ticks+59)/60; unsigned MUL high-half followed by SHR5, despite @INT result tag','cases':timer_cases,'scope':'20 boundary cases from the captured DWORD and unsigned multiply/shift instructions; no timer-validity or positive-time inference for invalid values.'}
 annotations=load(HERE/'annotations.json')['annotations']
 for key,a in annotations.items():
  bank,index=map(int,key.split(':'));row=rows[index]
  assert bank==4 and a['handlerRva']==row['handlerRva'] and a['declaredOperandCount']==row['flags']&0xffff and a['hasReturnSlot']==bool(row['flags']&0x40000000)
 for rel,expected in load(HERE/'source-snapshots.json').items():assert digest(HERE/rel)==expected['sha256']
 receipt={'success':True,'originalSha256':SHA,'records':len(rows),'nonnullRecords':57,'annotatedCalls':len(annotations),'fullBodies':len(bodies),'instructions':sum(x['instructions'] for x in bodies),'bodyBytes':sum(x['bytes'] for x in bodies),'codeRanges':stubs,'inlineData':inline_data,'capturedRegionBytes':sum(map(len,regions.values())),'verifiedXrefs':len(xrefs),'semanticAnchors':len(anchors),'arithmeticCases':len(cases),'roundedTimerCases':len(timer_cases),'rtti':rtti,'bodies':bodies,'scope':e['captureScope']}
 return receipt,model

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--exe',type=Path,default=DEFAULT_EXE);ap.add_argument('--check',action='store_true');args=ap.parse_args()
 receipt,model=derive(args.exe)
 for name,value in [('verification.json',receipt),('arithmetic-model.json',model)]:
  if args.check:assert (HERE/name).read_bytes()==encoded(value),name
  else:(HERE/name).write_bytes(encoded(value))
 if args.check:
  manifest=load(HERE/'manifest.json');actual={p.relative_to(HERE).as_posix() for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json'}
  assert actual==set(manifest['files'])
  for rel,row in manifest['files'].items():assert (HERE/rel).stat().st_size==row['bytes'] and digest(HERE/rel)==row['sha256'],rel
 print(json.dumps({k:v for k,v in receipt.items() if k not in ['bodies','rtti','inlineData','scope']},indent=2))
if __name__=='__main__':main()
