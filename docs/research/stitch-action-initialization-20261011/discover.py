"""Read-only original-PE candidate discovery; raw candidates are not claims."""
from pathlib import Path
import bisect, capstone, hashlib, json, struct
H=Path(__file__).resolve().parent
P=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
B=P.read_bytes(); SHA=hashlib.sha256(B).hexdigest()
assert SHA=='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
pe=struct.unpack_from('<I',B,60)[0]; opt=pe+24; base=struct.unpack_from('<Q',B,opt+24)[0]
sections=[]
for k in range(struct.unpack_from('<H',B,pe+6)[0]):
 s=opt+struct.unpack_from('<H',B,pe+20)[0]+40*k
 vs,rva,size,off=struct.unpack_from('<4I',B,s+8)
 sections.append((B[s:s+8].rstrip(b'\0').decode(),rva,size,off))
def raw(rva,n):
 for _,r,size,off in sections:
  if r<=rva and rva+n<=r+size:return B[off+rva-r:off+rva-r+n]
 raise ValueError(hex(rva))
er,ez=struct.unpack_from('<II',B,opt+112+3*8)
runtime=list(struct.iter_unpack('<III',raw(er,ez)));starts=[a for a,b,u in runtime]
cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);cs.detail=True
def enclosing(r):
 j=bisect.bisect_right(starts,r)-1
 return [hex(v)for v in runtime[j]]if j>=0 and r<runtime[j][1]else None
if __name__=='__main__':
 out=[];targets={0x1c8610,0x1c8700,0x1c8440}
 for name,rva,size,off in sections:
  if name!='.text':continue
  d=B[off:off+size]
  for j in range(len(d)-7):
   if d[j] not in (0x48,0x4c) or d[j+1] not in (0x8d,0x89,0x8b) or d[j+2]&0xc7!=5:continue
   target=rva+j+7+struct.unpack_from('<i',d,j+3)[0]
   if target not in targets and not 0x724340<=target<0x724340+7*72:continue
   x=next(cs.disasm(d[j:j+16],base+rva+j,count=1),None)
   if x:out.append(dict(addr=hex(x.address),target=hex(base+target),asm=x.mnemonic+' '+x.op_str,bytes=x.bytes.hex(),pdata=enclosing(rva+j)))
 (H/'discovery.json').write_text(json.dumps(dict(originalSha256=SHA,scope='Selected raw RIP-relative candidates only; validate full enclosing bodies with IDA before claims.',matches=out),indent=2)+'\n')
 print(json.dumps(out,indent=2))
