"""Verify saved IDA bodies and optionally run three original leaves in private memory.

No process is opened. The optional probe executes only the three named, hash-checked
functions with bounded synthetic buffers in this Python process. It is not gameplay.
"""
import argparse, copy, ctypes, hashlib, json, math, struct
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

H = Path(__file__).resolve().parent
EXE = Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
EXPECTED = '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
load = lambda n: json.loads((H/n).read_text(encoding='utf-8-sig'))
sha = lambda b: hashlib.sha256(b).hexdigest()
checks = 0
def need(value, label):
    global checks
    checks += 1
    if not value: raise AssertionError(label)
def dump(n, o): (H/n).write_text(json.dumps(o, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
def f32(x): return struct.unpack('<f', struct.pack('<f', x))[0]
def bits(values): return struct.pack('<'+'f'*len(values), *values).hex()

def original_image():
    blob = EXE.read_bytes()
    need(sha(blob) == EXPECTED, 'original PE hash')
    pe = struct.unpack_from('<I', blob, 60)[0]
    count, opt = struct.unpack_from('<H', blob, pe+6)[0], struct.unpack_from('<H', blob, pe+20)[0]
    base = struct.unpack_from('<Q', blob, pe+48)[0]
    sections = [struct.unpack_from('<8sIIII', blob, pe+24+opt+40*i) for i in range(count)]
    def get(addr, size):
        rva = addr-base
        for _, vs, start, raw, off in sections:
            if start <= rva and rva+size <= start+raw:
                return blob[off+rva-start:off+rva-start+size]
        raise AssertionError(('PE range', hex(addr), size))
    return base, get

def verify_capture():
    base, original = original_image()
    capture = load('capture.json')
    cs = Cs(CS_ARCH_X86, CS_MODE_64); cs.detail = True
    functions, decoded = [], {}
    for saved in capture['functions']:
        f = copy.deepcopy(saved); a = int(f['addr'], 16)
        data = bytes(int(v,16) for v in f['idaBytes'].split())
        need(data == original(a, f['size']) and len(data) == f['size'], ('PE body', f['addr']))
        rows = [r for page in f['pages'] for r in page['asm']['lines']]
        need(len(f['pages']) == 1 and f['pages'][0]['cursor'].get('done') and
             f['pages'][0]['instruction_count'] == f['pages'][0]['total_instructions'] == len(rows), 'complete ASM page')
        ins = list(cs.disasm(data, a))
        need(sum(x.size for x in ins) == len(data) and [x.address for x in ins] == [int(r['addr'],16) for r in rows], 'contiguous instruction boundaries')
        dec = f['decompilePages']
        need(len(dec) == 1 and dec[0]['cursor'].get('done') and dec[0]['line_count'] == dec[0]['total_lines'] and dec[0]['code'] == f['pseudocode'], 'complete decompiler page')
        f['disassembly'] = f['pages'][0]
        f['originalBytes'] = data.hex(' '); f['sha256'] = sha(data)
        functions.append(f); decoded[a] = ins
    need(len({f['addr'] for f in functions}) == len(functions) == 13, 'unique captured functions')
    body = decoded[base+0x40AC20]
    need([i.address-base for i in body if i.mnemonic == 'minss'] == [0x40ACF0,0x40AD01,0x40AD14,0x40AD27,0x40AD39,0x40AD50], 'six exact MINSS sites')
    need(not any(i.mnemonic == 'maxss' for i in body), 'no MAXSS in this complete body')
    index = {i.address-base:i for values in decoded.values() for i in values}
    call_anchors = {
        0x40A9F9:0x3C9B30, 0x40AA1D:0x152430, 0x3B63EA:0x40A9E0,
        0x3B6406:0x40A9E0, 0x3CC0CD:0x40AC20, 0x55BB42:0x40AC20,
        0x562CC5:0x40AC20, 0x3CCFE9:0x1A94C0, 0x3CD0E3:0x40B140,
        0x3CD1B5:0x1A94C0, 0x3BFAD0:0x3CCB90, 0x3BFAE3:0x3C6AA0,
        0x3BFB0F:0x40B140, 0x40B199:0x3C9C00, 0x3C9CCA:0x3B50F0,
    }
    for site,target in call_anchors.items():
        i=index[site]
        need(i.mnemonic=='call' and i.operands[0].type==X86_OP_IMM and i.operands[0].imm==base+target,('call anchor',hex(site)))
    text_anchors = {
        0x3B63E1:('mov','r8d, 1'), 0x3B63F6:('mov','r8d, 2'),
        0x3B63FF:('mov','qword ptr [rbx + 0xa00], rax'),
        0x3B640B:('mov','qword ptr [rbx + 0x640], rax'),
        0x3CC0C6:('lea','rdx, [rbx + 0x898]'),
        0x3CCFE5:('lea','rcx, [rdi + 0x40]'),
        0x3CD0D7:('mov','rcx, qword ptr [rdi + 0xa00]'),
        0x3CD18F:('lea','rcx, [rdi + 0x808]'),
        0x3BFB03:('mov','rcx, qword ptr [rbx + 0x640]'),
        0x40B146:('mov','dword ptr [rcx], 0'),
        0x40B153:('mov','eax, dword ptr [rcx + 0x9b8]'),
        0x40B159:('shr','eax, 0xa'),
    }
    for site,expected in text_anchors.items():
        need((index[site].mnemonic,index[site].op_str)==expected,('decoded operand anchor',hex(site)))
    probe_addrs = {base+x for x in (0x40AC20,0x184270,0x184940)}
    for a in probe_addrs:
        need(not any(op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP for i in decoded[a] for op in i.operands), ('probe no RIP-relative data', hex(a)))
        for i in decoded[a]:
            if i.mnemonic in ('call', 'jmp'):
                need(i.operands[0].type == X86_OP_IMM and
                     (i.operands[0].imm in probe_addrs or a <= i.operands[0].imm < a+sum(x.size for x in decoded[a])), 'probe transfer target')
    evidence = {'schema':1,'Domain':'native','originalSha256':EXPECTED,'imageBase':hex(base),'functions':functions}
    return evidence, decoded

CASES = [
    ('empty', []),
    ('single', [(1,2,3,4,5)]),
    ('negative_center', [(2,3,-7,-9,-11)]),
    ('two_x_separated', [(1,1,0,0,0),(1,1,100,0,0)]),
    ('two_x_reversed', [(1,1,100,0,0),(1,1,0,0,0)]),
    ('two_y_separated', [(1,2,0,-20,0),(1,3,0,20,0)]),
    ('two_z_separated', [(1,1,0,0,0),(3,2,0,0,50)]),
    ('nested', [(10,10,0,0,0),(1,1,0,0,0)]),
    ('identical', [(2,3,4,5,6),(2,3,4,5,6)]),
    ('three_axes', [(2,3,-10,2,3),(4,5,6,-20,8),(6,7,9,10,30)]),
    ('zero_radius', [(0,0,2,3,4),(0,0,4,5,6)]),
    ('fractional', [(0.25,0.5,1.25,-2.5,4.75),(1.5,2.25,-3.25,5.5,2.5)]),
]
def bounds(rows):
    boxes = [[f32(x-r),f32(y-h),f32(z-r),f32(x+r),f32(y+h),f32(z+r)] for r,h,x,y,z in rows]
    if not boxes: return [0.0]*6, [0.0]*6
    native = [min(b[i] for b in boxes) for i in range(6)]
    union = [min(b[i] for b in boxes) if i<3 else max(b[i] for b in boxes) for i in range(6)]
    return native, union

def run_native(evidence):
    need(ctypes.sizeof(ctypes.c_void_p) == 8, '64-bit host')
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.VirtualAlloc.argtypes = [ctypes.c_void_p,ctypes.c_size_t,ctypes.c_ulong,ctypes.c_ulong]; k.VirtualAlloc.restype = ctypes.c_void_p
    k.VirtualProtect.argtypes = [ctypes.c_void_p,ctypes.c_size_t,ctypes.c_ulong,ctypes.POINTER(ctypes.c_ulong)]; k.VirtualProtect.restype = ctypes.c_int
    k.VirtualFree.argtypes = [ctypes.c_void_p,ctypes.c_size_t,ctypes.c_ulong]; k.VirtualFree.restype = ctypes.c_int
    k.GetCurrentProcess.restype = ctypes.c_void_p
    k.FlushInstructionCache.argtypes = [ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t]; k.FlushInstructionCache.restype = ctypes.c_int
    allocations = []
    def alloc(size, prot):
        p = k.VirtualAlloc(None,size,0x3000,prot)
        need(bool(p),'private allocation'); allocations.append(p); return p
    def protect(p,n,prot):
        old=ctypes.c_ulong(); need(bool(k.VirtualProtect(p,n,prot,ctypes.byref(old))),'private page protection')
    def guard_buffer(n):
        p=alloc(0x3000,1); protect(p+0x1000,0x1000,4)
        need(0<n<0xF00,'bounded synthetic buffer')
        a=p+0x2000-n; ctypes.memset(a-32,0xA5,n+32); return a
    results=[]
    try:
        image=alloc(0x40C000,4)
        chosen=[]
        for f in evidence['functions']:
            rva=int(f['addr'],16)-0x140000000
            if rva in (0x40AC20,0x184270,0x184940):
                b=bytes.fromhex(f['originalBytes']); ctypes.memmove(image+rva,b,len(b)); chosen.append(rva)
        protect(image,0x40C000,1)
        for page in sorted({rva&~0xFFF for rva in chosen}): protect(image+page,0x1000,0x20)
        need(bool(k.FlushInstructionCache(k.GetCurrentProcess(),image,0x40C000)), 'private code cache flush')
        fn=ctypes.WINFUNCTYPE(None,ctypes.c_void_p,ctypes.c_void_p)(image+0x40AC20)
        for name,rows in CASES:
            raw=bytearray(24+40*len(rows)); struct.pack_into('<i',raw,0,len(rows))
            for idx,(radius,height,x,y,z) in enumerate(rows):
                at=24+40*idx
                struct.pack_into('<ff',raw,at+4,radius,height)
                struct.pack_into('<ffff',raw,at+24,x,y,z,1)
            src=guard_buffer(len(raw)); dst=guard_buffer(24); ctypes.memmove(src,bytes(raw),len(raw))
            before=ctypes.string_at(src-32,len(raw)+32)
            fn(src,dst)
            got=ctypes.string_at(dst,24); expect,union=bounds(rows)
            need(got.hex()==bits(expect),('original native result',name))
            need(ctypes.string_at(src-32,len(raw)+32)==before and ctypes.string_at(dst-32,32)==b'\xA5'*32,('buffer canaries',name))
            results.append({'case':name,'records':rows,'actualBits':got.hex(),'nativeMinimumBits':bits(expect),
                            'enclosingUnionBits':bits(union),'matchesEnclosingUnion':got.hex()==bits(union),
                            'actual':list(struct.unpack('<6f',got)),'enclosingUnion':union})
    finally:
        for p in reversed(allocations): need(bool(k.VirtualFree(p,0,0x8000)),'private allocation freed')
    return {'schema':1,'originalSha256':EXPECTED,'probeScriptSha256':sha(Path(__file__).read_bytes()),'executedOriginalFunctions':['0x14040ac20','0x140184270','0x140184940'],
            'cases':results,'caseCount':len(results),'nonEnclosingCases':sum(not r['matchesEnclosingUnion'] for r in results),
            'scope':'Original three bodies executed in this private Python process. Synthetic bounded, finite, nonnegative-dimension records; no stubs, game attach, game globals, real resources, game execution or game writes. Guard pages/canaries cover these calls only.'}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--run-native',action='store_true'); ap.add_argument('--check',action='store_true'); args=ap.parse_args()
    evidence,decoded=verify_capture()
    if args.run_native: dump('native-probe.json',run_native(evidence))
    probe=load('native-probe.json')
    need(probe['caseCount']==len(CASES)==len(probe['cases']),'native receipt cases')
    for (name,rows),r in zip(CASES,probe['cases']):
        expected,union=bounds(rows)
        need(r['case']==name and r['records']==[list(v) for v in rows] and r['actualBits']==bits(expected) and r['enclosingUnionBits']==bits(union),('reconcile native receipt',name))
    if args.check:
        need(load('evidence.json')==evidence,'normalized evidence reproducibility')
        if (H/'manifest.json').exists():
            for name,value in load('manifest.json')['files'].items(): need(sha((H/name).read_bytes())==value,('manifest',name))
    else:
        dump('evidence.json',evidence)
        dump('verification.json',{'checks':checks,'failures':0,'functions':len(evidence['functions']),
             'originalBytes':sum(f['size'] for f in evidence['functions']), 'instructions':sum(len(x) for x in decoded.values()),
             'nativeProbeCases':len(CASES),'nativeProbeRunThisInvocation':args.run_native,'originalSha256':EXPECTED,
             'limits':'Structural checks and 12 bounded native probes are separate evidence; neither proves whole-function or gameplay correctness.'})
    print(json.dumps({'checks':checks,'failures':0,'functions':len(evidence['functions']),'nativeProbeRun':args.run_native,'cases':len(CASES)}))
if __name__=='__main__': main()
