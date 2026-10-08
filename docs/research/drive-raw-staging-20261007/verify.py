"""Check complete IDA exports against the original on-disk PE, without game access."""
from pathlib import Path
import hashlib,json,struct

folder=Path(__file__).resolve().parent
ev=json.loads((folder/'evidence.json').read_text(encoding='utf-8-sig'))
original=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
raw=original.read_bytes()
assert hashlib.sha256(raw).hexdigest()==ev['originalSha256']
pe=struct.unpack_from('<I',raw,0x3c)[0]
assert raw[:2]==b'MZ' and raw[pe:pe+4]==b'PE\0\0'
section_start=pe+24+struct.unpack_from('<H',raw,pe+20)[0]
count=struct.unpack_from('<H',raw,pe+6)[0]
base=int(ev['imageBase'],16)
def original_at(addr,size):
    for i in range(count):
        _,va,n,offset=struct.unpack_from('<4I',raw,section_start+40*i+8)
        if va<=addr-base and addr-base-va+size<=n:
            start=offset+addr-base-va
            assert start+size<=len(raw)
            return raw[start:start+size]
    raise AssertionError('Unbacked original span')
instructions=total_bytes=0
for f in ev['functions']:
    addr,size=int(f['addr'],16),int(f['analysis']['size'],16)
    body=bytes(int(x,16) for x in f['bytes'].split())
    assert len(body)==size and body==original_at(addr,size)
    rows=f['asm']['lines']; addresses=[int(x['addr'],16) for x in rows]
    assert f['cursor']['done'] and not f['cursor'].get('cancelled',False)
    assert f['instruction_count']==f['total_instructions']==len(rows)
    assert addresses==sorted(set(addresses)) and addresses[0]==addr
    assert all(addr<=x<addr+size for x in addresses)
    assert len(f['pages'])==1 and f['pages'][0]['asm']==f['asm']
    pseudocode=f['pseudocode']
    assert pseudocode['cursor']['done'] and not pseudocode.get('truncated',False)
    assert pseudocode['line_count']==pseudocode['total_lines']
    instructions+=len(rows); total_bytes+=size
report=dict(success=True,functions=len(ev['functions']),instructions=instructions,originalBytes=total_bytes,originalSha256=ev['originalSha256'],scope='Complete recorded ASM and retail bytes; specific claims only, no live gameplay or whole-subsystem proof.')
(folder/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report))
