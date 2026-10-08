"""Verify bounded static timing callback evidence. Never runs the game or changes IDA."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, re, struct, sys
sys.dont_write_bytecode=True
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('retail',HERE.parent/'actor-scale-contract-20261007/verify.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,default=HERE/'verification.json');ap.add_argument('--check',action='store_true');args=ap.parse_args()
    ev=json.loads((HERE/'evidence.json').read_text());raw=base.DEFAULT_EXE.read_bytes();at=base.original_reader(raw,0x140000000)
    result=base.validate(ev,raw);md=Cs(CS_ARCH_X86,CS_MODE_64);md.detail=True;insns={};padding=[];embedded=[]
    for dep in ev['dependencies']:assert hashlib.sha256((HERE/dep['path']).read_bytes()).hexdigest()==dep['sha256']
    for f in ev['functions']:
        assert f['pseudocode']['cursor']['done'] and not f['pseudocode'].get('truncated',False)
        b=base.octets(f['originalBytes']);assert b==base.octets(f['idaBytes']);start=int(f['addr'],16);rows=f['asm']['lines']
        for n,row in enumerate(rows):
            pc=int(row['addr'],16);i=next(md.disasm(b[pc-start:],pc,count=1));insns[pc]=i
            end=int(rows[n+1]['addr'],16) if n+1<len(rows) else start+len(b)
            if i.address+i.size!=end:
                gap=b[pc-start+i.size:end-start]
                if (i.address+i.size,end)==(0x1403aad8c,0x1403aae10):
                    assert struct.unpack('<3I',gap[:12])==(0x3aad25,0x3aad36,0x3aad47)
                    assert len(gap[12:])==120 and set(gap[12:])=={0,1,2} and gap[12+74-19]==2
                    embedded.append({'addr':'0x1403aad8c','size':len(gap),'kind':'3 relative jump targets and 120 byte selectors; selector for message 74 reaches 3AAD47'})
                    continue
                assert i.address+i.size<end and gap and set(gap)=={0xcc},('gap',hex(pc),hex(end),i.mnemonic,i.op_str)
                padding.append({'after':hex(pc),'bytes':gap.hex()})
    tail=ev['sharedTail'];ta=int(tail['addr'],16);tb=base.octets(tail['originalBytes'])
    assert tb==base.octets(tail['idaBytes'])==at(ta,tail['size'])
    td=list(md.disasm(tb,ta));assert sum(i.size for i in td)==len(tb)
    tr=tail['asm'];assert tr['cursor']['done'] and tr['instruction_count']==len(tr['asm']['lines'])==12
    primary=next(f for f in ev['functions'] if f['addr']==tail['owner'])
    assert tr['asm']['lines'][:4]==primary['asm']['lines']
    assert [i.address for i in td]==[int(r['addr'],16) for r in tr['asm']['lines'][4:]]
    for i in td:insns[i.address]=i
    pe=struct.unpack_from('<I',raw,0x3c)[0];opt=pe+24;table=opt+struct.unpack_from('<H',raw,pe+20)[0]
    sections=[struct.unpack_from('<4I',raw,table+40*n+8) for n in range(struct.unpack_from('<H',raw,pe+6)[0])]
    for d in ev['initialState']:
        rva=int(d['addr'],16)-0x140000000;matched=[]
        for vs,va,rs,off in sections:
            if va<=rva and rva-va+d['size']<=max(vs,rs):
                n=min(d['size'],max(0,rs-(rva-va)));matched.append((raw[off+rva-va:off+rva-va+n]+bytes(d['size']-n),n))
        assert len(matched)==1 and matched[0]==(base.octets(d['originalImageBytes']),d['fileBackedBytes'])
        assert matched[0][0]==base.octets(d['idaBytes'])
    def string(addr):
        b=bytearray()
        while len(b)<1024:
            c=at(addr+len(b),1)[0]
            if not c:return b.decode('ascii')
            b.append(c)
        raise AssertionError('string')
    imports={};desc=0x140000000+struct.unpack_from('<I',raw,opt+120)[0]
    while True:
        oft,stamp,forward,name,ft=struct.unpack('<5I',at(desc,20))
        if not any((oft,stamp,forward,name,ft)):break
        dll=string(0x140000000+name);n=0
        while True:
            t=struct.unpack('<Q',at(0x140000000+(oft or ft)+8*n,8))[0]
            if not t:break
            if not t&(1<<63):imports[0x140000000+ft+8*n]={'addr':hex(0x140000000+ft+8*n),'dll':dll,'name':string(0x140000000+t+2),'originalThunk':hex(t)}
            n+=1
        desc+=20
    assert all(imports[int(x['addr'],16)]==x for x in ev['imports'])
    checks=[]
    def exact(pc,mn,op):
        i=insns[pc];assert (i.mnemonic,i.op_str)==(mn,op),(hex(pc),i.mnemonic,i.op_str)
        checks.append({'site':hex(pc),'instruction':mn+' '+op})
    def target(pc,dest,mn='call'):
        i=insns[pc];assert i.mnemonic==mn and any((o.type==X86_OP_IMM and o.imm==dest) or (o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and pc+i.size+o.mem.disp==dest) for o in i.operands),(hex(pc),i.mnemonic,i.op_str,hex(dest))
        checks.append({'site':hex(pc),'target':hex(dest),'instruction':i.mnemonic+' '+i.op_str})
    target(0x140127109,0x14011c150);exact(0x140127111,'mov','rax, qword ptr [rax + 0x2d8]');exact(0x140127118,'mov','qword ptr [rdx + 0x2d8], rbx')
    target(0x14015ef60,0x140127100,'jmp');target(0x14015448e,0x140154700,'lea');target(0x140154495,0x14015ef60);target(0x14015449a,0x14015ed70)
    target(0x1401532a4,0x140154440);target(0x14014edbf,0x1401532a0)
    target(0x140154704,0x1401574e0);target(0x140154709,0x1401570f0);target(0x14015472a,0x14015edb0);exact(0x14015472f,'xor','eax, eax')
    target(0x140154716,0x140abac00,'mov');target(0x140154724,0x140abac04,'mov');target(0x1401574e4,0x140152380)
    target(0x140152380,0x1409a98b0,'lea');exact(0x140157504,'cmp','ecx, 0xcdfe5c4');exact(0x14015751a,'mov','dword ptr [r8 + 0x2444], eax')
    exact(0x140157525,'mov','dword ptr [r8 + 0x2448], eax');exact(0x14015754d,'cmp','eax, 0x13');exact(0x140157581,'mov','dword ptr [r8 + rax*4 + 0x244c], edx')
    target(0x140157535,0x140717008,'movzx');target(0x14015752c,0x140716884,'cmp')
    target(0x14015ed7b,0x1400fd9c0);target(0x14015ed80,0x140abc610,'mov');target(0x14015edb0,0x140abc610,'mov');target(0x14015edba,0x1400fdb10,'jne')
    target(0x1400fdb21,0x14057b358,'jmp');target(0x1400fd9f4,0x14057b3e8);target(0x14015ee26,0x1400fdd90);target(0x1400fdda5,0x14057b340)
    target(0x140157097,0x1401571b0,'lea');target(0x1401570be,0x14014f770,'jmp');target(0x140157207,0x1403aabe0,'jmp');target(0x1403aad76,0x1403b4270)
    exact(0x1403b42a8,'call','qword ptr [r10 + 0x60]')
    target(0x140129114,0x1401287d0);target(0x14011d32a,0x140127ed0,'lea');target(0x14011d361,0x140129110,'lea')
    begin=next(a for a,i in imports.items() if i['name']=='_beginthreadex')
    target(0x14011d341,begin);target(0x14011d37e,begin);exact(0x14011d36b,'mov','dword ptr [rsp + 0x20], 4')
    exact(0x140128c3d,'mov','rax, qword ptr [rbx + 0x2d8]');exact(0x140128c4b,'xor','ecx, ecx');exact(0x140128c4d,'call','rax')
    exact(0x140128e01,'movzx','eax, byte ptr [rbx + 0x308]');exact(0x14011ae18,'mov','dword ptr [rbx + 0x328], 1')
    exact(0x14010a25b,'mov','qword ptr [rcx + 0x2d0], rax');exact(0x14010a294,'add','rcx, 8');target(0x14010a298,0x140109f50)
    exact(0x14010a2b1,'mov','dword ptr [rbx + 0x2f8], 0xffffffff')
    # The only outgoing control transfers in the complete immediate callback closure are internal branches and this fixed Win32 import.
    closure={0x140154700,0x1401574e0,0x140152380,0x1401570f0,0x14015edb0}
    closure_ins=[insns[int(r['addr'],16)] for f in ev['functions'] if int(f['addr'],16) in closure for r in f['asm']['lines']]+td
    closure_addresses={i.address for i in closure_ins};edges=[]
    for i in closure_ins:
        if i.mnemonic=='call' or i.mnemonic.startswith('j'):
            if i.operands[0].type==X86_OP_IMM:
                d=i.operands[0].imm;assert d in closure_addresses
            else:
                o=i.operands[0];assert o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP;d=i.address+i.size+o.mem.disp
                assert i.address==0x1400fdb21 and imports[d]['name']=='ReleaseSemaphore'
            edges.append({'from':hex(i.address),'to':hex(d),'kind':i.mnemonic})
    spans={int(d['addr'],16):d for d in ev['data']};xrefs=[];unresolved=[]
    er,es=struct.unpack_from('<II',raw,opt+136);unwind={0x140000000+er+n:struct.unpack('<3I',at(0x140000000+er+n,12)) for n in range(0,es,12)}
    for group in ev['xrefs']+ev['globalXrefs']:
        assert group['xref_count']==len(group['xrefs']) and not group['more'];dest=int(group['addr'],16)
        for x in group['xrefs']:
            a=int(x['addr'],16);b=base.octets(spans[a]['originalBytes']);assert b==base.octets(spans[a]['idaBytes'])
            kind=None;i=next(md.disasm(b,a,count=1),None)
            if i and any((o.type==X86_OP_IMM and o.imm==dest) or (o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and a+i.size+o.mem.disp==dest) for o in i.operands):kind='original instruction target'
            elif a in unwind and dest-0x140000000 in unwind[a][:2]:kind='RUNTIME_FUNCTION metadata (not call)'
            elif int.from_bytes(b[:8],'little')==dest or int.from_bytes(b[:4],'little')+0x140000000==dest:kind='original pointer/RVA data'
            else:unresolved.append({'source':hex(a),'target':hex(dest),'type':x['type']})
            xrefs.append({'source':hex(a),'target':hex(dest),'classification':kind or 'snapshot only; no direct-target proof'})
    # Offset searches are finite IDA listing snapshots, not alias analysis or a completeness proof for writers.
    searchhits=0
    for page in ev['offsetSearch']:
        assert page['cursor']['done'] and page['n']==len(page['hits']);searchhits+=page['n']
        for hit in page['hits']:
            a=int(hit['addr'],16);i=next(md.disasm(base.octets(spans[a]['originalBytes']),a,count=1))
            assert any(o.type==X86_OP_MEM and o.mem.disp in (0x2d0,0x2d8) for o in i.operands)
    result.update(evidenceSha256=hashlib.sha256((HERE/'evidence.json').read_bytes()).hexdigest(),freshFunctions=32,reusedFunctions=9,sharedTailInstructions=len(td),sharedTailBytes=len(tb),allInstructions=result['instructions']+len(td),allCodeBytes=result['originalFunctionBytes']+len(tb),padding=padding,checks=checks,imports=ev['imports'],callbackClosureEdges=edges,incomingReferences=len(xrefs),xrefDetails=xrefs,xrefSnapshotsWithoutDirectTargetProof=unresolved,offsetSearchHits=searchhits,initialStateSpans=len(ev['initialState']),scope='Static full saved primary-function ASM pagination, shared callback tail, original retail bytes, selected semantic anchors, imports and complete immediate callback closure. Frozen App bodies are reused with a pinned source hash. No target execution, callback ownership, alias-complete writer census, runtime scheduling, or whole-program Actor/STATUS ownership proof.')
    result.update(embeddedData=embedded,embeddedDataBytes=sum(x['size'] for x in embedded),machineInstructionBytes=sum(i.size for i in insns.values()))
    if (HERE/'claims.json').exists():
        claims=json.loads((HERE/'claims.json').read_text())['claims'];references=0
        for c in claims:
            assert c['addr'].lower() in {f['addr'].lower() for f in ev['functions']} and c['Finding']
            for ref in c['Evidence']:
                path,_,fragment=ref.partition('#');obj=json.loads((HERE/path).read_text())
                if fragment:
                    match=re.fullmatch(r'functions\[addr=(0x[0-9a-fA-F]+)\]',fragment)
                    assert match and any(f['addr'].lower()==match[1].lower() for f in obj['functions']),ref
                references+=1
        result.update(claims=len(claims),claimReferences=references)
    if args.check:
        assert json.loads(args.output.read_text())==result,'verification receipt differs'
        if (HERE/'manifest.json').exists():
            m=json.loads((HERE/'manifest.json').read_text())
            for f in m['files']:
                b=(HERE/f['file']).read_bytes();assert len(b)==f['bytes'] and hashlib.sha256(b).hexdigest()==f['sha256'],f['file']
    else:args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('success','functions','freshFunctions','reusedFunctions','allInstructions','allCodeBytes','incomingReferences','offsetSearchHits')}))
    if unresolved:print('Reference snapshots without exact-target classification: '+json.dumps(unresolved))
if __name__=='__main__':main()
