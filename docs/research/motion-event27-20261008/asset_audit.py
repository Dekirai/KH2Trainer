"""Read-only bounded BAR23/BDX census and original Event27 witness decoder.
No word search, asset execution, target process, or game-file writes.
"""
import collections, hashlib, importlib.util, json, struct
from pathlib import Path
HERE=Path(__file__).resolve().parent
GAME=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-')
LOOSE=GAME/'Modding/openkh/data/kh2'
DECODER=HERE.parent/'bdx-inspection-20261008/bdx_inspect.py'
def digest(b):return hashlib.sha256(b).hexdigest()
def load_decoder():
 s=importlib.util.spec_from_file_location('motion_bdx_decoder',DECODER);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def bar(raw):
 assert len(raw)>=16 and raw[:4]==b'BAR\x01'
 count,base=struct.unpack_from('<iI',raw,4);assert base==0 and 0<=count<=65536 and 16+count*16<=len(raw)
 result=[]
 for i in range(count):
  off=16+i*16;t,link,tag,start,n=struct.unpack_from('<HH4sII',raw,off)
  assert not n or 16+count*16<=start<=start+n<=len(raw)
  result.append(dict(ordinal=i,type=t,link=link,tagHex=tag.hex(),offset=start,length=n,headerHex=raw[off:off+16].hex()))
 return result
def definitions(data):
 assert len(data)>=64
 count,mask=struct.unpack_from('<iI',data);assert count>=0 and 64+20*count<=len(data)
 selected=[]
 for i in range(count):
  at=64+i*20;g,t=data[at],data[at+4]
  if t in (10,11):
   selected.append(dict(ordinal=i,offset=at,group=g,type=t,jointId=struct.unpack_from('<H',data,at+6)[0],height=struct.unpack_from('<h',data,at+18)[0],raw=data[at:at+20].hex()))
 return dict(count=count,defaultGroupMask=mask,recordEnd=64+20*count,trailingBytes=len(data)-64-20*count,headerHex=data[:64].hex(),contactDefinitions=selected)
def closure(doc,start):
 nodes={i['pc']:i for i in doc['instructions']};seen=set();pending=[start]
 while pending:
  pc=pending.pop()
  if pc in seen:continue
  assert pc in nodes,(pc,'missing decoded instruction');seen.add(pc)
  pending.extend(e['target'] for e in nodes[pc]['edges'] if e['target'] is not None)
 return [nodes[p] for p in sorted(seen)]
def build():
 decoder=load_decoder();inventory=[];type23=[];scripts=[];errors=[];empty=[]
 files=sorted((LOOSE/'obj').glob('*.mdlx'),key=lambda p:p.name.lower())
 assert files
 for path in files:
  asset=path.relative_to(LOOSE).as_posix();raw=path.read_bytes();sha=digest(raw)
  item=dict(asset=asset,sha256=sha,length=len(raw));inventory.append(item)
  try:entries=bar(raw)
  except (AssertionError,struct.error) as e:errors.append(dict(asset=asset,stage='BAR',error=str(e)));continue
  item['barEntries']=len(entries)
  for e in entries:
   data=raw[e['offset']:e['offset']+e['length']]
   if e['type'] in (3,23) and not e['length']:
    empty.append(dict(asset=asset,bar=e));continue
   if e['type']==23:
    try:
     d=definitions(data);type23.append(dict(asset=asset,bar=e,sha256=digest(data),**d))
    except (AssertionError,struct.error) as ex:errors.append(dict(asset=asset,stage='BAR23',ordinal=e['ordinal'],error=str(ex)))
   if e['type']==3:
    try:
     doc=decoder.inspect(data);ev=[v for v in doc['header']['events'] if v['id']==27 and not v['shadowed']]
     scripts.append(dict(asset=asset,bar=e,sha256=digest(data),header=doc['header'],instructionCount=len(doc['instructions']),diagnostics=doc['diagnostics'],event27=ev))
    except (AssertionError,ValueError,struct.error) as ex:errors.append(dict(asset=asset,stage='BDX',ordinal=e['ordinal'],error=str(ex)))
 witness_asset='obj/B_LK120.mdlx';r=(LOOSE/witness_asset).read_bytes();entries=bar(r)
 bdx_entry=next(e for e in entries if e['type']==3);data=r[bdx_entry['offset']:bdx_entry['offset']+bdx_entry['length']]
 doc=decoder.inspect(data);root=next(e['pc'] for e in doc['header']['events'] if e['id']==27 and not e['shadowed'])
 reachable=closure(doc,root);pcs={i['pc'] for i in reachable}
 witness=dict(asset=witness_asset,assetSha256=digest(r),bar=entries,bdxSha256=digest(data),header=doc['header'],
   event27Pc=root,closureScope='Syntactic over-approximation: both conditional edges, all static calls and possible continuations; returns terminate. Native trap side effects/callbacks and script mutation are excluded.',
   event27Instructions=reachable,event27Traps=[dict(pc=i['pc'],bank=i['bank'],index=i['index']) for i in reachable if i['group']==10],
   reachableRebindTraps=[i['pc'] for i in reachable if i.get('bank')==2 and i.get('index') in (9,95)],
   wholeScriptRebindTraps=[dict(pc=i['pc'],bank=i['bank'],index=i['index'],inEvent27Closure=i['pc'] in pcs) for i in doc['instructions'] if i.get('bank')==2 and i.get('index') in (9,95)],
   type23=next(v for v in type23 if v['asset']==witness_asset),
   scriptDiagnostics=doc['diagnostics'])
 return dict(schema=1,scope='All direct obj/*.mdlx loose files present, bounded BAR parsing; all direct BAR23 records and BAR3 BDX headers. No recursive BAR or other asset classes; only selected B_LK120 independently matches retail package.',
  decoderSha256=digest(DECODER.read_bytes()),files=len(files),inventory=inventory,type23=type23,scripts=scripts,emptyEntries=empty,errors=errors,
  totals=dict(type23=len(type23),scripts=len(scripts),event27Scripts=sum(bool(s['event27']) for s in scripts),
   contactDefinitions=sum(len(d['contactDefinitions']) for d in type23),maximumContactsInOnePayload=max(len(d['contactDefinitions']) for d in type23)),
  witness=witness)
if __name__=='__main__':
 d=build();(HERE/'asset-census.json').write_text(json.dumps(d,indent=2)+'\n',encoding='utf8')
 print(json.dumps(dict(files=d['files'],totals=d['totals'],errors=len(d['errors']),witnessTraps=d['witness']['event27Traps'],event27Instructions=len(d['witness']['event27Instructions']),rebind=d['witness']['wholeScriptRebindTraps'])))
