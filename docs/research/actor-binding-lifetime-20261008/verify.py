"""Validate fresh static actor-binding evidence against the original retail PE."""
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
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    decoded = {}; gaps = []
    for f in ev['functions']:
        start = int(f['addr'], 16); b = base.octets(f['originalBytes']); rows = f['asm']['lines']; insns = []
        for n, row in enumerate(rows):
            pc = int(row['addr'], 16); insn = next(md.disasm(b[pc-start:], pc, count=1), None)
            assert insn is not None, hex(pc)
            end = int(rows[n+1]['addr'], 16) if n+1 < len(rows) else start+len(b)
            assert insn.address+insn.size <= end, hex(pc)
            if insn.address+insn.size != end:
                gaps.append(dict(function=hex(start), start=hex(insn.address+insn.size), end=hex(end), bytes=b[insn.address+insn.size-start:end-start].hex()))
            insns.append(insn)
        decoded[start] = insns
    # The only non-instruction ranges are original DWORD switch tables.
    assert [(x['function'],x['start'],x['end']) for x in gaps] == [
        ('0x1403df930','0x1403dfe3c','0x1403dfea0'),
        ('0x1403fcec0','0x1403fd100','0x1403fd124')]
    for gap in gaps:
        valid = {i.address for i in decoded[int(gap['function'],16)]}
        targets = [0x140000000+x[0] for x in struct.iter_unpack('<I',bytes.fromhex(gap['bytes']))]
        assert all(t in valid for t in targets)
        gap['targets'] = [hex(t) for t in targets]
    all_insns = {i.address:i for body in decoded.values() for i in body}
    expected = {
        0x1403b3251:('xor','r14d, r14d'),
        0x1403b33a0:('mov','qword ptr [rsi + 0x5c0], r14'),
        0x1403b3969:('call','qword ptr [r8 + 8]'),
        0x1403a7af4:('mov','qword ptr [rip + 0x2668ad5], rsi'),
        0x1403a7b16:('call','0x1403c0620'),
        0x1403a7b1b:('mov','qword ptr [rsi + 0x5c0], rax'),
        0x1403a7b32:('mov','dword ptr [rbx + 0x268], eax'),
        0x1403dfa51:('jmp','0x1403a7cb0'),
        0x1403dfe25:('jmp','0x1403a7cb0'),
        0x140405056:('call','0x1403a7a40'),
        0x14041569c:('call','0x1403a7a40'),
        0x1404158dd:('call','0x1403a80e0'),
        0x1404159b9:('call','0x1403a7a40'),
        0x1403da97d:('call','0x1403b3200'),
        0x1403d2db5:('call','0x1403da940'),
        0x1403d5863:('call','0x1403d2da0'),
        0x1403a7a74:('call','0x1403d5840'),
        0x1403a7e62:('call','0x140405030'),
        0x14040cbae:('call','0x14014f8a0'),
        0x14040cf17:('jmp','0x14040d000'),
        0x14040d0c2:('call','0x140150080'),
        0x14040d151:('call','0x140150060'),
        0x14040d16a:('call','0x140150060'),
        0x14040d2ac:('call','0x140405030'),
        0x14040d495:('call','0x140150060'),
        0x14040d4ae:('call','0x140150060'),
        0x1403fc9d0:('call','0x1401506b0'),
        0x1403fcaa0:('call','0x1403fcec0'),
        0x1403fd0f3:('call','0x1404158c0'),
        0x1403bf34b:('call','qword ptr [r8]'),
        0x1403bf4c6:('call','0x1403bf300'),
        0x1403bf4d1:('jmp','0x1403bf300'),
        0x1403bf881:('call','0x1401506b0'),
        0x14041ea3f:('call','0x14012ffd0'),
        0x14041ea4a:('call','0x1400fdbb0'),
        0x14041eaa9:('call','0x1403df930'),
        0x14041eb04:('call','0x1400fdd80')}
    for pc,wanted in expected.items():
        i = all_insns[pc]
        assert (i.mnemonic,i.op_str) == wanted, (hex(pc),i.mnemonic,i.op_str,wanted)
    # Independently verify every returned xref's exact source encoding. This
    # confirms each saved edge, not the absence of arbitrary computed callers.
    xref_kinds = {}; code_sites = 0; data_sites = 0
    spans = {int(d['addr'],16):d for d in ev['data']}
    for group in ev['xrefs']['result']:
        assert group['more'] is False and group['xref_count'] == len(group['xrefs'])
        target = int(group['addr'],16)
        for ref in group['xrefs']:
            pc = int(ref['addr'],16); d=spans[pc]; b=base.octets(d['originalBytes'])
            if ref['fn']:
                i=next(md.disasm(b,pc,count=1),None); assert i
                if ref['type']=='code':
                    assert i.mnemonic in ('call','jmp') and i.operands[0].type==X86_OP_IMM and i.operands[0].imm==target
                else:
                    assert i.mnemonic=='lea' and i.operands[1].type==X86_OP_MEM and i.operands[1].mem.base==X86_REG_RIP
                    assert i.address+i.size+i.operands[1].mem.disp==target
                code_sites+=1
            else:
                assert int.from_bytes(b,'little')+0x140000000==target
                data_sites+=1
    edges=[]; indirect=[]
    for start, body in decoded.items():
        for i in body:
            if i.mnemonic=='call' or i.mnemonic=='jmp':
                if i.operands[0].type==X86_OP_IMM:
                    edges.append(dict(function=hex(start),site=hex(i.address),operation=i.mnemonic,target=hex(i.operands[0].imm)))
                else: indirect.append(dict(function=hex(start),site=hex(i.address),instruction=i.mnemonic+' '+i.op_str))
    result.update(evidenceSha256=hashlib.sha256(source).hexdigest(),capstoneInstructions=sum(len(v) for v in decoded.values()),
        embeddedSwitchBytes=sum(len(bytes.fromhex(x['bytes'])) for x in gaps),switchTables=gaps,
        assertedKeySites=[hex(x) for x in expected],verifiedInstructionXrefs=code_sites,verifiedDataXrefs=data_sites,
        callAndTailEdges=edges,indirectCallsOrJumps=indirect,failures=0,liveGame=False,productFilesChanged=False,
        scope='20 complete bodies; all original bytes, pagination and decoded instruction boundaries; two checked switch tables; key stores/calls and every returned xref source. No whole-program thread, lifetime, all-callers or mutex closure claim.')
    (HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('bodies','data','callAndTailEdges','indirectCallsOrJumps','switchTables','assertedKeySites')}))

if __name__ == '__main__': main()
