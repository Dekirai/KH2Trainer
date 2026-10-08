"""Verify complete captured ASM and runtime pins against the retail PE. No process access."""
from pathlib import Path
import argparse,hashlib,json,re,struct

folder=Path(__file__).resolve().parent
root=folder.parents[2]
ev=json.loads((folder/'evidence.json').read_text(encoding='utf-8-sig'))
parser=argparse.ArgumentParser()
parser.add_argument('--original',type=Path,default=Path(ev['originalPath']))
raw=parser.parse_args().original.read_bytes()
assert hashlib.sha256(raw).hexdigest()==ev['originalSha256']
pe=struct.unpack_from('<I',raw,0x3c)[0]
assert raw[:2]==b'MZ' and raw[pe:pe+4]==b'PE\0\0'
base=int(ev['imageBase'],16)
section_start=pe+24+struct.unpack_from('<H',raw,pe+20)[0]
sections=[struct.unpack_from('<4I',raw,section_start+40*i+8) for i in range(struct.unpack_from('<H',raw,pe+6)[0])]
def disk(addr,size):
    rva=addr-base
    for _,va,raw_size,offset in sections:
        if va<=rva and rva-va+size<=raw_size:
            start=offset+rva-va
            assert start+size<=len(raw)
            return raw[start:start+size]
    raise AssertionError(('Unbacked PE span',hex(addr),size))
def unhex(s): return bytes(int(x,16) for x in s.split())
bodies={};instructions=0
for f in ev['functions']:
    addr=int(f['addr'],16);size=int(f['size'],16)
    assert addr not in bodies and size==int(f['analysis']['size'],16)
    body=unhex(f['original_bytes'])
    assert len(body)==size and body==disk(addr,size)
    joined=[];offset=0
    for i,p in enumerate(f['pages']):
        rows=p['asm']['lines'];cursor=p['cursor']
        assert p['offset']==offset and rows and not cursor.get('cancelled',False)
        assert p['instruction_count']==len(rows) and p['total_instructions']==f['total_instructions']
        joined+=rows;offset+=len(rows)
        if i+1<len(f['pages']): assert not cursor.get('done',False) and cursor.get('next')==offset
        else: assert cursor.get('done') is True and 'next' not in cursor
    assert joined==f['asm']['lines'] and len(joined)==f['instruction_count']==f['total_instructions']
    assert f['cursor'].get('done') is True and not f['cursor'].get('cancelled',False)
    addresses=[int(row['addr'],16) for row in joined]
    assert addresses==sorted(set(addresses)) and addresses[0]==addr
    assert all(addr<=a<addr+size for a in addresses) and all(r['instruction'].strip() for r in joined)
    bodies[addr-base]=body;instructions+=len(joined)
for d in ev['data']:
    data=unhex(d['original_bytes'])
    assert len(data)==d['size'] and data==disk(int(d['addr'],16),d['size'])
source=root/'src/KH2Trainer.Bridge/CombatGuardPins.inl'
text=source.read_text(encoding='utf-8-sig')
pins=re.findall(r'static const BYTE combatPin_([0-9a-f]+)\[\] = \{(.*?)\};',text,re.S)
pin_bytes=0;seen=set()
for key,contents in pins:
    data=bytes(int(b,16) for b in re.findall(r'0x([0-9A-Fa-f]{2})',contents))
    rva=int(key,16)
    assert rva not in seen and data==bodies[rva],key
    seen.add(rva);pin_bytes+=len(data)
entries=re.findall(r'\{0x([0-9a-f]+),combatPin_([0-9a-f]+),sizeof\(combatPin_([0-9a-f]+)\)\}',text)
assert len(entries)==len(pins)==9 and all(a==b==c for a,b,c in entries)
assert {int(a,16) for a,_,_ in entries}==seen
result={'success':True,'originalSha256':ev['originalSha256'],'functions':len(bodies),'instructions':instructions,
    'originalBytes':sum(map(len,bodies.values())),'originalDataBytes':sum(d['size'] for d in ev['data']),
    'runtimePins':len(pins),'runtimePinBytes':pin_bytes,'runtimePinSourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),
    'scope':'Complete ASM metadata and original disk bytes verified. No live gameplay and no whole-program semantic proof.'}
(folder/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
