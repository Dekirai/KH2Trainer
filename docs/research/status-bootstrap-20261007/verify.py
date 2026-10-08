"""Original-byte and bounded STATUS call-closure verification; no live process access."""
from pathlib import Path
import hashlib, importlib.util, json, struct, sys
sys.dont_write_bytecode = True
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('retail_verify', HERE.parent/'actor-scale-contract-20261007/verify.py')
base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)

def main():
    source = (HERE/'evidence.json').read_bytes(); ev = json.loads(source)
    raw = base.DEFAULT_EXE.read_bytes(); result = base.validate(ev, raw)
    at = base.original_reader(raw, 0x140000000)
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    bodies = {int(f['addr'], 16): f for f in ev['functions']}
    decoded = {}; embedded = 0
    for start, f in bodies.items():
        b = base.octets(f['originalBytes']); rows = f['asm']['lines']; insns = []
        for n, row in enumerate(rows):
            pc = int(row['addr'], 16); insn = next(md.disasm(b[pc-start:], pc, count=1), None)
            assert insn is not None, hex(pc)
            end = int(rows[n+1]['addr'], 16) if n+1 < len(rows) else start+len(b)
            if insn.address+insn.size != end:
                if (start, insn.address+insn.size, end) == (0x1404AD2C0, 0x1404AD2FC, 0x1404AD300):
                    assert b[insn.address+insn.size-start:end-start] == bytes.fromhex('0f1f4000')
                    embedded += 4
                    insns.append(insn)
                    continue
                # 401730 has a three-byte NOP, 27 DWORD targets, 152 selector bytes.
                assert (start, insn.address+insn.size, end) == (0x140401730, 0x140401A59, 0x140401B60)
                tail = b[insn.address+insn.size-start:]
                assert len(tail) == 263 and tail[:3] == bytes.fromhex('0f1f00')
                targets = [0x140000000+x[0] for x in struct.iter_unpack('<I', tail[3:111])]
                valid = {int(r['addr'], 16) for r in rows}
                assert len(targets) == 27 and all(t in valid for t in targets)
                assert len(tail[111:]) == 152 and all(i < 27 for i in tail[111:])
                embedded += len(tail)
            insns.append(insn)
        decoded[start] = insns

    # Init calls EncodeNullable with ECX=0 at each of its five call sites.
    # There are no jumps in this straight-line constructor.
    init = decoded[0x1403C0010]; null_calls = []; last_rcx = None
    for insn in init:
        assert not insn.mnemonic.startswith('j')
        if insn.mnemonic == 'call':
            if insn.operands[0].type == X86_OP_IMM and insn.operands[0].imm == 0x1404AD240:
                assert last_rcx is not None and last_rcx.mnemonic == 'xor' and last_rcx.op_str == 'ecx, ecx'
                null_calls.append(insn.address)
            last_rcx = None
        elif any(insn.reg_name(r) in ('rcx', 'ecx', 'cx', 'cl', 'ch') for r in insn.regs_access()[1]):
            last_rcx = insn
    assert len(null_calls) == 5
    encoder = decoded[0x1404AD240]
    assert [(i.mnemonic, i.op_str) for i in encoder[:9]] == [
        ('push','rbx'),('sub','rsp, 0x20'),('mov','rbx, rcx'),('test','rcx, rcx'),
        ('jne','0x1404ad256'),('xor','eax, eax'),('add','rsp, 0x20'),('pop','rbx'),('ret','')]
    lookup = {i.address:i for i in decoded[0x14041E8F0]}
    cmp_address = lookup[0x14041E8FB]
    assert cmp_address.mnemonic == 'lea' and cmp_address.operands[1].mem.base == X86_REG_RIP
    assert cmp_address.address+cmp_address.size+cmp_address.operands[1].mem.disp == 0x14041E8E0
    assert lookup[0x14041E90B].mnemonic == 'mov' and lookup[0x14041E90B].op_str == 'qword ptr [rsp + 0x20], rax'
    assert [(i.mnemonic,i.op_str) for i in decoded[0x14041E8E0]] == [
        ('movzx','eax, word ptr [rdx]'),('sub','ecx, eax'),('mov','eax, ecx'),('ret','')]

    # Verify PE import identity directly from the original import directory.
    pe = struct.unpack_from('<I', raw, 0x3c)[0]; optional = pe+24
    import_rva = struct.unpack_from('<I', raw, optional+120)[0]
    def cstring(addr):
        out = bytearray()
        while len(out) < 1024:
            ch = at(addr+len(out), 1)[0]
            if ch == 0: return out.decode('ascii')
            out.append(ch)
        raise AssertionError('unbounded import string')
    imports = {}; descriptor = 0x140000000+import_rva
    while True:
        oft, stamp, forward, name, ft = struct.unpack('<5I', at(descriptor, 20))
        if (oft,stamp,forward,name,ft) == (0,0,0,0,0): break
        index = 0
        while True:
            value = struct.unpack('<Q', at(0x140000000+(oft or ft)+8*index,8))[0]
            if value == 0: break
            if not value & (1 << 63): imports[0x140000000+ft+8*index] = cstring(0x140000000+value+2)
            index += 1
        descriptor += 20
    expected_imports = {
        0x14057B2D8:'EnterCriticalSection', 0x14057B2D0:'LeaveCriticalSection',
        0x14057B150:'WaitForSingleObjectEx', 0x14057B280:'SetEvent',
        0x14057B2C0:'ResetEvent', 0x14057BB80:'bsearch'}
    assert all(imports.get(addr) == name for addr,name in expected_imports.items())

    closure = {int(a,16) for a in ev['specializedWriterClosure']}
    edges = []; external = []; switch_count = 0
    for start in sorted(closure):
        end = start+bodies[start]['size']
        for insn in decoded[start]:
            # The nonnull encoder branch cannot be reached by these roots.
            if start == 0x1404AD240 and insn.address >= 0x1404AD256: continue
            if insn.mnemonic != 'call' and not insn.mnemonic.startswith('j'): continue
            op = insn.operands[0]
            if op.type == X86_OP_IMM:
                target = op.imm
                if start <= target < end: continue
                assert target in closure, ('missing tail/call target',hex(insn.address),hex(target))
                edges.append([hex(insn.address),hex(target)])
            elif insn.address == 0x1404017B3:
                assert insn.mnemonic == 'jmp' and insn.op_str == 'rcx'; switch_count += 1
            else:
                assert op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP, hex(insn.address)
                slot = insn.address+insn.size+op.mem.disp
                if slot == 0x14057BCA0:
                    assert insn.address in (0x140439FF9,0x14043A066)
                    name = 'CFG dispatch to decoded condition-variable API'
                else:
                    assert slot in expected_imports, (hex(insn.address),hex(slot))
                    name = expected_imports[slot]
                external.append(dict(site=hex(insn.address),slot=hex(slot),contract=name))
    assert switch_count == 1
    assert len(closure) == 25
    for root in ev['writerRoots']:
        start = int(root,16); end = start+bodies[start]['size']
        assert not any(i.mnemonic == 'jmp' and (i.operands[0].type != X86_OP_IMM or not start <= i.operands[0].imm < end) for i in decoded[start])
    for d in ev['data']:
        assert base.octets(d['originalBytes']) == d['label'].encode('ascii')+b'\0'
    result.update(evidenceSha256=hashlib.sha256(source).hexdigest(), capstoneInstructions=sum(len(i) for i in decoded.values()),
        embeddedSwitchAndPaddingBytes=embedded, specializedClosureFunctions=len(closure), nullEncodeCallsites=[hex(i) for i in null_calls],
        closureEdges=edges, externalContractCalls=external, rootsKeepTheirFrames=True,
        failures=0, liveGame=False, installedObserver=False,
        scope='Original PE bytes, complete ASM, decoded control-flow closure with five null-encoder call sites, fixed bsearch comparator and explicit external API contracts. Does not prove arbitrary exception/invalid-parameter handlers, mod code, all native threads, runtime import integrity or successful bootstrap.')
    (HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('bodies','data','closureEdges','externalContractCalls')}))

if __name__ == '__main__': main()
