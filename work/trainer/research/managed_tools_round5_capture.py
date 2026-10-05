"""Read-only original PE extraction for the CIL host and CLR initialization/unload family."""
from pathlib import Path
import hashlib,json,struct,sys

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'work/trainer/research'
sys.path.insert(0,str(ROOT/'work/pe/deps'))
import dnfile
SOURCE=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
raw=SOURCE.read_bytes(); digest=hashlib.sha256(raw).hexdigest()
assert digest=='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
pe=dnfile.dnPE(data=raw); base=pe.OPTIONAL_HEADER.ImageBase
bodies=json.loads((OUT/'managed_tools_round5_evidence.json').read_text(encoding='utf-8'))
by_name={b['asm']['name']:b for b in bodies}
method_meta={}; mapped={}
for td in pe.net.mdtables.TypeDef.rows:
    namespace,typename=str(td.TypeNamespace),str(td.TypeName)
    owner=(namespace+'.'+typename).lstrip('.'); seen={}
    for ix in td.MethodList:
        m=ix.row; name=str(m.Name); n=seen.get(name,0);seen[name]=n+1
        display_name=name if n==0 else name+'_'+str(n-1)
        display=('::'+display_name if typename=='<Module>' else owner+'::'+display_name)
        display=display.replace(' ','_')
        token=0x06000000+ix.row_index
        meta=dict(token=hex(token),owner=owner,name=name,signatureHex=m.Signature.value.hex(),
            headerRva=hex(m.Rva),native=bool(m.ImplFlags.miNative),cil=bool(m.ImplFlags.miIL))
        if m.ImplFlags.miNative:meta['nativeVa']=hex(base+m.Rva)
        method_meta[token]=meta
        if display in by_name:mapped[display]=(m,meta)
assert len(mapped)==len(bodies)
methods=[]; imports=[]; field_refs=set(); edges=[]; strings=[]
for name,(m,meta) in mapped.items():
    b=by_name[name]
    if m.Rva==0:
        impl=[]
        for row in pe.net.mdtables.ImplMap.rows:
            if row.MemberForwarded.table.name=='MethodDef' and 0x06000000+row.MemberForwarded.row_index==int(meta['token'],16):
                impl.append(dict(module=str(row.ImportScope.row.Name),entryPoint=str(row.ImportName),mappingFlags=int(row.struct.MappingFlags)))
        imports.append({**meta,'idaSyntheticAddress':b['addr'],'display':name,
            'pinvoke':bool(m.Flags.mdPinvokeImpl),'preserveSig':bool(m.ImplFlags.miPreserveSig),
            'methodFlags':int(m.struct.Flags),'implFlags':int(m.struct.ImplFlags),'implMap':impl,
            'claimEligible':False,'reason':'RVA=0 means no stored method body; IDA placeholder is not executable CIL.'})
        continue
    header=pe.get_data(m.Rva,12)
    if header[0]&3==2:hsize,csize,flags,maxstack,local=1,header[0]>>2,2,8,0
    else:
        assert header[0]&3==3
        flags,maxstack,csize,local=struct.unpack('<HHII',header);hsize=(flags>>12)*4
        assert hsize>=12
    code=pe.get_data(m.Rva+hsize,csize);assert len(code)==csize
    sections=[];end=m.Rva+hsize+csize
    if flags&8:
        sec=(end+3)&~3
        while True:
            sh=pe.get_data(sec,4);size=int.from_bytes(sh[1:4],'little') if sh[0]&0x40 else sh[1]
            sections.append(dict(rva=hex(sec),kind=sh[0],bytesHex=pe.get_data(sec,size).hex()))
            end=sec+size
            if not sh[0]&0x80:break
            sec=(end+3)&~3
    for line in b['asm']['lines']:
        off=int(line['addr'],16)-int(b['addr'],16);ins=line['instruction']
        if ins.startswith(('ldsfld ','ldsflda ','stsfld ','ldfld ','ldflda ','stfld ')):
            token=int.from_bytes(code[off+1:off+5],'little')
            if token>>24==4:field_refs.add(token&0xffffff)
        if ins.startswith('ldstr '):
            token=int.from_bytes(code[off+1:off+5],'little')
            us=pe.net.user_strings.get(token&0xffffff)
            strings.append(dict(cilAddress=b['addr'],ilOffset=off,token=hex(token),text=us.value))
        if ins.startswith(('call ','calli ','callvirt ','ldftn ','newobj ')):
            prefix=2 if ins.startswith('ldftn ') else 1
            token=int.from_bytes(code[off+prefix:off+prefix+4],'little')
            edge=dict(cilAddress=b['addr'],ilOffset=off,instruction=ins,token=hex(token))
            if token in method_meta:edge['method']=method_meta[token]
            elif token>>24==0x0a:
                member=pe.net.mdtables.MemberRef.rows[(token&0xffffff)-1]
                edge['memberRef']=dict(name=str(member.Name),signatureHex=member.Signature.value.hex())
                if member.Class.table.name=='MethodDef':edge['varargParent']=method_meta[0x06000000+member.Class.row_index]
            elif token>>24==0x11:
                edge['standaloneSignatureHex']=pe.net.mdtables.StandAloneSig.rows[(token&0xffffff)-1].Signature.value.hex()
            edges.append(edge)
    methods.append({**meta,'idaSyntheticAddress':b['addr'],'display':name,'headerHex':pe.get_data(m.Rva,hsize).hex(),
        'codeSize':csize,'codeHex':code.hex(),'codeSha256':hashlib.sha256(code).hexdigest(),
        'maxStack':maxstack,'localSignatureToken':hex(local),
        'localSignatureHex':pe.net.mdtables.StandAloneSig.rows[(local&0xffffff)-1].Signature.value.hex() if local else None,
        'extraSections':sections,
        'wholeBodyHex':pe.get_data(m.Rva,end-m.Rva).hex(),
        'addressNote':'Synthetic CIL address is not a native RVA; headerRva identifies stored IL, not callable machine code.'})
fields=[]
for fr in pe.net.mdtables.FieldRva.rows:
    if fr.Field.row_index not in field_refs:continue
    f=fr.Field.row;data=pe.get_data(fr.Rva,256)
    entry=dict(name=str(f.Name),token=hex(0x04000000+fr.Field.row_index),signatureHex=f.Signature.value.hex(),
        rva=hex(fr.Rva),nativeVa=hex(base+fr.Rva),first64BytesHex=data[:64].hex())
    if str(f.Name).startswith('??_C@'):
        entry['nullTerminatedBytesHex']=data.split(b'\0',1)[0].hex()
        entry['ascii']=data.split(b'\0',1)[0].decode('ascii',errors='backslashreplace')
    fields.append(entry)
layouts=[]
for row in pe.net.mdtables.ClassLayout.rows:
    name=str(row.Parent.row.TypeName)
    if any(x in name for x in ['FVECTOR2','LanguageSupport','gcroot','GUID','AppInterface']):
        layouts.append(dict(type=name,size=row.ClassSize,packing=row.PackingSize))
referencedFields=[]
for td in pe.net.mdtables.TypeDef.rows:
    for idx in td.FieldList:
        if idx.row_index in field_refs:
            f=idx.row;referencedFields.append(dict(token=hex(0x04000000+idx.row_index),owner=str(td.TypeName),name=str(f.Name),signatureHex=f.Signature.value.hex(),isStatic=bool(f.Flags.fdStatic)))
result=dict(sourceSha256=digest,addressPolicy='CIL addresses are synthetic; nativeVa fields are original PE image VAs.',
    methodBodies=methods,bodylessImports=imports,fields=fields,classLayouts=layouts,callEdges=edges,userStrings=strings,referencedFields=referencedFields)
(OUT/'managed_tools_round5_metadata.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(dict(methods=len(methods),instructions=sum(len(b['asm']['lines']) for b in bodies),fieldCount=len(fields),stringCount=len(strings),layouts=layouts),indent=2))
