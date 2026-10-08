"""Independent byte/table review and exhaustive structural opcode oracle."""
from pathlib import Path
import hashlib,importlib.util,json,struct,sys
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
DOC=ROOT/'docs/research/bdx-inspection-20261008'
TARGET='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
BASE=0x140000000
raw=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe').read_bytes()
assert hashlib.sha256(raw).hexdigest()==TARGET
pe=struct.unpack_from('<I',raw,0x3c)[0];opt=pe+24
assert raw[pe:pe+4]==b'PE\0\0' and struct.unpack_from('<Q',raw,opt+24)[0]==BASE
table=opt+struct.unpack_from('<H',raw,pe+20)[0]
sections=[struct.unpack_from('<4I',raw,table+40*i+8) for i in range(struct.unpack_from('<H',raw,pe+6)[0])]
def read(addr,n):
 rva=addr-BASE
 matches=[raw[off+rva-va:off+rva-va+n] for _,va,size,off in sections if va<=rva and rva-va+n<=size]
 assert len(matches)==1 and len(matches[0])==n
 return matches[0]
ev=json.loads((DOC/'evidence.json').read_bytes());md=Cs(CS_ARCH_X86,CS_MODE_64)
count=0;size=0
for f in ev['functions']:
 a=int(f['addr'],16);b=bytes(int(x,16) for x in f['originalBytes'].split())
 assert b==read(a,f['size'])
 rows=f['disassembly']['asm']['lines'];pages=f.get('pages',[f['disassembly']])
 assert len(rows)==f['disassembly']['total_instructions']==sum(len(p['asm']['lines']) for p in pages)
 assert rows==[x for p in pages for x in p['asm']['lines']] and pages[-1]['cursor'].get('done')
 end=int(rows[-1]['addr'],16);last=next(md.disasm(read(end,15),end,count=1))
 code=b[:end+last.size-a];decoded=list(md.disasm(code,a))
 assert sum(i.size for i in decoded)==len(code)
 assert [i.address for i in decoded]==[int(x['addr'],16) for x in rows]
 if a==0x14041b400:
  assert len(b)-len(code)==231 and read(a+len(code),3)==bytes.fromhex('0f1f00')
 else:assert len(code)==len(b)
 count+=len(rows);size+=len(b)
# Read native switch cells independently, including the invalid-subcase destinations.
unaryI=struct.unpack('<12I',read(BASE+0x41c600,48))
unaryF=struct.unpack('<11I',read(BASE+0x41c5d4,44))
controls=struct.unpack('<10I',read(BASE+0x41c660,40))
validI={i for i,dest in enumerate(unaryI) if dest!=0x41be7c}
validF={i+1 for i,dest in enumerate(unaryF) if dest!=0x41be7c}
validC={i for i,dest in enumerate(controls) if dest!=0x41c51a}
for t in ev['switchTables']:
 b=read(int(t['addr'],16),4*len(t['targets']))
 assert [BASE+x for x in struct.unpack('<'+'I'*len(t['targets']),b)]==[int(x,16) for x in t['targets']]
assert struct.unpack('<Q',read(BASE+0x7534a0,8))[0]==BASE+0x756b60
for index,argc,adapter in [(9,3,0x431a70),(95,2,0x431aa0)]:
 target,flags,_=struct.unpack('<QII',read(BASE+0x756b60+16*index,16))
 assert target==BASE+adapter and flags&0xffff==argc and flags&0x40000000==0
# This oracle checks stored-width/edge classes, not stack/native execution.
# Bits: Next1, Branch2, Call4, ReturnContinuation8, Resume16, Native32, DynamicReturn64.
spec=importlib.util.spec_from_file_location('prototype',DOC/'bdx_inspect.py');proto=importlib.util.module_from_spec(spec);spec.loader.exec_module(proto)
def i32(x):return (x+2**31)%2**32-2**31
records=bytearray();samples=[]
for word in range(65536):
 group=word%16; mode=(word//16)%4; sub=word//64
 width=([3,3,2,2][mode] if group==0 else {1:2,2:3,3:2,7:2,8:2,10:2,11:3}.get(group,1))
 err=group>11
 if group==5:err=not ((mode==0 and sub in validI) or (mode==1 and sub in validF))
 if group==6:err=mode>1 or (mode==1 and sub>4)
 if group==7:err=sub>2
 if group==9:err=sub not in validC
 mask=0 if err else 1
 if not err:
  if group==7:mask=2|(1 if sub else 0)
  elif group in (8,11):mask=12
  elif group==9:mask={0:16,1:0,2:64}.get(sub,1)
  elif group==10:mask=32
  elif (group in (1,2) or group==0 and mode==3) and sub>3:mask=0
 records+=bytes([width,int(err),mask])
 data=b'\0'*44+struct.pack('<HHH',word,0xfffe,0x8000)
 got=proto.instruction(data,14)
 assert got['width']==width,(word,'width')
 kinds={'fallthrough':1,'conditional-fallthrough':1,'branch':2,'conditional-branch':2,'call':4,'call-continuation':8,'yield-resume':16,'native-trap-continuation':32,'dynamic-return-or-status3':64}
 actual=0
 for e in got['edges']:
  actual|=kinds.get(e['kind'],0)
  if e['target'] is not None:
   expected=i32(14+width+(-2 if group in (7,8) else -2147418114)) if e['kind'] in ('branch','conditional-branch','call') else 14+width
   assert e['target']==expected,(word,e,expected)
 assert actual==mask and any(e['kind']=='status5-invalid-opcode' for e in got['edges'])==err,(word,actual,mask)
(HERE/'oracle.bin').write_bytes(records)
receipt={'status':'PASS','originalSha256':TARGET,'nativeBodies':len(ev['functions']),'nativeInstructions':count,'nativeBodyBytes':size,'opcodeCases':65536,'widthErrorFlowTriples':len(records)//3,'validIntegerUnary':sorted(validI),'validFloatUnary':sorted(validF),'validControl':sorted(validC),'bank2PointerAndDescriptorsChecked':True,'oracleSha256':hashlib.sha256(records).hexdigest(),'scope':'Independent PE extraction, complete body instruction boundaries, native table-derived valid sets; exhaustive width/status/edge classes and signed relative targets. No native VM execution.'}
(HERE/'oracle-review.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt,indent=2))
