"""Read-only verifier of recorded bodies/byte anchors and narrow policy cases."""
import argparse,hashlib,json,pathlib,re,struct
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_MEM,X86_OP_IMM
H=pathlib.Path(__file__).resolve().parent
ROOT=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir())
EXE=pathlib.Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
EXPECTED='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(b):return hashlib.sha256(b).hexdigest()
def bs(s):return bytes(int(x,16) for x in s.split())
def a(s):return int(s,16)
def un(d):return d.get('structuredContent',d)
def put_or_check(name,v,write):
 p=H/name
 if write:p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 else:assert read(p)==v,name

def main(write=False):
 pe=EXE.read_bytes();assert sha(pe)==EXPECTED
 nt=struct.unpack_from('<I',pe,0x3c)[0];assert pe[nt:nt+4]==b'PE\0\0'
 count=struct.unpack_from('<H',pe,nt+6)[0];opt=struct.unpack_from('<H',pe,nt+20)[0]
 base=struct.unpack_from('<Q',pe,nt+48)[0];assert base==0x140000000
 secs=[struct.unpack_from('<8sIIII',pe,nt+24+opt+40*i) for i in range(count)]
 def original(va,n):
  rva=va-base
  for _,vs,rs,sz,ptr in secs:
   if rs<=rva and n<=sz and rva-rs<=sz-n:return pe[ptr+rva-rs:ptr+rva-rs+n]
  raise AssertionError('not file-backed '+hex(va))
 deps=read(H/'dependencies.json');cache={}
 for dep in deps['bodies']+deps['context']:
  p=ROOT/dep['path'];assert sha(p.read_bytes())==dep['sha256'],dep['path']
  if 'addresses' in dep:cache[dep['path']]=read(p)
 fs=read(H/'evidence.json')['functions'];assert len({f['addr'] for f in fs})==len(fs)
 cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True;insmap={};body=[]
 for f in fs:
  va=a(f['addr']);size=f['size'];raw=bs(f['originalBytes'])
  assert len(raw)==size and sha(raw)==f['sha256'] and raw==original(va,size)
  lines=f['asm']['lines'];assert lines==f['disassembly']['asm']['lines']
  assert f['pages'][-1]['cursor']['done'] and [l for p in f['pages'] for l in p['asm']['lines']]==lines
  for page in f['pages']:assert page['instruction_count']==len(page['asm']['lines']) and page['total_instructions']==len(lines)
  pp=f['pseudocode']['pages'];assert pp[-1]['cursor']['done'] and not any(p.get('truncated',False) for p in pp)
  assert sum(p['line_count'] for p in pp)==pp[-1]['total_lines']
  assert f['pseudocode']['code']=='\n'.join(p['code'] for p in pp)
  if f['freshCapture']:
   assert f['pages']==[un(read(H/f['source']))]
   assert pp==[un(read(H/('root-decompile-'+f['addr']+'.json')))]
   batches=[bs(b['data']) for p in H.glob('root-bytes*.json') for b in un(read(p))['result'] if a(b['addr'])==va]
   assert batches and all(b==raw for b in batches)
  else:
   path,frag=f['source'].split('#');sf=next(x for x in cache[path]['functions'] if a(x['addr'])==va)
   sa=sf.get('disassembly',{}).get('asm',sf.get('asm'));assert (sa if isinstance(sa,list) else sa['lines'])==lines
   sb=sf.get('originalBytes',sf.get('bytes'))
   if sb is None:
    chunks=sf['original_bytes'];chunks=[chunks] if isinstance(chunks,dict) else chunks;sb=b''.join(bs(c['data']) for c in sorted(chunks,key=lambda c:a(c['addr'])))
   else:sb=bs(sb)
   assert raw==sb
  covered=set()
  for l in lines:
   at=a(l['addr']);assert va<=at<va+size
   ins=next(cs.disasm(raw[at-va:],at,count=1),None);assert ins and at+ins.size<=va+size
   span=set(range(at,at+ins.size));assert not span&covered;covered|=span;insmap[at]=(ins,l,f['addr'])
  missing=sorted(set(range(va,va+size))-covered);gaps=[]
  for at in missing:
   if gaps and at==gaps[-1][1]:gaps[-1][1]+=1
   else:gaps.append([at,at+1])
  body.append({'addr':f['addr'],'freshCapture':f['freshCapture'],'size':size,'instructions':len(lines),'instructionBytes':len(covered),'unrenderedSpans':[{'addr':hex(x),'size':y-x,'originalBytes':original(x,y-x).hex(' ')} for x,y in gaps]})
 # Decode actual PE imports, tying the read calls to the original named CRT entries.
 def u32(r):return struct.unpack('<I',original(base+r,4))[0]
 def zstr(r):
  b=bytearray()
  while True:
   c=original(base+r+len(b),1)[0]
   if c==0:return b.decode('ascii')
   b.append(c)
 imp_rva=struct.unpack_from('<I',pe,nt+24+112+8)[0];imports={};di=0
 while True:
  oft,stamp,fwd,name,ft=struct.unpack('<IIIII',original(base+imp_rva+20*di,20));di+=1
  if not any([oft,stamp,fwd,name,ft]):break
  dll=zstr(name);ti=0
  while True:
   thunk=struct.unpack('<Q',original(base+(oft or ft)+8*ti,8))[0]
   if not thunk:break
   imports[base+ft+8*ti]={'dll':dll,'name':('#'+str(thunk&65535)) if thunk>>63 else zstr(thunk+2)};ti+=1
 assert imports[base+0x57BA98]['name']=='_read'
 assert imports[base+0x57BA08]['name']=='_lseeki64'
 for at,iat in [(0x1076A7,0x57BA98),(0x107704,0x57BA98),(0x107744,0x57BA98),(0x10764F,0x57BA08)]:
  ins=insmap[base+at][0];op=ins.operands[0]
  assert ins.mnemonic=='call' and op.type==X86_OP_MEM and ins.reg_name(op.mem.base)=='rip' and ins.address+ins.size+op.mem.disp==base+iat
 for at,reg in [(0x14F2FA,'r8d'),(0x14F2FD,'edx'),(0x14F2FF,'ecx')]:
  ins=insmap[base+at][0];assert ins.mnemonic=='xor' and ins.op_str==reg+', '+reg
 initcall=insmap[base+0x14F301][0];assert initcall.mnemonic=='call' and initcall.operands[0].imm==base+0x12EE70
 # No silently omitted instruction intervals: these are the original documented switch tails.
 assert [(b['addr'],[(x['addr'],x['size']) for x in b['unrenderedSpans']]) for b in body if b['unrenderedSpans']]==[
  ('0x1403a64f0',[('0x1403a67fa',66)]),('0x1403a6840',[('0x1403a69b7',83)]),('0x1403a6a10',[('0x1403a6be6',82)])]
 # Verify every direct handler-global Xref has complete original body coverage and exactly one is a store.
 xr=un(read(H/'root-xrefs-handlers.json'))['result'];globalrefs=next(x for x in xr if a(x['addr'])==base+0x8AEF38)
 assert globalrefs['more']==False
 writes=[];classed=[]
 for x in globalrefs['xrefs']:
  at=a(x['addr']);ins,line,owner=insmap[at]
  # X64 RIP-relative address is evaluated from the actual instruction end.
  hits=[i for i,o in enumerate(ins.operands) if o.type==X86_OP_MEM and ins.reg_name(o.mem.base)=='rip' and ins.address+ins.size+o.mem.disp==base+0x8AEF38]
  assert hits
  store=ins.mnemonic=='mov' and 0 in hits
  if store:writes.append(hex(at))
  classed.append({'addr':hex(at),'body':owner,'operation':ins.mnemonic+' '+ins.op_str,'writesHandlerGlobal':store})
 assert writes==['0x14012ee77']
 setterrefs=next(x for x in xr if a(x['addr'])==base+0x12EE70);assert not setterrefs['more']
 assert [a(x['addr']) for x in setterrefs['xrefs'] if x['type']=='code']==[base+0x14F301]
 # Classify the complete direct context-Xref result without promoting the excluded reader to a captured body.
 cx=next(x for x in un(read(H/'root-xrefs-retirement.json'))['result'] if a(x['addr'])==base+0x8AEF30)
 assert cx['more']==False and len(cx['xrefs'])==29
 roles={0x12DDA0:'replacement-range lookup',0x12DE20:'normalized-name lookup',0x12DF90:'name and exact-primary alias lookup',0x12E100:'primary-overlap lookup',0x12E180:'primary-range lookup and optional detach',0x12E230:'16-byte digest lookup',0x12E310:'replacement type and name lookup',0x12E460:'entry retirement',0x12E5C0:'entry creation and dispatch',0x12E860:'context retirement',0x12E980:'RootFileData lookup',0x12EA20:'context construction',0x12EB70:'RootFileData and dependency-name insertion',0x12EEA0:'range lookup and optional caller callback before retirement',0x12EF80:'group-zero retirement',0x3F9850:'ordinary reader currentEntry access',0x3F99E0:'alternate reader, outside admitted ordinary path'}
 contextrefs=[];contextwrites=[]
 for x in cx['xrefs']:
  at=a(x['addr']);owner=a(x['fn']['addr']);assert owner-base in roles
  ins=insmap[at][0] if at in insmap else next(cs.disasm(original(at,15),at,count=1))
  hits=[i for i,o in enumerate(ins.operands) if o.type==X86_OP_MEM and ins.reg_name(o.mem.base)=='rip' and ins.address+ins.size+o.mem.disp==base+0x8AEF30]
  assert hits
  if at not in insmap:assert at==base+0x3F9B15 and owner==base+0x3F99E0
  store=ins.mnemonic=='mov' and 0 in hits
  if store:contextwrites.append(at)
  contextrefs.append({'addr':hex(at),'function':hex(owner),'role':roles[owner-base],'fullBodyInStudy':at in insmap,'writesContextGlobal':store,'bytes':bytes(ins.bytes).hex(' '),'independentDecode':ins.mnemonic+' '+ins.op_str})
 assert contextwrites==[base+0x12E966,base+0x12EA6B]
 # The two-stage BAR dispatch is checked from actual file-backed table bytes, not IDA's switch comments.
 tags=original(base+0x3A680C,48);targets=original(base+0x3A67FC,16)
 selection={n:base+struct.unpack_from('<I',targets,tags[n-1]*4)[0] for n in [9,17]}
 assert selection=={9:base+0x3A6790,17:base+0x3A6610}
 # Anchors are manually selected after reading full bodies; each uses independently decoded bytes.
 selected=read(H/'anchor-spec.json')['anchors'];anchors=[]
 for s in selected:
  at=a(s['addr']);ins,line,owner=insmap[at]
  anchors.append({'addr':hex(at),'function':owner,'meaning':s['meaning'],'ida':line['instruction'],'independentDecode':ins.mnemonic+' '+ins.op_str,'bytes':bytes(ins.bytes).hex(' ')})
 put_or_check('anchors.json',{'anchors':anchors,'handlerGlobalReferences':classed,'handlerSetterCallsites':[hex(base+0x14F301)],'contextGlobalReferences':contextrefs,'barPreparationSwitch':{'indexTable':{'addr':hex(base+0x3A680C),'bytes':tags.hex(' ')},'targetTable':{'addr':hex(base+0x3A67FC),'bytes':targets.hex(' ')},'selectedTargets':{str(k):hex(v) for k,v in selection.items()}},'imports':{hex(k):v for k,v in imports.items() if k in [base+0x57BA98,base+0x57BA08,base+0x57B788]}},write)
 import models
 model=models.run(insmap,base);put_or_check('model-results.json',model,write)
 report=read(H/'report.json');refs=0
 for c in report['claims']:
  assert {'addr','Finding','Evidence','Limitations'}<=c.keys() and c['addr'] in {f['addr'] for f in fs}
  for ref in c['Evidence']:
   file,sep,frag=ref.partition('#');assert (H/file).is_file(),ref
   if sep:
    m=re.fullmatch(r'functions\[addr=(0x[0-9a-f]+)\]',frag);assert m and m.group(1) in {f['addr'] for f in read(H/file)['functions']},ref
   refs+=1
 out={'status':'PASS','originalSha256':EXPECTED,'functions':len(fs),'freshCapturedBodies':sum(f['freshCapture'] for f in fs),'explicitReusedBodies':sum(not f['freshCapture'] for f in fs),'extentBytes':sum(f['size'] for f in fs),'instructions':len(insmap),'instructionBytes':sum(b['instructionBytes'] for b in body),'anchors':len(anchors),'claims':len(report['claims']),'resolvedReferences':refs,'models':model['counts'],'bodies':body,'limits':['No live provider, no game access, no hook or source edits.','Direct-xref closure concerns this original retail image; modified/third-party providers are outside it.','Library calls rely on normal CRT/in-process codec contracts, not an exhaustive library implementation proof.']}
 put_or_check('verification.json',out,write)
 if (H/'manifest.json').exists() and not write:
  m=read(H/'manifest.json');actual={p.relative_to(H).as_posix() for p in H.rglob('*') if p.is_file() and p!=H/'manifest.json'};assert actual=={x['path'] for x in m['files']}
  for x in m['files']:
   p=H/x['path'];assert p.stat().st_size==x['bytes'] and sha(p.read_bytes())==x['sha256'],x['path']
 print(json.dumps({k:v for k,v in out.items() if k!='bodies'},indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--write',action='store_true');ap.add_argument('--check',action='store_true');main(ap.parse_args().write)
