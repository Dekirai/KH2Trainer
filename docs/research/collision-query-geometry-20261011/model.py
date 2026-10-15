"""Meaningful bounded geometry and caller cases over decoded original code.

All input tables and states are synthetic. Query cases execute 173B30 and its
captured computational callees, with only __security_check_cookie stubbed.
Caller cases explicitly replace the moving-list query by an effect stub; they
do not establish moving-node ownership or real-world collider transforms.
"""
import math,struct
from machine import Machine,B,STACK,bits,floating,f32
C=0x200000;H=0x210000;N=0x220000;L=0x230000;P=0x240000;V=0x250000;NORMAL=0x260000;A=0x270000;BOX=0x280000;S=0x290000;O=0x2a0000;ID=0x2b0000;NODEOUT=0x2c0000;VP=0x2d0000
SENTINEL=(123.,456.,789.,42.)

def run(ins,pe_read,need):
    cases=[];steps=0;visited=set();cache={}
    def pe(a,n):
        if (a,n) not in cache:cache[a,n]=pe_read(a,n)
        return cache[a,n]
    def fixture(start=(0,10,0,1),end=(0,-10,0,1),heights=(0,),quad=False,shiftx=0):
        m=Machine(ins,pe)
        for p,n in [(C,248),(H,64),(N,32),(L,20),(P,max(16,16*len(heights))),(V,max(64,64*len(heights))),(NORMAL,16),(A,4),(BOX,12),(S,32),(O,64),(ID,8),(NODEOUT,8),(VP,40)]:m.allocate(p,n)
        for offset,p in [(0,H),(8,N),(16,L),(24,P),(32,V),(40,A),(48,NORMAL),(56,BOX)]:m.put(C+offset,8,p)
        m.put(C+229,1,1)
        for i in range(8):m.put(N+2*i,2,65535)
        for i,v in enumerate([-100,-100,-100,100,100,100]):m.put(N+16+2*i,2,v);m.put(L+2*i,2,v);m.put(BOX+2*i,2,v)
        m.put(N+30,2,1);m.put(L+14,2,len(heights));m.put(L+16,1,1)
        for j,y in enumerate(heights):
            verts=[(-10+shiftx,y,-10,1),(0+shiftx,y,10,1),(10+shiftx,y,-10,1)] if not quad else [(-10+shiftx,y,-10,1),(-10+shiftx,y,10,1),(10+shiftx,y,10,1),(10+shiftx,y,-10,1)]
            for k,v in enumerate(verts):m.vector(V+j*64+k*16,v)
            for k,v in enumerate([j*4,j*4+1,j*4+2,j*4+3 if quad else 65535,0,65535,0]):m.put(P+j*16+2+2*k,2,v)
        m.vector(NORMAL,(0,1,0,0));m.vector(S,start);m.vector(S+16,end);m.vector(O,SENTINEL);m.put(ID,2,0x1234)
        return m
    def execute(m,rva,args,label,expect_error=None):
        nonlocal steps
        error=None
        try:m.invoke(rva,args)
        except AssertionError as e:
            if expect_error is None:raise
            error=str(e);need(expect_error in error,label+' expected bounded fixture rejection')
        if expect_error:need(error is not None,label+' hazard observed')
        steps+=m.steps;visited.update(m.visited)
        return error
    def query(label,want_hit,want_point=None,want_id=0,prepare=None,**kw):
        m=fixture(**kw)
        if prepare:prepare(m)
        execute(m,0x173b30,(C,S,O,ID,15),label)
        need(bool(m.reg('al'))==want_hit,label+' hit flag')
        need(m.get(ID,2)==(want_id if want_hit else 65535),label+' polygon sentinel/selection')
        if want_point is None:want_point=SENTINEL
        need(m.floats(O)==tuple(want_point),label+' exact output float32')
        cases.append(dict(name=label,kind='full-query',hit=want_hit,point=list(m.floats(O)),polygon=m.get(ID,2),instructionSteps=m.steps))
        return m
    query('interior t=0.5',True,(0,0,0,1))
    query('start endpoint t=0 inclusive',True,(0,0,0,1),start=(0,0,0,1))
    query('end endpoint t=1 inclusive',True,(0,0,0,1),end=(0,0,0,1))
    query('back-facing segment',False,start=(0,-10,0,1),end=(0,10,0,1))
    query('parallel',False,start=(0,10,0,1),end=(1,10,0,1))
    query('zero-length',False,start=(0,0,0,1),end=(0,0,0,1))
    query('plane before start',False,start=(0,-1,0,1),end=(0,-10,0,1))
    query('plane after end',False,start=(0,10,0,1),end=(0,1,0,1))
    query('outside polygon edge',False,start=(11,10,0,1),end=(11,-10,0,1))
    query('triangle vertex',True,(-10,0,-10,1),start=(-10,10,-10,1),end=(-10,-10,-10,1))
    query('quad interior',True,(9,0,9,1),quad=True,start=(9,10,9,1),end=(9,-10,9,1))
    query('disabled leaf preserves caller output',False,prepare=lambda m:m.put(L+16,1,0))
    query('nearer second polygon',True,(0,5,0,1),heights=(0,5),want_id=1)
    query('equal distance keeps first',True,(0,5,0,1),heights=(5,5),want_id=0)
    def matrix(m,local,world):
        m.put(C+229,1,0);m.vector(C+164,local);m.vector(C+100,world)
    def affine(tx=0,sy=1,wy=0):return (1,0,0,0,0,sy,0,0,0,0,1,0,tx,wy,0,1)
    query('affine inverse translation round trip',True,(20,30,0,1),start=(20,40,0,1),end=(20,20,0,1),prepare=lambda m:matrix(m,affine(-20,1,-30),affine(20,1,30)))
    query('affine inverse scale round trip',True,(0,0,0,1),start=(0,20,0,1),end=(0,-20,0,1),prepare=lambda m:matrix(m,affine(sy=.5),affine(sy=2)))
    query('inconsistent matrices can return off-segment point',True,(100,0,0,1),prepare=lambda m:matrix(m,affine(),affine(tx=100)))
    query('input W affects transform before query forces W1',True,(10,0,0,1),start=(0,10,0,0),end=(0,-10,0,0),prepare=lambda m:matrix(m,affine(tx=-10),affine(tx=10)))
    world=list(affine());world[15]=2
    query('output transform has no homogeneous divide',True,(0,0,0,2),prepare=lambda m:matrix(m,affine(),world))
    # Unordered primitive comparisons can all fall through, but the enclosing
    # nearest-distance comparison rejects its NaN result.
    query('NaN normal produces no selected query hit',False,prepare=lambda m:m.vector(NORMAL,(0,float('nan'),0,0)))
    # Isolate primitive output behavior with a real pointer-array ABI.
    for label,x,nan,want in [('edge rejection writes temporary',11,False,False),('NaN primitive accepts under masked exceptions',0,True,True)]:
        m=fixture();m.vector(S,(x,10,0,1));m.vector(S+16,(0,-20,0,1))
        for k in range(3):m.put(VP+k*8,8,V+k*16)
        m.put(VP+32,4,3)
        if nan:m.vector(NORMAL,(0,float('nan'),0,0))
        execute(m,0x18b4d0,(S,VP,NORMAL,O),label)
        need(bool(m.reg('al'))==want,label+' return')
        need(all(math.isnan(v) for v in m.floats(O)[:3]) if nan else m.floats(O)==(11,0,0,1),label+' written output')
        cases.append(dict(name=label,kind='primitive',hit=want,pointBits=[hex(m.get(O+4*k,4)) for k in range(4)],instructionSteps=m.steps))
    # Candidate cap: first 1023 accepted polygons are all geometrically outside;
    # only polygon1023 covers the segment. The same table with the leaf starting
    # at1023 hits. This is a genuine full-query false-negative witness.
    m=fixture(heights=(0,)*1024,shiftx=30)
    for k,v in enumerate([(-10,0,-10,1),(0,0,10,1),(10,0,-10,1)]):m.vector(V+1023*64+k*16,v)
    execute(m,0x173b30,(C,S,O,ID,15),'candidate truncation')
    need(m.reg('al')==0 and m.floats(O)==SENTINEL and m.get(ID,2)==65535,'1024th sole hit not collected')
    cases.append(dict(name='1024th sole geometric hit omitted',kind='full-query',hit=False,instructionSteps=m.steps))
    m=fixture(heights=(0,)*1024,shiftx=30);m.put(L+12,2,1023)
    for k,v in enumerate([(-10,0,-10,1),(0,0,10,1),(10,0,-10,1)]):m.vector(V+1023*64+k*16,v)
    execute(m,0x173b30,(C,S,O,ID,15),'same final polygon isolated')
    need(m.reg('al')==1 and m.get(ID,2)==1023 and m.floats(O)==(0,0,0,1),'omitted polygon really intersects')
    cases.append(dict(name='same 1024th polygon queried alone hits',kind='full-query',hit=True,instructionSteps=m.steps))
    # Traversal hazards are fixture-stop observations, not game fault claims.
    for child,expected,label in [(0xfffe,'unallocated synthetic read','signed child -2 has no native index guard'),(0,'fixture recursion budget','self-cycle has no native cycle guard')]:
        m=fixture();m.put(N,2,child);m.put(N+30,2,0)
        err=execute(m,0x173b30,(C,S,O,ID,15),label,expected)
        cases.append(dict(name=label,kind='bounded-traversal-hazard',fixtureStop=err,instructionSteps=m.steps))
    # Full combined wrapper + full static query. Only moving query is stubbed.
    # Its effect follows already-captured163FC0: write output and shorten end.
    for moving,static_y,label,want_node,want_poly,want_y in [(False,0,'static only',0,0,0),(True,0,'moving nearer than static',0x345600,7,5),(True,5,'equal moving/static endpoint selects static',0,0,5),(True,7,'static nearer than moving',0,0,7)]:
        m=fixture(heights=(static_y,));m.allocate(B+0xabd448,8);m.put(B+0xabd448,8,C)
        observed=[]
        def moving_stub(v):
            observed.append(v.floats(v.reg('rcx')+16))
            v.put(v.reg('r8'),2,7 if moving else 65535)
            if moving:
                v.vector(v.reg('rdx'),(0,5,0,1));v.vector(v.reg('rcx')+16,(0,5,0,1));v.put(v.get(v.reg('rsp')+48,8),8,0x345600)
            v.setreg('al',int(moving))
        m.stubs[B+0x163fc0]=moving_stub
        execute(m,0x171090,(S,O,ID,NODEOUT,15),label)
        need(m.reg('al')==1 and m.get(ID,2)==want_poly and m.get(NODEOUT,8)==want_node and m.floats(O)==(0,want_y,0,1),label+' result identity/order')
        need(observed==[(0,-10,0,1)] and m.floats(S+16)==((0,5,0,1) if moving else (0,-10,0,1)),label+' endpoint mutation')
        cases.append(dict(name=label,kind='combined-with-moving-effect-stub',node=hex(want_node),polygon=want_poly,point=list(m.floats(O)),instructionSteps=m.steps))
    # Higher wrapper, with explicit recording query stubs, checks ABI and stale
    # output policy without manufacturing any game-world validity.
    for flags,hit in [(15,False),(15,True),(0x10004,True),(0x20004,True)]:
        m=fixture(start=(1,2,3,7),end=(4,5,6,9));events=[]
        def wrapper_stub(v):
            combined=v.pc==B+0x40c33a
            category=v.get(v.reg('rsp')+32,4) if combined else v.reg('r9d')
            events.append((combined,category,v.floats(v.reg('rcx')),v.floats(v.reg('rcx')+16)))
            if hit:v.vector(v.reg('rdx'),(8,9,10,1));v.put(v.reg('r8'),2,33)
            v.setreg('al',int(hit))
        m.stubs[B+0x171090]=wrapper_stub;m.stubs[B+0x171350]=wrapper_stub
        execute(m,0x40c2b0,(O,S,S+16,flags),'result wrapper')
        need(events==[(bool(flags&0x10000),flags&65535 if flags&0x10000 else flags,(1,2,3,1),(4,5,6,1))],'result wrapper exact W/category')
        need(bool(m.reg('al'))==hit and m.get(O+20,4)==(33 if hit else 0xffffffff),'result wrapper validity sentinel')
        need(m.floats(O)==((8,9,10,1) if hit else SENTINEL),'result wrapper stale point on miss')
        cases.append(dict(name='result wrapper flags '+hex(flags)+' hit '+str(hit),kind='caller-with-query-stubs',events=events,instructionSteps=m.steps))
    m=fixture(start=(1,20,3,7));events=[]
    def fallback_stub(v):events.append((v.floats(v.reg('rcx')),v.floats(v.reg('rcx')+16),v.reg('r8d')));v.setreg('al',0)
    m.stubs[B+0x171030]=fallback_stub
    execute(m,0x3f3cc0,(S,O,4),'vertical fallback')
    need(events==[((1,-30,3,7),(1,120,3,7),4)] and m.reg('al')==0 and m.floats(O)==(1,20,3,7),'vertical caller miss fallback and input W')
    cases.append(dict(name='vertical caller miss returns original point with false',kind='caller-with-query-stub',events=events,instructionSteps=m.steps))
    return {'summary':{'cases':len(cases),'instructionSteps':steps,'uniqueInstructionsExecuted':len(visited),'fullQueryCases':sum(c['kind']=='full-query' for c in cases)},'cases':cases,'interpretedAddresses':[hex(a) for a in sorted(visited)],'boundaries':['No native code or game state was executed.','All tables/geometry/transforms are synthetic and bounded; security-cookie check is a no-op.','IEEE float32 rounding assumes masked exceptions with DAZ/FTZ off; NaN payload identity is not asserted.','Combined caller cases replace moving query163FC0 by a documented effect stub; graph lifetime and actual transform pairing remain open.','Cycle/negative-index cases report fixture safety stops, not demonstrated game faults.']}
