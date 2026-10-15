"""Bounded interpreter copied from reviewed audio-header-profile study.
Local additions: MOVAPS/MOVSD transport, CMOVE/CMOVNE, instruction trace.
Only exercised instructions are claimed; this is not a CPU emulator."""
from capstone.x86_const import X86_OP_REG,X86_OP_MEM,X86_OP_IMM,X86_REG_RIP
BASE=0x140000000
ins={}
imports={}
class Memory:
 def __init__(self):self.data={};self.writes=[]
 def put(self,a,n,v,record=True):
  v&=(1<<(n*8))-1
  if record:self.writes.append((a,n,v))
  for j in range(n):self.data[a+j]=(v>>(8*j))&255
 def get(self,a,n):return sum(self.data.get(a+j,0)<<(8*j) for j in range(n))
def signed(v,bits):v&=(1<<bits)-1;return v-(1<<bits) if v>>(bits-1) else v
class VM:
 def __init__(self,start,mem=None):
  self.pc=BASE+start;self.mem=mem or Memory();self.reg={};self.setreg('rsp',0x900000);self.z=False;self.lt=False;self.below=False;self.events=[];self.calls={};self.stops=set();self.finished=False;self.trace=[]
 def alias(self,n):
  if n.startswith('xmm'):return n,128
  for root,forms in [('rax',['rax','eax','ax','al']),('rbx',['rbx','ebx','bx','bl']),('rcx',['rcx','ecx','cx','cl']),('rdx',['rdx','edx','dx','dl']),('rsi',['rsi','esi','si','sil']),('rdi',['rdi','edi','di','dil']),('rbp',['rbp','ebp','bp','bpl']),('rsp',['rsp','esp','sp','spl'])]:
   if n in forms:return root,[64,32,16,8][forms.index(n)]
  if n.startswith('r') and n[1:].rstrip('dwb').isdigit():
   suffix=n[-1];return (n[:-1],{'d':32,'w':16,'b':8}[suffix]) if suffix in 'dwb' else (n,64)
  raise AssertionError(('register',n))
 def getreg(self,n):root,bits=self.alias(n);return self.reg.get(root,0)&((1<<bits)-1)
 def setreg(self,n,v):
  root,bits=self.alias(n);mask=(1<<bits)-1
  self.reg[root]=(v&mask) if bits>=32 else (self.reg.get(root,0)&~mask)|(v&mask)
 def addr(self,o,i):
  m=o.mem;v=m.disp
  if m.base:v+=(i.address+i.size) if m.base==X86_REG_RIP else self.getreg(i.reg_name(m.base))
  if m.index:v+=self.getreg(i.reg_name(m.index))*m.scale
  return v&((1<<64)-1)
 def val(self,o,i):
  if o.type==X86_OP_IMM:return o.imm
  if o.type==X86_OP_REG:return self.getreg(i.reg_name(o.reg))
  if o.type==X86_OP_MEM:return self.mem.get(self.addr(o,i),o.size)
  raise AssertionError('operand')
 def put(self,o,i,v):
  if o.type==X86_OP_REG:self.setreg(i.reg_name(o.reg),v)
  else:self.mem.put(self.addr(o,i),o.size,v)
 def run(self,limit=5000):
  for _ in range(limit):
   if self.pc in self.stops:return self
   i=ins[self.pc];self.trace.append(self.pc);ops=i.operands;m=i.mnemonic;nextpc=i.address+i.size
   if m in ('mov','movabs','movzx','movups','movdqu','movdqa','movss','movsd','movaps'):self.put(ops[0],i,self.val(ops[1],i))
   elif m in ('movsxd','movsx'):self.put(ops[0],i,signed(self.val(ops[1],i),ops[1].size*8))
   elif m in ('cmovne','cmove'):
    if self.z == (m=='cmove'):self.put(ops[0],i,self.val(ops[1],i))
   elif m=='cdqe':self.setreg('rax',signed(self.getreg('eax'),32))
   elif m=='lea':self.put(ops[0],i,self.addr(ops[1],i))
   elif m=='xorps':self.put(ops[0],i,self.val(ops[0],i)^self.val(ops[1],i))
   elif m=='imul' and len(ops)==3:self.put(ops[0],i,self.val(ops[1],i)*self.val(ops[2],i))
   elif m in ('xor','and','or','add','sub','imul','shl','shr'):
    x=self.val(ops[0],i);y=self.val(ops[1],i)
    v={'xor':lambda:x^y,'and':lambda:x&y,'or':lambda:x|y,'add':lambda:x+y,'sub':lambda:x-y,'imul':lambda:x*y,'shl':lambda:x<<y,'shr':lambda:x>>y}[m]()
    self.put(ops[0],i,v);self.z=(v&((1<<(ops[0].size*8))-1))==0
   elif m in ('inc','dec'):self.put(ops[0],i,self.val(ops[0],i)+(1 if m=='inc' else -1))
   elif m=='div':
    denominator=self.val(ops[0],i);n=(self.getreg('rdx')<<64)|self.getreg('rax');self.setreg('rax',n//denominator);self.setreg('rdx',n%denominator)
   elif m in ('test','cmp'):
    x=self.val(ops[0],i);y=self.val(ops[1],i);bits=ops[0].size*8
    if m=='test':self.z=(x&y)==0;self.lt=signed(x&y,bits)<0;self.below=False
    else:self.z=(x&((1<<bits)-1))==(y&((1<<bits)-1));self.lt=signed(x,bits)<signed(y,bits);self.below=(x&((1<<bits)-1))<(y&((1<<bits)-1))
   elif m in ('je','jne','jl','jle','jg','jge','ja','jb','jae','jbe','js','jns','jmp'):
    take={'je':self.z,'jne':not self.z,'jl':self.lt,'jle':self.lt or self.z,'jg':not(self.lt or self.z),'jge':not self.lt,'ja':not(self.below or self.z),'jb':self.below,'jae':not self.below,'jbe':self.below or self.z,'js':self.lt,'jns':not self.lt,'jmp':True}[m]
    if take:
     nextpc=self.val(ops[0],i)
     if nextpc in self.calls:self.setreg('rax',self.calls[nextpc](self));self.finished=True;return self
   elif m in ('sete','setne','setbe'):self.put(ops[0],i,int(self.below or self.z if m=='setbe' else self.z if m=='sete' else not self.z))
   elif m=='push':self.setreg('rsp',self.getreg('rsp')-8);self.mem.put(self.getreg('rsp'),8,self.val(ops[0],i))
   elif m=='pop':self.put(ops[0],i,self.mem.get(self.getreg('rsp'),8));self.setreg('rsp',self.getreg('rsp')+8)
   elif m=='nop':pass
   elif m=='call':
    target=self.val(ops[0],i)
    if ops[0].type==X86_OP_MEM and ops[0].mem.base==X86_REG_RIP and self.addr(ops[0],i) in imports:
     name=imports[self.addr(ops[0],i)];assert name in ('EnterCriticalSection','LeaveCriticalSection');self.setreg('rax',0)
    elif target in self.calls:self.setreg('rax',self.calls[target](self))
    else:raise AssertionError(('unsupported call',hex(i.address),hex(target),i.op_str))
   elif m=='ret':self.finished=True;return self
   else:raise AssertionError(('unsupported instruction',hex(i.address),m,i.op_str))
   self.pc=nextpc
  raise AssertionError('bounded simulation instruction budget')

