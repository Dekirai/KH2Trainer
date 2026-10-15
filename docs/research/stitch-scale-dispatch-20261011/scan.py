from pathlib import Path
import struct,hashlib,json,capstone
H=Path(__file__).resolve().parent
P=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
b=P.read_bytes();assert hashlib.sha256(b).hexdigest()=='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
pe=struct.unpack_from('<I',b,60)[0];o=pe+24;n=struct.unpack_from('<H',b,pe+6)[0];sz=struct.unpack_from('<H',b,pe+20)[0];base=struct.unpack_from('<Q',b,o+24)[0]
cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);cs.detail=True
out=[]
for k in range(n):
 s=o+sz+40*k;name=b[s:s+8].rstrip(b'\0').decode();vs,rva,length,pos=struct.unpack_from('<4I',b,s+8)
 if name!='.text':continue
 for j in range(length-4):
  if b[pos+j]!=255 or b[pos+j+1] not in list(range(0x50,0x58))+list(range(0x60,0x68)):continue
  i=next(cs.disasm(b[pos+j:pos+j+10],base+rva+j,count=1),None)
  if i and i.mnemonic in ('call','jmp') and any(x.type==capstone.CS_OP_MEM and x.mem.disp==80 for x in i.operands):out.append({'addr':hex(i.address),'asm':i.mnemonic+' '+i.op_str,'bytes':i.bytes.hex()})
(H/'slot80-byte-candidates.json').write_text(json.dumps({'scope':'Positive raw byte candidates only; not instruction boundaries until IDA and enclosing body validation. A REX prefix may precede these bytes. No absence claim.','matches':out},indent=2)+'\n')
print(json.dumps({'rawSlot80Candidates':len(out)}))
