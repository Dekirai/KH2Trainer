"""Strict mapped-byte, limited original-instruction interpreter for two bodies.

All reads require explicit synthetic bytes. This is an instruction-result model,
not a runtime-memory/lifetime proof. No game code is executed.
"""
import struct
from capstone import CS_OP_REG, CS_OP_IMM, CS_OP_MEM
from discover import base, raw, cs

class VM:
 def __init__(self):self.reg={};self.mem={};self.steps=0;self.stores=[];self.flags=(False,False,False)
 def map(self,a,b):self.mem.update({a+i:v for i,v in enumerate(b)})
 def read(self,a,n):
  assert all(a+i in self.mem for i in range(n)),('unmapped read',hex(a),n)
  return int.from_bytes(bytes(self.mem[a+i]for i in range(n)),'little')
 def write(self,a,n,v):
  assert all(a+i in self.mem for i in range(n)),('unmapped write',hex(a),n)
  self.map(a,(v&((1<<(n*8))-1)).to_bytes(n,'little'));self.stores.append((a,n))
 def alias(self,n):
  aliases={'eax':'rax','ecx':'rcx','edx':'rdx','ebx':'rbx','esp':'rsp','ebp':'rbp','esi':'rsi','edi':'rdi'}
  return aliases.get(n,n[:-1]if n.startswith('r')and n.endswith('d')else n)
 def get(self,n):return self.reg.get(self.alias(n),0)&((1<<32)-1 if n.startswith('e')or n.endswith('d')else(1<<128)-1 if n.startswith('xmm')else(1<<64)-1)
 def put(self,n,v):self.reg[self.alias(n)]=v&((1<<32)-1 if n.startswith('e')or n.endswith('d')else(1<<128)-1 if n.startswith('xmm')else(1<<64)-1)
 def ea(self,x,o):
  m=o.mem; b=x.address+x.size if x.reg_name(m.base)=='rip' else self.get(x.reg_name(m.base))if m.base else 0
  return (b+(self.get(x.reg_name(m.index))*m.scale if m.index else 0)+m.disp)&((1<<64)-1)
 def val(self,x,o):
  if o.type==CS_OP_IMM:return o.imm
  if o.type==CS_OP_REG:return self.get(x.reg_name(o.reg))
  if o.type==CS_OP_MEM:return self.read(self.ea(x,o),o.size)
  raise AssertionError(o.type)
 def set(self,x,o,v):
  if o.type==CS_OP_REG:self.put(x.reg_name(o.reg),v)
  elif o.type==CS_OP_MEM:self.write(self.ea(x,o),o.size,v)
  else:raise AssertionError(o.type)
 def signed(self,v,bits):v&=(1<<bits)-1;return v-(1<<bits)if v&(1<<(bits-1))else v
 def flag(self,a,b,r,bits,sub=False):
  mask=(1<<bits)-1;s=1<<(bits-1);r&=mask
  ov=bool(((a^b)&(a^r)&s)if sub else(~(a^b)&(a^r)&s));self.flags=(r==0,bool(r&s),ov)
 def run(self,rva,size):
  code={x.address:x for x in cs.disasm(raw(rva,size),base+rva)};pc=base+rva
  while True:
   x=code[pc];self.steps+=1;assert self.steps<100000
   m=x.mnemonic;o=x.operands;n=pc+x.size
   if m=='ret':return self.get('rax')
   if m=='push':self.put('rsp',self.get('rsp')-8);self.write(self.get('rsp'),8,self.val(x,o[0]))
   elif m=='pop':self.set(x,o[0],self.read(self.get('rsp'),8));self.put('rsp',self.get('rsp')+8)
   elif m in ('mov','movups','movaps','movsd'):self.set(x,o[0],self.val(x,o[1]))
   elif m=='movsxd':self.set(x,o[0],self.signed(self.val(x,o[1]),32))
   elif m=='lea':self.set(x,o[0],self.ea(x,o[1]))
   elif m in ('xor','test'):
    a,b=self.val(x,o[0]),self.val(x,o[1]);v=a^b if m=='xor'else a&b
    bits=o[0].size*8;v&=(1<<bits)-1;self.flags=(v==0,bool(v&(1<<(bits-1))),False)
    if m=='xor':self.set(x,o[0],v)
   elif m in ('add','sub','cmp','inc'):
    a=self.val(x,o[0]);b=1 if m=='inc'else self.val(x,o[1]);sub=m in ('sub','cmp');v=a-b if sub else a+b
    self.flag(a,b,v,o[0].size*8,sub)
    if m!='cmp':self.set(x,o[0],v)
   elif m in ('je','jne','jl','jle'):
    z,s,v=self.flags;take={'je':z,'jne':not z,'jl':s!=v,'jle':z or s!=v}[m]
    if take:n=self.val(x,o[0])
   else:raise AssertionError((hex(pc),m,x.op_str))
   pc=n

def run_cases():
 cases=checks=steps=0;table=base+0x724340;targets=[0x1c7f40,0x1c8950,0x1ca6e0,0x1c8100,0x1c8610,0x1c8700,0x1c8440]
 outputs=[]
 for poison in range(256):
  v=VM();v.map(table,raw(0x724340,504));v.map(0x10000,bytes([poison])*512);v.put('rsp',0x10100);v.put('rbp',0x22334455)
  v.run(0x96b0,0x26c);cases+=1;steps+=v.steps
  assert v.get('rsp')==0x10100 and v.get('rbp')==0x22334455;checks+=2
  for k,t in enumerate(targets):
   a=table+k*72;assert v.read(a+8,8)==base+t;assert v.read(a+16,12)==0;assert v.read(a+28,4)==int.from_bytes(bytes([poison])*4,'little');checks+=3
  assert all(table<=a and a+n<=table+504 or 0x10000<=a and a+n<=0x10200 for a,n in v.stores);checks+=1
  if poison in (0,165,255):outputs.append({'stackPoison':poison,'rows':[{'index':k,'pointer':hex(v.read(table+k*72+8,8)),'keyTail':v.read(table+k*72+16,12),'padding28':hex(v.read(table+k*72+28,4))}for k in range(7)]})
  state=dict(v.mem)
  # Execute the accepted original lookup body, not a rewritten lookup loop.
  for target in targets+[0x123456]:
   w=VM();w.mem=dict(state);w.map(0x20000,bytes(64));w.map(0x30000,struct.pack('<QIII',base+target,0,0,0));w.write(0x20018,4,7);w.write(0x20020,8,table);w.put('rcx',0x20000);w.put('rdx',0x30000);w.put('rsp',0x10100)
   got=w.run(0x1cd150,115);expected=table+targets.index(target)*72 if target in targets else 0
   assert got==expected;checks+=1;cases+=1;steps+=w.steps
 # Changes to any compared key-tail field prevent the nonzero function match.
 for offset in (8,12,16):
  w=VM();w.mem=dict(state);w.map(0x20000,bytes(64));w.map(0x30000,struct.pack('<QIII',base+0x1c8610,0,0,0));w.write(0x30000+offset,4,1);w.write(0x20018,4,7);w.write(0x20020,8,table);w.put('rcx',0x20000);w.put('rdx',0x30000);w.put('rsp',0x10100)
  assert w.run(0x1cd150,115)==0;cases+=1;checks+=1;steps+=w.steps
 return dict(cases=cases,checks=checks,interpretedInstructions=steps,examples=outputs,limits='Only initializer0096B0 and reused lookup1CD150 interpreted. Explicit synthetic table/stack/personality/key maps; read/write bounds enforce fixture mapping, not native memory safety. Stack poison is uniform for each of256 cases; no game execution, allocator/lifetime or full startup emulation.')
