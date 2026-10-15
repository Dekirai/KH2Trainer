"""Verify frozen native implementation evidence. No builds, game or IDA access."""
import argparse,hashlib,json,pathlib,re,struct,zipfile
HERE=pathlib.Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'src/KH2Trainer.Core').is_dir())
EXE=pathlib.Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def encoded(v):return (json.dumps(v,indent=2)+'\n').encode()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');parser.add_argument('--check-current-product',action='store_true');args=parser.parse_args()
    info=read(HERE/'implementation.json');data=EXE.read_bytes();assert sha(data)==info['originalSha256']
    p=struct.unpack_from('<I',data,0x3c)[0];n=struct.unpack_from('<H',data,p+6)[0];z=struct.unpack_from('<H',data,p+20)[0]
    sections=[struct.unpack_from('<8sIIII',data,p+24+z+40*i) for i in range(n)]
    def original(rva,size):
        for _,vs,rv,rs,fo in sections:
            if rv<=rva and rva+size<=rv+rs:return data[fo+rva-rv:fo+rva-rv+size]
        raise AssertionError('Signature outside original file')
    for item in info['sourcePins']:
        assert sha((HERE/item['snapshot']).read_bytes())==item['sha256']
        if args.check_current_product:assert sha((ROOT/item['path']).read_bytes())==item['sha256'],item['path']
    source=(HERE/info['sourcePins'][0]['snapshot']).read_text(encoding='utf-8-sig')
    arrays={m[0]:bytes(int(x,16) for x in re.findall(r'0x([0-9a-fA-F]+)',m[1])) for m in re.findall(r'constexpr BYTE (Request\w+)\[\]\s*=\s*\{([^}]+)\}',source)}
    table=re.search(r'const Code requestCode\[\]=\{(.+?)\};',source,re.S)[1]
    signatures=[]
    for rva,name,size in re.findall(r'\{(RequestSetterRva|0x[0-9A-Fa-f]+),(\w+),sizeof\((\w+)\)\}',table):
        assert name==size;rva=0x2312b0 if rva=='RequestSetterRva' else int(rva,16);b=arrays[name]
        assert b==original(rva,len(b)),name
        signatures.append({'rva':hex(rva),'array':name,'bytes':len(b),'sha256':sha(b),'originalMatch':True})
    assert len(signatures)==16 and signatures[0]['array']=='RequestSetterCode' and arrays['RequestSetterCode']==bytes.fromhex('83 49 44 02 c3')
    assert {x['array'] for x in signatures}==set(arrays)
    # Verify the old charge/reads section is unchanged, apart from the explicit new action route/capability.
    studyPaths=[ROOT/info['study']['path'],ROOT/'artifacts/gummi-gameplay-continuation-20261011']
    study=next(p for p in studyPaths if p.is_dir() and sha((p/'manifest.json').read_bytes())==info['study']['manifestSha256'])
    oldctx=read(study/'context.json');archive=study/oldctx['sourceArchive'];assert sha(archive.read_bytes())==oldctx['sourceArchiveSha256']
    with zipfile.ZipFile(archive) as z:old=z.read('src/KH2Trainer.Bridge/GummiExtraFeatures.inl').decode('utf-8-sig').replace('\r\n','\n')
    new=source
    start=new.index('// A normal input request only.');end=new.index('\n}\nbool GummiExtraHandle',start)
    stripped=new[:start]+new[end+1:]
    stripped=stripped.replace('    if(slot==gummi_extra::RequestSlot)return gummi_extra::RequestHandle(host,args,result);\n','')
    stripped=stripped.replace('SupportCapability(slot);SupportCapability(gummi_extra::RequestSlot);','SupportCapability(slot);')
    assert stripped==old,'Existing charge/snapshot code changed'
    for item in info['testEvidence']:
        path=HERE/item['path'];assert sha(path.read_bytes())==item['sha256']
        text=path.read_text(encoding='utf-8-sig');assert re.search(re.escape(item['suite'])+rf": {item['checks']} checks, 0 failures",text)
    result={'status':'PASS','originalSha256':info['originalSha256'],'signatures':signatures,'signatureSpans':16,'signatureBytes':sum(x['bytes'] for x in signatures),'oldChargeAndSnapshotsUnchanged':True,'sourcePins':len(info['sourcePins']),'syntheticTests':[{'suite':x['suite'],'checks':x['checks'],'failures':0} for x in info['testEvidence']],'scope':'Original-byte/static/source integrity and frozen recorded synthetic logs; this verifier does not rerun tests or imply live gameplay validation.'}
    target=HERE/'verification.json';out=encoded(result)
    if args.write:target.write_bytes(out)
    else:assert target.read_bytes()==out
    if not args.write:
        manifest=HERE/'manifest.json';m=read(manifest);expected={x['path'] for x in m['files']}
        actual={p.relative_to(HERE).as_posix() for p in HERE.rglob('*') if p.is_file() and p!=manifest}
        assert actual==expected,actual^expected
        for item in m['files']:assert sha((HERE/item['path']).read_bytes())==item['sha256'],item['path']
    print(json.dumps({k:v for k,v in result.items() if k!='signatures'},indent=2))
if __name__=='__main__':main()
