"""Bounded offline Voice/request lifecycle verification; --check never writes.
Game code is not executed. Native function completeness uses exact IDA pages,
original PE bytes, independent Capstone decoding and explicitly bounded extents.
"""
import argparse, copy, hashlib, importlib.util, json, struct
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def load(path): return json.loads(path.read_bytes())
def enc(value): return (json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode()
def sha(data): return hashlib.sha256(data).hexdigest()
def number(value): return int(value,16) if isinstance(value,str) else value
def octets(value): return bytes(int(x,16) for x in value.split())
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path)
 m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
pm=module('voice_pe',HERE.parent/'bdx-trap-registry-20261008/verify.py')
def native(pe):
 cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
 aliases={'retn':'ret','jz':'je','jnz':'jne','jnb':'jae','cmovz':'cmove','cmovnz':'cmovne','setz':'sete','setnz':'setne','setnb':'setae','sal':'shl'}
 functions=[];data=[];instructions={};listing=[];imports=[];xrefs=[]
 for filename in ('capture.json','additional-capture.json','extra-data.json'):
  cap=load(HERE/filename);assert cap['Domain']=='native'
  if 'functions' in cap:assert cap['originalSha256']==pm.SHA and number(cap['imageBase'])==pe.base
  for f0 in cap.get('functions',[]):
   f=copy.deepcopy(f0);start=number(f['addr']);raw,z=pe.read(start,f['size'])
   assert not z and raw==octets(f['idaBytes'])
   d=f['disassembly'];rows=d['asm']['lines'];assert number(d['addr'])==number(d['asm']['start_ea'])==start
   assert d['instruction_count']==d['total_instructions']==len(rows)>0
   assert d['cursor']=={'done':True}
   collected=[];offset=0
   for index,page in enumerate(f['pages']):
    assert page['offset']==offset and number(page['addr'])==number(page['asm']['start_ea'])==start
    assert not page.get('truncated') and not page['cursor'].get('cancelled')
    assert page['total_instructions']==len(rows) and page['instruction_count']==len(page['asm']['lines'])
    offset+=page['instruction_count'];collected+=page['asm']['lines']
    if index+1==len(f['pages']):assert page['cursor']=={'done':True}
    else:assert page['cursor'].get('next')==offset and not page['cursor'].get('done')
   assert collected==rows and offset==len(rows)
   count=0
   for index,p in enumerate(f['pseudocode']['pages']):
    assert p['offset']==count and p['line_count']==len(p['code'].splitlines()) and not p['cursor'].get('cancelled')
    count+=p['line_count'];assert bool(p.get('truncated'))==(p['line_count']<p['total_lines'])
    if index+1==len(f['pseudocode']['pages']):assert p['cursor']=={'done':True} and count==p['total_lines']
    else:assert p['cursor'].get('next')==count and not p['cursor'].get('done')
   assert f['pseudocode']['cursor']=={'done':True}
   pcs=[number(r['addr']) for r in rows];assert pcs==sorted(set(pcs)) and pcs[0]==start
   covered=set();decoded=[];listing.append('\n'+f['addr']+' '+f['name'])
   for row in rows:
    pc=number(row['addr']);assert start<=pc<start+len(raw)
    i=next(cs.disasm(raw[pc-start:pc-start+15],pc,count=1))
    span=set(range(pc-start,pc-start+i.size));assert not span&covered and max(span)<len(raw);covered|=span
    mn=row['instruction'].split()[0].lower()
    assert mn==i.mnemonic or aliases.get(mn)==i.mnemonic or (mn=='mov' and i.mnemonic=='movabs') or (mn=='xchg' and i.bytes==b'\x66\x90' and i.mnemonic=='nop'),(hex(pc),mn,i.mnemonic)
    assert pc not in instructions;instructions[pc]=i
    decoded.append(dict(addr=hex(pc),bytes=i.bytes.hex(),size=i.size,mnemonic=i.mnemonic,operands=i.op_str))
    listing.append(f'{pc:016x} {i.bytes.hex():<30} {i.mnemonic} {i.op_str}')
   gaps=sorted(set(range(len(raw)))-covered);assert not gaps,(hex(start),gaps[:20],len(gaps))
   f.update(originalBytes=raw.hex(' '),sha256=sha(raw),decodedInstructions=decoded,sourceCapture=filename)
   functions.append(f)
  for d in cap.get('data',[]):
   raw,z=pe.read(number(d['addr']),d['size']);assert not z and raw==octets(d['idaBytes'])
   data.append(dict(label=d['label'],addr=d['addr'],size=d['size'],originalBytes=raw.hex(' '),sha256=sha(raw)))
  if 'xrefs' in cap:xrefs.append(cap['xrefs'])
 for a in load(HERE/'anchors.json'):
  i=instructions[number(a['addr'])];assert (i.mnemonic,i.op_str,i.bytes.hex())==(a['mnemonic'],a['operands'],a['bytes']),a
 im=pe.imports()
 for pc,i in sorted(instructions.items()):
  if i.mnemonic not in ('call','jmp') or not i.operands:continue
  op=i.operands[0]
  if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
   a=pc+i.size+op.mem.disp
   if a in im:imports.append(dict(site=hex(pc),iat=hex(a),dll=im[a][0],symbol=im[a][1],bytes=i.bytes.hex()))
 def read(a,n):
  b,z=pe.read(a,n);assert not z;return b
 def q(a):return struct.unpack('<Q',read(a,8))[0]
 assert q(0x140750588)==0x1405cc860
 for off,fn in ((0,0x140406600),(0x28,0x1404066b0),(0x40,0x1404066e0),(0xa0,0x140406810)):assert q(0x1405cc860+off)==fn
 assert q(0x14074c468)==0x1405c6918 and q(0x1405c6910)==0x140679c60
 assert q(0x1405c6ac8+8)==0x1403ce570 and q(0x1405c6ae0)==0x1403d85a0 and q(0x1405c6ae8)==0x1403ce560
 rtti=[(0x140679c60,0x795208,b'.?AV?$VTABLE@VPARTY@YS@@@PARTY@YS@@'),(0x14067b9e0,0x795dc0,b'.?AV?$VTABLE@VBTLNPC@YS@@@BTLOBJ@YS@@'),(0x140679e90,0x7952e8,b'.?AVVOICE_IOP@YS@@'),(0x140679f10,0x795310,b'.?AVVOICE_EE@YS@@')]
 for col,typ,name in rtti:
  fields=struct.unpack('<6I',read(col,24));assert fields[0]==1 and fields[3]==typ and fields[5]==col-pe.base
  assert read(pe.base+typ+16,len(name)+1)==name+b'\0'
 assert read(0x1405b4b24,7)==b'ORIGIN\0' and read(0x1405abaf8,8)==b'SEDBSSCF'
 evidence=dict(schema=1,Domain='native',originalSha256=pm.SHA,imageBase=hex(pe.base),functions=functions,data=data,imports=imports,semanticAnchors=load(HERE/'anchors.json'),xrefInventory=xrefs,limits='Selected complete function bodies and byte extents only. IDA auto-analysis was not ready; returned xrefs and text search are not exhaustive. No full audio/Actor lifecycle, thread ownership, exception closure or game execution validation.')
 return evidence,'\n'.join(listing)+'\n',dict(functions=len(functions),instructions=len(instructions),primaryBytes=sum(f['size'] for f in functions),dataSpans=len(data),semanticAnchors=len(evidence['semanticAnchors']),importSites=len(imports),rttiIdentities=4)
def manifest():
 return dict(schema=1,originalSha256=pm.SHA,files={p.relative_to(HERE).as_posix():sha(p.read_bytes()) for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='manifest.json' and not {'artifacts','bin','obj','__pycache__'}&set(p.relative_to(HERE).parts)})
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
 pins=load(HERE/'provenance.json')
 for r in pins['files']:assert sha((ROOT/r['path']).read_bytes())==r['sha256'],r['path']
 pe=pm.PE(pm.TARGET);e,asm,n=native(pe)
 old=module('voice_upstream',HERE.parent/'timer-audience-operation-20261008/verify.py')
 _,assets=old.verify_assets()
 model=module('voice_model',HERE/'model.py').checks()
 claims=load(HERE/'claims.json');assert claims==load(HERE/'report.json')['findings']
 addrs={number(f['addr']) for f in e['functions']}
 import re
 for c in claims:
  assert number(c['addr']) in addrs and isinstance(c['Evidence'],list) and c['Evidence']
  for ref in c['Evidence']:
   name,sep,fragment=ref.partition('#');assert (HERE/name).is_file() or name in ('evidence.json','verification.json')
   if sep:
    match=re.fullmatch(r'functions\[addr=(0x[0-9A-Fa-f]+)\]',fragment);assert match and number(match[1]) in addrs
 outputs={'evidence.json':enc(e),'native-asm.txt':asm.encode(),'verification.json':enc(dict(success=True,originalSha256=pm.SHA,native=n,upstreamAssets=assets,model=model,claims=len(claims),limits=['Original asset stored-entry and loose-payload identity rechecked through pinned upstream verifier; no fresh decompression in this verifier.','Models cover normal-return, valid-memory, sequential synthetic states; external calls are explicit nondeterministic outcomes.','No runtime schedule, audible playback, all-writers, exception/lifetime closure or universal NULL-binding proof.']))}
 for name,b in outputs.items():
  if args.check:assert (HERE/name).read_bytes()==b,name
  else:(HERE/name).write_bytes(b)
 m=enc(manifest())
 if args.check:assert (HERE/'manifest.json').read_bytes()==m,'manifest.json'
 else:(HERE/'manifest.json').write_bytes(m)
 print(json.dumps(dict(success=True,**n,claims=len(claims),model=model)))
if __name__=='__main__':main()
