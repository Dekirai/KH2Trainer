"""Read-only verification, exception tables, initializer arrays and exact-token caller edges."""
from pathlib import Path
import json,struct,hashlib,sys
ROOT=Path(__file__).resolve().parents[3]; OUT=ROOT/'work/trainer/research'
sys.path.insert(0,str(ROOT/'work/pe/deps'))
import dnfile
SOURCE=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
raw=SOURCE.read_bytes(); sha=hashlib.sha256(raw).hexdigest()
d=json.loads((OUT/'managed_tools_round6_metadata.json').read_text());assert sha==d['sourceSha256']
pe=dnfile.dnPE(data=raw); base=pe.OPTIONAL_HEADER.ImageBase
bodies=json.loads((OUT/'managed_tools_round6_evidence.json').read_text())
captured={int(b['addr'],16):b for b in bodies}
readbytes=json.loads((OUT/'managed_tools_round6_cil_bytes.json').read_text())['result']
readbytes={int(b['addr'],16):bytes(int(x,16) for x in b['data'].split()) for b in readbytes}
checks=[];eh=[];verified=[]
for m in d['methodBodies']:
    addr=int(m['idaSyntheticAddress'],16);b=captured[addr]
    assert readbytes[addr]==bytes.fromhex(m['codeHex'])
    assert b['cursor']['done'] is True
    assert len(b['asm']['lines'])==b['instruction_count']==b['total_instructions']
    flags=int.from_bytes(bytes.fromhex(m['headerHex'])[:2],'little')
    checks.append(dict(addr=hex(addr),token=m['token'],codeSize=m['codeSize'],codeSha256=m['codeSha256'],
        instruction_count=b['instruction_count'],actual_instructions=len(b['asm']['lines']),
        complete=True,originalBytesEqualIda=True,initLocals=bool(flags&0x10)))
    verified.append(b)
    for s in m['extraSections']:
        bs=bytes.fromhex(s['bytesHex']);fat=bool(bs[0]&0x40);stride=24 if fat else 12
        assert len(bs)>=4 and (len(bs)-4)%stride==0
        for off in range(4,len(bs),stride):
            v=struct.unpack_from('<IIIIII' if fat else '<HHBHBI',bs,off)
            fl,tstart,tlen,hstart,hlen,value=v
            row=dict(addr=hex(addr),methodToken=m['token'],flags=fl,
                kind={0:'catch',1:'filter',2:'finally',4:'fault'}.get(fl,str(fl)),
                tryOffset=tstart,tryLength=tlen,handlerOffset=hstart,handlerLength=hlen,
                tokenOrFilterOffset=hex(value),clauseBytesHex=bs[off:off+stride].hex())
            assert tstart+tlen<=m['codeSize'] and hstart+hlen<=m['codeSize']
            if fl==0 and value>>24==1:
                tr=pe.net.mdtables.TypeRef.rows[(value&0xffffff)-1]
                row['catchType']=(str(tr.TypeNamespace)+'.'+str(tr.TypeName)).lstrip('.')
            eh.append(row)
methods={};by_display={}
for td in pe.net.mdtables.TypeDef.rows:
    owner=(str(td.TypeNamespace)+'.'+str(td.TypeName)).lstrip('.');seen={}
    for ix in td.MethodList:
        m=ix.row; name=str(m.Name);n=seen.get(name,0);seen[name]=n+1
        display_name=name if n==0 else name+'_'+str(n-1)
        display=('::'+display_name if str(td.TypeName)=='<Module>' else owner+'::'+display_name).replace(' ','_')
        token=0x6000000+ix.row_index
        row=dict(token=hex(token),name=display,rva=hex(m.Rva),native=bool(m.ImplFlags.miNative),cil=bool(m.ImplFlags.miIL))
        methods[token]=row;by_display[display]=(row,m)
field={str(fr.Field.row.Name):fr.Rva for fr in pe.net.mdtables.FieldRva.rows}
tables=[]
for a,z,kind in [('__xi_vt_a','__xi_vt_z','managed-method-tokens'),('__xc_mp_a','__xc_mp_z','managed-method-tokens'),('__xc_ma_a','__xc_ma_z','managed-method-tokens'),('__xi_a','__xi_z','native-pointers'),('__xc_a','__xc_z','native-pointers')]:
    start,end=field[a],field[z]; data=pe.get_data(start,end-start);assert len(data)==end-start and len(data)%8==0
    entries=[]
    for i in range(0,len(data),8):
        value=int.from_bytes(data[i:i+8],'little')
        if not value:continue
        row=dict(slot=i//8,rva=hex(start+i),value=hex(value))
        if kind=='managed-method-tokens':
            assert value<=0xffffffff and value in methods
            row['method']=methods[value]
        entries.append(row)
    tables.append(dict(startField=a,endField=z,startRva=hex(start),endExclusiveRva=hex(end),kind=kind,
        totalSlots=len(data)//8,nonzeroSlots=len(entries),bytesHex=data.hex(),sha256=hashlib.sha256(data).hexdigest(),entries=entries))
selected={int(m['token'],16) for m in d['methodBodies']};callers=[];caller_bodies={}
for p in (ROOT/'work/managed').glob('0x*.json'):
    b=json.loads(p.read_text());name=b['asm']['name'];pair=by_display.get(name)
    if not pair:continue
    meta,m=pair
    if not m.Rva or not m.ImplFlags.miIL:continue
    header=pe.get_data(m.Rva,12)
    if header[0]&3==2:hsize,csize=1,header[0]>>2
    else:hsize=(int.from_bytes(header[:2],'little')>>12)*4;csize=int.from_bytes(header[4:8],'little')
    code=pe.get_data(m.Rva+hsize,csize);assert len(code)==csize
    for line in b['asm']['lines']:
        op=line['instruction'].split(' ',1)[0]
        if op not in ('call','callvirt','newobj','ldftn','ldvirtftn'):continue
        offset=int(line['addr'],16)-int(b['addr'],16);n=2 if op.startswith('ld') else 1
        expected={'call':b'\x28','callvirt':b'\x6f','newobj':b'\x73','ldftn':b'\xfe\x06','ldvirtftn':b'\xfe\x07'}[op]
        assert code[offset:offset+n]==expected,(name,line)
        token=int.from_bytes(code[offset+n:offset+n+4],'little')
        if token not in selected:continue
        callers.append(dict(caller=meta,callerSyntheticAddress=b['addr'],ilOffset=offset,opcode=op,
            bytesHex=code[offset:offset+n+4].hex(),target=methods[token],targetToken=hex(token)))
        caller_bodies[meta['token']]={**meta,'syntheticAddress':b['addr'],'codeSize':csize,'codeHex':code.hex(),
            'codeSha256':hashlib.sha256(code).hexdigest(),'source':'Original PE; call offsets identified with existing work/managed export.'}
result=dict(sourceSha256=sha,verification=checks,bodylessImports=d['bodylessImports'],exceptionClauses=eh,initializerTables=tables,
    incomingCallEdges=callers,callerBodies=list(caller_bodies.values()),
    limitations='Caller edges are direct MethodDef token operands only; dynamic delegates, native COM/vtable calls and externally triggered CLR initialization are not an exhaustive callgraph.')
(OUT/'managed_tools_round6_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
(OUT/'managed_tools_round6_bodyless_imports.json').write_text(json.dumps(dict(sourceSha256=sha,imports=d['bodylessImports']),indent=2),encoding='utf-8')
print(json.dumps(dict(verifiedBodies=len(checks),codeBytes=sum(c['codeSize'] for c in checks),instructions=sum(c['instruction_count'] for c in checks),EHClauses=len(eh),
    tables=[{k:t[k] for k in ('startField','kind','totalSlots','nonzeroSlots')} for t in tables],directEdges=len(callers),callerBodies=len(caller_bodies)),indent=2))
