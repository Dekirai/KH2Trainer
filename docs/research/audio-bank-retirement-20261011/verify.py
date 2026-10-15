"""Verify the bounded static study against the original PE. --check writes nothing."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_MEM,X86_OP_IMM,X86_REG_RIP,X86_REG_RAX
sys.dont_write_bytecode=True
import model
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'src/KH2Trainer.Core').is_dir())
TARGET=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
BASE=0x140000000
ORIGINAL='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def dump(p,value):p.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def require(ok,what):
    if not ok:raise AssertionError(what)

# Chosen semantic sites: exact mnemonic/operand requirements, not hash-only anchors.
ANCHORS='''
078b85|jne|0x140078ba2
078b98|call|qword ptr [rax + 0x180]
078ba0|je|0x140078bc1
078bb7|call|qword ptr [rax + 0x38]
078bbf|mov|bl, 1
078c1f|je|0x140078ce3
078c2d|je|0x140078ce3
078c7e|cmp|ax, word ptr [rdi + 0x34]
078c82|jl|0x140078cd0
078cc2|call|qword ptr [rax + 0x180]
078ce3|mov|bl, 1
091d2f|call|0x140088fc0
091d3f|call|0x14009a780
091d48|xor|eax, eax
091d4a|cmp|ax, word ptr [rdi + 0x34]
091d4e|jl|0x140091d73
091d50|test|byte ptr [rdi + 0x80], 8
091d62|cmp|eax, 3
091d6a|call|0x1400986a0
091d78|mov|dil, 1
091aad|xor|r15d, r15d
091c88|cmp|r15w, word ptr [rdi + 0x34]
091c8d|jl|0x140091cbe
091cb4|call|0x14008a570
091cc3|mov|dil, 1
09a7e8|call|qword ptr [rax + 0x290]
09a7f8|call|qword ptr [rax + 0x278]
09a800|jne|0x14009a7c0
0986e0|cmp|dword ptr [rdx + 0x20], ebx
09871a|cmp|eax, 1
098759|call|qword ptr [rax + 0x10]
09875e|sete|dil
098220|cmp|dword ptr [rdi + 0x20], r15d
09827b|dec|dword ptr [rax + 0x78]
09827e|mov|dword ptr [rdi + 0x1c], 0xffffffff
0982a5|mov|qword ptr [rdi], rcx
0982a8|mov|qword ptr [rsi + 8], rdi
098318|mov|dword ptr [rax + 0x24], 1
098330|cmp|ecx, 1
098344|test|eax, eax
09834d|jne|0x140098335
09835d|call|qword ptr [rax + 0x10]
098362|setne|r14b
08a66a|dec|dword ptr [rip + 0x2af6cc0]
08a67e|and|byte ptr [rbx + 0x80], 0xdf
08a687|call|0x1400981c0
08a6be|call|0x14008c250
08a713|dec|dword ptr [rip + 0x2af6bf7]
08a73f|call|0x1400a1710
08a74c|call|qword ptr [rax]
08a773|mov|qword ptr [rbx], rax
08a776|mov|qword ptr [rip + 0x2af6b2b], rbx
08a793|dec|dword ptr [rip + 0x2af6977]
09f910|mov|rax, qword ptr [rcx + 0x28]
09fa89|mov|qword ptr [rcx], rax
09fa8c|test|dl, 1
09fa8f|je|0x14009fab0
09fa96|call|0x140031e80
136098|cmp|dword ptr [rcx + 0x6c], 0
1360c1|cmp|dword ptr [rdi + 0x6c], ebx
1360c4|jne|0x1401360f9
1360cb|call|0x140078b50
1360e3|call|0x14007d3f0
1360f9|cmp|dword ptr [rdi + 0x70], 2
1360fd|je|0x140136113
136108|call|qword ptr [rip + 0x44567a]
13610f|mov|qword ptr [rdi + 0x58], rbx
07d447|call|0x14009d460
07d461|call|qword ptr [rax + 0xc8]
09d4cf|call|qword ptr [rax + 0x290]
06b252|cmp|r14d, dword ptr [rcx + 0x3c]
06b267|xor|bl, bl
06b286|mov|bl, 1
06d971|call|0x140039d30
039d9d|mov|dword ptr [rax + 0x50], r12d
039da1|mov|byte ptr [rax + 0x4c], r13b
039e58|dec|dword ptr [rdi + 0x58]
091284|lea|rax, [rip + 0x58a4d5]
09128b|mov|qword ptr [rcx], rax
069e50|lea|rax, [rip + 0x5aff91]
069e57|mov|qword ptr [rcx], rax
076fdb|call|0x140091250
076fe5|mov|qword ptr [rip + 0x2b0adf4], rax
0770f6|mov|qword ptr [rip + 0x2b0aceb], rcx
078869|call|0x140089390
089449|mov|rax, qword ptr [rbx]
08944c|mov|qword ptr [rip + 0x2af7e55], rax
08947b|jne|0x140089421
08947d|cmp|dword ptr [r14 + 8], 4
089482|ja|0x14008941d
089484|call|0x140088f20
0894b9|jne|0x14008941d
0894d2|mov|qword ptr [rbx + 8], r14
0896a9|call|qword ptr [rax + 0x10]
0ba4a0|inc|word ptr [rcx + 0x34]
0ba4b0|dec|word ptr [rcx + 0x34]
0bb1f2|inc|word ptr [rbx + 0x34]
0bb636|dec|word ptr [rdi + 0x34]
088ff5|shr|rbx, 0x14
089008|cmp|qword ptr [rax + rbx + 0x10], rcx
08900f|cmp|dword ptr [rbx + 0x20], edi
08902b|call|qword ptr [rip + 0x4f229f]
089031|mov|rax, rbx
088f3b|jl|0x140088f52
088f86|jne|0x140088f67
088f8a|mov|dword ptr [rip + 0x2af817c], edx
0889f9|lea|rax, [rip + 0x2af8950]
088a13|lea|rcx, [rip + 0x2af9136]
088dd9|add|rax, 0x400
088ddf|cmp|rax, rcx
088de2|jl|0x140088a30
0913a6|call|0x1400889b0
09fca1|call|0x14008c1a0
09fcc8|call|qword ptr [rax + 0x18]
09fccd|mov|byte ptr [rax + 0xf], 0xff
09fd39|cmovl|r8d, edx
09fd9a|movsxd|rax, dword ptr [rcx + rdi*4]
09fd9e|add|rax, qword ptr [rbx + 8]
'''

def build():
    raw=TARGET.read_bytes();require(sha(raw)==ORIGINAL,'original EXE SHA256')
    pe=struct.unpack_from('<I',raw,60)[0];require(raw[:2]==b'MZ' and raw[pe:pe+4]==b'PE\0\0','PE identity')
    opt=pe+24;size=struct.unpack_from('<H',raw,pe+20)[0];count=struct.unpack_from('<H',raw,pe+6)[0]
    require(struct.unpack_from('<H',raw,opt)[0]==0x20b and struct.unpack_from('<Q',raw,opt+24)[0]==BASE,'PE64 image base')
    sections=[struct.unpack_from('<III',raw,opt+size+40*i+12) for i in range(count)]
    def read(address,length):
        rva=address-BASE
        for va,raw_size,ptr in sections:
            if va<=rva and rva+length<=va+raw_size:
                b=raw[ptr+rva-va:ptr+rva-va+length];require(len(b)==length,'raw extent');return b
        raise AssertionError(('not file backed',hex(address),length))
    cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
    evidence=dict(schema=1,Domain='native',originalSha256=ORIGINAL,imageBase=hex(BASE),functions=[],data=[],trailingData=[],anchors=[],virtualTargets=[],rtti=[],positiveRefs=[],dependencyBodies=[])
    instructions={};total_bytes=instruction_bytes=0
    capture_files=[HERE/'capture.json']+[HERE/f'capture-{n}.json' for n in range(2,9)]
    for path in capture_files:
        capture=load(path)
        require(capture['originalSha256']==ORIGINAL and int(capture['imageBase'],16)==BASE and capture['autoAnalysisReady'] is False,'capture identity/readiness')
        for f in capture['functions']:
            a=int(f['addr'],16);b=bytes(int(x,16) for x in f['idaBytes'].split())
            require(len(b)==f['size'] and b==read(a,len(b)),'complete original body '+f['addr'])
            pages=f['pages'];joined=[]
            for page in pages:
                require(page['offset']==len(joined),'ASM offset')
                require(page['instruction_count']==len(page['asm']['lines']),'ASM page length')
                joined.extend(page['asm']['lines'])
            require(pages[-1]['cursor']=={'done':True} and joined==f['disassembly']['asm']['lines'],'complete ASM pages')
            require(all(p['total_instructions']==len(joined) for p in pages),'consistent ASM total')
            pseudo=f['pseudocode'];require('\n'.join(p['code'] for p in pseudo['pages'])==pseudo['code'],'pseudocode page join')
            require(pseudo['pages'][-1]['cursor']=={'done':True} and not any(p.get('truncated',False) for p in pseudo['pages']),'complete pseudocode pages')
            line_offset=0
            for page in pseudo['pages']:
                require(page['offset']==line_offset and page['line_count']==len(page['code'].splitlines()),'pseudocode offsets/counts')
                require(page['total_lines']==len(pseudo['code'].splitlines()),'pseudocode total lines')
                line_offset+=page['line_count']
            decoded=[];covered=set()
            for row in joined:
                pc=int(row['addr'],16);require(a<=pc<a+len(b),'instruction start in body')
                i=next(cs.disasm(b[pc-a:],pc,count=1),None);require(i is not None,'Capstone decode')
                span=set(range(pc,pc+i.size));require(not span&covered and pc+i.size<=a+len(b),'nonoverlapping bounded instructions')
                require(pc not in instructions,'unique captured instruction');instructions[pc]=i;covered|=span;instruction_bytes+=i.size
                decoded.append(dict(addr=hex(pc),size=i.size,bytes=i.bytes.hex(),mnemonic=i.mnemonic,operands=i.op_str,idaText=row['instruction']))
                refs={o.imm for o in i.operands if o.type==X86_OP_IMM}|{pc+i.size+o.mem.disp for o in i.operands if o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP}
                for ref in row.get('refs',[]):
                    target=int(ref['addr'],16)
                    if target in refs:evidence['positiveRefs'].append(dict(site=hex(pc),target=hex(target),bytes=i.bytes.hex()))
            missing=set(range(a,a+len(b)))-covered
            if missing:
                start=min(missing);require(missing==set(range(start,a+len(b))) and b[start-a:]==b'\xcc'*len(missing),'only explicit trailingCC gaps')
                evidence['trailingData'].append(dict(function=hex(a),start=hex(start),count=len(missing),hex=b[start-a:].hex(),classification='trailing INT3 padding omitted by IDA instruction list'))
            evidence['functions'].append(dict(addr=hex(a),name=f['name'],size=len(b),sha256=sha(b),originalBytes=b.hex(' '),capture=path.name,instructions=decoded,pseudocodeLines=len(pseudo['code'].splitlines()),disassembly=f['disassembly'],pages=f['pages'],pseudocode=f['pseudocode'],sourceMetadata=dict(captureFile=path.name,captureSha256=sha(path.read_bytes()),document={k:v for k,v in capture.items() if k!='functions'})))
            total_bytes+=len(b)
    require(len(evidence['functions'])==40,'40 fresh selected bodies')
    for d in load(HERE/'data-capture.json')['data']:
        a=int(d['addr'],16);b=bytes(int(x,16) for x in d['idaBytes'].split());require(len(b)==d['size'] and b==read(a,len(b)),'data capture')
        evidence['data'].append(dict(addr=hex(a),size=len(b),originalBytes=b.hex(),sha256=sha(b),label=d['label']))
    for specification in ANCHORS.strip().splitlines():
        rva,mnemonic,operands=specification.split('|');a=BASE+int(rva,16);i=instructions[a]
        require((i.mnemonic,i.op_str)==(mnemonic,operands),'semantic anchor '+hex(a))
        evidence['anchors'].append(dict(addr=hex(a),bytes=i.bytes.hex(),mnemonic=mnemonic,operands=operands))
    targets=[(0x61b798,0x091a70),(0x61b7a0,0x091d00),(0x61b7f0,0x093330),(0x619eb0,0x06d910),(0x619f68,0x06b1d0),(0x61c9f0,0x09fa70),(0x61c9f8,0x09f9d0),(0x61ca00,0x09fbd0),(0x61ca08,0x09fd20),(0x61cad8,0x09f910)]
    for cell,target in targets:
        require(struct.unpack('<Q',read(BASE+cell,8))[0]==BASE+target,'concrete virtual target')
        evidence['virtualTargets'].append(dict(cell=hex(BASE+cell),target=hex(BASE+target)))
    for slot,name in [(0x61b758,'SoundDriver'),(0x619de0,'LayoutManager'),(0x61c9e8,'ActualBank')]:
        col=struct.unpack('<Q',read(BASE+slot,8))[0];fields=struct.unpack('<6I',read(col,24));td=BASE+fields[3]
        require(fields[0]==1 and BASE+fields[5]==col,'RTTI locator')
        raw_name=read(td+16,128).split(b'\0')[0];require(name.encode() in raw_name,'RTTI identity')
        evidence['rtti'].append(dict(vtableLocatorCell=hex(BASE+slot),locator=hex(col),typeDescriptor=hex(td),name=raw_name.decode('ascii')))
    for rva,text in [(0x089475,b'SEDB'),(0x0894b3,b'SSCF')]:
        i=instructions[BASE+rva];operand=i.operands[1]
        require(i.mnemonic=='cmp' and operand.type==X86_OP_MEM and operand.mem.base==X86_REG_RIP,'header compare memory')
        address=i.address+i.size+operand.mem.disp;require(read(address,4)==text,'original header signature')
        evidence['data'].append(dict(addr=hex(address),size=4,originalBytes=text.hex(),sha256=sha(text),label='original header comparison literal '+text.decode()))
    # This dependency is reused from the independently reviewed prior study,
    # not counted as a41st fresh IDA body.
    dep=load(HERE/'dependency-08c1a0.json');a=int(dep['addr'],16);b=bytes.fromhex(dep['originalBytes'])
    require(sha(b)==dep['sha256'] and read(a,len(b))==b,'reused insertion dependency')
    for row in dep['decodedInstructions']:
        pc=int(row['addr'],16);i=next(cs.disasm(read(pc,row['size']),pc,count=1))
        require((i.mnemonic,i.op_str,i.bytes.hex())==(row['mnemonic'],row['operands'],row['bytes']),'dependency ASM')
    evidence['dependencyBodies'].append(dict(addr=dep['addr'],size=len(b),sha256=dep['sha256'],source='dependency-08c1a0.json',freshCapture=False))
    # The32 immediate node-offset stores repeat twice; retained-state/nonalias
    # conditions remain explicit, since this is not an all-writers search.
    loop=[i for a,i in sorted(instructions.items()) if BASE+0x088a30<=a<BASE+0x088dd9]
    stores=[]
    for i in loop:
        dst,src=i.operands
        require(i.mnemonic=='mov' and dst.type==X86_OP_MEM and dst.mem.base==X86_REG_RAX,'initializer loop shape')
        if src.type==X86_OP_IMM:stores.append((dst.mem.disp,dst.size,src.imm))
    require(stores==[(8+32*k,8,104) for k in range(32)],'32 unrolled bucket offsets')
    start=instructions[BASE+0x0889f9];end=instructions[BASE+0x088a13]
    lo=start.address+start.size+start.operands[1].mem.disp;hi=end.address+end.size+end.operands[1].mem.disp
    require((lo,hi)==(BASE+0x2b81350,BASE+0x2b81b50),'initializer64 buckets')
    models=model.run();require(models['status']=='PASS','models')
    # Trace the actual decoded091D00 branch graph using synthetic helper
    # outcomes. This deliberately stops before unlock/epilogue and is not a
    # general CPU emulator or a proof that the helper outcomes are reachable.
    traces=0
    for case in models['results']:
        if case['group']!='eligibility':continue
        present,player,refs,flag,kind,busy=case['input']
        pc=BASE+0x091d37;rax=int(present);zero=False;less=False;result=None
        for _ in range(40):
            if pc==BASE+0x091d7b:break
            i=instructions[pc];nextpc=pc+i.size;rva=pc-BASE
            if rva==0x091d37:zero=rax==0
            elif rva==0x091d3f:rax=int(player)
            elif rva in [0x091d44,0x091d6f]:zero=(rax&255)==0
            elif rva==0x091d48:rax=0
            elif rva==0x091d4a:less=0<model.signed16(refs)
            elif rva==0x091d50:zero=not flag
            elif rva==0x091d5f:rax=kind
            elif rva==0x091d62:zero=rax==3
            elif rva==0x091d6a:rax=int(busy)
            elif rva==0x091d73:result=False
            elif rva==0x091d78:result=True
            elif i.mnemonic in ['je','jne','jl','jmp']:
                take=i.mnemonic=='jmp' or i.mnemonic=='je' and zero or i.mnemonic=='jne' and not zero or i.mnemonic=='jl' and less
                if take:nextpc=i.operands[0].imm
            else:require(i.mnemonic=='mov','predicate trace unsupported instruction')
            pc=nextpc
        require(pc==BASE+0x091d7b and result==case['result'],'native-shaped eligibility trace')
        traces+=1
    claims=load(HERE/'report.json')['claims'];require(len({x['address'] for x in claims})==len(claims),'unique claim addresses')
    for c in claims:require(int(c['address'],16) in instructions and c['limitations'] and c['evidence'],'claim address/evidence/limits')
    provenance=load(HERE/'provenance.json')
    for entry in provenance['capturePins']:
        require(sha((HERE/entry['path']).read_bytes())==entry['sha256'],'capture provenance '+entry['path'])
    for entry in provenance['dependencies']:
        scope=entry.get('base','repository');require(scope in ('repository','study'),'explicit provenance base')
        dependency=(HERE if scope=='study' else ROOT)/entry['path']
        require(sha(dependency.read_bytes())==entry['sha256'],'provenance '+entry['path'])
    stats=dict(functions=40,instructions=len(instructions),primaryBytes=total_bytes,instructionBytes=instruction_bytes,trailingCCBytes=total_bytes-instruction_bytes,semanticAnchors=len(evidence['anchors']),positiveRefs=len(evidence['positiveRefs']),dataSpans=len(evidence['data']),virtualTargets=len(targets),rttiTypes=3,reusedDependencyBodies=1,verifiedBucketOffsets=64,claims=len(claims),modelCases=models['cases'],decodedPredicateTraces=traces)
    verification=dict(status='PASS',originalSha256=ORIGINAL,checks=stats,allFreshCapturedBytesMatchOriginal=True,allASMPagesComplete=True,allPseudocodePagesComplete=True,autoAnalysisReady=False,independentReviewComplete=False,gameExecution=False,scope='40 selected complete fresh bodies plus1 clearly reused insertion dependency. Exact PE bytes, instruction decoding, semantic anchors and bounded synthetic models. No global lifetime, synchronization, all-writers, reachability or live-audio guarantee.')
    return evidence,models,verification

def main():
    ap=argparse.ArgumentParser();g=ap.add_mutually_exclusive_group(required=True);g.add_argument('--check',action='store_true');g.add_argument('--write',action='store_true');args=ap.parse_args()
    expected=build()
    for name,value in zip(['evidence.json','model-results.json','verification.json'],expected):
        if args.write:dump(HERE/name,value)
        else:require(load(HERE/name)==value,'reproducible '+name)
    if args.check:
        manifest=load(HERE/'manifest.json')['files'];actual={p.name for p in HERE.iterdir() if p.is_file() and p.name!='manifest.json'}
        require(set(manifest)==actual,'exact frozen file set')
        for name,pin in manifest.items():
            b=(HERE/name).read_bytes();require(sha(b)==pin['sha256'] and len(b)==pin['bytes'],'manifest '+name)
    print(json.dumps(expected[2],sort_keys=True))
if __name__=='__main__':main()
