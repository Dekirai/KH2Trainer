"""Bounded original-byte and binary32 model verification for BDX Actor query calls.
No original code, game process or game script is executed. --check is read-only.
"""
import argparse,copy,hashlib,importlib.util,json,math,struct
from pathlib import Path
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_MEM,X86_OP_IMM,X86_REG_RIP
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PE_SOURCE=HERE.parent/'bdx-trap-registry-20261008/verify.py'
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def enc(x):return (json.dumps(x,indent=2,ensure_ascii=False)+'\n').encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def num(x):return int(x,16) if isinstance(x,str) else x
def blob(x):return bytes(int(v,16) for v in x.split())
def need(v,msg):
 if not v:raise AssertionError(msg)
def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def bits(x):return struct.unpack('<I',struct.pack('<f',x))[0]

def model():
 # Models only the captured arithmetic/copy decisions. Native query effects are
 # supplied booleans, not an emulator of the transitive collision implementation.
 def run(limit,mode,breaks=(),budget=20):
  limit=f32(limit);step=f32(0);copies=0;values=[]
  if math.isnan(limit) or limit<=0:return dict(state='entry_return',copies=0,steps=[])
  for i in range(budget):
   added=f32(step+f32(100));step=min(limit,added);values.append(step)
   if not mode and i<len(breaks) and breaks[i]:return dict(state='flag_break',copies=copies,steps=values)
   copies+=1
   if not limit>step:return dict(state='limit_reached',copies=copies,steps=values)
  return dict(state='model_budget',copies=copies,steps=values)
 cases=[];checks=0
 for limit in [-math.inf,-100,-1,-0.0,0.0,math.nan]:
  r=run(limit,False);need(r['copies']==0 and r['state']=='entry_return','entry no-copy');checks+=1;cases.append(dict(limit=str(limit),mode=False,result=r))
 for limit,expected in [(1,[1]),(50,[50]),(100,[100]),(101,[100,101]),(200,[100,200]),(250,[100,200,250]),(1000,list(range(100,1001,100)))]:
  r=run(limit,False);need(r['steps']==expected and r['copies']==len(expected) and r['state']=='limit_reached','bounded progress');checks+=1;cases.append(dict(limit=limit,mode=False,result=r))
 for mode,flags,expected in [(False,[True],0),(False,[False,True],1),(True,[True,True,True],3)]:
  r=run(250,mode,flags);need(r['copies']==expected,'supplied flag-copy boundary');checks+=1;cases.append(dict(limit=250,mode=mode,suppliedBreakFlags=flags,result=r))
 # A finite positive fixed point exists at2^31. Below that binade, the positive
 # spacing is at most128, and adding100 cannot round back to the same normal.
 fixed=f32(2**31);before=struct.unpack('<f',struct.pack('<I',bits(fixed)-1))[0];after=struct.unpack('<f',struct.pack('<I',bits(fixed)+1))[0]
 need(before==fixed-128 and after==fixed+256,'adjacent binary32 values');checks+=1
 need(f32(before+100)==fixed and f32(fixed+100)==fixed,'RN-even fixed point');checks+=1
 need(not fixed>fixed and after>fixed and math.inf>fixed,'loop comparison boundary');checks+=1
 need(min(after,f32(fixed+100))==fixed and min(math.inf,f32(fixed+100))==fixed,'MINSS normal/infinity arithmetic');checks+=1
 return dict(success=True,checks=checks,cases=cases,fixedPoint=dict(value=fixed,bits=f'{bits(fixed):08x}',predecessor=before,successor=after,condition='Loop condition remains true only when input limit exceeds2^31; equality terminates normally.'),scope='Own binary32 arithmetic with rounding held at nearest-even, relevant SSE exceptions masked, and supplied break decisions. COMISS unordered entry handling assumes masked invalid exception. No target instruction/collision code executed; no retail reachability or global absence of reentrant writers claimed.')

def derive():
 spec=importlib.util.spec_from_file_location('query_original_pe',PE_SOURCE);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);pe=m.PE(m.TARGET)
 def read(a,n):
  b,z=pe.read(a,n);need(z==0,('stored PE bytes',hex(a)));return b
 documents=[load(HERE/n) for n in ['capture.json','helper-capture.json','imported-evidence.json']]
 cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True;functions=[];instructions={};body_bytes=0;instruction_count=0;imports=[]
 for document in documents:
  need(document['originalSha256']==m.SHA and num(document['imageBase'])==pe.base,'retail capture identity')
  for source in document['functions']:
   f=copy.deepcopy(source);a=num(f['addr']);size=f['size'];raw=read(a,size)
   need(raw==blob(f.get('idaBytes',f.get('originalBytes'))),('captured bytes',f['addr']))
   if 'importedFrom' in f:
    pin=f['importedFrom'];path=ROOT/pin['path'];need(sha(path.read_bytes())==pin['sha256'],'source pin')
    original=next(row for row in load(path)['functions'] if num(row['addr'])==a)
    need(blob(original['originalBytes'])==raw,'imported body identity');imports.append(pin)
   d=f['disassembly'];lines=d['asm']['lines'];pages=f['pages'];need(d['cursor'].get('done') and len(lines)==d['instruction_count']==d['total_instructions'],('ASM cursor/count',f['addr']))
   need(lines==[line for page in pages for line in page['asm']['lines']],'identical pages');count=0
   for page in pages:
    need(page['instruction_count']==len(page['asm']['lines']),'page count');count+=page['instruction_count'];need(page['cursor'].get('done') or page['cursor'].get('next')==count,'page cursor')
   need(pages[-1]['cursor'].get('done'),'last page')
   if 'decompile' in f:need(f['decompile']['cursor'].get('done') and not f['decompile'].get('truncated'),'pseudocode completion')
   decoded=list(cs.disasm(raw,a));need(sum(i.size for i in decoded)==size and [i.address for i in decoded]==[num(x['addr']) for x in lines],('complete body decode',f['addr']))
   need(a not in [num(x['addr']) for x in functions],'duplicate body')
   instructions.update({i.address:i for i in decoded});f['originalBytes']=raw.hex(' ');f['decodedInstructions']=[dict(addr=hex(i.address),bytes=i.bytes.hex(),mnemonic=i.mnemonic,operands=i.op_str) for i in decoded];functions.append(f)
   body_bytes+=size;instruction_count+=len(decoded)
 extra=load(HERE/'additional-capture.json');data=[]
 for row in extra['data']['result']:
  raw=blob(row['data']);need(read(num(row['addr']),len(raw))==raw,'literal/table data');data.append(dict(addr=row['addr'],size=len(raw),originalBytes=raw.hex(' '),sha256=sha(raw)))
 need(read(0x140623a80,4)==struct.pack('<f',1) and read(0x140623be4,4)==struct.pack('<f',100),'floating literals')
 need(read(0x140756b48,16)==struct.pack('<ffff',0,0,0,1),'original shared buffer')
 need(read(0x140756a60,16)==struct.pack('<QII',0x14042bb40,0x40000003,0),'descriptor1:367')
 for key,note in load(HERE/'annotations.json')['annotations'].items():
  bank,index=map(int,key.split(':'));need(bank==1,'annotation bank')
  handler,flags,padding=struct.unpack('<QII',read(pe.base+0x755370+index*16,16))
  need(note['handlerRva']==handler-pe.base and note['declaredOperandCount']==flags&65535 and note['hasReturnSlot']==bool(flags&0x40000000) and padding==0,('original annotation metadata',key))
 anchors={0x1403b8596:('movaps','xmm7, xmm2'),0x1403b85ed:('comiss','xmm7, xmm6'),0x1403b85f0:('jbe','0x1403b868c'),0x1403b8617:('addss','xmm0, xmm8'),0x1403b861f:('minss','xmm6, xmm0'),0x1403b862d:('call','0x14016fec0'),0x1403b863b:('jne','0x1403b865d'),0x1403b8651:('call','0x1401a8e60'),0x1403b8656:('comiss','xmm7, xmm6'),0x1403b8659:('mov','bl, 1'),0x1403b865b:('ja','0x1403b8610'),0x14042bb7f:('call','0x1403b8510'),0x14042bb8b:('call','0x1404ad240'),0x14042b7da:('call','0x1401a8e60')}
 for a,expected in anchors.items():need((instructions[a].mnemonic,instructions[a].op_str)==expected,('semantic anchor',hex(a),(instructions[a].mnemonic,instructions[a].op_str)))
 xrefs=[]
 for row in extra['xrefs']['result']:
  need(not row.get('more') and row['xref_count']==len(row['xrefs']),'xref count');target=num(row['addr'])
  for ref in row['xrefs']:
   if not ref['fn']:continue # includes non-pointer RVA metadata; no guessed encoding
   a=num(ref['addr']);i=next(cs.disasm(read(a,15),a,count=1));need(any(o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and a+i.size+o.mem.disp==target or o.type==X86_OP_IMM and o.imm==target for o in i.operands),'original xref encoding');xrefs.append(dict(source=hex(a),target=hex(target)))
 model_receipt=model()
 evidence=dict(schema=1,Domain='native',originalSha256=m.SHA,imageBase=hex(pe.base),functions=functions,data=data,imports=imports,semanticAnchors=[dict(addr=hex(a),mnemonic=mn,operands=op,bytes=instructions[a].bytes.hex()) for a,(mn,op) in anchors.items()],verifiedCodeXrefs=xrefs)
 receipt=dict(success=True,bodies=len(functions),freshBodies=7,importedBodies=2,instructions=instruction_count,bodyBytes=body_bytes,dataSpans=len(data),dataBytes=sum(x['size'] for x in data),anchors=len(anchors),codeXrefs=len(xrefs),modelChecks=model_receipt['checks'],scope='Bounded immediate query path and scalar/copy decisions. Transitive16FEC0 collision effects remain open. No original-code execution or live game.')
 return {'evidence.json':enc(evidence),'model.json':enc(model_receipt),'verification.json':enc(receipt)}

def manifest():
 return dict(schema=1,files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p.read_bytes())) for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='manifest.json'},dependencies={str(PE_SOURCE.relative_to(ROOT)):sha(PE_SOURCE.read_bytes())})
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();outputs=derive()
 for name,b in outputs.items():
  if a.check:need((HERE/name).read_bytes()==b,('derived file changed',name))
  else:(HERE/name).write_bytes(b)
 if a.check:need(load(HERE/'manifest.json')==manifest(),'manifest changed')
 elif (HERE/'report.txt').exists():(HERE/'manifest.json').write_bytes(enc(manifest()))
 print(outputs['verification.json'].decode())
