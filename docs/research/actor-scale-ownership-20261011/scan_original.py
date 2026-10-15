from pathlib import Path
import capstone,json,hashlib,struct
H=Path(__file__).resolve().parent
P=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
b=P.read_bytes();assert hashlib.sha256(b).hexdigest()=='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
pe=struct.unpack_from('<I',b,60)[0]; opt=pe+24
ns=struct.unpack_from('<H',b,pe+6)[0];os=struct.unpack_from('<H',b,pe+20)[0]
base=struct.unpack_from('<Q',b,opt+24)[0]
sections=[struct.unpack_from('<IIII',b,opt+os+40*i+8) for i in range(ns)]
def read(r,n):
 offsets=[p+r-v for vs,v,size,p in sections if v<=r and r+n<=v+size]
 assert len(offsets)==1
 return b[offsets[0]:offsets[0]+n]
exc,es=struct.unpack_from('<II',b,opt+112+3*8)
entries=list(struct.iter_unpack('<III',read(exc,es)))
c=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);c.detail=True
out=[]
for a,z,unwind in entries:
 if not (0x1b1000<=a<0x1ce000):continue
 for i in c.disasm(read(a,z-a),base+a):
  if any(x.type==capstone.CS_OP_MEM and x.mem.disp==80 for x in i.operands) and (i.mnemonic in ['call','jmp'] or i.mnemonic=='mov' and i.operands[0].type==capstone.CS_OP_REG and i.op_str.startswith('rax,')):
   out.append({'function':hex(base+a),'address':hex(i.address),'asm':i.mnemonic+' '+i.op_str})
(H/'original-slot80-candidates.json').write_text(json.dumps({'scope':'Positive original PE Capstone candidates in .pdata function starts 1B1000..1CE000 only; no completeness or target identity claim.','matches':out},indent=2)+'\n')
print(json.dumps(out,indent=2))
