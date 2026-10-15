"""Bounded interpreter of selected, independently decoded original instructions.

Adapted from this reviewer's selected_machine.py in the Gummi action review.
This is a synthetic fixture, not native execution. SSE uses round-to-nearest
float32 with masked invalid/divide exceptions, without DAZ/FTZ. It does not model
MXCSR exception flags, NaN payload identity, asynchronous mutation, or lifetime.
"""
import math,struct
from capstone.x86_const import X86_OP_IMM,X86_OP_REG,X86_OP_MEM,X86_REG_RIP
B=0x140000000; MASK=(1<<64)-1; STACK=0x900008
def signed(v,n):
    v&=(1<<n)-1
    return v-(1<<n) if v>>(n-1) else v
def bits(v):
    try:return struct.unpack('<I',struct.pack('<f',v))[0]
    except OverflowError:return 0xff800000 if v<0 else 0x7f800000
def floating(v):return struct.unpack('<f',struct.pack('<I',v&0xffffffff))[0]
def f32(v):return floating(bits(v))
def divide(a,b):
    if b==0:
        if a==0 or math.isnan(a):return float('nan')
        return math.copysign(float('inf'),math.copysign(1,a)*math.copysign(1,b))
    return a/b
class Machine:
    def __init__(self,instructions,pe_read):
        self.ins=instructions;self.pe_read=pe_read;self.regs={'rsp':STACK};self.memory={};self.flags=dict(z=False,s=False,o=False,c=False)
        self.steps=0;self.events=[];self.visited=set();self.stubs={B+0x439a60:lambda m:None};self.depth=0
        self.allocate(STACK-0x10000,0x10200);self.put(STACK,8,0)
    def allocate(self,p,n):
        if any(p+j in self.memory for j in range(n)):raise AssertionError('overlapping allocation')
        self.memory.update({p+j:0 for j in range(n)})
    def alias(self,n):
        if n.startswith('xmm'):return n,128
        for root,aliases in [('rax',['eax','ax','al']),('rbx',['ebx','bx','bl']),('rcx',['ecx','cx','cl']),('rdx',['edx','dx','dl']),('rsi',['esi','si','sil']),('rdi',['edi','di','dil']),('rbp',['ebp','bp','bpl']),('rsp',['esp','sp','spl'])]:
            if n in aliases:return root,[32,16,8][aliases.index(n)]
        if n.startswith('r') and n[-1] in 'dwb' and n[1:-1].isdigit():return n[:-1],{'d':32,'w':16,'b':8}[n[-1]]
        return n,64
    def reg(self,n):
        root,w=self.alias(n);return self.regs.get(root,0)&((1<<w)-1)
    def setreg(self,n,v):
        root,w=self.alias(n);mask=(1<<w)-1
        self.regs[root]=(v&mask) if w in (32,64,128) else (self.regs.get(root,0)&~mask)|(v&mask)
    def get(self,p,n):
        if all(p+j in self.memory for j in range(n)):return int.from_bytes(bytes(self.memory[p+j] for j in range(n)),'little')
        if p>=B:return int.from_bytes(self.pe_read(p,n),'little')
        raise AssertionError('unallocated synthetic read '+hex(p))
    def put(self,p,n,v):
        if not all(p+j in self.memory for j in range(n)):raise AssertionError('unallocated synthetic write '+hex(p))
        for j in range(n):self.memory[p+j]=(v>>(j*8))&255
    def vector(self,p,vs):
        for j,v in enumerate(vs):self.put(p+j*4,4,bits(v))
    def floats(self,p,n=4):return tuple(floating(self.get(p+j*4,4)) for j in range(n))
    def ea(self,i,o):
        m=o.mem;base=i.address+i.size if m.base==X86_REG_RIP else self.reg(i.reg_name(m.base)) if m.base else 0
        return (base+(self.reg(i.reg_name(m.index))*m.scale if m.index else 0)+m.disp)&MASK
    def value(self,i,o):
        if o.type==X86_OP_IMM:return o.imm
        if o.type==X86_OP_REG:return self.reg(i.reg_name(o.reg))
        if o.type==X86_OP_MEM:return self.get(self.ea(i,o),o.size)
        raise AssertionError('operand')
    def assign(self,i,o,v):
        if o.type==X86_OP_REG:self.setreg(i.reg_name(o.reg),v)
        elif o.type==X86_OP_MEM:self.put(self.ea(i,o),o.size,v)
        else:raise AssertionError('destination')
    def scalar(self,i,o,v):
        if o.type==X86_OP_REG and i.reg_name(o.reg).startswith('xmm'):v=(self.value(i,o)&~0xffffffff)|(v&0xffffffff)
        self.assign(i,o,v)
    def arithmetic(self,a,b,w,sub):
        mask=(1<<w)-1;a&=mask;b&=mask;r=(a-b if sub else a+b)&mask
        self.flags=dict(z=r==0,s=bool(r>>(w-1)),c=a<b if sub else a+b>mask,o=bool(((a^b)&(a^r) if sub else ~(a^b)&(a^r))&(1<<(w-1))))
        return r
    def branch(self,op):
        z,s,o,c=(self.flags[x] for x in ('z','s','o','c'))
        return dict(je=z,jne=not z,ja=not c and not z,jbe=c or z,jb=c,jae=not c,jge=s==o,jl=s!=o,jg=not z and s==o,jle=z or s!=o,js=s,jns=not s,jp=self.flags.get('p',False),jnp=not self.flags.get('p',False))[op]
    def invoke(self,rva,args=(),budget=1000000):
        for name,v in zip(['rcx','rdx','r8','r9'],args):self.setreg(name,v)
        for j,v in enumerate(args[4:]):self.put(self.reg('rsp')+40+j*8,8,v)
        self.pc=B+rva
        for _ in range(budget):
            self.steps+=1;self.visited.add(self.pc);i=self.ins[self.pc];op=i.mnemonic;x=i.operands;nxt=self.pc+i.size
            if op in ('mov','movabs','movzx','movsx','movsxd','movups','movaps','movd'):
                v=self.value(i,x[1]);self.assign(i,x[0],signed(v,x[1].size*8) if op in ('movsx','movsxd') else v)
            elif op=='movss':
                v=self.value(i,x[1])&0xffffffff
                if x[1].type==X86_OP_MEM:self.assign(i,x[0],v)
                else:self.scalar(i,x[0],v)
            elif op=='lea':self.assign(i,x[0],self.ea(i,x[1]))
            elif op in ('add','sub','cmp'):
                v=self.arithmetic(self.value(i,x[0]),self.value(i,x[1]),x[0].size*8,op!='add')
                if op!='cmp':self.assign(i,x[0],v)
            elif op in ('inc','dec'):
                c=self.flags['c'];v=self.arithmetic(self.value(i,x[0]),1,x[0].size*8,op=='dec');self.flags['c']=c;self.assign(i,x[0],v)
            elif op in ('and','or','xor','test','xorps'):
                a,b=(self.value(i,o) for o in x);v=a&b if op in ('and','test') else a|b if op=='or' else a^b;v&=(1<<(x[0].size*8))-1
                if op!='xorps':self.flags=dict(z=v==0,s=bool(v>>(x[0].size*8-1)),c=False,o=False)
                if op!='test':self.assign(i,x[0],v)
            elif op in ('shl','shr'):
                a,n=(self.value(i,o) for o in x);w=x[0].size*8;n&=63 if w==64 else 31
                v=(a<<n)&((1<<w)-1) if op=='shl' else a>>n
                if n:
                    carry=bool((a>>(w-n if op=='shl' else n-1))&1)
                    overflow=bool(v>>(w-1))!=carry if op=='shl' else bool(a>>(w-1))
                    self.flags=dict(z=v==0,s=bool(v>>(w-1)),c=carry,o=overflow)
                self.assign(i,x[0],v)
            elif op=='not':self.assign(i,x[0],~self.value(i,x[0]))
            elif op in ('bt','bts'):
                assert x[0].type==X86_OP_REG, 'Selected BT/BTS supports register destination only'
                value=self.value(i,x[0]);bit=self.value(i,x[1])%(x[0].size*8)
                self.flags['c']=bool((value>>bit)&1)
                if op=='bts':self.assign(i,x[0],value|(1<<bit))
            elif op.startswith('set'):self.assign(i,x[0],int(self.branch('j'+op[3:])))
            elif op.startswith('cmov'):
                if self.branch('j'+op[4:]):self.assign(i,x[0],self.value(i,x[1]))
            elif op in ('comiss','ucomiss'):
                a,b=(floating(self.value(i,o)) for o in x);u=math.isnan(a) or math.isnan(b);self.flags=dict(z=u or a==b,c=u or a<b,s=False,o=False,p=u)
            elif op in ('addss','subss','mulss','divss','minss','maxss'):
                a,b=(floating(self.value(i,o)) for o in x)
                v=a+b if op=='addss' else a-b if op=='subss' else a*b if op=='mulss' else divide(a,b) if op=='divss' else (a if a>b else b) if op=='maxss' else a if a<b else b
                self.scalar(i,x[0],bits(v))
            elif op=='mulps':
                a,b=(self.value(i,o) for o in x);self.assign(i,x[0],sum(bits(floating(a>>(32*k))*floating(b>>(32*k)))<<(32*k) for k in range(4)))
            elif op=='shufps':
                a,b,c=(self.value(i,o) for o in x);self.assign(i,x[0],sum((((a if k<2 else b)>>(32*((c>>(2*k))&3)))&0xffffffff)<<(32*k) for k in range(4)))
            elif op=='cvttss2si':
                v=floating(self.value(i,x[1]));w=x[0].size*8;v=math.trunc(v) if math.isfinite(v) else -(1<<(w-1));v=v if -(1<<(w-1))<=v<(1<<(w-1)) else -(1<<(w-1));self.assign(i,x[0],v)
            elif op=='cvtdq2ps':self.assign(i,x[0],sum(bits(signed(self.value(i,x[1])>>(32*k),32))<<(32*k) for k in range(4)))
            elif op=='push':self.setreg('rsp',self.reg('rsp')-8);self.put(self.reg('rsp'),8,self.value(i,x[0]))
            elif op=='pop':self.assign(i,x[0],self.get(self.reg('rsp'),8));self.setreg('rsp',self.reg('rsp')+8)
            elif op=='call':
                target=self.value(i,x[0]);self.events.append(hex(target))
                if target in self.stubs:self.stubs[target](self)
                else:
                    self.depth+=1
                    if self.depth>128:raise AssertionError('fixture recursion budget')
                    self.setreg('rsp',self.reg('rsp')-8);self.put(self.reg('rsp'),8,nxt);nxt=target
            elif op=='ret':
                nxt=self.get(self.reg('rsp'),8);self.setreg('rsp',self.reg('rsp')+8);self.depth-=1
                if not nxt:return self.reg('rax')
            elif op=='jmp':
                nxt=self.value(i,x[0])
                if nxt in self.stubs:
                    self.events.append(hex(nxt));self.stubs[nxt](self)
                    nxt=self.get(self.reg('rsp'),8);self.setreg('rsp',self.reg('rsp')+8);self.depth-=1
                    if not nxt:return self.reg('rax')
            elif op.startswith('j'):
                if self.branch(op):nxt=self.value(i,x[0])
            elif op=='nop':pass
            else:raise AssertionError('unsupported '+hex(i.address)+' '+op)
            self.pc=nxt
        raise AssertionError('fixture instruction budget')
