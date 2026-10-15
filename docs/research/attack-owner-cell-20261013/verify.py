"""Compare five complete IDA captures with the original PE; no game execution."""
from pathlib import Path
import hashlib,json,struct
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'src/KH2Trainer').is_dir())
ORIGINAL=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
sha=lambda b:hashlib.sha256(b).hexdigest()
raw=ORIGINAL.read_bytes()
assert sha(raw)=='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
pe=struct.unpack_from('<I',raw,0x3c)[0]
sections_at=pe+24+struct.unpack_from('<H',raw,pe+20)[0]
sections=[struct.unpack_from('<IIII',raw,sections_at+i*40+8) for i in range(struct.unpack_from('<H',raw,pe+6)[0])]
def original(addr,size):
 rva=addr-0x140000000
 for _,va,n,offset in sections:
  if va<=rva and rva+size<=va+n:return raw[offset+rva-va:offset+rva-va+size]
 raise ValueError(hex(addr))
byte_rows=json.loads((HERE/'bytes.json').read_bytes())['result']
captured={int(x['addr'],16):bytes(int(v,16) for v in x['data'].split()) for x in byte_rows}
sizes={0x3d25d0:324,0x3d29b0:46,0x3d24b0:90,0x3d0eb0:80,0x3d2720:126}
inventory={int(x['address'],16):x for line in (ROOT/'docs/research/coverage/function_status.jsonl').read_text().splitlines() if (x:=json.loads(line))['domain']=='native'}
decoder=Cs(CS_ARCH_X86,CS_MODE_64)
records=[]
for rva,size in sizes.items():
 addr=0x140000000+rva
 name='3d25d0-insns.json' if rva==0x3d25d0 else f'0x{addr:X}-insns.json'
 query=json.loads((HERE/name).read_bytes())['result'][0]
 assert query['cursor']['done'] and not query['truncated'] and not query['error']
 data=captured[addr][:size]
 assert data==original(addr,size)
 decoded=list(decoder.disasm(data,addr))
 assert sum(i.size for i in decoded)==size
 assert [int(m['addr'],16) for m in query['matches']]==[i.address for i in decoded]
 assert query['count']==query['scanned']==len(decoded)
 assert inventory[addr]['size']==size
 records.append({'addr':hex(addr),'size':size,'sha256':sha(data),'instructions':len(decoded),
 'priorClaimStatus':inventory[addr]['claimStatus'],'priorNewClaimIds':inventory[addr]['newClaimIds'],
 'originalBytes':data.hex(),'disassembly':[{'addr':hex(i.address),'bytes':i.bytes.hex(),'instruction':i.mnemonic+' '+i.op_str} for i in decoded]})
report={'status':'PASS','scope':'Five complete original-PE/IDA body comparisons. Static dataflow findings, no game/native execution or global lifetime proof.',
 'originalSha256':sha(raw),'idaSession':'9d62332c','autoAnalysisReady':False,
 'functions':records,'functionCount':len(records),'instructions':sum(x['instructions'] for x in records),'originalBodyBytes':sum(x['size'] for x in records),
 'extraCapturedBytes':{'0x1403d0eb0':5,'scope':'Trailing bytes excluded from the function and every instruction count.'}}
(HERE/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:report[k] for k in ['status','functionCount','instructions','originalBodyBytes']}))
