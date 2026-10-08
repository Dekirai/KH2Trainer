"""Reproduce the bounded motion/contact Event27 evidence from original files.
--check is read-only and compares all derived output/manifest hashes.
Requires Python+Capstone and the local original retail files; never runs game code.
"""
import argparse,copy,hashlib,importlib.util,json,struct,sys
from pathlib import Path
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
import asset_audit,event_prefix
HERE=Path(__file__).resolve().parent
def module(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
PEMODULE=HERE.parent/'bdx-trap-registry-20261008/verify.py'
PE=module(PEMODULE,'motion_pe')
def digest(b):return hashlib.sha256(b).hexdigest()
def enc(d):return (json.dumps(d,indent=2,ensure_ascii=False)+'\n').encode()
def number(a):return int(a,16)if isinstance(a,str)else a
ANCHORS={
 0x1403b3220:('mov','rsi, rcx'),
 0x1403b3235:('mov','rcx, rsi'),
 0x1403b323a:('call','0x1404ad240'),
 0x1403b3242:('mov','dword ptr [rsi + 4], eax'),
 0x1403b3a41:('xor','r8d, r8d'),
 0x1403b3a52:('mov','rcx, qword ptr [rsi + 0x920]'),
 0x1403b3a59:('lea','edx, [r8 + 0x17]'),
 0x1403b3a5d:('call','0x1403a6420'),
 0x1403b3a82:('call','0x1404ad270'),
 0x1403b3a8a:('mov','qword ptr [rsi + 0xab8], rax'),
 0x1403b6319:('mov','qword ptr [rcx + 0xab8], rdx'),
 0x1403c9b83:('lea','r9, [r8 + 0x14]'),
 0x1403c9b87:('movsxd','r8, dword ptr [rcx]'),
 0x1403c9b8a:('lea','rax, [rcx + 0x40]'),
 0x1403c9ba8:('movzx','ecx, byte ptr [rax + 4]'),
 0x1403c9bb0:('add','rax, 0x14'),
 0x1403ba5bb:('mov','ecx, dword ptr [rax + 4]'),
 0x1403ba5be:('bt','ecx, ebx'),
 0x1403c80f0:('movsx','ecx, word ptr [rsi + 0x12]'),
 0x1403c80fb:('movzx','r8d, word ptr [rsi + 6]'),
 0x1403c811c:('call','0x1401a8670'),
 0x1403c819c:('call','0x1401a8670'),
 0x1403c81ea:('jmp','0x1401a8d90'),
 0x1401a86c5:('movzx','eax, word ptr [rdx + rax + 4]'),
 0x1401a86ca:('mov','word ptr [rsi + 0x1c], ax'),
 0x1401a86d5:('movss','dword ptr [rsi + 0x18], xmm0'),
 0x1401a86e7:('mov','word ptr [rsi + 0x1e], di'),
 0x1401a86eb:('btr','ecx, 0x15'),
 0x1401c3ad0:('mov','dword ptr [rax - 4], r9d'),
 0x1401c460d:('cmp','r12d, 2'),
 0x1401c4630:('cmp','word ptr [rdi + 0x1c], r14w'),
 0x1401c4637:('add','rdi, 0x20'),
 0x1401c463b:('test','dword ptr [rdi + 0x14], 0x200000'),
 0x1401c468b:('test','dword ptr [rdi + 0x14], 0x80000'),
 0x1401c4694:('movss','xmm9, dword ptr [rdi + 0x18]'),
 0x1401c47e6:('call','0x1401712b0'),
 0x1401c47ef:('or','dword ptr [rdi + 0x10], 1'),
 0x1401c47fd:('call','0x1401a8e60'),
 0x1403c6b29:('mov','esi, 0x10'),
 0x1403c6b51:('call','0x1403c8070'),
 0x1403c6bac:('call','0x1401a4cd0'),
 0x1403c6bcd:('call','0x1401a4d40'),
 0x1401a4d28:('call','0x1401c3a30'),
 0x1401a4df4:('call','qword ptr [r9 + 0x10]'),
 0x1403c6c14:('test','byte ptr [rdi + 0x10], 1'),
 0x1403c6c56:('mov','r8, rdi'),
 0x1403c6c59:('movzx','edx, ax'),
 0x1403c6c5c:('call','0x1403b5e80'),
 0x1403b5ebc:('mov','dword ptr [rsp + 0x34], 0x52444140'),
 0x1403b5ec8:('mov','dword ptr [rsp + 0x3c], 0x544e4940'),
 0x1403b5edc:('lea','r8, [rsp + 0x30]'),
 0x1403b5ee1:('mov','r9d, 3'),
 0x1403b5efc:('lea','edx, [r9 + 0x18]'),
 0x1403b5f00:('call','0x1403e1840'),
 0x14042b490:('mov','edx, dword ptr [rax + 0x180]'),
 0x14042b498:('mov','dword ptr [rbx + 4], 0x544e4940'),
 0x14042d563:('call','0x1404ad270'),
 0x14042d568:('mov','ecx, dword ptr [rax + 4]'),
 0x14042d56b:('call','0x1404ad270'),
 0x14042d584:('call','0x1403b6670')}
def build():
 pe=PE.PE(PE.TARGET);cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
 captures=[json.loads((HERE/n).read_bytes())for n in('capture.json','dispatch-capture.json','resource-capture.json')]
 functions=[];allins={};listing=[];instruction_count=bodybytes=padding=0
 for source in captures:
  for original in source['functions']:
   f=copy.deepcopy(original);a=number(f['addr']);raw,z=pe.read(a,f['size']);assert not z
   assert raw==bytes(int(x,16)for x in f['idaBytes'].split()),f['addr']
   p=f['pages'];d=f['disasm'];rows=d['asm']['lines'];assert d['cursor']['done']
   assert len(rows)==d['instruction_count']==d['total_instructions']==sum(len(x['asm']['lines'])for x in p)
   assert rows==[row for page in p for row in page['asm']['lines']]
   count=0
   for page in p:
    assert page['instruction_count']==len(page['asm']['lines']);count+=page['instruction_count']
    assert page['cursor'].get('done') or page['cursor']['next']==count
   covered=set();decoded=[];listing.append('\n'+f['addr']+' '+f['name'])
   for row in rows:
    x=number(row['addr']);assert a<=x<a+len(raw);i=next(cs.disasm(raw[x-a:x-a+15],x,count=1),None);assert i
    interval=set(range(x-a,x-a+i.size));assert not interval&covered;covered|=interval;allins[x]=i
    decoded.append(dict(addr=hex(x),bytes=i.bytes.hex(),mnemonic=i.mnemonic,operands=i.op_str))
    listing.append(f'{x:016x}  {i.bytes.hex():<30} {i.mnemonic} {i.op_str}')
   missing=sorted(set(range(len(raw)))-covered)
   if missing:
    assert a==0x1401c3a30 and len(missing)==4 and missing==list(range(missing[0],missing[0]+4))
    gap=raw[missing[0]:missing[0]+4];ins=list(cs.disasm(gap,a+missing[0]));assert len(ins)==1 and ins[0].mnemonic=='nop' and ins[0].size==4
   f['originalBytes']=raw.hex(' ');f['sha256']=digest(raw);f['decodedInstructions']=decoded;f['verifiedInstructionCount']=len(decoded);f['unlistedPaddingBytes']=len(missing)
   functions.append(f);instruction_count+=len(rows);bodybytes+=len(raw);padding+=len(missing)
 anchors=[]
 for a,(mn,op)in ANCHORS.items():
  i=allins[a];assert(i.mnemonic,i.op_str)==(mn,op),(hex(a),(i.mnemonic,i.op_str),(mn,op))
  anchors.append(dict(addr=hex(a),bytes=i.bytes.hex(),mnemonic=i.mnemonic,operands=i.op_str))
 data=[]
 for d in captures[0]['data']:
  raw,z=pe.read(number(d['addr']),d['size']);assert not z and raw==bytes(int(x,16)for x in d['data'].split())
  data.append(dict(addr=d['addr'],size=d['size'],idaBytes=d['data'],originalBytes=raw.hex(' '),sha256=digest(raw)))
 assert all(not x.get('more')for x in captures[0]['xrefs']['result'])
 imports=pe.imports();boundaries=[];seen=set()
 for i in allins.values():
  if i.mnemonic not in('call','jmp'):continue
  if len(i.operands)!=1:continue
  op=i.operands[0];iat=None;stub=None
  if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:iat=i.address+i.size+op.mem.disp
  elif op.type==X86_OP_IMM and op.imm not in allins:
   b,z=pe.read(op.imm,15);s=next(cs.disasm(b,op.imm,count=1),None)
   if s and s.mnemonic=='jmp' and s.operands[0].type==X86_OP_MEM and s.operands[0].mem.base==X86_REG_RIP:
    iat=s.address+s.size+s.operands[0].mem.disp;stub=dict(addr=hex(s.address),bytes=s.bytes.hex())
  if iat in imports and (i.address,iat)not in seen:
   seen.add((i.address,iat));dll,symbol=imports[iat];boundaries.append(dict(callsite=hex(i.address),iat=hex(iat),dll=dll,symbol=symbol,originalForwarder=stub))
 census=asset_audit.build();prefix=event_prefix.build();assert not census['errors']
 witness=census['witness'];assert len(witness['event27Instructions'])==201 and not witness['reachableRebindTraps']
 assert witness['wholeScriptRebindTraps']==[dict(pc=21314,bank=2,index=9,inEvent27Closure=False)]
 retail=json.loads((HERE/'retail-witness.json').read_bytes());assert retail['success']and len(retail['results'])==1;r=retail['results'][0]
 assert witness['assetSha256']==r['decodedSha256'] and r['fullLooseIdentical']
 hed=(asset_audit.GAME/'Image/dt'/r['hed']).read_bytes();assert digest(hed)==r['hedSha256']
 row=hed[r['Ordinal']*32:(r['Ordinal']+1)*32];assert row.hex()==r['hedRowHex']
 name,off,stored,original=struct.unpack('<16sQii',row);assert(name.hex(),off,stored,original)==(r['NameHash'],r['Offset'],r['StoredLength'],r['OriginalLength'])
 with (asset_audit.GAME/'Image/dt'/r['pkg']).open('rb')as stream:
  assert stream.seek(0,2)==r['pkgLength'];stream.seek(off);assert digest(stream.read(stored))==r['storedEntrySha256']
 raw=(asset_audit.LOOSE/witness['asset']).read_bytes();assert digest(raw)==r['decodedSha256']
 for child in r['children']:
  b=raw[child['RelativeOffset']:child['RelativeOffset']+child['Length']];assert digest(b)==child['sha256']
 assert witness['type23']['recordEnd']==3344 and len(witness['type23']['contactDefinitions'])==9
 assert {c['jointId']for c in witness['type23']['contactDefinitions']}=={94,103,83,127,121}
 assert not witness['type23']['defaultGroupMask']&(1<<12|1<<13)
 ev=r['children'][0]['script'];assert not ev['HitLimit']and ev['diagnostics']==0
 assert [(x['id'],x['pc'])for x in witness['header']['events']]==[(x['Id'],x['Pc'])for x in ev['events']]
 # Independent native identity of 1:15/1:87, along with all other syntactic Event27 traps.
 descriptors=[]
 for bank,index in sorted({(t['bank'],t['index'])for t in witness['event27Traps']}):
  base=struct.unpack('<Q',pe.read(0x140753490+bank*8,8)[0])[0]
  raw,_=pe.read(base+16*index,16);callback,flags,pad=struct.unpack('<QII',raw)
  assert any(number(d['addr'])==base+16*index and bytes.fromhex(d['originalBytes'])==raw for d in data)
  descriptors.append(dict(bank=bank,index=index,addr=hex(base+16*index),callback=hex(callback),declaredArguments=flags&65535,returnsValue=bool(flags&0x40000000),flags=hex(flags)))
 assert next(d for d in descriptors if(d['bank'],d['index'])==(1,87))['declaredArguments']==4
 evidence=dict(schema=1,Domain='native',originalSha256=PE.SHA,imageBase=hex(pe.base),functions=functions,data=data,semanticAnchors=anchors,imports=boundaries,xrefs=captures[0]['xrefs'],trapDescriptors=descriptors)
 receipt=dict(success=True,scope='Static local original-PE/body-byte verification and bounded stored-asset reproduction. No runtime/lifetime/whole-program closure proof.',functions=len(functions),instructions=instruction_count,bodyBytes=bodybytes,unlistedPaddingBytes=padding,semanticAnchors=len(anchors),directImportBoundaries=len(boundaries),dataSpans=len(data),dataBytes=sum(d['size']for d in data),looseFiles=census['files'],censusTotals=census['totals'],emptyEntries=len(census['emptyEntries']),parseErrors=len(census['errors']),event27Instructions=len(witness['event27Instructions']),scriptPrefixCases=prefix['caseCount'],scriptPrefixTraces=prefix['uniqueTraceCount'],retailStoredEntryHashRevalidated=True,decodedIdentityReceipt='retail-witness.json (reproduce using retail-probe)',limitations=['Nonblended virtual evaluator target not resolved.','Motion pose-cache construction and runtime IK mode activation not proven for this actor.','Native effects beyond first1:87 and callback/dynamic script mutation excluded.','Census covers direct loose obj/*.mdlx only; only selected B_LK120 has retail-package byte identity.'])
 return {'evidence.json':enc(evidence),'listings.txt':('\n'.join(listing)+'\n').encode(),'verification.json':enc(receipt),'asset-census.json':enc(census),'event27-prefixes.json':enc(prefix)}
def manifest():
 names=['capture.json','dispatch-capture.json','resource-capture.json','asset_audit.py','event_prefix.py','verify.py','evidence.json','listings.txt','verification.json','asset-census.json','event27-prefixes.json','retail-witness.json','report.txt','report.json','claims.json','retail-probe/RetailProbe.csproj','retail-probe/Program.cs']
 return dict(schema=1,files={n:dict(sha256=digest((HERE/n).read_bytes()),bytes=(HERE/n).stat().st_size)for n in names},dependencies={str(p.relative_to(HERE.parent)):digest(p.read_bytes())for p in(PEMODULE,asset_audit.DECODER,HERE.parent/'status-worker-observation-20261007/evidence.json',HERE.parent/'actor-rebind-context-20261008/evidence.json')},excluded='retail-probe/bin and obj generated build products; no original raw assets copied')
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
 outputs=build()
 for n,b in outputs.items():
  if args.check:assert (HERE/n).read_bytes()==b,('derived output mismatch',n)
  else:(HERE/n).write_bytes(b)
 if args.check:assert json.loads((HERE/'manifest.json').read_bytes())==manifest(),'manifest mismatch'
 elif (HERE/'report.txt').exists():(HERE/'manifest.json').write_bytes(enc(manifest()))
 print(json.dumps(json.loads(outputs['verification.json'])))
