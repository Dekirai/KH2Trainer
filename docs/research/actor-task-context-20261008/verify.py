"""Verify static task/fiber context capture against the exact original retail PE."""
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
    decoded = {}; all_insns = {}
    for f in ev['functions']:
        start = int(f['addr'],16); b = base.octets(f['originalBytes']); rows = f['asm']['lines']; insns = []
        assert f['pseudocode']['cursor']['done'] and not f['pseudocode'].get('truncated')
        for n,row in enumerate(rows):
            pc = int(row['addr'],16); i = next(md.disasm(b[pc-start:],pc,count=1),None)
            end = int(rows[n+1]['addr'],16) if n+1<len(rows) else start+len(b)
            assert i and i.address+i.size == end, ('instruction gap',hex(pc),hex(end))
            insns.append(i); all_insns[pc]=i
        decoded[start]=insns
    assert len(decoded)==38
    checks=[]
    def exact(pc,mnemonic,operands):
        i=all_insns[pc]
        assert (i.mnemonic,i.op_str)==(mnemonic,operands),(hex(pc),i.mnemonic,i.op_str)
        checks.append(dict(site=hex(pc),instruction=mnemonic+' '+operands))
    def branch(pc,target,kind='call'): exact(pc,kind,hex(target))
    def rip(pc,target,mnemonic):
        i=all_insns[pc]
        assert i.mnemonic==mnemonic and any(o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and i.address+i.size+o.mem.disp==target for o in i.operands),hex(pc)
        checks.append(dict(site=hex(pc),ripTarget=hex(target),instruction=i.mnemonic+' '+i.op_str))
    branch(0x14014ed63,0x14014f600);rip(0x14014ed68,0x1409ba888,'mov')
    branch(0x14014eddd,0x140150740)
    rip(0x140150752,0x140716888,'mov');rip(0x140150760,0x140716890,'mov')
    branch(0x14015078a,0x14014f600);rip(0x14015078f,0x140716868,'mov')
    branch(0x140153192,0x140150820);exact(0x1401531a2,'jmp','qword ptr [rdx + 8]')
    rip(0x140150604,0x1409ba888,'mov');branch(0x14015061f,0x14014f8a0)
    branch(0x14014ecd9,0x14014fc20);branch(0x14014fc25,0x14014fd60,'jmp')
    exact(0x1401503a2,'call','qword ptr [rax + 0x10]')
    exact(0x140150590,'mov','rax, qword ptr [rcx + 0x28]');exact(0x14015059c,'jmp','rax')
    branch(0x1401503b9,0x14014fc20);branch(0x1401503c3,0x140150060)
    branch(0x1401503d4,0x1401500d0);exact(0x1401503e2,'call','qword ptr [rax + 0x18]')
    exact(0x1401504f0,'mov','rax, qword ptr [rcx + 0x30]');exact(0x1401504fc,'jmp','rax')
    branch(0x140150723,0x1401524e0);branch(0x14015073a,0x140150060,'jmp')
    branch(0x1401503f6,0x14014fc20);branch(0x140150400,0x140150060);branch(0x140150416,0x14014fa60)
    exact(0x14014f659,'call','qword ptr [rcx]');branch(0x14014f67b,0x140135470,'jmp')
    branch(0x140150076,0x140135470,'jmp');branch(0x1401500a0,0x140135470,'jmp')
    for site in (0x140152787,0x1401527cb,0x1401528f5):branch(site,0x140150060)
    exact(0x14014fdfc,'call','qword ptr [rbx]')
    branch(0x14014fe2f,0x140135250);branch(0x14014fe4a,0x140135470)
    branch(0x14014fe5b,0x1401352e0);branch(0x14014fe7d,0x14014f680)
    exact(0x1401354e0,'call','qword ptr [rax]')
    exact(0x1401352e0,'cmp','qword ptr [rcx + 8], 0')
    exact(0x1401352e5,'mov','dword ptr [rcx + 0x28], 1')
    branch(0x1401352ec,0x140135320,'jne')
    exact(0x14013530f,'mov','qword ptr [rax + 8], rcx')
    rip(0x140135319,0x140713438,'mov')
    exact(0x1401352af,'mov','qword ptr [rbx + 0x20], rax')
    exact(0x1401352b3,'mov','rax, rbx')
    exact(0x14013522b,'call','qword ptr [rax + 0x10]')
    branch(0x140135230,0x140135230,'jmp')
    for site in (0x14014f70b,0x14014fa25,0x14014fb10,0x14014fbe0,0x14014fffd,0x140150180):
        branch(site,0x1401352e0)
    # Original descriptor and vtables, not live pointer assumptions.
    assert struct.unpack('<4Q',at(0x1405b14b8,32))==(0x140150640,0x1401505a0,0x140150590,0x1401504f0)
    field=struct.unpack('<7Q',at(0x140716860,56))
    assert field[0]==0x1405b14b8 and field[1]==0 and field[5]==field[6]==0
    assert struct.unpack('<Q',at(0x1405aaa90,8))[0]==0x1401351d0
    assert struct.unpack('<Q',at(0x140713420,8))[0]==0x43214321
    assert struct.unpack('<Q',at(0x1405b11b0,8))[0]==0x14014eb70
    # Decode all captured incoming xrefs, including RIP-relative global accesses.
    spans={int(d['addr'],16):d for d in ev['data']}; xref_count=0; unwind_end_refs=[]; unwind_begin_refs=[]
    pe=struct.unpack_from('<I',raw,0x3c)[0]; optional=pe+24
    exception_rva,exception_size=struct.unpack_from('<II',raw,optional+136)
    runtime_functions={0x140000000+exception_rva+n:struct.unpack('<3I',at(0x140000000+exception_rva+n,12)) for n in range(0,exception_size,12)}
    for group in ev['xrefs']+ev['globalXrefs']:
        assert not group['more'] and group['xref_count']==len(group['xrefs'])
        target=int(group['addr'],16)
        for ref in group['xrefs']:
            pc=int(ref['addr'],16);b=base.octets(spans[pc]['originalBytes'])
            if ref['fn']:
                i=next(md.disasm(b,pc,count=1),None);assert i
                assert any((o.type==X86_OP_IMM and o.imm==target) or (o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and pc+i.size+o.mem.disp==target) for o in i.operands),('xref mismatch',hex(pc),i.mnemonic,i.op_str,hex(target))
            else:
                direct=int.from_bytes(b[:4],'little')+0x140000000==target or int.from_bytes(b[:8],'little')==target
                entry=runtime_functions.get(pc)
                if entry and entry[0]+0x140000000==target:
                    unwind_begin_refs.append(dict(source=hex(pc),target=hex(target),kind='RUNTIME_FUNCTION.BeginAddress; not a caller'))
                if not direct:
                    assert entry and entry[1]+0x140000000==target,('data xref mismatch',hex(pc))
                    unwind_end_refs.append(dict(source=hex(pc),target=hex(target),kind='RUNTIME_FUNCTION.EndAddress; not a caller'))
            xref_count+=1
    # Parse import descriptors, OriginalFirstThunk and names directly from PE.
    pe=struct.unpack_from('<I',raw,0x3c)[0]; optional=pe+24
    imports={}; descriptor=0x140000000+struct.unpack_from('<I',raw,optional+120)[0]
    def cstring(addr):
        out=bytearray()
        while len(out)<1024:
            b=at(addr+len(out),1)[0]
            if not b:return out.decode('ascii')
            out.append(b)
        raise AssertionError('unterminated import name')
    while True:
        oft,stamp,forward,name,ft=struct.unpack('<5I',at(descriptor,20))
        if not any((oft,stamp,forward,name,ft)):break
        dll=cstring(0x140000000+name);idx=0
        while True:
            thunk=struct.unpack('<Q',at(0x140000000+(oft or ft)+idx*8,8))[0]
            if not thunk:break
            if not thunk&(1<<63):imports[0x140000000+ft+idx*8]=dict(dll=dll,name=cstring(0x140000000+thunk+2),originalThunk=hex(thunk))
            idx+=1
        descriptor+=20
    checked_imports=[]
    for expected in ev['imports']:
        addr=int(expected['addr'],16);actual=imports[addr]
        assert actual['name']==expected['name']
        checked_imports.append(dict(slot=hex(addr),**actual))
    import_calls=[]
    for body in decoded.values():
        for i in body:
            if i.mnemonic=='call' and i.operands[0].type==X86_OP_MEM and i.operands[0].mem.base==X86_REG_RIP:
                slot=i.address+i.size+i.operands[0].mem.disp
                if slot in {int(x['addr'],16) for x in ev['imports']}:
                    import_calls.append(dict(site=hex(i.address),slot=hex(slot),name=imports[slot]['name']))
    assert len(import_calls)==6
    result.update(evidenceSha256=hashlib.sha256(source).hexdigest(),capstoneInstructions=len(all_insns),embeddedDataBytes=0,
        verifiedIncomingXrefs=xref_count,unwindEndReferences=unwind_end_refs,unwindBeginReferences=unwind_begin_refs,importIdentities=checked_imports,fiberImportCalls=import_calls,keySites=checks,
        indirectEdges=[dict(function=hex(start),site=hex(i.address),instruction=i.mnemonic+' '+i.op_str) for start,body in decoded.items() for i in body if i.mnemonic in ('call','jmp') and i.operands[0].type!=X86_OP_IMM],
        failures=0,liveGame=False,idbMutated=False,
        scope='38 complete original bodies, instruction boundaries, pseudocode completion, all captured incoming/global xrefs, descriptor/vtable bindings and five PE import identities. Does not establish all OS-thread entries, valid runtime objects/imports, callback closure or native no-yield behavior beyond the stated sites.')
    (HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('bodies','data','keySites','indirectEdges','importIdentities','fiberImportCalls','unwindBeginReferences')}))

if __name__=='__main__':main()
