"""Normalize only the selected Root IDA captures and pinned prior bodies."""
import hashlib,json,pathlib,runpy,struct
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
H=pathlib.Path(__file__).resolve().parent
ROOT=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir())
BASE=0x140000000
EXE=pathlib.Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
PIN='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(b):return hashlib.sha256(b).hexdigest()
def write(n,x):(H/n).write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def addr(x):return int(x,16)
class PE:
 def __init__(self):
  self.data=EXE.read_bytes();assert sha(self.data)==PIN
  nt=struct.unpack_from('<I',self.data,60)[0];optional=nt+24
  assert self.data[nt:nt+4]==b'PE\0\0' and struct.unpack_from('<Q',self.data,optional+24)[0]==BASE
  table=optional+struct.unpack_from('<H',self.data,nt+20)[0]
  self.sections=[struct.unpack_from('<III',self.data,table+i*40+12) for i in range(struct.unpack_from('<H',self.data,nt+6)[0])]
 def raw(self,at,n):
  r=at-BASE;matches=[self.data[p+r-v:p+r-v+n] for v,size,p in self.sections if v<=r and r+n<=v+size]
  assert n>0 and len(matches)==1,(hex(at),n)
  return matches[0]
def derive():
 pe=PE();sizes={};blobs={}
 for p in H.glob('root-lookup*.json'):
  for r in read(p)['result']:
   f=r['fn'];assert f is not None
   a,n=addr(f['addr']),addr(f['size'])
   assert a not in sizes or sizes[a]==n;sizes[a]=n
 for p in H.glob('root-bytes*.json'):
  for r in read(p)['result']:
   a=addr(r['addr']);b=bytes(int(x,16) for x in r['data'].split())
   assert b==pe.raw(a,len(b)) and (a not in blobs or blobs[a]==b);blobs[a]=b
 rows=[]
 for p in sorted(H.glob('root-disasm-*.json')):
  d=read(p);a=addr(d['addr']);dec=read(H/('root-decompile-'+hex(a)+'.json'));b=blobs[a]
  assert len(b)==sizes[a] and d['cursor']['done'] and d['instruction_count']==d['total_instructions']==len(d['asm']['lines'])
  assert dec['cursor']['done'] and not dec['truncated'] and dec['line_count']==dec['total_lines']==len(dec['code'].splitlines())
  rows.append(dict(addr=hex(a),name=d['asm']['name'],size=len(b),complete=True,originalBytes=b.hex(' '),sha256=sha(b),pages=[d],disassembly=d,pseudocode=dec,sourceMetadata=dict(freshCapture=True,source=p.name,operator='/root',session='28e14b48',autoAnalysisReady=False)))
 src=ROOT/'docs/research/collision-position-dispatch-20261011/evidence.json';old=read(src)
 assert sha(src.read_bytes())=='67f0dee6056f7802f93316bdd6c6d6295d79f8fe324f3d47a8d6430cd397a0f0'
 assert sha((src.parent/'manifest.json').read_bytes())=='b83e6023f60e527731c2d26061628049cdba744de26770a6de15bf35d5b7be9a'
 deps=[{'path':src.relative_to(ROOT).as_posix(),'sha256':sha(src.read_bytes()),'manifestSha256':sha((src.parent/'manifest.json').read_bytes()),'bodies':['0x14040f1c0','0x14040f610','0x1403d1960']}]
 for a in deps[0]['bodies']:
  f=next(f for f in old['functions'] if f['addr']==a)
  r={k:f[k] for k in ('addr','name','size','originalBytes','pages','disassembly','pseudocode')}
  r.update(complete=True,sha256=sha(bytes.fromhex(r['originalBytes'])),sourceMetadata={'freshCapture':False,'source':deps[0]['path']+'#functions[addr='+a+']','sourceSha256':deps[0]['sha256']});rows.append(r)
 assert len(rows)==len({r['addr'] for r in rows})
 parser=ROOT/'scripts/update-analysis-coverage.py';api=runpy.run_path(str(parser),run_name='selected_baseline_read')
 _,cov,_=api['load_baseline']();inventory={api['address'](f['address']):f for f in cov['functions'] if f['domain']=='native'}
 functions=[];ranges=[]
 for r in rows:
  a=addr(r['addr']);b=bytes.fromhex(r['originalBytes']);assert b==pe.raw(a,r['size'])
  if a in inventory:
   assert inventory[a]['size']==r['size'];functions.append(r)
  else:
   r.update(end_exclusive=hex(a+r['size']),asm=r['disassembly']['asm'],observed_line_count=len(r['disassembly']['asm']['lines']),classification='separate_code_range_not_inventory_function');ranges.append(r)
 cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
 for r in rows:
  start=addr(r['addr']);body=bytes.fromhex(r['originalBytes']);covered=set()
  for line in r['disassembly']['asm']['lines']:
   at=addr(line['addr']);assert start<=at<start+len(body)
   i=next(cs.disasm(body[at-start:],at,count=1));span=set(range(at,at+i.size))
   assert at+i.size<=start+len(body) and not covered&span;covered|=span
  assert covered==set(range(start,start+len(body))),r['addr']+' incomplete captured instruction span'
 data=[]
 for a in [BASE+0x5c5e78,BASE+0x5ce6c0]:
  b=blobs[a];assert len(b)==32
  data.append({'addr':hex(a),'size':32,'originalBytes':b.hex(' '),'sha256':sha(b),'qwords':[hex(x) for x in struct.unpack('<4Q',b)]})
 return {'schema':'bounded-native-evidence-v2','originalSha256':PIN,'functions':functions,'code_ranges':ranges,'data':data},deps,sha(parser.read_bytes())
if __name__=='__main__':
 e,d,p=derive();write('evidence.json',e);write('dependencies.json',{'dependencies':d,'coverageParserSha256':p});print(json.dumps({'functions':len(e['functions']),'ranges':len(e['code_ranges']),'fresh':sum(f['sourceMetadata']['freshCapture'] for f in e['functions']+e['code_ranges']),'bytes':sum(f['size'] for f in e['functions']+e['code_ranges'])}))
