"""New reviewer-only integer instruction fixture; no author VM reuse."""
from itertools import product
from capstone.x86_const import X86_OP_IMM, X86_OP_REG, X86_OP_MEM, X86_REG_RIP
B=0x140000000; MASK=(1<<64)-1
def signed(x,bits):
    x&=(1<<bits)-1
    return x-(1<<bits) if x>>(bits-1) else x

def run(instructions,pe_read,imports,check):
    class Machine:
        def __init__(self,start):
            self.pc=B+start;self.regs={'rsp':0x900000};self.memory={};self.calls={};self.events=[];self.reads=[]
            self.flags={'z':False,'s':False,'o':False,'c':False};self.exit=None
        def alias(self,n):
            aliases={'eax':('rax',32),'ax':('rax',16),'al':('rax',8),'ebx':('rbx',32),'bx':('rbx',16),'bl':('rbx',8),
                'ecx':('rcx',32),'cx':('rcx',16),'cl':('rcx',8),'edx':('rdx',32),'dx':('rdx',16),'dl':('rdx',8),
                'edi':('rdi',32),'dil':('rdi',8),'esi':('rsi',32),'sil':('rsi',8),'ebp':('rbp',32),'esp':('rsp',32)}
            if n in aliases:return aliases[n]
            if n.startswith('r') and n[-1] in 'dwb' and n[1:-1].isdigit():return n[:-1],{'d':32,'w':16,'b':8}[n[-1]]
            return n,64
        def reg(self,n):
            n,width=self.alias(n);return self.regs.get(n,0)&((1<<width)-1)
        def setreg(self,n,v):
            n,width=self.alias(n);v&=(1<<width)-1
            self.regs[n]=v if width in (32,64) else (self.regs.get(n,0)&~((1<<width)-1))|v
        def put(self,p,n,v):
            for j in range(n):self.memory[(p+j)&MASK]=(v>>(8*j))&255
        def get(self,p,n):
            p&=MASK;self.reads.append((p,n))
            if p>=B and not any(p+j in self.memory for j in range(n)):return int.from_bytes(pe_read(p,n),'little')
            return sum(self.memory.get((p+j)&MASK,0)<<(8*j) for j in range(n))
        def ea(self,i,o):
            m=o.mem;base=i.address+i.size if m.base==X86_REG_RIP else self.reg(i.reg_name(m.base)) if m.base else 0
            return (base+(self.reg(i.reg_name(m.index))*m.scale if m.index else 0)+m.disp)&MASK
        def value(self,i,o):
            if o.type==X86_OP_IMM:return o.imm
            if o.type==X86_OP_REG:return self.reg(i.reg_name(o.reg))
            if o.type==X86_OP_MEM:return self.get(self.ea(i,o),o.size)
            raise AssertionError('unknown operand')
        def assign(self,i,o,v):
            if o.type==X86_OP_REG:self.setreg(i.reg_name(o.reg),v)
            elif o.type==X86_OP_MEM:self.put(self.ea(i,o),o.size,v)
            else:raise AssertionError('invalid assignment')
        def arithmetic(self,a,b,width,subtract):
            mask=(1<<width)-1;a&=mask;b&=mask;result=(a-b if subtract else a+b)&mask
            self.flags={'z':result==0,'s':bool(result>>(width-1)),
                'c':a<b if subtract else a+b>mask,
                'o':bool(((a^b)&(a^result) if subtract else ~(a^b)&(a^result))&(1<<(width-1)))}
            return result
        def branch(self,name):
            z,s,o,c=(self.flags[x] for x in ['z','s','o','c'])
            return {'je':z,'jne':not z,'ja':not c and not z,'jbe':c or z,'jb':c,'jae':not c,
                'jge':s==o,'jl':s!=o,'jg':not z and s==o,'jle':z or s!=o}[name]
        def run(self,stops=(),tails=()):
            stops={B+x for x in stops};tails={B+x for x in tails}
            for _ in range(2000):
                if self.pc in stops or self.pc in tails:self.exit=self.pc;return
                i=instructions[self.pc];op=i.mnemonic;x=i.operands;nextpc=self.pc+i.size
                if op in ('mov','movzx','movsxd','movsx'):
                    v=self.value(i,x[1]);self.assign(i,x[0],signed(v,8*x[1].size) if op in ('movsxd','movsx') else v)
                elif op=='lea':self.assign(i,x[0],self.ea(i,x[1]))
                elif op in ('add','sub','cmp'):
                    v=self.arithmetic(self.value(i,x[0]),self.value(i,x[1]),8*x[0].size,op!='add')
                    if op!='cmp':self.assign(i,x[0],v)
                elif op in ('and','or','xor','test'):
                    a,b=self.value(i,x[0]),self.value(i,x[1]);v=a&b if op in ('and','test') else a|b if op=='or' else a^b
                    v&=(1<<(8*x[0].size))-1;self.flags={'z':v==0,'s':bool(v>>(8*x[0].size-1)),'c':False,'o':False}
                    if op!='test':self.assign(i,x[0],v)
                elif op=='imul':
                    if len(x)!=3:raise AssertionError('only explicit three-operand IMUL in selected fixture')
                    self.assign(i,x[0],self.value(i,x[1])*self.value(i,x[2]))
                elif op=='push':self.setreg('rsp',self.reg('rsp')-8);self.put(self.reg('rsp'),8,self.value(i,x[0]))
                elif op=='pop':self.assign(i,x[0],self.get(self.reg('rsp'),8));self.setreg('rsp',self.reg('rsp')+8)
                elif op=='call':
                    if i.address in self.calls:self.calls[i.address](self)
                    elif x[0].type==X86_OP_MEM and x[0].mem.base==X86_REG_RIP and imports.get(self.ea(i,x[0])) in ('EnterCriticalSection','LeaveCriticalSection'):
                        self.events.append(imports[self.ea(i,x[0])])
                    else:raise AssertionError('unmodeled call '+hex(i.address))
                elif op=='jmp':nextpc=self.value(i,x[0])
                elif op.startswith('j'):
                    if self.branch(op):nextpc=self.value(i,x[0])
                elif op=='ret':self.exit='ret';return
                elif op=='nop':pass
                else:raise AssertionError('unmodeled instruction '+hex(i.address)+' '+op)
                self.pc=nextpc
            raise AssertionError('fixture instruction budget')

    groups={};cases=0
    def done(group):
        nonlocal cases
        cases+=1;groups[group]=groups.get(group,0)+1
    # Complete getters, including their CS call sites; synthetic caller-readable memory only.
    for version,profile,index,offset,magic in product([0,1,4,0xffffffff],[(0,4),(1,8),(255,0)],[-1,0,1,0x80000000],[-64,256],[True,False]):
        m=Machine(0x7ad30);file=0x500000;h=96
        m.setreg('rcx',file);m.setreg('edx',index);m.put(file,4,0x42444553 if magic else 0);m.put(file+4,4,0x11223344)
        m.put(file+8,4,version);m.put(file+12,1,profile[0]);m.put(file+13,1,profile[1]);m.put(file+14,2,h)
        m.put(file+h+6,2,65535);m.put(file+h+32+4*signed(index,32),4,offset);m.put(file+offset+12,2,999)
        m.run();check(m.reg('eax')==(65535*1000+999 if magic else 0xffffffff),'get-ID signed index/offset, fixed32, magic-only result')
        check(m.events==['EnterCriticalSection','LeaveCriticalSection'],'getter CS import order')
        if magic:check(((file+h+32+4*signed(index,32))&MASK,4) in m.reads and (file+offset+12,2) in m.reads,'actual signed address reads')
        done('metadata_getter')
    for h,profile,magic in product([0x40,0xfff0],[(0,4),(15,255)],[True,False]):
        m=Machine(0x7ada0);p=0x500000;m.setreg('rcx',p);m.put(p,4,0x42444553 if magic else 0)
        m.put(p+12,1,profile[0]);m.put(p+13,1,profile[1]);m.put(p+14,2,h);m.put(p+h,2,0xffee);m.run()
        check(m.reg('eax')==(0xffee if magic else 0xffffffff),'count getter exact WORD');done('count_getter')
    for rva,version in product([0xa13b0,0xa4020],[0,1,2,3,4,5,0x7fffffff,0x80000000,0xfffffffe,0xffffffff]):
        m=Machine(rva);m.setreg('rcx',0x400000 if rva==0xa13b0 else version);m.put(0x400018,4,version)
        def diagnostic(q):q.events.append('diagnostic');q.setreg('rax',0xabcdef)
        m.calls[B+(0xa13f5 if rva==0xa13b0 else 0xa4062)]=diagnostic;m.run()
        expected=16 if version==1 else 32 if version in (2,3,4) else 0
        check(m.reg('eax')==expected and m.events==([] if expected else ['diagnostic']),'unsigned version partition and postcallback zero');done('size_helpers')
    for flags,index in product(range(256),[0,1,0x100,0x10000,0xffffffff]):
        m=Machine(0xa2840);m.setreg('rcx',0x400000);m.setreg('edx',index);m.put(0x400080,1,flags);m.run(tails=[0x9fd20])
        check((m.exit==B+0x9fd20)==bool(flags&2 and index==0),'full DWORD index and flag2 delegate');done('sequence_wrapper')
    # Enter only state0 with progress already80. Provider scheduling remains outside this fixture.
    for capacity,magic,counts,version in product([-1,79,80,81],[(1,1),(1,0),(0,1)],[(1,1,1),(0,1,1),(1,2,1),(1,1,0)],[0,4,0xffffffff]):
        m=Machine(0xa362e);sub=0x4000a0;bank=0x400000;file=0x500000
        m.setreg('rdi',sub);m.setreg('r13d',0);m.put(sub+48,4,capacity);m.put(sub+64,4,80);m.put(sub+40,8,file)
        m.put(bank+128,1,0x95);m.put(bank+24,4,0x11111111);m.put(bank+48,4,0x22222222);m.put(bank+28,4,0x33333333)
        m.put(file,4,0x42444553 if magic[0] else 0);m.put(file+4,4,0x46435353 if magic[1] else 0)
        m.put(file+8,4,version);m.put(file+12,2,0xfefd);m.put(file+14,2,0x7777);m.put(file+16,4,0xffffffff)
        for p,v in zip([48,50,52],counts):m.put(file+p,2,v)
        m.put(file+54,2,0xffee)
        def state(q):q.events.append(('state',q.reg('rcx'),q.reg('edx')))
        m.calls[B+0xa377a]=state;m.run(stops=[0xa3ecf,0xa3eee])
        copied=capacity>=80 and all(magic);accepted=copied and counts==(1,1,1)
        check(m.get(bank+24,4)==(version if copied else 0x11111111) and m.get(bank+48,4)==(0xffffffff if copied else 0x22222222),'version/length copy precedes count acceptance')
        check(m.events==([('state',bank,1)] if accepted else []),'fixed-count header gate state transition')
        check(m.get(bank+128,1)==(0x95 if accepted else ((0x95&0x7d)|2)),'failed capacity/signature/count flags')
        check(m.get(bank+28,4)==(0xffee if accepted else 0x33333333),'absolute bank ID accepted only after counts')
        done('state0_header')
    for length,allocation in product([0,1,0x7fffffff,0x80000000,0xfffffffe,0xffffffff],[0,0x600000]):
        m=Machine(0xa09c2);file=0x500000;bank=0x400000;m.setreg('rdx',file);m.put(file+16,4,length)
        m.run(stops=[0xa09c6]);check(m.reg('rbx')==(signed(length,32)&MASK),'original MOVSXD header length')
        m.pc=B+0xa0a06;m.setreg('rsi',file);m.setreg('rbp',bank)
        allocator_load=instructions[B+0xa0a11];m.put(m.ea(allocator_load,allocator_load.operands[1]),8,0x880000)
        def alloc(q):q.events.append(('allocate',q.reg('rdx')));q.setreg('rax',allocation)
        def copy(q):q.events.append(('memcpy',q.reg('rcx'),q.reg('rdx'),q.reg('r8')));q.setreg('rax',allocation)
        m.calls={B+0xa0a18:alloc,B+0xa0a29:copy};m.run(stops=[0xa0a32])
        signedsize=signed(length,32)&MASK
        check(m.events==[('allocate',signedsize),('memcpy',allocation,file,signedsize)] and m.get(bank+8,8)==allocation,'allocator/copy suffix forwards signed size and null allocation')
        done('signed_copy_suffix')
    # Selected standby arithmetic block; no pending handle, provider, or callback semantics assumed.
    for length,subtract in product([0,1,0x7fffffff,0x80000000,0xffffffff],[0,1,65535]):
        m=Machine(0xa2303);file=0x500000;bank=0x400000;m.setreg('rdx',file);m.setreg('rdi',bank)
        m.put(file+14,2,80);m.put(file+8,4,0x12345678);m.put(file+16,4,length);m.put(file+108,2,subtract)
        m.calls[B+0xa2341]=lambda q:q.events.append('diagnostic');m.run(stops=[0xa2347])
        check(m.get(bank+24,4)==0x12345678 and m.get(bank+48,4)==((length-subtract)&0xffffffff) and m.events==['diagnostic'],'standby DWORD minus WORD wraps')
        done('standby_arithmetic')
    for old,source,table in product([0,0x600000],[0x600000,0x700000],[B+0x61cb70,0x800000]):
        m=Machine(0xa0b00);bank=0x400000;m.setreg('rcx',bank);m.setreg('rdx',source);m.put(bank,8,table);m.put(bank+8,8,old)
        m.calls[B+0xa0b10]=lambda q:q.events.append('unlink')
        m.calls[B+0xa0b1e]=lambda q:q.events.append(('cleanup',q.reg('rcx')))
        def rebind(q):q.events.append(('copy',q.reg('rdx'),q.get(bank+8,8)));q.put(bank+8,8,0x900000)
        m.calls[B+0xa0b31]=rebind;m.calls[B+0xa0b53]=lambda q:q.events.append('virtual16');m.run()
        expected=['unlink']+([('cleanup',old)] if old else [])+[('copy',source,0)]+(['virtual16'] if table!=B+0x61cb70 else [])
        check(m.events==expected,'rebind order and absent local source-alias guard');done('rebind_order')
    return {'cases':cases,'groups':groups,'limits':'Independent selected original-instruction fixture over synthetic memory. Helper side effects explicitly stubbed; TLS, full streaming scheduler, provider calls and native memory execution excluded.'}
