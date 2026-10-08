"""Read-only retail-byte verification and bounded instruction candidate census.

No IDA mutation, process access, game execution, or whole-program writer claim.
"""
from pathlib import Path
import hashlib, importlib.util, json, re, sys
sys.dont_write_bytecode = True
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_AC_WRITE
from capstone.x86 import X86_OP_MEM, X86_OP_REG, X86_OP_IMM, X86_REG_RIP

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('retail_reader', HERE.parent/'actor-scale-contract-20261007/verify.py')
retail = importlib.util.module_from_spec(spec); spec.loader.exec_module(retail)
def read(name): return json.loads((HERE/name).read_text(encoding='utf-8'))
def octets(value): return bytes(int(x,16) for x in value.split())
def done(value):
    assert value.get('done') is True and not value.get('cancelled') and value.get('next') is None, value

def main():
    ev=read('evidence.json'); raw=retail.DEFAULT_EXE.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==ev['original_sha256']
    at=retail.original_reader(raw,int(ev['image_base'],16))
    md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
    decoded={}; bodies=[]; instruction_count=0
    for f in ev['functions']:
        start=int(f['addr'],16); blob=octets(f['originalBytes']); asm=f['disasm']
        assert len(blob)==f['size'] and at(start,len(blob))==blob, f['addr']
        done(asm['cursor']);done(f['decompile']['cursor'])
        rows=asm['asm']['lines'];assert len(rows)==asm['instruction_count']==asm['total_instructions']
        assert int(rows[0]['addr'],16)==start
        for n,row in enumerate(rows):
            pc=int(row['addr'],16);insn=next(md.disasm(blob[pc-start:],pc,count=1))
            end=int(rows[n+1]['addr'],16) if n+1<len(rows) else start+len(blob)
            assert insn.address+insn.size==end, (f['addr'],hex(pc),hex(end))
            decoded[pc]=insn
        instruction_count+=len(rows)
        bodies.append({'addr':f['addr'],'size':len(blob),'instructions':len(rows),'sha256':hashlib.sha256(blob).hexdigest()})

    search=read('search-pages.json')['pages'];hit_rows={};next_ea=0x140001000
    for page in search:
        q=page['query'];r=page['response'];done(r['cursor']);assert not r.get('error')
        assert int(q['start'],16)==next_ea;next_ea=int(q['end'],16)
        assert r['n']==len(r['hits']) and len(r['hits'])<q['limit']
        for hit in r['hits']:
            pc=int(hit['addr'],16);assert int(q['start'],16)<=pc<next_ea and pc not in hit_rows
            hit_rows[pc]=hit
    assert next_ea==0x14057b000 and len(search)==88
    hit_bytes=read('search-hit-bytes.json')
    assert len(hit_bytes['result'])==len(hit_rows)
    assert sum(q['count'] for q in hit_bytes['requests'])==len(hit_rows)
    for row in hit_bytes['result']:
        pc=int(row['addr'],16);assert pc in hit_rows and octets(row['data'])==at(pc,15)
    patterns=read('byte-patterns.json')['result'];pattern_addresses=set()
    for row in patterns:
        done(row['cursor']);assert not row.get('error') and row['n']==len(row['matches'])
        needle=bytes.fromhex(row['pattern'])
        for addr in row['matches']:
            pc=int(addr,16);assert at(pc,len(needle))==needle
            if 0x140001000<=pc<0x14057b000:pattern_addresses.add(pc)
    windows=read('pattern-instruction-windows.json')
    assert [int(x,16) for x in windows['patternAddresses']]==sorted(pattern_addresses)
    assert len(windows['windows'])==len(pattern_addresses)
    heads={};skipped_range_starts=[]
    for needle_pc,w in zip(sorted(pattern_addresses),windows['windows']):
        done(w['cursor']);assert not w.get('error') and not w['truncated'] and not w['next_start']
        lo=int(w['query']['start'],16);hi=int(w['query']['end'],16)
        assert lo==max(0x140001000,needle_pc-15) and hi==needle_pc+4
        assert len(w['matches'])==w['count']
        for row in w['matches']:
            pc=int(row['addr'],16);assert lo<=pc<hi
            # insn_query may report an arbitrary range start inside an existing
            # instruction, with the containing head's rendered text. Discard it.
            # An instruction containing the complete four-byte needle cannot
            # start 15 bytes before it (x86 maximum instruction length is 15).
            if pc==lo:skipped_range_starts.append(hex(pc));continue
            heads[pc]=row

    global_refs=read('discovery.json')['global_xrefs']['result'][0]
    assert global_refs['next_offset'] is None and global_refs['total']==len(global_refs['data'])
    global_pcs={int(row['addr'],16) for row in global_refs['data']}
    for pc in global_pcs:heads.setdefault(pc,{'addr':hex(pc),'source':'direct IDA xref'})
    # Text hits can be comments or misleading stack expressions. Classify actual
    # retail machine operands, never the substring alone.
    for pc,row in hit_rows.items():heads.setdefault(pc,{'addr':hex(pc),'function':row.get('function'),'source':'text'})
    candidates=[];global_matches=set()
    for pc,row in sorted(heads.items()):
        insn=next(md.disasm(at(pc,15),pc,count=1),None)
        if insn is None:continue
        fields=[]
        for op in insn.operands:
            if op.type!=X86_OP_MEM:continue
            mem=op.mem;absolute=pc+insn.size+mem.disp if mem.base==X86_REG_RIP else None
            field=None
            if absolute==0x142a105d0:field='current_player_global';global_matches.add(pc)
            elif mem.base and md.reg_name(mem.base) not in ('rsp','esp'):
                if 0x5c0<=mem.disp<=0x5c7:field='actor_offset_candidate'
                elif 0x268<=mem.disp<=0x26b:field='status_offset_candidate'
            if field:
                fields.append({'field':field,'base':md.reg_name(mem.base),'index':md.reg_name(mem.index),
                    'displacement':mem.disp,'width':op.size,'write':bool(op.access&CS_AC_WRITE),
                    'address_only':insn.mnemonic=='lea'})
        if fields:candidates.append({'addr':hex(pc),'mnemonic':insn.mnemonic,'operands':insn.op_str,
            'bytes':insn.bytes.hex(),'fields':fields,'ida':row})
    assert global_pcs==global_matches, (global_pcs-global_matches,global_matches-global_pcs)
    by_pc={int(x['addr'],16):x for x in candidates}
    actor_writers=[0x1403a7b1b,0x1403b33a0,0x1403c2e56,0x1404112d7,0x140411377]
    backlink_writers=[0x1403a7b32,0x1403c01f5,0x1403c2e6d,0x1404112ee,0x14041138e]
    current_writers=[0x1403a7133,0x1403a7af4,0x1403a8132,0x1403a8163,0x1403a8f43]
    for pcs,field,width in [(actor_writers,'actor_offset_candidate',8),(backlink_writers,'status_offset_candidate',4),(current_writers,'current_player_global',8)]:
        for pc in pcs:
            assert pc in decoded
            assert any(f['field']==field and f['width']==width and f['write'] for f in by_pc[pc]['fields']),hex(pc)
    actual_current_writers=[int(x['addr'],16) for x in candidates if any(f['field']=='current_player_global' and f['write'] for f in x['fields'])]
    assert actual_current_writers==current_writers
    for pc,target in [(0x1404112cb,0x1403c07e0),(0x1404112d2,0x1403c06b0),
        (0x14041136b,0x1403c07e0),(0x140411372,0x1403c0280),
        (0x1404112e9,0x1404ad240),(0x140411389,0x1404ad240)]:
        i=decoded[pc];assert i.mnemonic=='call' and i.operands[0].type==X86_OP_IMM and i.operands[0].imm==target
    shared_increment=decoded[0x1403c07ca]
    assert shared_increment.mnemonic=='inc' and shared_increment.operands[0].mem.disp==0x264
    result={'result':'PASS','function_bodies':bodies,'body_count':len(bodies),'body_instructions':instruction_count,
        'body_bytes':sum(x['size'] for x in bodies),'text_pages':len(search),'text_hits':len(hit_rows),
        'byte_patterns':len(patterns),'executable_pattern_positions':len(pattern_addresses),'instruction_windows':len(windows['windows']),
        'discarded_arbitrary_range_start_rows':len(skipped_range_starts),'current_player_xrefs':len(global_pcs),
        'current_player_direct_writers':[hex(x) for x in current_writers],
        'confirmed_actor_slot_writers':[hex(x) for x in actor_writers],
        'confirmed_status_backlink_writers':[hex(x) for x in backlink_writers],
        'limits':'Classified instructions are bounded candidates, not object-role or alias completeness. Unknown bytes, renamed/typed operands, base-biased aliases, negative/indexed addresses, wider stores starting before the field, bulk copies and indirect writes are not excluded.'}
    (HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    (HERE/'instruction-candidates.json').write_text(json.dumps({'candidates':candidates},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('function_bodies','limits')},indent=2))
if __name__=='__main__':main()
