"""Read-only PE/CLR evidence extraction for the round-three dialog family."""
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'work/trainer/research'
sys.path.insert(0, str(ROOT / 'work/pe/deps'))
import dnfile

SOURCE = Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
raw = SOURCE.read_bytes()
pe = dnfile.dnPE(data=raw)
base = pe.OPTIONAL_HEADER.ImageBase
evidence = json.loads((OUT/'managed_tools_round3_evidence.json').read_text(encoding='utf-8'))
support = json.loads((OUT/'managed_tools_round3_support_cil.json').read_text(encoding='utf-8'))
support.append(json.loads((OUT/'managed_tools_round3_wndproc.json').read_text(encoding='utf-8')))
support.extend(json.loads((OUT/'managed_tools_round3_exit_cil.json').read_text(encoding='utf-8')))
all_bodies = evidence + support
methods = []
field_refs = set()
native = []

def utf16_at(va):
    if not va:
        return None
    assert base <= va < base + pe.OPTIONAL_HEADER.SizeOfImage, hex(va)
    block = pe.get_data(va-base, 16384)
    for i in range(0,len(block)-1,2):
        if block[i:i+2] == b'\0\0':
            return block[:i].decode('utf-16le')
    raise ValueError('Unterminated UTF16 string')

for td in pe.net.mdtables.TypeDef.rows:
    namespace,typename = str(td.TypeNamespace),str(td.TypeName)
    owner = namespace+'.'+typename
    display_owner = owner.lstrip('.')
    seen = {}
    for ix in td.MethodList:
        m=ix.row
        name=str(m.Name)
        number=seen.get(name,0)
        seen[name]=number+1
        display_name=name if number==0 else name+'_'+str(number-1)
        display=('::'+display_name if typename=='<Module>' else display_owner+'::'+display_name)
        meta={'token':hex(0x06000000+ix.row_index),'owner':owner,'name':name,
              'signatureHex':m.Signature.value.hex(),'headerRva':hex(m.Rva),
              'native':bool(m.ImplFlags.miNative),'cil':bool(m.ImplFlags.miIL)}
        if m.ImplFlags.miNative and any(x in name for x in ('get_Language','get_RegionNumber','get_GameStatus','ShowEnd','EndMessage','AnyMessage','fileIoOpen','fileIoWrite','fileIoClose')):
            native.append({**meta,'va':hex(base+m.Rva)})
        body=next((b for b in all_bodies if b['asm']['name']==display),None)
        if body is None:
            continue
        assert m.Rva and m.ImplFlags.miIL
        header=pe.get_data(m.Rva,12)
        if header[0]&3==2:
            hsize,csize,flags,maxstack,local=1,header[0]>>2,2,8,0
        else:
            flags,maxstack,csize,local=struct.unpack('<HHII',header)
            hsize=(flags>>12)*4
        code=pe.get_data(m.Rva+hsize,csize)
        assert len(code)==csize
        sections=[]
        end=m.Rva+hsize+csize
        if flags&8:
            sec=(end+3)&~3
            while True:
                sh=pe.get_data(sec,4)
                size=int.from_bytes(sh[1:4],'little') if sh[0]&0x40 else sh[1]
                sections.append({'rva':hex(sec),'kind':sh[0],'bytesHex':pe.get_data(sec,size).hex()})
                end=sec+size
                if not sh[0]&0x80:break
                sec=(end+3)&~3
        tokens=[]
        for line in body['asm']['lines']:
            off=int(line['addr'],16)-int(body['addr'],16)
            ins=line['instruction']
            if ins.startswith(('ldsfld ','ldsflda ','stsfld ','ldfld ','ldflda ','stfld ')):
                token=int.from_bytes(code[off+1:off+5],'little')
                if token>>24==4:field_refs.add(token&0xffffff)
            if ins.startswith('ldstr '):
                token=int.from_bytes(code[off+1:off+5],'little')
                value=pe.net.user_strings.get(token&0xffffff)
                tokens.append({'ilOffset':off,'token':hex(token),'value':value.value})
        methods.append({**meta,'idaSyntheticAddress':body['addr'],'display':display,
            'headerHex':pe.get_data(m.Rva,hsize).hex(),'codeSize':csize,'codeHex':code.hex(),
            'codeSha256':hashlib.sha256(code).hexdigest(),'maxStack':maxstack,
            'localSignatureToken':hex(local),'initLocals':bool(flags&16),
            'extraSections':sections,'wholeBodyHex':pe.get_data(m.Rva,end-m.Rva).hex(),
            'strings':tokens,'supportOnly':body in support,
            'addressNote':'Synthetic IDA address is not a native RVA. HeaderRva identifies stored CLR IL, not a callable machine-code entrypoint.'})

assert len(methods)==len(all_bodies),(len(methods),len(all_bodies),set(b['asm']['name'] for b in all_bodies)-set(m['display'] for m in methods))
fields=[]
for fr in pe.net.mdtables.FieldRva.rows:
    if fr.Field.row_index not in field_refs:continue
    f=fr.Field.row
    name=str(f.Name)
    fields.append({'name':name,'token':hex(0x04000000+fr.Field.row_index),
                   'signatureHex':f.Signature.value.hex(),'rva':hex(fr.Rva),'va':hex(base+fr.Rva),
                   'first48BytesHex':pe.get_data(fr.Rva,48).hex()})

tables={}
for f in fields:
    rva=int(f['rva'],16)
    if f['name'] in ['Axa.strwText','Axa.strwProcessRunText','Axa.strwGamePlayText','Axa.strwYesText','Axa.strwNoText']:
        pointers=struct.unpack('<6Q',pe.get_data(rva,48))
        tables[f['name']]={'rva':f['rva'],'rawHex':pe.get_data(rva,48).hex(),
                          'entries':[{'index':i,'va':hex(v),'text':utf16_at(v)} for i,v in enumerate(pointers)]}
    if f['name']=='Axa.strwCaption':
        v=struct.unpack('<Q',pe.get_data(rva,8))[0]
        tables[f['name']]={'rva':f['rva'],'va':hex(v),'text':utf16_at(v)}
    if f['name']=='Axa._wtable':
        entries=[]
        for msg in range(8):
            for lang in range(6):
                off=(msg*6+lang)*32
                data=pe.get_data(rva+off,32)
                text,ok,cancel,flags=struct.unpack('<QQQI',data[:28])
                entries.append({'message':msg,'language':lang,'rva':hex(rva+off),'rawHex':data.hex(),
                  'textPointer':hex(text),'text':utf16_at(text),'ok':utf16_at(ok),'cancel':utf16_at(cancel),
                  'confirmation':flags,'reservedHex':data[28:].hex()})
        tables[f['name']]={'rva':f['rva'],'entries':entries,
          'dimensionEvidence':'Field type $ArrayType$$$BY175Umessage_tablew@Axa@@; size independently verified below.'}

layouts=[]
for r in pe.net.mdtables.ClassLayout.rows:
    name=str(r.Parent.row.TypeName)
    if 'message_tablew' in name:
        layouts.append({'type':name,'classSize':r.ClassSize,'packingSize':r.PackingSize})
result={'source':str(SOURCE),'sourceSha256':hashlib.sha256(raw).hexdigest(),
        'methodBodies':methods,'fieldRvas':fields,'nativeBoundaries':native,
        'tables':tables,'typeLayouts':layouts}
(OUT/'managed_tools_round3_metadata.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'methods':len(methods),'fields':len(fields),'native':len(native),'layouts':layouts},ensure_ascii=False,indent=2))
