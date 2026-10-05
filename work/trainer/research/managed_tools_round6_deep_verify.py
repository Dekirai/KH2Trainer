"""Independent IL boundary/operand verification and native original-PE comparison."""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[3];P=ROOT/'work/trainer/research'
sys.path.insert(0,str(ROOT/'work/pe/deps'))
import pefile
m=json.loads((P/'managed_tools_round6_metadata.json').read_text())
b={r['addr']:r for r in json.loads((P/'managed_tools_round6_evidence.json').read_text())}
v=json.loads((P/'managed_tools_round6_verification.json').read_text())
opinfo=json.loads((P/'managed_tools_round6_opcodes.json').read_text(encoding='utf-8-sig'))
opcodes={r['value']:r for r in opinfo['opcodes']}
sizes={'InlineNone':0,'ShortInlineVar':1,'InlineVar':2,'ShortInlineI':1,'InlineI':4,'InlineI8':8,
    'ShortInlineBrTarget':1,'InlineBrTarget':4,'ShortInlineR':4,'InlineR':8,'InlineMethod':4,
    'InlineField':4,'InlineType':4,'InlineTok':4,'InlineSig':4,'InlineString':4}
methods=[];calls=[]
for body in m['methodBodies']:
    addr=body['idaSyntheticAddress'];code=bytes.fromhex(body['codeHex']);offset=0;rows=[]
    while offset<len(code):
        start=offset;value=code[offset];offset+=1
        if value==254:value=0xfe00|code[offset];offset+=1
        op=opcodes[value];operand=op['operand']
        assert op['size']==offset-start
        if operand=='InlineSwitch':size=4+4*int.from_bytes(code[offset:offset+4],'little')
        else:size=sizes[operand]
        assert offset+size<=len(code)
        raw=code[offset:offset+size];row=dict(offset=start,size=offset+size-start,opcode=op['name'],bytesHex=code[start:offset+size].hex())
        if operand in ['ShortInlineBrTarget','InlineBrTarget']:
            row['target']=offset+size+int.from_bytes(raw,'little',signed=True)
        elif operand=='InlineSwitch':
            row['targets']=[offset+size+struct.unpack_from('<i',raw,i)[0] for i in range(4,size,4)]
        elif operand in ['InlineMethod','InlineField','InlineType','InlineTok','InlineSig','InlineString']:
            row['token']=hex(int.from_bytes(raw,'little'))
        elif size and operand not in ['InlineR','ShortInlineR']:
            row['operandValue']=int.from_bytes(raw,'little',signed=operand in ['ShortInlineI','InlineI','InlineI8'])
        rows.append(row);offset+=size
    listing=b[addr]; assert listing['cursor']['done'] is True
    assert len(rows)==len(listing['asm']['lines'])==listing['instruction_count']==listing['total_instructions']
    boundaries={r['offset'] for r in rows};boundaries.add(len(code))
    for row,line in zip(rows,listing['asm']['lines']):
        assert int(line['addr'],16)==int(addr,16)+row['offset']
        assert line['instruction'].split(' ',1)[0]==row['opcode'],(addr,row,line)
        if 'target' in row:assert row['target'] in boundaries
        for target in row.get('targets',[]):assert target in boundaries
        if row['opcode'] in ['call','callvirt','calli','ldftn','ldvirtftn','newobj']:
            edge=[x for x in m['callEdges'] if x['cilAddress']==addr and x['ilOffset']==row['offset']]
            assert len(edge)==1 and edge[0]['token']==row['token']
            calls.append(dict(addr=addr,offset=row['offset'],token=row['token'],opcode=row['opcode']))
    for eh in v['exceptionClauses']:
        if eh['addr']!=addr:continue
        for x in [eh['tryOffset'],eh['tryOffset']+eh['tryLength'],eh['handlerOffset'],eh['handlerOffset']+eh['handlerLength']]:assert x in boundaries
    methods.append(dict(addr=addr,token=body['token'],complete=True,instructions=len(rows),codeBytes=len(code),decoded=rows))

source=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
raw=source.read_bytes();sha=hashlib.sha256(raw).hexdigest();assert sha==m['sourceSha256']
pe=pefile.PE(data=raw);base=pe.OPTIONAL_HEADER.ImageBase
native=json.loads((P/'managed_tools_round6_native_evidence.json').read_text())
native_verified=[]
for f in native['functions']:
    asm=f['disassembly'];a=int(f['addr'],16)
    data=bytes(int(s,16) for s in f['bytes']['result'][0]['data'].split())
    assert pe.get_data(a-base,len(data))==data
    assert len(asm['asm']['lines'])==asm['instruction_count']==asm['total_instructions'] and asm['cursor']['done'] is True
    assert int(f['analysis']['size'],16)==len(data)
    native_verified.append(dict(addr=f['addr'],fileOffset=hex(pe.get_offset_from_rva(a-base)),size=len(data),
        instructions=asm['instruction_count'],originalBytesEqualIda=True,bytesHex=data.hex(),sha256=hashlib.sha256(data).hexdigest()))
imports={i.address:(dll.dll.decode(),i.name.decode() if i.name else f'ordinal:{i.ordinal}') for dll in pe.DIRECTORY_ENTRY_IMPORT for i in dll.imports}
thunks=[]
for a in [0x140471ebc,0x14043ad16,0x14043ad1c]:
    data=pe.get_data(a-base,6);assert data[:2]==b'\xff\x25'
    iat=a+6+int.from_bytes(data[2:6],'little',signed=True);assert iat in imports
    dll,name=imports[iat]
    thunks.append(dict(nativeVa=hex(a),bytesHex=data.hex(),instruction='jmp qword ptr [rip+disp32]',iatVa=hex(iat),module=dll,importName=name,
        evidence='Original PE thunk bytes and IMAGE_IMPORT_DESCRIPTOR; no target library function executed.'))
result=dict(sourceSha256=sha,scope='All154 selected original IL streams decoded using runtime opcode metadata; full operand boundaries checked against fresh IDA. Five native boundary bodies match original PE, with import thunk targets independently resolved from PE.',
    realBodies=len(methods),originalCodeBytes=sum(r['codeBytes'] for r in methods),actualInstructions=sum(r['instructions'] for r in methods),
    directOrIndirectCallOperands=len(calls),exceptionClauses=len(v['exceptionClauses']),methods=methods,callOperands=calls,nativeBodies=native_verified,importThunks=thunks)
(P/'managed_tools_round6_deep_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:x for k,x in result.items() if k not in ['methods','callOperands','nativeBodies']},indent=2))
