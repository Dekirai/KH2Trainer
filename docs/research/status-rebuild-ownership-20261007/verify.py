"""Offline completeness/original-byte validation. No process access or IDB writes."""
from pathlib import Path
import argparse, hashlib, json, struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

folder=Path(__file__).resolve().parent
ev=json.loads((folder/'evidence.json').read_text(encoding='utf-8-sig'))
p=argparse.ArgumentParser();p.add_argument('--original',type=Path,default=Path(ev['originalPath']))
raw=p.parse_args().original.read_bytes()
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
def unhex(s):return bytes(int(x,16) for x in s.split())
md=Cs(CS_ARCH_X86,CS_MODE_64);seen=set();counts=0;body_bytes=0
for f in ev['functions']:
    addr=int(f['addr'],16);size=int(f['size'],16)
    assert addr not in seen and addr==int(f['analysis']['addr'],16)
    assert size==int(f['analysis']['size'],16)
    body=unhex(f['original_bytes']);assert len(body)==size and body==disk(addr,size)
    joined=[];offset=0
    for i,page in enumerate(f['pages']):
        rows=page['asm']['lines'];cursor=page['cursor']
        assert page['offset']==offset and rows and not cursor.get('cancelled',False)
        assert page['instruction_count']==len(rows) and page['total_instructions']==f['total_instructions']
        joined+=rows;offset+=len(rows)
        if i+1<len(f['pages']):assert cursor.get('next')==offset and not cursor.get('done',False)
        else:assert cursor.get('done') is True and 'next' not in cursor
    assert joined==f['asm']['lines'] and len(joined)==f['instruction_count']==f['total_instructions']
    assert f['cursor'].get('done') is True and not f['cursor'].get('cancelled',False)
    addresses=[int(row['addr'],16) for row in joined]
    assert addresses==sorted(set(addresses)) and addresses[0]==addr
    for index,row in enumerate(joined):
        ip=int(row['addr'],16);assert addr<=ip<addr+size and row['instruction'].strip()
        insn=list(md.disasm(body[ip-addr:],ip,count=1));assert len(insn)==1
        assert insn[0].address==ip and ip+insn[0].size<=addr+size
        if index+1<len(joined):assert ip+insn[0].size<=addresses[index+1]
    assert f['pc']['cursor'].get('done') is True and not f['pc'].get('truncated',False)
    seen.add(addr);counts+=len(joined);body_bytes+=size
for d in ev['data']:
    b=unhex(d['original_bytes']);assert len(b)==d['size'] and b==disk(int(d['addr'],16),d['size'])
result={'success':True,'originalSha256':ev['originalSha256'],'functions':len(seen),'instructions':counts,
        'originalBytes':body_bytes,'originalDataOrFragmentBytes':sum(d['size'] for d in ev['data']),
        'limitations':'Per-instruction independent decode validates boundaries; embedded data is not claimed as instructions. No runtime/writer-exhaustiveness proof.'}
(folder/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
