"""Reproduce static App/CLR/thread evidence. Never loads or executes the target PE."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, struct, subprocess, sys
sys.dont_write_bytecode=True
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('retail_verify',HERE.parent/'actor-scale-contract-20261007/verify.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--rebuild-clr',action='store_true');ap.add_argument('--output',type=Path,default=HERE/'verification.json');args=ap.parse_args()
    raw=base.DEFAULT_EXE.read_bytes();ev=json.loads((HERE/'evidence.json').read_text());clr=json.loads((HERE/'clr-evidence.json').read_text())
    result=base.validate(ev,raw);at=base.original_reader(raw,0x140000000)
    assert ev['Domain']=='native' and clr['Domain']=='clr'
    assert clr['originalSha256']==ev['originalSha256']
    if args.rebuild_clr:
        target=HERE/'clr-reproduced.json'
        subprocess.run(['dotnet','run','--project',str(HERE/'MetadataDump.csproj'),'--',str(base.DEFAULT_EXE),str(target)],check=True,capture_output=True,text=True)
        assert json.loads(target.read_text())==clr,'metadata regeneration differs'
        target.unlink()
    md=Cs(CS_ARCH_X86,CS_MODE_64);md.detail=True;insns={};gaps=[]
    for f in ev['functions']:
        start=int(f['addr'],16);b=base.octets(f['originalBytes']);rows=f['asm']['lines']
        assert f['pseudocode']['cursor']['done']
        assert base.octets(f['idaBytes'])==b
        for n,row in enumerate(rows):
            pc=int(row['addr'],16);i=next(md.disasm(b[pc-start:],pc,count=1),None);assert i
            end=int(rows[n+1]['addr'],16) if n+1<len(rows) else start+len(b)
            if i.address+i.size!=end:
                gap=b[pc-start+i.size:end-start]
                assert i.address+i.size<end and gap and set(gap)=={0xcc},('instruction gap',hex(pc),hex(end),i.mnemonic,i.op_str)
                gaps.append({'after':hex(pc),'bytes':gap.hex(),'kind':'INT3 padding in IDA primary extent'})
            insns[pc]=i
    assert len(ev['functions'])==29 and len(ev['chunkedFunctions'])==2
    chunk_bytes=0;chunk_instructions=0
    for f in ev['chunkedFunctions']:
        merged=[]
        for p in f['pages']:
            assert p['offset']==len(merged) and p['instruction_count']==len(p['asm']['lines'])
            merged.extend(p['asm']['lines'])
        assert f['cursor']['done'] and f['pages'][-1]['cursor']['done'] and merged==f['asm']['lines']
        assert len(merged)==f['total_instructions']==f['instruction_count']
        expected=[int(r['addr'],16) for r in merged];actual=[]
        for c in f['chunks']:
            a=int(c['addr'],16);b=base.octets(c['originalBytes']);assert b==base.octets(c['idaBytes'])==at(a,c['size'])
            decoded=list(md.disasm(b,a));assert sum(i.size for i in decoded)==len(b)
            for i in decoded:insns[i.address]=i;actual.append(i.address)
            chunk_bytes+=len(b)
        assert actual==expected
        chunk_instructions+=len(actual)
    checks=[]
    def exact(pc,mn,op):
        i=insns[pc];assert (i.mnemonic,i.op_str)==(mn,op),(hex(pc),i.mnemonic,i.op_str)
        checks.append({'site':hex(pc),'instruction':mn+' '+op})
    def target(pc,addr,mn='call'):
        i=insns[pc];assert i.mnemonic==mn and any((o.type==X86_OP_IMM and o.imm==addr) or (o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and i.address+i.size+o.mem.disp==addr) for o in i.operands),(hex(pc),i.mnemonic,i.op_str,hex(addr))
        checks.append({'site':hex(pc),'target':hex(addr),'instruction':i.mnemonic+' '+i.op_str})
    target(0x1405669ce,0x14057bbf0,'jmp');target(0x1404393dd,0x1404391d8,'jmp');target(0x1404392d9,0x140143720)
    target(0x140143739,0x14062ba70);assert struct.unpack('<Q',at(0x14062ba70,8))[0]==0x14014f1e0
    target(0x14014f4a7,0x140105420)
    target(0x14014f215,0x1405b1190,'lea');target(0x140579bfa,0x140747c60,'jmp');target(0x140579bca,0x140747c30,'jmp')
    target(0x14011d098,0x14011d0a0,'jmp');target(0x140127ed4,0x140121d90);target(0x140127ed9,0x140579bc0)
    target(0x140129114,0x1401287d0);exact(0x140121f06,'call','qword ptr [rax + 0x20]')
    target(0x14014ecd9,0x14014fc20);exact(0x140121f52,'call','qword ptr [rax + 0x28]')
    vt=struct.unpack('<8Q',at(0x1405b1190,64));assert vt==(0x14014dd30,0x14014ed40,0x14014e9f0,0x14014eff0,0x14014eb70,0x14014eb00,0x14014eeb0,0x14014f010)
    # Incoming reference instructions and data are independently decoded. Unwind table entries are metadata, not callers.
    pe=struct.unpack_from('<I',raw,0x3c)[0];opt=pe+24
    er,es=struct.unpack_from('<II',raw,opt+136)
    unwind={0x140000000+er+n:struct.unpack('<3I',at(0x140000000+er+n,12)) for n in range(0,es,12)}
    spans={int(x['addr'],16):x for x in ev['data']};refs=[]
    for group in ev['xrefs']+ev['globalXrefs']:
        assert not group['more'] and group['xref_count']==len(group['xrefs'])
        dest=int(group['addr'],16)
        for x in group['xrefs']:
            pc=int(x['addr'],16);b=base.octets(spans[pc]['originalBytes']);kind=x['type']
            assert base.octets(spans[pc]['idaBytes'])==b
            if x['fn']:
                i=next(md.disasm(b,pc,count=1),None);assert i
                direct=any((o.type==X86_OP_IMM and o.imm==dest) or (o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and pc+i.size+o.mem.disp==dest) for o in i.operands)
                if not direct:
                    slots=[pc+i.size+o.mem.disp for o in i.operands if o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP]
                    assert i.mnemonic in ('call','jmp') and any(struct.unpack('<Q',at(a,8))[0]==dest for a in slots),('xref',hex(pc),i.mnemonic,i.op_str,hex(dest))
                    kind='indirect through original file pointer (not proof of immutable live binding)'
            elif pc in unwind and dest-0x140000000 in unwind[pc][:2]:
                kind='RUNTIME_FUNCTION.'+('BeginAddress' if unwind[pc][0]+0x140000000==dest else 'EndAddress')
            elif pc==0x14070e348 and dest==0x14014f1e0:
                assert struct.unpack_from('<I',b,32)[0]+0x140000000==dest
                kind='RVA array element at70E368, IDA item-head xref at70E348; not a caller'
            else:
                if int.from_bytes(b[:8],'little')!=dest and int.from_bytes(b[:4],'little')+0x140000000!=dest:
                    i=next(md.disasm(b,pc,count=1),None)
                    assert i and any(o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and pc+i.size+o.mem.disp==dest for o in i.operands),('unowned xref',hex(pc),hex(dest))
                    kind='unassigned native instruction with exact RIP target; no owning-function or thread claim'
            refs.append({'source':hex(pc),'target':hex(dest),'kind':kind})
    def cstring(addr):
        out=bytearray()
        while len(out)<1024:
            c=at(addr+len(out),1)[0]
            if not c:return out.decode('ascii')
            out.append(c)
        raise ValueError('unterminated PE string')
    imports={};desc=0x140000000+struct.unpack_from('<I',raw,opt+120)[0]
    while True:
        oft,stamp,forward,name,ft=struct.unpack('<5I',at(desc,20))
        if not any((oft,stamp,forward,name,ft)):break
        dll=cstring(0x140000000+name);n=0
        while True:
            t=struct.unpack('<Q',at(0x140000000+(oft or ft)+8*n,8))[0]
            if not t:break
            if not t&(1<<63): imports[0x140000000+ft+8*n]={'addr':hex(0x140000000+ft+8*n),'dll':dll,'name':cstring(0x140000000+t+2),'originalThunk':hex(t)}
            n+=1
        desc+=20
    assert all(imports[int(i['addr'],16)]==i for i in ev['imports'])
    begin=next(a for a,i in imports.items() if i['name']=='_beginthreadex')
    for site in (0x14011d341,0x14011d37e):target(site,begin)
    target(0x14011d32a,0x140127ed0,'lea');target(0x14011d361,0x140129110,'lea')
    exact(0x14011d368,'mov','r9, rbx');exact(0x14011d36b,'mov','dword ptr [rsp + 0x20], 4')
    exact(0x140127eb9,'mov','byte ptr [rax + 0x308], 1');exact(0x140125a19,'mov','byte ptr [rax + 0x308], 0')
    exact(0x140128c3d,'mov','rax, qword ptr [rbx + 0x2d8]');exact(0x140128c4d,'call','rax')
    exact(0x14011ae18,'mov','dword ptr [rbx + 0x328], 1')
    assert imports[0x14057bbf0]['name']=='_CorExeMain'
    # COR header and all fixup rows are read directly from original bytes.
    cor_rva,cor_size=struct.unpack_from('<II',raw,opt+112+14*8);cor=at(0x140000000+cor_rva,cor_size)
    assert struct.unpack_from('<II',cor,16)==(0,0x0600012a)
    assert struct.unpack_from('<I',raw,opt+16)[0]==int(clr['peEntryPointRva'],16)==0x5669ce
    fr,fs=struct.unpack_from('<II',cor,48);fixupraw=at(0x140000000+fr,fs);assert fs==len(clr['fixups'])*8
    for n,f in enumerate(clr['fixups']):
        rva,count,flags=struct.unpack_from('<IHH',fixupraw,n*8);assert (rva,count,flags)==(int(f['rva'],16),f['count'],f['flags'])
        b=at(0x140000000+rva,count*(8 if flags&2 else 4));assert b==bytes.fromhex(f['bytes'])
        assert [int(t['token'],16) for t in f['tokens']]==[struct.unpack_from('<I',b,j*(8 if flags&2 else 4))[0] for j in range(count)]
    fixes={int(f['rva'],16):f for f in clr['fixups']}
    for rva,t in ((0x747c28,0x060000aa),(0x747c30,0x060000aa),(0x747c58,0x060000bc),(0x747c60,0x060000bc)):
        assert int(fixes[rva]['tokens'][0]['token'],16)==t
    methods={m['token']:m for m in clr['methods']};ilcount=0;ilbytes=0;ilinstructions=0
    for m in clr['methods']:
        b=m['body']
        if b is None:continue
        code=bytes.fromhex(b['headerAndBodyBytes']);assert len(code)==b['size'] and at(0x140000000+int(m['rva'],16),len(code))==code
        il=bytes.fromhex(b['ilBytes']);assert b''.join(bytes.fromhex(i['bytes']) for i in b['instructions'])==il
        if code[0]&3==2:header=1;assert code[0]>>2==len(il)
        else:header=(struct.unpack_from('<H',code)[0]>>12)*4;assert struct.unpack_from('<I',code,4)[0]==len(il)
        assert code[header:header+len(il)]==il
        offsets={i['offset'] for i in b['instructions']};position=0
        for i in b['instructions']:
            assert int(i['offset'][3:],16)==position;position+=len(bytes.fromhex(i['bytes']))
            targets=[i['operand']] if isinstance(i['operand'],str) and i['operand'].startswith('IL_') else i['operand'] if i['op']=='switch' else []
            assert all(t in offsets for t in targets),(m['token'],i)
        ilcount+=1;ilbytes+=len(il);ilinstructions+=len(b['instructions'])
    native_bindings={'0x0600012A':0x4393d0,'0x060001B2':0x11d070,'0x060001B4':0x11ad80,'0x060001AB':0x125a10}
    for token,rva in native_bindings.items():assert int(methods[token]['rva'],16)==rva and methods[token]['body'] is None
    cilchecks=[]
    def cil(token,offset,op,callee):
        i=next(i for i in methods[token]['body']['instructions'] if i['offset']==offset)
        assert i['op']==op and i['operand']['token']==callee,(token,offset,i)
        cilchecks.append({'method':token,'offset':offset,'op':op,'callee':callee})
    cil('0x060000BC','IL_0011','call','0x06000209');cil('0x060000BC','IL_0016','call','0x0A0000A8')
    cil('0x06000209','IL_0009','newobj','0x06000205');cil('0x0600020F','IL_0015','call','0x060001B2')
    cil('0x060000AA','IL_0000','call','0x0600020A');cil('0x0600020A','IL_0036','call','0x0A0000B1')
    cil('0x06000214','IL_0069','call','0x060001B4')
    result.update(evidenceSha256=hashlib.sha256((HERE/'evidence.json').read_bytes()).hexdigest(),clrEvidenceSha256=hashlib.sha256((HERE/'clr-evidence.json').read_bytes()).hexdigest(),incomingXrefs=len(refs),xrefDetails=refs,imports=ev['imports'],nativeChecks=checks,clrChecks=cilchecks,clrMethodDefinitions=len(methods),clrILBodies=ilcount,clrILBytes=ilbytes,clrILInstructions=ilinstructions,clrFixupGroups=len(fixes),scope='Static bytes, full native pagination, independent x86 decoding, incoming xrefs, imports, COR fixup rows, IL body bytes/instruction coverage/branch bounds and selected control-flow edges. --rebuild-clr also reproduces metadata names and tokens with the read-only .NET parser. No target execution, runtime scheduling, whole-program ownership or failure-path recovery proof.')
    result.update(chunkedFunctions=2,chunkedInstructions=chunk_instructions,originalChunkBytes=chunk_bytes,allNativeFunctions=31,allNativeInstructions=result['instructions']+chunk_instructions,allNativeBytes=result['originalFunctionBytes']+chunk_bytes,padding=gaps)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['success','functions','instructions','originalFunctionBytes','dataSpans','originalDataBytes','incomingXrefs','clrMethodDefinitions','clrILBodies','clrILBytes','clrILInstructions','clrFixupGroups']}))
if __name__=='__main__':main()
