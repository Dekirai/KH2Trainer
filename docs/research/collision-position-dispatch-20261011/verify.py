"""Reproduce original-PE/IDA evidence and bounded, synthetic dispatch cases."""
import argparse, hashlib, importlib.util, json, struct, sys
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
sys.dont_write_bytecode = True
H = Path(__file__).resolve().parent
R = next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir())
B = 0x140000000
ORIGINAL = Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
ORIGINAL_SHA = '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
load = lambda p: json.loads(p.read_bytes())
sha = lambda b: hashlib.sha256(b).hexdigest()
encoded = lambda x: (json.dumps(x, indent=2, ensure_ascii=False)+'\n').encode()
checks = 0

def need(x, reason):
    global checks
    checks += 1
    if not x: raise AssertionError(reason)

class PE:
    def __init__(self):
        self.data = ORIGINAL.read_bytes()
        need(sha(self.data) == ORIGINAL_SHA, 'Pinned original executable')
        p = struct.unpack_from('<I', self.data, 60)[0]
        o = p+24
        s = o+struct.unpack_from('<H', self.data, p+20)[0]
        need(self.data[p:p+4] == b'PE\0\0' and struct.unpack_from('<Q', self.data, o+24)[0] == B, 'PE/imagebase')
        self.sections = [struct.unpack_from('<III', self.data, s+40*i+12) for i in range(struct.unpack_from('<H', self.data, p+6)[0])]
    def raw(self, a, n):
        r = a-B
        offsets = [ptr+r-va for va, size, ptr in self.sections if va <= r and r+n <= va+size]
        need(n > 0 and len(offsets) == 1, 'Bounded file-backed original read')
        return self.data[offsets[0]:offsets[0]+n]
    def u64(self, a): return int.from_bytes(self.raw(a, 8), 'little')

def derive():
    pe = PE(); sizes = {}; raw = {}; rows = []; dependencies = []
    for dep in load(H/'research-plan.json')['dependencies']:
        b=(R/dep['path']).read_bytes()
        need(len(b)==dep['length'] and sha(b)==dep['sha256'],'Pinned frozen dependency '+dep['path'])
    provenance=load(H/'provenance.json')
    base=(R/provenance['interpreterBase']['path']).read_bytes()
    need(sha(base)==provenance['interpreterBase']['sha256'],'Pinned prior interpreter')
    expected=base.decode('utf-8-sig').replace('jle=z or s!=o,jns=not s,','jle=z or s!=o,js=s,jns=not s,')
    need((H/'machine.py').read_text(encoding='utf-8-sig').replace('\r\n','\n')==expected.replace('\r\n','\n'),'Interpreter delta is JS/CMOVS support only')
    need(sha((R/'scripts/update-analysis-coverage.py').read_bytes())==provenance['coverageParserSha256'],'Coverage parser pin')
    for p in sorted(H.glob('root-lookup*.json')):
        for row in load(p)['result']:
            f = row['fn']; need(f is not None, 'IDA function lookup')
            a = int(f['addr'], 16); n = int(f['size'], 16)
            if a in sizes: need(sizes[a] == n, 'Consistent IDA extent')
            sizes[a] = n
    for p in sorted(H.glob('root-xrefs*.json')):
        for row in load(p)['result']:
            need(not row.get('more', False),'Untruncated selected xrefs')
            for ref in row['xrefs']:
                f=ref.get('fn')
                if not f:continue
                a=int(f['addr'],16);n=int(f['size'],16)
                if a in sizes:need(sizes[a]==n,'Consistent xref function extent')
                sizes[a]=n
    for p in sorted(H.glob('root-bytes*.json')):
        for row in load(p)['result']:
            a = int(row['addr'], 16); d = bytes(int(v, 16) for v in row['data'].split())
            if a in raw: need(raw[a] == d, 'Consistent IDA bytes')
            raw[a] = d
            need(d == pe.raw(a, len(d)), 'IDA bytes equal original '+hex(a))
    for p in sorted(H.glob('root-disasm-*.json')):
        asm = load(p); a = int(asm['addr'], 16); dec = load(H/('root-decompile-'+hex(a)+'.json'))
        need(asm['cursor'].get('done') and asm['instruction_count'] == asm['total_instructions'] == len(asm['asm']['lines']), 'Complete fresh ASM page')
        need(dec['cursor'].get('done') and not dec['truncated'] and dec['line_count'] == dec['total_lines'] == len(dec['code'].splitlines()), 'Complete fresh pseudocode')
        need(len(raw[a]) == sizes[a], 'Full IDA byte extent')
        rows.append(dict(addr=hex(a), name=asm['asm']['name'], size=sizes[a], originalBytes=raw[a].hex(' '), pages=[asm], disassembly=asm, pseudocode=dec,
                         sourceMetadata=dict(freshCapture=True, toolOperator='/root', disasmFile=p.name, session='28e14b48')))
    source = R/'docs/research/collision-placement-writer-20261011/evidence.json'
    prior = load(source)
    dependencies.append(dict(path=source.relative_to(R).as_posix(), sha256=sha(source.read_bytes()), manifestSha256=sha((source.parent/'manifest.json').read_bytes())))
    for a in [0x3d1960, 0x3d0bb0, 0x13fcc0, 0x1a8e60]:
        f = next(f for f in prior['functions'] if int(f['addr'], 16) == B+a)
        row = {k: f[k] for k in ['addr', 'name', 'size', 'originalBytes', 'pages', 'disassembly', 'pseudocode']}
        row['sourceMetadata'] = dict(freshCapture=False, path=dependencies[-1]['path'], sha256=dependencies[-1]['sha256'])
        rows.append(row)
    need(len({f['addr'] for f in rows}) == len(rows), 'Unique functions')
    cs = Cs(CS_ARCH_X86, CS_MODE_64); cs.detail = True
    aliases = dict(retn='ret', sal='shl', jz='je', jnz='jne', jnb='jae', jnae='jb', setz='sete', setnz='setne', movabs='mov', cmovnz='cmovne', cmovz='cmove')
    ins = {}
    for f in rows:
        a = int(f['addr'], 16); d = bytes.fromhex(f['originalBytes'])
        need(len(d) == f['size'] and d == pe.raw(a, len(d)), 'Full original body '+f['addr'])
        lines = []
        for page in f['pages']:
            need(page.get('offset', len(lines)) == len(lines), 'ASM page continuity')
            lines.extend(page['asm']['lines'])
            need(page['cursor'].get('done') or page['cursor'].get('next') == len(lines), 'ASM cursor progress')
        need(f['pages'][-1]['cursor'].get('done') and lines == f['disassembly']['asm']['lines'] and len(lines) == f['disassembly']['total_instructions'], 'Complete ASM join')
        covered = set(); decoded = []
        for row in lines:
            pc = int(row['addr'], 16)
            i = next(cs.disasm(d[pc-a:], pc, count=1))
            span = set(range(pc, pc+i.size))
            need(a <= pc and pc+i.size <= a+len(d) and not span & covered, 'Bounded nonoverlapping instruction')
            covered |= span
            op = row['instruction'].split(';')[0].split()[0].lower()
            need(aliases.get(op, op) == aliases.get(i.mnemonic, i.mnemonic) or op == 'xchg' and i.mnemonic == 'nop', 'Original mnemonic '+hex(pc))
            ins[pc] = i
            decoded.append(dict(addr=hex(pc), bytes=i.bytes.hex(' '), size=i.size, mnemonic=i.mnemonic, operands=i.op_str))
        need(len(covered) == len(d), 'Entire body instruction coverage '+f['addr'])
        f.update(sha256=sha(d), instructions=decoded, complete=True)
    data = []
    def datum(a, n, purpose):
        d = pe.raw(a, n); row = dict(addr=hex(a), size=n, originalBytes=d.hex(' '), sha256=sha(d), purpose=purpose)
        data.append(row); return d
    descriptors = []
    for descriptor, expected_vt, expected_target in [(0x74af78,0x5c4f10,0x1afe10),(0x750300,0x5cba28,0x404eb0),(0x7523b8,0x5d15a0,0x4153e0)]:
        vt = int.from_bytes(datum(B+descriptor,8,'Selected native descriptor vptr'), 'little')
        target = int.from_bytes(datum(vt+216,8,'Virtual slot+216'), 'little')
        need(vt == B+expected_vt and target == B+expected_target, 'Selected descriptor/slot chain')
        col = int.from_bytes(datum(vt-8,8,'MSVC RTTI locator pointer'), 'little')
        rtti = datum(col,24,'MSVC complete object locator')
        sig, offset, cd, td, ch, self_rva = struct.unpack('<6I',rtti)
        need(sig == 1 and self_rva+B == col and offset == 0, 'RTTI locator self/signature/offset')
        name_data = pe.raw(B+td+16,128); end = name_data.index(0)
        name = datum(B+td+16,end+1,'RTTI decorated class name')[:-1].decode('ascii')
        descriptors.append(dict(descriptor=hex(B+descriptor),vtable=hex(vt),slot=hex(vt+216),target=hex(target),rttiName=name))
    vt = B+0x5ce6c0
    need(int.from_bytes(datum(vt+24,8,'ATTACK_OBJ virtual slot+24'),'little') == B+0x40f610,'Attack update slot')
    col = int.from_bytes(datum(vt-8,8,'ATTACK_OBJ RTTI locator pointer'),'little')
    rtti = datum(col,24,'ATTACK_OBJ complete object locator'); sig, offset, cd, td, ch, self_rva = struct.unpack('<6I',rtti)
    need(sig == 1 and offset == 0 and self_rva+B == col,'ATTACK_OBJ RTTI locator')
    name = pe.raw(B+td+16,128).split(b'\0')[0]
    need(name == b'.?AVATTACK_OBJ@YS@@','Concrete attack-object RTTI name')
    datum(B+td+16,len(name)+1,'ATTACK_OBJ type name')
    i=ins[B+0x3d6401];constant=i.address+i.size+i.operands[1].mem.disp
    need(constant==B+0x623c48 and datum(constant,4,'Fixed fifth argument of3D63E0')==bytes.fromhex('00 00 80 bf'),'Fixed callback scalar minus1')
    return pe, dict(schema=1, Domain='native', originalSha256=ORIGINAL_SHA, imageBase=hex(B), functions=rows, originalPeData=data, selectedDescriptors=descriptors, dependencies=dependencies), ins

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--write', action='store_true'); ap.add_argument('--check',action='store_true'); args=ap.parse_args()
    pe,evidence,ins=derive()
    import model
    models=model.run(ins,pe.raw,need)
    if args.write:
        (H/'evidence.json').write_bytes(encoded(evidence))
        (H/'model-results.json').write_bytes(encoded(models))
    result=dict(status='PASS',originalSha256=ORIGINAL_SHA,freshBodies=sum(f['sourceMetadata']['freshCapture'] for f in evidence['functions']),reusedBodies=sum(not f['sourceMetadata']['freshCapture'] for f in evidence['functions']),originalBodyBytes=sum(f['size'] for f in evidence['functions']),instructions=len(ins),originalDataRows=len(evidence['originalPeData']),modelSummary=models['summary'])
    if (H/'report.json').is_file():
        spec=importlib.util.spec_from_file_location('coverage',R/'scripts/update-analysis-coverage.py'); parser=importlib.util.module_from_spec(spec); spec.loader.exec_module(parser)
        claims=load(H/'report.json')['claims']
        for c in claims:
            need(c['addr'] in {f['addr'] for f in evidence['functions']} and c['Finding'] and c['Limitations'],'Bounded canonical claim')
            for ref in c['Evidence']: need(parser.resolve_reference(H/'report.json',ref)['status']=='exists','Resolvable reference '+ref)
        for f in evidence['functions']:
            ok,asm,why=parser.body_assembly(f); need(ok and len(asm)==len(f['instructions']),'Coverage full ASM '+why)
            need(parser.has_raw_code(f,int(f['addr'],16),f['size']),'Coverage raw span')
        result['claims']=len(claims)
    result['checks']=checks
    for name,value in [('evidence.json',evidence),('model-results.json',models),('verification.json',result)]:
        d=encoded(value)
        if args.write:(H/name).write_bytes(d)
        else:need((H/name).read_bytes()==d,'Exact reproduction '+name)
    if args.check:
        m=load(H/'manifest.json'); actual={p.relative_to(H).as_posix() for p in H.rglob('*') if p.is_file() and p != H/'manifest.json'}
        need(actual=={f['path'] for f in m['files']},'Exact recursive study file set')
        for f in m['files']:
            b=(H/f['path']).read_bytes();need(len(b)==f['length'] and sha(b)==f['sha256'],'Manifest pin '+f['path'])
    print(json.dumps(result))

if __name__=='__main__':main()
