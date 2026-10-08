"""Bounded, offline native/data verification. Never executes game code.

--check is read-only. The separate retail-probe reproduces PKG decompression;
this verifier rechecks its original HED/stored-entry hashes and loose payloads.
"""
import argparse, copy, hashlib, importlib.util, json, struct
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PEFILE = HERE.parent / 'bdx-trap-registry-20261008/verify.py'
spec = importlib.util.spec_from_file_location('audience_original_pe', PEFILE)
pm = importlib.util.module_from_spec(spec); spec.loader.exec_module(pm)
GAME = pm.TARGET.parent
LOOSE = GAME / 'Modding/openkh/data/kh2'
SOURCE = HERE.parent / 'timer-message74-handlers-20261008/script-analysis.json'
def sha(b): return hashlib.sha256(b).hexdigest()
def enc(x): return (json.dumps(x, indent=2, ensure_ascii=False)+'\n').encode('utf-8')
def num(x): return int(x,16) if isinstance(x,str) else x
def octets(x): return bytes(int(s,16) for s in x.split())
def read_json(p): return json.loads(p.read_bytes())

# Exact, manually reviewed semantic anchors. These do not assert callees' closure.
ANCHORS = {
 0x14042be0e:('mov','r9d, edi'), 0x14042be11:('mov','r8d, esi'),
 0x14042be14:('mov','rdx, rbx'), 0x14042be17:('mov','rcx, rax'),
 0x14042be2c:('jmp','qword ptr [r10 + 0xa0]'),
 0x1403dfa13:('movzx','eax, byte ptr [rbx + 4]'),
 0x1403dfa17:('cmp','eax, 0x18'), 0x1403dfad9:('mov','ecx, 0xd48'),
 0x1403dfade:('call','0x140152430'), 0x1403dfae6:('je','0x1403dfe2a'),
 0x1403dfb07:('jmp','0x140406940'),
 0x140406958:('call','0x140410940'),
 0x14040695d:('lea','rcx, [rip + 0x349c24]'),
 0x140406969:('mov','dword ptr [rbx], eax'),
 0x140410955:('call','0x1403d2da0'), 0x1403d2db5:('call','0x1403da940'),
 0x1403da97d:('call','0x1403b3200'),
 0x1403b323a:('call','0x1404ad240'), 0x1403b3242:('mov','dword ptr [rsi + 4], eax'),
 0x1403b3709:('lea','rcx, [rsi + 0x910]'),
 0x1403b3710:('mov','r8, rbp'), 0x1403b3713:('call','0x1403e63d0'),
 0x140406813:('mov','rcx, rdx'), 0x140406816:('mov','edx, eax'),
 0x140406818:('mov','r8d, r9d'), 0x14040681b:('jmp','0x1403dad90'),
 0x1403dada5:('mov','ecx, dword ptr [rcx + 0xbb4]'),
 0x1403dadb5:('je','0x1403dadd2'), 0x1403dadc5:('mov','r9, rbx'),
 0x1403dadcd:('call','0x1403ce580'),
 0x1403ce586:('cmp','dword ptr [rcx + 0xc], 0'),
 0x1403ce58d:('jge','0x1403ce595'),
 0x1403ce58f:('cmp','dword ptr [rcx + 0x14], 0'),
 0x1403ce593:('je','0x1403ce59b'),
 0x1403ce595:('cmp','r8d, dword ptr [rcx + 0x10]'),
 0x1403ce599:('jl','0x1403ce5ad'),
 0x1403ce59b:('mov','dword ptr [rcx + 0xc], edx'),
 0x1403ce59e:('mov','dword ptr [rcx + 0x10], r8d'),
 0x1403ce5aa:('mov','dword ptr [rbx + 0x1c], eax'),
 0x1403da99d:('mov','dword ptr [rdi + 0xbb4], eax'),
 0x1403da9a5:('mov','dword ptr [r14 + 0xc], 0xffffffff'),
 0x1403da9ce:('mov','qword ptr [r14], r12'),
 0x1403da9f8:('mov','rcx, qword ptr [rdi + 0x928]'),
 0x1403daa02:('je','0x1403dab4f'),
 0x1403daa84:('lea','edx, [r8 + 0x22]'),
 0x1403daa93:('je','0x1403daadb'), 0x1403daaa0:('je','0x1403daadb'),
 0x1403daac4:('mov','qword ptr [r14 + 0x20], rax'),
 0x1403daad5:('mov','dword ptr [rdi + 0xbb4], eax'),
 0x1403e6420:('mov','qword ptr [rbx + 0x18], rax'),
 0x1403e6466:('jmp','0x1403e6120'),
 0x1403e615e:('movzx','eax, byte ptr [rcx + 0x48]'),
 0x1403e6162:('not','al'), 0x1403e6164:('test','al, 1'),
 0x1403e6166:('je','0x1403e617d'), 0x1403e6179:('mov','qword ptr [rbx + 0x18], rax'),
 0x1403e0ac1:('jne','0x1403e0acb'), 0x1403e0ac3:('xor','eax, eax'),
 0x1403e0af8:('lea','r8, [rdi + 8]'),
 0x1403e0f3f:('movsxd','r8, dword ptr [rdx + 4]'),
 0x1403e0f46:('add','rdx, 8'), 0x1403e0f4f:('mov','r9d, 0x60'),
 0x1403e0f5e:('jne','0x1403e0f6d'), 0x1403e0f66:('cmp','ebx, 3'),
 0x14039cb08:('call','0x1403e0440'),
 0x1403e0444:('mov','rcx, qword ptr [rip + 0x36c8bd]'),
 0x1403e044b:('call','0x1403e5fa0'), 0x1403e0457:('jmp','0x1403e0e00'),
 0x1404066b3:('jmp','0x1403dad10'), 0x1404066e3:('jmp','0x1403dac30'),
 0x1403ce273:('test','esi, esi'), 0x1403ce275:('js','0x1403ce2c6'),
 0x1403ce282:('call','0x1401de500'),
 0x1403ce291:('mov','dword ptr [rdi + 0xc], 0xffffffff'),
 0x1403ce2a3:('call','0x1403b5b40'),
 0x1403ce2b0:('call','qword ptr [rbx + 8]'),
 0x1403ce2b8:('mov','dword ptr [rdi + 0x14], eax'),
 0x1403ce560:('mov','r9d, dword ptr [rcx + 0x18]'),
 0x1403ce564:('mov','rcx, qword ptr [rcx + 0x20]'),
 0x1403ce568:('jmp','0x1401de230'),
 0x1403dad40:('call','0x1403ce260'), 0x1403dac74:('call','0x1403ce260'),
 0x1401de268:('cmp','eax, 0x10'), 0x1401de26b:('jle','0x1401de303'),
 0x1401de278:('cmp','r10d, 0x18'), 0x1401de27c:('jg','0x1401de303'),
 0x1401de2ba:('call','0x1401deb50'),
 0x1401de2f6:('mov','qword ptr [rbx + 0x18], r14'),
 0x1401de2fa:('mov','dword ptr [rbx + 0x10], ebp'),
 0x1401de2fd:('mov','word ptr [rbx + 0x2e], di'),
}

def model_checks():
 # Separate logical predicate versus the observed CMP/JGE/JZ/CMP/JL path.
 def signed(v): return (v&0xffffffff)-0x100000000 if v&0x80000000 else v&0xffffffff
 def branches(pending,handle,old,new):
  if signed(pending)>=0:
   return not signed(new)<signed(old)
  if handle==0: return True
  return not signed(new)<signed(old)
 values=[0,1,3,8,0x7fffffff,0x80000000,0xffffffff]
 count=0
 for pending in values:
  for handle in (0,1,0xffffffff):
   for old in values:
    for new in values:
     expected=(signed(pending)<0 and handle==0) or signed(new)>=signed(old)
     assert branches(pending,handle,old,new)==expected;count+=1
 # Lower priority can replace an entirely idle entry, ties replace busy entries.
 assert branches(0xffffffff,0,8,3)
 assert not branches(8,0,8,3)
 assert branches(8,1,3,3)
 assert not branches(8,1,3,0xffffffff)
 assert branches(8,1,0xffffffff,3)
 return dict(priorityCases=count,edgeChecks=5,scope='Synthetic branch-equivalence only; no game execution, schedule, lifetime or backend validation.')

def verify_native(pe):
 cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
 aliases={'retn':'ret','jz':'je','jnz':'jne','jnb':'jae','cmovz':'cmove','cmovnz':'cmovne','setz':'sete','setnz':'setne','setnb':'setae'}
 functions=[];ins={};listing=[];data=[];uncovered=[];imports=[]
 for name in ['capture.json','additional-capture.json']:
  cap=read_json(HERE/name);assert cap['Domain']=='native' and cap['originalSha256']==pm.SHA and num(cap['imageBase'])==pe.base
  for original in cap['functions']:
   f=copy.deepcopy(original);at=num(f['addr']);raw,z=pe.read(at,f['size']);assert not z and raw==octets(f['idaBytes'])
   body=f['disassembly'];lines=body['asm']['lines'];pages=f['pages'];gathered=[];count=0
   assert num(body['addr'])==num(body['asm']['start_ea'])==at
   assert body['instruction_count']==body['total_instructions']==len(lines)>0
   assert body['cursor'].get('done') is True and not body['cursor'].get('cancelled') and body['cursor'].get('next') is None
   for index,page in enumerate(pages):
    assert page['offset']==count and num(page['addr'])==num(page['asm']['start_ea'])==at
    assert page['total_instructions']==len(lines) and page['instruction_count']==len(page['asm']['lines'])
    assert not page.get('truncated') and not page['cursor'].get('cancelled')
    count+=page['instruction_count'];gathered+=page['asm']['lines']
    if index==len(pages)-1: assert page['cursor'].get('done') is True and page['cursor'].get('next') is None
    else: assert not page['cursor'].get('done') and page['cursor'].get('next')==count
   assert gathered==lines and count==len(lines)
   dcount=0
   for index,page in enumerate(f['pseudocode']['pages']):
    assert page['offset']==dcount and not page['cursor'].get('cancelled')
    assert page['line_count']==len(page['code'].splitlines());dcount+=page['line_count']
    # IDA marks every slice of a paginated decompilation truncated, including
    # the last slice. Completeness is checked across exact cursor/offset sums.
    assert bool(page.get('truncated'))==(page['line_count']<page['total_lines'])
    if index==len(f['pseudocode']['pages'])-1: assert page['cursor'].get('done') is True and dcount==page['total_lines']
    else: assert page['cursor'].get('next')==dcount and not page['cursor'].get('done')
   assert f['pseudocode']['cursor'].get('done') is True
   pcs=[num(r['addr']) for r in lines];assert pcs==sorted(set(pcs)) and pcs[0]==at
   covered=set();decoded=[];listing.append('\n'+f['addr']+' '+f['name'])
   for row in lines:
    pc=num(row['addr']);assert at<=pc<at+len(raw)
    i=next(cs.disasm(raw[pc-at:pc-at+15],pc,count=1));span=set(range(pc-at,pc-at+i.size))
    assert not span&covered and max(span)<len(raw);covered|=span
    mn=row['instruction'].split()[0].lower();assert mn==i.mnemonic or aliases.get(mn)==i.mnemonic,(hex(pc),mn,i.mnemonic)
    assert pc not in ins;ins[pc]=i
    decoded.append(dict(addr=hex(pc),bytes=i.bytes.hex(),size=i.size,mnemonic=i.mnemonic,operands=i.op_str))
    listing.append(f'{pc:016x} {i.bytes.hex():<30} {i.mnemonic} {i.op_str}')
   gaps=sorted(set(range(len(raw)))-covered)
   # Only two known trailing native switch tables, never promote them to code.
   expected={0x1403df930:(0x50c,0x570),0x1403dfeb0:(0x190,0x2a5)}.get(at)
   if expected: assert gaps==list(range(*expected)),(hex(at),gaps[:20],len(gaps))
   else: assert not gaps,(hex(at),gaps[:20])
   if gaps:
    g=dict(function=f['addr'],addr=hex(at+gaps[0]),length=len(gaps),originalBytes=raw[gaps[0]:].hex(' '),role='Trailing switch-table data, not instructions')
    uncovered.append(g);listing.append('DATA '+g['addr']+' '+g['originalBytes'])
   f['originalBytes']=raw.hex(' ');f['sha256']=sha(raw);f['decodedInstructions']=decoded
   f['sourceCapture']=name;functions.append(f)
  for r in cap.get('data',[]):
   raw,z=pe.read(num(r['addr']),r['size']);assert not z and raw==octets(r['data'])
   data.append(dict(name=r['name'],addr=r['addr'],size=r['size'],originalBytes=raw.hex(' '),sha256=sha(raw)))
 for addr,pair in ANCHORS.items(): assert (ins[addr].mnemonic,ins[addr].op_str)==pair,(hex(addr),pair,ins[addr].mnemonic,ins[addr].op_str)
 importmap=pe.imports()
 for pc,i in sorted(ins.items()):
  if i.mnemonic not in ('call','jmp') or not i.operands:continue
  op=i.operands[0]
  if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
   target=pc+i.size+op.mem.disp
   if target in importmap: imports.append(dict(site=hex(pc),iat=hex(target),dll=importmap[target][0],symbol=importmap[target][1],bytes=i.bytes.hex()))
 assert any(r['symbol']=='bsearch' and r['site']=='0x1403e0f55' for r in imports)
 def read(a,n):
  b,z=pe.read(a,n);assert not z;return b
 def q(a): return struct.unpack('<Q',read(a,8))[0]
 assert q(0x140750588)==0x1405cc860 and q(0x1405cc860+0xa0)==0x140406810
 assert q(0x1405cc860+0x28)==0x1404066b0 and q(0x1405cc860+0x40)==0x1404066e0
 assert q(0x1405cc858)==0x14067b9e0 and q(0x1405c6ad8)==0x140679f10
 assert struct.unpack('<6I',read(0x14067b9e0,24))==(1,0,0,0x795dc0,0x67ba08,0x67b9e0)
 assert struct.unpack('<6I',read(0x140679f10,24))==(1,0,0,0x795310,0x679f38,0x679f10)
 assert read(0x140795dd0,48).split(b'\0')[0]==b'.?AV?$VTABLE@VBTLNPC@YS@@@BTLOBJ@YS@@'
 assert read(0x140795320,24).split(b'\0')[0]==b'.?AVVOICE_EE@YS@@'
 assert q(0x1405c6ae8)==0x1403ce560
 assert struct.unpack('<I',read(0x1403dfe3c+9*4,4))[0]==0x3dfad9
 assert struct.unpack('<QII',read(0x1407563d0,16))==(0x14042bde0,3,0)
 assert q(0x14074cd08)==0x1405bca68 and read(0x1405bca68,15)==b'00objentry.bin\0'
 evidence=dict(schema=1,Domain='native',originalSha256=pm.SHA,imageBase=hex(pe.base),functions=functions,data=data,trailingData=uncovered,imports=imports,semanticAnchors=[dict(addr=hex(a),mnemonic=p[0],operands=p[1],bytes=ins[a].bytes.hex()) for a,p in ANCHORS.items()],limits='34 selected complete IDA function listings and primary byte extents. Two trailing switch tables are data. No transitive semantic closure, complete xref inventory, or runtime execution claim.')
 return evidence,'\n'.join(listing)+'\n',dict(functions=len(functions),instructions=len(ins),primaryBytes=sum(f['size'] for f in functions),trailingDataBytes=sum(g['length'] for g in uncovered),dataSpans=len(data),semanticAnchors=len(ANCHORS),importSites=len(imports))

def verify_assets():
 receipt=read_json(HERE/'retail-witnesses.json');assert receipt['success'] is True and len(receipt['results'])==2
 selected_script=None;objectrow=None
 for row in receipt['results']:
  hed=(GAME/'Image/dt'/row['hed']).read_bytes();assert sha(hed)==row['hedSha256']
  record=hed[row['Ordinal']*32:(row['Ordinal']+1)*32];assert record.hex()==row['hedRowHex']
  assert record[:16].hex()==row['NameHash']
  assert struct.unpack('<QII',record[16:])==(row['Offset'],row['StoredLength'],row['OriginalLength'])
  pkg=GAME/'Image/dt'/row['pkg'];assert pkg.stat().st_size==row['pkgLength']
  with pkg.open('rb') as stream:stream.seek(row['Offset']);stored=stream.read(row['StoredLength'])
  assert sha(stored)==row['storedEntrySha256']
  raw=(LOOSE/row['asset']).read_bytes();assert len(raw)==row['decodedBytes']==row['OriginalLength'] and sha(raw)==row['decodedSha256'] and row['fullLooseIdentical'] is True
  if row['asset']=='00objentry.bin':
   assert struct.unpack('<II',raw[:8])==(3,1900);ids=[struct.unpack_from('<I',raw,8+96*n)[0] for n in range(1900)];assert ids==sorted(set(ids))
   s=row['selected'];assert s['recordBytes']==96 and s['headerBytes']==8 and s['trailingBytes']==8
   match=s['matches'][0];assert len(s['matches'])==1 and match['row']==1514 and match['offset']==8+96*1514
   objectrow=raw[match['offset']:match['offset']+96];assert objectrow.hex()==match['rowHex']
   assert struct.unpack_from('<I',objectrow,0)[0]==2149 and objectrow[4]==9 and struct.unpack_from('<I',objectrow,72)[0]==1
   assert objectrow[8:40].split(b'\0')[0]==b'N_EX650_BTL10'
  else:
   assert raw[:4]==b'BAR\x01' and struct.unpack_from('<I',raw,4)[0]==3
   for child in row['selected']['barEntries']:
    kind=struct.unpack_from('<H',raw,16+child['Ordinal']*16)[0]
    off,n=struct.unpack_from('<II',raw,24+child['Ordinal']*16)
    assert kind==child['Type'] and off==child['RelativeOffset'] and n==child['Length'] and off+n<=len(raw)
    b=raw[off:off+n];assert sha(b)==child['sha256']
    if kind==3:selected_script=b
   assert all(c['Type']!=34 for c in row['selected']['barEntries'])
 assert selected_script is not None and objectrow is not None
 source=read_json(SOURCE);selected=next(s for s in source['selected'] if s['asset']=='obj/N_EX650_BTL10.mdlx')
 assert sha(selected_script)==selected['scriptSha256']=='f0c8b6a2f315b78190404607a290d9b8fb9b60cee85fd874d91279bda8aa4efc'
 for r in selected['event0Instructions']+selected['event10Instructions']:
  off=16+2*r['pc'];assert r['fileOffset']==off and selected_script[off:off+2*r['width']].hex()==r['raw']
 assert selected['wrapperWorkOffset']==0 and selected['wrapperBindingStores']==[dict(pc=862,address=['work',4],value=['incoming Actor',0])]
 for case in selected['cases']:
  if case['message']!=74:continue
  requests=[r for r in case['result']['native'] if (r['bank'],r['index'])==(1,262)]
  assert bool(requests)==(case['assumptions']['summaries']['1:39']==1)
  if requests:assert requests==[dict(pc=73,bank=1,index=262,stackBefore=[74,['work',0],8,3])]
 # Evidence is an exact selected upstream model, plus raw instruction rechecks;
 # this does not rerun or extend that model across unknown native calls.
 out=dict(schema=1,source=SOURCE.relative_to(ROOT).as_posix(),sourceSha256=sha(SOURCE.read_bytes()),selected=selected,rawInstructionChecks=len(selected['event0Instructions'])+len(selected['event10Instructions']),limits='Reuses the frozen bounded Event0/Event10 symbolic model. Every selected instruction is checked against the same original-archive-pinned script. No new runtime, whole-script or native-side-effect emulation.')
 return out,dict(originalAssets=2,objentryRecordsChecked=1900,selectedId=2149,type=9,flags72=1,scriptInstructions=out['rawInstructionChecks'])

def manifest():
 files={}
 for p in sorted(HERE.rglob('*')):
  rel=p.relative_to(HERE)
  if p.is_file() and p.name!='manifest.json' and not {'bin','obj','artifacts','__pycache__'}&set(rel.parts):files[rel.as_posix()]=sha(p.read_bytes())
 return dict(schema=1,originalSha256=pm.SHA,files=files)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
 pins=read_json(HERE/'provenance.json')
 for r in pins['files']:
  path=ROOT/r['path'];assert sha(path.read_bytes())==r['sha256'],r['path']
 pe=pm.PE(pm.TARGET);e,listing,native=verify_native(pe);script,assets=verify_assets();model=model_checks()
 outputs={'evidence.json':enc(e),'native-asm.txt':listing.encode('utf-8'),'selected-script.json':enc(script),'verification.json':enc(dict(success=True,originalSha256=pm.SHA,native=native,assets=assets,model=model,limits=['No execution or process inspection.','No all-writers, all-callers, concrete live-instance, backend voice-ID mapping, or guaranteed update scheduling proof.','Fresh package decompression is separately reproducible through retail-probe; --check verifies captured original stored bytes and exact loose payload identities.']))}
 for name,b in outputs.items():
  if args.check:assert (HERE/name).read_bytes()==b,name
  else:(HERE/name).write_bytes(b)
 # All claim text is human-reviewed; this only enforces reference address coverage.
 if (HERE/'claims.json').exists():
  import re
  addresses={f['addr'].lower() for f in e['functions']}
  for carrier in ['claims.json','report.json']:
   for c in read_json(HERE/carrier)['claims']:
    assert c['addr'].lower() in addresses
    assert isinstance(c['Evidence'],list) and c['Evidence']
    for reference in c['Evidence']:
     assert isinstance(reference,str) and reference
     for a in re.findall(r'evidence\.json#functions\[addr=(0x[0-9a-fA-F]+)\]',reference):assert a.lower() in addresses
 if args.check:assert read_json(HERE/'manifest.json')==manifest(),'manifest'
 else:(HERE/'manifest.json').write_bytes(enc(manifest()))
 print(json.dumps(dict(success=True,native=native,assets=assets,model=model)))
if __name__=='__main__':main()
