"""Own-folder reproduction of complete IDA views, original bytes and bounded models."""
import argparse, hashlib, importlib.util, json, struct, sys
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent
R=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir())
B=0x140000000
EXPECTED='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
ORIGINAL=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
def digest(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(p.read_bytes())
def encoded(o):return (json.dumps(o,indent=2,ensure_ascii=False)+'\n').encode()
checks=0
def need(v,s):
    global checks
    checks+=1
    if not v:raise AssertionError(s)
class PE:
    def __init__(self):
        self.data=ORIGINAL.read_bytes();need(digest(self.data)==EXPECTED,'original SHA')
        p=struct.unpack_from('<I',self.data,60)[0];o=p+24;s=o+struct.unpack_from('<H',self.data,p+20)[0]
        need(self.data[p:p+4]==b'PE\0\0' and struct.unpack_from('<Q',self.data,o+24)[0]==B,'PE/imagebase')
        self.sections=[struct.unpack_from('<III',self.data,s+40*i+12) for i in range(struct.unpack_from('<H',self.data,p+6)[0])]
    def raw(self,a,n):
        r=a-B;sp=[ptr+r-va for va,size,ptr in self.sections if va<=r and r+n<=va+size]
        need(n>0 and len(sp)==1,'backed original extent');return self.data[sp[0]:sp[0]+n]
def derive():
    pe=PE();sizes={};raw={};rows=[];deps=[]
    for p in sorted(H.glob('root-ida-*lookup*.json')):
        for row in load(p)['result']:
            f=row['fn'];need(f is not None,'IDA lookup');a=int(f['addr'],16);n=int(f['size'],16)
            if a in sizes:need(sizes[a]==n,'consistent duplicate lookup')
            sizes[a]=n
    for p in sorted(H.glob('root-ida-*bytes*.json')):
        for row in load(p)['result']:
            a=int(row['addr'],16);d=bytes(int(v,16) for v in row['data'].split())
            if a in raw:need(raw[a]==d,'consistent duplicate bytes')
            raw[a]=d
    for p in sorted(H.glob('root-ida-disasm-*.json')):
        asm=load(p);a=int(asm['addr'],16);dec=load(H/('root-ida-decompile-'+hex(a)+'.json'))
        need(asm['cursor'].get('done') and asm['instruction_count']==asm['total_instructions']==len(asm['asm']['lines']),'complete fresh ASM page')
        need(dec['cursor'].get('done') and not dec['truncated'] and dec['line_count']==dec['total_lines']==len(dec['code'].splitlines()),'complete fresh pseudocode')
        need(len(raw[a])==sizes[a],'full fresh IDA byte extent')
        rows.append(dict(addr=hex(a),name=asm['asm']['name'],size=sizes[a],originalBytes=raw[a].hex(' '),pages=[asm],disassembly=asm,pseudocode=dec,sourceMetadata=dict(freshCapture=True,toolOperator='/root',disasmFile=p.name)))
    reused={
      'actor-query-collision-20261008':[0x13f900,0x13fcc0,0x13fce0,0x13fd20,0x1a8e60,0x140f50,0x142080,0x183a50,0x183920,0x183a90,0x184970,0x173320,0x1745c0,0x175190,0x174640,0x173ef0],
      'collision-query-geometry-20261011':[0x3d0bb0,0x173b30]
    }
    for directory,addresses in reused.items():
        source=R/'docs/research'/directory/'evidence.json';prior=load(source)
        dep=dict(path=source.relative_to(R).as_posix(),sha256=digest(source.read_bytes()),manifestSha256=digest((source.parent/'manifest.json').read_bytes()),addresses=[hex(B+a) for a in addresses]);deps.append(dep)
        for a in addresses:
            f=next(f for f in prior['functions'] if int(f['addr'],16)==B+a)
            rows.append(dict(addr=f['addr'],name=f['name'],size=f['size'],originalBytes=f['originalBytes'],pages=f['pages'],disassembly=f['disassembly'],pseudocode=f.get('pseudocode',f.get('decompile')),sourceMetadata=dict(freshCapture=False,path=dep['path'],sha256=dep['sha256'])))
    cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True;ins={};aliases={'retn':'ret','sal':'shl','jz':'je','jnz':'jne','jnb':'jae','jnae':'jb','setz':'sete','setnz':'setne','movabs':'mov'}
    for f in rows:
        a=int(f['addr'],16);d=bytes.fromhex(f['originalBytes']);need(d==pe.raw(a,f['size']),'all IDA bytes match original '+f['addr']);f['sha256']=digest(d)
        pages=f['pages'];asm=[]
        for page in pages:
            need(page.get('offset',len(asm))==len(asm),'continuous ASM pages')
            asm.extend(page['asm']['lines']);need(page['cursor'].get('done') or page['cursor'].get('next')==len(asm),'ASM cursor progress')
        need(pages[-1]['cursor'].get('done') and asm==f['disassembly']['asm']['lines'] and len(asm)==f['disassembly']['total_instructions'],'full body join')
        covered=set();decoded=[]
        for row in asm:
            pc=int(row['addr'],16);i=next(cs.disasm(d[pc-a:],pc,count=1));span=set(range(pc,pc+i.size))
            need(a<=pc and pc+i.size<=a+len(d) and not covered&span,'bounded nonoverlapping instruction');covered|=span
            op=row['instruction'].split(';')[0].split()[0].lower();need(aliases.get(op,op)==aliases.get(i.mnemonic,i.mnemonic) or op=='xchg' and i.mnemonic=='nop','mnemonic original comparison '+hex(pc)+' '+op+'/'+i.mnemonic)
            ins[pc]=i;decoded.append(dict(addr=hex(pc),bytes=i.bytes.hex(' '),size=i.size,mnemonic=i.mnemonic,operands=i.op_str))
        need(len(covered)==len(d),'whole extent decoded '+f['addr']);f['instructions']=decoded;f['complete']=True
    need(len({f['addr'] for f in rows})==len(rows),'no duplicate functions')
    return pe,dict(schema=1,Domain='native',originalSha256=EXPECTED,imageBase=hex(B),functions=rows,dependencies=deps),ins
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--write',action='store_true');ap.add_argument('--check',action='store_true');ap.add_argument('--bytes-only',action='store_true');args=ap.parse_args()
    pe,evidence,ins=derive();outputs={'evidence.json':encoded(evidence)}
    if (H/'provenance.json').is_file():
        provenance=load(H/'provenance.json')
        need(digest((R/'scripts/update-analysis-coverage.py').read_bytes())==provenance['coverageParserSha256'],'unchanged coverage parser')
        old=provenance['interpreterBase'];need(digest((R/old['path']).read_bytes())==old['sha256'],'pinned interpreter base')
    result=dict(status='PASS',originalSha256=EXPECTED,freshBodies=sum(f['sourceMetadata']['freshCapture'] for f in evidence['functions']),reusedBodies=sum(not f['sourceMetadata']['freshCapture'] for f in evidence['functions']),originalBytes=sum(f['size'] for f in evidence['functions']),instructions=len(ins))
    if not args.bytes_only:
        import model
        models=model.run(ins,pe.raw,need);outputs['model-results.json']=encoded(models);result['modelSummary']=models['summary']
        claims=load(H/'report.json')['claims'];spec=importlib.util.spec_from_file_location('coverage',R/'scripts/update-analysis-coverage.py');parser=importlib.util.module_from_spec(spec);spec.loader.exec_module(parser)
        for c in claims:
            need(c['addr'] in {f['addr'] for f in evidence['functions']} and c['Finding'] and c['Limitations'],'bounded canonical claim')
            for ref in c['Evidence']:need(parser.resolve_reference(H/'report.json',ref)['status']=='exists','resolvable evidence '+ref)
        for f in evidence['functions']:
            ok,asm,why=parser.body_assembly(f);need(ok and len(asm)==len(f['instructions']),'coverage full ASM '+why);need(parser.has_raw_code(f,int(f['addr'],16),f['size']),'coverage raw span')
        result['claims']=len(claims)
    result['checks']=checks;outputs['verification.json']=encoded(result)
    for name,data in outputs.items():
        if args.write:(H/name).write_bytes(data)
        else:need((H/name).read_bytes()==data,'exact reproduction '+name)
    if args.check:
        manifest=load(H/'manifest.json');actual={p.relative_to(H).as_posix() for p in H.rglob('*') if p.is_file() and p!=H/'manifest.json'}
        need(actual=={f['path'] for f in manifest['files']},'exact recursive study file set')
        for f in manifest['files']:
            d=(H/f['path']).read_bytes();need(len(d)==f['length'] and digest(d)==f['sha256'],'manifest pin '+f['path'])
    print(json.dumps(result))
if __name__=='__main__':main()
