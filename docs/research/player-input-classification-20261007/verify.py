"""Read-only original-PE verification for full input/event/controller captures."""
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
def raw(x):return bytes(int(t,16) for t in x.split())
md=Cs(CS_ARCH_X86,CS_MODE_64);count=0;size=0;gaps=[]
for f in e['functions']:
    a=int(f['addr'],16);data=raw(f['original_bytes'])
    assert len(data)==int(f['size'],16) and data==disk(a,len(data)),f['addr']
    rows=f['asm']['lines'];pages=f['pages'];pc=f['pseudocode']
    assert pc['cursor']=={'done':True} and not pc.get('truncated') and pc['line_count']==pc['total_lines']
    assert len(pages)==1 and pages[0]['offset']==0 and pages[0]['cursor']=={'done':True}
    assert rows==pages[0]['asm']['lines'] and len(rows)==f['instruction_count']==f['total_instructions']==pages[0]['instruction_count']==pages[0]['total_instructions']
    assert f['cursor']=={'done':True}
    addresses=[int(x['addr'],16) for x in rows]
    assert addresses==sorted(set(addresses)) and addresses[0]==a
    covered=set()
    for addr in addresses:
        ins=list(md.disasm(data[addr-a:],addr,count=1))
        assert len(ins)==1 and ins[0].address==addr and addr+ins[0].size<=a+len(data)
        offsets=set(range(addr-a,addr-a+ins[0].size))
        assert not covered.intersection(offsets)
        covered.update(offsets)
    missing=sorted(set(range(len(data)))-covered)
    if missing:
        # FIELD_COMMAND reaction submenu switch has a 12-entry RVA table after RET.
        assert a==0x1404060E0 and missing==list(range(0x278,0x2A8)),(f['addr'],missing)
        targets=struct.unpack_from('<12I',data,0x278)
        assert all(base+t in addresses for t in targets)
        gaps.append({'addr':hex(a+0x278),'size':48,'kind':'12 switch target RVAs after final RET'})
    count+=len(rows);size+=len(data)
for d in e['data']:
    data=raw(d['original_bytes'])
    assert len(data)==d['size'] and data==disk(int(d['addr'],16),len(data))
source=p.parents[2]/'src/KH2Trainer.Bridge/GameplayStateSupport.inl'
native=source.read_text(encoding='utf-8-sig');pins=[]
for match in re.finditer(r'static const BYTE pin_([0-9A-Fa-f]+)\[\]\s*=\s*\{(.*?)\};',native,re.S):
    data=bytes(int(x,16) for x in re.findall(r'0x([0-9a-fA-F]{2})',match[2]));addr=base+int(match[1],16)
    assert data==disk(addr,len(data)),hex(addr)
    pins.append({'addr':hex(addr),'size':len(data)})
out={'passed':True,'sha256':e['originalSha256'],'functions':len(e['functions']),'instructions':count,'bodyBytes':size,
     'nonInstructionBodyRanges':gaps,'dataBytes':sum(d['size'] for d in e['data']),
     'runtimePins':len(pins),'runtimePinBytes':sum(x['size'] for x in pins),'pins':pins,
     'checks':['exact original PE SHA256','all captured IDA full-body bytes equal PE','finished ASM and pseudocode cursors/counts',
     'every instruction independently decoded with nonoverlapping Capstone boundaries','only explicit in-body switch data excluded from instruction count',
     'role/controller vtable and leaf bytes','every current gameplay_state pin equals original PE'],
     'scope':'Static original bytes and bounded control-flow evidence. No live process or blanket minigame-control claim.'}
(p/'verification.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out,indent=2))
