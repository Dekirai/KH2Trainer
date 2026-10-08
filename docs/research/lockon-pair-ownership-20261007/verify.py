"""Compare fresh complete IDA bodies with the exact retail PE; no process access."""
from pathlib import Path
import hashlib,json,struct,re
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
p=Path(__file__).resolve().parent
e=json.loads((p/'evidence.json').read_text(encoding='utf-8'))
b=Path(e['originalPath']).read_bytes()
assert hashlib.sha256(b).hexdigest()==e['originalSha256']
pe=struct.unpack_from('<I',b,60)[0]
s=pe+24+struct.unpack_from('<H',b,pe+20)[0]
sections=[struct.unpack_from('<4I',b,s+i*40+8) for i in range(struct.unpack_from('<H',b,pe+6)[0])]
base=int(e['imageBase'],16)
def disk(a,n):
    r=a-base
    for _,v,z,o in sections:
        if v<=r and r-v+n<=z:return b[o+r-v:o+r-v+n]
    raise AssertionError((a,n))
md=Cs(CS_ARCH_X86,CS_MODE_64); count=0; size=0
for f in e['functions']:
    a=int(f['addr'],16); raw=bytes(int(x,16) for x in f['original_bytes'].split())
    assert len(raw)==int(f['size'],16) and raw==disk(a,len(raw))
    rows=f['asm']['lines']; pages=f['pages']
    assert len(pages)==1 and pages[0]['offset']==0 and pages[0]['cursor']=={'done':True}
    assert rows==pages[0]['asm']['lines'] and len(rows)==f['instruction_count']==f['total_instructions']==pages[0]['instruction_count']==pages[0]['total_instructions']
    assert f['cursor']=={'done':True}
    instructions=list(md.disasm(raw,a))
    assert [i.address for i in instructions]==[int(x['addr'],16) for x in rows]
    assert sum(i.size for i in instructions)==len(raw)
    count+=len(rows);size+=len(raw)
for d in e['data']:
    raw=bytes(int(x,16) for x in d['original_bytes'].split())
    assert len(raw)==d['size'] and raw==disk(int(d['addr'],16),len(raw))
native=(p.parents[2]/'src/KH2Trainer.Bridge/TargetingFeatures.inl').read_text(encoding='utf-8-sig')
for name,addr,pin_size in [('scale',0x1403ABD60,29),('distance',0x1403ABD80,9)]:
    match=re.search(r'static const BYTE '+name+r'\[\]=\{(.*?)\};',native,re.S)
    assert match
    pinned=bytes(int(x,16) for x in re.findall(r'0x([0-9a-fA-F]{2})',match.group(1)))
    assert pinned==disk(addr,pin_size)
out={'passed':True,'sha256':e['originalSha256'],'functions':len(e['functions']),'instructions':count,'bodyBytes':size,'dataBytes':sum(d['size'] for d in e['data']),
     'runtimePins':2,'runtimePinBytes':38,'checks':['original PE SHA256','every full body byte','cursor/count/row consistency','independent Capstone instruction boundaries','both Float32 constants','both complete runtime setter pins'],
     'scope':'Static bytes and instruction coverage only; no live process and no universal behavioral proof.'}
(p/'verification.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out,indent=2))
