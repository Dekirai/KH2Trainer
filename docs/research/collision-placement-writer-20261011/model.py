"""Original-instruction cases with explicit boundary stubs, not full physics.

1752E0 executes original vector, matrix, bounds, quantization and retry code.
Collector and polygon-correction results are controlled effect stubs; the final
segment query is also a stub. Writer models run the captured normal/attribute
helpers but replace pointer decoding, optional effects and virtual dispatch.
"""
import math
from machine import Machine,B,bits,floating
C=0x200000;S=0x210000;H=0x220000;P=0x230000;A=0x240000;N=0x250000
PT=0x260000;NODE=0x270000;NODEPTR=0x280000;RES=0x290000
TEMPLATE=0x300000;OWNER=0x310000;RECORD=0x320000;RECEIVER=0x330000;VT=0x340000;SPAWN=0x350000;ORIENTATION=0x360000
VIRTUAL=0x370000

def run(ins,pe_read,need):
    cases=[];steps=0;visited=set();cache={}
    def pe(a,n):
        if (a,n) not in cache:cache[a,n]=pe_read(a,n)
        return cache[a,n]
    sqrt_target=ins[B+0x140f72].operands[0].imm
    def machine():
        m=Machine(ins,pe)
        # CRT sqrtf is a declared arithmetic boundary, not native execution.
        m.stubs[sqrt_target]=lambda m:m.setreg('xmm0',bits(math.sqrt(floating(m.reg('xmm0')))))
        return m
    def invoke(m,rva,args,label):
        nonlocal steps
        m.invoke(rva,args,budget=100000);steps+=m.steps;visited.update(m.visited)
        return dict(name=label,entry=hex(B+rva),steps=m.steps,returnRax=hex(m.reg('rax')))
    def affine(tx=0,sy=1,wy=0):return (1,0,0,0,0,sy,0,0,0,0,1,0,tx,wy,0,1)
    def volume(label,flags=0,status=0,radius=20,offset=7,start=(1,10,3,1),move=(10,-2,1,0),candidate_count=0,correction=0,segment=False,local=None,world=None,expected=None,expected_return=0):
        m=machine()
        for p,n in [(C,248),(S,144),(H,64)]:m.allocate(p,n)
        m.put(C,8,H);m.put(C+229,1,int(local is None));m.vector(C+100,world or affine());m.vector(C+164,local or affine())
        m.vector(S,start);m.vector(S+16,move);m.put(S+32,4,bits(radius));m.put(S+36,4,bits(60));m.put(S+108,4,bits(offset));m.put(S+112,4,flags);m.put(S+116,4,status);m.vector(S+48,(99,98,97,96))
        calls=[];collector=[];segments=[]
        def collect(x):
            countptr=x.get(x.reg('rsp')+32,8);x.put(countptr,2,candidate_count)
            collector.append(dict(category=x.get(x.reg('rsp')+40,4),quantized=[x.get(x.reg('r9')+j*2,2) for j in range(6)],filters=[x.get(C+92,4),x.get(C+96,4),x.get(C+228,1),x.get(C+231,1)]))
            if candidate_count:x.put(x.reg('rdx'),2,0)
        def correct(x):
            out=x.get(x.reg('rsp')+40,8);state=x.get(x.reg('rsp')+48,8)
            calls.append(dict(center=list(x.floats(x.reg('r9'))),radius=floating(x.get(x.reg('r9')+16,4)),state=hex(state)))
            if correction>0:x.vector(out,x.floats(x.reg('r9')))
            x.setreg('eax',correction)
        def query(x):
            segments.append(list(x.floats(x.reg('rdx'),8)));x.setreg('eax',int(segment))
        m.stubs[B+0x1741c0]=collect;m.stubs[B+0x174640]=correct;m.stubs[B+0x173b30]=query
        row=invoke(m,0x1752e0,(C,S),label)
        need(m.reg('eax')==expected_return,label+' exact return')
        if expected is not None:need(m.floats(S+48)==tuple(expected),label+' exact output')
        need(collector[0]['filters']==[15,4,1,0],label+' shared filter stores precede collect')
        need(all(x['radius']==radius and x['state']==hex(S) for x in calls),label+' correction radius/state provenance')
        row.update(output=list(m.floats(S+48)),flags=m.get(S+112,4),status=m.get(S+116,4),collector=collector,correctionCalls=calls,segmentCalls=segments)
        cases.append(row);return row
    volume('empty candidates moves output yet returns false',expected=(11,8,4,1))
    volume('empty candidates false despite incoming correction bit',status=4,expected=(11,8,4,1))
    volume('ordinary candidates with no correction returns false',candidate_count=1,expected=(11,8,4,1))
    volume('incoming correction bit survives standalone call',candidate_count=1,status=4,expected=(11,8,4,1),expected_return=1)
    volume('final segment hit restores original point and returns false',candidate_count=1,segment=True,expected=(1,10,3,1))
    volume('correction minus1 restores prior substep and sets status',candidate_count=1,correction=-1,expected=(1,10,3,1),expected_return=1)
    r=volume('positive correction retries through counter6',candidate_count=1,correction=1,expected=(11,8,4,1),expected_return=1)
    need(len(r['correctionCalls'])==6,'bounded retry chain uses six correction invocations at one substep')
    r=volume('category6 rewrites mode and skips final segment',flags=0x32,candidate_count=1,segment=True,expected=(11,8,4,1))
    need(r['flags']==0x34 and not r['segmentCalls'],'category6 low-mode rewrite and postcheck skip')
    r=volume('radius4 splits length10 into3 steps',start=(0,0,0,1),move=(10,0,0,0),offset=0,radius=4,candidate_count=1,expected=(10,0,0,1))
    need(len(r['correctionCalls'])==3,'CVTTSS2SI length/radius plus1')
    volume('affine translation roundtrip keeps world target',local=affine(-20,1,-30),world=affine(20,1,30),expected=(11,8,4,1))
    volume('inconsistent matrix pair reports false with displaced output',local=affine(),world=affine(100),expected=(111,8,4,1))
    r=volume('startW0 changes local displacement and substep count',start=(1,10,3,0),candidate_count=1,local=affine(-20,1,-30),world=affine(20,1,30),expected=(11,8,4,1))
    need(len(r['correctionCalls'])==2,'input startW0 makes local displacement differ from W1 case')
    r=volume('zero radius conversion skips step loop and retains old output',radius=0,candidate_count=1,expected=(99,105,97,96))
    need(not r['correctionCalls'],'masked infinity conversion produces signed-negative step count')
    r=volume('matrix scale does not rescale radius passed to corrector',start=(0,0,0,1),move=(0,20,0,0),offset=0,radius=10,candidate_count=1,local=affine(sy=.5),world=affine(sy=2),expected=(0,20,0,1))
    need(len(r['correctionCalls'])==2 and all(x['radius']==10 for x in r['correctionCalls']),'local length controls subdivision with unchanged radius scalar')

    for moving in [0,1]:
     for second in [False,True]:
      for measure in [False,True]:
        m=machine();m.allocate(S,144);m.allocate(B+0xABD448,8);m.put(B+0xABD448,8,C)
        m.vector(S,(1,2,3,1));m.vector(S+48,(4,6,8,1));m.put(S+116,4,255);m.put(S+120,8,0x9999)
        order=[]
        def moving_query(x):
            order.append('moving');need(x.reg('rcx')==S and x.get(S+116,4)==251 and x.get(S+98,4)==0xffffffff,'wrapper clears correction flag and two WORD IDs before queries');x.setreg('eax',moving)
        def static_query(x):
            order.append('static');need(x.reg('rcx')==C and x.reg('rdx')==S,'wrapper passes current static global and same state');x.setreg('eax',0 if order.count('static')==1 else 1)
        def floor_query(x):
            order.append('floor');need(x.get(S+120,8)==0,'wrapper nulls node before floor query')
            if measure:x.put(x.reg('rdx'),4,bits(12.5))
            x.setreg('eax',int(second))
        def fallback(x):order.append('fallback');x.put(S+120,8,0x7777);x.setreg('eax',1)
        m.stubs[B+0x1638f0]=moving_query;m.stubs[B+0x1752e0]=static_query;m.stubs[B+0x163750]=floor_query;m.stubs[B+0x172840]=fallback
        row=invoke(m,0x16fec0,(S,),f'wrapper moving{moving} second{second} measure{measure}')
        need(order==['moving','static','floor',('static' if second else 'fallback')],'wrapper operation order')
        need(m.reg('eax')==(moving|int(second)),'wrapper combines correction return values')
        if second:need(m.floats(S+16)==(3,4,5,0),'second static probe receives output-minus-start float4 displacement')
        need(m.get(S+116,4)==(249 if measure else 251),'floor measurement controls separate status bit2')
        if measure:need(floating(m.get(S+104,4))==12.5,'floor measurement stored independently')
        row.update(order=order,status=m.get(S+116,4));cases.append(row)

    def writer_fixture(kind=1,moving=False,initial=0,spawn=False,spawn_result=True,notify=False,callback=0):
        m=machine()
        for p,n in [(C,248),(S,224),(H,64),(P,16),(A,4),(N,16),(PT,16),(NODE,32),(NODEPTR,8),(RES,64),(TEMPLATE,16),(OWNER,1800),(RECORD,16),(RECEIVER,16),(VT,224),(SPAWN,64),(ORIENTATION,16),(B+0xABD448,16)]:m.allocate(p,n)
        m.put(C+24,8,P);m.put(C+40,8,A);m.put(C+48,8,N);m.put(C+229,1,1);m.vector(C+100,affine());m.put(A,4,kind);m.vector(N,(0,2,0,55))
        m.put(B+0xABD448,8,C);m.put(NODE+8,8,C);m.put(NODEPTR,8,NODE if moving else 0);m.vector(PT,(7,8,9,4));m.put(S+8,4,initial);m.put(S+40,4,1);m.put(S+20,4,2);m.put(S+16,4,3);m.put(S+48,8,RES);m.put(RES+11,1,2 if spawn else 0);m.put(RES+18,1,1)
        m.put(TEMPLATE,8,int(spawn));m.put(OWNER+1736,4,64 if notify else 0);m.put(RECORD,4,4);m.put(RECEIVER,8,VT);m.put(VT+216,8,VIRTUAL)
        effects=[]
        def decode(x):x.setreg('rax',{1:TEMPLATE,2:OWNER,3:RECORD,4:RECEIVER}[x.reg('ecx')])
        def effect(name,result):
            def f(x):
                effects.append(dict(name=name,args=[hex(x.reg(y)) for y in ['rcx','rdx','r8','r9']],storedPoint=list(x.floats(S+180)),flags=x.get(S+8,4)))
                x.setreg('rax',result)
            return f
        m.stubs[B+0x4ad270]=decode
        m.stubs[B+0x3f6410]=effect('optional-create',SPAWN if spawn_result else 0)
        m.stubs[B+0x3b7710]=effect('orientation-conversion',PT)
        m.stubs[B+0x2be1b0]=effect('orientation-destination',ORIENTATION)
        m.stubs[B+0x3d9be0]=effect('spawn-finalize',0)
        m.stubs[B+0x3b5b40]=effect('owner-position-access',PT)
        m.stubs[B+0x3dadf0]=effect('owner-notification',0)
        m.stubs[VIRTUAL]=effect('virtual+216',callback)
        return m,effects
    for sy in [0,2]:
        m,effects=writer_fixture();m.put(C+229,1,0);m.vector(C+100,affine(100,sy,200))
        row=invoke(m,0x173500,(C,PT,0),'metadata normal matrix excludes translation and normalizes scale'+str(sy))
        want=(0,1 if sy else 0,0,1)
        need(m.floats(PT)==want and m.reg('rax')==PT,'metadata normal helper returns caller output with translation removed')
        row.update(output=list(m.floats(PT)));cases.append(row)
    for kind in [0,1,2,15,17]:
      for moving in [False,True]:
       for initial in [0,0x100,0x300]:
        label=f'writer attribute{kind} moving{moving} flags{initial:x}'
        m,effects=writer_fixture(kind,moving,initial,callback=0xABCD)
        row=invoke(m,0x3d1960,(S,0,PT,NODEPTR),label)
        expected_flags=initial|(16 if kind&15==1 else 8)
        need(m.floats(S+180)==(7,8,9,4) and m.get(S+8,4)==expected_flags,label+' point/flags copied')
        need([e['name'] for e in effects]==([] if initial&0x100 else ['virtual+216']),label+' final dispatch predicate')
        need(m.reg('rax')==(expected_flags>>8 if initial&0x100 else 0xABCD),label+' incidental return rather than Boolean success')
        if effects:need(effects[-1]['args'][:3]==[hex(RECEIVER),hex(RECORD),hex(S)],label+' compressed-record virtual arguments')
        row.update(flags=expected_flags,point=list(m.floats(S+180)),effects=effects);cases.append(row)
    for kind in [1,2]:
     for spawn_result in [False,True]:
      m,effects=writer_fixture(kind,True,0,True,spawn_result,True,callback=0)
      row=invoke(m,0x3d1960,(S,0,PT,NODEPTR),'writer optional effects return'+str(spawn_result)+' kind'+str(kind))
      need(all(e['storedPoint']==[7,8,9,4] for e in effects),'point is written before every opaque optional effect')
      create=effects[0];need(int(create['args'][1],16)==((0x100000000<<1)|(0x100 if kind==1 else 2)),'resource byte11 selects shifted effect mask')
      need(effects[-1]['name']=='virtual+216' and effects[-2]['name']=='owner-notification','notification precedes final virtual dispatch')
      need(m.reg('rax')==0,'writer callback zero does not undo stored point')
      row.update(effects=effects,point=list(m.floats(S+180)));cases.append(row)
    for hit in [False,True]:
        m,effects=writer_fixture(callback=0)
        def query(x):
            x.vector(x.reg('rdx'),(7,8,9,4));x.put(x.reg('r8'),2,0);x.put(x.reg('r9'),8,0);x.setreg('eax',int(hit))
        m.stubs[B+0x171090]=query
        row=invoke(m,0x3d0bb0,(S,PT,PT),'caller returns its own Boolean query'+str(hit))
        need(m.reg('al')==int(hit),'caller forces success after normal writer return despite callback zero')
        need(bool(effects)==hit,'writer is not invoked on absent hit')
        row.update(effects=effects);cases.append(row)
    return dict(summary=dict(cases=len(cases),instructionSteps=steps,distinctInstructions=len(visited),stubBoundaries=['CRT sqrtf and stack cookie','volume candidate collector1741C0/corrector174640/final segment173B30','16FEC0 wrapper moving/static/floor-query result effects','writer Ptr32 decode and optional native effect/virtual callees','caller171090 hit/result effect']),cases=cases)
