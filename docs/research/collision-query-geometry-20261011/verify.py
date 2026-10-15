"""Read-only reproducible collision geometry study; --write updates own artifacts.
Full original PE/capture comparison, bounded instruction models and claim anchors.
No game or IDB execution. Python3 and Capstone5 required.
"""
import argparse,copy,hashlib,json,struct,sys,importlib.util
from pathlib import Path
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent
R=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir())
B=0x140000000
EXPECTED='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
ORIGINAL=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
def digest(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(p.read_bytes())
def encoded(x):return (json.dumps(x,indent=2,ensure_ascii=False)+'\n').encode()
checks=0
def need(v,s):
    global checks
    checks+=1
    if not v:raise AssertionError(s)
class PE:
    def __init__(self):
        self.data=ORIGINAL.read_bytes();need(digest(self.data)==EXPECTED,'original retail identity')
        u16=lambda p:struct.unpack_from('<H',self.data,p)[0]
        u32=lambda p:struct.unpack_from('<I',self.data,p)[0]
        p=u32(60);opt=p+24;sec=opt+u16(p+20)
        need(self.data[:2]==b'MZ' and self.data[p:p+4]==b'PE\0\0' and u16(p+4)==0x8664 and u16(opt)==0x20b and struct.unpack_from('<Q',self.data,opt+24)[0]==B,'AMD64 PE32+ identity')
        self.sections=[(u32(sec+40*i+12),u32(sec+40*i+16),u32(sec+40*i+20)) for i in range(u16(p+6))]
    def raw(self,addr,n):
        rva=addr-B;found=[ptr+rva-va for va,size,ptr in self.sections if va<=rva and rva+n<=va+size]
        need(n>0 and len(found)==1,'single physical PE extent '+hex(addr));return self.data[found[0]:found[0]+n]
def derive():
    pe=PE();capture=load(H/'capture.json');need(capture['originalSha256']==EXPECTED and capture['health']['auto_analysis_ready'] is False,'capture identity and global analysis limit')
    provenance=load(H/'provenance.json')
    need(provenance['originalSha256']==EXPECTED and provenance['analysisInputCopySha256']==EXPECTED and provenance['captureSha256']==digest((H/'capture.json').read_bytes()),'pinned original capture provenance')
    sources=[('docs/research/actor-query-collision-20261008',[0x13f900,0x13fd20,0x13fcc0,0x13fce0,0x140200,0x1a8e60,0x1a8f20,0x183990,0x184850,0x183a90,0x184970,0x1741c0,0x1842d0,0x18b760,0x142120,0x1745c0,0x173ef0]),('docs/research/collision-resource-lifetime-20261011',[0x163fc0])]
    rows=[];deps=[]
    for f in capture['functions']:
        rows.append((f,{'file':'capture.json','sha256':digest((H/'capture.json').read_bytes()),'freshCapture':True}))
    for path,addrs in sources:
        prior=load(R/path/'evidence.json')
        deps.append({'path':path,'manifestSha256':digest((R/path/'manifest.json').read_bytes()),'evidenceSha256':digest((R/path/'evidence.json').read_bytes()),'selectedAddresses':[hex(B+a) for a in addrs]})
        need(deps[-1] in provenance['priorEvidence'],'explicit immutable prior dependency pin')
        for a in addrs:
            found=[f for f in prior['functions'] if int(f['addr'],16)==B+a];need(len(found)==1,'explicit prior body selection')
            rows.append((found[0],{'file':path+'/evidence.json','sha256':deps[-1]['evidenceSha256'],'freshCapture':False}))
    cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True;instructions={};functions=[]
    aliases={'retn':'ret','jz':'je','jnz':'jne','jnb':'jae','jnae':'jb','jna':'jbe','jnbe':'ja','jnl':'jge','jng':'jle','jnle':'jg','setnz':'setne','setz':'sete','setnl':'setge','cmovnz':'cmovne','cmovz':'cmove','sal':'shl'}
    for original,meta in rows:
        a=int(original['addr'],16);data=bytes(int(x,16) for x in original['idaBytes'].split());need(len(data)==original['size'] and data==pe.raw(a,len(data)),'full original body '+hex(a))
        lines=[]
        for page in original['pages']:
            need(page.get('offset',len(lines))==len(lines) and page['instruction_count']==len(page['asm']['lines']),'ASM continuous page')
            lines.extend(page['asm']['lines']);need(page['cursor'].get('done') or page['cursor'].get('next')==len(lines),'ASM next cursor')
        need(original['pages'][-1]['cursor'].get('done') and lines==original['disassembly']['asm']['lines'] and len(lines)==original['disassembly']['total_instructions'],'complete preserved ASM')
        dp=original['decompilePages'];count=0
        for page in dp:
            need(page.get('offset',count)==count and page['line_count']==len(page['code'].splitlines()),'pseudocode continuous page')
            count+=page['line_count'];need(page['cursor'].get('done') or page['cursor'].get('next')==count,'pseudocode completion cursor')
        # Legacy paginated tool results flag every non-whole page truncated,
        # including the last. Exact contiguous counts plus done close the body.
        need(dp[-1]['cursor'].get('done') and count==dp[0]['total_lines'] and (not meta['freshCapture'] or not dp[-1].get('truncated')),'full pseudocode')
        covered=set();decoded=[]
        for row in lines:
            at=int(row['addr'],16);need(a<=at<a+len(data),'body instruction position')
            i=next(cs.disasm(data[at-a:],at,count=1));span=set(range(at,at+i.size));need(not covered&span and at+i.size<=a+len(data),'bounded disjoint decode')
            covered|=span;instructions[at]=i
            op=row['instruction'].split(';')[0].split()[0].lower();need(aliases.get(op,op)==aliases.get(i.mnemonic,i.mnemonic) or (op=='xchg' and i.mnemonic=='nop'),'original mnemonic matches IDA')
            decoded.append({'addr':hex(at),'size':i.size,'bytes':i.bytes.hex(' '),'mnemonic':i.mnemonic,'operands':i.op_str})
        gaps=[];j=0
        while j<len(data):
            if a+j in covered:j+=1;continue
            start=j
            while j<len(data) and a+j not in covered:j+=1
            gaps.append({'addr':hex(a+start),'bytes':data[start:j].hex(' '),'size':j-start})
        if gaps:need(a==B+0x1741c0 and gaps==[{'addr':'0x1401743f5','bytes':data[565:].hex(' '),'size':67}],'explicit prior collector switch/padding tail only')
        f={'addr':hex(a),'name':original['name'],'size':len(data),'originalBytes':data.hex(' '),'sha256':digest(data),'pages':original['pages'],'disassembly':original['disassembly'],'pseudocode':{'pages':dp,'code':'\n'.join(p['code'] for p in dp)},'instructions':decoded,'noninstructionSpans':gaps,'sourceMetadata':meta}
        functions.append(f)
    need(len({f['addr'] for f in functions})==len(functions)==31,'13 fresh and18 explicit reused bodies without duplicates')
    data=[]
    for a,n in [(0x5b22d4,4),(0x623a80,4),(0x6239d8,4),(0x71b3f0,32),(0x71ba50,12),(0x71ba60,16),(0x5b2674,4),(0x623c20,4),(0x5b2670,4),(0x5b266c,4)]:
        raw=pe.raw(B+a,n);data.append({'addr':hex(B+a),'originalBytes':raw.hex(' '),'float32':list(struct.unpack('<'+'f'*(n//4),raw))})
    evidence={'schema':1,'Domain':'native','originalSha256':EXPECTED,'imageBase':hex(B),'functions':functions,'originalPeData':data,'dependencies':deps}
    result={'status':'PASS','freshBodies':13,'freshBytes':3041,'freshInstructions':729,'reusedBodies':18,'totalOriginalBytes':sum(f['size'] for f in functions),'totalInstructions':len(instructions),'dataOrPaddingBytes':67,'originalExeSha256':EXPECTED}
    return pe,evidence,instructions,result

def review_inputs(evidence,instructions):
    provenance=load(H/'provenance.json');parser_path=R/'scripts/update-analysis-coverage.py'
    need(digest(parser_path.read_bytes())==provenance['coverageParserSha256'],'unchanged coverage parser pin')
    spec=importlib.util.spec_from_file_location('coverage_parser',parser_path);parser=importlib.util.module_from_spec(spec);spec.loader.exec_module(parser)
    report=load(H/'report.json');need(report['originalSha256']==EXPECTED and report['Domain']=='native','canonical report domain/identity')
    addresses={f['addr']:f for f in evidence['functions']};need(len(report['claims'])==17 and len({c['addr'] for c in report['claims']})==17,'one canonical claim per chosen function')
    refs=[]
    for c in report['claims']:
        need(c['addr'] in addresses and bool(c['Finding']) and bool(c['Limitations']),'bounded claim on complete evidence body')
        for ref in c['Evidence']:
            item=parser.resolve_reference(H/'report.json',ref);need(item['status']=='exists','unchanged parser resolves '+ref);refs.append(item)
    for f in evidence['functions']:
        ok,rows,why=parser.body_assembly(f);need(ok and len(rows)==len(f['instructions']),'unchanged full body parser '+f['addr']+' '+why)
        need(parser.has_raw_code(f,int(f['addr'],16),f['size']),'unchanged original byte witness parser')
    anchors=load(H/'anchors.json')['anchors']
    for a in anchors:
        i=instructions[int(a['addr'],16)];f=addresses[a['owner']]
        need(int(f['addr'],16)<=i.address<int(f['addr'],16)+f['size'],'anchor owner')
        need(a['bytes']==i.bytes.hex(' ') and a['size']==i.size and a['mnemonic']==i.mnemonic and a['operands']==i.op_str,'exact original anchor bytes and operands')
    return {'claims':len(report['claims']),'anchors':len(anchors),'resolvedReferences':len(refs),'acceptedCompleteBodies':len(addresses),'parserSha256':provenance['coverageParserSha256']}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--write',action='store_true');ap.add_argument('--check',action='store_true');ap.add_argument('--bytes-only',action='store_true');args=ap.parse_args()
    pe,evidence,instructions,result=derive()
    outputs={'evidence.json':encoded(evidence)}
    if not args.bytes_only:
        import model
        models=model.run(instructions,pe.raw,need);outputs['model-results.json']=encoded(models);result['modelSummary']=models['summary']
        result['claimAndParserChecks']=review_inputs(evidence,instructions)
    result['checks']=checks;outputs['verification.json']=encoded(result)
    for name,data in outputs.items():
        if args.write:(H/name).write_bytes(data)
        else:need((H/name).read_bytes()==data,'reproduced '+name)
    if args.check and (H/'manifest.json').is_file():
        m=load(H/'manifest.json')['files'];need(set(m)=={p.relative_to(H).as_posix() for p in H.rglob('*') if p.is_file() and p.name!='manifest.json'},'exact recursive manifest')
        for name,item in m.items():need(digest((H/name).read_bytes())==item['sha256'] and (H/name).stat().st_size==item['bytes'],'frozen '+name)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
