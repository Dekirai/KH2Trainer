"""Small fail-closed interpreter of original x64 bytes, versus an independent phase model.

This is not native execution and not a general x86 emulator. Unsupported opcodes,
unexpected calls or reads outside mapped synthetic/PE spans fail immediately.
External ship dispatch calls are recorded only; no claim of projectile emission.
"""
import copy, math, struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_REG, X86_OP_IMM, X86_OP_MEM

COMBO=0x100000; STACK=0x200000; MAIN=0x300000; COMP1=0x400000; COMP2=0x500000
def f32(x): return struct.unpack('<f',struct.pack('<f',x))[0]
def bits(x): return struct.unpack('<I',struct.pack('<f',x))[0]
def flt(x): return struct.unpack('<f',int(x&0xffffffff).to_bytes(4,'little'))[0]
def signed(x,size):
    bit=1<<(size*8-1); return (x&(bit-1))-(x&bit)

class Machine:
    def __init__(self,pe,state):
        self.pe=pe; self.mem={}; self.regs={}; self.flags={}; self.calls=[]; self.trace=[]
        self.md=Cs(CS_ARCH_X86,CS_MODE_64);self.md.detail=True
        self.map(COMBO,bytes(256));self.map(STACK-1024,bytes(2048))
        self.setreg('rcx',COMBO); self.setreg('rsp',STACK); self.setreg('rbx',0x5555)
        for off,val in [(0,state['phase']),(52,state['index']),(56,state['progress']),(60,state['stock']),(64,bits(state['timer'])),(68,state['flags'])]: self.write(COMBO+off,4,val)
        for off,val in [(8,MAIN),(16,state['companions'][0]),(24,state['companions'][1])]:self.write(COMBO+off,8,val)
        for i,val in enumerate(state['counts']):self.write(COMBO+32+4*i,4,val)
        self.step=state['step']
    def map(self,addr,data): self.mem.update({addr+i:b for i,b in enumerate(data)})
    def read(self,addr,size):
        if all(addr+i in self.mem for i in range(size)):return int.from_bytes(bytes(self.mem[addr+i] for i in range(size)),'little')
        return int.from_bytes(self.pe.bytes(addr,size),'little')
    def write(self,addr,size,value):
        assert all(addr+i in self.mem for i in range(size)), f'Unexpected write {addr:x}'
        self.map(addr,(value&((1<<(8*size))-1)).to_bytes(size,'little'))
    def alias(self,name):
        if name.startswith('xmm'):return name,128
        table={'eax':('rax',32),'ax':('rax',16),'al':('rax',8),'ecx':('rcx',32),'cl':('rcx',8),'edx':('rdx',32),'dl':('rdx',8),'ebx':('rbx',32),'bl':('rbx',8),'esp':('rsp',32),'r8d':('r8',32)}
        return table.get(name,(name,64))
    def reg(self,name):
        root,n=self.alias(name);return self.regs.get(root,0)&((1<<n)-1)
    def setreg(self,name,val):
        root,n=self.alias(name);mask=(1<<n)-1
        self.regs[root]=val&mask if n>=32 else (self.regs.get(root,0)&~mask)|(val&mask)
    def ea(self,op,ins):
        m=op.mem; base=ins.address+ins.size if ins.reg_name(m.base)=='rip' else self.reg(ins.reg_name(m.base)) if m.base else 0
        return (base+(self.reg(ins.reg_name(m.index))*m.scale if m.index else 0)+m.disp)&((1<<64)-1)
    def get(self,op,ins):
        if op.type==X86_OP_IMM:return op.imm&((1<<(8*op.size))-1)
        if op.type==X86_OP_REG:return self.reg(ins.reg_name(op.reg))
        if op.type==X86_OP_MEM:return self.read(self.ea(op,ins),op.size)
        raise AssertionError('Unsupported operand')
    def put(self,op,ins,val):
        if op.type==X86_OP_REG:self.setreg(ins.reg_name(op.reg),val)
        elif op.type==X86_OP_MEM:self.write(self.ea(op,ins),op.size,val)
        else:raise AssertionError('Unsupported destination')
    def intflags(self,a,b,size,subtract=True):
        mask=(1<<(size*8))-1; high=1<<(size*8-1);a&=mask;b&=mask
        r=(a-b)&mask if subtract else a&b
        self.flags={'zf':r==0,'sf':bool(r&high),'cf':a<b if subtract else False,'of':bool((a^b)&(a^r)&high) if subtract else False}
    def cond(self,name):
        f=self.flags;z=f.get('zf',False);s=f.get('sf',False);o=f.get('of',False);c=f.get('cf',False)
        return {'e':z,'ne':not z,'a':not c and not z,'b':c,'ge':s==o,'g':not z and s==o,'le':z or s!=o,'l':s!=o}[name]
    def run(self,start):
        ip=start
        for _ in range(2000):
            # Decode one real original instruction; no JSON instruction string drives execution.
            ins=next(self.md.disasm(self.pe.bytes(ip,15),ip,count=1));self.trace.append(hex(ip));ip+=ins.size
            op=ins.operands;m=ins.mnemonic
            a=lambda n:self.get(op[n],ins)
            w=lambda v:self.put(op[0],ins,v)
            if m=='ret':return
            elif m=='push':self.setreg('rsp',self.reg('rsp')-8);self.write(self.reg('rsp'),8,a(0))
            elif m=='pop':w(self.read(self.reg('rsp'),8));self.setreg('rsp',self.reg('rsp')+8)
            elif m in ('mov','movzx','movss'):w(a(1))
            elif m=='movsxd':w(signed(a(1),op[1].size))
            elif m=='lea':w(self.ea(op[1],ins))
            elif m in ('cmp','test'):self.intflags(a(0),a(1),op[0].size,m=='cmp')
            elif m=='comiss':
                x,y=flt(a(0)),flt(a(1));nan=math.isnan(x) or math.isnan(y)
                self.flags={'zf':nan or x==y,'cf':nan or x<y,'sf':False,'of':False}
            elif m=='addss':w(bits(f32(flt(a(0))+flt(a(1)))))
            elif m in ('or','and','xor'):
                v={'or':lambda x,y:x|y,'and':lambda x,y:x&y,'xor':lambda x,y:x^y}[m](a(0),a(1));w(v);self.intflags(v,v,op[0].size,False)
            elif m=='shr':w(a(0)>>a(1))
            elif m in ('add','sub','inc'):
                x=a(0);y=1 if m=='inc' else a(1);v=x-y if m=='sub' else x+y
                w(v)
                if m=='sub':self.intflags(x,y,op[0].size)
                else:
                    mask=(1<<(op[0].size*8))-1;high=1<<(op[0].size*8-1);r=v&mask
                    self.flags={'zf':r==0,'sf':bool(r&high),'cf':v>mask,'of':bool(~(x^y)&(x^r)&high)}
            elif m=='setge':w(int(self.cond('ge')))
            elif m=='jmp':ip=a(0)
            elif m.startswith('j'):
                if self.cond(m[1:]):ip=a(0)
            elif m=='call':
                target=a(0)
                if target==0x140154430:self.setreg('xmm0',bits(self.step))
                elif target==0x1401fbc50:self.calls.append(['main',self.reg('rcx'),self.reg('edx')])
                elif target==0x1401fbcb0:self.calls.append(['companion',self.reg('rcx')])
                else:raise AssertionError(f'Unexpected call {target:x}')
                # Call hooks only emulate declared observable return/no combo mutation.
            elif m=='nop':pass
            else:raise AssertionError(f'Unsupported {m} at {ins.address:x}')
        raise AssertionError('Instruction budget reached')
    def state(self,original):
        out=copy.deepcopy(original)
        for key,off in [('phase',0),('index',52),('progress',56),('stock',60),('flags',68)]:out[key]=self.read(COMBO+off,4)
        out['timer']=flt(self.read(COMBO+64,4));return out

def reference(s):
    s=copy.deepcopy(s);calls=[]
    if not s['flags']&1:return s,calls
    p=s['phase'];t=s['timer'];i=s['index'];request=bool(s['flags']&2)
    if p==0 and request and s['stock']>0:
        if s['flags']&4:s['flags']&=~4;s['progress']=0
        s['stock']-=1;s['phase']=2
    elif p==1:
        if t>=[0.,0.,10.,10.,20.][i]:s['phase']=2
    elif p==2:
        if i<5:calls.append(['main',MAIN,[621,605,606,607,608][i]])
        i+=1
        while i<5 and s['counts'][i]<=0:i+=1
        s['index']=i;s['phase']=3 if i<5 else 4;s['timer']=0.
    elif p==3:
        if t>50:s['phase']=5;s['timer']=0.
        elif t>=10 and request:s['phase']=1
    elif p==4 and t>=4:
        calls.extend(['companion',p] for p in s['companions'] if p);s['phase']=5;s['timer']=0.
    elif p==5 and t>=40:
        s['phase']=0;s['index']=next((i for i,n in enumerate(s['counts']) if n>0),5);s['timer']=0.
    s['timer']=f32(s['timer']+s['step']);s['flags']&=~2
    return s,calls

def baseline(**kw):
    d=dict(phase=0,index=0,progress=66,stock=1,timer=0.,flags=1,counts=[1,1,1,1,1],companions=[COMP1,COMP2],step=1.)
    d.update(kw);return d

def run(pe):
    cases=[]
    for stock in [0,1,9]:
        for flags in [1,3,5,7]:cases.append((f'idle-stock-{stock}-flags-{flags}',baseline(stock=stock,flags=flags)))
    for t in [0.,9.999999046325684,10.,49.999996185302734,50.,50.000003814697266]:
        for request in [False,True]:cases.append((f'window-{t}-request-{request}',baseline(phase=3,index=2,stock=0,timer=t,flags=1|(2 if request else 0))))
    for index in range(5):
        for t in sorted(set([0.,max(0.,[0.,0.,10.,10.,20.][index]-.5),[0.,0.,10.,10.,20.][index]])):
            cases.append((f'wait-{index}-{t}',baseline(phase=1,index=index,timer=t,flags=3)))
    for index in range(6):
        for counts in [[1,1,1,1,1],[0,0,0,0,0],[1,0,0,0,1]]:
            cases.append((f'stage-{index}-{counts}',baseline(phase=2,index=index,counts=counts,flags=3)))
    for t in [3.999999761581421,4.,40.]:
        for companions in [[0,0],[COMP1,0],[0,COMP2],[COMP1,COMP2]]:
            cases.append((f'companion-{t}-{companions}',baseline(phase=4,index=6,timer=t,companions=companions,flags=3)))
    for t in [39.999996185302734,40.,41.]:
        for first in range(6):cases.append((f'recovery-{t}-first-{first}',baseline(phase=5,index=6,timer=t,counts=[int(i==first) for i in range(5)],flags=3)))
    for phase in range(6):cases.append((f'uninstalled-{phase}',baseline(phase=phase,flags=2)))
    for phase in [6,0xffffffff]:cases.append((f'invalid-phase-{phase}',baseline(phase=phase,flags=3)))
    for step in [0.,.5,2.]:cases.append((f'global-step-{step}',baseline(phase=2,step=step,flags=3)))
    results=[];checks=0;steps=0
    for name,state in cases:
        m=Machine(pe,state);m.run(0x140230d20);expected,calls=reference(state)
        assert m.state(state)==expected,(name,m.state(state),expected)
        assert m.calls==calls,(name,m.calls,calls)
        # Counts and pointer slots are immutable in this body (external hooks do not write them).
        assert [m.read(COMBO+32+4*i,4) for i in range(5)]==state['counts']
        assert [m.read(COMBO+x,8) for x in (8,16,24)]==[MAIN]+state['companions']
        checks+=4;steps+=len(m.trace)
        results.append({'name':name,'input':state,'output':m.state(state),'calls':m.calls,'instructionSteps':len(m.trace)})
    # Lifecycle traces prove pulses are not retained/auto-chained and that stock is consumed once.
    traces=[]
    for name,pulses,initial in [('single-pulse', {0},baseline()),('full-native-chain',{0,11,23,35,47},baseline()),('early-followup-pulses',{0,11,22,33,44},baseline()),('companion-only',{0},baseline(index=5,counts=[0]*5))]:
        state=initial;calls=[];phases=[];nsteps=0
        for frame in range(120):
            m=Machine(pe,state)
            if frame in pulses:
                before=bytes(m.mem[COMBO+i] for i in range(72));m.run(0x1402312b0)
                after=bytes(m.mem[COMBO+i] for i in range(72))
                expected=bytearray(before);struct.pack_into('<I',expected,68,struct.unpack_from('<I',expected,68)[0]|2)
                assert after==expected;checks+=1
                state=dict(state,flags=state['flags']|2)
            m.setreg('rcx',COMBO);m.run(0x140230d20);expected,framecalls=reference(state)
            assert m.state(state)==expected and m.calls==framecalls;checks+=1
            state=m.state(state);calls.extend([frame]+c for c in m.calls);phases.append(state['phase']);nsteps+=len(m.trace)
        assert state['stock']==0;checks+=1
        assert not any(c[0]==0 for c in calls);checks+=1
        if name=='single-pulse':assert [c[3] for c in calls if c[1]=='main']==[621];checks+=1
        if name=='full-native-chain':assert [c[3] for c in calls if c[1]=='main']==[621,605,606,607,608] and [c[2] for c in calls if c[1]=='companion']==[COMP1,COMP2];checks+=1
        if name=='early-followup-pulses':assert [c[3] for c in calls if c[1]=='main']==[621,605,606];checks+=1
        if name=='companion-only':assert [c[1] for c in calls]==['companion','companion'];checks+=1
        traces.append({'name':name,'frames':120,'pulseFrames':sorted(pulses),'dispatches':calls,'final':state,'phaseSequence':phases,'instructionSteps':nsteps});steps+=nsteps
    # The endpoint is only a per-instance request latch; mode mismatch has zero writes.
    latch=[]
    for mode in [0,1,255]:
        for flags in [0,1,4,5,0xffffffff]:
            m=Machine(pe,baseline());m.write(COMBO+0x90,1,mode);m.write(COMBO+0x94,1,77);m.write(COMBO+0x9c,4,flags);m.setreg('edx',0)
            before=bytes(m.mem[COMBO+i] for i in range(256));m.run(0x1401f26a0);after=bytes(m.mem[COMBO+i] for i in range(256));expected=bytearray(before)
            if mode==0:
                struct.pack_into('<I',expected,0x9c,flags|1)
                if flags&4:expected[0x94]=0
            assert after==expected and not m.calls;checks+=1;steps+=len(m.trace)
            latch.append({'mode':mode,'flagsBefore':flags,'flagsAfter':m.read(COMBO+0x9c,4),'byte148After':m.read(COMBO+0x94,1),'instructionSteps':len(m.trace)})
    return {'status':'PASS','summary':{'singleUpdateCases':len(results),'lifecycleTraces':len(traces),'lifecycleUpdates':120*len(traces),'weaponLatchCases':len(latch),'checks':checks,'interpretedInstructionSteps':steps},'limitations':['Only the original combo update/request setter/weapon latch are interpreted. Ship dispatch callees are recorded hooks; no allocations, actors or projectiles are emulated.','Finite nonnegative timers and nonnegative native step are model inputs. Corrupt stage indices are excluded from indexed phase1/phase2 cases.','Same-source symbolic/reference agreement supports the documented branch behavior, not live gameplay validation.'],'singleUpdates':results,'lifecycleTraces':traces,'weaponLatchCases':latch}
