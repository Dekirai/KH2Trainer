"""Check bounded allocator evidence against the fixed retail PE. No process access."""
from pathlib import Path
import argparse
import hashlib
import json
import struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

HERE = Path(__file__).resolve().parent
BASE = 0x140000000
EXPECTED = '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'


def sha(b):
    return hashlib.sha256(b).hexdigest()


def octets(s):
    return bytes(int(x, 16) for x in s.split())


def reader(raw):
    assert raw[:2] == b'MZ'
    pe, = struct.unpack_from('<I', raw, 0x3c)
    assert raw[pe:pe+4] == b'PE\0\0'
    assert struct.unpack_from('<H', raw, pe+4)[0] == 0x8664
    opt = pe+24
    assert struct.unpack_from('<H', raw, opt)[0] == 0x20b
    assert struct.unpack_from('<Q', raw, opt+24)[0] == BASE
    table = opt+struct.unpack_from('<H', raw, pe+20)[0]
    sections = [struct.unpack_from('<4I', raw, table+40*i+8)
                for i in range(struct.unpack_from('<H', raw, pe+6)[0])]

    def at(addr, size):
        rva = addr-BASE
        matches = [raw[offset+rva-va:offset+rva-va+size]
                   for _, va, extent, offset in sections
                   if va <= rva and rva-va+size <= extent]
        assert len(matches) == 1 and len(matches[0]) == size, (hex(addr), size)
        return matches[0]
    return at, opt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--generate-header', action='store_true')
    args = parser.parse_args()
    ev = json.loads((HERE/'evidence.json').read_text(encoding='utf-8-sig'))
    helper = json.loads((HERE/'helper-evidence.json').read_text(encoding='utf-8-sig'))
    raw = Path(ev['originalPath']).read_bytes()
    assert sha(raw) == ev['originalSha256'] == helper['originalSha256'] == EXPECTED
    at, opt = reader(raw)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    functions = ev['functions']+helper['functions']
    rows = []
    decoded = {}
    arrays = []
    for f in functions:
        start = int(f['addr'], 16)
        b = octets(f['originalBytes'] if 'originalBytes' in f else f['bytes']['data'])
        assert len(b) == f['size'] == int(f['analysis']['size'], 16)
        assert b == at(start, len(b)), f['addr']
        pages = f.get('pages', f.get('disasm_pages'))
        assert pages and pages[-1]['cursor'].get('done')
        assert not any(p.get('error') or p['cursor'].get('cancelled') for p in pages)
        lines = [line for page in pages for line in page['asm']['lines']]
        assert lines == f['asm']['lines']
        assert len(lines) == f['instruction_count'] == f['total_instructions']
        instructions = list(md.disasm(b, start))
        assert sum(i.size for i in instructions) == len(b)
        assert [i.address for i in instructions] == [int(line['addr'], 16) for line in lines]
        assert f['pseudocode']['cursor'].get('done')
        assert not f['pseudocode'].get('truncated')
        decoded[start] = instructions
        rows.append({'addr':f['addr'], 'size':len(b), 'instructions':len(lines),
                     'originalBytesEqual':True, 'completeDecodedBody':True})
        arrays.append((start-BASE, b))
    assert len(rows) == len(decoded) == 14

    # IDA can attach a reference to a whole 12-byte RUNTIME_FUNCTION row:
    # notably 19C0AC is the end address of the preceding function.
    xref_counts = {'code':0, 'staticData':0, 'runtimeFunctionEndBoundary':0}
    exception_rva, exception_size = struct.unpack_from('<II', raw, opt+112+3*8)
    groups = ev['xrefs']['result']+[f['xrefs'] for f in helper['functions']]
    for group in groups:
        target = int(group['addr'], 16)
        assert not group.get('more') and len(group['xrefs']) == group['xref_count']
        for x in group['xrefs']:
            pc = int(x['addr'], 16)
            if x['type'] == 'code' or x['fn']:
                i = next(md.disasm(at(pc, 15), pc, count=1))
                candidates = [o.imm for o in i.operands if o.type == X86_OP_IMM]
                candidates += [pc+i.size+o.mem.disp for o in i.operands
                               if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP]
                assert target in candidates, (group['addr'], x, i.mnemonic, i.op_str)
                assert i.mnemonic == 'call' or i.mnemonic.startswith('j')
                xref_counts['code'] += 1
            else:
                b = at(pc, 12)
                q = struct.unpack_from('<Q', b)[0]
                dwords = struct.unpack('<III', b)
                if q == target or target-BASE == dwords[0]:
                    xref_counts['staticData'] += 1
                else:
                    assert BASE+exception_rva <= pc < BASE+exception_rva+exception_size
                    assert (pc-BASE-exception_rva)%12 == 0
                    assert dwords[0] < dwords[1] == target-BASE
                    assert pc == 0x142B964DC and target == 0x14019C0AC
                    xref_counts['runtimeFunctionEndBoundary'] += 1
    for item in ev['data']:
        b = octets(item['data'])
        assert b == at(int(item['addr'], 16), len(b))
    slots = struct.unpack('<8Q', at(0x1405B2BB0, 64))
    assert slots == tuple(BASE+x for x in [0x19C0C0,0x19C2B0,0x19C470,0x19C510,
                                        0x19C520,0x19C6E0,0x66F970,0x19C0AC])
    chained = []
    for rva in [0x6B46B4,0x6B46C8]:
        version_flags, _, count, _ = at(BASE+rva, 4)
        assert version_flags & 7 == 1 and version_flags >> 3 == 4
        chain = struct.unpack('<III', at(BASE+rva+4+((count+1)&~1)*2, 12))
        assert chain == (0x19C230,0x19C23D,0x6B46AC)
        chained.append({'rva':hex(rva),'version':1,'flags':4,'kind':'CHAININFO','target':list(map(hex,chain))})
    assert at(0x1406B46D8, 1)[0] == 1  # locked Free has no EH/UH handler flag

    # Verify the CloseHandle import consumed by the two destructors from PE
    # descriptors and names, without trusting an IDA annotation.
    imp_rva, imp_size = struct.unpack_from('<II', raw, opt+112+8)
    imports = {}
    for offset in range(0, imp_size, 20):
        oft, stamp, forwarder, dll_name, iat = struct.unpack('<5I', at(BASE+imp_rva+offset,20))
        if not any([oft,stamp,forwarder,dll_name,iat]):
            break
        index = 0
        while True:
            value, = struct.unpack('<Q', at(BASE+(oft or iat)+index*8,8))
            if not value:
                break
            if not value >> 63:
                name = at(BASE+value+2,120).split(b'\0',1)[0].decode('ascii')
                imports[BASE+iat+index*8] = name
            index += 1
    assert imports[0x14057B368] == 'CloseHandle'
    destructor_import_calls = []
    for start in [0x1400FDA70,0x1400FD950]:
        for i in decoded[start]:
            if i.mnemonic == 'call' and i.operands[0].type == X86_OP_MEM:
                op = i.operands[0]
                assert op.mem.base == X86_REG_RIP
                target = i.address+i.size+op.mem.disp
                assert target == 0x14057B368
                destructor_import_calls.append(hex(i.address))
    assert len(destructor_import_calls) == 3

    header = '// Generated by verify.py from original-byte-verified captures.\n#pragma once\n'
    for rva,b in arrays:
        header += f'static const unsigned char body_{rva:X}[] = {{\n'
        for offset in range(0,len(b),16):
            header += '    '+','.join(f'0x{x:02x}' for x in b[offset:offset+16])+',\n'
        header += '};\n'
    header += 'struct NativeBody { unsigned rva; const unsigned char* bytes; size_t size; };\n'
    header += 'static const NativeBody nativeBodies[] = {\n'
    header += ''.join(f'    {{0x{rva:X}, body_{rva:X}, sizeof(body_{rva:X})}},\n' for rva,_ in arrays)
    header += '};\n'
    hpath = HERE/'NativeBodies.h'
    if args.generate_header:
        hpath.write_text(header, encoding='utf-8', newline='\n')
    assert hpath.read_text(encoding='utf-8') == header
    result = {'passed':True, 'originalSha256':EXPECTED, 'functions':rows,
              'completeBodies':len(rows), 'instructions':sum(r['instructions'] for r in rows),
              'bodyBytes':sum(r['size'] for r in rows), 'dataBytes':sum(len(octets(d['data'])) for d in ev['data']),
              'incomingXrefs':xref_counts, 'chainedUnwind':chained,
              'closeHandleIat':'0x14057B368','verifiedImportCalls':destructor_import_calls,
              'scope':'Static body/table/import verification; no caller completeness or live thread guarantees.',
              'inputs':{p:sha((HERE/p).read_bytes()) for p in ['evidence.json','helper-evidence.json','NativeBodies.h']}}
    (HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['passed','completeBodies','instructions','bodyBytes','dataBytes','incomingXrefs']}))


if __name__ == '__main__':
    main()
