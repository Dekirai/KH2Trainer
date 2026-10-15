"""Selected original instructions, explicit engine-boundary stubs, no native execution.

Tests cover argument forwarding, flag/counter effects, processed suppression and
the two motion-request branches. Engine callees are opaque; they may alter Actor
position. These cases cannot prove absence of such effects or safe placement.
"""
from machine import Machine, B, bits, floating

A=0x200000; CONTACT=0x210000; ACTION=0x220000; DESCRIPTOR=0x230000

def run(ins, pe_read, need):
    cases=[]; steps=0; visited=set(); cache={}
    def pe(a,n):
        if (a,n) not in cache:cache[a,n]=pe_read(a,n)
        return cache[a,n]
    def create(flags=0,counter=0,contact_flags=0,action=0,branch=False):
        m=Machine(ins,pe)
        for p,n in [(A,4096),(CONTACT,512),(ACTION,32)]:m.allocate(p,n)
        m.put(A+288,4,flags);m.put(A+3444,1,counter);m.put(A+12,4,0x11)
        m.put(CONTACT+8,4,contact_flags);m.put(ACTION+8,4,action)
        # Sentinel transform-related bytes help detect direct writes in this
        # captured slice. Callees are stubs, so this is not a game-side promise.
        for j in range(64):m.put(A+1648+j,1,(j*11+7)&255)
        calls=[]
        def decode(x):
            need(x.reg('ecx')==0x11,'Only fixture action pointer decoded')
            x.setreg('rax',ACTION)
        def state_query(x):
            need(x.reg('rcx')==A,'Actor query argument');calls.append(dict(callee='3BA9A0',actor=hex(A)));x.setreg('eax',int(branch))
        def request(x):
            calls.append(dict(callee='3C86A0',record=hex(x.reg('rcx')),code=x.reg('edx'),xmm2=x.reg('xmm2'),xmm3=x.reg('xmm3')))
            x.setreg('rax',0x1111222233334444)
        def mode(x):
            calls.append(dict(callee='3C8310',record=hex(x.reg('rcx')),mode=x.reg('edx'),xmm2=x.reg('xmm2'),xmm3=x.reg('xmm3'),stack5=x.get(x.reg('rsp')+32,8)))
            x.setreg('rax',0x5555666677778888)
        def direction(x):
            need(x.reg('rcx')==A,'Direction helper actor argument')
            out=x.reg('rdx');x.vector(out,(2,-3,4,1));x.setreg('rax',out)
            calls.append(dict(callee='3B56E0',output=hex(out)))
        def velocity(which):
            def call(x):
                calls.append(dict(callee=which,actor=hex(x.reg('rcx')),vector=list(x.floats(x.reg('rdx'))),scalar=floating(x.reg('xmm2'))))
                x.setreg('rax',0x9999aaaabbbbcccc)
            return call
        def special(x):
            calls.append(dict(callee='403940',actor=hex(x.reg('rcx')),contact=hex(x.reg('rdx')),arg3=hex(x.reg('r8'))));x.setreg('rax',0xddddeeeeffff1234)
        m.stubs.update({B+0x4ad270:decode,B+0x3ba9a0:state_query,B+0x3c86a0:request,B+0x3c8310:mode,B+0x3b56e0:direction,B+0x3d4800:velocity('3D4800'),B+0x3d4960:velocity('3D4960'),B+0x403940:special})
        return m,calls
    def invoke(m,rva,args,label):
        nonlocal steps
        m.invoke(rva,args,budget=20000);steps+=m.steps;visited.update(m.visited)
        row=dict(name=label,entry=hex(B+rva),steps=m.steps,rax=hex(m.reg('rax')))
        cases.append(row);return row
    # Both concrete native descriptor thunks execute through the real callback
    # and the real contact-flags early exit. No motion code is stub-executed here.
    for rva in [0x404eb0,0x4153e0]:
      for flags in [0,0x12345678,0xffffffff]:
       for counter in [0,1,2,255]:
        m,calls=create(flags,counter,0x440)
        before=dict(m.memory)
        row=invoke(m,rva,(DESCRIPTOR,A,CONTACT),f'thunk{rva:x} flags{flags:x} counter{counter}')
        need(m.get(A+288,4)==flags|0x02000000,'Actor flag OR exact')
        need(m.get(A+3444,1)==max(0,counter-1),'Byte counter decremented only when nonzero')
        need(m.get(CONTACT+8,4)==0x440 and m.reg('rax')==0x440>>6,'Processed contact bypass preserves flag and raw shifted return')
        need(not calls,'Processed contact bypass invokes no opaque engine helper')
        changed={p for p in before if before[p]!=m.memory[p] and A<=p<A+4096}
        need(changed <= set(range(A+288,A+292))|{A+3444},'Direct Actor stores confined to flag and byte counter in selected callback path')
        need(bytes(m.memory[A+1648+j] for j in range(64))==bytes(before[A+1648+j] for j in range(64)),'Selected callback does not directly overwrite sentinel transform bytes')
        row.update(flags=m.get(A+288,4),counter=m.get(A+3444,1),opaqueCalls=calls)
    # RET0 is not a Boolean-false function: the instruction keeps incoming RAX.
    for initial in [0,1,0x123456789abcdef0]:
        m=Machine(ins,pe);m.setreg('rax',initial)
        row=invoke(m,0x1afe10,(DESCRIPTOR,A,CONTACT),'base null callback RAX '+hex(initial))
        need(m.reg('rax')==initial,'RET0 preserves incoming RAX');row['incomingRax']=hex(initial)
    for action in [0,23]:
     for branch in [False,True]:
      for magnitude in [-1.0,0.0,12.5,float('nan')]:
       for motion in [-1,7]:
        m,calls=create(contact_flags=0x200,action=action,branch=branch)
        row=invoke(m,0x3d4650,(A,CONTACT,0xabcdef,motion&0xffffffff,bits(magnitude)),f'contact action{action} branch{branch} magnitude{magnitude} code{motion}')
        order=[x['callee'] for x in calls]
        if action==23:
            need(order==['403940'],'Action23 delegates without ordinary motion path')
            need(m.get(CONTACT+8,4)==0x200,'Action23 does not locally set processed flag')
            need(calls[0]['arg3']==hex(0xabcdef) and m.reg('rax')==0xddddeeeeffff1234,'Action23 forwards third argument and opaque return')
        else:
            positive=magnitude!=0 and magnitude==magnitude
            expected=['3BA9A0','3C86A0']+(['3C8310'] if branch else [])+(['3B56E0','3D4800' if branch else '3D4960'] if positive else [])+([] if branch else ['3C8310'])
            need(order==expected,'Ordinary path call order including direction/mode')
            need(m.get(CONTACT+8,4)==0x240,'Ordinary path marks contact processed')
            request=next(x for x in calls if x['callee']=='3C86A0');mode=next(x for x in calls if x['callee']=='3C8310')
            need(request['record']==hex(A+344) and request['code']==(motion if motion>=0 else 43 if branch else 41),'Selected motion record/code')
            need(mode['record']==hex(A+344) and mode['mode']==(4 if branch else 0) and mode['xmm2']==mode['xmm3']==mode['stack5']==0,'Mode helper arguments')
            need(request['xmm2']==request['xmm3']==0,'Motion helper scalar registers zero')
            if positive:
                v=next(x for x in calls if x['callee'] in ['3D4800','3D4960'])
                need(v['actor']==hex(A) and v['vector']==[-2.0,3.0,-4.0,-1.0],'Direction helper float4 negated by real13FCC0')
                need(v['scalar']==(50.0 if magnitude<0 else magnitude),'Negative input replaced by50 and magnitude forwarded in XMM2')
            need(m.reg('rax')==(0x9999aaaabbbbcccc if branch and positive else 0x5555666677778888),'Ordinary return comes from final opaque helper')
        row.update(opaqueCalls=calls,contactFlags=m.get(CONTACT+8,4))
    # One composed ordinary callback records the fixed default scalar emitted by
    #3D63E0, then runs both helper branches through3D4650.
    for branch in [False,True]:
        m,calls=create(flags=0x80000000,counter=2,branch=branch)
        row=invoke(m,0x404eb0,(DESCRIPTOR,A,CONTACT),'composed Sora callback ordinary branch '+str(branch))
        need(m.get(A+288,4)==0x82000000 and m.get(A+3444,1)==1,'Composed flag/counter')
        need(m.get(CONTACT+8,4)==0x40,'Composed processed marker')
        row.update(opaqueCalls=calls)
    # Native3D1960 uses its actual double decoder call and vtable load; the
    # decoder mapping is an explicit fixture admission, not an ownership proof.
    # Normal/category queries are also stubs, with all copies and dispatch real.
    for desc in [0x74af78,0x750300,0x7523b8]:
     for suppressed in [False,True]:
      for category in [0,1]:
        m,calls=create(flags=0x123456,counter=2,contact_flags=0x100 if suppressed else 0)
        point,owner,nodeptr=0x240000,0x250000,0x260000
        for p,n in [(point,16),(owner,8),(nodeptr,8)]:m.allocate(p,n)
        m.vector(point,(10,20,30,1));m.put(nodeptr,8,0);m.put(owner,8,0)
        m.put(CONTACT+16,4,0x22);m.put(A,4,0x33);m.put(CONTACT+20,4,0x22);m.put(CONTACT+40,4,0x44)
        decodes=[]
        def decode(x):
            token=x.reg('ecx');mapping={0x11:ACTION,0x22:A,0x33:B+desc,0x44:owner}
            need(token in mapping,'Declared composed Ptr32 token');decodes.append(token);x.setreg('rax',mapping[token])
        def normal(x):
            need(x.reg('r8d')==0,'Static normal selector0');out=x.reg('rcx');x.vector(out,(0,1,0,1));x.setreg('rax',out)
        def attribute(x):
            need(x.reg('edx')==0,'Static attribute selector0');x.setreg('eax',category)
        m.stubs[B+0x4ad270]=decode;m.stubs[B+0x170ac0]=normal;m.stubs[B+0x170910]=attribute
        row=invoke(m,0x3d1960,(CONTACT,9,point,nodeptr),f'writer dispatch descriptor{desc:x} suppressed{suppressed} category{category}')
        need(m.floats(CONTACT+180)==(10,20,30,1),'Contact float4 copy precedes descriptor dispatch')
        expected=(0x100 if suppressed else 0)|(0x10 if category==1 else 8)
        player=desc!=0x74af78 and not suppressed
        need(m.get(CONTACT+8,4)==expected|(0x40 if player else 0),'Category and callback processed flag composition')
        need(m.get(A+288,4)==(0x123456|(0x02000000 if player else 0)),'Only selected player callback sets Actor reaction flag')
        need(m.get(A+3444,1)==(1 if player else 2),'Only selected player callback changes counter')
        if suppressed:
            need(0x33 not in decodes and not calls and m.reg('rax')==1,'Suppression avoids descriptor decode and callback')
        else:
            need(decodes.count(0x33)==1,'Unsuppressed path resolves exactly one selected descriptor')
            if not player:need(not calls,'Base null target emits no opaque engine call')
        row.update(descriptor=hex(B+desc),decoderTokens=decodes,contactFlags=m.get(CONTACT+8,4),opaqueCalls=calls)
    for owner_state in ['null','noContext','context0','context255']:
     for resource_flags in [0,2,8,10]:
        m=Machine(ins,pe);resource=0x270000;context=0x280000;secondary=0x290000
        for p,n in [(CONTACT,736),(A,4096),(resource,64),(context,640),(secondary,256)]:m.allocate(p,n)
        owner=0 if owner_state=='null' else A
        m.put(A+1472,8,context if owner_state.startswith('context') else 0)
        m.put(context+600,1,255 if owner_state=='context255' else 0);m.put(resource+18,1,resource_flags)
        calls=[]
        def base_construct(x):
            args=[x.reg(n) for n in ['rcx','rdx','r8','r9']]+[x.get(x.reg('rsp')+32+j*8,8) for j in range(3)]
            need(args[:4]==[CONTACT,owner,secondary,17],'Derived constructor forwards first four args')
            need(args[4]==(255 if owner_state=='context255' else 0) and args[5]&0xffffffff==0xffffffff and args[6]&0xffffffff==0x11223344,'Derived constructor conditional-byte and stack args')
            # These fields are produced by the opaque base constructor stub.
            # Their construction semantics are deliberately not inferred.
            x.put(CONTACT+16,4,0x88);x.put(CONTACT+20,4,0x99);x.put(CONTACT+40,4,0x77);x.put(CONTACT+48,8,resource)
            calls.append('3CF830')
        def decode_owner(x):
            need(x.reg('ecx')==0x99,'Derived effect bind decodes base-produced+20');x.setreg('rax',A);calls.append('decode20')
        def encode_effect(x):
            need(x.reg('rcx')==A+128,'Derived effect bind uses decoded Actor+128');x.setreg('eax',0x6677);calls.append('encode128')
        m.stubs.update({B+0x3cf830:base_construct,B+0x4ad270:decode_owner,B+0x4ad240:encode_effect})
        row=invoke(m,0x40f1c0,(CONTACT,owner,secondary,17,0x123456789abcdef0,0x11223344,29),f'attack constructor {owner_state} resource{resource_flags:x}')
        need(m.get(CONTACT,8)==B+0x5ce6c0 and m.get(CONTACT+200,4)==29 and m.get(CONTACT+720,8)==0x123456789abcdef0,'Derived vtable, selector and extra pointer')
        need(all(m.floats(CONTACT+208+j*16)==(0,0,0,1) for j in range(32)),'All32 history float4 records initialized')
        need(m.get(CONTACT+16,4)==0x88 and m.get(CONTACT+20,4)==0x99,'Derived body preserves base-produced+16/+20')
        need(m.get(CONTACT+40,4)==(0x6677 if resource_flags&10==0 else 0x77),'Conditional effect binding update')
        need(calls==(['3CF830','decode20','encode128'] if resource_flags&10==0 else ['3CF830']),'Constructor helper order')
        need(m.reg('rax')==CONTACT,'Constructor return pointer')
        row.update(calls=calls,effectToken=m.get(CONTACT+40,4))
    return dict(status='PASS',scope='Original-instruction slices only. Ptr32, base attack constructor, static normal/category suppliers, actor-state query, motion requests, direction supplier and two downstream direction/scalar helpers are explicit stubs. No actual position, movement, allocation, race or lifetime guarantee.',cases=cases,summary=dict(cases=len(cases),steps=steps,distinctInstructions=len(visited)),executedAddresses=[hex(a) for a in sorted(visited)])
