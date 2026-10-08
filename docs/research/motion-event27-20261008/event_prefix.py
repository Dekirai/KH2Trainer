"""Closed-subset Event27 prefix model; stop before first effectful native call.
Not an emulator or proof that game state satisfies the supplied values.
Only 1:15 is summarized: exact captured adapter reads decode(arg0)+384.
"""
import json,struct
import asset_audit as assets
def ptr(s,n=0):return(s,n)
def add(a,b):
 if isinstance(a,tuple):return(a[0],a[1]+b)
 if isinstance(b,tuple):return(b[0],b[1]+a)
 return(a+b)&0xffffffff
def run(data,joint,flag,source_field,work5044,timer):
 actor=ptr('incoming Actor');source=ptr('gate source from Work+580');record=ptr('contact record')
 mem={ptr('work',580):source,ptr('work',932):flag,ptr('work',5044):work5044}
 mem.update({ptr('work',8+4*i):timer for i in range(4)})
 stack=[actor,joint,record];frames=[];frame=16;pc=2904;visited=[];calls=[];branches=[];reads=[];decoder=assets.load_decoder()
 def pop():assert stack,('underflow',pc);return stack.pop()
 def addr(sub,off):
  if sub==0:return ptr('frame',frame+off)
  if sub==1:return ptr('work',off)
  if sub==2:return add(mem[ptr('frame',frame)],off)
  raise AssertionError(('unexpected selector',sub,pc))
 def load(p):reads.append(dict(pc=pc,address=list(p)));return mem[p]
 for step in range(1000):
  x=decoder.instruction(data,pc);visited.append(pc);nxt=pc+x['width'];g,mode,sub,ops=x['group'],x['mode'],x['sub'],x['operands']
  if g==0:
   if mode==0:stack.append(ops[0]|ops[1]<<16)
   elif mode==1:stack.append(struct.unpack('<f',struct.pack('<HH',*ops))[0])
   elif mode==2:stack.append(addr(sub,ops[0]))
   else:stack.append(load(addr(sub,ops[0])))
  elif g==1:mem[addr(sub,ops[0])]=pop()
  elif g==3:
   assert mode==0 and sub==0;stack.append(load(add(pop(),ops[0])))
  elif g==5:
   v=pop()
   if mode==0 and sub in (4,8):stack.append(int(v==0))
   elif mode==1 and sub==7:stack.append(int(v<=0))
   else:raise AssertionError(('unary',pc))
  elif g==6:
   b,a=pop(),pop()
   if mode==0 and sub==0:stack.append(add(a,b))
   elif mode==0 and sub==1:stack.append((a-b)&0xffffffff)
   elif mode==0 and sub==2:stack.append((a*b)&0xffffffff)
   elif mode==1 and sub==1:stack.append(a-b)
   else:raise AssertionError(('binary',pc))
  elif g==7:
   take=sub==0 or (pop()==0 if sub==1 else pop()!=0)
   target=next(e['target'] for e in x['edges'] if e['kind'] in ('branch','conditional-branch'))
   branches.append(dict(pc=pc,taken=take,target=target));nxt=target if take else nxt
  elif g in(8,11):
   target=next(e['target'] for e in x['edges'] if e['kind']=='call');frames.append((frame,nxt));frame+=sub*4
   calls.append(dict(pc=pc,target=target,frame=frame));nxt=target
  elif g==9:
   if sub==2:
    if not frames:return dict(result='root return before effectful trap',pcs=visited,calls=calls,branches=branches,reads=reads)
    frame,nxt=frames.pop()
   elif sub==3:pop()
   elif sub==5:stack.append(stack[-1])
   else:raise AssertionError(('control',pc))
  elif g==10:
   if (sub,ops[0])==(1,15):
    assert pop()==source;stack.append(source_field)
   elif (sub,ops[0])==(1,87):
    args=stack[-4:];assert args==[actor,{103:213,83:214,127:215,121:216}[joint],1,0]
    return dict(result='first effectful trap',pc=pc,bank=1,index=87,arguments=[list(v)if isinstance(v,tuple)else v for v in args],pcs=visited,calls=calls,branches=branches,reads=reads)
   else:raise AssertionError(('unexpected trap before stop',pc,sub,ops))
  else:raise AssertionError(('opcode',pc))
  pc=nxt
 raise AssertionError('step bound')
def build():
 raw=(assets.LOOSE/'obj/B_LK120.mdlx').read_bytes();e=next(x for x in assets.bar(raw)if x['type']==3);data=raw[e['offset']:e['offset']+e['length']]
 allowed={1,3,4,5,213,214,221,222,233,164};sources=sorted(allowed|{47,0})
 traces={};cases=[]
 for joint in(103,83,127,121,94,0):
  for flag in(0,1):
   for src in sources:
    for work in(0,7):
     for timer in(0.0,1.0):
      r=run(data,joint,flag,src,work,timer);key=assets.digest(json.dumps(r,sort_keys=True).encode())
      traces[key]=r;expected=(src in allowed or src==47 and work==7)if flag==0 else src==164
      expected=expected and joint in(103,83,127,121)and timer<=0
      assert (r['result']=='first effectful trap')==expected
      cases.append(dict(joint=joint,work932=flag,gateSource384=src,work5044=work,timer=timer,trace=key,expectedFirstEffectfulTrap=expected))
 return dict(schema=1,scriptSha256=assets.digest(data),
  scope='Offline concrete representatives of conditional stored-byte prefixes; no game execution. Gate source is assumed readable; Work+580 is not asserted equal to incoming Actor. Stop before trap1:87, whose effects and later native calls remain external.',
  conditions=['Work+932 selects gate branch: zero vs nonzero.','1:15 reads DWORD at decode(Work+580)+384.','If Work+932 is zero: allowed values1,3,4,5,213,214,221,222,233,164, or47 together with Work+5044==7. Otherwise only164.',
  'Incoming joint103/83/127/121 maps to parameter213/214/215/216 and timer slot Work+8/+12/+16/+20.','Finite timer<=0 reaches trap1:87 with [incoming Actor, parameter,1,0].'],
  cases=cases,traces=traces,caseCount=len(cases),uniqueTraceCount=len(traces))
if __name__=='__main__':
 d=build();(assets.HERE/'event27-prefixes.json').write_text(json.dumps(d,indent=2)+'\n',encoding='utf8');print(json.dumps({k:d[k]for k in('caseCount','uniqueTraceCount')}))
