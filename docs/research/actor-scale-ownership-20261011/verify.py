"""Portable read-only author verifier; --write updates only study result files."""
from pathlib import Path
import json,hashlib,struct,itertools,argparse,sys,importlib.util,collections
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;ROOT=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir());BASE=0x140000000
EXE=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
def load(p):return json.loads(p.read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
def dump(n,j):(H/n).write_text(json.dumps(j,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def run():
 checks=0
 def ck(v,label):
  nonlocal checks
  checks+=1
  if not v:raise AssertionError(label)
 raw=EXE.read_bytes();ck(sha(raw)=='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed','original SHA256')
 pe=struct.unpack_from('<I',raw,60)[0];opt=pe+24
 ns=struct.unpack_from('<H',raw,pe+6)[0];os=struct.unpack_from('<H',raw,pe+20)[0]
 ck(raw[pe:pe+4]==b'PE\0\0' and struct.unpack_from('<Q',raw,opt+24)[0]==BASE,'PE64 base')
 sections=[struct.unpack_from('<IIII',raw,opt+os+40*i+8) for i in range(ns)]
 def read(a,n):
  r=a-BASE;p=[p+r-v for vs,v,size,p in sections if v<=r and r+n<=v+size]
  ck(len(p)==1,'bounded original PE range')
  return raw[p[0]:p[0]+n]
 e=load(H/'evidence.json');cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True;ins={};bytesum=0
 for f in e['functions']+e['dependencies']:
  a=int(f['addr'],16);b=bytes.fromhex(f['originalBytes']);ck(len(b)==f['size'] and b==read(a,len(b)) and sha(b)==f['sha256'],'original full body '+f['addr'])
  rows=[];pages=f['pages']
  for idx,p in enumerate(pages):
   ck(p.get('offset',len(rows))==len(rows),'ASM offset')
   ck(p['instruction_count']==len(p['asm']['lines']),'ASM page count');rows+=p['asm']['lines']
   if idx<len(pages)-1:ck(p['cursor']=={'next':len(rows)},'ASM intermediate cursor')
  ck(pages[-1]['cursor']=={'done':True} and rows==f['disassembly']['asm']['lines'],'ASM complete join')
  ck(all(p['total_instructions']==len(rows) for p in pages),'ASM total')
  ck(not f['nonInstructionSpans'],'no hidden gaps in selected bodies')
  ck(len(rows)==len(f['instructions']),'normalized instruction count')
  cursor=a
  for row,n in zip(rows,f['instructions']):
   pc=int(row['addr'],16);ck(pc==cursor,'contiguous original instruction')
   i=next(cs.disasm(read(pc,15),pc,count=1));ins[pc]=i;cursor=pc+i.size
   ck(n=={'addr':hex(pc),'size':i.size,'bytes':i.bytes.hex(),'mnemonic':i.mnemonic,'operands':i.op_str},'Capstone exact original decode')
  ck(cursor==a+len(b),'complete body extent');bytesum+=len(b)
  m=f['sourceMetadata']
  if f['freshCapture']:
   cap=load(H/m['captureFile']);c=next(x for x in cap['functions'] if x['addr']==f['addr'])
   ck(sha((H/m['captureFile']).read_bytes())==m['captureSha256'],'capture pin')
   ck(bytes(int(x,16) for x in c['idaBytes'].split())==b,'IDA and original bytes')
   ck(all(c[k]==f[k] for k in ['pages','disassembly','pseudocode']),'fresh transport equal')
   pp=f['pseudocode']['pages'];lines=0
   for idx,p in enumerate(pp):
    ck(p['line_count']==len(p['code'].splitlines()),'pseudocode page count');lines+=p['line_count']
    if idx<len(pp)-1:ck(p['cursor']=={'next':lines},'pseudocode intermediate cursor')
   ck(pp[-1]['cursor']=={'done':True} and all(p['total_lines']==lines for p in pp),'pseudocode full cursor')
  else:
   p=ROOT/m['evidenceFile'];ck(sha(p.read_bytes())==m['evidenceSha256'],'reused evidence pin')
   old=next(x for x in load(p)['functions'] if x['addr']==f['addr'])
   ck(old['pages']==f['pages'] and old['asm']==f['disassembly']['asm'],'reused ASM equality')
   ck(old['analysis']['decompile']==f['pseudocode']['code'],'reused pseudocode equality')
 for p in load(H/'provenance.json')['dependencies']:ck(sha((ROOT/p['path']).read_bytes())==p['sha256'],'source dependency pin')
 for d in e['data']:ck(bytes.fromhex(d['originalBytes'])==read(int(d['addr'],16),len(bytes.fromhex(d['originalBytes']))),'original data bytes')
 for r in e['positiveRefs']:
  i=ins[int(r['site'],16)];targets={o.imm for o in i.operands if o.type==X86_OP_IMM}|{i.address+i.size+o.mem.disp for o in i.operands if o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP}
  ck(int(r['target'],16) in targets,'positive encoded reference')
 def q(rva):return struct.unpack('<Q',read(BASE+rva,8))[0]
 ck(q(0x5b3fc0)==BASE+0x670460,'Stitch COL pointer')
 col=struct.unpack('<6I',read(BASE+0x670460,24));ck(col==(1,0,0,0x791e70,0x670488,0x670460),'Stitch original COL')
 ck(read(BASE+0x791e80,16)==b'.?AVStitch@kn@@\0','Stitch type name')
 ck(q(0x5b3fc8+72)==BASE+0x1c9d60 and q(0x5b3fc8+80)==BASE+0x1c7e00 and q(0x5b3fc8)==BASE+0x1c7440,'vtable slots and separate destructor')
 ck(q(0x753498)==BASE+0x755370,'BDX bank1 table')
 for at,fn,argc,index in [(0x755490,0x42c550,6,18),(0x7559d0,0x42c5f0,1,102)]:
  ck(struct.unpack('<QII',read(BASE+at,16))==(BASE+fn,argc,0),'BDX trap descriptor')
  ck((at-0x755370)//16==index and (at-0x755370)%16==0,'BDX trap index')
 for r in load(H/'capture-xrefs.json')['result']:ck(r['next_offset'] is None and len(r['data'])==r['total'],'xref page terminal')
 # Typed original instruction anchors make each semantic report point locatable.
 anchors=load(H/'anchors.json')
 for a in anchors:
  i=ins[BASE+int(a['rva'],16)];ck(i.mnemonic==a['mnemonic'] and i.op_str==a['operands'],'semantic original anchor '+a['rva'])
 spec=importlib.util.spec_from_file_location('scale_ownership_vm',H/'vm.py');vm=importlib.util.module_from_spec(spec);spec.loader.exec_module(vm);vm.ins=ins
 def setup(start):
  # Synthetic fixture memory intentionally returns zero for unspecified bytes.
  # This is neither bounds checking nor a native readability/lifetime proof.
  v=vm.VM(start,vm.Memory())
  for d in e['data']:
   for j,x in enumerate(bytes.fromhex(d['originalBytes'])):v.mem.put(int(d['addr'],16)+j,1,x,False)
  return v
 def at(v,a,n,x):v.mem.put(a,n,x,False)
 def call(v,target,name,result=0,action=None):
  def hook(w):
   args=[w.getreg(x) for x in ['rcx','rdx','r8','r9']]
   w.events.append([name,*args])
   return action(w,args) if action else result
  v.calls[BASE+target]=hook
 def calls(v,name):return [x[1:] for x in v.events if x[0]==name]
 cases=[];steps=0;flag_consumers=0
 def audit_flags(trace):
  # Audit only executed paths, separately from the instruction interpreter.
  # Its arithmetic operations implement Z but not general SF/OF/CF; INC/DEC
  # implement no flags. Calls leave unknown flags in real native execution.
  # Require every consumed flag to have a valid modeled local producer.
  nonlocal flag_consumers
  z=None;comparison=None
  for pc in trace:
   i=ins[pc];m=i.mnemonic
   if m in ('je','jne','sete','setne','cmove','cmovne'):
    ck(z is not None,'modeled Z producer before '+hex(pc));flag_consumers+=1
   elif m in ('jl','jle','jg','jge','ja','jb','jae','jbe','js','jns','setbe'):
    ck(comparison is not None,'CMP/TEST producer before '+hex(pc));flag_consumers+=1
   if m in ('cmp','test'):z=pc;comparison=pc
   elif m in ('xor','and','or','add','sub'):z=pc;comparison=None
   elif m in ('inc','dec','call','imul','shl','shr'):z=None;comparison=None
 def record(v,group,inputs,out):
  nonlocal steps
  ck(v.finished,'decoded body terminal '+group);audit_flags(v.trace);steps+=len(v.trace)
  cases.append({'group':group,'input':inputs,'output':out,'instructionCount':len(v.trace)})
 scalarbits=[0,0x3e800000,0x3f000000,0x3f800000,0x40000000,0x40800000,0x7fc00000,0x7f800000]
 # Full Stitch virtual-slot80 body. Helper calls are inert explicit stubs, except
 # selecting cached player / choosing two joint IDs. Tests prove local behavior
 # and argument ordering, not the helpers' complete side effects.
 for bits,alias,mask,flags in itertools.product(scalarbits,[False,True],range(4),range(8)):
  v=setup(0x1c7e00);s=0x400000;p=0x410000;actor=p if alias else 0x420000;children=[0x430000,0x440000]
  v.setreg('rcx',s);at(v,s+8,8,actor);at(v,p+60,4,bits);at(v,p+2008,4,0xdeadbeef)
  if not alias:at(v,actor+60,4,0x40c00000)
  for j in range(3):at(v,s+1928+j,1,(flags>>j)&1)
  for j,c in enumerate(children):at(v,p+3424+8*j,8,c if mask&(1<<j) else 0);at(v,c+2008,4,0xdeadbeef);at(v,c+60,4,0x3f400000)
  call(v,0x1b4ac0,'observer',0x460000);call(v,0x1cd8e0,'resetObserver')
  call(v,0x1b4b70,'cachedPlayer',p)
  for t,n in [(0x3cc3b0,'resetTransform'),(0x3cd820,'renderRestore'),(0x3da250,'detach'),(0x3d9fe0,'attach'),(0x3b4da0,'action'),(0x3db100,'contextReset'),(0x1b7d20,'callbackClear')]:call(v,t,n)
  call(v,0x3d7620,'joint',action=lambda w,a:0x1200+a[1])
  v.run()
  ck(v.mem.get(p+60,4)==0x3f800000 and v.mem.get(p+2008,4)==0,'cached player scalar reset independent of old bits')
  ck(calls(v,'cachedPlayer')[0][0]==0 and calls(v,'observer')[0][0]==actor,'distinct actor vs cache context')
  if not alias:ck(v.mem.get(actor+60,4)==0x40c00000,'does not reset context Actor+60 directly')
  present=[j for j in range(2) if mask&(1<<j)]
  ck([a[:4] for a in calls(v,'attach')]==[[children[j],p,0x1200+j,0] for j in present],'child reattach args')
  ck([a[0] for a in calls(v,'detach')]==[children[j] for j in present],'child detach selection')
  ck([a[0] for a in calls(v,'renderRestore')]==([p] if flags&1 else [])+[children[j] for j in present if flags&(2<<j)],'saved render flags')
  ck(calls(v,'action')[0][:2]==[p,0] and calls(v,'contextReset')[0][0]==actor and calls(v,'callbackClear')[0][:2]==[actor,0],'two context cleanup args')
  for j in range(2):ck(v.mem.get(children[j]+60,4)==0x3f400000 and v.mem.get(children[j]+2008,4)==(0 if j in present else 0xdeadbeef),'local child writes and scalar preservation')
  names=[x[0] for x in v.events]
  ck(names[:3]==['observer','resetObserver','cachedPlayer'] and names[-3:]==['action','contextReset','callbackClear'],'helper order')
  record(v,'stitch-local-reset',[bits,alias,mask,flags],{'reset':v.mem.get(p+60,4),'attached':len(present)})
 # Original BDX adapter: the high DWORD tag bytes are never interpreted locally.
 for joint,flags,callback,context in itertools.product([0,0x4000,0x4002,0xffff,0x12345678],[0,1,2,0xabcdef01],[0,1,0x80000000,0xffffffff],[0,0x500000,0x500080]):
  v=setup(0x42c550);args=0x400000;child=0x410000;parent=0x420000;recordptr=0x430000
  v.setreg('rcx',args);values=[0x101,0x202,joint,flags,callback,0x303]
  for j,x in enumerate(values):at(v,args+8*j,8,x|(0x52444140+j)<<32)
  at(v,0x440004,4,0x401);at(v,0x450004,4,0x402)
  decode={0x101:0x440000,0x202:0x450000,0x401:child,0x402:parent,0x303:0x460000}
  call(v,0x4ad270,'decode',action=lambda w,a:decode[a[0]])
  call(v,0x3d9fe0,'attach',recordptr);at(v,BASE+0x2a25048,8,context)
  for offset,n,x in [(16,8,0x123456789),(24,4,0xfedcba98),(32,8,0x987654321)]:at(v,recordptr+offset,n,x)
  v.run();ck(calls(v,'attach')==[[child,parent,joint,flags]],'BDX low DWORD argument routing')
  expected=[context,callback,0x460000] if callback else [0x123456789,0xfedcba98,0x987654321]
  got=[v.mem.get(recordptr+16,8),v.mem.get(recordptr+24,4),v.mem.get(recordptr+32,8)]
  ck(got==expected,'BDX optional callback fields')
  ck([a[0] for a in calls(v,'decode')]==[0x202,0x402,0x101,0x401]+([0x303] if callback else []),'decode exact low32 order')
  record(v,'bdx-attach',[joint,flags,callback,context],got)
 for tag in [0,1,0x52444140,0xffffffff]:
  v=setup(0x42c5f0);v.setreg('rcx',0x400000);at(v,0x400000,8,(tag<<32)|0x111);at(v,0x410004,4,0x222)
  call(v,0x4ad270,'decode',action=lambda w,a:{0x111:0x410000,0x222:0x420000}[a[0]])
  call(v,0x3da250,'detach',0x998877);v.run();ck(calls(v,'detach')[0][0]==0x420000 and v.getreg('rax')==0x998877,'BDX detach tail dispatch')
  record(v,'bdx-detach',[tag],calls(v,'detach')[0][0])
 for joint,flags,oldparent in itertools.product([0,1,0x4000,0x4002,0x7fff,0x8000,0xfffe,0xffff],[0,1,2,3,0x7fff,0x8000,0xfffe,0xffff],[0,0x470000,0x480000]):
  v=setup(0x3da210);child=0x400000;newparent=0x410000;v.setreg('rcx',child);v.setreg('rdx',newparent)
  at(v,child+1696,4,0x5678);at(v,child+1700,2,joint);at(v,child+1702,2,flags)
  call(v,0x4ad270,'decode',oldparent);call(v,0x3d9fe0,'attach',0x7777);v.run()
  ck(calls(v,'decode')[0][0]==0x5678 and calls(v,'attach')[0]==[child,newparent,joint,flags] and v.getreg('rax')==0x7777,'reparent forwards stored words ignoring decoded old parent result')
  record(v,'reparent-local',[joint,flags,oldparent],calls(v,'attach')[0])
 # Full cache refresh, observer replacements are inert stubs. Same-value cache
 # generations are not inferred; no lease or quiescence conclusion is drawn.
 for oldplayer,newplayer,oldmask,newmask in itertools.product([0,0x410000,0x420000],[0,0x410000,0x420000],range(4),range(4)):
  v=setup(0x1b7f70);old=[oldplayer,*[0x430000+0x10000*j if oldmask&(1<<j) else 0 for j in range(2)]]
  new=[newplayer,*[0x430000+0x10000*j if newmask&(1<<j) else 0 for j in range(2)]]
  for j,x in enumerate(old):at(v,BASE+0xad6a18+8*j,8,x)
  at(v,BASE+0x2a105d0,8,newplayer)
  for j in range(2):at(v,0x430000+0x10000*j+3576,8,0x450000+0x10000*j)
  call(v,0x3c3270,'companion',action=lambda w,a:new[1+a[0]])
  call(v,0x1cd1d0,'bindPersonality');call(v,0x1cd6e0,'replaceObserver');call(v,0x1cd730,'pruneObserver')
  # Security cookie is an explicit inert runtime stub; no stack-security claim.
  cookie=next(int(r['target'],16)-BASE for r in e['positiveRefs'] if r['site']=='0x1401b804a')
  call(v,cookie,'securityCookie');v.run()
  ck([v.mem.get(BASE+0xad6a18+8*j,8) for j in range(3)]==new,'cache new exact tuple')
  ck([a[:2] for a in calls(v,'replaceObserver')]==[[o,n] for o,n in zip(old,new) if o!=n],'replace only changed pointer pairs')
  ck([a[0] for a in calls(v,'companion')]==[0,1] and len(calls(v,'pruneObserver'))==1,'two companion lookups then prune')
  for j in range(2):
   if new[j+1]:ck(v.mem.get(new[j+1]+3596,4)==j+1,'companion slot ID')
  record(v,'cached-player-refresh',[oldplayer,newplayer,oldmask,newmask],new)
 for index in [-1,0,1,2,3,0x7fffffff,-0x80000000]:
  v=setup(0x1b4b70);v.setreg('ecx',index);address=(BASE+0xad6a18+index*8)&((1<<64)-1)
  at(v,address,8,0x123456789abcdef0);v.run();ck(v.getreg('rax')==0x123456789abcdef0,'unchecked sign extended index')
  record(v,'cache-index',[index],address)
 for encoded,decoded in [(0,0),(1,0),(1,0x410000),(0xffffffff,0x420000)]:
  v=setup(0x3da520);v.setreg('rcx',0x400000);at(v,0x400000+1696,4,encoded);call(v,0x4ad270,'decode',decoded);v.run()
  ck(v.getreg('al')==int(bool(decoded)) and calls(v,'decode')[0][0]==encoded,'parent predicate only decoded pointer')
  record(v,'parent-predicate',[encoded,decoded],v.getreg('al'))
 for attached in [0,1,2,255]:
  v=setup(0x405a00);v.setreg('rcx',0x400000)
  call(v,0x3da520,'parent',attached);call(v,0x3da250,'detach');call(v,0x3c86a0,'motion');call(v,0x3b4da0,'action')
  v.run();ck(len(calls(v,'detach'))==int(bool(attached)) and calls(v,'motion')[0][:2]==[0x400000+344,54] and calls(v,'action')[0][:2]==[0x400000,41],'conditional detach then motion/action')
  record(v,'native-detach-transition',[attached],len(calls(v,'detach')))
 for start,exists,encodedParent,bits in itertools.product([0x402fe0,0x403cc0],[False,True],[0,0x87654321],scalarbits):
  v=setup(start);p=0x400000;c=0x410000 if exists else 0;v.setreg('rcx',p if start==0x403cc0 else 0x990000);v.setreg('rdx',p)
  at(v,p+1696,4,encodedParent);at(v,p+60,4,bits)
  for t,n in [(0x3a8e70,'prepare'),(0x3d9fe0,'attach'),(0x3c8e90,'motionLink'),(0x3c86a0,'motion'),(0x3c8310,'motionReset'),(0x3b4da0,'action'),(0x3db140,'schedule')]:call(v,t,n)
  call(v,0x3b4110,'lookup',c);v.run()
  ck(v.mem.get(p+3600,8)==c and calls(v,'lookup')[0][0]==1620,'lookup descriptor and raw child slot')
  ck([a[:4] for a in calls(v,'attach')]==([[c,p,0x4002,0]] if exists else []),'native child attach independent of local parent encoding')
  ck(v.mem.get(p+60,4)==bits and v.mem.get(p+1696,4)==encodedParent,'no direct parent scalar/attachment mutation with inert helpers')
  ck(calls(v,'action')[0][:2]==[p,23] and calls(v,'schedule')[0][:2]==[p,9],'action and scheduling values')
  record(v,'native-child-attach',[start,exists,encodedParent,bits],{'child':c,'attach':exists})
 groups=collections.Counter(c['group'] for c in cases)
 return {'status':'PASS','scope':'Static original bytes and bounded synthetic original-instruction execution with explicit inert helper stubs and zero-default synthetic memory. No memory-safety, game, concurrency, global ownership or live safety guarantee.','checks':checks,'freshBodies':len(e['functions']),'reusedBodies':len(e['dependencies']),'freshBytes':sum(f['size'] for f in e['functions']),'allBytes':bytesum,'freshInstructions':sum(len(f['instructions']) for f in e['functions']),'allInstructions':len(ins),'anchors':len(anchors),'positiveReferences':len(e['positiveRefs']),'cases':len(cases),'interpretedInstructions':steps,'flagConsumersWithValidLocalProducers':flag_consumers,'groups':dict(groups),'modelResultsSha256':sha((json.dumps(cases,sort_keys=True,separators=(',',':'))).encode())},cases
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');p.add_argument('--check',action='store_true');args=p.parse_args()
 result,cases=run()
 if args.write:dump('verification.json',result);dump('model-results.json',cases)
 else:
  assert load(H/'verification.json')==result,'recorded verification differs'
  assert load(H/'model-results.json')==cases,'recorded model cases differ'
 print(json.dumps(result))

