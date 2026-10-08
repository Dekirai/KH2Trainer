"""Static bounded bulk-lifetime evidence verifier. No process or IDB access."""
from pathlib import Path
import hashlib
import json
import struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = 0x140000000
EXPECTED_SHA = '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def octets(value):
    return bytes(int(part, 16) for part in value.split())


def reader(raw):
    assert raw[:2] == b'MZ'
    pe = struct.unpack_from('<I', raw, 0x3c)[0]
    assert raw[pe:pe+4] == b'PE\0\0'
    assert struct.unpack_from('<H', raw, pe+4)[0] == 0x8664
    opt = pe+24
    assert struct.unpack_from('<H', raw, opt)[0] == 0x20b
    assert struct.unpack_from('<Q', raw, opt+24)[0] == BASE
    table = opt+struct.unpack_from('<H', raw, pe+20)[0]
    sections = [struct.unpack_from('<4I', raw, table+40*i+8)
                for i in range(struct.unpack_from('<H', raw, pe+6)[0])]

    def at(addr, length):
        rva = addr-BASE
        spans = []
        for _, va, size, offset in sections:
            if va <= rva and rva-va+length <= size:
                start = offset+rva-va
                assert start+length <= len(raw)
                spans.append(raw[start:start+length])
        assert len(spans) == 1, (hex(addr), length)
        return spans[0]

    return at, opt


def main():
    source = (HERE/'evidence.json').read_bytes()
    ev = json.loads(source)
    raw = Path(ev['originalPath']).read_bytes()
    assert sha(raw) == ev['originalSha256'] == EXPECTED_SHA
    at, opt = reader(raw)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    decoded = {}

    def body(f, fresh):
        start = int(f['addr'], 16)
        b = octets(f['originalBytes'])
        assert len(b) == f['size'] == f['analysis']['size']
        assert b == at(start, len(b)), f['addr']
        rows = f['asm']['lines']
        assert f['cursor'].get('done') and not f['cursor'].get('next')
        assert not f['cursor'].get('cancelled')
        assert len(rows) == f['instruction_count'] == f['total_instructions']
        assert [r for p in f['pages'] for r in p['asm']['lines']] == rows
        addresses = [int(r['addr'], 16) for r in rows]
        assert addresses == sorted(set(addresses)) and addresses[0] == start
        instructions = list(md.disasm(b, start))
        assert sum(i.size for i in instructions) == len(b)
        assert [i.address for i in instructions] == addresses, f['addr']
        decoded[start] = {i.address: i for i in instructions}
        return {'addr':f['addr'], 'size':len(b), 'instructions':len(rows),
                'originalBytesEqual':True, 'completeDecodedBody':True,
                'freshCapture':fresh}

    fresh = [body(f, True) for f in ev['functions']]
    assert len(fresh) == 15 and len(decoded) == 15
    reused = []
    reused_sources = []
    for item in ev['reusedEvidence']:
        path = ROOT/item['path']
        content = path.read_bytes()
        old = json.loads(content)
        assert old['originalSha256'] == EXPECTED_SHA
        records = {f['addr'].lower():f for f in old['functions']}
        for addr in item['functionAddresses']:
            reused.append(body(records[addr.lower()], False))
        reused_sources.append({'path':item['path'], 'sha256':sha(content)})

    # Validate captured incoming references against the PE, without claiming
    # that every caller body or every possible indirect caller was analyzed.
    xrefs = {'directCode':0, 'functionDataReference':0, 'staticData':0}
    for f in ev['functions']:
        target = int(f['addr'], 16)
        result, = f['xrefs']['result']
        assert not result['more']
        assert result['xref_count'] == len(result['xrefs'])
        for x in result['xrefs']:
            pc = int(x['addr'], 16)
            if x['type'] == 'code' or x['fn']:
                i = next(md.disasm(at(pc, 15), pc, count=1))
                candidates = []
                for op in i.operands:
                    if op.type == X86_OP_IMM:
                        candidates.append(op.imm)
                    elif op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                        candidates.append(pc+i.size+op.mem.disp)
                assert target in candidates, (f['addr'], x, i.mnemonic, i.op_str)
                if x['type'] == 'code':
                    assert i.mnemonic == 'call' or i.mnemonic.startswith('j')
                    xrefs['directCode'] += 1
                else:
                    xrefs['functionDataReference'] += 1
            else:
                b = at(pc, 8)
                assert struct.unpack('<Q', b)[0] == target or struct.unpack('<I', b[:4])[0] == target-BASE
                xrefs['staticData'] += 1

    for item in ev['data']:
        assert octets(item['data']) == at(int(item['addr'], 16), item['size'])
    assert struct.unpack('<Q', at(0x1405B2BC0, 8))[0] == 0x14019C470

    def instruction(pc, mnemonic, operands=None):
        matches = [items[pc] for items in decoded.values() if pc in items]
        assert len(matches) == 1, hex(pc)
        i = matches[0]
        assert i.mnemonic == mnemonic, (hex(pc), i.mnemonic)
        if operands is not None:
            assert i.op_str == operands, (hex(pc), i.op_str, operands)
        return i

    def call(pc, target):
        i = instruction(pc, 'call')
        assert i.operands[0].type == X86_OP_IMM and i.operands[0].imm == target

    # Exact ordered call sites of all four recorded field-heap teardown paths.
    sequences = [
        (0x1401524A0, [0x1401524AB,0x1401524B7,0x1401524BE], None),
        (0x1401524E0, [0x140152541,0x14015254D,0x140152554], 0x1401524FF),
        (0x140152680, [0x1401527F7,0x140152803,0x14015280A], 0x1401527E6),
        (0x140152A90, [0x140152B40,0x140152B4C,0x140152B53], 0x140152AFE)]
    for _, pcs, early in sequences:
        for pc, target in zip(pcs, [0x14019FFD0,0x14039D400,0x14039CCA0]):
            call(pc, target)
        # ECX=0 immediately before this direct resource-marking call.
        all_i = next(v for v in decoded.values() if pcs[-1] in v)
        prev = max(k for k in all_i if k < pcs[-1])
        assert all_i[prev].mnemonic == 'xor' and all_i[prev].op_str == 'ecx, ecx'
        if early is not None:
            call(early, 0x14014FF10)
            assert early < pcs[0]
    instruction(0x14014FFEA, 'call', 'rax')
    instruction(0x140150014, 'call', 'qword ptr [rax + 0x10]')
    instruction(0x140150021, 'call', 'qword ptr [rax + 0x10]')
    instruction(0x140152570, 'mov', 'rdx, rcx')
    instruction(0x14015257D, 'jmp', 'qword ptr [rax + 0x10]')
    instruction(0x14019C4E2, 'mov', 'eax, 0xefaccafe')
    instruction(0x14019C4E7, 'rep stosd')
    instruction(0x14039CDD5, 'cmp', 'ebx, 0x1388')
    instruction(0x14039CDDB, 'jne', '0x14039ce50')
    instruction(0x14039CE45, 'call', 'qword ptr [rax + 0x10]')
    instruction(0x14039D44B, 'add')
    instruction(0x14039D454, 'mov')
    call(0x14019FFDD, 0x1401AE6B0)
    assert not any(i.mnemonic == 'call' for i in decoded[0x1401AE6B0].values())
    assert not any(i.mnemonic == 'call' for i in decoded[0x14039B640].values())
    instruction(0x14014F8C5, 'mov', 'rbx, r9')
    instruction(0x14014F8F7, 'mov', 'qword ptr [rax], rbx')
    instruction(0x140150076, 'jmp', '0x140135470')

    def cstring(addr):
        result = bytearray()
        for offset in range(1024):
            ch = at(addr+offset, 1)[0]
            if not ch:
                return result.decode('ascii')
            result.append(ch)
        raise AssertionError('unterminated import name')

    imports = {}
    descriptor = BASE+struct.unpack_from('<I', raw, opt+120)[0]
    while True:
        oft, stamp, forward, name, ft = struct.unpack('<5I', at(descriptor, 20))
        if not any((oft,stamp,forward,name,ft)):
            break
        index = 0
        while True:
            value = struct.unpack('<Q', at(BASE+(oft or ft)+8*index, 8))[0]
            if not value:
                break
            if not value & (1 << 63):
                imports[BASE+ft+8*index] = {'declaringDll':cstring(BASE+name), 'name':cstring(BASE+value+2)}
            index += 1
        descriptor += 20
    fiber_imports = []
    for pc, expected in [(0x1401352A9,'CreateFiber'),(0x140135490,'ConvertThreadToFiber'),
                         (0x1401354A8,'SwitchToFiber'),(0x1401354AE,'ConvertFiberToThread'),
                         (0x140135529,'SwitchToFiber')]:
        i = instruction(pc, 'call')
        operand = i.operands[0]
        assert operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP
        slot = pc+i.size+operand.mem.disp
        assert imports[slot]['name'] == expected
        fiber_imports.append({'call':hex(pc),'iatSlot':hex(slot),**imports[slot]})

    result = {'status':'PASS','originalSha256':sha(raw),'evidenceSha256':sha(source),
              'freshFunctions':len(fresh),'freshInstructions':sum(f['instructions'] for f in fresh),
              'freshOriginalBytes':sum(f['size'] for f in fresh),'freshDataBytes':sum(d['size'] for d in ev['data']),
              'functions':fresh,'reusedFunctions':reused,'reusedSources':reused_sources,
              'callerReferenceSitesValidated':xrefs,'fiberImports':fiber_imports,
              'limits':['Xref lists are complete for the current IDA database query, not a proof of all indirect targets.',
                        'Caller sites are byte-decoded references, not complete analyzed caller bodies.',
                        'No Actor-wide serialization or common pre-destruction boundary is proved.',
                        'No game instructions were executed and no running process was read.']}
    (HERE/'verification.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','freshFunctions','freshInstructions','freshOriginalBytes','freshDataBytes','callerReferenceSitesValidated')}))


if __name__ == '__main__':
    main()
