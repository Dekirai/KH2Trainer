"""Closed-subset symbolic dataflow, never script execution or a general VM emulator.

Only the two selected Event0 prefixes are accepted. Native summaries are explicit;
they model destination ranges, not engine behavior, floats or unknown motion fields.
All 256 values of the one byte-valued external branch input are checked.
"""
import hashlib, importlib.util, json, struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FROZEN = ROOT / 'docs/research/bdx-inspection-20261008'
ASSETS = Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\Modding\openkh\data\kh2')

def module(path, name):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

decoder = module(FROZEN / 'bdx_inspect.py', 'rebind_decoder')
def sha(data): return hashlib.sha256(data).hexdigest()
def require(ok, message):
    if not ok: raise ValueError(message)
def ptr(space, offset): return (space, offset)
def add(value, offset):
    require(isinstance(value, tuple) and isinstance(offset, int), 'pointer addition')
    return ptr(value[0], value[1] + offset)
def label(value):
    return dict(space=value[0], offset=value[1]) if isinstance(value, tuple) else value

def trace(data, witness, descriptors, difficulty):
    al = 'B_AL020' in witness['asset']
    wrapper = ptr('work', 192 if al else 144)
    motion = ptr('work', 480 if al else 320)
    actor = ptr('actor', 0)
    sizes = struct.unpack_from('<iii', data, 16)
    mem = {}; stack = [actor]; frame = 16
    pc = witness['routes'][0]['entryPc']; target = witness['trap']['pc']
    pcs=[]; calls=[]; branches=[]; stores=[]; traps=[]; records={}
    max_stack=1; max_frame=frame
    for i in range(4): mem[ptr('frame', 4*i)] = 0
    def load(address):
        require(address in mem, 'uninitialized dataflow read '+str(address))
        return mem[address]
    def write(address, value, origin, width=4):
        require(isinstance(address, tuple), 'non-pointer store')
        if address[0] in ('work','frame'):
            size=sizes[0 if address[0]=='work' else 1]
            require(0 <= address[1] and address[1]+width <= size, 'store outside declared storage')
        mem[address]=value
        stores.append(dict(pc=pc, destination=label(address), value=label(value), width=width, origin=origin))
    def address(sub, offset):
        if sub==0:return ptr('frame',frame+offset)
        if sub==1:return ptr('work',offset)
        if sub==2:return add(load(ptr('frame',frame)),offset)
        if sub==3:return ptr('script',16+2*offset)
        raise ValueError('unknown selector')
    def pop():
        require(bool(stack),'operand underflow at '+str(pc));return stack.pop()
    for step in range(10000):
        x=decoder.instruction(data,pc); pcs.append(pc)
        nxt=pc+x['width']; g=x['group']; sub=x['sub']; mode=x['mode']; ops=x['operands']
        if pc==target:
            d=descriptors[(2,witness['trap']['index'])]; n=d['declaredArguments']
            args=stack[-n:]
            require(args[0]==wrapper and args[1]==(138 if al else 216),'final operands')
            require(load(add(wrapper,4))==actor,'wrapper Actor field')
            require(load(ptr('frame',frame))==wrapper and frame==32,'main frame retained')
            require(len(stack)==n,'no residual operands at selected trap')
            return dict(difficultyRepresentative=difficulty, instructionCount=len(pcs), pcs=pcs,
                calls=calls, branches=branches, stores=stores, traps=traps,
                final=dict(pc=pc, frameOffset=frame, arguments=[label(a) for a in args],
                           wrapperActor=label(load(add(wrapper,4))), operandDepth=len(stack)),
                maximumOperandDepth=max_stack, maximumFrameOffset=max_frame,
                motionRecordCount=len(records), motionBase=label(motion), wrapper=label(wrapper))
        if g==0:
            if mode<2:stack.append(ops[0] | ops[1]<<16)
            elif mode==2:stack.append(address(sub,ops[0]))
            else:stack.append(load(address(sub,ops[0])))
        elif g==1:write(address(sub,ops[0]),pop(),'script-store')
        elif g==4:
            require(x['word']<64,'unsupported memcpy'); value=pop(); dest=pop();write(dest,value,'script-indirect-store')
        elif g==5:
            require(mode==0 and sub==8,'unsupported unary'); value=pop();require(isinstance(value,int),'unary pointer');stack.append(int(value==0))
        elif g==6:
            right,left=pop(),pop();require(mode==0 and sub in (0,1),'unsupported binary')
            if sub==0:
                stack.append(add(left,right) if isinstance(left,tuple) else add(right,left) if isinstance(right,tuple) else (left+right)&0xffffffff)
            else:
                require(isinstance(left,int) and isinstance(right,int),'pointer subtraction');stack.append((left-right)&0xffffffff)
        elif g==7:
            take=True if sub==0 else (pop()==0 if sub==1 else pop()!=0)
            require(sub in (0,1,2),'branch mode');nxt=x['edges'][0]['target'] if take else nxt
            branches.append(dict(pc=pc,target=nxt,taken=take))
        elif g in (8,11):
            prior=frame;frame+=4*sub;max_frame=max(frame,max_frame)
            write(ptr('frame',frame-8),sub,'return-frame-size');write(ptr('frame',frame-4),nxt,'return-pc')
            calls.append(dict(pc=pc,target=x['edges'][0]['target'],fromFrame=prior,toFrame=frame,operandStack=[label(a) for a in stack]))
            nxt=x['edges'][0]['target']
        elif g==9:
            if sub==2:
                nxt=load(ptr('frame',frame-4));frame-=4*load(ptr('frame',frame-8));require(nxt!=0,'returned before target')
            elif sub==3:pop()
            elif sub==5:stack.append(stack[-1])
            else:raise ValueError('unmodeled control')
        elif g==10:
            bank,index=x['bank'],x['index'];d=descriptors[(bank,index)]; n=d['declaredArguments']
            require(len(stack)>=n,'trap underflow');args=stack[-n:] if n else []; del stack[len(stack)-n:]
            traps.append(dict(pc=pc,bank=bank,index=index,arguments=[label(a) for a in args],descriptor=d['addr']))
            if (bank,index)==(1,5):
                require(args==[motion],'motion initialization argument')
                for j in range(128):write(add(motion,32*j),0,'native-1:5-clear')
            elif (bank,index)==(1,7):
                require(args==[wrapper,motion] and load(add(wrapper,4))==actor,'actor association')
                write(ptr('actor',1184),motion,'native-1:7-actor',8);write(ptr('actor',1176),wrapper,'native-1:7-actor',8)
            elif (bank,index)==(1,6):
                require(args[0]==motion and isinstance(args[1],tuple) and args[1][0]=='script','motion record arguments')
                start=args[1][1]; end=data.find(b'\0',start)
                require(0<=start<len(data) and end>=start,'bounded script string')
                name=data[start:end]
                if name not in records:records[name]=len(records)
                slot=records[name];require(slot<128,'motion table full')
                dest=add(motion,32*slot)
                write(dest,args[1],'native-1:6-record-key')
                # Unknown native stack slots12..14 affect only WORD fields in this range.
                require(dest[1]+32<=sizes[0], 'motion record outside work')
                require(not (dest[1]+4<=wrapper[1]+4<dest[1]+32), 'motion fields alias Actor link')
                stores.append(dict(pc=pc,destination=label(add(dest,4)),width=28,origin='native-1:6-record-fields',value='stored operands plus unspecified vector slots12..14'))
            elif (bank,index)==(1,23):
                require(d['returnsValue'],'difficulty return flag');stack.append(difficulty)
            else:raise ValueError('unmodeled native trap '+str((bank,index)))
        else:raise ValueError('unmodeled group '+str(g))
        max_stack=max(max_stack,len(stack));pc=nxt
    raise ValueError('trace budget')

def derive(descriptors):
    output=[]
    for w in json.loads((FROZEN/'asset-witnesses.json').read_text(encoding='utf-8')):
        whole=(ASSETS/w['asset']).read_bytes();require(sha(whole)==w['assetSha256'],'asset identity')
        data=whole[w['scriptOffset']:w['scriptOffset']+w['scriptLength']]
        require(sha(data)==w['scriptSha256'],'script identity')
        variants={}; cases=[]
        for difficulty in range(256) if 'AL020' in w['asset'] else [0]:
            t=trace(data,w,descriptors,difficulty)
            digest=sha(json.dumps(t['pcs']).encode());cases.append(dict(value=difficulty,pathSha256=digest))
            if digest not in variants:variants[digest]=t
        pcs=sorted({p for t in variants.values() for p in t['pcs']})
        output.append(dict(asset=w['asset'],assetSha256=w['assetSha256'],scriptSha256=w['scriptSha256'],
            scriptOffset=w['scriptOffset'],scriptLength=w['scriptLength'],eventId=0,entryPc=w['routes'][0]['entryPc'],
            targetPc=w['trap']['pc'],pathCases=cases,variants=list(variants.values()),
            instructions=[decoder.instruction(data,p) for p in pcs]))
    return output
