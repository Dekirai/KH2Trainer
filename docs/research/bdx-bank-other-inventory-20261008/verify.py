"""Verify seven bounded native descriptor regions against IDA capture and retail PE.

This records structural extents, not native dispatch limits or all-handler semantics.
--check is read-only. No game code, script, or live process is executed.
"""
import argparse,copy,hashlib,importlib.util,json,struct
from pathlib import Path
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_MEM,X86_REG_RIP,X86_OP_IMM

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PE_SOURCE=HERE.parent/'bdx-trap-registry-20261008/verify.py'
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def encoded(x):return (json.dumps(x,indent=2,ensure_ascii=False)+'\n').encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def num(x):return int(x,16) if isinstance(x,str) else x
def blob(x):return bytes(int(v,16) for v in x.split())
def require(ok,why):
 if not ok:raise AssertionError(why)
def pe_module():
 spec=importlib.util.spec_from_file_location('bank_inventory_original_pe',PE_SOURCE)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

TABLES={3:(0x72f1a0,179),4:(0x757250,59),5:(0x789be0,35),6:(0x787e80,72),7:(0x7883f0,37),8:(0x787530,9),10:(0x787070,60)}
# Distinct data accesses beyond each descriptor cluster, checked from original instructions.
ANCHORS={
 0x140012e06:('mov','eax, dword ptr [rip + 0x71cec4]',0x14072fcd0),
 0x140012e12:('mov','eax, dword ptr [rip + 0x71cebc]',0x14072fcd4),
 0x14002ce6a:('and','qword ptr [rip + 0x72a7bf], rax',0x140757630),
 0x14002cf10:('mov','rax, qword ptr [rip + 0x72a7b9]',0x1407576d0),
 0x1400304a0:('mov','rax, qword ptr [rip + 0x759969]',0x140789e10),
 0x14002f57a:('and','qword ptr [rip + 0x758daf], rax',0x140788330),
 0x14002f5a0:('mov','rax, qword ptr [rip + 0x758e29]',0x1407883d0),
 0x14002f63a:('and','qword ptr [rip + 0x75902f], rax',0x140788670),
 0x14002eeba:('and','qword ptr [rip + 0x75872f], rax',0x1407875f0),
 0x14002edba:('and','qword ptr [rip + 0x75869f], rax',0x140787460),
}
RANGES={0x140433510:(5,0x1403fb1c0),0x140433520:(5,0x1403fb4d0),0x140433830:(16,0x1403fb250)}

def derive():
 m=pe_module();pe=m.PE(m.TARGET);capture=load(HERE/'capture.json');lookups=load(HERE/'handler-lookups.json')['result']
 require(capture['originalSha256']==m.SHA and num(capture['imageBase'])==pe.base,'retail identity')
 cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
 def read(a,n):
  b,z=pe.read(a,n);require(z==0,('stored original span',hex(a)));return b
 def executable(a):return any(pe.base+va<=a<pe.base+va+vs and flags&0x20000000 for name,va,vs,rs,rp,flags in pe.sections)
 function_rows=[];ins_by_addr={};listed_bytes=0;listed_count=0
 for f in capture['functions']:
  a=num(f['addr']);raw=read(a,f['size']);require(raw==blob(f['idaBytes']),('IDA bytes',f['addr']))
  asm=f['disassembly'];lines=asm['asm']['lines'];pages=f['pages']
  require(asm['cursor'].get('done') and len(lines)==asm['instruction_count']==asm['total_instructions'],('complete ASM',f['addr']))
  require(lines==[row for page in pages for row in page['asm']['lines']],('pages match',f['addr']))
  count=0
  for page in pages:
   require(page['instruction_count']==len(page['asm']['lines']),('page count',f['addr']));count+=page['instruction_count']
   require(page['cursor'].get('done') or page['cursor'].get('next')==count,('page cursor',f['addr']))
  require(pages[-1]['cursor'].get('done') and not f['pseudocode']['truncated'] and f['pseudocode']['cursor'].get('done'),('final cursors',f['addr']))
  offsets=set();decoded=[]
  for row in lines:
   at=num(row['addr']);require(a<=at<a+len(raw),('instruction extent',hex(at)))
   i=next(cs.disasm(raw[at-a:at-a+15],at,count=1),None);require(i is not None,('decode',hex(at)))
   span=set(range(at-a,at-a+i.size));require(not offsets&span,('instruction overlap',hex(at)));offsets|=span
   ins_by_addr[at]=i;decoded.append(dict(addr=hex(at),bytes=i.bytes.hex(),mnemonic=i.mnemonic,operands=i.op_str))
  require(offsets==set(range(len(raw))),('whole function extent',f['addr']))
  result=copy.deepcopy(f);result['originalBytes']=raw.hex(' ');result['sha256']=sha(raw);result['decodedInstructions']=decoded;function_rows.append(result)
  listed_bytes+=len(raw);listed_count+=len(lines)
 anchors=[]
 for a,(mn,op,target) in ANCHORS.items():
  i=ins_by_addr[a];require((i.mnemonic,i.op_str)==(mn,op),('semantic anchor',hex(a),(i.mnemonic,i.op_str)))
  require(any(o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and i.address+i.size+o.mem.disp==target for o in i.operands),('RIP target',hex(a)))
  anchors.append(dict(addr=hex(a),bytes=i.bytes.hex(),mnemonic=i.mnemonic,operands=i.op_str,target=hex(target)))
 lookup={num(x['query']):x for x in lookups};require(len(lookup)==len(lookups),'unique handler lookups')
 known_targets=set();tables=[];descriptors=[];nulls=[]
 for t in capture['tables']:
  bank=t['bank'];rva,count=TABLES[bank];require((t['rva'],t['count'])==(rva,count),'fixed bounded extent')
  a=pe.base+rva;data=t['capture']['result'];require(len(data)==1 and num(data[0]['addr'])==a,'capture address')
  raw=blob(data[0]['data']);require(len(raw)==count*16+128 and read(a,len(raw))==raw,('descriptor table bytes',bank))
  state=2 if bank==3 else 1
  slot=struct.unpack('<Q',read(pe.base+0x753490+bank*8,8))[0]
  require(slot==(0 if bank==3 else a),('original registry slot',bank))
  for index in range(count):
   b=raw[index*16:index*16+16];handler,flags,pad=struct.unpack('<QII',b)
   require(pad==0 and flags&~0x4000ffff==0,('descriptor flags/padding',bank,index))
   if handler:
    require(executable(handler),('executable target section',bank,index));known_targets.add(handler)
    entry=lookup[handler]
    if handler in RANGES:require(entry['fn'] is None and entry['error']=='Not a function',('recorded IDA code-range boundary',bank,index))
    else:require(entry['error'] is None and num(entry['fn']['addr'])==handler,('exact IDA function entry',bank,index))
   else:nulls.append(dict(bank=bank,index=index))
   descriptors.append(dict(bank=bank,index=index,descriptorRva=rva+16*index,handlerRva=handler-pe.base if handler else 0,flags=flags,name='',summary='',notes='',evidence='bdx-bank-other-inventory-20261008/evidence.json'))
  end=struct.unpack('<QII',raw[count*16:count*16+16]);require(not((not end[0] or executable(end[0])) and not(end[1]&~0x4000ffff) and end[2]==0),('distinct following data',bank))
  tables.append(dict(bank=bank,state=state,tableRva=rva,capturedRecords=count,capturedEndRva=rva+16*count,originalBytes=raw.hex(' '),sha256=sha(raw),followingFirstRecord=dict(qword=hex(end[0]),dword8=hex(end[1]),dword12=hex(end[2])),scope='Contiguous structurally supported descriptor cluster, followed by a distinct data family. No native bounds check or source-language array size is inferred.'))
 require(set(TABLES)=={t['bank'] for t in tables} and len(tables)==7,'seven table captures')
 require(set(lookup)==known_targets,'lookup inventory matches unique nonnull targets')
 # IDA did not define these three entries as functions. Decode only their bounded code ranges.
 supplemental=capture['additionalIdaBytes']['result'];ranges=[]
 for a,(size,target) in RANGES.items():
  region=next(x for x in supplemental if num(x['addr'])<=a and a+size<=num(x['addr'])+len(blob(x['data'])))
  region_start=num(region['addr']);whole=blob(region['data']);require(read(region_start,len(whole))==whole,'extra IDA bytes')
  raw=read(a,size);decoded=list(cs.disasm(raw,a));require(sum(i.size for i in decoded)==size,'bounded code decode')
  last=decoded[-1];require(last.mnemonic=='jmp' and last.operands[0].type==X86_OP_IMM and last.operands[0].imm==target,'direct tail target')
  require(executable(target),'branch target code section')
  rows=[dict(addr=hex(i.address),bytes=i.bytes.hex(),mnemonic=i.mnemonic,operands=i.op_str,instruction=i.mnemonic+' '+i.op_str) for i in decoded]
  ranges.append(dict(addr=hex(a),end_exclusive=hex(a+size),size=size,originalBytes=raw.hex(' '),sha256=sha(raw),tailTarget=hex(target),instructions=rows,asm=dict(lines=rows),observed_line_count=len(rows),note='Explicit original-PE code range decoded with Capstone, absent from captured IDA function definitions; not promoted into the canonical function inventory.'))
 for x in capture['boundaryXrefs']['result']+capture['tableXrefs']['result']:require(x.get('more') is False,'xref truncation')
 receipt=dict(success=True,descriptorRecords=len(descriptors),banks=len(tables),nullHandlerRecords=len(nulls),nonnullRecords=len(descriptors)-len(nulls),uniqueNonNullTargets=len(known_targets),exactIdaFunctionTargets=len(known_targets)-len(ranges),additionalCodeRanges=len(ranges),boundaryFunctions=len(function_rows),boundaryInstructions=listed_count,boundaryFunctionBytes=listed_bytes,semanticAnchors=len(anchors),rangeInstructions=sum(len(x['instructions']) for x in ranges),rangeBytes=sum(x['size'] for x in ranges),dataBytes=sum(len(blob(x['originalBytes'])) for x in tables),nullSlots=nulls,nativeDispatchBoundsProven=False,completeHandlerSemantics=False,liveGame=False)
 require((receipt['descriptorRecords'],receipt['nullHandlerRecords'],receipt['uniqueNonNullTargets'])==(451,5,446),'inventory totals')
 evidence=dict(schema=1,Domain='native',originalSha256=m.SHA,imageBase=hex(pe.base),functions=function_rows,tables=tables,code_ranges=ranges,semanticAnchors=anchors)
 return {'evidence.json':encoded(evidence),'descriptors.json':encoded(dict(schema=1,originalSha256=m.SHA,descriptors=descriptors)),'verification.json':encoded(receipt)}

def manifest():
 return dict(schema=1,files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p.read_bytes())) for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='manifest.json'},dependencies={str(PE_SOURCE.relative_to(ROOT)):sha(PE_SOURCE.read_bytes()),'docs/research/bdx-trap-registry-20261008/manifest.json':sha((HERE.parent/'bdx-trap-registry-20261008/manifest.json').read_bytes())})
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();outputs=derive()
 for name,data in outputs.items():
  if a.check:require((HERE/name).read_bytes()==data,('derived output changed',name))
  else:(HERE/name).write_bytes(data)
 if a.check:require(load(HERE/'manifest.json')==manifest(),'manifest changed')
 elif (HERE/'report.txt').exists():(HERE/'manifest.json').write_bytes(encoded(manifest()))
 print(outputs['verification.json'].decode())
