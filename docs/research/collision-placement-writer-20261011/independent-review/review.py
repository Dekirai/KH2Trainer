"""Independent bounded source/PE/claim review. Never modifies author artifacts."""
import hashlib, json, pathlib, struct, subprocess, sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

HERE=pathlib.Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'src/KH2Trainer.Core').is_dir())
AUTHOR=ROOT/'artifacts/collision-placement-writer-20261011'
ORIGINAL=pathlib.Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
EXPECTED='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
MANIFEST='6d202c02813e9a35518a6012b34a7846ed2ec7b360be9f87164a437b64b669e9'
BASE=0x140000000
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_bytes())
def enc(v):return (json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode()
checks=0
def need(test,label):
 global checks
 checks+=1
 if not test:raise AssertionError(label)

def run():
 manifestBytes=(AUTHOR/'manifest.json').read_bytes()
 need(sha(manifestBytes)==MANIFEST,'final author manifest pin')
 manifest=json.loads(manifestBytes)
 actual={p.relative_to(AUTHOR).as_posix() for p in AUTHOR.rglob('*') if p.is_file() and p.name!='manifest.json'}
 need(actual=={x['path'] for x in manifest['files']},'exact frozen34-member set')
 for x in manifest['files']:
  b=(AUTHOR/x['path']).read_bytes();need(len(b)==x['length'] and sha(b)==x['sha256'],'member '+x['path'])
 original=ORIGINAL.read_bytes();need(sha(original)==EXPECTED,'original EXE identity')
 pe=struct.unpack_from('<I',original,60)[0];optional=pe+24
 need(original[pe:pe+4]==b'PE\0\0' and struct.unpack_from('<H',original,pe+4)[0]==0x8664,'PE64 machine')
 need(struct.unpack_from('<Q',original,optional+24)[0]==BASE,'image base')
 sections=optional+struct.unpack_from('<H',original,pe+20)[0]
 sections=[struct.unpack_from('<8sIIII',original,sections+40*n) for n in range(struct.unpack_from('<H',original,pe+6)[0])]
 def bytes_at(addr,size):
  rva=addr-BASE
  match=[raw+rva-va for name,vs,va,rs,raw in sections if va<=rva and size<=rs-(rva-va)]
  need(len(match)==1 and size>0,'unique PE-backed body')
  return original[match[0]:match[0]+size]
 evidence=read(AUTHOR/'evidence.json');cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
 instructions={};fresh=0;reuse=0;bytecount=0;source_cache={}
 for f in evidence['functions']:
  addr=int(f['addr'],16);body=bytes.fromhex(f['originalBytes'])
  need(len(body)==f['size'] and body==bytes_at(addr,len(body)),'independent original body '+f['addr'])
  pages=f['pages'];lines=[]
  for page in pages:
   need(page.get('offset',len(lines))==len(lines),'page start')
   lines.extend(page['asm']['lines'])
   need(page['cursor'].get('done') or page['cursor'].get('next')==len(lines),'page continuation')
  need(pages[-1]['cursor'].get('done') and lines==f['disassembly']['asm']['lines'],'full joined listing')
  spans=set()
  for row in lines:
   pc=int(row['addr'],16);need(addr<=pc<addr+len(body),'instruction begins in body')
   i=next(cs.disasm(body[pc-addr:],pc,count=1));covered=set(range(pc,pc+i.size))
   need(pc+i.size<=addr+len(body) and not covered.intersection(spans),'instruction span exact/no overlap')
   spans.update(covered);instructions[pc]=i
  need(len(spans)==len(body),'entire IDA body decoded')
  if f['sourceMetadata']['freshCapture']:
   fresh+=1
   raw=read(AUTHOR/f['sourceMetadata']['disasmFile'])
   need(raw['asm']['lines']==lines and raw['instruction_count']==raw['total_instructions']==len(lines),'fresh raw capture correspondence')
  else:
   reuse+=1;p=ROOT/f['sourceMetadata']['path']
   need(sha(p.read_bytes())==f['sourceMetadata']['sha256'],'prior source pin')
   if str(p) not in source_cache:source_cache[str(p)]=read(p)
   old=next(o for o in source_cache[str(p)]['functions'] if int(o['addr'],16)==addr)
   need(bytes.fromhex(old['originalBytes'])==body and old['size']==len(body),'reused body exact identity')
  bytecount+=len(body)
 need((fresh,reuse,len(instructions),bytecount)==(8,18,2045,8796),'independent evidence totals')
 def op(rva,mnemonic,operand):
  i=instructions[BASE+rva]
  need(i.mnemonic==mnemonic and operand in i.op_str,f'claim operation{rva:x} {i.mnemonic} {i.op_str}')
 anchors=[
  (0x175323,'and','ecx, 0xfffffffd'),(0x175326,'or','ecx, 4'),
  (0x1754b3,'divss','xmm0, xmm7'),(0x1754b7,'cvttss2si','r14d, xmm0'),
  (0x1754bc,'inc','r14d'),(0x17567d,'jle','0x1401757bd'),
  (0x17564c,'mov','eax, r12d'),(0x17564f,'jmp','0x1401758d3'),
  (0x17579a,'or','dword ptr [rdi + 0x74], 4'),
  (0x1758b0,'call','0x140173b30'),(0x1758b9,'mov','rdx, rdi'),
  (0x1758bc,'lea','[rdi + 0x30]'),(0x1758c0,'call','0x1401a8e60'),
  (0x1758c8,'jmp','0x1401758e2'),(0x1758cd,'shr','eax, 2'),
  (0x16fecf,'and','[rcx + 0x74], 0xfffffffb'),(0x16fed6,'mov','[rcx + 0x62], 0xffffffff'),
  (0x16ff09,'or','esi, ebx'),(0x16ff81,'and','[rdi + 0x74], 0xfffffffd'),
  (0x3d1995,'movzx','ebx, dx'),(0x3d1a19,'or','[rsi + 8], eax'),
  (0x3d1a1c,'lea','[rsi + 0xb4]'),(0x3d1a26,'call','0x1401a8e60'),
  (0x3d1a64,'shl','rdx, cl'),(0x3d1aff,'shr','eax, 8'),
  (0x3d1b04,'jne','0x1403d1b2b'),(0x3d1b24,'call','[r9 + 0xd8]'),
  (0x17351e,'movzx','[rax + r8*8 + 0xa]'),(0x173528,'add','[rcx + 0x30]'),
  (0x1735c2,'call','0x14013f900'),(0x1735e3,'call','0x140142080'),
  (0x17330b,'movzx','[rax + r8*8 + 0xe]'),(0x173315,'lea','[rax + rdx*4]')]
 for a in anchors:op(*a)
 report=read(AUTHOR/'report.json');need(len(report['claims'])==10,'ten bounded claims')
 need(not any(' bit4' in c['Finding'] or ' bit256' in c['Finding'] for c in report['claims']),'reported bit-mask ambiguity corrected')
 # Independently chosen semantic obligations, checked against the stored traces.
 models=read(AUTHOR/'model-results.json');cases={c['name']:c for c in models['cases']}
 examples=[
  ('empty candidates moves output yet returns false',[11,8,4,1],'0x0'),
  ('final segment hit restores original point and returns false',[1,10,3,1],'0x0'),
  ('incoming correction bit survives standalone call',[11,8,4,1],'0x1'),
  ('zero radius conversion skips step loop and retains old output',[99,105,97,96],'0x0')]
 for name,output,result in examples:
  c=cases[name];need(c['output']==output and c['returnRax']==result,'semantic trace '+name)
 for c in models['cases']:
  if 'writer attribute' in c['name']:
   need(c['point']==[7,8,9,4],'writer preserves full pointW')
   expected=hex(c['flags']>>8) if c['flags']&0x100 else '0xabcd'
   need(c['returnRax']==expected,'writer callback/raw-flag return distinguished')
  if c['name'].startswith('writer optional effects'):
   need(all(e['storedPoint']==[7,8,9,4] for e in c['effects']),'store precedes opaque call observations')
   need(c['effects'][-1]['name']=='virtual+216' and c['returnRax']=='0x0','zero callback does not define placement failure')
 need(cases['caller returns its own Boolean queryTrue']['returnRax']=='0x1','caller Boolean independent of zero callback')
 need(models['summary']['cases']==60 and models['summary']['instructionSteps']==15185,'bounded author model roster')
 # Reproduce author checker read-only. Its own selected interpreter remains author
 # evidence; this review does not rename those60 cases independent native tests.
 completed=subprocess.run([sys.executable,'-B',str(AUTHOR/'verify.py'),'--check'],cwd=ROOT,capture_output=True,text=True)
 (HERE/'author-reproduction.txt').write_text(completed.stdout+completed.stderr,encoding='utf-8')
 need(completed.returncode==0,'author reproduction PASS')
 need((AUTHOR/'manifest.json').read_bytes()==manifestBytes,'author manifest unchanged after checker')
 for x in manifest['files']:need(sha((AUTHOR/x['path']).read_bytes())==x['sha256'],'author file unchanged '+x['path'])
 receipt={'schemaVersion':1,'status':'accepted','authorManifestSha256':MANIFEST,
  'authorEvidenceSha256':sha((AUTHOR/'evidence.json').read_bytes()),'authorReportSha256':sha((AUTHOR/'report.json').read_bytes()),
  'independentChecks':checks,'originalExeSha256':EXPECTED,'freshBodies':fresh,'reusedBodies':reuse,
  'originalBytes':bytecount,'decodedInstructions':len(instructions),'specificDecodedAnchors':len(anchors),
  'authorReproduction':{'status':'PASS','cases':60,'instructionSteps':15185,'kind':'author interpreter reproduced; not independent native execution'},
  'findings':[{'id':'ambiguous-bit-labels','severity':'wording','status':'fixed before final freeze','resolution':'Claims now use explicit0x04/0x02/0x100/0x40 masks.'}],
  'manualConclusions':['Query return0 can accompany either moved target or restored start; it cannot approve collision-free placement.',
   'State+116 mask0x04 persists in1752E0;16FEC0 explicitly clears it before moving/static chain.',
   '3D1960 directly stores a full float4 at object+180; optional callouts and virtual+216 occur afterward and remain opaque.',
   'Writer return is shifted flags or callback result;3D0BB0 overwrites AL=1 after ordinary writer return.',
   'Matrix+100 normal path drops translation and normalizes XYZ; no general inverse-transpose or affine-pair proof.',
   'Radius and finite/subdivision validation are absent locally; a bounded masked-FP zero-radius fixture preserves oldXYZ before Yoffset addition.',
   '16FEC0/moving-list sequencing is supported; no initialized complete Actor-body layout or linked-resource lifetime is inferred.',
   'Eight fresh captures plus18 byte-identical dependencies are separate from ten claim rows; no26-new-functions credit.'],
  'limitations':['No game/process/GUI/attach/native-engine execution','No collision-free placement or teleport API approval',
   'Original instruction models have explicit collector/corrector/final-query/opaque-callback boundaries',
   'The moving-list traversal was statically reviewed and is not instruction-modeled by the author',
   'No fresh IDA session or database mutation by reviewer; captured original bytes independently verified'],
  'sourcePin':sha(pathlib.Path(__file__).read_bytes())}
 (HERE/'review.json').write_bytes(enc(receipt))
 members=[{'path':p.name,'size':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='manifest.json']
 (HERE/'manifest.json').write_bytes(enc({'schemaVersion':1,'files':members}))
 print(json.dumps({'status':'accepted','independentChecks':checks,'receiptSha256':sha((HERE/'review.json').read_bytes()),'manifestSha256':sha((HERE/'manifest.json').read_bytes())}))

if __name__=='__main__':run()
