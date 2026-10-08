"""Reproduce bounded native-byte, prototype and local-asset evidence without IDA/game."""
from pathlib import Path
import argparse, copy, hashlib, importlib.util, json, struct
import capstone
import bdx_inspect, scan_local, test_bdx_inspect

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=0x140000000
EXE=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
TARGET='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def blob(s):return bytes(int(x,16) for x in s.split())
def encoded(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def require(v,s):
    if not v:raise ValueError(s)
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def derive():
    sources={}
    for s in load(HERE/'imports.json')['sources']:
        b=(ROOT/s['path']).read_bytes();require(sha(b)==s['sha256'],'Imported source changed '+s['path'])
        if s['path'].endswith('.json'):sources[s['path']]=json.loads(b)
    pe=module(ROOT/'docs/research/actor-scale-contract-20261007/verify.py','bdx_pe')
    cv=module(ROOT/'scripts/update-analysis-coverage.py','bdx_coverage')
    original=EXE.read_bytes();require(sha(original)==TARGET,'Original executable SHA')
    read=pe.original_reader(original,BASE)
    rebind=sources['docs/research/actor-rebind-context-20261008/evidence.json']
    scale=sources['docs/research/actor-scale-contract-20261007/evidence.json']
    wanted={'0x14041b400','0x14041c690','0x14041b320','0x1403e1240','0x14041c900','0x140431a70','0x140431aa0','0x1403e1840',
            '0x14041c6c0','0x14041c780','0x1404ad240'}
    functions={}
    for origin,doc in [('actor-scale-contract-20261007',scale),('actor-rebind-context-20261008',rebind)]:
        for f in doc['functions']:
            if f['addr'] not in wanted:continue
            x=copy.deepcopy(f)
            if 'disassembly' not in x:
                x['disassembly']={k:x[k] for k in ('addr','asm','cursor','instruction_count','total_instructions')}
            x['provenance']='../'+origin+'/evidence.json#functions[addr='+x['addr']+']'
            functions[x['addr']]=x
    require(set(functions)==wanted,'Required bodies')
    cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
    decoded={};instruction_count=0;body_bytes=0
    for a,f in sorted(functions.items()):
        good,addresses,why=cv.body_assembly(f);require(good,a+': '+why)
        b=blob(f['originalBytes']);start=int(a,16)
        require(len(b)==f['size'] and read(start,len(b))==b,'Body bytes '+a)
        last=start
        for addr in addresses:
            require(addr==last,'Instruction boundary '+hex(addr))
            ins=next(cs.disasm(b[addr-start:],addr,count=1),None);require(ins is not None,'Instruction decode')
            decoded[addr]=ins;last=addr+ins.size
        require(last==start+len(b) or a=='0x14041b400' and start+len(b)-last==231,'Body complete '+a)
        instruction_count+=len(addresses);body_bytes+=len(b)
    # Exact boundary assertions are independently decoded from original PE bytes.
    sites={
      0x41b521:('mov','dword ptr [r14 + 8], r8d'),
      0x41b525:('movzx','edi, word ptr [r9 + rax*2 + 0x10]'),
      0x41b52f:('and','eax, 0xf'),0x41b532:('cmp','eax, 0xb'),
      0x41b635:('movzx','ecx, word ptr [r9 + r10*2 + 0x14]'),
      0x41b63b:('movzx','eax, word ptr [r9 + r10*2 + 0x12]'),
      0x41b812:('add','dword ptr [r14 + 8], 2'),
      0x41b862:('movzx','edi, word ptr [rdx + rax*2 + 0x10]'),
      0x41b92b:('movzx','r15d, word ptr [rdi + rax*2 + 0x10]'),
      0x41b938:('movzx','edi, word ptr [rdi + rcx*2 + 0x12]'),
      0x41be80:('mov','r15d, 5'),0x41bf05:('mov','r15d, 5'),
      0x41bfc5:('ja','0x14041c13d'),
      0x41c16c:('movsx','edx, word ptr [r9 + r10*2 + 0x12]'),
      0x41c1db:('movsx','edx, word ptr [r9 + r10*2 + 0x12]'),
      0x41c1f4:('mov','dword ptr [rax - 4], ecx'),
      0x41c22c:('add','dword ptr [r14 + 8], edx'),
      0x41c235:('movzx','eax, word ptr [r9 + r10*2 + 0x12]'),
      0x41c23f:('movzx','edx, word ptr [r9 + r10*2 + 0x14]'),
      0x41c249:('shl','edx, 0x10'),0x41c24c:('or','edx, eax'),
      0x41c29c:('add','dword ptr [r14 + 8], edx'),
      0x41c2c4:('mov','r15d, 1'),0x41c2cf:('mov','r15d, 2'),
      0x41c2de:('mov','ecx, dword ptr [rdx - 4]'),
      0x41c2e1:('mov','dword ptr [r14 + 8], ecx'),
      0x41c4b2:('shr','rax, 6'),0x41c4b6:('mov','rdi, qword ptr [rcx + rax*8]'),
      0x41c4c2:('movzx','eax, word ptr [r9 + r10*2 + 0x12]'),
      0x41c4c8:('shl','rax, 4'),0x41c4cf:('movzx','edx, word ptr [rdi + 8]'),
      0x41c4fa:('call','qword ptr [rdi]'),0x41c4fc:('test','dword ptr [rdi + 8], 0x40000000'),
      0x41c51a:('mov','r15d, 5'),
      0x41c693:('cmp','dword ptr [r8 + 0x20], 0'),
      0x41c698:('lea','rax, [r8 + 0x1c]'),0x41c6a0:('cmp','dword ptr [rax], edx'),
      0x41c6a2:('je','0x14041c6b1'),0x41c6a4:('add','rax, 8'),
      0x41c6a8:('cmp','dword ptr [rax + 4], 0'),0x41c6b1:('mov','eax, dword ptr [rax + 4]')}
    assertions=[]
    for rva,expected in sites.items():
        ins=decoded.get(BASE+rva);require(ins is not None and (ins.mnemonic,ins.op_str)==expected,'Semantic anchor '+hex(rva))
        assertions.append(dict(addr=hex(BASE+rva),mnemonic=ins.mnemonic,operands=ins.op_str,originalBytes=bytes(ins.bytes).hex()))
    tables=[]
    for name,rva,count,bias in [('group',0x41c5a4,12,0),('float-unary',0x41c5d4,11,1),('integer-unary',0x41c600,12,0),('integer-binary',0x41c630,12,0),('control',0x41c660,10,0)]:
        data=read(BASE+rva,count*4);targets=struct.unpack('<'+'I'*count,data)
        require(all(BASE+x in decoded for x in targets),'Table target not an instruction')
        tables.append(dict(name=name,addr=hex(BASE+rva),indexBias=bias,originalBytes=data.hex(' '),targets=[hex(BASE+x) for x in targets]))
    require(tables[0]['targets'][10]=='0x14041c4aa','Trap main dispatch')
    require(tables[1]['targets'][2:4]==['0x14041be7c']*2,'Float invalid operations3/4')
    require(tables[2]['targets'][1]=='0x14041be7c','Integer unary invalid operation1')
    require(tables[4]['targets'][4]=='0x14041c51a','Control invalid4')
    descriptor=[]
    for addr,index,argc,adapter in [(0x140756bf0,9,3,0x140431a70),(0x140757150,95,2,0x140431aa0)]:
        b=read(addr,16);fn,flags,pad=struct.unpack('<QII',b)
        require(fn==adapter and flags&0xffff==argc and not flags&0x40000000,'Trap descriptor')
        descriptor.append(dict(addr=hex(addr),bank=2,index=index,arguments=argc,returnsValue=False,adapter=hex(fn),flags=flags,originalBytes=b.hex(' ')))
    scan=scan_local.run();require(scan==load(HERE/'loose-scan.json'),'Local asset scan no longer reproduces')
    selected=[];witnesses=[]
    for h in scan['hits']:
        if h['asset'] not in ('obj/B_AL020.mdlx','obj/B_EX400.mdlx'):continue
        data=(Path(scan['sourceRoot'])/h['asset']).read_bytes()[h['offset']:h['offset']+h['length']]
        doc=bdx_inspect.inspect(data)
        selected.append(dict(asset=h['asset'],scriptSha256=doc['sha256'],header=doc['header'],diagnostics=doc['diagnostics'],instructions=[{k:i[k] for k in ('pc','width','edges')} for i in doc['instructions']]))
        for w in h['witnesses']:
            pc=w['instruction']['pc'];start=pc-8 if w['instruction']['index']==9 else pc-5
            excerpt=[i for i in doc['instructions'] if start<=i['pc']<=pc]
            require(excerpt[0]['pc']==start,'Witness excerpt boundary')
            witnesses.append(dict(asset=h['asset'],assetSha256=h['assetSha256'],barOrdinal=h['barOrdinal'],
                                  scriptOffset=h['offset'],scriptLength=h['length'],scriptSha256=doc['sha256'],
                                  headerBytes=data[:doc['header']['end']].hex(' '),trap=w['instruction'],routes=w['routes'],
                                  excerptStartPc=start,excerptBytes=data[16+2*start:16+2*(pc+2)].hex(' '),
                                  excerptInstructions=excerpt,limits='Conditional static event0 path. Pushed immediate ID is visible; validity/provenance of operand0 is not proved.'))
    require(selected==load(HERE/'selected-structure.json'),'Selected prototype result changed')
    retail=load(HERE/'retail-comparison.json')
    require(retail['passed'] and retail['expectedStructureSha256']==sha((HERE/'selected-structure.json').read_bytes()),'Independent retail comparison input')
    require(len(retail['results'])==len(selected),'Retail result count')
    for item in retail['results']:
        match=next(s for s in selected if s['asset']==item['asset'])
        require(item['payloadSha256']==match['scriptSha256'] and item['loosePayloadIdentical'] and item['allInstructionPcsWidthsAndEdgesMatch'] and item['instructionCount']==len(match['instructions']),'Retail comparison result')
    tests=test_bdx_inspect.run()
    metrics=dict(functions=len(functions),instructions=instruction_count,originalBodyBytes=body_bytes,
                 semanticAnchors=len(assertions),switchTables=len(tables),syntheticChecks=tests['checkCount'],
                 looseFiles=scan['fileCount'],looseScripts=len(scan['scripts']),looseScriptFailures=len(scan['failures']),
                 trapScripts=len(scan['hits']),selectedInstructions=sum(len(s['instructions']) for s in selected),
                 rootRetailComparisonChecks=retail['checks'])
    evidence=dict(schema=1,originalSha256=TARGET,imageBase=hex(BASE),functions=list(functions.values()),
                  semanticAnchors=assertions,switchTables=tables,trapDescriptors=descriptor,
                  scope='Eleven reused complete bodies with original-byte verification; no new exhaustive writer or runtime claim.')
    receipt=dict(status='PASS',metrics=metrics,tests=tests,limits=['Static stored-byte CFG, no game or script execution.',
                  'Local loose corpus is not a retail-package census. Two selected package identities are separately checked by Root; receipt copied into this package.',
                  'Native side effects, mutated code, operand validity, exception paths and computed VM returns remain outside CFG proof.'])
    return {'evidence.json':evidence,'verification.json':receipt,'asset-witnesses.json':witnesses}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
    derived=derive()
    for name,data in derived.items():
        if args.check:require(load(HERE/name)==data,'Derived evidence changed: '+name)
        else:(HERE/name).write_bytes(encoded(data))
    if args.check:
        for name,entry in load(HERE/'manifest.json')['files'].items():
            b=(HERE/name).read_bytes();require(len(b)==entry['bytes'] and sha(b)==entry['sha256'],'Manifest '+name)
    print('PASS',derived['verification.json']['metrics'])
