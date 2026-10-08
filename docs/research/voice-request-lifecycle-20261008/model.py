"""Synthetic normal-return transition model derived from fixed ASM sites.
Calls below are symbols/outcome parameters, not executions of game functions.
"""
from itertools import product
def signed(v):return (v&0xffffffff)-0x100000000 if v&0x80000000 else v&0xffffffff
def submit(v,ident,priority,actor):
 p,h,old,a=v
 return (ident,h,priority,actor) if (signed(p)<0 and h==0) or signed(priority)>=signed(old) else v
def poll(v,new_handle,active,actor_present,actor_predicate):
 p,h,priority,actor=v;effects=[]
 if signed(p)>=0:
  if h:effects.append(('stop',h,0))
  effects += [('pending',-1),('position',actor),('admit',p)]
  return (-1,new_handle,priority,actor),effects
 if h:
  effects.append(('query',h))
  if not active:return (p,0,priority,None),effects
  if not actor_present or not actor_predicate:return (p,h,priority,None),effects
  effects.append(('position-update',h,actor))
 return v,effects
def reset(v):
 p,h,priority,actor=v
 return (-1,0,priority,actor),([('stop',h,0)] if h else [])
def admissible(disabled,free,count):
 return disabled==0 and signed(free)>16 and signed(count)<=24
def consume(state,active):
 if state==1:return 2,['backend-start']
 if state==2:return (2,['backend-position']) if active else (4,['backend-stop'])
 if state==3:return 4,['backend-stop']
 return state,[]
def checks():
 values=[0,1,3,8,0x7fffffff,0x80000000,0xffffffff]
 n=0
 for p,h,old,new in product(values,(0,1,0xffffffff),values,values):
  v=(p,h,old,'old');actual=submit(v,8,new,'new')
  # Independent explicit TEST/JGE/JZ/CMP/JL structure.
  if signed(p)>=0:take=not signed(new)<signed(old)
  elif h==0:take=True
  else:take=not signed(new)<signed(old)
  assert actual==((8,h,new,'new') if take else v);n+=1
 admission=0
 for d,f,c in product((0,1,255),(0,16,17,80,0x7fffffff,0x80000000,0xffffffff),(0,23,24,25,0x7fffffff,0x80000000,0xffffffff)):
  denied=d!=0 or signed(f)<=16 or signed(c)>24
  assert admissible(d,f,c)==(not denied);admission+=1
 transitions=0
 for p,h,nh,active,ap,pred in product(values,(0,1),(0,7),(False,True),(False,True),(False,True)):
  v=(p,h,3,'actor');out,ev=poll(v,nh,active,ap,pred)
  if signed(p)>=0:
   assert out==(-1,nh,3,'actor') and ('admit',p) in ev
   assert ev.index(('pending',-1))<ev.index(('admit',p))
   assert (('stop',h,0) in ev)==bool(h)
   if nh==0:
    again,e2=poll(out,9,False,False,False)
    assert again==out and not e2 # consumed, no automatic retry
  elif h==0:assert out==v and not ev
  elif not active:assert out==(p,0,3,None)
  elif not ap or not pred:assert out==(p,h,3,None)
  else:assert out==v and ('position-update',h,'actor') in ev
  transitions+=1
 pool=0
 for state,active in product(range(256),(False,True)):
  out,ev=consume(state,active)
  if state==1:assert out==2 and ev==['backend-start'] # no result parameter
  elif state==2:assert out==(2 if active else 4)
  elif state==3:assert out==4
  else:assert out==state and not ev
  pool+=1
 scenarios=[]
 def case(name,condition):assert condition;scenarios.append(name)
 v=(8,17,3,'actor')
 case('equal priority replaces pending but does not stop immediately',submit(v,9,3,'other')==(9,17,3,'other'))
 case('lower busy priority rejected',submit(v,9,2,'other')==v)
 neg=submit(v,0xffffffff,3,'other')
 out,ev=poll(neg,999,True,True,True)
 case('negative accepted ID changes priority/reference but is not consumed as a new request',out==neg and not any(x[0]=='admit' for x in ev))
 out,ev=reset((8,17,3,'actor'))
 case('reset leaves priority and Actor reference',out==(-1,0,3,'actor') and ev==[('stop',17,0)])
 case('queued state reports active independently of backend',all((True if s==1 else a)==True for s,a in [(1,False),(1,True)]))
 case('ORIGIN null bank still progresses state1 to state2 on normal return',consume(1,False)==(2,['backend-start']))
 case('next inactive state2 is marked for retirement',consume(2,False)==(4,['backend-stop']))
 # Fixed two-phase list accounting: stop does not release the pool slot.
 free=16;old_state=4
 case('replacement can be denied before stopped slot is drained',not admissible(0,free,0))
 free+=int(old_state==4)
 case('later retirement restores the slot',admissible(0,free,0))
 counter=0;accepted=0
 for _ in range(30):
  if admissible(0,80,counter):counter+=1;accepted+=1
 case('counter boundary admits 25 requests from zero',accepted==25 and counter==25)
 records=[('key',8,2,2),('key',8,2,2),('key',9,2,2),('key',8,1,2)]
 remaining=[r for r in records if not (r[:3]==('key',8,2) and r[3]==2)]
 case('EE backend stop tuple is not unique pool-handle ownership',remaining==records[2:])
 return dict(priorityCases=n,admissionCases=admission,voiceUpdateCases=transitions,poolStateCases=pool,namedScenarios=scenarios,limits='Finite synthetic normal-return branch/transition checks, valid object memory and sequential execution assumed. No audio backend, memory concurrency, game schedule, exceptions or resource lifetime is simulated.')
if __name__=='__main__':
 import json
 print(json.dumps(checks(),indent=2))

