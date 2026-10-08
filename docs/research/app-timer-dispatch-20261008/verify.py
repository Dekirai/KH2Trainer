"""Reproduce static App timer dispatch evidence from the original PE and local script bytes.
No game execution, process attach, IDA mutation, script execution or simulated native traps.
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, re, struct, sys
sys.dont_write_bytecode = True
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('retail', HERE.parent/'actor-scale-contract-20261007/verify.py')
base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def readj(path): return json.loads(path.read_text(encoding='utf-8'))
def census():
    src = HERE.parent/'bdx-inspection-20261008/loose-scan.json'
    doc = readj(src); root = Path(doc['sourceRoot']); hits = []
    for x in doc['scripts']:
        data = (root/x['asset']).read_bytes()[x['offset']:x['offset']+x['length']]
        assert hashlib.sha256(data).hexdigest() == x['scriptSha256']
        events = []; terminated = False
        for off in range(28, len(data)-7, 8):
            eid, pc = struct.unpack_from('<2i', data, off)
            if pc == 0: terminated = True; break
            if eid == 10: events.append(dict(id=eid, pc=pc, fileOffset=off))
        assert terminated
        if events:
            hits.append(dict(asset=x['asset'], name=x['name'], offset=x['offset'], length=x['length'],
                             scriptSha256=x['scriptSha256'], events=events))
    return dict(source='docs/research/bdx-inspection-20261008/loose-scan.json', sourceSha256=sha(src),
                scriptCount=len(doc['scripts']), event10Count=len(hits), events=hits,
                scope='Raw header pairs checked against all pinned local script hashes. Event table presence only, no message74 path proof; loose source equality to installed archives applies only where separately verified.')
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--output', type=Path, default=HERE/'verification.json')
    args = ap.parse_args()
    ev = readj(HERE/'evidence.json'); raw = base.DEFAULT_EXE.read_bytes()
    at = base.original_reader(raw, 0x140000000)
    result = base.validate(ev, raw)
    for dep in ev['dependencies']: assert sha(HERE/dep['path']) == dep['sha256']
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    insns = {}; padding = []; embedded = []
    for f in ev['functions']:
        assert f['pseudocode']['cursor']['done'] and not f['pseudocode'].get('truncated', False)
        start = int(f['addr'],16); data = base.octets(f['originalBytes'])
        assert data == base.octets(f['idaBytes'])
        rows = f['asm']['lines']
        for n,row in enumerate(rows):
            pc = int(row['addr'],16)
            inst = next(md.disasm(data[pc-start:], pc, count=1)); insns[pc] = inst
            end = int(rows[n+1]['addr'],16) if n+1<len(rows) else start+len(data)
            if inst.address+inst.size != end:
                gap = data[pc-start+inst.size:end-start]
                if (inst.address+inst.size,end) == (0x1403aad8c,0x1403aae10):
                    assert struct.unpack('<3I',gap[:12]) == (0x3aad25,0x3aad36,0x3aad47)
                    assert len(gap[12:]) == 120 and gap[12+74-19] == 2
                    embedded.append(dict(addr='0x1403aad8c',bytes=len(gap),kind='3 RVA jump targets and 120 byte selectors; message74 uses default target'))
                else:
                    assert inst.address+inst.size < end and gap and set(gap)=={0xcc}, (hex(pc),hex(end))
                    padding.append(dict(after=hex(pc),bytes=gap.hex()))
    checks = []
    def exact(pc,mn,op):
        i=insns[pc]; assert (i.mnemonic,i.op_str)==(mn,op),(hex(pc),i.mnemonic,i.op_str)
        checks.append(dict(site=hex(pc),instruction=mn+' '+op))
    def target(pc,dest,mn='call'):
        i=insns[pc]
        assert i.mnemonic==mn and any(
            (o.type==X86_OP_IMM and o.imm==dest) or
            (o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and pc+i.size+o.mem.disp==dest)
            for o in i.operands), (hex(pc),i.mnemonic,i.op_str,hex(dest))
        checks.append(dict(site=hex(pc),target=hex(dest),instruction=i.mnemonic+' '+i.op_str))
    target(0x140157207,0x1403aabe0,'jmp')
    target(0x1403aad76,0x1403b4270)
    target(0x1403b4285,0x1403bf4f0); exact(0x1403b4292,'mov','ecx, dword ptr [rbx]')
    target(0x1403b4294,0x1404ad270); exact(0x1403b42a8,'call','qword ptr [r10 + 0x60]')
    target(0x1403b42af,0x1403bf4f0)
    target(0x1403bf505,0x142a171c8,'mov')
    exact(0x1403bf50e,'mov','ecx, dword ptr [rbx + 0xa90]')
    exact(0x1403baa80,'test','dword ptr [rcx + 0x120], 0x10080000')
    target(0x1403b3951,0x1403bfbc0)
    exact(0x1403bfc00,'cmp','byte ptr [rbx + 0xb91], cl')
    target(0x1403bfc20,0x142a171c8,'mov'); target(0x1403bfc19,0x142a171d0,'mov')
    exact(0x1403b4c94,'mov','rcx, qword ptr [rcx + 0x5b0]')
    exact(0x1403b4c9f,'mov','dword ptr [rsp + 0x34], 0x544e4940')
    exact(0x1403b4cac,'mov','dword ptr [rsp + 0x3c], 0x544e4940')
    exact(0x1403b4cb9,'mov','r9d, 2'); exact(0x1403b4ccd,'lea','edx, [r9 + 8]')
    target(0x1403b4cd1,0x1403e1840)
    target(0x1403e186b,0x14041c690); target(0x1403e1882,0x1403e1240)
    exact(0x1403e189c,'jle','0x1403e18c9')
    target(0x1403e18ab,0x14041b320); target(0x1403e18c4,0x1403e1c80)
    target(0x1403e18ce,0x142a250b0,'mov'); target(0x1403e18d5,0x142a25048,'mov')
    target(0x1403e18dc,0x1403e1410)
    exact(0x1403e1341,'call','qword ptr [rax + 8]'); exact(0x1403e1371,'call','qword ptr [rax + 8]')
    exact(0x1403e13cf,'inc','dword ptr [rax]'); exact(0x1403e13ea,'inc','dword ptr [rax + 0x5b8]')
    exact(0x1403e14d9,'dec','dword ptr [rax + 0x5b8]'); exact(0x1403e1ced,'dec','dword ptr [rax + 0x5b8]')
    target(0x1403e1cb9,0x14041b400); target(0x1403e1440,0x14041b400)
    exact(0x1403e1491,'call','qword ptr [rax + 0x10]'); exact(0x1403e14a2,'call','qword ptr [rax + 0x10]')
    target(0x1403b452b,0x1403e1730)
    target(0x1403b4619,0x1403e1410); target(0x1403b4621,0x1403e1510)
    exact(0x1403b4626,'mov','qword ptr [rbx + 0x5b0], rsi')
    exact(0x1403b46e9,'mov','dword ptr [rbx + 0x120], eax')
    exact(0x1403bf325,'mov','ecx, dword ptr [rbx + 0xa90]')
    target(0x1403bf336,0x1403b4e80); exact(0x1403bf34b,'call','qword ptr [r8]')
    exact(0x1403bf3b5,'shr','ecx, 0x13')
    target(0x1403bf4c6,0x1403bf300); target(0x1403bf4d1,0x1403bf300,'jmp')
    target(0x1403b3d79,0x1403c07e0); target(0x1404049f8,0x140152570)
    target(0x140577820,0x1405b2e58,'lea'); target(0x140577827,0x140750300,'mov')
    target(0x140029390,0x140577820,'lea'); target(0x140439950,0x140471cbe)
    target(0x140439961,0x140471cb2)
    forwards=[]
    for addr in ev['forwarders']:
        f=next(f for f in ev['functions'] if f['addr'].lower()==addr.lower())
        instructions=[insns[int(row['addr'],16)] for row in f['asm']['lines']]
        assert [(i.mnemonic,i.op_str) for i in instructions]==[
            ('mov','eax, r8d'),('mov','rcx, rdx'),('mov','edx, eax'),('mov','r8d, r9d'),('jmp','0x1403b4c90')]
        assert f['size']==16
        forwards.append(addr)
    descriptors=[]
    binds={
      '0x14074af78':('0x1403b3200',0x1403b3924),
      '0x14074c7c8':('0x1403da940',0x1403da9e3),
      '0x14074c380':('0x1403d2da0',0x1403d2e20),
      '0x14074c468':('0x1403d5840',0x1403d58d8),
      '0x14074a518':('0x1403a7a40',0x1403a7ae0),
      '0x140750300':('0x140405030',0x14040505d),
      '0x1407523b8':('0x140415670',0x1404156a3),
      '0x14074f178':('0x1403f8010',0x1403f80b5),
      '0x140752658':('0x140419230',0x140419265)}
    # Constructor data references are checked through incoming original-operand spans below.
    for d in ev['descriptors']:
        addr=int(d['addr'],16); vt=int(d['vtable'],16); col=int(d['col'],16); td=int(d['typeDescriptor'],16)
        assert struct.unpack('<Q',at(addr,8))[0]==vt
        assert struct.unpack('<Q',at(vt+96,8))[0]==int(d['handler'],16)
        assert struct.unpack('<Q',at(vt-8,8))[0]==col
        fields=struct.unpack('<6I',at(col,24)); assert fields[0]==1 and fields[3]+0x140000000==td and fields[5]+0x140000000==col
        assert at(td+16,112).split(b'\0')[0].decode('ascii')==d['rttiName']
        g=next(g for g in ev['xrefs'] if g['addr'].lower()==d['addr'])
        ctor=binds[d['addr']][0]
        assert any(x.get('fn') and x['fn']['addr'].lower()==ctor for x in g['xrefs'])
        descriptors.append(d)
    pe=struct.unpack_from('<I',raw,0x3c)[0]; opt=pe+24
    def cstring(a):
        out=bytearray()
        while len(out)<1024:
            b=at(a+len(out),1)[0]
            if not b:return out.decode('ascii')
            out.append(b)
        raise AssertionError('unterminated import')
    imports={}; desc=0x140000000+struct.unpack_from('<I',raw,opt+120)[0]
    while True:
        oft,stamp,forward,name,ft=struct.unpack('<5I',at(desc,20))
        if not any((oft,stamp,forward,name,ft)):break
        dll=cstring(0x140000000+name); n=0
        while True:
            v=struct.unpack('<Q',at(0x140000000+(oft or ft)+8*n,8))[0]
            if not v:break
            if not v&(1<<63):imports[0x140000000+ft+8*n]=dict(dll=dll,name=cstring(0x140000000+v+2))
            n+=1
        desc+=20
    crt=[]
    assert struct.unpack('<13Q',at(0x1405b2e58,104))==(0x140471a3c,)*13
    for pc,name in [(0x140471cbe,'_crt_atexit'),(0x140471cb2,'_register_onexit_function'),(0x140471a3c,'_purecall')]:
        i=insns[pc]; o=i.operands[0]; assert o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP
        dest=pc+i.size+o.mem.disp; assert imports[dest]['name']==name
        crt.append(dict(stub=hex(pc),iat=hex(dest),**imports[dest]))
    spans={int(x['addr'],16):x for x in ev['data']}
    er,es=struct.unpack_from('<II',raw,opt+136)
    unwind={0x140000000+er+n:struct.unpack('<3I',at(0x140000000+er+n,12)) for n in range(0,es,12)}
    xr=[]; unresolved=[]; limited=[]
    for group in ev['xrefs']:
        assert group['xref_count']==len(group['xrefs'])
        if group['more']:
            assert group['addr']=='0x1404399b0' and group['queryLimit']==10 and len(group['xrefs'])==10
            limited.append(dict(addr=group['addr'],returned=10,complete=False))
        dest=int(group['addr'],16)
        for x in group['xrefs']:
            a=int(x['addr'],16); data=base.octets(spans[a]['originalBytes']); assert data==base.octets(spans[a]['idaBytes'])
            i=next(md.disasm(data,a,count=1),None); kind=None
            if i and any((o.type==X86_OP_IMM and o.imm==dest) or (o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and a+i.size+o.mem.disp==dest) for o in i.operands):kind='instruction target'
            elif a in unwind and dest-0x140000000 in unwind[a][:2]:kind='RUNTIME_FUNCTION metadata'
            elif int.from_bytes(data[:8],'little')==dest or int.from_bytes(data[:4],'little')+0x140000000==dest:kind='pointer or RVA data'
            else:unresolved.append(dict(source=hex(a),target=hex(dest),type=x['type']))
            xr.append(dict(source=hex(a),target=hex(dest),kind=kind or 'snapshot only'))
    assert census()==readj(HERE/'script-event10-census.json')
    references=0
    if (HERE/'claims.json').exists():
        for c in readj(HERE/'claims.json')['claims']:
            assert c['addr'].lower() in {f['addr'].lower() for f in ev['functions']}
            for ref in c['Evidence']:
                path,_,frag=ref.partition('#'); assert (HERE/path).is_file()
                if frag:
                    m=re.fullmatch(r'functions\[addr=(0x[0-9a-fA-F]+)\]',frag); assert m
                    assert any(f['addr'].lower()==m[1].lower() for f in readj(HERE/path)['functions'])
                references+=1
    result.update(evidenceSha256=sha(HERE/'evidence.json'), machineInstructionBytes=sum(i.size for i in insns.values()),
                  padding=padding,embeddedData=embedded, semanticChecks=checks,forwarders=forwards,
                  descriptorChains=descriptors,crtImports=crt,incomingReferences=len(xr),xrefDetails=xr,
                  xrefsWithoutDirectTargetProof=unresolved,limitedXrefSamples=limited,scriptCount=921,localScriptsWithEvent10=66,
                  claimReferences=references,scope='Bounded static original PE/IDA body and data agreement, instruction boundaries, selected semantic anchors, constructor/RTTI/slot provenance, saved incoming xref snapshots (common CRT registrar limited to10, all others complete as returned) and hash-pinned loose-script header census. No executed timer event, selected message74 BDX path, runtime thread ownership, all-type census or all-binary alias/lifetime proof.')
    if args.check:
        assert readj(args.output)==result,'verification receipt differs'
        for x in readj(HERE/'manifest.json')['files']:
            b=(HERE/x['file']).read_bytes(); assert len(b)==x['bytes'] and hashlib.sha256(b).hexdigest()==x['sha256'],x['file']
    else:args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['success','functions','instructions','originalFunctionBytes','originalDataBytes','incomingReferences','claimReferences','scriptCount','localScriptsWithEvent10']}))
    if unresolved:print('Snapshot references without direct operand proof: '+json.dumps(unresolved))
if __name__=='__main__':main()
