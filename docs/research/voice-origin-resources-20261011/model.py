"""Explicit branch models; valid memory and sequential normal returns are premises.
The model does not execute game code or validate concurrent resource ownership.
"""
import copy, itertools, struct

def prepare(origin, *, kind=34, alias=False, size=48, bar_resolved=False,
            replacement_disabled=False, found=None):
 result=copy.deepcopy(origin)
 if bar_resolved or not size or alias or kind not in (31,34,48) or replacement_disabled or origin['signature']!=b'ORIGIN\0':return result
 if found is None:result.update(payload=0,payload_size=0)
 else:result.update(payload=found[0],payload_size=found[1],name_last=0)
 return result

def start(origin):
 result=copy.deepcopy(origin)
 if origin['signature']!=b'ORIGIN\0':raise ValueError('This model is restricted to ORIGIN')
 if not result['payload']:return result,[]
 result['key']=result['payload']&0xffffffff
 return result,[('invalidate',result['key'],2),('register',result['key'],result['payload'],result['payload_size'],2,2),('create',result['key']),('play',result['key'])]

def release_events(origin,kind=34,alias=False,size=48,owner=True):
 events=[]
 if size and not alias and kind in (34,48) and origin['signature']==b'ORIGIN\0' and origin['key']:
  events.append(('invalidate',origin['key'],2))
 if owner:events.append(('destroy_resource_entry',))
 return events

def bank_destructor_payload(mode,payload,waits_return=True):
 if not waits_return:return 'not_reached'
 return 'aligned_free_then_zero' if mode!=2 and payload else ('zero' if mode!=2 else 'unchanged')

def mutation_offsets(version,header_offset,sequence_offsets):
 assert version in (1,2,3,4)
 table=header_offset+(16 if version==1 else 32)
 return table,[offset+15 for offset in sequence_offsets]

def run():
 cases=[]
 def check(name,condition,**details):
  assert condition,name
  cases.append(dict(name=name,**details))
 initial=dict(signature=b'ORIGIN\0',key=7,payload=0x12340000,payload_size=256,name_last=99)
 for kind,alias,disabled,resolved,found in itertools.product((0,31,34,48,49),(False,True),(False,True),(False,True),(None,(0x10020000,512))):
  got=prepare(initial,kind=kind,alias=alias,replacement_disabled=disabled,bar_resolved=resolved,found=found)
  eligible=kind in (31,34,48) and not (alias or disabled or resolved)
  expected=initial.copy()
  if eligible:expected.update(payload=0 if found is None else found[0],payload_size=0 if found is None else found[1])
  if eligible and found is not None:expected['name_last']=0
  check('prepare-gates',got==expected and got['key']==7,kind=kind,alias=alias,disabled=disabled,resolved=resolved,found=found is not None)
 for pointer in (0,1,0xffff,0x100000000,0x10000ffff,0x140123400,0x240123400,0xffffffffffffffff):
  state=initial|dict(payload=pointer)
  got,events=start(state)
  check('start-key',got['key']==(pointer&0xffffffff if pointer else 7) and bool(events)==bool(pointer),pointer=hex(pointer),key=hex(got['key']))
 a,ea=start(initial|dict(payload=0x140123400));b,eb=start(initial|dict(payload=0x240123400))
 check('low32-alias',a['key']==b['key'] and ea[0]==eb[0])
 z,events=start(initial|dict(payload=0x100000000))
 check('nonnull-payload-zero-key',z['key']==0 and len(events)==4 and release_events(z)==[('destroy_resource_entry',)])
 s,events=start(initial|dict(payload=0x10000ffff))
 check('retirement-sentinel-key',s['key']==0xffff and events[0]==('invalidate',0xffff,2))
 for kind,key,alias,owner in itertools.product((31,34,48),(0,7,0xffffffff),(False,True),(False,True)):
  events=release_events(initial|dict(key=key),kind=kind,alias=alias,owner=owner)
  expected=[]
  if kind in (34,48) and key and not alias:expected.append(('invalidate',key,2))
  if owner:expected.append(('destroy_resource_entry',))
  check('release-order',events==expected,kind=kind,key=key,alias=alias,owner=owner)
 for mode,payload,wait in itertools.product((0,1,2,3,-1),(0,0x1234),(False,True)):
  result=bank_destructor_payload(mode,payload,wait)
  expected='not_reached' if not wait else ('unchanged' if mode==2 else ('aligned_free_then_zero' if payload else 'zero'))
  check('destructor-mode',result==expected,mode=mode,payload=payload,waits_return=wait)
 for global_present,key,ready in itertools.product((False,True),(0,7,0xffff,0xffffffff),(False,True)):
  check('retirement-gate',(global_present and key==0xffff and ready)==(all((global_present,ready)) and key==65535),global_present=global_present,key=key,ready=ready)
 for version,head in itertools.product((1,2,3,4),(32,48,65535)):
  table,positions=mutation_offsets(version,head,[128,320,512])
  data=bytearray(1024);before=bytes(data)
  for p in positions:data[p]=255
  check('borrowed-payload-sequence-markers',table==head+(16 if version==1 else 32) and [i for i in range(len(data)) if data[i]!=before[i]]==[143,335,527],version=version,header_offset=head)
 # Model08C1A0's selected intrusive-node writes, including a previous valid bank.
 # These cases assume0889B0 completed and its offset104 was not overwritten.
 for bucket_index,has_tail in itertools.product(range(64),(False,True)):
  bank=bytearray([0xA5]*160);previous=bytearray([0x5A]*160)
  struct.pack_into('<Q',bank,8,0x140123400);struct.pack_into('<Q',bank,40,0)
  before=bytes(bank);old_previous=bytes(previous)
  offset=104
  struct.pack_into('<Q',bank,offset+16,0x142B81340+32*bucket_index)
  struct.pack_into('<Q',bank,offset,0x12340000 if has_tail else 0)
  struct.pack_into('<Q',bank,offset+8,0)
  if has_tail:struct.pack_into('<Q',previous,offset+8,0x12350000)
  changed={i for i,(x,y) in enumerate(zip(bank,before)) if x!=y}
  previous_changed={i for i,(x,y) in enumerate(zip(previous,old_previous)) if x!=y}
  check('initialized-bucket-preserves-sequence-fields',changed<=set(range(104,128)) and previous_changed<=set(range(112,120)) and all(bank[a:b]==before[a:b] for a,b in ((0,8),(8,16),(40,48),(128,129),(152,154))),bucket=bucket_index,has_tail=has_tail,node_offset=offset)
 # Negative controls demonstrate why the previous unqualified claim was too strong.
 for offset,field in ((0,8),(24,40)):
  bank=bytearray([0xA5]*160);before=bytes(bank)
  struct.pack_into('<Q',bank,offset,0);struct.pack_into('<Q',bank,offset+8,0);struct.pack_into('<Q',bank,offset+16,0x142B81340)
  check('changed-bucket-offset-breaks-preservation',bank[field:field+8]!=before[field:field+8],node_offset=offset,affected_field=field)
 # A sequential demonstration of the bounded local order, not a live UAF witness.
 state,_=start(initial)
 release=release_events(state)
 deferred_bank={'key':0xffff,'payload':state['payload'],'mode':2}
 check('resource-delete-does-not-clear-origin-or-bank-pointer',release[-1]==('destroy_resource_entry',) and state['payload']==deferred_bank['payload'] and bank_destructor_payload(2,state['payload'])=='unchanged')
 return dict(status='PASS',cases=len(cases),results=cases,premises=['Valid readable/writable buffers and intact, nonoverlapping bank/list objects','For the selected payload-mutation path,0889B0 completed and bucket+24 offsets remain104','Sequential calls and normal returns','No resource allocation, real audio, thread scheduling, live reachability or exception simulation'],limits='Case counts measure this model only; they are not coverage of all native behavior.')

if __name__=='__main__':
 import json
 print(json.dumps(run(),indent=2))
