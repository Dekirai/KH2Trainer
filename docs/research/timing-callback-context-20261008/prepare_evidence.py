"""Enrich read-only IDA captures with bytes from the SHA-pinned retail PE."""
from pathlib import Path
import hashlib, importlib.util, json, struct, sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('retail',HERE.parent/'actor-scale-contract-20261007/verify.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
def dump(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
def octets(b):return ' '.join('0x%02x'%x for x in b)
raw=base.DEFAULT_EXE.read_bytes();at=base.original_reader(raw,0x140000000)
ev=json.loads((HERE/'capture.json').read_text())
extra=json.loads((HERE/'dispatch-capture.json').read_text());ev['functions'].extend(extra['functions'])
already={d['addr'] for d in ev['data']};ev['data'].extend(d for d in extra['data'] if d['addr'] not in already)
assert hashlib.sha256(raw).hexdigest()==ev['originalSha256']
ev['xrefs']=[f.pop('xrefs') for f in ev['functions']]
for f in ev['functions']:
    f['originalBytes']=octets(at(int(f['addr'],16),f['size']))
    f['provenance']='Fresh read-only IDA session 83662637 capture.'
for d in ev['data']:d['originalBytes']=octets(at(int(d['addr'],16),d['size']))
t=ev['sharedTail'];t['originalBytes']=octets(at(int(t['addr'],16),t['size']))
borrow=HERE.parent/'app-execution-context-20261008/evidence.json'
assert hashlib.sha256(borrow.read_bytes()).hexdigest()=='71136a6c1d400910f88384062b900ebd8a7bfac8a8a89bab7e4633d5497cda8c'
src=json.loads(borrow.read_text());wanted={int(x,16) for x in ['11d0a0','127ed0','121d90','129110','1287d0','14ed40','11ad80','127eb0','125a10']}
reused=[]
for f in src['functions']:
    if int(f['addr'],16)-0x140000000 in wanted:
        f['provenance']='Reused unchanged body from ../app-execution-context-20261008/evidence.json; source SHA256 recorded in dependencies.'
        ev['functions'].append(f);reused.append(f['addr'])
assert len(reused)==len(wanted)
ev['dependencies']=[{'path':'../app-execution-context-20261008/evidence.json','sha256':hashlib.sha256(borrow.read_bytes()).hexdigest(),'reusedFunctions':reused}, {'path':'../actor-scale-contract-20261007/verify.py','sha256':hashlib.sha256((HERE.parent/'actor-scale-contract-20261007/verify.py').read_bytes()).hexdigest()}]
task=HERE.parent/'actor-task-context-20261008/evidence.json'
ev['dependencies'].append({'path':'../actor-task-context-20261008/evidence.json','sha256':hashlib.sha256(task.read_bytes()).hexdigest(),'use':'Previously verified task registration/dispatch connection; no body duplication here.'})
pe=struct.unpack_from('<I',raw,0x3c)[0];opt=pe+24;table=opt+struct.unpack_from('<H',raw,pe+20)[0]
sections=[struct.unpack_from('<4I',raw,table+40*i+8) for i in range(struct.unpack_from('<H',raw,pe+6)[0])]
def virtual(addr,size):
    rva=addr-0x140000000
    for vs,va,rs,off in sections:
        if va<=rva and rva-va+size<=max(vs,rs):
            n=min(size,max(0,rs-(rva-va)));return raw[off+rva-va:off+rva-va+n]+bytes(size-n),n
    raise ValueError(hex(addr))
ev['initialState']=json.loads((HERE/'state-capture.json').read_text())
for d in ev['initialState']:
    b,n=virtual(int(d['addr'],16),d['size']);d['originalImageBytes']=octets(b);d['fileBackedBytes']=n
def string(addr):
    b=bytearray()
    while True:
        c=at(addr+len(b),1)[0]
        if not c:return b.decode('ascii')
        b.append(c)
imports=[];desc=0x140000000+struct.unpack_from('<I',raw,opt+120)[0]
while True:
    oft,stamp,forward,name,ft=struct.unpack('<5I',at(desc,20))
    if not any((oft,stamp,forward,name,ft)):break
    dll=string(0x140000000+name);n=0
    while True:
        t=struct.unpack('<Q',at(0x140000000+(oft or ft)+8*n,8))[0]
        if not t:break
        if not t&(1<<63):imports.append({'addr':hex(0x140000000+ft+8*n),'dll':dll,'name':string(0x140000000+t+2),'originalThunk':hex(t)})
        n+=1
    desc+=20
names={'CreateSemaphoreA','ReleaseSemaphore','WaitForSingleObject','CloseHandle','_beginthreadex','ResumeThread','SetThreadPriority','GetExitCodeThread','Sleep','DestroyWindow'}
ev['imports']=[i for i in imports if i['name'] in names]
dump(HERE/'evidence.json',ev)
with (HERE/'native-listings.txt').open('w',encoding='utf-8') as out:
    for f in ev['functions']:
        out.write('\n'+f['addr']+' '+f['name']+' '+f['provenance']+'\n')
        out.write(f['pseudocode']['code']+'\n\n')
        for row in f['asm']['lines']:out.write(row['addr']+' '+row['instruction']+'\n')
    out.write('\nShared out-of-line tail, owner 15EDB0. Complete IDA request at tail entry follows:\n')
    for row in ev['sharedTail']['asm']['asm']['lines']:out.write(row['addr']+' '+row['instruction']+'\n')
print(json.dumps({'functions':len(ev['functions']),'fresh':32,'reused':len(reused),'dataSpans':len(ev['data'])}))
