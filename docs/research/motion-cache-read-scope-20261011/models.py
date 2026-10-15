"""Small policy counterexamples grounded in the documented order; not native execution."""
def run():
 traces=[]
 def observe(name, stages):
  out=[]
  for label,active,queue,state,known,expect in stages:
   admitted=active==0 and not queue and state==3 and known
   assert admitted==expect,(name,label)
   out.append({'stage':label,'active':active,'queue':queue,'nodeState':state,'knownOrdinaryOrigin':known,'admitted':admitted})
  traces.append({'name':name,'observations':out})
 observe('successful ordinary async load',[
 ('cache entered',1,False,0,True,False),('enqueued',2,True,1,True,False),
 ('submit returned; bases already equal',0,True,1,True,False),('worker state1',0,True,1,True,False),
 ('worker state2; consumer not started',0,True,1,True,False),('consumer fixup',1,True,1,True,False),
 ('callback set state3; still linked',1,True,3,True,False),('last unlink before consumer return',1,False,3,True,False),
 ('outer consumer returned',0,False,3,True,True)])
 observe('zero-result failure',[('callback failure',1,True,255,True,False),('request consumed',0,False,255,True,False)])
 observe('suppressed submit',[('cache state1 but no enqueue',0,False,1,True,False)])
 observe('reentrant callback submits new request',[('outer callback state3',2,True,3,True,False),('outer consumer returned but new request pending',0,True,3,True,False)])
 observe('unknown child with same stable fields',[('queue empty; same bases and state3',0,False,3,False,False)])
 observe('synchronous relocation',[('planner changed target',1,False,3,True,False),('recursive movement active',2,False,1,True,False),('inner finalization completed',1,False,3,True,False),('outer completed',0,False,3,True,True)])
 observe('existing call missed at installation',[('reported active0/queue0 but origin unknown',0,False,3,False,False)])
 profiles=[]
 for high in range(16):
  b=(high<<4)|1
  native_special=(b&0xc0)==0x40
  policy=(b&0xf)==1 and (b&0x40)==0
  assert policy==(high in [0,1,2,3,8,9,10,11])
  assert not (policy and native_special)
  profiles.append({'byte3':b,'nativeSpecialPath':native_special,'copierPolicyAdmitsProfile':policy})
 # Bit40+C0 distinction is intentional, and profiles do not imply complete BAR validity.
 assert profiles[12]['nativeSpecialPath']==False and profiles[12]['copierPolicyAdmitsProfile']==False
 return {'kind':'policy-order models, not original-native execution','traceCount':len(traces),'stateObservations':sum(len(t['observations']) for t in traces),'profileCases':len(profiles),'traces':traces,'profiles':profiles,'limits':'Events and preconditions, including synchronous alias-free provider completion, are supplied by each model. No concurrency, actual lifetime, scheduler identity, byte ownership or hook completeness is proven.'}
