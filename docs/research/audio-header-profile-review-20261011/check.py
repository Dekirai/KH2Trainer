"""Independent read-only PE/capture review. No author verifier or VM imported."""
import hashlib, importlib.util, json, struct, sys
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
sys.dont_write_bytecode = True
H = Path(__file__).resolve().parent
R = next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir())
S = R/'artifacts/audio-header-profile-20261011'
B = 0x140000000
checks = 0
def ck(value, description):
    global checks
    checks += 1
    if not value: raise AssertionError(description)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path): return json.loads(path.read_bytes())
def save(name,value): (H/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
ck(sha(S/'manifest.json')=='20449ff941a9205bbb8edcfe34bb292563100096ecba7f1cc5293d279163f7d7','reviewed manifest')
manifest = load(S/'manifest.json')['files']
ck(set(manifest)=={p.name for p in S.iterdir() if p.is_file() and p.name!='manifest.json'},'exact manifest scope')
for name,pin in manifest.items():
    ck(sha(S/name)==pin['sha256'] and (S/name).stat().st_size==pin['bytes'],'frozen '+name)
original = Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe').read_bytes()
ck(hashlib.sha256(original).hexdigest()=='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed','original retail identity')
u16=lambda p:struct.unpack_from('<H',original,p)[0]
u32=lambda p:struct.unpack_from('<I',original,p)[0]
u64=lambda p:struct.unpack_from('<Q',original,p)[0]
pe=u32(60);opt=pe+24;section_at=opt+u16(pe+20)
ck(original[:2]==b'MZ' and original[pe:pe+4]==b'PE\0\0' and u16(pe+4)==0x8664 and u16(opt)==0x20b and u64(opt+24)==B,'AMD64 PE32+ header')
sections=[]
for i in range(u16(pe+6)):
    p=section_at+40*i
    sections.append((u32(p+12),u32(p+16),u32(p+20),u32(p+36)))
def raw(addr,n):
    rva=addr-B
    matches=[(ptr+rva-va,flags) for va,size,ptr,flags in sections if va<=rva and n>=0 and rva+n<=va+size]
    ck(len(matches)==1,'unique file-backed PE span '+hex(addr))
    p,flags=matches[0];ck(p+n<=len(original),'file bound')
    return original[p:p+n]
def string(addr):
    result=bytearray()
    for i in range(1024):
        b=raw(addr+i,1)[0]
        if not b:return bytes(result).decode('ascii')
        result.append(b)
    raise AssertionError('unbounded string')
# Resolve import identities independently through the on-disk import descriptors.
imports={};import_rva=u32(opt+112+8)
for d in range(1000):
    lookup,stamp,chain,name,iat=struct.unpack('<IIIII',raw(B+import_rva+20*d,20))
    if not any((lookup,stamp,chain,name,iat)):break
    for i in range(10000):
        item=struct.unpack('<Q',raw(B+(lookup or iat)+8*i,8))[0]
        if not item:break
        imports[B+iat+8*i]=('#'+str(item&65535)) if item>>63 else string(B+item+2)
else:raise AssertionError('import descriptor termination')

e=load(S/'evidence.json');allrows=e['functions']+e['dependencies'];ins={};body_checks=[]
cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
aliases={'retn':'ret','jz':'je','jnz':'jne','jnb':'jae','jnae':'jb','jna':'jbe','jnbe':'ja','jnl':'jge','jng':'jle','jnle':'jg','jge':'jge','setnz':'setne','setz':'sete','cmovnz':'cmovne','cmovz':'cmove','sal':'shl'}
for f in allrows:
    a=int(f['addr'],16);data=bytes.fromhex(f['originalBytes'])
    ck(data==raw(a,len(data)) and len(data)==f['size'] and hashlib.sha256(data).hexdigest()==f['sha256'],'whole original body '+f['addr'])
    pages=f['pages'];rows=[]
    for page in pages:
        ck(page.get('offset',len(rows))==len(rows) and page['instruction_count']==len(page['asm']['lines']),'continuous ASM page')
        rows.extend(page['asm']['lines'])
    ck(pages[-1]['cursor']=={'done':True} and all(p['total_instructions']==len(rows) for p in pages),'complete ASM page cursor and totals')
    ck(rows==f['disassembly']['asm']['lines'] and len(rows)==len(f['instructions']),'aggregated ASM preserved')
    pseudopages=f['pseudocode']['pages'];linecount=0
    for p in pseudopages:
        ck(p.get('offset',linecount)==linecount and p['line_count']==len(p['code'].splitlines()),'continuous pseudocode page')
        linecount+=p['line_count']
    ck(pseudopages[-1]['cursor']=={'done':True} and all(p['total_lines']==linecount for p in pseudopages),'pseudocode explicit completion')
    ck('\n'.join(p['code'] for p in pseudopages)==f['pseudocode']['code'],'pseudocode exact join')
    covered=set()
    for row,norm in zip(rows,f['instructions']):
        pc=int(row['addr'],16);ck(a<=pc<a+len(data),'instruction inside body')
        i=next(cs.disasm(data[pc-a:],pc,count=1),None);ck(i is not None,'independent decode')
        span=set(range(pc,pc+i.size));ck(not span&covered and pc+i.size<=a+len(data),'nonoverlap and bounds')
        covered|=span;ins[pc]=i
        ida=row['instruction'].split(';')[0].split()[0].lower()
        ck(aliases.get(ida,ida)==aliases.get(i.mnemonic,i.mnemonic) or (ida=='xchg' and i.mnemonic=='nop'),'IDA mnemonic equals original instruction '+hex(pc))
        ck(norm=={'addr':hex(pc),'size':i.size,'bytes':i.bytes.hex(),'mnemonic':i.mnemonic,'operands':i.op_str},'all normalized operands rederived')
    missing=set(range(a,a+len(data)))-covered;declared=set()
    for gap in f['nonInstructionSpans']:
        g=int(gap['addr'],16);b=bytes.fromhex(gap['bytes']);ck(len(b)==gap['length'] and b==raw(g,len(b)),'explicit uncovered bytes')
        declared.update(range(g,g+len(b)))
        if a==B+0xa3590:
            ck(g==B+0xa3f21 and b[:3]==bytes.fromhex('0f1f00') and struct.unpack('<6I',b[3:])==(0xa362e,0xa3784,0xa3870,0xa3a1a,0xa3d31,0xa35e3),'full original alignment and switch table')
        else:ck(a==B+0x89390 and b==b'\xcc' and g==B+0x896ed,'only explicit prior trailing CC')
    ck(missing==declared,'complete instruction-or-data coverage')
    meta=f['sourceMetadata']
    if f['freshCapture']:
        cap=load(S/meta['captureFile']);ck(sha(S/meta['captureFile'])==meta['captureSha256'],'capture pin')
        originalf=next(x for x in cap['functions'] if x['addr']==f['addr'])
        ck(bytes(int(token,16) for token in originalf['idaBytes'].split())==data,'IDA original bytes equal PE')
        ck(all(originalf[k]==f[k] for k in ['pages','disassembly','pseudocode']),'transport exact')
        ck(cap['originalSha256']==hashlib.sha256(original).hexdigest() and cap['databaseHealth']['auto_analysis_ready'] is False,'capture identity and analysis state')
    else:
        src=R/meta['evidenceFile'];ck(sha(src)==meta['evidenceSha256'],'explicit reuse pin')
        originalf=next(x for x in load(src)['functions'] if x['addr']==f['addr'])
        ck(bytes.fromhex(originalf['originalBytes'])==data,'exact reused body')
    body_checks.append({'addr':f['addr'],'bytes':len(data),'instructions':len(rows),'fresh':f['freshCapture']})
for r in e['positiveRefs']:
    i=ins[int(r['site'],16)]
    targets={o.imm for o in i.operands if o.type==X86_OP_IMM}|{i.address+i.size+o.mem.disp for o in i.operands if o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP}
    ck(int(r['target'],16) in targets,'positive ref encoded in original')
for data in e['data']:
    b=bytes.fromhex(data['originalBytes']);ck(raw(int(data['addr'],16),len(b))==b,'exact captured data')
for cell,target in [(0x61cfc0,0x9fbd0),(0x61cfc8,0xa2840),(0x61cbd0,0xa0b00),(0x78a950,0x3b670)]:
    ck(struct.unpack('<Q',raw(B+cell,8))[0]==B+target,'concrete virtual/diagnostic target')
col=struct.unpack('<Q',raw(B+0x61cb70-8,8))[0]
td=struct.unpack_from('<I',raw(col,24),12)[0]
ck(string(B+td+16)=='.?AVToolBank@Driver@Sd@Engine@CDev@SQEX@@','independent ToolBank RTTI')
ck(string(B+0x61d408)=='SQEX::CDev::Engine::Sd::Driver::ScdHeader::GetScdHeaderSize','complete diagnostic source string')
thunk=next(cs.disasm(raw(B+0x471a60,6),B+0x471a60,count=1));o=thunk.operands[0]
ck(thunk.mnemonic=='jmp' and o.mem.base==X86_REG_RIP and imports[thunk.address+thunk.size+o.mem.disp]=='memcpy','copy target is PE memcpy import thunk')
for pc in [0x7ad47,0x7ad88,0x7adb0,0x7add6,0xa3502,0xa351e]:
    i=ins[B+pc];o=i.operands[0];slot=i.address+i.size+o.mem.disp
    ck(imports[slot] in ['EnterCriticalSection','LeaveCriticalSection'],'actual critical-section imports')
inventory=load(S/'priorwork-inventory.json');fresh=set(inventory['freshCapturedAddresses'])
ck(fresh=={x['addr'] for x in e['functions']} and len(fresh)==12,'exact fresh inventory')
for p in inventory['sources']:
    ck(sha(R/p['path'])==p['sha256'],'prior evidence pin')
    addresses={x.get('addr') for x in load(R/p['path']).get('functions',[])}
    ck(sorted(addresses&fresh)==p['matchingFunctionAddresses']==[],'bounded prior-array absence')
for p in load(S/'provenance.json')['dependencies']:ck(sha(R/p['path'])==p['sha256'],'provenance pin')
parser=R/'scripts/update-analysis-coverage.py'
ck(sha(parser)=='546d0defdacd8857d7f2461283516348ca28776d13e253d8d954ad43622cc1b2','unchanged parser')
spec=importlib.util.spec_from_file_location('coverage_review',parser);coverage=importlib.util.module_from_spec(spec);spec.loader.exec_module(coverage)
refs=[ref for c in load(S/'report.json')['claims'] for ref in c['Evidence']]
for ref in refs:ck(coverage.resolve_reference(S/'report.json',ref)['status']=='exists','reference resolves')
for f in allrows:
    ck(coverage.body_assembly(f)[0],'compatible complete ASM')
    spans=coverage.original_spans(f);ck(len(spans)==1 and spans[0][1]==raw(spans[0][0],len(spans[0][1])),'compatible complete PE bytes')

# Independently written machine over selected original decoded instructions.
import selected_machine
models=selected_machine.run(ins,raw,imports,ck)
summary={'status':'PASS','checks':checks,'manifestSha256':sha(S/'manifest.json'),'evidenceSha256':sha(S/'evidence.json'),
         'bodies':body_checks,'claimReferences':len(refs),'priorEvidencePins':len(inventory['sources']),'models':models,
         'scope':'Independent PE/capture/ASM/import/RTTI checks and selected original-instruction simulation. Author VM/verifier not used for these checks; no native execution.'}
save('checks.json',summary)
print(json.dumps({k:v for k,v in summary.items() if k!='bodies'}))
