"""Verify the recorded collision-query path against the original executable.
No game, target instruction or runtime script execution. --check writes nothing.
"""
import argparse, copy, hashlib, importlib.util, json, struct
import model
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PE_SOURCE = HERE.parent/'bdx-trap-registry-20261008/verify.py'
load = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
enc = lambda d: (json.dumps(d, indent=2, ensure_ascii=False)+'\n').encode()
sha = lambda b: hashlib.sha256(b).hexdigest()
num = lambda n: int(n, 16) if isinstance(n, str) else n
blob = lambda text: bytes(int(x, 16) for x in text.split())

def need(value, message):
    if not value: raise AssertionError(message)

def derive():
    spec = importlib.util.spec_from_file_location('collision_original_pe', PE_SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pe = module.PE(module.TARGET)
    def read(addr, size):
        data, zeros = pe.read(addr, size)
        need(zeros == 0, ('file-backed bytes', hex(addr)))
        return data
    cs = Cs(CS_ARCH_X86, CS_MODE_64)
    cs.detail = True
    functions, decoded_by_addr, primary_bytes, instruction_count = [], {}, 0, 0
    for name in ['capture.json', 'helper-capture.json', 'final-helper-capture.json']:
        source = load(HERE/name)
        need(source['Domain'] == 'native' and source['originalSha256'] == module.SHA and num(source['imageBase']) == pe.base, 'capture identity')
        for original in source['functions']:
            f = copy.deepcopy(original)
            addr, size = num(f['addr']), f['size']
            raw = read(addr, size)
            need(raw == blob(f['idaBytes']), ('IDA/original bytes', hex(addr)))
            disassembly, pages = f['disassembly'], f['pages']
            lines = disassembly['asm']['lines']
            need(disassembly['cursor'].get('done') and len(lines) == disassembly['instruction_count'] == disassembly['total_instructions'], ('ASM counts', hex(addr)))
            need(lines == [line for page in pages for line in page['asm']['lines']], 'page concatenation')
            offset = 0
            for page in pages:
                need(page['instruction_count'] == len(page['asm']['lines']), 'page size')
                offset += page['instruction_count']
                need(page['cursor'].get('done') or page['cursor'].get('next') == offset, 'page cursor')
            need(pages[-1]['cursor'].get('done'), 'last page complete')
            dp = f['decompilePages']
            need(dp[-1]['cursor'].get('done') and f['decompile']['code'] == '\n'.join(p['code'] for p in dp), 'pseudocode pages')
            need(sum(p['line_count'] for p in dp) == f['decompile']['line_count'] == dp[0]['total_lines'], 'pseudocode counts')
            code_size = size
            if addr == 0x1401741C0:
                # IDA includes the aligned 16-entry switch table after RET in this
                # function's extent. Verify its exact layout instead of decoding data.
                code_size = 0x235
                targets = [0x174303, 0x174308, 0x17430D, 0x174320,
                           0x174312, 0x174318, 0x174303] + [0x17432D] * 9
                need(size == 0x278 and raw[code_size:] == b'\x0f\x1f\x00' + struct.pack('<16I', *targets), 'collector switch-table tail')
                f['embeddedData'] = dict(paddingAddr=hex(addr + code_size), paddingBytes=3,
                    tableAddr='0x1401743f8', entryBytes=4, tableBytes=64,
                    rvaTargets=[hex(t) for t in targets])
            decoded = list(cs.disasm(raw[:code_size], addr))
            need(sum(i.size for i in decoded) == code_size and [i.address for i in decoded] == [num(line['addr']) for line in lines], ('primary ASM extent', hex(addr), len(decoded), len(lines)))
            if addr == 0x1401741C0:
                by_addr = {i.address: i for i in decoded}
                expected = {0x1401742E7: ('cmp', 'ebp, 0xf'),
                            0x1401742EA: ('ja', '0x14017432d'),
                            0x1401742EC: ('lea', 'r9, [rip - 0x1742f3]'),
                            0x1401742F6: ('mov', 'ecx, dword ptr [r9 + rbp*4 + 0x1743f8]'),
                            0x1401742FE: ('add', 'rcx, r9'),
                            0x140174301: ('jmp', 'rcx'),
                            0x1401743F4: ('ret', '')}
                for at, pair in expected.items():
                    need((by_addr[at].mnemonic, by_addr[at].op_str) == pair, ('switch consumer', hex(at)))
                need(all(pe.base + t in by_addr for t in targets), 'switch target instruction starts')
            f['instructionBytes'] = code_size
            need(addr not in [num(row['addr']) for row in functions], 'duplicate function')
            f['originalBytes'] = raw.hex(' ')
            f['decodedInstructions'] = [dict(addr=hex(i.address), bytes=i.bytes.hex(), mnemonic=i.mnemonic, operands=i.op_str) for i in decoded]
            functions.append(f)
            decoded_by_addr.update({i.address: i for i in decoded})
            primary_bytes += size
            instruction_count += len(decoded)
    extra = load(HERE/'additional-capture.json')
    data, xrefs = [], []
    for row in extra['data']['result']:
        raw = blob(row['data'])
        need(raw == read(num(row['addr']), len(raw)), 'data bytes')
        data.append(dict(addr=row['addr'], originalBytes=raw.hex(' '), size=len(raw)))
    need(read(0x14071BA50, 12) == struct.pack('<iii', 1, 2, 0), 'triangle edge order')
    need(read(0x14071BA60, 16) == struct.pack('<iiii', 1, 2, 3, 0), 'quad edge order')
    need(read(0x14071B3F0, 32) == struct.pack('<8f', 1,10,20,100,1,.1,.05,.01), 'quantization margins and scales')
    for row in extra['xrefs']['result']:
        need(not row.get('more') and row['xref_count'] == len(row['xrefs']), 'xref truncation/count')
        target = num(row['addr'])
        for ref in row['xrefs']:
            if not ref.get('fn'): continue
            at = num(ref['addr'])
            ins = next(cs.disasm(read(at, 15), at, count=1))
            need(any(op.type == X86_OP_IMM and op.imm == target or op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP and ins.address + ins.size + op.mem.disp == target for op in ins.operands), ('xref encoding', hex(at)))
            xrefs.append(dict(addr=hex(at), target=hex(target), bytes=ins.bytes.hex()))
    anchors = []
    anchor_path = HERE/'semantic-anchors.json'
    if anchor_path.exists():
        for row in load(anchor_path)['anchors']:
            ins = decoded_by_addr[num(row['addr'])]
            need((ins.mnemonic, ins.op_str) == (row['mnemonic'], row['operands']), ('semantic anchor', row['addr']))
            anchors.append(dict(row, bytes=ins.bytes.hex()))
    starts = {num(f['addr']) for f in functions}
    calls = []
    for f in functions:
        for row in f['decodedInstructions']:
            ins = decoded_by_addr[num(row['addr'])]
            owner_start = num(f['addr'])
            is_call = ins.mnemonic == 'call'
            is_tail = ins.mnemonic == 'jmp' and len(ins.operands) == 1 and ins.operands[0].type == X86_OP_IMM and not owner_start <= ins.operands[0].imm < owner_start + f['size']
            if is_call or is_tail:
                direct = len(ins.operands) == 1 and ins.operands[0].type == X86_OP_IMM
                target = ins.operands[0].imm if direct else None
                calls.append(dict(owner=f['addr'], addr=row['addr'], kind='call' if is_call else 'external-tail-jump', target=hex(target) if target else None, operands=ins.op_str, recordedCompleteBody=target in starts))
    scalar_data = []
    for at in [0x140175516, 0x140173CBE, 0x14018B3E3, 0x14018B3FB, 0x14018B7F0, 0x1401849AC, 0x1401849B7, 0x1401849BF]:
        ins = decoded_by_addr[at]
        mem = [op.mem for op in ins.operands if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP]
        need(len(mem) == 1, ('scalar RIP operand', hex(at)))
        location = ins.address + ins.size + mem[0].disp
        raw = read(location, 4)
        scalar_data.append(dict(instruction=hex(at), addr=hex(location), originalBytes=raw.hex(' '), binary32=struct.unpack('<f',raw)[0]))
    expected_scalars = [1.5,1e14,-.001,.001,.01,-32768,32767,-32767]
    need([bytes.fromhex(v['originalBytes']) for v in scalar_data] == [struct.pack('<f',v) for v in expected_scalars], 'scalar values')
    evidence = dict(schema=1, Domain='native', originalSha256=module.SHA, imageBase=hex(pe.base), functions=functions, data=data, originalPeScalarConstants=scalar_data, verifiedXrefs=xrefs, semanticAnchors=anchors, calls=calls)
    models = model.run()
    receipt = dict(success=True, functions=len(functions), instructions=instruction_count, bodyBytes=primary_bytes, instructionBytes=sum(f['instructionBytes'] for f in functions), embeddedPaddingAndTableBytes=67, dataSpans=len(data), originalPeScalarConstants=len(scalar_data), verifiedXrefs=len(xrefs), semanticAnchors=len(anchors), callAndExternalTailSites=len(calls), unclosedSites=sum(not c['recordedCompleteBody'] for c in calls), modelChecks=models['checks'], scope='Recorded native bodies, exact original bytes, selected branches/fields and immediate geometry helpers. External runtime/ownership and arbitrary live state remain separate. No target code or game execution.')
    return {'evidence.json': enc(evidence), 'verification.json': enc(receipt), 'model.json': enc(models)}

def manifest():
    dependencies = [PE_SOURCE] + [HERE.parent/'bdx-actor-query-20261008'/n for n in ['manifest.json','evidence.json','model.json','annotations.json']]
    return dict(schema=1, files={p.name: dict(bytes=p.stat().st_size, sha256=sha(p.read_bytes())) for p in sorted(HERE.iterdir()) if p.is_file() and p.name != 'manifest.json'}, dependencies={p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in dependencies})

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    outputs = derive()
    for name, content in outputs.items():
        if args.check: need((HERE/name).read_bytes() == content, ('derived bytes', name))
        else: (HERE/name).write_bytes(content)
    if args.check: need(load(HERE/'manifest.json') == manifest(), 'manifest')
    elif (HERE/'report.txt').exists(): (HERE/'manifest.json').write_bytes(enc(manifest()))
    print(outputs['verification.json'].decode())
