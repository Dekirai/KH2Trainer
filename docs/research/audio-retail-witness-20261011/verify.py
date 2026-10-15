"""Independent metadata re-read from existing loose files and bounded archive records.
No asset bytes are written. Does not duplicate the product package decoder.
"""
from pathlib import Path
import hashlib,json,struct,collections,argparse
ap=argparse.ArgumentParser();modes=ap.add_mutually_exclusive_group(required=True);modes.add_argument('--check',action='store_true');modes.add_argument('--write',action='store_true');args=ap.parse_args()
H=Path(__file__).resolve().parent
R=next(p for p in H.parents if (p/'src/KH2Trainer.Core/AssetArchiveReader.cs').is_file())
G=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-')
L=G/'Modding/openkh/data/kh2'
W=json.loads((H/'witness.json').read_text(encoding='utf-8-sig'))
checks=0
def ck(value,label):
 global checks
 checks+=1
 if not value:raise AssertionError(label)
def sha(b):return hashlib.sha256(b).hexdigest()
def span(p,n,length):return 0<=p<=length and 0<=n<=length-p
def u16(b,p):return struct.unpack_from('<H',b,p)[0]
def u32(b,p):return struct.unpack_from('<I',b,p)[0]
def i32(b,p):return struct.unpack_from('<i',b,p)[0]
def source(relative,pin):
 p=L/relative
 b=p.read_bytes()
 ck(len(b)==pin['physicalLength'] and sha(b)==pin['sha256'],'loose byte identity '+relative)
 return b
summary=[];wrapper_count=0;table_count=0
def scd(b,s,label):
 global table_count
 ck(b[:8]==b'SEDBSSCF','SCD signature')
 v=u32(b,8);h=u16(b,14);declared=u32(b,16)
 ck(v in (3,4) and span(h,32,len(b)),'selected header extent/version')
 scalar={'version':v,'headerOffset':h,'fieldByte12':b[12],'fieldByte13':b[13],'declaredLengthAt16':declared,'physicalLength':len(b),'physicalMinusDeclared':len(b)-declared,'sequenceCount':u16(b,h),'tableBCount':u16(b,h+2),'tableCCount':u16(b,h+4),'bankId':u16(b,h+6),'sequenceOffsetsTable':h+32,'tableBOffset':u32(b,h+8),'tableCOffset':u32(b,h+12),'auxOffsetsTable':u32(b,h+16),'headerInDeclaredLength':span(h,32,declared)}
 for key,value in scalar.items():ck(s[key]==value,'SCD scalar '+key)
 def table(key,offset,count,extent):
  global table_count
  ck(span(offset,count*4,len(b)),'table physical span')
  entries=[i32(b,offset+i*4) for i in range(count)]
  expected={'count':count,'tableBytes':count*4,'tableInPhysicalLength':True,'tableInDeclaredLength':span(offset,count*4,declared),'negativeOffsets':sum(o<0 for o in entries),'zeroOffsets':entries.count(0),'distinctOffsets':len(set(entries)),'minimumOffset':min(entries,default=None),'maximumOffset':max(entries,default=None),'referentMinimumBytes':extent,'referentSpansInPhysicalLength':sum(span(o,extent,len(b)) for o in entries),'referentSpansInDeclaredLength':sum(span(o,extent,declared) for o in entries)}
  ck(s[key]==expected,'independent table statistics '+key);table_count+=1
  return entries
 seq=table('sequenceTableStats',h+32,scalar['sequenceCount'],16 if v==3 else 32)
 table('tableBStats',scalar['tableBOffset'],scalar['tableBCount'],1)
 table('tableCStats',scalar['tableCOffset'],scalar['tableCCount'],1)
 if scalar['auxOffsetsTable']:table('auxTableStats',scalar['auxOffsetsTable'],scalar['sequenceCount'],128)
 else:ck(s['auxTableStats'] is None,'absent auxiliary table')
 rows=[]
 for i,p in enumerate(seq):
  if p<=0 or not span(p,16 if v==3 else 32,len(b)):continue
  rows.append(dict(index=i,relativeOffset=p,basicHeaderInDeclaredLength=span(p,16 if v==3 else 32,declared),tracksInSequence=b[p],kind=b[p+3],flags=u32(b,p+4),sequenceId=u16(b,p+12),fieldByte15=b[p+15]))
 ck(rows==s['sequenceHeaders'],'all selected sequence header fields')
 ids=[r['sequenceId'] for r in rows]
 ck(len(rows)==s['interpretedSequenceHeaders'] and len(set(ids))==s['uniqueSequenceIds'] and len(ids)-len(set(ids))==s['duplicateSequenceIdCount'],'sequence ID counts')
 for key,field in [('sequenceKinds','kind'),('sequenceByte15Values','fieldByte15')]:ck(s[key]==[dict(value=v,count=n) for v,n in sorted(collections.Counter(r[field] for r in rows).items())],'sequence histogram '+field)
 summary.append(dict(asset=label,sha256=sha(b),version=v,bankId=scalar['bankId'],sequences=scalar['sequenceCount'],tableB=scalar['tableBCount'],tableC=scalar['tableCCount'],physicalLength=len(b),declaredLength=declared,physicalMinusDeclared=len(b)-declared,byte15Values=s['sequenceByte15Values']))

ck(W['archiveRecords']==12 and len(W['selectedNames'])==10,'bounded selection count')
for pin in W['linkedSourcePins']:ck(sha((R/pin['path']).read_bytes())==pin['sha256'],'linked product source remains exact')
heds={}
for item in W['indices']:
 b=(G/'Image/dt'/item['hed']).read_bytes();heds[item['hed']]=b
 ck(sha(b)==item['sha256'] and len(b)//32==item['indexEntries'],'complete small HED fingerprint')
 ck((G/'Image/dt'/item['hed'].replace('.hed','.pkg')).stat().st_size==item['packageLength'],'package physical length')
for r in W['results']:
 hed=heds[r['hed']];row=hed[r['Ordinal']*32:(r['Ordinal']+1)*32]
 ck(hashlib.md5(r['asset'].encode()).digest()==row[:16] and row[:16].hex()==r['NameHash'],'selected name locator')
 ck(sha(row)==r['hedRowSha256'],'HED row identity')
 offset,stored,original=struct.unpack_from('<qii',row,16)
 ck((offset,stored,original)==(r['Offset'],r['StoredLength'],r['OriginalLength']),'record locator bounds')
 with (G/'Image/dt'/r['hed'].replace('.hed','.pkg')).open('rb') as f:
  f.seek(offset);remaining=stored;digest=hashlib.sha256()
  while remaining:
   data=f.read(min(65536,remaining));ck(bool(data),'stored selected record complete');digest.update(data);remaining-=len(data)
  ck(digest.hexdigest()==r['storedEntrySha256'],'selected encoded record hash')
  f.seek(offset);head=f.read(16);raw,count,mode,creation=struct.unpack('<4i',head);metadata=f.read(count*48)
 ck((raw,count,mode,creation)==(original,r['remasteredPartCount'],r['StoredMode'],r['CreationValue']),'package record header metadata')
 orig=source(r['asset'],r['original']);ck(r['original']['loose']['fullByteEquality'],'actual reader full equality result')
 if r['original']['scd']:scd(orig,r['original']['scd'],r['hed']+'/'+r['asset'])
 if r['audioChildren']:
  ck(orig[:4]==b'BAR\x01','audio child parent BAR')
  for w in r['audioChildren']:
   typ,link,tag,start,n=struct.unpack_from('<HH4sII',orig,16+w['Ordinal']*16)
   ck((typ,start,n)==(w['Type'],w['RelativeOffset'],w['Length']) and n==48,'BAR audio locator')
   b=orig[start:start+n];ck(sha(b)==w['sha256'] and b[:6]==b'ORIGIN','ORIGIN identity')
   name=b[16:48].split(b'\0',1)[0].decode('ascii')
   ck((name,len(name),len(name)>16,u16(b,8),u16(b,10),u32(b,12))==(w['nameAt16'],w['nameByteLength'],w['nameReachesRuntimeFieldAt32'],w['fieldU16At8'],w['fieldU16At10'],w['fieldU32At12']),'ORIGIN bounded disk fields')
   ck(sum(a['Name']==name for a in r['audioRemasters'])==1,'exact wrapper/replacement name association');wrapper_count+=1
 for a in r['audioRemasters']:
  p=a['Ordinal']*48;name=metadata[p:p+32].split(b'\0',1)[0].decode('ascii');logical,oldoff,rawlen,storedmode=struct.unpack_from('<IIii',metadata,p+32)
  ck((name,logical,oldoff,rawlen,storedmode)==(a['Name'],a['LogicalOffset'],a['OriginalAssetOffset'],a['physicalLength'],a['StoredMode']),'audio remaster header fields')
  relative='remastered/'+r['asset']+'/'+name
  data=source(relative,a);ck(a['loose']['fullByteEquality'],'actual reader remaster full equality result');scd(data,a['scd'],r['asset']+'/'+name)
ck(wrapper_count==W['wrapperSamples']==3 and len(summary)==W['scdSamples']==13,'complete selected witness set')
out={'status':'PASS_INDEPENDENT_METADATA_RECHECK','checks':checks,'archiveRecords':12,'ORIGINWrappers':wrapper_count,'SCDInstances':len(summary),'uniqueSCDHashes':len(set(s['sha256'] for s in summary)),'tableStatisticsChecked':table_count,'witnessSha256':sha((H/'witness.json').read_bytes()),'scope':'Independent Python parsing of existing loose files, original HED rows and bounded package record metadata/stored hashes. Full archive decoding and retail/loose byte comparison use the unmodified C# product reader; this recheck does not claim an independent decoder. No payload exports or original writes.','samples':summary}
if args.write:(H/'verification.json').write_text(json.dumps(out,indent=2)+'\n')
else:assert json.loads((H/'verification.json').read_text())==out,'stored verification must match independent recheck'
print(json.dumps({k:v for k,v in out.items() if k!='samples'}))
for s in summary:print(json.dumps(s))
