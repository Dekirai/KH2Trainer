"""Original-PE, complete IDA transport and bounded decoded-instruction verification."""
from pathlib import Path
import json,hashlib,struct,sys,importlib.util,argparse,itertools,collections
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;R=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir());BASE=0x140000000
P=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
def js(p):return json.loads(p.read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
def dump(n,v):(H/n).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
def run():
 checks=0
 def ck(v,n):
  nonlocal checks
  checks+=1
  if not v:raise AssertionError(n)
 b=P.read_bytes();ck(sha(b)=='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed','original executable hash')
 pe=struct.unpack_from('<I',b,60)[0];o=pe+24;ns=struct.unpack_from('<H',b,pe+6)[0];os=struct.unpack_from('<H',b,pe+20)[0]
 sections=[struct.unpack_from('<4I',b,o+os+40*k+8) for k in range(ns)]
 def read(a,n):
  r=a-BASE;locations=[p+r-v for vs,v,s,p in sections if v<=r and r+n<=v+s];ck(len(locations)==1,'bounded PE section read');return b[locations[0]:locations[0]+n]
 e=js(H/'evidence.json');dep=js(H/'dependencies.json');fs=e['functions']+dep['functions'];ins={};cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
 cap=js(H/'capture.json')
 for f in fs:
  a=int(f['addr'],16);raw=bytes.fromhex(f['originalBytes']);ck(len(raw)==f['size'] and raw==read(a,len(raw)) and sha(raw)==f['sha256'],'complete original body '+f['addr'])
  joined=[]
  for n,p in enumerate(f['pages']):
   ck(p.get('offset',len(joined))==len(joined),'ASM page offset');ck(p['instruction_count']==len(p['asm']['lines']),'ASM page size');joined+=p['asm']['lines']
   ck(p['cursor']==({'done':True} if n==len(f['pages'])-1 else {'next':len(joined)}),'ASM cursor')
  ck(joined==f['disassembly']['asm']['lines'] and len(joined)==f['disassembly']['total_instructions'],'complete ASM join')
  ck(all(p['total_instructions']==len(joined) for p in f['pages']),'ASM complete totals')
  cursor=a
  for row,n in zip(joined,f['instructions']):
   pc=int(row['addr'],16);ck(pc==cursor,'contiguous executable instructions')
   i=next(cs.disasm(read(pc,15),pc,count=1));ins[pc]=i;cursor=pc+i.size
   ck(n=={'addr':hex(pc),'size':i.size,'bytes':i.bytes.hex(),'mnemonic':i.mnemonic,'operands':i.op_str},'independent original decode')
  if f['addr']=='0x1401b06e0':
   ck(cursor==BASE+0x1b0e53 and a+len(raw)==BASE+0x1b0f6c,'factory executable end and recorded extent')
   ck(f['nonInstructionSpans']==[{'addr':hex(cursor),'bytes':read(cursor,281).hex(' ')}],'explicit 281-byte switch-data tail')
   ck(read(cursor,1)==b'\x90','one alignment NOP before switch tables')
  else:ck(cursor==a+len(raw) and not f['nonInstructionSpans'],'no hidden instruction gaps')
  m=f['sourceMetadata'];source=(H/m['path']) if f['freshCapture'] else (R/m['path']);ck(sha(source.read_bytes())==m['sha256'],'capture/reuse pin')
  old=next(x for x in (cap if f['freshCapture'] else js(source))['functions'] if x['addr']==f['addr'])
  ck(all(f[k]==old[k] for k in ('pages','disassembly','pseudocode')),'exact capture transport')
  if f['freshCapture']:
   ck(bytes(int(x,16) for x in old['idaBytes'].split())==raw,'IDA original bytes')
   pp=f['pseudocode']['pages'];lines=0
   for idx,p in enumerate(pp):
    ck(p.get('offset',lines)==lines and p['line_count']==len(p['code'].splitlines()),'pseudocode page count');lines+=p['line_count']
    ck(p['cursor']==({'done':True} if idx==len(pp)-1 else {'next':lines}),'pseudocode cursor')
   ck(all(p['total_lines']==lines for p in pp),'pseudocode complete total')
 for d in e['data']:ck(read(int(d['addr'],16),len(bytes.fromhex(d['originalBytes'])))==bytes.fromhex(d['originalBytes']),'original data region')
 for p in js(H/'provenance.json')['sourcePins']:ck(sha((R/p['path']).read_bytes())==p['sha256'],'prior evidence dependency')
 def q(r):return struct.unpack('<Q',read(BASE+r,8))[0]
 ck(q(0x753490+10*8)==BASE+0x787070,'original bank10')
 ck(q(0x753490+7*8)==BASE+0x7883f0,'original bank7')
 for r,t,arg,ret in [(0x7870a0,0x536480,1,False),(0x7870b0,0x5364b0,1,False),(0x788590,0x53fa00,2,True)]:
  ck(struct.unpack('<QII',read(BASE+r,16))==(BASE+t,arg|(0x40000000 if ret else 0),0),'original descriptor')
 ck((0x7870a0-0x787070)//16==3 and (0x7870b0-0x787070)//16==4 and (0x788590-0x7883f0)//16==26,'physical descriptor indices')
 ck(q(0x5b3fc8+72)==BASE+0x1c9d60 and q(0x5b3fc8+80)==BASE+0x1c7e00 and q(0x5b3fc8)==BASE+0x1c7440 and q(0x5b3fc8+8)==BASE+0x1cc760,'Stitch vtable dispatch and distinct cleanup')
 ck(q(0x5b3fc0)==BASE+0x670460 and struct.unpack('<6I',read(BASE+0x670460,24))==(1,0,0,0x791e70,0x670488,0x670460),'original RTTI COL')
 ck(read(BASE+0x791e80,16)==b'.?AVStitch@kn@@\0','Stitch RTTI name')
 ck(all(q(0x724340+72*j+8)==0 for j in range(7)),'original action record function fields uninitialized')
 # The existing VM models only exercised integer/transport instructions. Synthetic
 # memory returns zero for unspecified bytes; this is not native memory safety.
 spec=importlib.util.spec_from_file_location('stitch_vm',H/'vm.py');vm=importlib.util.module_from_spec(spec);spec.loader.exec_module(vm);vm.ins=ins
 cases=[];flagchecks=steps=0
 def setup(start):
  v=vm.VM(start)
  for d in e['data']:
   for j,x in enumerate(bytes.fromhex(d['originalBytes'])):v.mem.put(int(d['addr'],16)+j,1,x,False)
  # Load switch selectors and destinations exactly as in the original image.
  for j,x in enumerate(read(BASE+0x1b0e54,280)):v.mem.put(BASE+0x1b0e54+j,1,x,False)
  return v
 def at(v,a,n,x):v.mem.put(a,n,x,False)
 def hook(v,target,name,value=0,fn=None):
  def h(w):
   args=[w.getreg(x) for x in ('rcx','rdx','r8','r9')];w.events.append([name,*args]);return fn(w,args) if fn else value
  v.calls[BASE+target]=h
 def calls(v,n):return [x[1:] for x in v.events if x[0]==n]
 def flags(trace):
  nonlocal flagchecks
  z=cmp=False
  for pc in trace:
   m=ins[pc].mnemonic
   if m in ('je','jne','sete','setne','cmove','cmovne'):ck(z,'modeled Z producer '+hex(pc));flagchecks+=1
   elif m in ('jl','jle','jg','jge','ja','jb','jae','jbe','js','jns','setbe'):ck(cmp,'modeled CMP/TEST producer '+hex(pc));flagchecks+=1
   if m in ('test','cmp'):z=cmp=True
   elif m in ('xor','and','or','add','sub'):z=True;cmp=False
   elif m in ('call','inc','dec','shl','shr','imul'):z=cmp=False
 def rec(v,name,inputs,out,terminal=True):
  nonlocal steps
  if terminal:ck(v.finished,'terminal '+name)
  flags(v.trace);steps+=len(v.trace);cases.append({'group':name,'input':inputs,'output':out,'steps':len(v.trace)})
 A=0x400000;S=0x410000;P0=0x420000;ARGS=0x430000;WRAP=0x440000;T=BASE+0x5b3fc8
 # Execute both complete BDX adapters, varying ignored high tag DWORDs and the
 # selected vtable. Accessor semantics are also executed separately below.
 for entry,slot,target in [(0x536480,72,0x1c9d60),(0x5364b0,80,0x1c7e00)]:
  for tag,other in itertools.product([0,1,0x52444140,0xffffffff],[False,True]):
   v=setup(entry);v.setreg('rcx',ARGS);at(v,ARGS,8,0x111|(tag<<32));at(v,WRAP+4,4,0x222);at(v,S,8,T if not other else 0x450000)
   hook(v,0x4ad270,'decode',fn=lambda w,a:{0x111:WRAP,0x222:A}[a[0]])
   hook(v,0x1b4b80,'personality',S);actual=0x100000 if other else target
   if other:at(v,0x450000+slot,8,BASE+actual)
   hook(v,actual,'virtualTarget',0x12345678);v.run()
   ck([x[0] for x in calls(v,'decode')]==[0x111,0x222] and calls(v,'personality')[0][0]==A,'double decode and accessor routing')
   ck(calls(v,'virtualTarget')[0][0]==S and v.getreg('rax')==0x12345678,'exact selected target and this')
   ck(v.mem.get(ARGS,8)==0x111|(tag<<32),'nonreturn adapter leaves operand cell')
   rec(v,'bdx-virtual-dispatch',[entry,tag,other],{'slot':slot,'target':hex(BASE+actual)})
 for ptr in (0,S,0xffffffffffffffff):
  v=setup(0x1b4b80);v.setreg('rcx',A);at(v,A+3576,8,ptr);v.run();ck(v.getreg('rax')==ptr,'accessor has no pointer filter');rec(v,'personality-accessor',[ptr],ptr)
 # Decode the real factory switch from its type-selection block. RDI=Actor,
 # RSI=0 are explicit premises established by the preceding captured prologue.
 # Native allocation/construction/binding calls are inert, recorded stubs.
 for typ,allocate in itertools.product(list(range(206))+[0xffffffff,0x80000000],[False,True]):
  v=setup(0x1b08f2);v.setreg('rdi',A);v.setreg('rsi',0);v.setreg('rbx',1)
  hook(v,0x3b5b20,'type',typ);hook(v,0x152430,'allocate',S if allocate else 0)
  hook(v,0x4ad270,'decode',WRAP);hook(v,0x1cccf0,'bindResources')
  for target in [0x1ce770,0x1ce820,0x1ce9b0,0x1cea70,0x1ceb20,0x1cebf0,0x1cecc0,0x1cee20,0x1ceef0,0x1cefd0,0x1cf0a0,0x1cf150,0x1c6d00,0x1cf220,0x1cbcb0,0x1cf530,0x1caea0,0x1cc120]:hook(v,target,'constructor:'+hex(target),S)
  v.run();selected=calls(v,'constructor:0x1c6d00')
  ck(bool(selected)==(typ==200 and allocate),'only type200 successful allocation selects Stitch')
  if typ==200:
   ck(calls(v,'allocate')[0][0]==1944,'Stitch allocation size')
   ck(v.mem.get(A+3592,4)==14 and v.mem.get(A+3584,8)==BASE+0x1ca240,'Stitch type and handler assignment')
   ck(v.mem.get(A+3576,8)==(S if allocate else 0),'personality publish after constructor')
   ck(v.mem.get(A+3608,4)&2 and v.mem.get(A+3344,4)&2,'Stitch local flag writes')
   if allocate:ck(selected[0][:2]==[S,A],'factory constructor this and Actor argument despite abbreviated pseudotype')
  rec(v,'factory-type-selection',[typ,allocate],{'stitchConstructor':bool(selected),'personality':v.mem.get(A+3576,8)})
 # Base constructor actually stores the Actor and resource pointer used by
 # Stitch's inherited setup. No allocation/lifetime proof follows.
 for actor,res in itertools.product([0,A,P0],[0,0x460000]):
  v=setup(0x1cc120);v.setreg('rcx',S);v.setreg('rdx',actor);v.setreg('r8',res);v.run()
  ck(v.mem.get(S+8,8)==actor and v.mem.get(S+16,8)==res and v.mem.get(S+24,4)==0 and v.mem.get(S+32,8)==0,'base context fields');rec(v,'base-context',[actor,res],v.mem.get(S+8,8))
 # Callback installation and indirect call are actual complete native bodies.
 for callback in [0,BASE+0x1c7bf0,BASE+0x100000]:
  v=setup(0x1b7d20);v.setreg('rcx',A);v.setreg('rdx',callback);v.run();ck(v.mem.get(A+4000,8)==callback,'callback setter accepts every pointer');rec(v,'callback-setter',[callback],callback)
 for tag,action,returned in itertools.product([0,0xffffffff],[0,525,526,527,0xffffffff],[0,0x100000002,0xffffffffffffffff]):
  v=setup(0x53fa00);v.setreg('rcx',ARGS);at(v,ARGS,8,0x111|(tag<<32));at(v,ARGS+8,8,action|(tag<<32));at(v,WRAP+4,4,0x222)
  hook(v,0x4ad270,'decode',fn=lambda w,a:{0x111:WRAP,0x222:A}[a[0]])
  hook(v,0x1b2870,'callbackForward',returned);v.run()
  ck(calls(v,'callbackForward')[0][:2]==[A,action],'second argument low32 survives decode calls')
  ck(v.mem.get(ARGS,8)==((0x544e4940<<32)|(returned&0xffffffff)),'native adapter return cell/tag')
  rec(v,'bdx-callback-adapter',[tag,action,returned],v.mem.get(ARGS,8))
 for action in [0,525,526,527,0xffffffff]:
  v=setup(0x1b2870);v.setreg('rcx',A);v.setreg('edx',action);at(v,A+4000,8,BASE+0x1c7bf0);hook(v,0x1c7bf0,'installed',99);v.run();ck(calls(v,'installed')[0][:2]==[A,action],'callback tail forwards actor/action');rec(v,'callback-invocation',[action],99)
 # Exercise the real callback only until its unchecked record dereference.
 # This separates selection/clearing from any claim of initialized live records.
 for action,record in itertools.product([0,524,525,526,527,528,0xffffffff],[0,0x470000]):
  v=setup(0x1c7bf0);v.setreg('rcx',A);v.setreg('edx',action);v.stops.add(BASE+0x1c7cb3)
  hook(v,0x1b4b80,'personality',S)
  hook(v,0x1cd150,'lookup',record,fn=lambda w,a: (w.events.append(['lookupKey',w.mem.get(a[1],8),w.mem.get(a[1]+8,8),w.mem.get(a[1]+16,4)]) or record))
  hook(v,0x3bda50,'clearTagged');hook(v,0x1b7f10,'clearCurrent');v.run()
  expected={525:0x1c8610,526:0x1c8700,527:0x1c8440}.get(action)
  ck(len(calls(v,'lookup'))==int(expected is not None),'callback local selector domain')
  if expected:ck(calls(v,'lookupKey')==[[BASE+expected,0,0]],'callback exact member descriptor key')
  ck(calls(v,'clearCurrent')[0][:3]==[A,0,0],'current record cleared before unchecked dereference')
  ck(v.getreg('rdi')==(record if expected else 0),'record pre-dereference value; missing not locally rejected')
  rec(v,'callback-selection-to-dereference',[action,record],{'record':v.getreg('rdi'),'targetKey':hex(BASE+expected) if expected else None},False)
 # Local reset body from the prior accepted study, now connected to bank10:4.
 # Explicit native stubs isolate local memory stores and context argument flow.
 for scalar,alias in itertools.product([0,0x3e800000,0x3f800000,0x40000000,0x7fc00000,0x7f800000],[False,True]):
  v=setup(0x1c7e00);actor=P0 if alias else A;v.setreg('rcx',S);at(v,S+8,8,actor);at(v,P0+60,4,scalar);at(v,actor+4000,8,BASE+0x1c7bf0)
  if not alias:at(v,A+60,4,0x40800000)
  hook(v,0x1b4ac0,'observer',0x460000);hook(v,0x1cd8e0,'resetObserver');hook(v,0x1b4b70,'cached',P0)
  for target,name in [(0x3cd820,'render'),(0x3cc3b0,'transform'),(0x3da250,'detach'),(0x3d9fe0,'attach'),(0x3d7620,'joint'),(0x3b4da0,'action'),(0x3db100,'context')]:hook(v,target,name)
  hook(v,0x1b7d20,'clearCallback',fn=lambda w,a:(w.mem.put(a[0]+4000,8,a[1]) or 0));v.run()
  ck(v.mem.get(P0+60,4)==0x3f800000 and v.mem.get(actor+4000,8)==0,'cached scale reset/context callback clear')
  ck(any(a==P0+60 and n==4 and x==0x3f800000 for a,n,x in v.mem.writes),'unconditional same-value write recorded')
  if not alias:ck(v.mem.get(A+60,4)==0x40800000,'passed context need not be scalar target')
  ck(calls(v,'cached')[0][0]==0 and calls(v,'clearCallback')[0][:2]==[actor,0],'cache index and callback owner')
  rec(v,'connected-reset-local',[scalar,alias],{'scale':v.mem.get(P0+60,4),'callback':v.mem.get(actor+4000,8)})
 # Distinct generic cleanup: virtual slot0 destructs three object fields, then
 # clears them. The separate pre-cleanup selects personality slot8 (a RET0 for
 # the recorded Stitch table), not slot80. Callee side effects remain stubs.
 for mask in range(8):
  v=setup(0x1b1400);v.setreg('rcx',A)
  for i,offset in enumerate((3560,3568,3576)):
   obj=S+i*0x10000;at(v,A+offset,8,obj if mask&(1<<i) else 0);at(v,obj,8,0x480000+i*0x100);at(v,0x480000+i*0x100,8,BASE+0x100000+i);hook(v,0x100000+i,'destruct:'+str(i))
  hook(v,0x3c3470,'baseCleanup');v.run()
  ck(all(v.mem.get(A+x,8)==0 for x in (3560,3568,3576)),'generic cleanup zeroes visited object fields')
  ck([i for i in range(3) if calls(v,'destruct:'+str(i))]==[i for i in range(3) if mask&(1<<i)],'generic cleanup selected destructors')
  rec(v,'generic-cleanup',[mask],[x[0] for x in v.events])
 results={'checks':checks,'freshBodies':len(e['functions']),'freshBytes':sum(x['size'] for x in e['functions']),'freshInstructions':sum(len(x['instructions']) for x in e['functions']),'reusedBodies':len(dep['functions']),'totalBytes':sum(x['size'] for x in fs),'totalInstructions':len(ins),'explicitNonInstructionBytes':281,'syntheticCases':len(cases),'executedInstructions':steps,'auditedFlagConsumers':flagchecks,'groups':dict(collections.Counter(c['group'] for c in cases)),'status':'PASS','limits':'Explicit helper stubs, zero-default synthetic memory and exercised decoded instructions only. No pointer safety, runtime record initialization, live execution, thread ownership, callback closure or total-writer proof.'}
 return results,{'cases':cases}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');p.add_argument('--check',action='store_true');a=p.parse_args();r,m=run()
 if a.write:dump('verification.json',r);dump('model-results.json',m)
 else:assert js(H/'verification.json')==r and js(H/'model-results.json')==m
 print(json.dumps(r))

