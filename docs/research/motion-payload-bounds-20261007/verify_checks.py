"""Independent evidence-integrity regressions and concrete ABI/constant assertions; no game execution."""
import copy
import importlib.util
import json
from pathlib import Path
import struct
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('motion_verifier', HERE/'verify.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
e = json.loads((HERE/'evidence.json').read_text(encoding='utf-8'))
f = {int(x['addr'],16):x for x in e['functions']}
d = {int(x['addr'],16):v.octets(x['originalBytes']) for x in e['data']}
checks = 0
def check(ok, message):
    global checks
    checks += 1
    if not ok: raise AssertionError(message)
def instructions(addr): return [x['instruction'] for x in f[addr]['asm']['lines']]
check('lea rdx, [rcx+90h]' in instructions(0x1401C5F20), 'payload begins at type9+144')
raw = instructions(0x1401DB470)
check('cvttss2si edx, xmm2' in raw and 'xorps xmm2, xmm2' in raw and 'movaps xmm3, xmm2' in raw, 'RAW conversion/clamp/fourth float ABI')
check('subss xmm2, xmm1' in raw, 'RAW fraction is scaled minus clamped first')
normal = instructions(0x140142080)
check('movaps xmm0, xmm2' in normal and 'movss dword ptr [rbx+8], xmm8' in normal and not any('[rbx+0Ch]' in x for x in normal), 'normalize returns XYZ length and preserves W')
channels = instructions(0x1401DAD10)
check(any('[r14+3Ch]' in x for x in channels) and any('[r14+38h]' in x for x in channels) and any(x.split(';')[0].strip()=='add rbx, 6' for x in channels), 'second declared curve-table count/offset/stride')
check(struct.unpack_from('<Q',d[0x1405B4958],40)[0]==0x1401DA6A0,'Prototype root vslot')
check(struct.unpack_from('<Q',d[0x1405B4A38],40)[0]==0x1401DB470,'RAW root vslot')
for addr,value in [(0x140623B18,2),(0x140623BD4,60),(0x140623A80,1),(0x1405A9CB8,3)]:
    check(struct.unpack('<f',d[addr])[0]==value,hex(addr)+' constant')
for body in e['functions']:
    v.validate_body(body); check(True,body['addr']+' complete')
for mutation in ['cancelled','notdone','total','duplicate','outofbody','missinginstruction','bytecount']:
    b=copy.deepcopy(e['functions'][0])
    if mutation=='cancelled': b['pages'][0]['cursor']['cancelled']=True
    elif mutation=='notdone': b['cursor']['done']=False
    elif mutation=='total': b['total_instructions']+=1
    elif mutation=='duplicate':
        b['pages'][0]['asm']['lines'][1]['addr']=b['pages'][0]['asm']['lines'][0]['addr'];b['asm']['lines']=copy.deepcopy(b['pages'][0]['asm']['lines'])
    elif mutation=='outofbody':
        b['pages'][0]['asm']['lines'][-1]['addr']='0x180000000';b['asm']['lines']=copy.deepcopy(b['pages'][0]['asm']['lines'])
    elif mutation=='missinginstruction':
        b['pages'][0]['asm']['lines'][0]['instruction']='';b['asm']['lines']=copy.deepcopy(b['pages'][0]['asm']['lines'])
    elif mutation=='bytecount': b['originalBytes']='00'
    try: v.validate_body(b)
    except (ValueError,KeyError,TypeError): check(True,mutation+' rejected')
    else: check(False,mutation+' not rejected')
report={'checks':checks,'failures':0,'scope':'Saved evidence validation and concrete ABI/data assertions only.'}
(HERE/'verify-checks.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report))
