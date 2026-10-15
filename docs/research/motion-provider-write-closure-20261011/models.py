"""Small instruction-driven checks; no game execution and no library emulation."""
from capstone.x86 import X86_OP_REG,X86_OP_MEM,X86_OP_IMM
MASK=(1<<64)-1

class Leaf:
 def __init__(self,insmap,base):
  self.insmap=insmap;self.base=base;self.reg={};self.mem={};self.writes=[];self.steps=0;self.z=self.c=self.s=self.o=False
 def rn(self,n):
  if not n:return '',64
  aliases={'eax':('rax',32),'ecx':('rcx',32),'edx':('rdx',32),'ebx':('rbx',32),'esi':('rsi',32),'edi':('rdi',32),'ebp':('rbp',32),'esp':('rsp',32)}
  if n in aliases:return aliases[n]
  if n.startswith('r') and n.endswith('d'):return n[:-1],32
  return n,64
 def get(self,n):
  p,b=self.rn(n);return self.reg.get(p,0)&((1<<b)-1)
 def set(self,n,v):
  p,b=self.rn(n);self.reg[p]=v&((1<<b)-1)
 def load(self,at,n):return sum(self.mem.get((at+i)&MASK,0)<<(8*i) for i in range(n))
 def seed(self,at,v,n=8):
  for i in range(n):self.mem[(at+i)&MASK]=(v>>(8*i))&255
 def address(self,ins,op):
  m=op.mem;b=ins.reg_name(m.base);ix=ins.reg_name(m.index)
  return ((ins.address+ins.size if b=='rip' else self.get(b))+self.get(ix)*m.scale+m.disp)&MASK
 def val(self,ins,op):
  if op.type==X86_OP_REG:return self.get(ins.reg_name(op.reg))
  if op.type==X86_OP_IMM:return op.imm
  if op.type==X86_OP_MEM:return self.load(self.address(ins,op),op.size)
  raise AssertionError(op.type)
 def put(self,ins,op,v):
  if op.type==X86_OP_REG:self.set(ins.reg_name(op.reg),v)
  elif op.type==X86_OP_MEM:
   at=self.address(ins,op);self.seed(at,v,op.size);self.writes.append((at,op.size))
  else:raise AssertionError(op.type)
 def flags(self,x,y,b):
  mask=(1<<b)-1;x&=mask;y&=mask;r=(x-y)&mask
  self.z=r==0;self.c=x<y;self.s=bool(r>>(b-1));self.o=bool(((x^y)&(x^r))>>(b-1))
 def execute(self,rva,one=False):
  pc=self.base+rva
  while True:
   self.steps+=1;assert self.steps<2000
   ins=self.insmap[pc][0];ops=ins.operands;n=ins.mnemonic;nextpc=pc+ins.size
   if n=='ret':return self.get('rax')
   if n=='mov':self.put(ins,ops[0],self.val(ins,ops[1]))
   elif n=='lea':self.put(ins,ops[0],self.address(ins,ops[1]))
   elif n=='xor':
    v=self.val(ins,ops[0])^self.val(ins,ops[1]);self.put(ins,ops[0],v);self.z=v==0;self.c=self.o=False
   elif n=='test':
    v=self.val(ins,ops[0])&self.val(ins,ops[1]);self.z=v==0;self.c=self.o=False
   elif n=='cmp':self.flags(self.val(ins,ops[0]),self.val(ins,ops[1]),ops[0].size*8)
   elif n=='add':self.put(ins,ops[0],self.val(ins,ops[0])+self.val(ins,ops[1]))
   elif n=='dec':
    v=self.val(ins,ops[0]);cf=self.c;self.flags(v,1,ops[0].size*8);self.c=cf;self.put(ins,ops[0],v-1)
   elif n in ('nop','xchg'):assert n=='nop' or ins.op_str=='ax, ax'
   elif n.startswith('j'):
    take={'jmp':True,'je':self.z,'jne':not self.z,'ja':not self.c and not self.z,'jb':self.c}.get(n)
    assert take is not None,n
    if take:nextpc=self.val(ins,ops[0])
   else:raise AssertionError((hex(pc),n,ins.op_str))
   if one:return self.get('rax')
   pc=nextpc

def run(insmap,base):
 cases=[];steps=0
 # Execute the original six-instruction configuration setter, including real RIP addresses.
 for handler in [0,0xA000]:
  m=Leaf(insmap,base);m.set('rcx',handler);m.set('rdx',0);m.set('r9',0xB000)
  m.execute(0x12EE70)
  assert m.load(base+0x8AEF38,8)==handler and m.load(base+0x8AEF40,8)==0 and m.load(base+0x8AEF50,8)==0xB000
  assert [a for a,n in m.writes]==[base+x for x in [0x8AEF38,0x8AEF48,0x8AEF40,0x8AEF50]]
  cases.append({'name':'setter-null' if handler==0 else 'setter-nonnull-is-possible-with-different-caller','kind':'original leaf instructions','steps':m.steps});steps+=m.steps
 # Start at the actual null guard and stop before return epilogue. Null reaches currentEntry without a call.
 guard=insmap[base+0x12E69D][0];branch=insmap[base+0x12E6A0][0]
 assert guard.mnemonic=='test' and guard.op_str=='rax, rax' and branch.mnemonic=='je' and branch.operands[0].imm==base+0x12E835
 ctor=insmap[base+0x12CF16][0];assert ctor.mnemonic=='mov' and ctor.operands[0].mem.disp==1612 and (ctor.operands[1].imm&0xffffffff)==0xffffffff
 cases.append({'name':'retail-null-skips-dispatch-and-index-store','kind':'original branch target / constructor-store check','nullTarget':hex(branch.operands[0].imm),'matchedCallback':hex(base+0x12E82A),'matchedIndexStore':hex(base+0x12E82E)})
 # Real leaf lookup/removal is interpreted with private list entries and distinguishable primary bytes.
 fixturecases=[('empty',[],0x5000,1,None),('first',[0,1,2],0x5000,1,0),('middle',[0,1,2],0x6010,1,1),('last',[0,1,2],0x701f,1,2),('single',[1],0x6000,1,1),('lookup-keeps-list',[0,1,2],0x6008,0,1),('end-exclusive',[1],0x6020,1,None),('before-start',[1],0x5fff,1,None),('zero-length',[3],0x8000,1,None)]
 for name,ids,ptr,remove,hit in fixturecases:
  m=Leaf(insmap,base);ctx=0x1000;nodes={i:0x10000+i*0x1000 for i in ids};m.seed(base+0x8AEF30,ctx)
  m.seed(ctx+8,nodes[ids[0]] if ids else 0);m.seed(ctx+16,nodes[ids[-1]] if ids else 0);m.seed(ctx+24,len(ids),4)
  for k,i in enumerate(ids):
   n=nodes[i];p=0x5000+i*0x1000;m.seed(n+8,nodes[ids[k+1]] if k+1<len(ids) else 0);m.seed(n+16,p);m.seed(n+1624,p);m.seed(n+1600,0 if i==3 else 32,4)
   for off in range(32):m.seed(p+off,off^i,1)
  before=dict(m.mem);m.set('rcx',ptr);m.set('edx',remove);ret=m.execute(0x12E180)
  assert ret==(nodes[hit] if hit is not None else 0)
  remaining=[i for i in ids if not(remove and hit==i)]
  assert m.load(ctx+8,8)==(nodes[remaining[0]] if remaining else 0)
  assert m.load(ctx+16,8)==(nodes[remaining[-1]] if remaining else 0)
  assert m.load(ctx+24,4)==len(remaining)
  for k,i in enumerate(remaining):assert m.load(nodes[i]+8,8)==(nodes[remaining[k+1]] if k+1<len(remaining) else 0)
  if remove and hit is not None:assert m.load(nodes[hit]+8,8)==0
  allowed=set(range(ctx+8,ctx+28))|{nodes[i]+8+j for i in ids for j in range(8)}
  assert all(m.mem.get(a)==b for a,b in before.items() if a not in allowed)
  assert all(set(range(a,a+n))<=allowed for a,n in m.writes)
  cases.append({'name':'range-list-'+name,'kind':'original leaf instructions','steps':m.steps,'returnedEntry':hex(ret),'remainingEntries':len(remaining),'primaryAliasesAndBytesUnchanged':True});steps+=m.steps
 # Actual return reload discards earlier EAX, irrespective of the CRT or codec result.
 for name,rva,previous in [('raw-short-read',0x10774A,7),('stored-read-error',0x107728,-1),('codec-error',0x1076E3,-3),('raw-full-read',0x10774A,64)]:
  m=Leaf(insmap,base);m.set('rbx',0x1000);m.seed(0x1000+300,64,4);m.set('eax',previous)
  assert m.execute(rva,one=True)==64
  cases.append({'name':name,'kind':'original nominal-length reload; preceding helper result is synthetic','previousEax':previous,'returnedNominalSize':64});steps+=m.steps
 return {'scope':'Original leaf instructions and selected original branch/load semantics; no IO, codec, live-thread, allocation or arbitrary alias-consumer emulation.','counts':{'cases':len(cases),'interpretedInstructions':steps},'cases':cases}
