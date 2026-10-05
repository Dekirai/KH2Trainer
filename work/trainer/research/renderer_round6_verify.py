"""Verify original-byte provenance and complete capture of round6 renderer evidence.

Reads the original EXE and captured JSON only; writes this round's verification report.
"""
from pathlib import Path
import hashlib
import json
import struct

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'work/trainer/research'
EXE = Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
EXPECTED = '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
blob = EXE.read_bytes()
sha = hashlib.sha256(blob).hexdigest()
assert sha == EXPECTED
pe = struct.unpack_from('<I', blob, 0x3c)[0]
assert blob[pe:pe+4] == b'PE\0\0'
count = struct.unpack_from('<H', blob, pe+6)[0]
opt_size = struct.unpack_from('<H', blob, pe+20)[0]
opt = pe+24
assert struct.unpack_from('<H', blob, opt)[0] == 0x20b
base = struct.unpack_from('<Q', blob, opt+24)[0]
sections=[]
for i in range(count):
    p=opt+opt_size+40*i
    vsize,rva,rawsize,rawptr=struct.unpack_from('<4I',blob,p+8)
    sections.append((rva,rawsize,rawptr))
def original(addr,size):
    rva=int(addr,16)-base
    for start,length,pos in sections:
        if start <= rva and rva+size <= start+length:
            return blob[pos+rva-start:pos+rva-start+size],pos+rva-start
    raise ValueError((addr,size))

raw=json.loads((OUT/'renderer_round6_idb_bytes.json').read_text(encoding='utf-8'))
results=[]
for kind,rows in [('function',raw['functions']),('data',raw['data']['result'])]:
    for row in rows:
        assert not row.get('error') and row['data']
        captured=bytes(int(x,16) for x in row['data'].split())
        source,pos=original(row['addr'],len(captured))
        assert source == captured, row['addr']
        results.append(dict(addr=row['addr'],kind=kind,size=len(source),file_offset=hex(pos),sha256=hashlib.sha256(source).hexdigest(),identical=True))

captures=[]
for path in sorted(OUT.glob('renderer_round6_full*.json')):
    for row in json.loads(path.read_text(encoding='utf-8'))['functions']:
        pages=row['pages']; lines=[]; offset=0
        for index,p in enumerate(pages):
            assert p['offset']==offset and p['total_instructions']==pages[0]['total_instructions']
            assert p['instruction_count']==len(p['asm']['lines'])
            assert int(p['asm']['start_ea'],16)==int(row['addr'],16)
            assert not p.get('error') and not p['cursor'].get('cancelled',False)
            offset+=p['instruction_count']; lines+=p['asm']['lines']
            if index+1 < len(pages):
                assert p['cursor']['next']==offset and not p['cursor'].get('done',False)
            else:
                assert p['cursor']['done'] and p['cursor'].get('next') is None
        assert offset == pages[0]['total_instructions'] and offset>0
        assert len({int(x['addr'],16) for x in lines})==offset
        assert int(lines[0]['addr'],16)==int(row['addr'],16)
        start=int(row['addr'],16); end=start+int(row['size'],16)
        assert all(start<=int(x['addr'],16)<end for x in lines)
        pc=row['codepages']; next_line=0
        for index,p in enumerate(pc):
            assert p['offset']==next_line and p['code'] and not p.get('error')
            assert not p['cursor'].get('cancelled',False)
            next_line+=p['line_count']
            if index+1<len(pc): assert p['cursor']['next']==next_line
            else: assert p['cursor']['done'] and p['cursor'].get('next') is None
        assert next_line==pc[0]['total_lines']
        matches=[x for x in results if x['kind']=='function' and int(x['addr'],16)==start]
        assert len(matches)==1 and matches[0]['size']==int(row['size'],16)
        captures.append(dict(addr=row['addr'],instructions=offset,pseudocode_lines=next_line,evidence=str(path.relative_to(ROOT)).replace('\\','/')))
assert len({x['addr'] for x in captures})==len(captures)==len(raw['functions'])
report=dict(source=str(EXE),source_sha256=sha,session=raw['session'],function_count=len(captures),instructions=sum(x['instructions'] for x in captures),function_bytes=sum(x['size'] for x in results if x['kind']=='function'),all_original_bytes_match=True,all_asm_and_pseudocode_complete=True,captures=captures,bytes=results,limits='Capture completeness and byte identity establish provenance. They do not imply semantic coverage or runtime validation. No IDB, EXE, product source or process was modified.')
(OUT/'renderer_round6_verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ['source_sha256','function_count','instructions','function_bytes','all_original_bytes_match','all_asm_and_pseudocode_complete']},indent=2))
