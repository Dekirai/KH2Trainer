from pathlib import Path
import struct,json
root=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\Modding\openkh\data\kh2')
out=[]
for name in ['obj/M_EX950.mdlx','obj/P_EX100.mdlx','obj/N_EX650_BTL10.mdlx','obj/B_EX120.a.us','obj/B_EX170.a.us']:
 p=root/name
 with p.open('rb') as f:
  h=f.read(16)
  assert h[:4]==b'BAR\x01'
  n=struct.unpack_from('<I',h,4)[0];assert n<10000
  t=f.read(n*16);rows=[]
  for i in range(n):
   typ,link,tag,off,size=struct.unpack_from('<HH4sII',t,i*16)
   if typ in (31,34,48):
    f.seek(off);b=f.read(min(size,48));rows.append(dict(type=typ,tag=tag.hex(),offset=off,length=size,header=b.hex()))
  out.append(dict(name=name,entryCount=n,audio=rows))
print(json.dumps(out,indent=2))
