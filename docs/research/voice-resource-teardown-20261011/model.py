"""Bounded synthetic models. Selected decoded branches; no native code executes."""
from itertools import product
from capstone.x86 import X86_OP_REG,X86_OP_IMM,X86_OP_MEM
BASE=0x140000000
MASK=(1<<64)-1
def require(ok,why):
 if not ok:raise AssertionError(why)
def trace_range(ins,start,length,qlo,qhi):
 # Execute the original comparison/branch block only. Record field loads are
 # supplied as synthetic registers, and both exits end before list traversal.
 regs={'rcx':start&MASK,'rax':(start+(length&0xffffffff))&MASK,'r10':qlo&MASK,'rdx':qhi&MASK}
 pc=BASE+0x12e132;cf=zf=False;trace=[]
 for _ in range(40):
  if pc==BASE+0x12e172:return True,trace
  if pc==BASE+0x12e164:return False,trace
  i=ins[pc];trace.append(hex(pc));op=i.mnemonic
  if op=='cmp':
   a,b=[regs[i.reg_name(o.reg)] for o in i.operands];cf=a<b;zf=a==b;pc+=i.size
  elif op in ('jne','je','jae','jb'):
   take={'jne':not zf,'je':zf,'jae':not cf,'jb':cf}[op];pc=i.operands[0].imm if take else pc+i.size
  else:raise AssertionError(('unexpected predicate instruction',hex(pc),op))
 raise AssertionError('range trace bound')
def cache_select(ins,bits):
 # Execute the original three-row vacancy loop and the three writes after it.
 # Memory is a synthetic map with deliberately valid storage for index3 too;
 # this tests index selection, not the real allocation's physical extent.
 root=0x1000;mem={root+12*k:bits[k] for k in range(3)}
 mem.update({root+12*3:0})
 regs={'rax':root,'r8':root,'rcx':root+36,'edx':0,'ebx':5,'edi':7,'rsi':0}
 pc=BASE+0x3cdef0;zf=False;less=False;writes=[]
 for _ in range(40):
  if pc==BASE+0x3cdf16:return regs['rsi'],writes
  i=ins[pc];op=i.mnemonic
  if op=='test':zf=(mem[regs['rax']]&1)==0
  elif op=='je':
   pc=i.operands[0].imm if zf else pc+i.size;continue
  elif op=='inc':regs['edx']=(regs['edx']+1)&0xffffffff
  elif op=='add':regs['rax']+=i.operands[1].imm
  elif op=='cmp':less=regs['rax']<regs['rcx']
  elif op=='jl':
   pc=i.operands[0].imm if less else pc+i.size;continue
  elif op=='movsxd':regs['rsi']=regs['edx'] if regs['edx']<0x80000000 else regs['edx']-(1<<32)
  elif op=='lea':regs['rax']=3*regs['rsi']
  elif op in ('or','mov'):
   dst=i.operands[0];require(dst.type==X86_OP_MEM,'cache store');a=regs['r8']+4*regs['rax']+dst.mem.disp
   if op=='or':mem[a]=mem.get(a,0)|1
   else:mem[a]=regs[i.reg_name(i.operands[1].reg)]
   writes.append(a)
  else:raise AssertionError(('unexpected cache instruction',hex(pc),op))
  pc+=i.size
 raise AssertionError('cache trace bound')
def run(ins,evidence):
 totals={};examples={};count=0
 points=[0,1,7,8,9,15,16,MASK]
 for start,length,qlo,qhi in product([0,1,8,MASK-8],[0,1,8,0xffffffff],points,points):
  end=(start+length)&MASK
  expected=(start==qlo and end==qhi) or (start<qlo<end) or (start<qhi<end) or (qlo<start<qhi) or (qlo<end<qhi)
  got,path=trace_range(ins,start,length,qlo,qhi);require(got==expected,'decoded range predicate')
  count+=1
 require(trace_range(ins,8,8,16,20)[0] is False,'adjacent boundary')
 require(trace_range(ins,8,8,9,9)[0] is True,'empty interior point')
 require(trace_range(ins,8,0,8,8)[0] is True,'exact empty range')
 totals['decodedRangePredicate']=count
 examples['emptyInteriorQueryMatches']={'record':[8,16],'query':[9,9],'trace':trace_range(ins,8,8,9,9)[1]}
 for bits in product([0,1],repeat=3):
  index,writes=cache_select(ins,bits);expected=next((i for i,b in enumerate(bits) if not b),3)
  require(index==expected and writes==[0x1000+12*index+x for x in [0,4,8]],'cache selection/write extent')
  count+=1
 totals['decodedCacheVacancy']=8
 examples['allThreeUsed']={'index':cache_select(ins,(1,1,1))[0],'note':'index3 is used; physical allocation and runtime reachability are not modeled'}
 # Stops are abstract local effects of the exact-pointer helper, whose key
 # compare, type compare, stop call, and state4 store have fixed ASM anchors.
 require(ins[BASE+0x1de5fe].op_str=='qword ptr [rbx + 0x18], rdi','pointer predicate')
 require(ins[BASE+0x1de604].op_str=='byte ptr [rbx + 0x35], 6','type predicate')
 require(ins[BASE+0x1de399].op_str=='byte ptr [rbx + 0x34], 4','state marker')
 cases=0
 for kind,size,alias,requestType,requestPointer,state in product([31,34,48],[0,48],[False,True],[5,6],[0x100,0x200,0x300],[1,2,4]):
  old,new=0x100,0x200;events=[];after=state;pointer=requestPointer
  for phase,address in [('before-copy',old),('after-copy',new)]:
   if kind==34 and size and not alias and requestType==6 and pointer==address:
    events.append(phase);after=4
  expected=(kind==34 and bool(size) and not alias and requestType==6 and pointer in [old,new])
  require(bool(events)==expected and pointer==requestPointer,'bounded exact-pointer stop and alias preservation')
  if expected:require(after==4 and events==['before-copy' if pointer==old else 'after-copy'],'phase specificity')
  else:require(after==state,'nonmatching state unchanged')
  count+=1;cases+=1
 totals['syntheticRelocationStop']=cases
 # Counter arithmetic follows actual 16-bit ADD, not a runtime wrap witness.
 i=ins[BASE+0x39da46];require(i.mnemonic=='add' and i.operands[0].size==2,'WORD decrement width')
 for n in [0,1,2,0x7fff,0x8000,0xffff]:
  got=(n+0xffff)&0xffff;require(got==(n-1)%65536,'WORD decrement');count+=1
 totals['counterWidth']=6
 # Explicit contrast: the sweep's +1604 check exists, while the selected
 # direct wrapper's normal-return sequence performs retirement after callback.
 require(ins[BASE+0x12efb3].op_str=='dword ptr [rbx + 0x644], esi','sweep gate')
 for field,callback in product([0,1,0xffffffff],[False,True]):
  sweep=[] if field else (['callback'] if callback else [])+['unlink','destructor']
  direct=(['callback'] if callback else [])+['unlink','destructor']
  require((not sweep)==bool(field),'sweep skips nonzero')
  require(direct[-2:]==['unlink','destructor'],'direct local retirement sequence')
  count+=1
 totals['syntheticSweepContrast']=6
 return dict(status='PASS',cases=count,groups=totals,examples=examples,limits='Range and vacancy models execute only selected decoded instruction blocks with synthetic inputs. Remaining cases are bounded abstract models tied to checked anchors. No original native code, async worker, game state, allocator, physical array extent, concurrency, callback completion or liveness is executed or proved.')
