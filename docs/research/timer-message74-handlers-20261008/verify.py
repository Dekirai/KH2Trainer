"""Reproduce only static native bytes, bounded models and original asset identity.
--check does not write. Rebuild the portable C# probe separately to decode PKGs.
"""
import argparse,copy,hashlib,importlib.util,json,struct
from pathlib import Path
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
import analyze_scripts as scripts
import test_model
HERE=Path(__file__).resolve().parent
PEFILE=HERE.parent/'bdx-trap-registry-20261008/verify.py'
spec=importlib.util.spec_from_file_location('timer_original_pe',PEFILE);pe_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(pe_module)
def enc(x):return(json.dumps(x,indent=2)+'\n').encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def number(x):return int(x,16)if isinstance(x,str)else x
def octets(s):return bytes(int(x,16)for x in s.split())
IMPORTED_SOURCE=HERE.parent/'app-timer-dispatch-20261008/evidence.json'
IMPORTED_SOURCE_SHA='ad5073e41d88be7bb45ba1b468b1e0fbb61d50cd1daaca6b1f2a2385555146ea'
IMPORTED_ADDRESSES=('0x1403b4c90','0x1403e1840','0x14041b320')
def imported_evidence(pe):
 """Exact native body copies; provenance stays outside each unchanged function object."""
 source_bytes=IMPORTED_SOURCE.read_bytes();assert sha(source_bytes)==IMPORTED_SOURCE_SHA
 source=json.loads(source_bytes);assert source['originalSha256']==pe_module.SHA and number(source['imageBase'])==pe.base
 cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True;functions=[];provenance=[];instruction_count=0;byte_count=0
 aliases={'retn':'ret','jz':'je','jnz':'jne','cmovz':'cmove'}
 for address in IMPORTED_ADDRESSES:
  matches=[f for f in source['functions']if f['addr'].lower()==address];assert len(matches)==1
  original_function=matches[0];f=copy.deepcopy(original_function);at=number(address);size=f['size']
  raw,z=pe.read(at,size);assert not z and raw==bytes.fromhex(f['originalBytes'])==octets(f['idaBytes'])
  lines=f['asm']['lines'];pages=f['pages'];assert number(f['asm']['start_ea'])==at
  assert f['cursor'].get('done')is True and not f['cursor'].get('cancelled')and f['cursor'].get('next')is None
  assert f['instruction_count']==f['total_instructions']==len(lines)>0
  gathered=[];count=0
  for i,p in enumerate(pages):
   assert number(p['addr'])==number(p['asm']['start_ea'])==at and p['total_instructions']==len(lines)
   if 'offset'in p:assert p['offset']==count
   assert p['instruction_count']==len(p['asm']['lines'])and not p.get('truncated')and not p['cursor'].get('cancelled')
   count+=p['instruction_count'];gathered+=p['asm']['lines']
   if i==len(pages)-1:assert p['cursor'].get('done')is True and p['cursor'].get('next')is None
   else:assert not p['cursor'].get('done')and p['cursor'].get('next')==count
  assert gathered==lines and count==len(lines)
  decoded=list(cs.disasm(raw,at));assert sum(i.size for i in decoded)==size and len(decoded)==len(lines)
  for i,row in zip(decoded,lines):
   assert i.address==number(row['addr']);mn=row['instruction'].split()[0].lower()
   assert mn==i.mnemonic or aliases.get(mn)==i.mnemonic,(address,hex(i.address),mn,i.mnemonic)
  assert f['pseudocode']['cursor'].get('done')is True and not f['pseudocode'].get('truncated')
  assert f==original_function
  canonical=json.dumps(original_function,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
  functions.append(f);instruction_count+=len(decoded);byte_count+=size
  provenance.append(dict(addr=address,sourceFile=IMPORTED_SOURCE.relative_to(HERE.parents[2]).as_posix(),sourceFragment='#functions[addr='+address+']',sourceFileSha256=IMPORTED_SOURCE_SHA,canonicalSourceBodySha256=sha(canonical),originalBodySha256=sha(raw),originalBodyBytes=size,instructions=len(decoded)))
 return dict(schema=1,Domain='native',originalSha256=pe_module.SHA,imageBase=hex(pe.base),sourceDomain=source['Domain'],functions=functions,provenance=provenance,canonicalBodyEncoding='UTF-8 JSON, sorted keys, separators comma/colon, ensure_ascii=False',limits='Exact copies of three previously captured native bodies, independently rechecked against original PE bytes. No new capture, semantic claim, transitive closure or whole-binary coverage.'),dict(functions=len(functions),instructions=instruction_count,bodyBytes=byte_count,sourceSha256=IMPORTED_SOURCE_SHA)
ANCHORS={
 0x14042c6bd:('mov','ecx, dword ptr [rcx + 8]'),0x14042c6cf:('mov','ecx, dword ptr [rax + 4]'),
 0x14042c6da:('lea','rcx, [rax + 0x390]'),0x14042c6eb:('jmp','0x1403cae60'),
 0x14042db0a:('mov','ebx, dword ptr [rcx + 8]'),0x14042db24:('call','0x1403b5df0'),0x14042db30:('mov','dword ptr [rdi + 4], 0x544e4940'),
 0x1403b5df0:('movsxd','rax, edx'),0x1403b5df3:('mov','eax, dword ptr [rcx + rax*4 + 0x9f4]'),
 0x14042be0e:('mov','r9d, edi'),0x14042be11:('mov','r8d, esi'),0x14042be14:('mov','rdx, rbx'),0x14042be17:('mov','rcx, rax'),0x14042be2c:('jmp','qword ptr [r10 + 0xa0]'),
 0x140433539:('call','0x1403fb840'),0x14043353e:('movzx','eax, al'),0x140433543:('mov','dword ptr [rbx + 4], 0x544e4940'),
 0x1403fb844:('call','0x1403a3b50'),0x1403fb84b:('je','0x1403fb85f'),0x1403fb84d:('call','0x1403a3970'),0x1403fb852:('test','byte ptr [rax + 4], 1'),
 0x1403a3b50:('cmp','qword ptr [rip + 0x266c410], 0'),0x1403a3970:('mov','rax, qword ptr [rip + 0x266c5f1]'),
 0x1403cae66:('test','byte ptr [rcx + 0x12c], 1'),0x1403cae7e:('call','0x1403ca700'),0x1403cae89:('je','0x1403caeb2'),
 0x1403cae97:('call','0x1403caec0'),0x1403cae9e:('mov','qword ptr [rbx], rax'),0x1403caea1:('mov','dword ptr [rbx + 0x128], eax'),0x1403caead:('call','0x1403cad00'),
 0x1403f4a34:('xor','esi, esi'),0x1403f4a4a:('inc','esi'),0x1403f4a4c:('add','rax, 0x10'),0x1403f4a53:('jl','0x1403f4a44'),
 0x1403f4a57:('call','0x1403e1730'),0x1403f4a82:('mov','qword ptr [rbp + rdi*8 + 8], rax'),0x1403f4a87:('call','0x1403e1840'),
 0x1403f4a99:('call','0x1403e1790'),0x1403f4aab:('mov','dword ptr [rbx + 0x40], eax'),
 0x1403f5ddc:('mov','ebx, edx'),0x1403f5e12:('cmp','r8d, 0x10'),0x1403f5e16:('jl','0x1403f5de8'),0x1403f5e1c:('mov','qword ptr [rbx], 0xffffffffffffffff'),
 0x1403f5e68:('mov','dword ptr [rbx], esi'),0x1403f5e6a:('mov','dword ptr [rbx + 4], edi'),
 0x1403f61b8:('call','0x14039a980'),0x1403f61c4:('call','0x14039afc0'),0x1403f61d0:('call','0x1403e3930'),
 0x1403f61f8:('call','0x1403a1a60'),0x1403f6200:('call','0x1403a1e70'),0x1403f6238:('call','0x1403fdf00'),0x1403f6248:('call','0x1403fdf60'),
 0x1403f6260:('mov','dword ptr [rbx], 0xffffffff')}
def build():
 pe=pe_module.PE(pe_module.TARGET);cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
 e=json.loads((HERE/'capture.json').read_bytes());assert e['originalSha256']==pe_module.SHA
 ins={};listing=[];bytecount=0;icount=0
 for f in e['functions']:
  at=number(f['addr']);raw,z=pe.read(at,f['size']);assert not z and raw==octets(f['idaBytes'])
  body=f['disassembly'];pages=f['pages'];lines=body['asm']['lines'];index=0;gathered=[]
  assert number(body['addr'])==number(body['asm']['start_ea'])==at
  assert body['instruction_count']==body['total_instructions']==len(lines)>0
  assert body['cursor'].get('done')is True and not body['cursor'].get('cancelled')and body['cursor'].get('next')is None
  for n,page in enumerate(pages):
   assert page['instruction_count']==len(page['asm']['lines'])and page['total_instructions']==len(lines)
   assert number(page['addr'])==number(page['asm']['start_ea'])==at
   assert not page.get('truncated') and not page['cursor'].get('cancelled');index+=page['instruction_count'];gathered+=page['asm']['lines']
   if n==len(pages)-1:assert page['cursor'].get('done')is True and page['cursor'].get('next')is None
   else:assert not page['cursor'].get('done')and page['cursor'].get('next')==index
  assert gathered==lines and index==len(lines)
  addresses=[number(x['addr'])for x in lines];assert addresses==sorted(set(addresses))and addresses[0]==at
  assert f['pseudocode']['cursor']['done']and not f['pseudocode']['truncated']
  covered=set();decoded=[];listing.append('\n'+f['addr']+' '+f['name'])
  for row in lines:
   pc=number(row['addr']);assert at<=pc<at+len(raw);i=next(cs.disasm(raw[pc-at:pc-at+15],pc,count=1));span=set(range(pc-at,pc-at+i.size))
   assert not span&covered and max(span)<len(raw);covered|=span;ins[pc]=i
   decoded.append(dict(addr=hex(pc),bytes=i.bytes.hex(),size=i.size,mnemonic=i.mnemonic,operands=i.op_str))
   listing.append(f'{pc:016x} {i.bytes.hex():<30} {i.mnemonic} {i.op_str}')
  assert covered==set(range(len(raw))),('unlisted native body bytes',f['addr'])
  f['originalBytes']=raw.hex(' ');f['decodedInstructions']=decoded;f['sha256']=sha(raw);bytecount+=len(raw);icount+=len(decoded)
 data=[]
 for row in e['data']:
  raw,z=pe.read(number(row['addr']),len(octets(row['data'])));assert not z and raw==octets(row['data']);data.append(dict(addr=row['addr'],originalBytes=raw.hex(' ')))
 e['data']=data;descriptors=[]
 for bank,index,addr,callback,flags in[(1,8,0x1407553f0,0x14042c6b0,2),(1,39,0x1407555e0,0x14042db00,0x40000002),(1,262,0x1407563d0,0x14042bde0,3),(4,21,0x1407573a0,0x140433530,0x40000000)]:
  raw,z=pe.read(addr,16);assert not z and struct.unpack('<QII',raw)==(callback,flags,0)
  root=struct.unpack('<Q',pe.read(0x140753490+8*bank,8)[0])[0];assert root+16*index==addr
  descriptors.append(dict(bank=bank,index=index,addr=hex(addr),handler=hex(callback),flags=hex(flags),declaredOperands=flags&0xffff,returnsValue=bool(flags&0x40000000),originalBytes=raw.hex(' ')))
 e['descriptors']=descriptors;anchors=[]
 annotations=json.loads((HERE/'annotations.json').read_bytes());assert annotations['originalSha256']==pe_module.SHA
 assert set(annotations['annotations'])=={'1:8','1:39','1:262','4:21'}
 for d in descriptors:
  a=annotations['annotations'][f"{d['bank']}:{d['index']}"]
  assert(a['bank'],a['index'],a['handlerRva'],a['declaredOperandCount'],a['hasReturnSlot'])==(d['bank'],d['index'],number(d['handler'])-pe.base,d['declaredOperands'],d['returnsValue'])
  assert all(isinstance(a[k],str)and a[k].strip()for k in('name','summary','notes','evidence'))
 for at,(mn,op)in ANCHORS.items():
  i=ins[at];assert(i.mnemonic,i.op_str)==(mn,op),(hex(at),i.mnemonic,i.op_str,mn,op)
  anchors.append(dict(addr=hex(at),bytes=i.bytes.hex(),mnemonic=mn,operands=op))
 e['semanticAnchors']=anchors
 xbytes={number(x['addr']):octets(x['data'])for x in e['xrefBytes']};xrefs=[]
 for group in e['xrefs']:
  assert not group.get('more');target=number(group['addr'])
  for ref in group['xrefs']:
   at=number(ref['addr']);raw=xbytes[at];original,z=pe.read(at,len(raw));assert not z and original==raw
   if ref['type']=='code':
    i=next(cs.disasm(raw,at,count=1));assert any(o.type==X86_OP_IMM and o.imm==target for o in i.operands)
   elif ref['fn']:
    i=next(cs.disasm(raw,at,count=1));assert any(o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and i.address+i.size+o.mem.disp==target for o in i.operands)
   else:assert struct.unpack('<I',raw[:4])[0]+pe.base==target or struct.unpack('<Q',raw[:8])[0]==target
   xrefs.append(dict(target=hex(target),addr=hex(at),kind=ref['type'],originalBytes=raw.hex(' ')))
 e['verifiedXrefs']=xrefs;imports=pe.imports();boundaries=[]
 for i in ins.values():
  if i.mnemonic not in('call','jmp')or len(i.operands)!=1:continue
  op=i.operands[0];iat=None;stub=None
  if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:iat=i.address+i.size+op.mem.disp
  elif op.type==X86_OP_IMM and op.imm not in ins:
   raw,z=pe.read(op.imm,15);s=next(cs.disasm(raw,op.imm,count=1))
   if s.mnemonic=='jmp'and s.operands[0].type==X86_OP_MEM and s.operands[0].mem.base==X86_REG_RIP:
    iat=s.address+s.size+s.operands[0].mem.disp;stub=dict(addr=hex(s.address),bytes=s.bytes.hex())
  if iat in imports:
   dll,symbol=imports[iat];boundaries.append(dict(callsite=hex(i.address),iat=hex(iat),dll=dll,symbol=symbol,originalForwarder=stub))
 e['imports']=boundaries
 analysis=scripts.build();tests=test_model.test();retail=json.loads((HERE/'retail-witnesses.json').read_bytes());assert retail['success']and len(retail['results'])==6
 for r in retail['results']:
  assert r['fullLooseIdentical'];asset=(scripts.LOOSE/r['asset']).read_bytes();assert sha(asset)==r['decodedSha256']and len(asset)==r['decodedBytes']
  hed=(scripts.GAME/'Image/dt'/r['hed']).read_bytes();assert sha(hed)==r['hedSha256'];row=hed[32*r['Ordinal']:32*(r['Ordinal']+1)];assert row.hex()==r['hedRowHex']
  name,off,stored,original=struct.unpack('<16sQii',row);assert(name.hex(),off,stored,original)==(r['NameHash'],r['Offset'],r['StoredLength'],r['OriginalLength'])
  with(scripts.GAME/'Image/dt'/r['pkg']).open('rb')as file:
   assert file.seek(0,2)==r['pkgLength'];file.seek(off);assert sha(file.read(stored))==r['storedEntrySha256']
  assert len(r['children'])==1
  for c in r['children']:
   raw=asset[c['RelativeOffset']:c['RelativeOffset']+c['Length']];assert sha(raw)==c['sha256']and c['diagnostics']==0 and not c['HitLimit']
   match=next(x for x in analysis['rows']if x['asset']==r['asset']);assert match['scriptSha256']==c['sha256']
   assert[(x['id'],x['pc'])for x in match['header']['events']]==[(x['Id'],x['Pc'])for x in c['events']]
 imported,import_counts=imported_evidence(pe)
 receipt=dict(success=True,functions=len(e['functions']),instructions=icount,bodyBytes=bytecount,semanticAnchors=len(anchors),descriptors=len(descriptors),verifiedXrefs=len(xrefs),imports=boundaries,importedNativeEvidence=import_counts,
  assetRows=len(analysis['rows']),distinctScripts=analysis['distinctScripts'],prefixOutcomes=analysis['prefixOutcomesByAsset'],retailAssets=6,annotations=len(annotations['annotations']),modelTests=tests,
  limits=['No native or script execution.','The C# probe decodes original archives; this check revalidates package hashes, HED rows and exact loose/header identity.','Capture is limited to selected helpers and finite direct-xref groups; no indirect alias exclusion.','Prefix outcomes describe stored instructions and explicit conditional state assumptions, not observed game behavior.'])
 return{'evidence.json':enc(e),'native-asm.txt':('\n'.join(listing)+'\n').encode(),'script-analysis.json':enc(analysis),'verification.json':enc(receipt),'imported-evidence.json':enc(imported)}
def manifest():
 names=['capture.json','analyze_scripts.py','test_model.py','verify.py','evidence.json','imported-evidence.json','native-asm.txt','script-analysis.json','retail-witnesses.json','verification.json','annotations.json','report.txt','report.json','claims.json','retail-probe/Program.cs','retail-probe/RetailProbe.csproj']
 dependencies=[PEFILE,scripts.DECODER,scripts.CENSUS,HERE.parent/'app-timer-dispatch-20261008/evidence.json',HERE.parent/'bdx-rebind-operands-20261008/evidence.json',HERE.parent/'bdx-system-calls-20261008/evidence.json']
 return dict(schema=1,files={n:dict(bytes=(HERE/n).stat().st_size,sha256=sha((HERE/n).read_bytes()))for n in names},dependencies={str(p.relative_to(HERE.parent)).replace('\\','/'):sha(p.read_bytes())for p in dependencies},excluded='retail-probe/bin and obj generated outputs; no original raw game assets copied')
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args();outputs=build()
 for n,raw in outputs.items():
  if args.check:assert(HERE/n).read_bytes()==raw,('derived output mismatch',n)
  else:(HERE/n).write_bytes(raw)
 if args.check:assert json.loads((HERE/'manifest.json').read_bytes())==manifest(),'manifest mismatch'
 elif(HERE/'report.txt').exists():(HERE/'manifest.json').write_bytes(enc(manifest()))
 print(json.dumps(json.loads(outputs['verification.json'])))
