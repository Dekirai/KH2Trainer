"""Original-PE verification and deterministic Bank1/2 inventory derivation.
--check never changes frozen files. No target instruction or script execution.
"""
import argparse,collections,hashlib,json,struct
from pathlib import Path
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_MEM,X86_OP_IMM,X86_REG_RIP
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
ORIGINAL=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
SHA='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
BASE=0x140000000
BOUNDS=[(1,0x755370,0x756a70),(2,0x756b60,0x757180)]
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def encoded(v):return (json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
def blob(s):return bytes(int(t,16) for t in s.split())
class PE:
 def __init__(self):
  self.raw=ORIGINAL.read_bytes();assert hashlib.sha256(self.raw).hexdigest()==SHA
  off=struct.unpack_from('<I',self.raw,0x3c)[0];assert self.raw[:2]==b'MZ' and self.raw[off:off+4]==b'PE\0\0'
  n=struct.unpack_from('<H',self.raw,off+6)[0];size=struct.unpack_from('<H',self.raw,off+20)[0];opt=off+24
  assert struct.unpack_from('<H',self.raw,opt)[0]==0x20b and struct.unpack_from('<Q',self.raw,opt+24)[0]==BASE
  self.sections=[]
  for i in range(n):
   s=opt+size+i*40;vs,va,stored,ptr=struct.unpack_from('<IIII',self.raw,s+8);flags=struct.unpack_from('<I',self.raw,s+36)[0]
   self.sections.append((va,stored,ptr,flags))
 def section(self,a,n):
  rva=a-BASE
  for va,size,ptr,flags in self.sections:
   if va<=rva and rva+n<=va+size:return (self.raw[ptr+rva-va:ptr+rva-va+n],flags)
  raise AssertionError(('not stored original bytes',hex(a),n))
 def read(self,a,n):return self.section(a,n)[0]
def derive():
 pe=PE();e=load(HERE/'evidence.json');assert e['originalSha256']==SHA and int(e['imageBase'],16)==BASE
 for path,expected in load(HERE/'dependencies.json').items():assert sha(ROOT/path)==expected,path
 captured={int(r['addr'],16):blob(r['data']) for r in e['dataRegions']}
 for addr,data in captured.items():assert pe.read(addr,len(data))==data,hex(addr)
 cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True;instructions={};bodies=[]
 for f in e['functions']:
  a=int(f['addr'],16);raw=blob(f['originalBytes']);assert len(raw)==f['size'] and pe.read(a,len(raw))==raw
  d=f['disassembly'];lines=d['asm']['lines'];pages=f['pages'];assert d['cursor'].get('done') and len(lines)==d['instruction_count']==d['total_instructions']
  assert sum(p['instruction_count'] for p in pages)==len(lines) and pages[-1]['cursor'].get('done')
  assert f['decompile']['cursor'].get('done') and not f['decompile'].get('truncated')
  decoded=list(cs.disasm(raw,a));assert len(decoded)==len(lines) and sum(i.size for i in decoded)==len(raw)
  assert [i.address for i in decoded]==[int(l['addr'],16) for l in lines]
  instructions.update({i.address:i for i in decoded});bodies.append({'addr':f['addr'],'bytes':f['size'],'instructions':len(decoded)})
 lookup={int(x['query'],16):x for x in e['handlerLookups']};assert len(lookup)==460
 records=[];summary=[];pointer_users=collections.defaultdict(list)
 for bank,start,end in BOUNDS:
  current=[]
  for i,a in enumerate(range(BASE+start,BASE+end,16)):
   raw=pe.read(a,16);pointer,flags,padding=struct.unpack('<QII',raw)
   # Compare all bytes with independently saved IDA regions, including NULL holes.
   region=next((v[a-k:a-k+16] for k,v in captured.items() if k<=a and a+16<=k+len(v)),None);assert region==raw
   assert padding==0 and flags&~0x4000ffff==0
   if pointer:
    info=lookup[pointer];assert not info['error'] and int(info['fn']['addr'],16)==pointer
    assert pe.section(pointer,1)[1]&0x20000000 and next(cs.disasm(pe.read(pointer,15),pointer,count=1),None)
    pointer_users[pointer].append(f'{bank}:{i}')
   r={'bank':bank,'index':i,'descriptorRva':a-BASE,'handlerRva':pointer-BASE if pointer else 0,'flags':flags,'name':'','summary':'','notes':'','evidence':'','declaredOperandCount':flags&0xffff,'hasReturnSlot':bool(flags&0x40000000),'padding':padding}
   records.append(r);current.append(r)
  summary.append({'bank':bank,'tableRva':start,'endExclusiveRva':end,'structuralRecordCount':len(current),'nonnullSlots':sum(bool(r['handlerRva']) for r in current),'nullIndices':[r['index'] for r in current if not r['handlerRva']],'returnSlots':sum(r['hasReturnSlot'] for r in current),'maximumDeclaredOperands':max(r['declaredOperandCount'] for r in current),'countIsNativeBound':False})
 assert [(s['structuralRecordCount'],s['nullIndices']) for s in summary]==[(368,[16,116,215,216,282]),(98,[])]
 assert len(records)==466 and len(pointer_users)==460
 assert [{k:r[k] for k in ['bank','index','descriptorRva','handlerRva','flags','padding']} for r in records]==e['rows']
 # Table pointers are stored in original registry slots 1 and 2.
 assert pe.read(BASE+0x753498,16)==struct.pack('<QQ',BASE+0x755370,BASE+0x756b60)
 # Separate adjacent data and the instructions accessing them anchor the boundaries.
 assert struct.unpack('<Q',pe.read(BASE+0x756a70,8))[0]==BASE+0x2b047d0
 assert struct.unpack('<Q',pe.read(BASE+0x757180,8))[0]==0x60
 anchors={0x02cd40:('mov','rax, qword ptr [rip +'),0x02cd4d:('mov','qword ptr [rip +'),0x02cd1a:('and','qword ptr [rip +'),0x02cdda:('and','qword ptr [rip +'),0x41131b:('mov','dword ptr [rdi + 0xd38], eax'),0x411331:('jne',None),0x41133b:('mov','dword ptr [rdi + 0xd40], eax')}
 for rva,(mnemonic,operand) in anchors.items():
  i=instructions[BASE+rva];assert i.mnemonic==mnemonic,(hex(i.address),i.mnemonic)
  if operand is not None:assert i.op_str.startswith(operand),(hex(i.address),i.op_str)
 refs={BASE+0x02cd40:BASE+0x756a70,BASE+0x02cd1a:BASE+0x756aa8,BASE+0x02cdda:BASE+0x7571b0}
 for a,target in refs.items():
  i=instructions[a];assert any(o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and a+i.size+o.mem.disp==target for o in i.operands)
 # Saved xrefs are byte-supported; their absence/completeness is only an IDB snapshot property.
 xrefs=[]
 for q in e['queries']:
  if q['type']!='xref':continue
  for r in q['result']['result']:
   assert not r.get('more') and len(r.get('xrefs',[]))==r['xref_count']
   for x in r.get('xrefs',[]):
    a=int(x['addr'],16);target=int(r['addr'],16)
    if x['fn'] is None:assert struct.unpack('<Q',pe.read(a,8))[0]==target
    else:
     i=next(cs.disasm(pe.read(a,15),a,count=1));assert any(o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and a+i.size+o.mem.disp==target for o in i.operands)
    xrefs.append({'from':hex(a),'to':hex(target)})
 rets=[]
 for f in e['functions']:
  if not f['name'].startswith('nullsub'):continue
  a=int(f['addr'],16);assert pe.read(a,3)==bytes.fromhex('c20000')
  matching=[r for r in records if r['handlerRva']==a-BASE];assert len(matching)==1 and not matching[0]['hasReturnSlot']
  rets.append({'bank':matching[0]['bank'],'index':matching[0]['index'],'handlerRva':a-BASE,'declaredOperandCount':matching[0]['declaredOperandCount'],'hasReturnSlot':False})
 assert len(rets)==6
 # This is a captured complete dispatch subpath, not a newly captured full VM body.
 dispatch=list(cs.disasm(captured[BASE+0x41c4aa],BASE+0x41c4aa));assert sum(i.size for i in dispatch)==112
 by={i.address:i for i in dispatch}
 expected={0x41c4b2:('shr','rax, 6'),0x41c4b6:('mov','rdi, qword ptr [rcx + rax*8]'),0x41c4c8:('shl','rax, 4'),0x41c4cf:('movzx','edx, word ptr [rdi + 8]'),0x41c4fa:('call','qword ptr [rdi]'),0x41c4fc:('test','dword ptr [rdi + 8], 0x40000000')}
 for rva,expected in expected.items():assert (by[BASE+rva].mnemonic,by[BASE+rva].op_str)==expected
 inventory={'schema':1,'originalSha256':SHA,'banks':[{'bank':bank,'state':1,'tableRva':start} for bank,start,end in BOUNDS],'descriptors':records,'recordedExtents':summary,'scope':'Bounded static inventory, not source-language array sizes or native bounds. Empty names are intentional; no semantic annotations are invented.'}
 verification={'success':True,'originalSha256':SHA,'records':466,'nonnullSlots':461,'uniqueHandlers':460,'nullRecords':5,'bankSummaries':summary,'fullBodies':len(bodies),'bodyInstructions':sum(r['instructions'] for r in bodies),'bodyBytes':sum(r['bytes'] for r in bodies),'capturedRegionBytes':sum(len(v) for v in captured.values()),'dispatchSpanBytes':112,'dispatchSpanInstructions':len(dispatch),'verifiedIncomingXrefs':xrefs,'retOnlyDescriptors':rets,'handlerAliases':{hex(k):v for k,v in pointer_users.items() if len(v)>1},'bodies':bodies,'idaSnapshotLimitation':e['captureScope']}
 return inventory,verification
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args();inventory,verification=derive()
 for name,value in [('descriptors.json',inventory),('verification.json',verification)]:
  if args.check:assert (HERE/name).read_bytes()==encoded(value),name+' differs'
  else:(HERE/name).write_bytes(encoded(value))
 if args.check:
  manifest=load(HERE/'manifest.json')
  for rel,item in manifest['files'].items():
   p=HERE/rel;assert p.stat().st_size==item['bytes'] and sha(p)==item['sha256'],rel
  actual={p.relative_to(HERE).as_posix() for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json'};assert actual==set(manifest['files'])
 print(json.dumps({k:v for k,v in verification.items() if k not in ['bodies','verifiedIncomingXrefs','retOnlyDescriptors','bankSummaries','idaSnapshotLimitation']},indent=2))
if __name__=='__main__':main()
