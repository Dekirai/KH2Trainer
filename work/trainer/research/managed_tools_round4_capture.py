"""Read-only original PE extraction for the source-searcher/cache family."""
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
bodies=json.loads((OUT/'managed_tools_round4_evidence.json').read_text(encoding='utf-8'))
by_name={b['asm']['name']:b for b in bodies}
method_meta={}; mapped={}
for td in pe.net.mdtables.TypeDef.rows:
    namespace,typename=str(td.TypeNamespace),str(td.TypeName)
    owner=(namespace+'.'+typename).lstrip('.'); seen={}
    for ix in td.MethodList:
        m=ix.row; name=str(m.Name); n=seen.get(name,0);seen[name]=n+1
        display_name=name if n==0 else name+'_'+str(n-1)
        display=('::'+display_name if typename=='<Module>' else owner+'::'+display_name)
        token=0x06000000+ix.row_index
        meta=dict(token=hex(token),owner=owner,name=name,signatureHex=m.Signature.value.hex(),
            headerRva=hex(m.Rva),native=bool(m.ImplFlags.miNative),cil=bool(m.ImplFlags.miIL))
        if m.ImplFlags.miNative:meta['nativeVa']=hex(base+m.Rva)
        method_meta[token]=meta
        if display in by_name:mapped[display]=(m,meta)
assert len(mapped)==len(bodies)
methods=[]; field_refs=set(); edges=[]
for name,(m,meta) in mapped.items():
    b=by_name[name]; header=pe.get_data(m.Rva,12)
    if header[0]&3==2:hsize,csize,flags,maxstack,local=1,header[0]>>2,2,8,0
    else:
        flags,maxstack,csize,local=struct.unpack('<HHII',header);hsize=(flags>>12)*4
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
        'maxStack':maxstack,'localSignatureToken':hex(local),'extraSections':sections,
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
    if any(x in name for x in ['SoundList','findeList','KNMList','KNAList','kh2ModelScarcher','kh2MotionScarcher','kh2SoundSearcher']):
        layouts.append(dict(type=name,size=row.ClassSize,packing=row.PackingSize))
result=dict(sourceSha256=digest,addressPolicy='CIL addresses are synthetic; nativeVa fields are original PE image VAs.',
    methodBodies=methods,fields=fields,classLayouts=layouts,callEdges=edges)
(OUT/'managed_tools_round4_metadata.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(dict(methods=len(methods),instructions=sum(len(b['asm']['lines']) for b in bodies),fields=fields,layouts=layouts),indent=2))
