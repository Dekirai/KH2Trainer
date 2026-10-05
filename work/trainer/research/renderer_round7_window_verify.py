"""Verify the exact implementation pins against the untouched source PE and full IDA ASM."""
from pathlib import Path
import hashlib,json,re,struct
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
EXE=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
EXPECTED='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
def sha(b): return hashlib.sha256(b).hexdigest()
def main():
    pe=EXE.read_bytes();assert sha(pe)==EXPECTED
    head=struct.unpack_from('<I',pe,0x3c)[0]
    count=struct.unpack_from('<H',pe,head+6)[0];opt=struct.unpack_from('<H',pe,head+20)[0]
    sections=[]
    for i in range(count):
        p=head+24+opt+i*40
        size,rva,rawsize,raw=struct.unpack_from('<IIII',pe,p+8)
        sections.append((rva,rawsize,raw))
    def read(rva,n):
        for start,size,raw in sections:
            if start<=rva and rva+n<=start+size:return pe[raw+rva-start:raw+rva-start+n]
        raise ValueError('Unmapped RVA '+hex(rva))
    evidence=json.loads((HERE/'renderer_round7_window_evidence.json').read_text(encoding='utf-8'))
    source_bytes=(ROOT/'trainer/Native/WindowDisplayFeatures.inl').read_bytes()
    source=source_bytes.decode('utf-8')
    result=[]
    for name,rva,size in [('SetterCode',0x124fe0,590),('CookieCode',0x439a60,33)]:
        row=next(x for x in evidence['bytes']['result'] if int(x['addr'],16)==0x140000000+rva)
        captured=bytes(int(x,16) for x in row['data'].split())
        body=re.search(r'constexpr BYTE '+name+r'\[\]=\{([^}]+)\}',source).group(1)
        pin=bytes(int(x,16) for x in body.split(','))
        native=read(rva,size)
        assert pin==captured==native and len(pin)==size
        asm=next(x for x in evidence['functions'] if int(x['addr'],16)==0x140000000+rva)
        lines=asm['asm']['lines'];addresses=[int(x['addr'],16) for x in lines]
        assert len(lines)==asm['instruction_count']==asm['total_instructions']
        assert asm['cursor']=={'done':True} and len(addresses)==len(set(addresses))
        assert addresses==sorted(addresses) and addresses[0]==0x140000000+rva
        assert all(0x140000000+rva<=a<0x140000000+rva+size for a in addresses)
        result.append(dict(addr=hex(0x140000000+rva),bytes=size,instructions=len(lines),sha256=sha(pin),equal=True))
    constants=[]
    for rva,value in [(0x5a9cbc,9.0),(0x623bc4,16.0),(0x5a9c9c,0.0625)]:
        data=read(rva,4);assert struct.unpack('<f',data)[0]==value
        constants.append(dict(rva=hex(rva),float32=value,hex=data.hex()))
    # Check the RIP-relative cookie operands in both original native bodies.
    setter=read(0x124fe0,590);cookie=read(0x439a60,33)
    assert 0x125008+7+struct.unpack_from('<i',setter,0x125008-0x124fe0+3)[0]==0x7591f8
    assert 0x439a60+7+struct.unpack_from('<i',cookie,3)[0]==0x7591f8
    output=dict(status='PASS',original_sha256=EXPECTED,source_sha256=sha(source_bytes),functions=result,
                constants=constants,bytes=sum(x['bytes']for x in result),instructions=sum(x['instructions']for x in result),
                limitations=['Function bodies and constants match; runtime import identities are checked by the module.',
                            'This does not test graphics drivers, monitor changes or successful window resizing.'])
    (HERE/'renderer_round7_window_validation.json').write_text(json.dumps(output,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:output[k]for k in ['status','bytes','instructions']}))
if __name__=='__main__':main()
