"""Small semantic oracles; no game process, native execution or external assets.
The selector oracle interprets the verified native comparison/branch region.
Other models check wraparound, packed extents, and scalar vs unrolled float32 work.
These are model checks, not live-game observations or whole-backend tests.
"""
import itertools,json,math,struct
from pathlib import Path
from capstone import Cs,CS_ARCH_X86,CS_MODE_64

def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def signed32(x):return x-2**32 if x&0x80000000 else x
def same(a,b):return (math.isnan(a) and math.isnan(b)) or struct.pack('<f',a)==struct.pack('<f',b)

def selector_oracle(fn,start,x,y,z):
    raw=bytes(int(t,16) for t in fn['originalBytes'].split())
    ins={i.address:i for i in Cs(CS_ARCH_X86,CS_MODE_64).disasm(raw,int(fn['addr'],16))}
    regs={'xmm0':y,'xmm1':x,'xmm2':z};pc=start;cf=zf=False
    for _ in range(32):
        i=ins[pc];nextpc=pc+i.size
        if i.mnemonic=='comiss':
            a,b=[regs[r.strip()] for r in i.op_str.split(',')]
            cf=math.isnan(a) or math.isnan(b) or a<b
            zf=math.isnan(a) or math.isnan(b) or a==b
        elif i.mnemonic=='jbe':
            if cf or zf:nextpc=int(i.op_str,16)
        elif i.mnemonic=='movss':
            dst,src=[v.strip() for v in i.op_str.split(',')]
            if dst=='dword ptr [rbx]':return regs[src]
            assert dst=='xmm2' and src=='dword ptr [rsp + 0x28]',i.op_str
            regs[dst]=z
        else:raise AssertionError((hex(pc),i.mnemonic,i.op_str))
        pc=nextpc
    raise AssertionError('selector did not return')

def factor(n,c,unrolled=False):
    if n<=0:return 1.0
    value=1.0;j=0
    if unrolled:
        while j+8<=n:
            for k in range(j+1,j+9):value=f32(value-f32(c/f32(k)))
            j+=8
    for k in range(j+1,n+1):value=f32(value-f32(c/f32(k)))
    # COMISS 0.1,value / JA; MINSS 1,value (second operand wins on NaN).
    if f32(0.1)>value:return f32(0.1)
    return value if math.isnan(value) or value<=1 else 1.0

def run():
    c=json.loads((Path(__file__).parent/'capture.json').read_text(encoding='utf-8-sig'))
    by={int(f['addr'],16):f for f in c['functions']};checks=0
    vals=[-20.,-10.,-0.,0.,10.,20.,math.nan,math.inf,-math.inf]
    for x,y,z in itertools.product(vals,repeat=3):
        lo=x if y>x and z>x else y if x>y and z>y else z
        hi=x if x>y and x>z else y if y>x and y>z else z
        assert same(selector_oracle(by[0x140228b60],0x140228b91,x,y,z),lo)
        assert same(selector_oracle(by[0x140228be0],0x140228c11,x,y,z),hi)
        checks+=2
    assert selector_oracle(by[0x140228b60],0x140228b91,10.,10.,20.)==20.
    assert selector_oracle(by[0x140228be0],0x140228c11,20.,20.,10.)==10.
    checks+=2
    for nibble,byte in itertools.product(range(16),range(256)):
        sx=byte if byte<128 else byte-256
        neg=(-sx)&0xffffffff
        magnitude=neg if byte&0x80 else sx
        native=signed32((nibble-magnitude)&0xffffffff)*10
        assert native==(nibble-abs(sx))*10;checks+=1
    for raw in (0,1,0x7fffffff,0x80000000,0xfffffffe,0xffffffff):
        assert (((raw+1)&0xffffffff)-1)&0xffffffff==raw
        assert (((raw-1)&0xffffffff)+1)&0xffffffff==raw;checks+=2
    assert signed32((0-1)&0xffffffff)==-1
    assert signed32((0x7fffffff+1)&0xffffffff)==-2147483648;checks+=2
    for n,cfg in itertools.product(range(-2,130),[f32(0),f32(0.1),f32(0.3),f32(-0.5),f32(2),math.nan]):
        assert same(factor(n,cfg),factor(n,cfg,True));checks+=1
    assert factor(0,math.nan)==1 and math.isnan(factor(1,math.nan));checks+=2
    return {'checks':checks,'failures':0,'selectorComparisons':1458,'extentCases':4096,'counterCases':14,'factorComparisons':792,'scope':'Pure bounded models and native selector-branch interpretation; IEEE default rounding/masked exceptions assumed. No timing, scheduling, resource-lifetime or live gameplay test.'}

if __name__=='__main__':print(json.dumps(run()))
