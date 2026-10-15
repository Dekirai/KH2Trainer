"""Execute selected original instructions in bounded synthetic memory fixtures."""
from machine import Machine,B,STACK
A=0x200000;G=0x210000;P=0x220000;T=0x230000;PARAM=0x240000;OWNER_CELL=0x250000
HEAD=B+0x2A24B40;TAIL=B+0x2A24B48;INNER_HEAD=B+0x2A24AC0;INNER_TAIL=B+0x2A24AC8;PLAYER=B+0x2A105D0
def run(instructions,pe,need):
 cases=[];visited=set();steps=0
 def fresh():
  m=Machine(instructions,pe)
  for addr,size in [(A,4096),(G,4096),(P,4096),(T,4096),(PARAM,64),(OWNER_CELL,16),(HEAD,16),(INNER_HEAD,16),(PLAYER,8)]:m.allocate(addr,size)
  enc={0:0};dec={0:0};calls=[]
  def encode(p):
   if p not in enc:enc[p]=0x100+len(enc)*4;dec[enc[p]]=p
   return enc[p]
  def encstub(x):x.setreg('eax',encode(x.reg('rcx')))
  def decstub(x):
   need(x.reg('ecx') in dec,'fixture Ptr32 token known');x.setreg('rax',dec[x.reg('ecx')])
  m.stubs.update({B+0x4ad240:encstub,B+0x4ad270:decstub})
  return m,encode,dec,calls
 def invoke(m,rva,args,label):
  nonlocal steps
  m.setreg('rsp',STACK);m.put(STACK,8,0);before=m.steps
  result=m.invoke(rva,args,budget=5000);steps+=m.steps-before;visited.update(m.visited)
  row={'case':label,'entry':hex(B+rva),'steps':m.steps-before,'rax':hex(result)};cases.append(row);return row
 # Distinct original owner and replacement receiver, all four relevant flag
 # combinations, original-owner/geometry aliases, null links and DWORD wrap.
 configs=[(A,g,profile,flags,typ) for g in [0,A,G] for profile in [0,1,3,5] for flags in [0,2,8,10] for typ in [3]]
 configs += [(0,g,p,f,0) for g in [0,G] for p in [0,1,3] for f in [0,2]]
 for owner,geometry,profile,flags,typ in configs:
  m,encode,dec,calls=fresh();m.put(PLAYER,8,P)
  m.put(PARAM+8,1,profile);m.put(PARAM+18,1,flags);m.put(PARAM+44,1,9)
  for actor in [A,G,P]:m.put(actor+1464,4,0xffffffff);m.put(actor+1244,4,typ);m.put(actor+688,8,actor+1024)
  m.put(OWNER_CELL,8,T)
  # Native helper boundaries remain opaque. The embedded-list initializer
  # supplies a one-member list fixture; this is not a claim about its body.
  def inner(x):
   member=x.reg('rcx');x.put(INNER_HEAD,8,member);x.put(INNER_TAIL,8,member);x.put(member+80,4,encode(0));x.setreg('rax',0)
  m.stubs.update({B+0x3eafc0:lambda x:x.setreg('rax',PARAM),B+0x3cf0f0:inner,
   B+0x3d0260:lambda x:x.setreg('eax',0),B+0x3cf400:lambda x:x.setreg('eax',7),
   B+0x3cf490:lambda x:x.setreg('eax',11),B+0x3d8a40:lambda x:x.setreg('rax',P+2048)})
  row=invoke(m,0x3cf830,(T,owner,geometry,17,22,-1,-1),f'construct owner{owner:x} geometry{geometry:x} profile{profile} flags{flags:x}')
  receiver=P if profile==1 else owner
  need(dec[m.get(T+12,4)]==owner and dec[m.get(T+16,4)]==receiver and dec[m.get(T+20,4)]==geometry,'original owner / replacement receiver / geometry binding')
  for actor in [A,G,P]:
   expected=(0xffffffff+int(owner==actor)+int(geometry==actor))&0xffffffff
   need(m.get(actor+1464,4)==expected,'only original owner and geometry counted, modulo DWORD')
  transform=P+2048 if flags&2 else receiver+1024+128 if flags&8 else owner+128 if owner else 0
  need(dec[m.get(T+40,4)]==transform,'local transform-source priority')
  need(m.get(HEAD,8)==m.get(TAIL,8)==T and dec[m.get(T+196,4)]==0,'constructor appends first contact')
  need(m.reg('rax')==T and m.get(T+32,4)==7 and m.get(T+36,4)==9,'constructor raw return and IDs')
  need(m.get(T+8,4)&0x400==0,'allocated-ID path lacks supplied-ID flag')
  row.update(owner=hex(owner),receiver=hex(receiver),geometry=hex(geometry),counterAlias=owner!=0 and owner==geometry)
 # Complete cleanup paths with first/middle/last node and owned/supplied IDs.
 for entry in [0x3cfb10,0x3cfcb0,0x40f4a0,0x40f4c0]:
  for position in [0,1,2]:
   for provided in [False,True]:
    deletion=[0,1,5] if entry in [0x3cfcb0,0x40f4c0] else [0]
    for deleteflags in deletion:
     m,encode,dec,calls=fresh();nodes=[T,T+768,T+1536];victim=nodes[position]
     m.put(HEAD,8,nodes[0]);m.put(TAIL,8,nodes[-1]);m.put(INNER_HEAD,8,nodes[0]+60);m.put(INNER_TAIL,8,nodes[-1]+60)
     for j,node in enumerate(nodes):
      m.put(node+196,4,encode(nodes[j+1] if j<2 else 0));m.put(node+140,4,encode(nodes[j+1]+60 if j<2 else 0));m.put(node+64,4,0xffffffff)
     for actor in [A,G,P]:m.put(actor+1464,4,0);m.put(actor+3228,4,0xffffffff)
     m.put(A+3320,8,victim);m.put(G+3320,8,0xabcdef)
     m.put(victim+12,4,encode(A));m.put(victim+16,4,encode(P));m.put(victim+20,4,encode(G));m.put(victim+8,4,0x400 if provided else 0);m.put(victim+32,4,5)
     m.put(victim+720,8,OWNER_CELL);m.put(OWNER_CELL,8,victim)
     def actors(x):x.setreg('rax',{0:A,A:G,G:0}[x.reg('rcx')])
     def release_id(x):calls.append(('release_id',x.reg('ecx')))
     def free(x):
      calls.append(('free',x.reg('rcx')))
      need(x.reg('rcx')==victim and m.get(HEAD,8)!=victim and m.get(TAIL,8)!=victim,'free follows unlink')
      if entry==0x40f4c0:need(m.get(OWNER_CELL,8)==0,'derived owner cell clear before free')
     m.stubs.update({B+0x3d2e50:actors,B+0x3cf3a0:release_id,B+0x152570:free})
     # nullsub_1 is a named external boundary, preserving its passed object/size.
     null_target=next(i.operands[0].imm for i in instructions.values() if i.address==(B+0x40f513 if entry==0x40f4c0 else B+0x3cfe4b))
     def alternate(x):calls.append(('alternate',x.reg('rcx'),x.reg('edx')))
     m.stubs[null_target]=alternate
     row=invoke(m,entry,(victim,deleteflags),f'cleanup{entry:x} pos{position} provided{provided} delete{deleteflags}')
     remaining=[n for n in nodes if n!=victim]
     need(m.get(HEAD,8)==remaining[0] and m.get(TAIL,8)==remaining[-1] and dec[m.get(remaining[0]+196,4)]==remaining[-1],'contact list repaired')
     need(m.get(INNER_HEAD,8)==remaining[0]+60 and m.get(INNER_TAIL,8)==remaining[-1]+60 and dec[m.get(remaining[0]+140,4)]==remaining[-1]+60,'embedded list repaired')
     need(dec[m.get(victim+196,4)]==0 and dec[m.get(victim+140,4)]==0,'retired next links encoded-null')
     need(m.get(A+1464,4)==0xffffffff and m.get(G+1464,4)==0xffffffff and m.get(P+1464,4)==0,'counter decrement is modulo DWORD and excludes replacement receiver')
     need([dec[m.get(victim+x,4)] for x in [12,16,20]]==[A,P,G],'cleanup leaves three encoded actor fields locally unchanged')
     for actor in [A,G]:need(m.get(actor+3228,4)==(0xffffffff if provided else 0xffffffdf),'conditional actor bit clear')
     need(m.get(A+3320,8)==(victim if provided else 0) and m.get(G+3320,8)==0xabcdef,'matching actor raw contact slot cleared only in owned-ID path')
     need(('release_id',5) in calls if not provided else not calls or all(c[0]!='release_id' for c in calls),'conditional ID release')
     if entry in [0x40f4a0,0x40f4c0]:need(m.get(OWNER_CELL,8)==0,'derived outer owner cell cleared')
     if entry in [0x3cfcb0,0x40f4c0]:need(m.reg('rax')==victim,'deleting wrapper returns original object')
     else:need(m.reg('rax')==0,'nondeleting wrapper propagates fixture encoded-null helper result')
     row['externalCalls']=[list(c) for c in calls]
 # Boundary indices are tested as arithmetic only, with allocated synthetic table.
 for ident in [0,1,31,32,63,64,511]:
  m,encode,dec,calls=fresh();m.put(T+32,4,ident);index=ident//32
  for j in range(17):m.put(A+4+j*4,4,0xffffffff)
  invoke(m,0x3cf7f0,(A,T),f'bit removal id{ident}')
  need(m.get(A+4+index*4,4)==(0xffffffff^(1<<(ident%32))),'selected ID bit cleared')
  need(all(m.get(A+4+j*4,4)==0xffffffff for j in range(17) if j!=index),'other synthetic table words unchanged')
 return {'kind':'Original-instruction fixtures with explicit engine/codec stubs','cases':cases,'caseCount':len(cases),'steps':steps,'distinctExecutedInstructions':len(visited),'limits':['No native execution, lifetime/concurrency proof, live reachability or all-writers claim.','Ptr32 is a supplied bijection and list membership is a trusted fixture; unknown reads/writes are rejected.','Constructor helper3CF0F0 is a stub establishing a synthetic one-member embedded list; its native behavior is not asserted.','Actor enumeration and external frees/ID helpers are stubs; counter wrap is arithmetic only.','BTS uses register operands only; only CF is modeled, and subsequent flag-dependent paths overwrite their tested flags before use.','Caller-save clobbering, exceptions and concurrent mutation are not modeled.']}
