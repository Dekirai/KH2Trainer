"""Read-only retail-byte/dataflow reproduction; --check also checks derived JSON.
No IDA, injected code, live process, or script execution is involved.
"""
import argparse, copy, hashlib, json, struct
from pathlib import Path
import capstone
import trace_model as tm

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
EXE=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
BASE=0x140000000
TARGET='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def encoded(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def blob(s):return bytes(int(x,16) for x in s.split())
require=tm.require
sha=tm.sha

def derive():
    for s in load(HERE/'imports.json')['sources']:
        require(sha((ROOT/s['path']).read_bytes())==s['sha256'],'import changed '+s['path'])
    original=EXE.read_bytes();require(sha(original)==TARGET,'original executable identity')
    pe=tm.module(ROOT/'docs/research/actor-scale-contract-20261007/verify.py','rebind_original_pe')
    read=pe.original_reader(original,BASE)
    capture=load(HERE/'ida-capture.json')
    require(capture['health']['status']=='ok' and capture['health']['auto_analysis_ready'],'IDA health')
    functions={}
    for source,wanted in [('bdx-inspection-20261008',None),('actor-scale-contract-20261007',{'0x1403e1c80','0x14041c890'})]:
        for f in load(ROOT/'docs/research'/source/'evidence.json')['functions']:
            if wanted is not None and f['addr'] not in wanted:continue
            f=copy.deepcopy(f)
            if 'disassembly' not in f:f['disassembly']={k:f[k] for k in ('addr','asm','cursor','instruction_count','total_instructions')}
            f['provenance']='../'+source+'/evidence.json#'+f['addr'];functions[f['addr']]=f
    for f in capture['functions']:
        f=copy.deepcopy(f);f['provenance']='ida-capture.json#'+f['addr'];functions[f['addr']]=f
    cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);cs.detail=True
    decoded={};count=0;byte_count=0
    for addr,f in sorted(functions.items()):
        start=int(addr,16);raw=blob(f['originalBytes'])
        require(len(raw)==f['size'] and read(start,len(raw))==raw,'original body '+addr)
        d=f['disassembly'];lines=d['asm']['lines']
        require(d['cursor'].get('done') and len(lines)==d['instruction_count']==d['total_instructions'],'full merged ASM '+addr)
        # Each captured page must be contiguous and the final cursor complete.
        pages=f.get('pages',[d])
        if pages and 'asm' in pages[0]:
            require(sum(p['instruction_count'] for p in pages)==len(lines),'page coverage '+addr)
            require(pages[-1]['cursor'].get('done'),'last page '+addr)
        last=start
        for line in lines:
            at=int(line['addr'],16);require(at==last,'instruction pagination/boundary '+hex(at))
            i=next(cs.disasm(raw[at-start:],at,count=1));decoded[at]=i;last=at+i.size
        tail=start+len(raw)-last
        require(tail==0 or addr=='0x14041b400' and tail==231,'body tail '+addr)
        count+=len(lines);byte_count+=len(raw)
    descriptors={};banks=[]
    for bank in (1,2):
        a=BASE+0x753490+8*bank;raw=read(a,8);banks.append(dict(addr=hex(a),bank=bank,originalBytes=raw.hex(' '),table=hex(struct.unpack('<Q',raw)[0])))
    for bank,index in [(1,5),(1,6),(1,7),(1,23),(2,9),(2,95)]:
        table=int(next(b['table'] for b in banks if b['bank']==bank),16)
        addr=table+16*index;raw=read(addr,16);fn,flags,_=struct.unpack('<QII',raw)
        require(hex(fn) in functions,'missing adapter body')
        descriptors[bank,index]=dict(bank=bank,index=index,addr=hex(addr),adapter=hex(fn),flags=flags,
            declaredArguments=flags&65535,returnsValue=bool(flags&0x40000000),originalBytes=raw.hex(' '))
    require(descriptors[1,6]['declaredArguments']==12 and descriptors[1,6]['adapter']=='0x14042e220','1:6 descriptor')
    anchors={
      0x41c4cf:('movzx','edx, word ptr [rdi + 8]'),0x41c4d3:('sub','rdx, 1'),
      0x41c4e0:('sub','rcx, 8'),0x41c4e8:('mov','rax, qword ptr [rcx]'),
      0x41c4eb:('mov','qword ptr [rbp + rdx*8 - 0x60], rax'),0x41c4f0:('sub','rdx, 1'),
      0x41c4f6:('lea','rcx, [rbp - 0x60]'),0x41c4fa:('call','qword ptr [rdi]'),
      0x42e288:('mov','eax, dword ptr [rcx + 0x60]'),0x42e28f:('mov','eax, dword ptr [rcx + 0x68]'),
      0x42e296:('mov','eax, dword ptr [rcx + 0x70]'),0x42e29d:('mov','eax, dword ptr [rcx + 0x78]'),
      0x3ca1ab:('mov','word ptr [rsi + 0x1a], ax'),0x3ca1b3:('mov','word ptr [rsi + 0x1c], ax'),
      0x3ca1bb:('mov','word ptr [rsi + 0x1e], ax'),
      0x41c9ad:('add','rax, qword ptr [rcx + 0x20]'),0x41c9ba:('add','rax, qword ptr [rcx + 0x10]'),
      0x41c997:('mov','ecx, dword ptr [rax]'),0x41c9a1:('add','rax, rcx'),
      0x41c1ec:('add','qword ptr [r14 + 0x10], rax'),0x41c1f4:('mov','dword ptr [rax - 4], ecx'),
      0x41c1fb:('mov','dword ptr [rax - 8], ebx'),0x41c2ed:('sub','rdx, rax'),
      0x41c087:('sub','esi, edi'),0x41bd98:('sete','al'),
      0x42e330:('movzx','eax, byte ptr [rip + 0x2e8cd1]')}
    semantic=[]
    for rva,expected in anchors.items():
        i=decoded[BASE+rva];require((i.mnemonic,i.op_str)==expected,'semantic '+hex(rva)+' actual '+i.mnemonic+' '+i.op_str)
        semantic.append(dict(addr=hex(i.address),mnemonic=i.mnemonic,operands=i.op_str,originalBytes=bytes(i.bytes).hex(' ')))
    traces=tm.derive(descriptors)
    structure=load(tm.FROZEN/'selected-structure.json')
    witness=load(tm.FROZEN/'asset-witnesses.json')
    mutation_checks=[];bar_witnesses=[]
    for item in traces:
        structure_item=next(s for s in structure if s['asset']==item['asset']);native_cfg={i['pc']:i for i in structure_item['instructions']}
        require(all(i['pc'] in native_cfg and native_cfg[i['pc']]['width']==i['width'] for i in item['instructions']),'frozen instruction boundaries')
        w=next(w for w in witness if w['asset']==item['asset']);whole=(tm.ASSETS/w['asset']).read_bytes()
        number=struct.unpack_from('<I',whole,4)[0];entries=[]
        for index in range(number):
            typ,link,name,offset,size=struct.unpack_from('<HH4sII',whole,16+16*index)
            if typ==3:entries.append(dict(ordinal=index,type=typ,offset=offset,size=size,originalBytes=whole[16+16*index:32+16*index].hex(' ')))
        require(len(entries)==1 and entries[0]['ordinal']==w['barOrdinal'] and entries[0]['offset']==w['scriptOffset'] and entries[0]['size']==w['scriptLength'],'unique BAR type3')
        bar_witnesses.append(dict(asset=item['asset'],type3Entries=entries))
        data=whole[w['scriptOffset']:w['scriptOffset']+w['scriptLength']]
        al='AL020' in w['asset']
        # A wrong field, a changed ID, or the wrong wrapper address must fail closed.
        for name,pc,replacement in [('wrong-actor-field',237 if al else 1899,8),('wrong-id',6029 if al else 7590,139 if al else 217),('wrong-work-wrapper',4642 if al else 3810,200 if al else 152)]:
            mutated=bytearray(data);struct.pack_into('<H',mutated,16+2*pc+2,replacement)
            try:tm.trace(bytes(mutated),w,descriptors,0)
            except (ValueError,KeyError):mutation_checks.append(dict(asset=item['asset'],name=name,rejected=True))
            else:raise ValueError('dataflow mutation not rejected '+name)
    # Profile-derived effect reaches slot14; slot15 has no read in this callee.
    discrepancy=dict(descriptor=descriptors[1,6],vectorCapacity=16,
        dispatchWritesSlots=list(range(12)),adapterReadsSlots=list(range(16)),
        uncopiedReads=[dict(slot=12,read='0x14042e288',recordField=26),dict(slot=13,read='0x14042e28f',recordField=28),
                      dict(slot=14,read='0x14042e296',recordField=30),dict(slot=15,read='0x14042e29d',recordField=None)],
        limits='Slots12..15 are inside the 16-value native scratch array but not populated by this dispatch. Their concrete values and any visible effect are not measured. Slot15 is copied to the adapter local array; the inspected callee does not consume it. No out-of-bounds or crash claim.')
    evidence=dict(schema='full-native-bodies-and-bounded-script-dataflow-v1',originalExeSha256=TARGET,
        functions=sorted(functions.values(),key=lambda f:f['addr']),bankPointers=banks,descriptors=list(descriptors.values()),semanticAnchors=semantic,barWitnesses=bar_witnesses)
    verification=dict(success=True,failures=0,functionCount=len(functions),instructionCount=count,originalBodyBytes=byte_count,
        semanticAnchors=len(semantic),scriptInstructionCount=sum(len(t['instructions']) for t in traces),
        boundedModelCases=sum(len(t['pathCases']) for t in traces),uniqueScriptPaths=sum(len(t['variants']) for t in traces),mutationChecks=mutation_checks,
        limitation='A conditional static dataflow proof for two original Event0 prefixes; not a native execution test, universal VM emulator, Event27 reachability proof, or concurrent lifetime proof.')
    return {'evidence.json':evidence,'descriptors.json':list(descriptors.values()),'script-dataflow.json':traces,'arity-discrepancy.json':discrepancy,'verification.json':verification}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    derived=derive()
    for name,value in derived.items():
        b=encoded(value)
        if args.check:require((HERE/name).read_bytes()==b,'derived mismatch '+name)
        else:(HERE/name).write_bytes(b)
    print(json.dumps(derived['verification.json'],ensure_ascii=False))
if __name__=='__main__':main()
