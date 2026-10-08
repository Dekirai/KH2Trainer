"""Original-PE verifier for bounded native allocator ownership evidence.
No game/process access. Capstone independently decodes every captured instruction.
"""
from pathlib import Path
import argparse, hashlib, json, struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=0x140000000
EXPECTED='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
def sha(b): return hashlib.sha256(b).hexdigest()
def octets(s): return bytes(int(x,16) for x in s.split())
def reader(raw):
    assert raw[:2]==b'MZ'
    pe=struct.unpack_from('<I',raw,0x3c)[0]
    assert raw[pe:pe+4]==b'PE\0\0'
    assert struct.unpack_from('<H',raw,pe+4)[0]==0x8664
    opt=pe+24
    assert struct.unpack_from('<H',raw,opt)[0]==0x20b
    assert struct.unpack_from('<Q',raw,opt+24)[0]==BASE
    table=opt+struct.unpack_from('<H',raw,pe+20)[0]
    sections=[struct.unpack_from('<4I',raw,table+40*i+8) for i in range(struct.unpack_from('<H',raw,pe+6)[0])]
    def at(addr,size):
        rva=addr-BASE
        matches=[raw[offset+rva-va:offset+rva-va+size] for _,va,extent,offset in sections if va<=rva and rva-va+size<=extent]
        assert len(matches)==1 and len(matches[0])==size,(hex(addr),size)
        return matches[0]
    return at,opt
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    source=(HERE/'evidence.json').read_bytes(); ev=json.loads(source)
    raw=Path(ev['originalPath']).read_bytes()
    assert sha(raw)==ev['originalSha256']==EXPECTED
    at,opt=reader(raw);md=Cs(CS_ARCH_X86,CS_MODE_64);md.detail=True
    decoded={}; all_xrefs=[]; source_rows=[]; pc_map={}
    def body(f,fresh):
        start=int(f['addr'],16);b=octets(f['originalBytes'])
        declared=f['analysis']['size']; declared=int(declared,16) if isinstance(declared,str) else declared
        assert len(b)==f['size']==declared and b==at(start,len(b)),f['addr']
        pages=f['pages']; rows=f['asm']['lines']
        assert pages and pages[-1]['cursor'].get('done')
        assert not any(p.get('error') or p['cursor'].get('cancelled') for p in pages)
        assert [r for p in pages for r in p['asm']['lines']]==rows
        assert len(rows)==f['instruction_count']==f['total_instructions']
        offset=0
        for p in pages:
            if 'offset' in p: assert p['offset']==offset
            offset+=len(p['asm']['lines'])
            assert p['total_instructions']==len(rows)
            if not p['cursor'].get('done'):assert p['cursor']['next']==offset
        full=list(md.disasm(b,start))
        assert sum(i.size for i in full)==len(b),(f['addr'],'undecoded span')
        padding={0x1401513DC:'nop',0x140151E2D:'int3',0x140150DAA:'nop'}
        skipped=[i for i in full if i.address in padding]
        for i in skipped:assert i.mnemonic==padding[i.address]
        ins=[i for i in full if i.address not in padding]
        assert [i.address for i in ins]==[int(r['addr'],16) for r in rows],f['addr']
        for i,row in zip(ins,rows):
            if i.mnemonic=='call' or i.mnemonic.startswith('j'):
                if i.operands[0].type==X86_OP_IMM:
                    assert i.operands[0].imm in [int(r['addr'],16) for r in row.get('refs',[])],hex(i.address)
        pseudocode=f.get('pc',f.get('pseudocode'))
        if pseudocode:
            assert pseudocode.get('cursor',{}).get('done') and not pseudocode.get('truncated')
        assert start not in decoded
        decoded[start]=ins
        for i in ins: assert i.address not in pc_map;pc_map[i.address]=i
        if fresh:
            group=f['xrefs']['result'][0];all_xrefs.append(group)
        return {'addr':f['addr'],'size':len(b),'instructions':len(ins),'padding':[{'addr':hex(i.address),'bytes':bytes(i.bytes).hex(),'mnemonic':i.mnemonic} for i in skipped],'freshCapture':fresh,'completeDecodedBody':True,'originalBytesEqual':True}
    fresh=[body(f,True) for f in ev['functions']]
    reused=[]
    for item in ev['reusedEvidence']:
        oldraw=(ROOT/item['path']).read_bytes();old=json.loads(oldraw)
        assert old['originalSha256']==EXPECTED
        oldmap={f['addr'].lower():f for f in old['functions']}
        reused += [body(oldmap[a.lower()],False) for a in item['functionAddresses']]
        source_rows.append({'path':item['path'],'sha256':sha(oldraw)})
    all_xrefs+=ev['globalXrefs']['result']
    pdata_rva,pdata_size=struct.unpack_from('<II',raw,opt+112+24)
    xrefs={'instructionReference':0,'staticData':0,'runtimeFunctionEndBoundary':0,'unownedInstructionReference':0}
    for g in all_xrefs:
        assert not g.get('more') and len(g['xrefs'])==g['xref_count'],g['addr']
        target=int(g['addr'],16)
        for x in g['xrefs']:
            pc=int(x['addr'],16)
            if x['type']=='code' or x.get('fn'):
                i=next(md.disasm(at(pc,15),pc,count=1))
                refs=[o.imm for o in i.operands if o.type==X86_OP_IMM]
                refs += [pc+i.size+o.mem.disp for o in i.operands if o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP]
                assert target in refs,(g['addr'],x,i.mnemonic,i.op_str)
                if x['type']=='code':assert i.mnemonic=='call' or i.mnemonic.startswith('j')
                xrefs['instructionReference']+=1
            else:
                b=at(pc,12);q=struct.unpack_from('<Q',b)[0];ds=struct.unpack('<III',b)
                if q==target or ds[0]==target-BASE:xrefs['staticData']+=1
                elif BASE+pdata_rva<=pc<BASE+pdata_rva+pdata_size and (pc-BASE-pdata_rva)%12==0 and ds[0]<ds[1]==target-BASE:
                    xrefs['runtimeFunctionEndBoundary']+=1
                else:
                    i=next(md.disasm(at(pc,15),pc,count=1))
                    assert any(o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and pc+i.size+o.mem.disp==target for o in i.operands),(g['addr'],x)
                    xrefs['unownedInstructionReference']+=1
    for d in ev['data']:assert octets(d['data'])==at(int(d['addr'],16),d['size'])
    # This is a primary TASK_MANAGER table, not the embedded MemoryAllocator table.
    assert struct.unpack('<4Q',at(0x1405B13E8,32))==(0x14014F590,0x14014F740,0x14014FC30,0x14014FC50)
    def cstring(addr):
        result=bytearray()
        for n in range(4096):
            c=at(addr+n,1)[0]
            if not c:return result.decode('ascii')
            result.append(c)
        raise AssertionError('unterminated import')
    imports={}; descriptor=BASE+struct.unpack_from('<I',raw,opt+120)[0]
    while True:
        oft,stamp,forward,name,ft=struct.unpack('<5I',at(descriptor,20))
        if not any((oft,stamp,forward,name,ft)):break
        index=0
        while True:
            thunk=struct.unpack('<Q',at(BASE+(oft or ft)+8*index,8))[0]
            if not thunk:break
            imports[BASE+ft+8*index]={'declaringDll':cstring(BASE+name),'name':('ordinal:'+str(thunk&0xffff)) if thunk>>63 else cstring(BASE+thunk+2)}
            index+=1
        descriptor+=20
    edges=[]
    for owner,ins in decoded.items():
        for i in ins:
            if i.mnemonic not in ('call','jmp'):continue
            op=i.operands[0]
            if op.type==X86_OP_IMM:
                target=op.imm
                kind='capturedBody' if target in decoded else ('localBranch' if any(j.address==target for j in ins) else 'unexpandedDirectTarget')
                edges.append({'owner':hex(owner),'site':hex(i.address),'kind':kind,'target':hex(target)})
            elif op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
                slot=i.address+i.size+op.mem.disp
                assert slot in imports,(hex(i.address),hex(slot))
                edges.append({'owner':hex(owner),'site':hex(i.address),'kind':'externalImport','slot':hex(slot),**imports[slot]})
            else:edges.append({'owner':hex(owner),'site':hex(i.address),'kind':'dynamicTarget','operands':i.op_str})
    assert imports[0x14057B2A8]['name']=='SwitchToFiber'
    assert imports[0x14057B288]['name']=='ConvertThreadToFiber'
    assert imports[0x14057B298]['name']=='ConvertFiberToThread'
    checks=[]
    def exact(pc,mn,operands=None):
        i=pc_map[pc];assert i.mnemonic==mn,(hex(pc),i.mnemonic,mn)
        if operands is not None:assert i.op_str==operands,(hex(pc),i.op_str,operands)
        checks.append({'addr':hex(pc),'mnemonic':i.mnemonic,'operands':i.op_str})
        return i
    def call(pc,target):
        i=pc_map[pc];assert i.mnemonic in ('call','jmp') and i.operands[0].type==X86_OP_IMM and i.operands[0].imm==target,(hex(pc),hex(target))
        checks.append({'addr':hex(pc),'target':hex(target),'kind':i.mnemonic})
    for pc,target in [
        (0x14014ED63,0x14014F600),(0x14014ED6F,0x14039DC50),(0x14014F606,0x14019C3A0),
        (0x14039DC60,0x14019C3A0),(0x140150B36,0x14019C3A0),(0x140150B4E,0x14019C3A0),
        (0x140150B95,0x14019C3A0),(0x140150BAA,0x14019C3A0),(0x14038DFFF,0x140150B70),
        (0x140151D6A,0x14019C3A0),(0x140151D8B,0x14019C3A0),(0x140151DA3,0x14019C3A0),(0x140151DBB,0x14019C3A0),
        (0x140151C46,0x14039D400),(0x140151C52,0x14039D400),
        (0x140151A8A,0x14019C3A0),(0x140151AC8,0x1401E18F0),(0x1401E1504,0x1401E2060),(0x1401E15F4,0x140212290),
        (0x1402122A0,0x1401E1FA0),(0x1402122B4,0x14019C3A0),(0x140212234,0x1401E2030),
        (0x140243BF0,0x1402513E0),(0x140243BF5,0x140253CB0),(0x140253CD1,0x14019C3A0),
        (0x140243B9C,0x140253C60),(0x140243BA1,0x1402513D0),
        (0x14015246B,0x14019C3A0),(0x140152737,0x14019C3A0),(0x140152803,0x14039D400),(0x14015285C,0x14019C3A0),
        (0x1405280D4,0x140150AF0),(0x140528054,0x140150C50),(0x140528060,0x14039D400)
    ]:call(pc,target)
    for pc,mn,ops in [
        (0x14014F61B,'call','qword ptr [r9 + 8]'),(0x14014F62B,'mov','qword ptr [rax + 8], rbx'),
        (0x140150B7D,'lea','eax, [rdx - 0x68000]'),(0x140150B8A,'mov','edx, eax'),(0x140150B90,'mov','ebx, eax'),
        (0x140151D80,'mov','edx, 0x40000'),(0x140151D90,'mov','edx, 0x180000'),(0x140151DB6,'mov','edx, 0x20000'),
        (0x140151D9C,'lea','rcx, [rbx + 0x40000]'),(0x140151DA8,'lea','rcx, [rbx + 0x1c0000]'),
        (0x140253CC6,'call','qword ptr [rax + 8]'),(0x140253C91,'call','qword ptr [rax + 0x10]'),
        (0x1402530CD,'lea','eax, [r8 - 1]'),(0x1402530D4,'add','eax, r9d'),
        (0x1402530DA,'movsxd','rdx, eax'),(0x1402530EA,'lea','edx, [rbx - 1]'),
        (0x1402530F5,'mov','r8d, edx'),(0x1402530FB,'not','r8'),(0x1402530FE,'and','rdx, r8'),
        (0x140152849,'add','edi, ecx'),(0x14015284B,'add','rdi, rdi'),
        (0x14019E52E,'lea','rdx, [rax + rax*8]'),(0x14019E535,'shl','rdx, 4'),
        (0x14019E54F,'imul','rdx, rax, 0x748')
    ]:exact(pc,mn,ops)
    # An absent store is only a property of this body, not all its callbacks.
    def rip_destinations(start):
        return [i.address+i.size+i.operands[0].mem.disp for i in decoded[start]
                if i.mnemonic=='mov' and i.operands[0].type==X86_OP_MEM and i.operands[0].mem.base==X86_REG_RIP]
    assert 0x1409A8818 not in rip_destinations(0x140151C20)
    assert set([0x1409A8800,0x1409A8808,0x1409A8810]) <= set(rip_destinations(0x140151C20))
    assert 0x140AF75E8 not in rip_destinations(0x140212210)
    assert 0x140AF75E0 in rip_destinations(0x140212210)
    assert 0x1409006D0 not in [i.address+i.size+i.operands[0].mem.disp for i in decoded[0x140150AF0] if i.address<0x140150B11 and i.mnemonic=='mov' and i.operands[0].type==X86_OP_MEM and i.operands[0].mem.base==X86_REG_RIP]
    for a in (0x14019C560,0x14019C050,0x14019BFB0):
        groups=[g for g in all_xrefs if int(g['addr'],16)==a]
        assert groups and all(not any(x['type']=='code' for x in g['xrefs']) for g in groups)
    geometry={
        'staticPair':{'start':'0x140900730','firstSize':0x38000,'secondStart':hex(0x140900730+0x38000),'secondSize':0x68000,'end':hex(0x140900730+0x38000+0x68000)},
        'dynamicPair':{'total':0x100000,'firstSize':0x100000-0x68000,'secondSize':0x68000},
        'mode4Split':{'offsets':[0,0x40000,0x1c0000],'sizes':[0x40000,0x180000,0x20000],'total':sum([0x40000,0x180000,0x20000])},
        'taskManager':{'payload':72,'roundedPayload':(72+15)&~15,'allocatorBlockSize':((72+15)&~15)+48},
        'mode2Child':{'payload':0x100000,'parentCharge':0x100000+48},
        'mode4Child':{'payload':3864000,'parentCharge':((3864000+15)&~15)+48},
        'fieldBuffers256':{'recordBytes':256*(144+1864),'requestBytesWith1MiBBuffer':0x100000+256*(144+1864),'allocatorCharge':0x100000+256*(144+1864)+3*48}
    }
    assert geometry['mode4Split']['total']==0x1e0000
    assert geometry['staticPair']['secondStart']=='0x140938730'
    result={'status':'PASS','originalSha256':EXPECTED,'evidenceSha256':sha(source),
            'freshBodies':len(fresh),'freshInstructions':sum(r['instructions'] for r in fresh),'freshBodyBytes':sum(r['size'] for r in fresh),
            'reusedBodies':len(reused),'reusedInstructions':sum(r['instructions'] for r in reused),'reusedBodyBytes':sum(r['size'] for r in reused),
            'dataBytes':sum(d['size'] for d in ev['data']),'incomingReferenceInstances':xrefs,
            'referenceLimit':'Complete materialized IDA xrefs to these selected symbols, not a global indirect-call/alias census.',
            'semanticChecks':checks,'geometry':geometry,'bodies':fresh+reused,'reusedSources':source_rows,
            'callAndTailEdges':edges,'runtimeWitness':False}
    dest=HERE/'verification.json'
    if args.check:assert json.loads(dest.read_bytes())==result
    else:dest.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    files=[]
    for name in ['evidence.json','report.json','report.txt','verify.py','verification.json']:
        p=HERE/name;data=p.read_bytes()
        files.append({'path':str(p.relative_to(ROOT)).replace('\\','/'),'size':len(data),'sha256':sha(data)})
    manifest={'schemaVersion':1,'scope':'Bounded static allocator ownership evidence; no retail runtime witness','originalSha256':EXPECTED,'files':files,'reusedEvidence':source_rows}
    mp=HERE/'manifest.json'
    if args.check:assert json.loads(mp.read_bytes())==manifest
    else:mp.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['status','freshBodies','freshInstructions','freshBodyBytes','reusedBodies','dataBytes','incomingReferenceInstances']},indent=2))
if __name__=='__main__':main()
