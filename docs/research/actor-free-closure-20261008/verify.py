"""Bounded static free/resource evidence verifier; reads no running process."""
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

# Complete IDA function spans include switch tables and intentional padding.
# Each range is byte-checked; switch destinations are separately decoded below.
NON_CODE = {
    0x1403a6a10: [(0x1403a6be6,0x1403a6c38)],
    0x1401b9890: [(0x1401b9a7b,0x1401b9a9c)],
    0x1401bcdf0: [(0x1401bdd2d,0x1401bdd2e)],
    0x1400818b0: [(0x140081a88,0x140081a89)],
    0x1401082b0: [(0x14010838e,0x14010838f),(0x140108450,0x140108451),(0x140108456,0x140108457)],
    0x1401b9aa0: [(0x1401b9b0f,0x1401b9b30)]}

def main():
    source = (HERE/'evidence.json').read_bytes()
    ev = json.loads(source)
    raw = Path(ev['originalPath']).read_bytes()
    assert sha(raw) == ev['originalSha256'] == EXPECTED_SHA
    at, opt = reader(raw)
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    decoded = {}; captures = {}; all_xrefs = []

    def body(f, fresh):
        start = int(f['addr'],16); b = octets(f['originalBytes'])
        assert len(b) == f['size'] == f['analysis']['size']
        assert b == at(start,len(b)), f['addr']
        rows = f['asm']['lines']
        assert f['cursor'].get('done') and not f['cursor'].get('next')
        assert not f['cursor'].get('cancelled')
        assert len(rows) == f['instruction_count'] == f['total_instructions']
        assert [r for p in f['pages'] for r in p['asm']['lines']] == rows
        page_offset=0
        for p in f['pages']:
            assert p['offset'] == page_offset
            page_offset += len(p['asm']['lines'])
            assert p['total_instructions'] == len(rows)
            if not p['cursor'].get('done'): assert p['cursor']['next'] == page_offset
        addresses = [int(r['addr'],16) for r in rows]
        assert addresses == sorted(set(addresses)) and addresses[0] == start
        previous=start; gaps=[]; instructions={}
        for pc,row in zip(addresses,rows):
            assert start <= pc < start+len(b) and pc >= previous
            if pc > previous:gaps.append((previous,pc))
            i=next(md.disasm(b[pc-start:],pc,count=1))
            previous=pc+i.size
            assert previous<=start+len(b)
            instructions[pc]=i
            # Direct control-flow references in the ASM must agree with PE bytes.
            if (i.mnemonic=='call' or i.mnemonic.startswith('j')) and i.operands[0].type==X86_OP_IMM:
                assert i.operands[0].imm in [int(r['addr'],16) for r in row.get('refs',[])], (hex(pc),row)
        if previous<start+len(b):gaps.append((previous,start+len(b)))
        assert gaps==NON_CODE.get(start,[]),(f['addr'],gaps)
        decoded[start]=instructions; captures[start]=f
        if fresh: all_xrefs.append((f['addr'],f['xrefs']['result'][0]))
        if f.get('pc',{}).get('pages'):
            pp=f['pc']['pages']
            assert sum(p['line_count'] for p in pp)==f['pc']['total_lines']
            assert pp[-1]['cursor']['done']
            assert f['pc']['code']=='\n'.join(p['code'] for p in pp)
        return {'addr':f['addr'],'size':len(b),'instructions':len(rows),
                'codeBytes':sum(i.size for i in instructions.values()),
                'nonCodeRanges':[{'addr':hex(a),'size':z-a,'bytes':at(a,z-a).hex()} for a,z in gaps],
                'originalBytesEqual':True,'allCapturedInstructionRowsDecoded':True,'freshCapture':fresh}

    fresh=[body(f,True) for f in ev['functions']]
    assert len(fresh)==len({f['addr'] for f in fresh})
    reused=[]; reused_sources=[]
    for item in ev['reusedEvidence']:
        content=(ROOT/item['path']).read_bytes(); old=json.loads(content)
        assert old['originalSha256']==EXPECTED_SHA
        records={f['addr'].lower():f for f in old['functions']}
        for addr in item['functionAddresses']:reused.append(body(records[addr.lower()],False))
        reused_sources.append({'path':item['path'],'sha256':sha(content)})
    for group in ev['globalXrefs']['result']:all_xrefs.append((group['addr'],group))
    export_rva=struct.unpack_from('<I',raw,opt+112)[0]
    export_header=struct.unpack('<IIHHIIIIIII',at(BASE+export_rva,40))
    eat=BASE+export_header[8]; export_count=export_header[6]
    pdata_rva,pdata_size=struct.unpack_from('<II',raw,opt+112+3*8)
    xrefs={'directCode':0,'resolvedStaticIndirectCode':0,'functionDataReference':0,'staticData':0,
           'exportArrayReference':0,'runtimeFunctionEndBoundary':0,'unownedInstructionReference':0}
    incomplete=[]; resolved_item_xrefs=[]
    for target_text,group in all_xrefs:
        target=int(target_text,16)
        if group['more']:
            assert group['xref_count']>=len(group['xrefs'])
            incomplete.append({'addr':target_text,'captured':len(group['xrefs']),'reported':group['xref_count'],'reason':'IDA cap/output clipping; only materialized sites count as evidence'})
        else:assert group['xref_count']==len(group['xrefs'])
        for x in group['xrefs']:
            pc=int(x['addr'],16)
            if x['type']=='code' or x['fn']:
                i=next(md.disasm(at(pc,15),pc,count=1)); refs=[]
                for op in i.operands:
                    if op.type==X86_OP_IMM:refs.append(op.imm)
                    elif op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:refs.append(pc+i.size+op.mem.disp)
                direct=target in refs
                static_indirect=False
                if not direct and (i.mnemonic=='call' or i.mnemonic=='jmp') and i.operands[0].type==X86_OP_MEM:
                    static_indirect=any(struct.unpack('<Q',at(ref,8))[0]==target for ref in refs)
                assert direct or static_indirect,(target_text,x,i.mnemonic,i.op_str)
                if x['type']=='code':
                    assert i.mnemonic=='call' or i.mnemonic.startswith('j')
                    xrefs['resolvedStaticIndirectCode' if static_indirect else 'directCode']+=1
                else:xrefs['functionDataReference']+=1
            else:
                b=at(pc,8)
                if struct.unpack('<Q',b)[0]==target or struct.unpack('<I',b[:4])[0]==target-BASE:
                    xrefs['staticData']+=1
                elif pc==eat and target-BASE in struct.unpack('<'+str(export_count)+'I',at(eat,export_count*4)):
                    entries=struct.unpack('<'+str(export_count)+'I',at(eat,export_count*4))
                    resolved_item_xrefs.append({'target':target_text,'addr':hex(pc),'kind':'PE export array item-head reference',
                                                'targetCells':[hex(eat+4*n) for n,v in enumerate(entries) if v==target-BASE]})
                    xrefs['exportArrayReference']+=1
                elif BASE+pdata_rva<=pc<BASE+pdata_rva+pdata_size and (pc-BASE-pdata_rva)%12==0 and struct.unpack_from('<I',b,4)[0]==target-BASE:
                    resolved_item_xrefs.append({'target':target_text,'addr':hex(pc),'kind':'PE runtime-function EndAddress; not a caller'})
                    xrefs['runtimeFunctionEndBoundary']+=1
                else:
                    i=next(md.disasm(at(pc,15),pc,count=1))
                    assert i.mnemonic=='lea' and any(op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP and pc+i.size+op.mem.disp==target for op in i.operands),(target_text,x)
                    resolved_item_xrefs.append({'target':target_text,'addr':hex(pc),'kind':'RIP-relative LEA outside an IDA-owned function; not a call'})
                    xrefs['unownedInstructionReference']+=1
    for d in ev['data']:assert octets(d['data'])==at(int(d['addr'],16),d['size'])

    def instruction(pc,mnemonic=None,operands=None):
        found=[items[pc] for items in decoded.values() if pc in items]
        assert len(found)==1,hex(pc)
        i=found[0]
        if mnemonic:assert i.mnemonic==mnemonic,(hex(pc),i.mnemonic,mnemonic)
        if operands is not None:assert i.op_str==operands,(hex(pc),i.op_str,operands)
        return i
    def call(pc,target):
        i=instruction(pc,'call');assert i.operands[0].type==X86_OP_IMM and i.operands[0].imm==target
    # Verify every switch target from the original tables, independent of IDA comments.
    switches=[]
    for owner,site,table,count in [(0x1403a6a10,0x1403a6ae3,0x1403a6be8,8),
                                   (0x1401b9890,0x1401b99b6,0x1401b9a7c,8),
                                   (0x1401b9aa0,0x1401b9ac6,0x1401b9b10,8)]:
        values=struct.unpack('<'+str(count)+'I',at(table,4*count))
        targets=[BASE+v for v in values]
        assert all(t in decoded[owner] for t in targets)
        row=next(r for r in captures[owner]['asm']['lines'] if int(r['addr'],16)==site)
        assert set(targets)=={int(r['addr'],16) for r in row['refs']}
        switches.append({'addr':hex(site),'table':hex(table),'targets':[hex(t) for t in targets]})
    assert all(v<8 for v in at(0x1403a6c08,48))
    assert at(0x1403a6be6,2)==b'\x66\x90'
    for owner,gaps in NON_CODE.items():
        if owner in (0x1403a6a10,0x1401b9890,0x1401b9aa0):continue
        for a,z in gaps:assert at(a,z-a)==b'\xcc'*(z-a)

    def cstring(addr):
        b=bytearray()
        for n in range(2048):
            c=at(addr+n,1)[0]
            if not c:return b.decode('ascii')
            b.append(c)
        raise AssertionError('unterminated import')
    imports={}; descriptor=BASE+struct.unpack_from('<I',raw,opt+120)[0]
    while True:
        oft,stamp,forward,name,ft=struct.unpack('<5I',at(descriptor,20))
        if not any((oft,stamp,forward,name,ft)):break
        index=0
        while True:
            value=struct.unpack('<Q',at(BASE+(oft or ft)+8*index,8))[0]
            if not value:break
            if not value&(1<<63):imports[BASE+ft+8*index]={'declaringDll':cstring(BASE+name),'name':cstring(BASE+value+2)}
            index+=1
        descriptor+=20
    imported_sites=[]; direct_frontier=[]; indirect_sites=[]
    for owner,items in decoded.items():
        for pc,i in items.items():
            if not (i.mnemonic=='call' or i.mnemonic=='jmp'):continue
            op=i.operands[0]
            if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP and pc+i.size+op.mem.disp in imports:
                slot=pc+i.size+op.mem.disp
                imported_sites.append({'addr':hex(pc),'owner':hex(owner),'iatSlot':hex(slot),**imports[slot]})
            elif op.type==X86_OP_IMM:
                if op.imm not in decoded and op.imm not in items:
                    direct_frontier.append({'addr':hex(pc),'owner':hex(owner),'target':hex(op.imm)})
            else:indirect_sites.append({'addr':hex(pc),'owner':hex(owner),'instruction':i.mnemonic+' '+i.op_str})
    for pc,name in [(0x1400fdda5,'WaitForSingleObject'),(0x1400fdc9b,'ReleaseSemaphore'),
                    (0x140119b46,'EnterCriticalSection'),(0x140119b85,'LeaveCriticalSection'),
                    (0x1401239ae,'EnterCriticalSection')]:
        assert any(i['addr']==hex(pc) and i['name']==name for i in imported_sites),(hex(pc),name)
    instruction(0x14012cf16,'mov','dword ptr [r15 + 0x64c], 0xffffffff')
    instruction(0x1400fdd99,'lock inc','dword ptr [rcx]')
    instruction(0x1400fdda0,'mov','edx, 0xffffffff')
    instruction(0x1400fddab,'lock dec','dword ptr [rbx]')
    instruction(0x1400fdc94,'xor','r8d, r8d')
    instruction(0x1400fdc97,'lea','edx, [r8 + 1]')
    instruction(0x14019c412,'mov','edx, 1')
    instruction(0x14019c417,'mov','ecx, edx')
    call(0x14019c419,0x1400fd9c0)
    call(0x14019c487,0x1400fdd90)
    instruction(0x14019c48c,'test','rbx, rbx')
    call(0x14019c2c7,0x1400fdd90)
    instruction(0x14019c2cc,'test','rbx, rbx')
    instruction(0x14019c4e2,'mov','eax, 0xefaccafe')
    instruction(0x14019c4e7,'rep stosd')
    instruction(0x14014f2fa,'xor','r8d, r8d')
    instruction(0x14014f2fd,'xor','edx, edx')
    instruction(0x14014f2ff,'xor','ecx, ecx')
    instruction(0x14039d325,'and','rsi, 0xffffffffffffff80')
    instruction(0x14039d32f,'sub')
    instruction(0x14039d385,'mov','byte ptr [rbx + 1], r14b')
    instruction(0x14039d389,'mov','qword ptr [rbx + 0x60], r14')
    call(0x14039d3a7,0x1403a6a10)
    call(0x14039d3ec,0x140471a6c)
    instruction(0x14039d3ea,'xor','edx, edx')
    instruction(0x14039d3c1,'call','qword ptr [rax + 0x10]')
    call(0x14039d423,0x1403a6a10)
    call(0x14039d43b,0x14012ef30)
    instruction(0x14039d44b,'add')
    instruction(0x14008198a,'call','rax')
    instruction(0x14012d70e,'mov','r8d, 0x400')
    instruction(0x14012e4cd,'call','r8')
    instruction(0x14012e58c,'call','qword ptr [rax]')
    call(0x14014f301,0x14012ee70)
    instruction(0x14012ee77,'mov')
    assert struct.unpack('<Q',at(0x1405aa190,8))[0]==0x14012d8e0
    assert struct.unpack('<Q',at(0x1405aa090,8))[0]==0x140129d30
    call(0x14012da3b,0x1404390a0)
    instruction(0x140123a50,'call','qword ptr [rax + 8]')
    instruction(0x140115310,'call','qword ptr [rax + 8]')
    # 3A08F0 has exactly one call and it is the pointer decoder, not a destructor callback.
    c=[i for i in decoded[0x1403a08f0].values() if i.mnemonic=='call']
    assert len(c)==1 and c[0].operands[0].imm==0x1404ad270
    result={'status':'PASS','originalSha256':sha(raw),'evidenceSha256':sha(source),
            'freshFunctions':len(fresh),'freshInstructions':sum(f['instructions'] for f in fresh),
            'freshOriginalBytes':sum(f['size'] for f in fresh),'freshCodeBytes':sum(f['codeBytes'] for f in fresh),
            'freshDataBytes':sum(d['size'] for d in ev['data']),'functions':fresh,
            'reusedFunctions':reused,'reusedSources':reused_sources,'callerReferenceSitesValidated':xrefs,
            'incompleteIncomingXrefs':incomplete,'itemHeadOrBoundaryXrefs':resolved_item_xrefs,'switches':switches,'imports':imported_sites,
            'unexpandedDirectSites':direct_frontier,'indirectSites':indirect_sites,
            'limits':['Complete paginated ASM and exact function-span bytes do not mean every transitive callee is closed.',
                      'Generic j_j_free incoming references were clipped by the tool; only materialized sites are validated, not claimed complete.',
                      'Indirect calls, exception/unwind funclets, native OS/CRT internals and external thread control remain explicit boundaries.',
                      'No Actor-wide serialization, universal pre-destruction hook or owner-thread proof is established.',
                      'No running process, save file or IDB was modified.']}
    (HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','freshFunctions','freshInstructions','freshOriginalBytes','freshCodeBytes','freshDataBytes','callerReferenceSitesValidated','incompleteIncomingXrefs')}))

if __name__=='__main__':main()
