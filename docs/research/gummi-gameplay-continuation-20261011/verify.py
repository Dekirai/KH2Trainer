"""Read-only original-PE comparison and complete IDA capture normalization.
Run: py -B verify.py [--write]. Requires capstone 5. No IDA/game execution.
"""
import argparse, hashlib, json, pathlib, struct, zipfile, re
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

HERE = pathlib.Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p/'src/KH2Trainer.Core').is_dir())
ORIGINAL = pathlib.Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
WORKCOPY = pathlib.Path(r'C:\Users\shinz\Documents\Codex\2026-10-01\e-steamlibrary-steamapps-common-kingdom-hearts-2\work\kh2_native.exe')
EXPECTED = '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
BASE = 0x140000000

def sha(data): return hashlib.sha256(data).hexdigest()
def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def raw(name): return read(HERE/'raw'/name)['structuredContent']
def parsebytes(s): return bytes(int(x,16) for x in s.split())
def encoded(x): return (json.dumps(x, indent=2, ensure_ascii=False)+'\n').encode()

class PE:
    def __init__(self, path):
        self.data=path.read_bytes()
        assert sha(self.data)==EXPECTED, 'Original EXE hash changed'
        p=struct.unpack_from('<I', self.data, 0x3c)[0]
        assert self.data[p:p+4]==b'PE\0\0'
        n=struct.unpack_from('<H',self.data,p+6)[0]
        z=struct.unpack_from('<H',self.data,p+20)[0]
        assert struct.unpack_from('<Q',self.data,p+24+24)[0]==BASE
        self.sections=[struct.unpack_from('<8sIIII',self.data,p+24+z+40*i) for i in range(n)]
    def bytes(self, va, n):
        rva=va-BASE
        for name,vs,rv,rs,fo in self.sections:
            if rv<=rva and rva+n<=rv+rs:
                off=fo+rva-rv
                return self.data[off:off+n]
        raise AssertionError(f'Not file backed: {va:x}+{n:x}')

def collect(pe):
    md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
    bodies={int(x['addr'],16):parsebytes(x['data']) for x in raw('body-bytes.json')['result']}
    functions=[]; totals={'functions':0,'instructions':0,'extentBytes':0,'instructionBytes':0,'dataOrPaddingBytes':0,'asmPages':0,'pseudocodeLines':0}
    for item in raw('functions.json')['result']:
        f=item['fn']; addr=int(f['addr'],16); size=int(f['size'],16); data=bodies[addr]
        assert len(data)==size and pe.bytes(addr,size)==data
        stem=f'0x{addr:X}'; pages=[]; lines=[]; offset=0
        while True:
            name=f'disasm-{stem}-{offset}.json'; d=raw(name)
            assert int(d['addr'],16)==addr and d['instruction_count']==len(d['asm']['lines'])
            pages.append(dict(d, offset=offset, capturePath='raw/'+name))
            lines.extend(d['asm']['lines']); totals['asmPages']+=1
            if d['cursor'].get('done'): break
            nxt=d['cursor']['next']; assert nxt==offset+d['instruction_count']; offset=nxt
        assert len(lines)==d['total_instructions']
        assert len({l['addr'] for l in lines})==len(lines)
        decoded=[]; covered=set()
        for line in lines:
            ea=int(line['addr'],16); assert addr<=ea<addr+size
            ins=next(md.disasm(data[ea-addr:],ea,count=1))
            assert ins.address==ea and len(ins.bytes)>0
            span=set(range(ea-addr,ea-addr+ins.size)); assert not (covered&span); covered|=span
            decoded.append({'addr':hex(ea),'size':ins.size,'bytes':ins.bytes.hex(' '),'mnemonic':ins.mnemonic,'operands':ins.op_str})
        # Every published instruction is independently decoded, and every gap is retained separately.
        assert decoded[0]['addr']==hex(addr)
        assert all(int(b['addr'],16)>int(a['addr'],16) for a,b in zip(decoded,decoded[1:]))
        gaps=[]; j=0
        while j<size:
            if j in covered: j+=1; continue
            start=j
            while j<size and j not in covered: j+=1
            gaps.append({'addr':hex(addr+start),'size':j-start,'bytes':data[start:j].hex(' '),'kind':'noninstruction bytes in IDA function extent'})
        p=raw(f'decompile-{stem}-0.json')
        assert p['cursor'].get('done') and not p.get('truncated') and p['line_count']==p['total_lines']
        assert int(p['addr'],16)==addr
        functions.append({'addr':hex(addr),'name':f['name'],'size':size,'originalBytes':data.hex(' '),'sha256':sha(data),
            'pages':pages,'disassembly':{'addr':hex(addr),'asm':{'start_ea':hex(addr),'name':f['name'],'lines':lines},'instruction_count':len(lines),'total_instructions':len(lines),'offset':0,'cursor':{'done':True}},'pseudocode':p,'pseudocodeComplete':True,
            'independentDecode':decoded,'noninstructionSpans':gaps})
        totals['functions']+=1; totals['instructions']+=len(lines); totals['extentBytes']+=size
        totals['instructionBytes']+=len(covered); totals['dataOrPaddingBytes']+=size-len(covered); totals['pseudocodeLines']+=p['line_count']
    constants=[]
    for item in raw('constants-bytes.json')['result']:
        a=int(item['addr'],16); b=parsebytes(item['data']); assert pe.bytes(a,len(b))==b
        constants.append({'addr':hex(a),'originalBytes':b.hex(' '),'sha256':sha(b),'float32':list(struct.unpack('<'+'f'*(len(b)//4),b))})
    assert constants[0]['float32']==[0,0,10,10,20]
    return {'schemaVersion':1,'originalExeSha256':EXPECTED,'imageBase':hex(BASE),'functions':functions,'constants':constants},totals

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--write',action='store_true'); args=ap.parse_args()
    pe=PE(ORIGINAL); assert sha(WORKCOPY.read_bytes())==EXPECTED
    evidence,totals=collect(pe)
    context=read(HERE/'context.json')
    assert sha((HERE/context['sourceArchive']).read_bytes())==context['sourceArchiveSha256']
    with zipfile.ZipFile(HERE/context['sourceArchive']) as z:
        assert set(z.namelist())=={x['path'] for x in context['files']}
        for item in context['files']:assert sha(z.read(item['path']))==item['sha256']
        features=json.loads(z.read('src/KH2Trainer/Data/features.json').decode('utf-8-sig'))
        assert len(features)==context['featureCount']==361
        assert max(f['CapabilitySlot'] for f in features)==context['maximumCapability']==484
        assert not any(f.get('CapabilitySlot')==485 or f.get('ValueSlot')==485 or f.get('CommandId')==1485 for f in features)
    dep=read(HERE/'dependencies.json');archive=ROOT/dep['archive']
    assert sha(archive.read_bytes())==dep['sha256']
    with zipfile.ZipFile(archive) as z:
        for item in dep['members']:assert sha(z.read(item['member']))==item['sha256']
    report=read(HERE/'report.json');byaddr={x['addr']:x for x in evidence['functions']};refs=0
    assert len(report['claims'])==10
    for claim in report['claims']:
        assert claim['addr'] in byaddr and claim['Finding'] and claim['Limitations']
        for ref in claim['Evidence']:
            path,_,fragment=ref.partition('#');assert (HERE/path).is_file() or path=='evidence.json'
            if fragment:
                match=re.fullmatch(r'functions\[addr=(0x[0-9a-f]+)\]',fragment)
                assert path=='evidence.json' and match and match[1] in byaddr
            refs+=1
    from model import run
    models=run(pe)
    outputs={'evidence.json':evidence,'model-results.json':models,'verification.json':{'status':'PASS','originalExeSha256':EXPECTED,'workcopyMatchesOriginal':True,'captureTotals':totals,'claims':10,'resolvedReferences':refs,'contextSnapshotAndHistoricalDependencies':'PASS','modelSummary':models['summary'],'scope':'Read-only IDA captures and original-PE comparison; isolated instruction interpreter. No live game or native original execution.'}}
    for name,obj in outputs.items():
        target=HERE/name; data=encoded(obj)
        if args.write: target.write_bytes(data)
        else: assert target.read_bytes()==data, 'Non-reproducible '+name
    manifest=HERE/'manifest.json'
    if manifest.exists() and not args.write:
        m=read(manifest); expected={x['path'] for x in m['files']}; actual={p.relative_to(HERE).as_posix() for p in HERE.rglob('*') if p.is_file() and p!=manifest}
        assert actual==expected, f'Manifest set mismatch {actual^expected}'
        for x in m['files']: assert sha((HERE/x['path']).read_bytes())==x['sha256'], x['path']
    print(json.dumps(outputs['verification.json'],indent=2))

if __name__=='__main__': main()
