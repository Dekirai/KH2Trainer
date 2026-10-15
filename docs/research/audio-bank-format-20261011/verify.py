"""Bounded original-PE verification. --check only reads files; never opens the game."""
import argparse, hashlib, json, struct, sys
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
sys.dont_write_bytecode=True
import model
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'src/KH2Trainer.Core').is_dir())
TARGET=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
BASE=0x140000000
ORIGINAL='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def dump(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def require(ok,label):
    if not ok:raise AssertionError(label)
def build():
    raw=TARGET.read_bytes();require(sha(raw)==ORIGINAL,'original EXE')
    pe=struct.unpack_from('<I',raw,60)[0];opt=pe+24
    require(raw[:2]==b'MZ' and raw[pe:pe+4]==b'PE\0\0' and struct.unpack_from('<H',raw,opt)[0]==0x20b,'PE64')
    require(struct.unpack_from('<Q',raw,opt+24)[0]==BASE,'imagebase')
    section_table=opt+struct.unpack_from('<H',raw,pe+20)[0]
    sections=[struct.unpack_from('<III',raw,section_table+40*i+12) for i in range(struct.unpack_from('<H',raw,pe+6)[0])]
    def read(a,n):
        for va,size,ptr in sections:
            rva=a-BASE
            if va<=rva and rva+n<=va+size:
                b=raw[ptr+rva-va:ptr+rva-va+n];require(len(b)==n,'raw extent');return b
        raise AssertionError(('not file-backed',hex(a),n))
    cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
    e=dict(schema=1,Domain='native',originalSha256=ORIGINAL,imageBase=hex(BASE),functions=[],data=[],dependencies=[],anchors=[])
    allins={};instruction_bytes=0
    for filename in ['capture.json','capture-2.json','capture-3.json']:
        c=load(HERE/filename)
        require(c['originalSha256']==ORIGINAL and c['autoAnalysisReady'] is False,'capture origin/readiness')
        for f in c['functions']:
            a=int(f['addr'],16);b=bytes(int(v,16) for v in f['idaBytes'].split())
            require(len(b)==f['size'] and b==read(a,len(b)),'body '+f['addr'])
            rows=[]
            for p in f['pages']:
                require(p['offset']==len(rows) and p['instruction_count']==len(p['asm']['lines']),'ASM offset/count')
                rows+=p['asm']['lines']
            require(f['pages'][-1]['cursor']=={'done':True} and rows==f['disassembly']['asm']['lines'],'ASM complete')
            require(all(p['total_instructions']==len(rows) for p in f['pages']),'ASM totals')
            p=f['pseudocode'];require('\n'.join(x['code'] for x in p['pages'])==p['code'],'pseudo join')
            require(p['pages'][-1]['cursor']=={'done':True},'pseudo complete')
            offset=0
            for x in p['pages']:
                require(x['offset']==offset and x['line_count']==len(x['code'].splitlines()) and not x.get('truncated',False),'pseudo page')
                require(x['total_lines']==len(p['code'].splitlines()),'pseudo total');offset+=x['line_count']
            decoded=[];covered=set()
            for row in rows:
                pc=int(row['addr'],16);require(a<=pc<a+len(b),'instruction range')
                i=next(cs.disasm(b[pc-a:],pc,count=1),None);require(i is not None,'decode')
                span=set(range(pc,pc+i.size));require(not span&covered and pc+i.size<=a+len(b),'instruction overlap/extent')
                require(pc not in allins,'unique instruction');allins[pc]=i;covered|=span;instruction_bytes+=i.size
                decoded.append(dict(addr=hex(pc),size=i.size,bytes=i.bytes.hex(),mnemonic=i.mnemonic,operands=i.op_str,idaText=row['instruction']))
            missing=set(range(a,a+len(b)))-covered
            require(not missing or (missing==set(range(min(missing),a+len(b))) and b[min(missing)-a:]==b'\xcc'*len(missing)),'only trailing CC')
            e['functions'].append(dict(addr=hex(a),name=f['name'],size=len(b),sha256=sha(b),originalBytes=b.hex(' '),capture=filename,disassembly=f['disassembly'],pages=f['pages'],pseudocode=f['pseudocode'],instructions=decoded,trailingCCBytes=len(missing)))
    require(len(e['functions'])==20,'20 fresh selected bodies')
    for filename in ['data-capture.json','data-capture-2.json']:
        for r in load(HERE/filename)['regions']:
            a=int(r['addr'],16);b=bytes(int(v,16) for v in r['data'].split());require(b==read(a,len(b)),'data bytes')
            e['data'].append(dict(addr=hex(a),size=len(b),originalBytes=b.hex(),sha256=sha(b),capture=filename))
    for d in load(HERE/'dependencies.json')['functions']:
        f=d['function'];a=int(f['addr'],16);b=bytes.fromhex(f['originalBytes']);require(sha(b)==f['sha256'] and b==read(a,len(b)),'reused body')
        source=ROOT/d['source'];require(sha(source.read_bytes())==d['sourceSha256'],'dependency pin')
        ins=f.get('instructions',f.get('decodedInstructions'))
        for row in ins:
            pc=int(row['addr'],16);i=next(cs.disasm(read(pc,row['size']),pc,count=1))
            require((i.bytes.hex(),i.mnemonic,i.op_str)==(row['bytes'],row['mnemonic'],row['operands']),'dependency decode')
        e['dependencies'].append(dict(addr=hex(a),size=len(b),sha256=sha(b),source=d['source'],sourceSha256=d['sourceSha256'],freshCapture=False))
    for rva,expected in load(HERE/'anchors.json').items():
        i=allins[BASE+int(rva,16)];require([i.mnemonic,i.op_str]==expected,'semantic anchor '+rva)
        e['anchors'].append(dict(addr=hex(i.address),bytes=i.bytes.hex(),mnemonic=i.mnemonic,operands=i.op_str))
    vt=load(HERE/'data-capture.json')['pointers']
    for p in vt:require(struct.unpack('<Q',read(BASE+0x61c9f0+p['offset'],8))[0]==int(p['address'],16),'vtable cell')
    col=struct.unpack('<Q',read(BASE+0x61c9e8,8))[0];fields=struct.unpack('<6I',read(col,24))
    require(fields[0]==1 and BASE+fields[5]==col,'RTTI locator')
    rtti=read(BASE+fields[3]+16,160).split(b'\0')[0].decode('ascii')
    require('ActualBank@' in rtti,'ActualBank RTTI');e['rtti']=dict(locator=hex(col),name=rtti)
    jpt=struct.unpack('<13I',read(BASE+0xb79f0,52));classes=read(BASE+0xb7a24,64)
    require(max(classes)<len(jpt),'opcode table bounds')
    e['opcodeTargets']=[dict(opcode=i,target=hex(BASE+jpt[c])) for i,c in enumerate(classes)]
    require(struct.unpack('<f',read(BASE+0x6239c4,4))[0]==struct.unpack('<f',struct.pack('<f',0.001))[0],'single precision duration scale')
    models=model.run(e)
    report=load(HERE/'report.json')
    require(len({c['address'] for c in report['claims']})==len(report['claims']),'unique claim addresses')
    for c in report['claims']:require(int(c['address'],16) in allins and c['evidence'] and c['limitations'],'claim anchor/limits')
    for pin in load(HERE/'provenance.json')['files']:
        require(sha((HERE/pin['path']).read_bytes())==pin['sha256'],'input pin '+pin['path'])
    stats=dict(freshBodies=len(e['functions']),instructions=len(allins),bytes=sum(f['size'] for f in e['functions']),instructionBytes=instruction_bytes,reusedBodies=len(e['dependencies']),dataSpans=len(e['data']),vtableCells=len(vt),semanticAnchors=len(e['anchors']),opcodeTargets=len(e['opcodeTargets']),claims=len(report['claims']),modelCases=models['cases'])
    verification=dict(status='PASS',originalSha256=ORIGINAL,checks=stats,gameExecution=False,autoAnalysisReady=False,fullSemanticCoverageEstablished=False,scope='Selected original-byte-verified readers and finite synthetic format models. No native execution, whole-format validity, audible duration, parser implementation or globally safe lifetime claim.')
    return e,models,verification
def main():
    ap=argparse.ArgumentParser();g=ap.add_mutually_exclusive_group(required=True);g.add_argument('--write',action='store_true');g.add_argument('--check',action='store_true');args=ap.parse_args()
    expected=build()
    for name,obj in zip(['evidence.json','model-results.json','verification.json'],expected):
        if args.write:dump(HERE/name,obj)
        else:require(load(HERE/name)==obj,'reproducible '+name)
    if args.check:
        pins=load(HERE/'manifest.json')['files'];actual={p.name for p in HERE.iterdir() if p.is_file() and p.name!='manifest.json'}
        require(set(pins)==actual,'exact study file set')
        for name,pin in pins.items():
            b=(HERE/name).read_bytes();require(len(b)==pin['bytes'] and sha(b)==pin['sha256'],'manifest '+name)
    print(json.dumps(expected[2],sort_keys=True))
if __name__=='__main__':main()
