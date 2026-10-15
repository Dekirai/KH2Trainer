"""Portable, read-only verification; --write updates only this study's results."""
from pathlib import Path
import argparse,json,hashlib,struct,itertools,sys,importlib.util
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;ROOT=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir());BASE=0x140000000;MASK=(1<<64)-1
def load(p):return json.loads(p.read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
def dump(n,j):(H/n).write_text(json.dumps(j,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def run():
 checks=0
 def ck(v,s):
  nonlocal checks
  checks+=1
  if not v:raise AssertionError(s)
 original=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe').read_bytes()
 ck(sha(original)=='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed','original identity')
 pe=struct.unpack_from('<I',original,60)[0];opt=pe+24;ns=struct.unpack_from('<H',original,pe+6)[0];os=struct.unpack_from('<H',original,pe+20)[0]
 ck(original[pe:pe+4]==b'PE\0\0' and struct.unpack_from('<Q',original,opt+24)[0]==BASE,'PE64/imagebase')
 sections=[struct.unpack_from('<IIII',original,opt+os+40*i+8) for i in range(ns)]
 def read(a,n):
  r=a-BASE;offsets=[p+r-v for vs,v,size,p in sections if v<=r and r+n<=v+size]
  ck(len(offsets)==1,'bounded PE range');return original[offsets[0]:offsets[0]+n]
 e=load(H/'evidence.json');cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True;ins={};byaddr={};gaps=[]
 for f in e['functions']+e['dependencies']:
  addr=int(f['addr'],16);b=bytes.fromhex(f['originalBytes']);ck(len(b)==f['size'] and b==read(addr,len(b)) and sha(b)==f['sha256'],'original complete body')
  pages=f['pages'];rows=[]
  for p in pages:
   ck(p.get('offset',len(rows))==len(rows),'ASM offset');ck(p['instruction_count']==len(p['asm']['lines']),'ASM count');rows+=p['asm']['lines']
  ck(pages[-1]['cursor']=={'done':True} and f['disassembly']['asm']['lines']==rows,'ASM cursor/aggregate')
  ck(all(p['total_instructions']==len(rows) for p in pages),'ASM total')
  pp=f['pseudocode']['pages'];n=0
  for p in pp:
   ck(p.get('offset',n)==n and p['line_count']==len(p['code'].splitlines()),'pseudo page '+f['addr']+' '+str({k:v for k,v in p.items() if k not in ('code','refs')}));n+=p['line_count']
   # MCP marks any partial offset page truncated, even its terminal page.
   # Complete coverage is proven by offsets, line totals and terminal cursor.
  ck(pp[-1]['cursor']=={'done':True} and '\n'.join(p['code'] for p in pp)==f['pseudocode']['code'],'pseudo cursor/join')
  ck(all(p['total_lines']==n for p in pp),'pseudo total')
  cursor=addr;observedgaps=[];decoded=[]
  for row,normalized in zip(rows,f['instructions']):
   pc=int(row['addr'],16);ck(pc>=cursor,'ordered original instructions')
   if pc>cursor:observedgaps.append({'addr':hex(cursor),'bytes':b[cursor-addr:pc-addr].hex(' '),'length':pc-cursor})
   i=next(cs.disasm(read(pc,15),pc,count=1));cursor=pc+i.size;ins[pc]=i;decoded.append(i)
   ck(normalized=={'addr':hex(pc),'size':i.size,'bytes':i.bytes.hex(),'mnemonic':i.mnemonic,'operands':i.op_str},'exact original decode')
  if cursor<addr+len(b):observedgaps.append({'addr':hex(cursor),'bytes':b[cursor-addr:].hex(' '),'length':addr+len(b)-cursor})
  ck(len(rows)==len(f['instructions']) and observedgaps==f['nonInstructionSpans'],'instruction count and explicit gaps')
  gaps.extend([{'function':f['addr'],**g} for g in observedgaps]);byaddr[f['addr']]=decoded
  meta=f['sourceMetadata']
  if f['freshCapture']:
   cap=load(H/meta['captureFile']);cf=next(x for x in cap['functions'] if x['addr']==f['addr'])
   ck(sha((H/meta['captureFile']).read_bytes())==meta['captureSha256'],'fresh capture pin')
   ck(bytes(int(x,16) for x in cf['idaBytes'].split())==b,'IDA bytes equal original')
   ck(all(f[k]==cf[k] for k in ('pages','disassembly','pseudocode')),'original complete capture transport')
  else:ck(sha((ROOT/meta['evidenceFile']).read_bytes())==meta['evidenceSha256'],'explicit reused pin')
 for x in load(H/'provenance.json')['dependencies']:ck(sha((ROOT/x['path']).read_bytes())==x['sha256'],'dependency pin')
 for ref in e['positiveRefs']:
  i=ins[int(ref['site'],16)];targets={o.imm for o in i.operands if o.type==X86_OP_IMM}|{i.address+i.size+o.mem.disp for o in i.operands if o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP}
  ck(int(ref['target'],16) in targets,'positive original encoded reference')
 for d in e['data']:ck(bytes.fromhex(d['originalBytes'])==read(int(d['addr'],16),len(bytes.fromhex(d['originalBytes']))),'original captured data')
 ck(read(BASE+0xa3f21,3)==bytes.fromhex('0f 1f 00'),'trailing alignment NOP')
 targets=struct.unpack('<6I',read(BASE+0xa3f24,24));ck(targets==(0xa362e,0xa3784,0xa3870,0xa3a1a,0xa3d31,0xa35e3),'entire original StreamBankEx switch')
 # Model interpreter inherited from a separately reviewed artifact, with one
 # explicit 3-operand IMUL extension; synthetic memory and helper returns only.
 spec=importlib.util.spec_from_file_location('header_study_vm',H/'vm.py');vm=importlib.util.module_from_spec(spec);spec.loader.exec_module(vm);vm.ins=ins
 class TracedMemory(vm.Memory):
  def __init__(self):super().__init__();self.reads=[]
  def get(self,a,n):self.reads.append((a,n));return super().get(a,n)
 def setup(start):
  v=vm.VM(start,TracedMemory())
  for d in e['data']:
   for j,b in enumerate(bytes.fromhex(d['originalBytes'])):v.mem.put(int(d['addr'],16)+j,1,b,False)
  return v
 def at(v,a,n,x):v.mem.put(a,n,x,False)
 def rip(pc,idx):
  i=ins[BASE+pc];o=i.operands[idx];ck(o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP,'RIP operand');return i.address+i.size+o.mem.disp
 # Only recognized CS imports are stubbed; callback/import semantics excluded.
 for f in e['functions']:
  for row in f['disassembly']['asm']['lines']:
   for name in ('EnterCriticalSection','LeaveCriticalSection'):
    if '__imp_'+name in row['instruction']:
     i=ins[int(row['addr'],16)];ck(i.mnemonic=='call','CS call');vm.imports[i.address+i.size+i.operands[0].mem.disp]=name
 cases=[]
 def record(group,inputs,outputs):cases.append({'group':group,'inputs':inputs,'outputs':outputs})
 versions=[0,1,2,3,4,5,255,256,0x7fffffff,0x80000000,0xfffffffe,0xffffffff]
 for start,version in itertools.product([0xa13b0,0xa4020],versions):
  v=setup(start);at(v,0x400018,4,version);v.setreg('rcx',0x400000 if start==0xa13b0 else version)
  def diagnostic(v):v.events.append('diagnostic');return 0x7654
  v.calls={0x14003b670:diagnostic};v.run();expected=16 if version==1 else 32 if version in (2,3,4) else 0
  ck(v.getreg('eax')==expected and v.events==([] if expected else ['diagnostic']),'header size version and returning diagnostic')
  record('header-size',[start,version],{'size':expected,'diagnostic':v.events})
 profiles=sorted(set([(x,4) for x in range(256)]+[(0,x) for x in range(256)]))
 for start,profile in itertools.product([0x7ad30,0x7ada0],profiles):
  v=setup(start);p=0x500000;v.setreg('rcx',p);v.setreg('edx',1)
  for off,n,val in [(0,4,int.from_bytes(b'SEDB','little')),(4,4,0),(8,4,0xffffffff),(12,1,profile[0]),(13,1,profile[1]),(14,2,48),(48,2,2),(54,2,999),(84,4,160),(172,2,34)]:at(v,p+off,n,val)
  v.run();expected=999034 if start==0x7ad30 else 2
  ck(v.getreg('eax')==expected,'metadata getter ignores varied profile/version/SSCF locally')
  ck(not any(a<p+14 and a+n>p+12 for a,n in v.mem.reads),'getter does not read file profile bytes')
  record('metadata-profile',[start,list(profile)],expected)
 for start,valid,index,offset in itertools.product([0x7ad30,0x7ada0],[False,True],[-1,0,1,0x7fffffff,-0x80000000],[-128,0,160]):
  v=setup(start);p=0x500000;v.setreg('rcx',p);v.setreg('edx',index);at(v,p,4,int.from_bytes(b'SEDB','little') if valid else 0);at(v,p+14,2,48);at(v,p+48,2,7);at(v,p+54,2,65535)
  if start==0x7ad30:at(v,(p+80+index*4)&MASK,4,offset);at(v,(p+offset+12)&MASK,2,65535)
  # offset0 overwrites raw profile bytes, still without a profile condition.
  v.run();expected=(65535*1000+65535 if start==0x7ad30 else 7) if valid else 0xffffffff
  ck(v.getreg('eax')==expected,'magic-only getter / signed index and offset')
  record('metadata-index',[start,valid,index,offset],expected)
 for flags,index in itertools.product(range(256),[0,1,-1,0x80000000]):
  v=setup(0xa2840);v.setreg('rcx',0x400000);v.setreg('edx',index);at(v,0x400080,1,flags)
  def lookup(v):v.events.append((v.getreg('rcx'),v.getreg('edx')));return 0x123456789abc
  v.calls={BASE+0x9fd20:lookup};v.run();yes=(flags&2)!=0 and index==0
  ck(v.events==([(0x400000,0)] if yes else []) and v.getreg('rax')==(0x123456789abc if yes else 0),'stream virtual sequence wrapper flags and index')
  record('stream-sequence-wrapper',[flags,index],yes)
 # Original state0 signature/count branch after the prior >=80-byte gate.
 # Reads explicit fixed offsets, not the dynamic h field used by ActualBank.
 for magic,counts,profile,version in itertools.product([0,1,2,3],[(1,1,1),(0,1,1),(1,0,1),(1,1,0),(2,2,2)],[(0,4),(1,8),(255,255)], [0,3,5,0xffffffff]):
  v=setup(0xa3713);obj=0x400000;p=0x500000;v.setreg('rdi',obj);at(v,obj+40,8,p);at(v,obj-32,1,0x80)
  for off,n,value in [(0,4,int.from_bytes(b'SEDB','little') if magic&1 else 0),(4,4,int.from_bytes(b'SSCF','little') if magic&2 else 0),(8,4,version),(12,1,profile[0]),(13,1,profile[1]),(14,2,4096),(16,4,0xf0000000),(48,2,counts[0]),(50,2,counts[1]),(52,2,counts[2]),(54,2,444)]:at(v,p+off,n,value)
  def advance(v):v.events.append((v.getreg('rcx'),v.getreg('edx')));return 0
  v.calls={BASE+0xa34e0:advance};v.stops={BASE+0xa3ecf,BASE+0xa3ed3,BASE+0xa3ef2};v.run();yes=magic==3 and counts==(1,1,1)
  ck(v.events==([(obj-160,1)] if yes else []),'stream state0 exact magic and fixed count gate')
  ck(not any(a<p+16 and a+n>p+12 for a,n in v.mem.reads),'stream gate no file profile/headerOffset read')
  ck(v.mem.get(obj-136,4)==(version if magic==3 else 0),'stream copies unvalidated raw version only after both magics')
  record('stream-header-gate',[magic,counts,profile,version],yes)
 # Inspect actual sign extension, then continue through allocator/copy suffix.
 for length,allocation in itertools.product([0,1,16,0x7fffffff,0x80000000,0xffffffff],[0,0x600000]):
  v=setup(0xa09c2);v.setreg('rdx',0x500000);at(v,0x500010,4,length);v.stops={BASE+0xa09c6};v.run();want=length if length<0x80000000 else length-(1<<32)
  ck(v.getreg('rbx')==want&MASK,'actual signed declared length extension')
  v.pc=BASE+0xa0a06;v.stops=set();v.setreg('rsi',0x500000);v.setreg('rbp',0x400000)
  def allocate(v):v.events.append(('allocate',v.getreg('rdx')));return allocation
  def copy(v):v.events.append(('copy',v.getreg('rcx'),v.getreg('rdx'),v.getreg('r8')));return 0
  copytarget=ins[BASE+0xa0a29].operands[0].imm;v.calls={BASE+0xf8920:allocate,copytarget:copy};v.run()
  ck(v.events==[('allocate',want&MASK),('copy',allocation,0x500000,want&MASK)] and v.mem.get(0x400008,8)==allocation,'copy suffix no null/length gate and publication after modeled helper return')
  record('tool-copy-length',[length,allocation],{'length64':want&MASK,'events':v.events})
 summary={'status':'PASS','checks':checks,'freshBodies':len(e['functions']),'reusedBodies':len(e['dependencies']),'freshBytes':sum(x['size'] for x in e['functions']),'freshInstructions':sum(len(x['instructions']) for x in e['functions']),'positiveEncodedReferences':len(e['positiveRefs']),'switchTargets':len(targets),'nonInstructionSpans':gaps,'modelCases':len(cases),'modelGroups':{g:sum(x['group']==g for x in cases) for g in sorted({x['group'] for x in cases})},'profileMeaning':'No semantic naming for file bytes12/13 is established. Models demonstrate only the selected local readers/gate and their fixed fixture paths.','limits':'No native execution, live reachability, allocation success, callback progress, complete streaming/codec implementation, all-callers or global lifetime guarantee.'}
 return summary,json.loads(json.dumps({'cases':cases,'limits':summary['limits']}))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--write',action='store_true');ap.add_argument('--check',action='store_true');args=ap.parse_args();summary,cases=run()
 if args.write:dump('verification.json',summary);dump('model-results.json',cases)
 else:
  assert load(H/'verification.json')==summary
  assert load(H/'model-results.json')==cases
  if (H/'manifest.json').exists():
   m=load(H/'manifest.json')['files']
   assert set(m)=={p.name for p in H.iterdir() if p.is_file() and p.name!='manifest.json'}
   for name,pin in m.items():assert sha((H/name).read_bytes())==pin['sha256'] and (H/name).stat().st_size==pin['bytes']
 print(json.dumps(summary))
if __name__=='__main__':main()
