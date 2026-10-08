"""Verify paginated IDA evidence against original disk PE bytes. Never opens a process."""
from pathlib import Path
import hashlib,json,re,struct

folder=Path(__file__).resolve().parent
ev=json.loads((folder/'evidence.json').read_text(encoding='utf-8-sig'))
modules={}
for module in ev['modules']:
    raw=Path(module['originalPath']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==module['originalSha256'],module['id']
    pe=struct.unpack_from('<I',raw,0x3c)[0]
    assert raw[:2]==b'MZ' and raw[pe:pe+4]==b'PE\0\0'
    section_start=pe+24+struct.unpack_from('<H',raw,pe+20)[0]
    count=struct.unpack_from('<H',raw,pe+6)[0]
    sections=[struct.unpack_from('<4I',raw,section_start+40*i+8) for i in range(count)]
    modules[module['id']]={'raw':raw,'base':int(module['imageBase'],16),'sections':sections,
        'functions':0,'instructions':0,'codeBytes':0,'dataBytes':0,'sha256':module['originalSha256']}
def disk(module,address,size):
    m=modules[module]; rva=address-m['base']
    for virtual_size,va,raw_size,offset in m['sections']:
        if va<=rva and rva-va+size<=raw_size:
            start=offset+rva-va
            assert start+size<=len(m['raw'])
            return m['raw'][start:start+size]
    raise AssertionError(('No backed PE span',module,hex(address),size))
def unhex(value):
    return bytes(int(b,16) for b in value.split())
seen=set()
for f in ev['functions']:
    key=(f['module'],f['addr']);assert key not in seen;seen.add(key)
    address=int(f['addr'],16);size=f['size']
    assert size==int(f['analysis']['size'],16)
    body=unhex(f['bytes']);assert len(body)==size and body==disk(f['module'],address,size),key
    joined=[];next_offset=0
    for i,p in enumerate(f['pages']):
        rows=p['asm']['lines'];cursor=p['cursor']
        assert p['offset']==next_offset and rows
        assert not cursor.get('cancelled',False)
        assert p['instruction_count']==len(rows)
        assert p['total_instructions']==f['total_instructions']
        joined+=rows;next_offset+=len(rows)
        if i+1<len(f['pages']):
            assert not cursor.get('done',False) and cursor.get('next')==next_offset
        else:
            assert cursor.get('done') is True and 'next' not in cursor
    assert f['asm']['lines']==joined
    assert f['instruction_count']==f['total_instructions']==len(joined)
    assert f['cursor'].get('done') is True and not f['cursor'].get('cancelled',False)
    addresses=[int(row['addr'],16) for row in joined]
    assert addresses==sorted(set(addresses)) and addresses[0]==address
    assert all(address<=a<address+size for a in addresses)
    assert all(row.get('instruction','').strip() for row in joined)
    pseudo=f['pseudocode'];next_line=0
    for i,p in enumerate(pseudo['pages']):
        assert p['offset']==next_line and p['code'] and not p.get('error')
        assert not p['cursor'].get('cancelled',False)
        assert len(p['code'].splitlines())==p['line_count']
        assert p['total_lines']==pseudo['total_lines']
        next_line+=p['line_count']
        if i+1<len(pseudo['pages']):
            assert p['cursor'].get('next')==next_line and not p['cursor'].get('done',False)
        else: assert p['cursor'].get('done') is True
    assert next_line==pseudo['line_count']==pseudo['total_lines']
    assert pseudo['code']=='\n'.join(p['code'] for p in pseudo['pages'])
    m=modules[f['module']];m['functions']+=1;m['instructions']+=len(joined);m['codeBytes']+=size
locators=[]
for d in ev['data']:
    body=unhex(d['bytes'])
    assert len(body)==d['size'] and body==disk(d['module'],int(d['addr'],16),d['size'])
    modules[d['module']]['dataBytes']+=len(body)
    if 'mask' in d:
        expected=int(d['expectedRetailTarget'],16);actual=disk('retail',expected,len(body))
        assert len(d['mask'])==len(body)
        assert all(mask=='?' or b==a for mask,b,a in zip(d['mask'],body,actual)),d['purpose']
        pattern=b''.join(b'.' if mask=='?' else re.escape(bytes([b])) for b,mask in zip(body,d['mask']))
        matches=list(re.finditer(pattern,modules['retail']['raw'],flags=re.DOTALL))
        match_addresses=[]
        for match in matches:
            for _,va,n,offset in modules['retail']['sections']:
                if offset<=match.start()<offset+n:
                    match_addresses.append(hex(modules['retail']['base']+va+match.start()-offset));break
        assert match_addresses==[hex(expected)],(d['purpose'],match_addresses)
        locators.append({'source':d['addr'],'purpose':d['purpose'],'uniqueOriginalTarget':hex(expected)})
package_table=next(d for d in ev['data'] if d['module']=='retail' and d['addr']=='0x140715600')
data=unhex(package_table['bytes']);assert len(data)%272==0
package_rows=[{'row':i//272,'path':data[i:i+260].split(b'\0')[0].decode('ascii'),'decodeFlag':data[i+260]} for i in range(0,len(data),272)]
result={'success':True,'modules':{name:{k:v for k,v in m.items() if k not in ('raw','base','sections')} for name,m in modules.items()},
    'functions':len(ev['functions']),'instructions':sum(m['instructions'] for m in modules.values()),
    'originalCodeBytes':sum(m['codeBytes'] for m in modules.values()),'originalDataBytes':sum(m['dataBytes'] for m in modules.values()),
    'uniquePanaceaLocators':locators,'nativePackageTableRows':package_rows,
    'limits':'Verifies original disk identity, bytes, complete pagination and reported counts. It does not prove live hook/configuration state or semantic coverage of every dependency.'}
(folder/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
