"""Independent original PE mapping and paginated IDA instruction review. No execution."""
import hashlib,json,struct
from pathlib import Path
from capstone import Cs,CS_ARCH_X86,CS_MODE_64

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
STUDY=ROOT/'docs/research/voice-request-lifecycle-20261008'
TARGET=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
sha=lambda b:hashlib.sha256(b).hexdigest()
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
checks=0
def check(ok,why):
    global checks
    checks+=1
    if not ok:raise AssertionError(why)

raw=TARGET.read_bytes();check(sha(raw)=='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed','original SHA')
pe=struct.unpack_from('<I',raw,0x3c)[0];check(raw[pe:pe+4]==b'PE\0\0','PE signature')
check(struct.unpack_from('<H',raw,pe+24)[0]==0x20b,'PE32+')
count=struct.unpack_from('<H',raw,pe+6)[0];optional=struct.unpack_from('<H',raw,pe+20)[0]
base=struct.unpack_from('<Q',raw,pe+48)[0];check(base==0x140000000,'base')
sections=[]
for index in range(count):
    vsize,rva,size,offset=struct.unpack_from('<4I',raw,pe+24+optional+40*index+8)
    sections.append((rva,size,offset))
def read(addr,size):
    rva=addr-base;found=[(v,s,p) for v,s,p in sections if v<=rva and rva+size<=v+s]
    check(len(found)==1,('unique file mapping',hex(addr),size))
    v,s,p=found[0];return raw[p+rva-v:p+rva-v+size]

cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
aliases={'retn':'ret','jz':'je','jnz':'jne','jnb':'jae','jnae':'jb','jna':'jbe','jnbe':'ja','cmovz':'cmove','cmovnz':'cmovne','cmovnb':'cmovae','cmovnbe':'cmova','setnz':'setne','setz':'sete','setnb':'setae','setnbe':'seta','sal':'shl','mov':'movabs'}
functions=[];ins={};data_count=0;captures=[]
for name in ['capture.json','additional-capture.json','extra-data.json']:
    path=STUDY/name;j=load(path);captures.append(dict(path=name,sha256=sha(path.read_bytes())))
    for f in j.get('functions',[]):
        addr=int(f['addr'],16);size=f['size'];body=read(addr,size)
        check(body==bytes(int(b,16) for b in f['idaBytes'].split()),('whole IDA body',f['addr']))
        asm=f['disassembly'];rows=asm['asm']['lines'];offset=0;aggregate=[]
        check(asm['instruction_count']==asm['total_instructions']==len(rows),('aggregate count',f['addr']))
        check(asm['cursor'].get('done') and not asm['cursor'].get('cancelled'),('aggregate done',f['addr']))
        for i,page in enumerate(f['pages']):
            check(page['offset']==offset and page['total_instructions']==len(rows),('page offset',f['addr']))
            check(page['instruction_count']==len(page['asm']['lines']),('page count',f['addr']))
            offset+=page['instruction_count'];aggregate+=page['asm']['lines']
            cursor=page['cursor'];check(not cursor.get('cancelled'),('page not cancelled',f['addr']))
            check(cursor.get('done') is True and cursor.get('next') is None if i==len(f['pages'])-1 else not cursor.get('done') and cursor.get('next')==offset,('page continuation',f['addr']))
        check(aggregate==rows and offset==len(rows),('all paginated rows',f['addr']))
        previous_end=addr;gaps=[];decoded_bytes=0
        for row in rows:
            a=int(row['addr'],16)
            check(previous_end<=a<addr+size,('ordered original instruction',hex(a)))
            if a>previous_end:gaps.append(dict(start=hex(previous_end),end=hex(a)))
            decoded=list(cs.disasm(body[a-addr:],a,count=1));check(len(decoded)==1,('instruction decode',hex(a)))
            inst=decoded[0];mn=row['instruction'].split()[0].lower()
            check(inst.address+inst.size<=addr+size,('instruction within body',hex(a)))
            check(mn==inst.mnemonic or aliases.get(mn)==inst.mnemonic or mn=='xchg' and inst.mnemonic=='nop' and bytes(inst.bytes)==b'\x66\x90',('mnemonic',hex(a),mn,inst.mnemonic))
            previous_end=a+inst.size;decoded_bytes+=inst.size;ins[a]=inst
        if previous_end<addr+size:gaps.append(dict(start=hex(previous_end),end=hex(addr+size)))
        functions.append(dict(addr=f['addr'],bytes=size,instructions=len(rows),instructionBytes=decoded_bytes,gaps=gaps))
    for row in j.get('data',[]):
        check(read(int(row['addr'],16),row['size'])==bytes(int(x,16) for x in row['idaBytes'].split()),('data',row['label']))
        data_count+=1

report=dict(success=True,checks=checks,captures=captures,functions=functions,dataSpans=data_count,totalFunctions=len(functions),totalBytes=sum(f['bytes'] for f in functions),totalInstructions=sum(f['instructions'] for f in functions),limits='Whole stored bodies and individual original instruction boundaries verified. Any listed gaps are not claimed decoded code. No game or original code execution; semantic review is separate.')
(HERE/'bytes-result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ['functions','captures']}))
if __name__=='__main__':
    selected=[0x1403CE291,0x1403CE2B8,0x1403CE319,0x1403CE550,0x1401DE874,0x1401DE876,0x1401DD66D,0x1401DD672,0x1401DFDC5,0x1401DFDCC,0x1401DFDEB,0x1403DA99D,0x1403DAAC4,0x1403DAAD5,0x1403CD908,0x1401DE378,0x1401DD912,0x1401DD91B,0x1401DC374,0x14013964A]
    for addr in selected:
        i=ins[addr];print(hex(addr),i.mnemonic,i.op_str)
