"""Read-only comparison of fresh IDB function spans with the original PE."""
from pathlib import Path
import hashlib
import json
import struct

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'work/trainer/research'
EXE = Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
EXPECTED = '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
blob = EXE.read_bytes()
sha = hashlib.sha256(blob).hexdigest()
assert sha == EXPECTED, 'Original EXE build mismatch'
pe = struct.unpack_from('<I',blob,0x3c)[0]
assert blob[pe:pe+4] == b'PE\0\0'
sections_n = struct.unpack_from('<H',blob,pe+6)[0]
opt_size = struct.unpack_from('<H',blob,pe+20)[0]
opt = pe+24
assert struct.unpack_from('<H',blob,opt)[0] == 0x20b
base = struct.unpack_from('<Q',blob,opt+24)[0]
sections = []
for i in range(sections_n):
    p = opt+opt_size+40*i
    name = blob[p:p+8].split(b'\0',1)[0].decode('ascii')
    vsize,rva,rawsize,rawptr = struct.unpack_from('<4I',blob,p+8)
    sections.append((name,rva,vsize,rawptr,rawsize))

def original(addr,size):
    rva = int(addr,16)-base
    for name,start,vsize,rawptr,rawsize in sections:
        if start <= rva and rva+size <= start+rawsize:
            pos = rawptr+rva-start
            return blob[pos:pos+size],name,pos
    raise ValueError(f'No complete file-backed span: {addr}/{size}')

spans = json.loads((OUT/'renderer_round5_idb_bytes.json').read_text(encoding='utf-8'))['functions']
results = []
for row in spans:
    captured = bytes(int(x,16) for x in row['data'].split())
    assert len(captured) == row['size']
    source,section,pos = original(row['addr'],len(captured))
    assert source == captured, f'IDA bytes differ at {row["addr"]}'
    results.append({'addr':row['addr'],'size':len(source),'file_offset':hex(pos),'section':section,
                    'sha256':hashlib.sha256(source).hexdigest(),'identical':True})
vtable_results = []
for row in json.loads((OUT/'renderer_round5_data.json').read_text(encoding='utf-8'))['bytes']['result']:
    captured=bytes(int(x,16) for x in row['data'].split())
    source,section,pos=original(row['addr'],len(captured))
    assert captured==source
    vtable_results.append({'addr':row['addr'],'size':len(source),'file_offset':hex(pos),
                           'sha256':hashlib.sha256(source).hexdigest(),'identical':True})
constants=[]
for row in json.loads((OUT/'renderer_round5_constants.json').read_text(encoding='utf-8'))['bytes']:
    captured=bytes(int(x,16) for x in row['data'].split())
    source,section,pos=original(row['addr'],len(captured))
    assert source==captured and len(source)==4
    constants.append({'addr':row['addr'],'float32':struct.unpack('<f',source)[0],
                      'file_offset':hex(pos),'hex':source.hex(),'identical':True})
report={'source':str(EXE),'source_sha256':sha,'image_base':hex(base),
        'function_spans':len(results),'function_bytes':sum(x['size'] for x in results),
        'all_function_bytes_identical':True,'functions':results,'vtable_spans':vtable_results,'constants':constants,
        'limits':'Full contiguous IDA function ranges and selected vtable spans match original file bytes. This verifies provenance, not runtime behavior or all semantic conclusions.'}
(OUT/'renderer_round5_verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ('source_sha256','function_spans','function_bytes','all_function_bytes_identical')},indent=2))
