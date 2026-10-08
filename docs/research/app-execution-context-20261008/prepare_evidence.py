"""Add original PE byte and import provenance to a fresh, read-only IDA export."""
from pathlib import Path
import hashlib, importlib.util, json, struct, sys
sys.dont_write_bytecode = True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('retail_verify',HERE.parent/'actor-scale-contract-20261007/verify.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
raw=base.DEFAULT_EXE.read_bytes(); at=base.original_reader(raw,0x140000000)
ev=json.loads((HERE/'evidence.json').read_text())
for data in json.loads((HERE/'additional-data.json').read_text()):
    ev['data']=[x for x in ev['data'] if x['addr']!=data['addr']]+[data]
chunked={x['owner']:x['chunks'] for x in json.loads((HERE/'chunk-capture.json').read_text())}
if 'chunkedFunctions' not in ev:
    ev['chunkedFunctions']=[f for f in ev['functions'] if f['addr'] in chunked]
    ev['functions']=[f for f in ev['functions'] if f['addr'] not in chunked]
for f in ev['chunkedFunctions']:
    f['chunks']=chunked[f['addr']]
    f['scope']='Complete paginated IDA function items with discontiguous/shared EH chunks. Separate from contiguous coverage bodies; lookup size is only the primary extent.'
assert hashlib.sha256(raw).hexdigest()==ev['originalSha256']
for row in ev['functions']+ev['data']+[x for f in ev['chunkedFunctions'] for x in f['chunks']]:
    original=at(int(row['addr'],16),row['size'])
    row['originalBytes']=original.hex(' ')
    row['idaMatchesOriginal']=base.octets(row['idaBytes'])==original
    assert row['idaMatchesOriginal'],row['addr']
pe=struct.unpack_from('<I',raw,0x3c)[0];opt=pe+24
def string(addr):
    result=bytearray()
    while len(result)<1024:
        b=at(addr+len(result),1)[0]
        if not b:return result.decode('ascii')
        result.append(b)
    raise ValueError('unterminated string')
imports={};desc=0x140000000+struct.unpack_from('<I',raw,opt+120)[0]
while True:
    oft,stamp,forward,name,ft=struct.unpack('<5I',at(desc,20))
    if not any((oft,stamp,forward,name,ft)):break
    dll=string(0x140000000+name);n=0
    while True:
        thunk=struct.unpack('<Q',at(0x140000000+(oft or ft)+8*n,8))[0]
        if not thunk:break
        if not thunk&(1<<63): imports[0x140000000+ft+8*n]={'addr':hex(0x140000000+ft+8*n),'dll':dll,'name':string(0x140000000+thunk+2),'originalThunk':hex(thunk)}
        n+=1
    desc+=20
used={int(r['addr'],16) for f in ev['functions']+ev['chunkedFunctions'] for i in f['asm']['lines'] for r in i.get('refs',[])}
ev['imports']=[imports[a] for a in sorted(used & imports.keys())]
(HERE/'evidence.json').write_text(json.dumps(ev,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'functions':len(ev['functions']),'instructions':sum(f['instruction_count'] for f in ev['functions']),'dataSpans':len(ev['data']),'imports':len(ev['imports'])}))
