"""Read-only Event10 census and bounded stored-instruction prefix model.

No target code is executed. Unknown reads/calls/opcodes stop the model. Two
explicit native read summaries are opt-in assumptions, never silent no-ops.
"""
import collections,hashlib,importlib.util,json,struct
from pathlib import Path
HERE=Path(__file__).resolve().parent
RESEARCH=HERE.parent
GAME=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-')
LOOSE=GAME/'Modding/openkh/data/kh2'
DECODER=RESEARCH/'bdx-inspection-20261008/bdx_inspect.py'
CENSUS=RESEARCH/'app-timer-dispatch-20261008/script-event10-census.json'
def digest(data):return hashlib.sha256(data).hexdigest()
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
decoder=module('timer_stored_decoder',DECODER)
def ptr(kind,offset=0):return(kind,offset)
def i32(v):return ((v+0x80000000)&0xffffffff)-0x80000000
def add(a,b):
 if isinstance(a,tuple)and isinstance(b,int):return(a[0],a[1]+i32(b))
 if isinstance(b,tuple)and isinstance(a,int):return(b[0],b[1]+i32(a))
 if isinstance(a,int)and isinstance(b,int):return(a+b)&0xffffffff
 raise Stop('unsupported pointer arithmetic')
class Stop(Exception):pass
def closure(doc,start):
 nodes={x['pc']:x for x in doc['instructions']};seen=set();todo=[start];missing=[]
 while todo:
  pc=todo.pop()
  if pc in seen:continue
  if pc not in nodes:missing.append(pc);continue
  seen.add(pc);todo.extend(e['target']for e in nodes[pc]['edges']if e['target']is not None)
 return [nodes[pc]for pc in sorted(seen)],sorted(set(missing))
def read_asset(row):
 raw=(LOOSE/row['asset']).read_bytes();data=raw[row['offset']:row['offset']+row['length']]
 assert len(data)==row['length'] and digest(data)==row['scriptSha256']
 doc=decoder.inspect(data);event=next(e for e in doc['header']['events']if e['id']==10 and not e['shadowed'])
 assert event['pc']==row['events'][0]['pc']
 return raw,data,doc
def run(data,doc,start,args,work=None,summaries=None,maximum=2048):
 nodes={x['pc']:x for x in doc['instructions']};stack=list(args);frames=[];frame=16;pc=start;mem={ptr('work',k):v for k,v in(work or{}).items()}
 trace=[];reads=[];writes=[];branches=[];calls=[];native=[];status=None;stop_pc=None
 def pop():
  if not stack:raise Stop('stack underflow in model')
  return stack.pop()
 def load(p):
  reads.append(dict(pc=pc,address=p))
  if p not in mem:raise Stop('unknown memory read')
  return mem[p]
 def store(p,v):
  if not isinstance(p,tuple)or p[0]not in('frame','work'):raise Stop('write outside modeled frame/work')
  if p[0]=='work' and not 0<=p[1]<=doc['header']['workSize']-4:raise Stop('work write outside declared bytes')
  mem[p]=v;writes.append(dict(pc=pc,address=p,value=v))
 def address(sub,offset):
  if sub==0:return ptr('frame',frame+offset)
  if sub==1:return ptr('work',offset)
  if sub==2:return add(load(ptr('frame',frame)),offset)
  if sub==3:return ptr('script',16+2*offset)
  raise Stop('unsupported address selector')
 try:
  for step in range(maximum):
   if pc not in nodes:raise Stop('PC outside decoded event-rooted graph')
   x=nodes[pc];trace.append(pc);g,mode,sub,ops=x['group'],x['mode'],x['sub'],x['operands'];nxt=i32(pc+x['width'])
   if g==0:
    if mode==0:stack.append(ops[0]|ops[1]<<16)
    elif mode==1:stack.append(struct.unpack('<f',struct.pack('<HH',*ops))[0])
    elif mode==2:stack.append(address(sub,ops[0]))
    else:stack.append(load(address(sub,ops[0])))
   elif g==1:store(address(sub,ops[0]),pop())
   elif g==3:stack.append(load(add(pop(),ops[0])))
   elif g==4:
    if sub:raise Stop('bulk indirect store outside model')
    value=pop();store(pop(),value)
   elif g==5:
    value=pop()
    if mode==0 and sub in(4,8):stack.append(int(value==0))
    else:raise Stop('unmodeled unary operation')
   elif g==6:
    right,left=pop(),pop()
    if mode==0 and sub==0:stack.append(add(left,right))
    elif mode==0 and sub==1 and isinstance(left,int)and isinstance(right,int):stack.append((left-right)&0xffffffff)
    elif mode==0 and sub==2 and isinstance(left,int)and isinstance(right,int):stack.append((left*right)&0xffffffff)
    else:raise Stop('unmodeled binary operation')
   elif g==7:
    if sub not in(0,1,2):raise Stop('invalid branch selector')
    value=None if sub==0 else pop();take=sub==0 or(value==0 if sub==1 else value!=0)
    target=next(e['target']for e in x['edges']if e['kind']in('branch','conditional-branch'))
    branches.append(dict(pc=pc,value=value,taken=take,target=target));nxt=target if take else nxt
   elif g in(8,11):
    if sub<2:raise Stop('call frame below native return slots')
    target=next(e['target']for e in x['edges']if e['kind']=='call');frames.append((frame,nxt));frame+=4*sub
    calls.append(dict(pc=pc,target=target,frame=frame));nxt=target
   elif g==9:
    if sub==2:
     if not frames:status='root return';break
     frame,nxt=frames.pop()
    elif sub==3:pop()
    elif sub==5:
     if not stack:raise Stop('dup of empty stack')
     stack.append(stack[-1])
    elif sub in(0,1):status='yield'if sub==0 else'exit';break
    else:raise Stop('unmodeled control')
   elif g==10:
    key=(sub,ops[0]);call=dict(pc=pc,bank=sub,index=ops[0],stackBefore=list(stack))
    if key==(4,21)and'4:21'in(summaries or{}):
     call['summary']='Captured native boolean read; caller supplies result under native prerequisites.';call['result']=int(bool(summaries['4:21']));stack.append(call['result']);native.append(call)
    elif key==(1,39)and'1:39'in(summaries or{}):
     index,wrapper=pop(),pop();assert index==1 and wrapper==ptr('work',0)
     call['summary']='Captured native read of Actor DWORD+2552 through Work+4 binding; caller supplies value under valid binding/lifetime.';call['result']=summaries['1:39']&0xffffffff;stack.append(call['result']);native.append(call)
    else:native.append(call);status='native boundary';break
   else:raise Stop('unmodeled opcode group')
   pc=nxt
  else:status='step budget'
 except Stop as ex:status=str(ex)
 stop_pc=pc
 return dict(status=status,stopPc=stop_pc,pcs=trace,reads=reads,writes=writes,branches=branches,calls=calls,native=native,stackAtStop=stack)
def build():
 source=json.loads(CENSUS.read_bytes());rows=[];selected={};variants={};literal=[];work_only=[]
 for entry in source['events']:
  raw,data,doc=read_asset(entry);start=entry['events'][0]['pc'];reachable,missing=closure(doc,start)
  constants=[i['pc']for i in reachable if i['group']==0 and i['mode']==0 and i['operands']==[74,0]]
  prefix=run(data,doc,start,[74,0]);key=entry['scriptSha256'];variants[key]=prefix
  row=dict(asset=entry['asset'],assetSha256=digest(raw),scriptSha256=key,offset=entry['offset'],length=entry['length'],header=doc['header'],event10Pc=start,syntacticInstructionCount=len(reachable),missingTargets=missing,diagnostics=doc['diagnostics'],decodedConstant74Pcs=constants,prefix74=prefix)
  rows.append(row)
  work_writes=[w for w in prefix['writes']if w['address'][0]=='work']
  if prefix['status']=='root return'and work_writes:
   work_only.append(dict(asset=entry['asset'],scriptSha256=key,event10Instructions=reachable,prefix74=prefix,workWrites=work_writes))
  if constants:
   literal.append(dict(asset=entry['asset'],scriptSha256=key,pcs=constants))
   selected[entry['asset']]=dict(row=row,event10Instructions=reachable,data=data,document=doc)
 representative=['obj/M_EX950.mdlx','obj/N_EX650_BTL10.mdlx','obj/B_EX120.mdlx','obj/B_EX120_HB_LV99.mdlx']
 witnesses=[]
 for asset in representative:
  v=selected[asset];data=v['data'];doc=v['document'];entry=v['row'];start=entry['event10Pc'];cases=[]
  options=([dict(work={540:x},summaries={})for x in(0,1,0xffffffff)]if asset.endswith('M_EX950.mdlx')else
           [dict(work={},summaries={'1:39':x})for x in(0,1,2,0xffffffff)]if 'N_EX650'in asset else
           [dict(work={},summaries={'4:21':x})for x in(0,1)])
  for message in(74,0):
   for option in options:cases.append(dict(message=message,parameter=0,assumptions=option,result=run(data,doc,start,[message,0],**option)))
  init=next(e['pc']for e in doc['header']['events']if e['id']==0 and not e['shadowed'])
  init_trace=run(data,doc,init,[ptr('incoming Actor')]);wrapper=428 if'M_EX950'in asset else 0 if'N_EX650'in asset else 144
  binding=[w for w in init_trace['writes']if w['address']==ptr('work',wrapper+4)and w['value']==ptr('incoming Actor')]
  assert binding,'wrapper binding must be established before first unknown native boundary'
  strings=[]
  for ins in v['event10Instructions']:
   if ins['group']==0 and ins['mode']==2 and ins['sub']==3:
    at=16+2*ins['operands'][0];end=data.find(b'\0',at);assert end>=at
    strings.append(dict(pc=ins['pc'],addressWord=ins['operands'][0],fileOffset=at,raw=data[at:end+1].hex(),value=data[at:end].decode('ascii')))
  init_ins={i['pc']:i for i in doc['instructions']}
  witnesses.append(dict(asset=asset,scriptSha256=entry['scriptSha256'],wrapperWorkOffset=wrapper,wrapperBindingStores=binding,event0Prefix=init_trace,event0Instructions=[init_ins[pc]for pc in sorted(set(init_trace['pcs']))],event10Instructions=v['event10Instructions'],scriptStrings=strings,cases=cases))
 return dict(schema=1,source=str(CENSUS.relative_to(RESEARCH)),sourceSha256=digest(CENSUS.read_bytes()),decoderSha256=digest(DECODER.read_bytes()),
  scope='The prior hash-pinned 66 Event10 loose-asset rows only (53 distinct script byte sequences). Syntactic graph is event-rooted, not a raw word scan. Prefix model stops at unknown reads/native effects/unsupported operations and is not runtime execution.',
  rows=rows,distinctScripts=len(variants),prefixOutcomesByAsset=dict(collections.Counter(r['prefix74']['status']for r in rows)),prefixOutcomesByDistinctScript=dict(collections.Counter(r['status']for r in variants.values())),
  decodedConstant74=literal,selected=witnesses,workOnlyHandlers=work_only,
  limits=['A decoded immediate74 is only a selection aid; selected frame/message comparisons and conditional prefixes establish its role.','Absence of an immediate74 does not exclude arithmetic/indirect/native handling of74.','Work and Actor reads are assumptions where supplied; validity, concurrent mutation and actual scheduling are not proven.','Native1:8 and1:262 effects beyond captured dispatch helpers remain boundaries; native calls are not silently ignored.'])
if __name__=='__main__':
 result=build();(HERE/'script-analysis.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
 print(json.dumps(dict(assets=len(result['rows']),variants=result['distinctScripts'],literal74Assets=len(result['decodedConstant74']),outcomes=result['prefixOutcomesByAsset'],selected=[(x['asset'],x['wrapperBindingStores'])for x in result['selected']])))
