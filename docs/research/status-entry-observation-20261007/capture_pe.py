"""Capture immutable PE unwind records for the five saved native bodies."""
from pathlib import Path
import json,struct,hashlib
p=Path(__file__).resolve().parent
e=json.loads((p/'evidence.json').read_text(encoding='utf-8'))
b=Path(e['originalPath']).read_bytes()
assert hashlib.sha256(b).hexdigest()==e['originalSha256']
nt=struct.unpack_from('<I',b,60)[0];o=nt+24
base=struct.unpack_from('<Q',b,o+24)[0]
sh=o+struct.unpack_from('<H',b,nt+20)[0]
sections=[struct.unpack_from('<4I',b,sh+40*i+8) for i in range(struct.unpack_from('<H',b,nt+6)[0])]
def disk(rva,n):
 for vs,va,rs,off in sections:
  if va<=rva and rva-va+n<=rs:return b[off+rva-va:off+rva-va+n]
 raise AssertionError(hex(rva))
pr,ps=struct.unpack_from('<II',b,o+112+3*8)
out={'originalSha256':e['originalSha256'],'entries':[]}
for f in e['functions']:
 rva=int(f['addr'],16)-base;end=rva+f['size'];records=[]
 for offset in range(0,ps,12):
  raw=disk(pr+offset,12);a,z,u=struct.unpack('<III',raw)
  if a>=end or z<=rva:continue
  h=disk(u,4);count=h[2];flags=h[0]>>3
  length=4+((count+1)&~1)*2+(12 if flags&4 else 4 if flags&3 else 0)
  records.append({'tableRva':hex(pr+offset),'runtimeBytes':raw.hex(' '),'begin':hex(a),'end':hex(z),
   'unwindRva':hex(u),'unwindBytes':disk(u,length).hex(' '),'version':h[0]&7,'flags':flags,
   'prologSize':h[1],'unwindCodeSlots':count,'frame':h[3]})
 out['entries'].append({'addr':f['addr'],'preceding16':disk(rva-16,16).hex(' '),'records':records})
(p/'pe-unwind.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out,indent=2))
