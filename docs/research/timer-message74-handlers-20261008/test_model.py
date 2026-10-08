"""Counterexample and witness checks for the bounded offline prefix model."""
import json
import analyze_scripts as a
def test():
 checks=0
 def ck(ok,why):
  nonlocal checks
  checks+=1
  assert ok,why
 result=a.build();ck(len(result['rows'])==66 and result['distinctScripts']==53,'bounded input census')
 ck(result['prefixOutcomesByAsset']=={'native boundary':15,'root return':49,'unknown memory read':2},'all prefixes classified without silently skipping an opcode')
 ck(len(result['decodedConstant74'])==8,'eight assets/four byte variants selected by decoded graph')
 ck(len({x['scriptSha256']for x in result['decodedConstant74']})==4,'duplicate asset byte identity')
 ck(len(result['workOnlyHandlers'])==2,'return paths with Work mutation remain visible')
 for selected in result['selected']:
  for c in selected['cases']:
   r=c['result'];native=r['native'];asset=selected['asset'];message=c['message']
   effects=[x for x in native if (x['bank'],x['index'])in((1,8),(1,262))]
   workwrites=[w for w in r['writes']if w['address'][0]=='work']
   if 'M_EX950'in asset:
    flag=c['assumptions']['work'][540];ck(bool(effects)==(message==74 and flag==0),'M: leave request iff message74 and Work540 zero')
    ck(bool(workwrites)==(message==74 and flag!=0),'M: pending flag iff message74 and Work540 nonzero')
    if workwrites:ck(workwrites==[dict(pc=68,address=('work',544),value=1)],'M exact Work store')
   elif 'N_EX650'in asset:
    value=c['assumptions']['summaries']['1:39'];ck(bool(effects)==(message==74 and value==1),'audience: slot1 exactly one')
    if effects:ck(effects[0]['stackBefore'][-3:]==[('work',0),8,3],'audience exact downstream arguments')
   else:
    flag=c['assumptions']['summaries']['4:21'];ck(bool(effects)==(message==74 and flag==1),'B_EX120: gated failure action')
    if effects:ck(effects[0]['stackBefore'][-2]==('work',144),'B_EX120 original wrapper')
   ck(all('summary'in x or x is native[-1] for x in native),'only explicit read summaries may precede stop')
  ck(len(selected['wrapperBindingStores'])==1,'one captured Event0 Actor backlink before first native boundary')
  ck(selected['event0Prefix']['status']=='native boundary','initialization prefix stops at first native boundary')
 source=json.loads(a.CENSUS.read_bytes())['events']
 for asset in ('obj/M_EX950.mdlx','obj/N_EX650_BTL10.mdlx'):
  row=next(r for r in source if r['asset']==asset);_,data,doc=a.read_asset(row);pc=row['events'][0]['pc']
  if'M_EX950'in asset:
   ck(a.run(data,doc,pc,[74,0])['status']=='unknown memory read','unset Work state is never invented')
   for message in range(256):
    r=a.run(data,doc,pc,[message,0],work={540:0});ck((r['status']=='native boundary')==(message==74),'M complete byte-message branch partition')
  else:
   for message in range(256):
    r=a.run(data,doc,pc,[message,0]);ck((r['status']=='native boundary')==(message in(74,90,123)),'audience shared branch admits74,90,123')
  ck(a.run(data,doc,pc,[])['status']=='stack underflow in model','missing incoming args fail closed')
  ck(a.run(data,doc,pc,[74,0],maximum=1)['status']=='step budget','budget exhaustion is explicit')
 # No summary exists for effectful 1:8, even when caller tries to supply one.
 row=next(r for r in source if r['asset']=='obj/M_EX950.mdlx');_,data,doc=a.read_asset(row)
 r=a.run(data,doc,row['events'][0]['pc'],[74,0],work={540:0},summaries={'1:8':0})
 ck(r['status']=='native boundary'and r['stopPc']==75,'unknown native effects cannot be supplied as a no-op')
 for asset,offset in [('obj/B_EX170.mdlx',296),('obj/B_EX170_LV99.mdlx',312)]:
  row=next(r for r in source if r['asset']==asset);_,data,doc=a.read_asset(row)
  for message in range(256):
   r=a.run(data,doc,row['events'][0]['pc'],[message,0]);writes=[w for w in r['writes']if w['address'][0]=='work']
   ck(r['status']=='root return'and len(writes)==1 and writes[0]['address']==('work',offset)and writes[0]['value']==int(message==82),
      'default branch changes Work for74 despite no explicit74 immediate')
 return dict(success=True,checks=checks,limits='Bounded stored-byte model tests and chosen conditional representatives; no game or native trap execution.')
if __name__=='__main__':print(json.dumps(test()))
