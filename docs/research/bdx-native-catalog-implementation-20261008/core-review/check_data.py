import argparse,hashlib,json,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description='Check catalog metadata against the SHA-pinned original game PE.')
parser.add_argument('--original',type=Path,default=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe'))
raw=parser.parse_args().original.read_bytes()
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha(raw)=='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
pe=struct.unpack_from('<I',raw,0x3c)[0];count=struct.unpack_from('<H',raw,pe+6)[0];opt=pe+24;optsz=struct.unpack_from('<H',raw,pe+20)[0]
base=struct.unpack_from('<Q',raw,opt+24)[0];sections=[]
for n in range(count):
 s=opt+optsz+n*40;vs,va,rs,rp=struct.unpack_from('<IIII',raw,s+8);sections.append((va,rs,rp))
def read(rva,n):
 for va,rs,rp in sections:
  if va<=rva and rva+n<=va+rs:return raw[rp+rva-va:rp+rva-va+n]
 raise AssertionError((rva,n))
source=ROOT/'src/KH2Trainer.Core/Data/BdxNativeCalls.json';j=json.loads(source.read_text());assert j['schema']==1 and j['originalSha256']==sha(raw)
banks=[]
for b in j['banks']:
 bank=b['bank'];original=struct.unpack('<Q',read(0x753490+bank*8,8))[0]
 table=original-base if original else {3:0x72f1a0,9:0x73d080}[bank]
 assert b['state']==(1 if original else 2) and b['tableRva']==table
 banks.append({'bank':bank,'state':b['state'],'tableRva':table})
assert [b['bank'] for b in banks]==list(range(11))
keys=set();rows=[]
for d in j['descriptors']:
 key=(d['bank'],d['index']);assert key not in keys;keys.add(key)
 rva=banks[d['bank']]['tableRva']+16*d['index'];handler,flags,pad=struct.unpack('<QII',read(rva,16));handler=handler-base if handler else 0
 assert pad==0 and d['descriptorRva']==rva and d['handlerRva']==handler and d['flags']==flags
 assert all(isinstance(d[name],str) for name in ('name','summary','notes','evidence'))
 rows.append({'bank':d['bank'],'index':d['index'],'descriptorRva':rva,'handlerRva':handler,'flags':flags})
assert len(rows)==150 and sum(bool(d['name']) for d in j['descriptors'])==44
assert {d['index'] for d in j['descriptors'] if d['bank']==0}==set(range(105))
assert {d['index'] for d in j['descriptors'] if d['bank']==9}==set(range(41))
# Recheck the exact native bodies underlying the disputed 1:6 annotation.
ev=ROOT/'docs/research/bdx-rebind-operands-20261008/evidence.json';e=json.loads(ev.read_text());checked=[]
for f in e['functions']:
 if int(f['addr'],16) in (0x14042e220,0x1403ca0e0):
  text=f['originalBytes'];b=bytes(int(x,16) for x in text.split()) if '0x' in text else bytes.fromhex(text)
  assert read(int(f['addr'],16)-base,len(b))==b;checked.append({'addr':f['addr'],'bytes':len(b),'sha256':sha(b)})
assert len(checked)==2
oracle={'banks':banks,'descriptors':rows};(OUT/'descriptor-oracle.json').write_text(json.dumps(oracle,indent=2)+'\n')
result={'success':True,'originalSha256':sha(raw),'productJsonSha256':sha(source.read_bytes()),'banks':len(banks),'descriptors':len(rows),'annotations':44,'metadataComparedToOriginalPe':True,'selectedAnnotationBodies':checked,'scope':'All numeric descriptors/bank snapshot states checked against original bytes. Selected1:6 native bodies rechecked. This does not independently re-prove every descriptive annotation.'}
(OUT/'data-review.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
