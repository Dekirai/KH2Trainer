"""Offline verification only. Original executable is read as a file; never executed."""
import argparse,ast,hashlib,json,pathlib,re,runpy,struct
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_MEM
import models
H=pathlib.Path(__file__).resolve().parent
ROOT=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir())
EXE=pathlib.Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
EXPECTED='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(b):return hashlib.sha256(b).hexdigest()
def bs(s):return bytes(int(x,16) for x in s.split())
def a(s):return int(s,16)
def unwrap(d):return d.get('structuredContent',d)
def result(name,v,write):
 p=H/name
 if write:p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 else:assert read(p)==v,name+' differs; do not accept stale results'
def main(write=False):
 pe=EXE.read_bytes();assert digest(pe)==EXPECTED
 off=struct.unpack_from('<I',pe,0x3c)[0]; assert pe[off:off+4]==b'PE\0\0'
 count=struct.unpack_from('<H',pe,off+6)[0]; opt=struct.unpack_from('<H',pe,off+20)[0]
 imagebase=struct.unpack_from('<Q',pe,off+24+24)[0];assert imagebase==0x140000000
 sections=[struct.unpack_from('<8sIIII',pe,off+24+opt+40*i) for i in range(count)]
 def original(va,n):
  rva=va-imagebase
  for _,vs,rs,sz,ptr in sections:
   if rs<=rva and n<=sz and rva-rs<=sz-n:return pe[ptr+rva-rs:ptr+rva-rs+n]
  raise AssertionError('not file-backed '+hex(va))
 ev=read(H/'evidence.json');fs=sorted(ev['functions']+ev['code_ranges'],key=lambda f:a(f['addr']));assert len({f['addr'] for f in fs})==len(fs)
 assert {f['addr'] for f in ev['code_ranges']}=={'0x14039dee0'}
 assert all(f['addr']!='0x14039dee0' for f in ev['functions'])
 assert ev['code_ranges'][0]['classification']=='separate_code_range_not_inventory_function'
 assert a(ev['code_ranges'][0]['end_exclusive'])==0x14039def3
 row=ev['code_ranges'][0]
 assert row['asm']==row['disassembly']['asm']
 assert type(row['observed_line_count']) is int and row['observed_line_count']==len(row['asm']['lines'])==6
 # Run only the unchanged parser's actual range predicate and its helpers, never its global run.
 parser_path=ROOT/'scripts/update-analysis-coverage.py'
 parser_source=parser_path.read_text(encoding='utf-8-sig')
 namespace=runpy.run_path(str(parser_path),run_name='coverage_range_schema_only')
 predicates=[n.value for n in ast.walk(ast.parse(parser_source)) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='valid_range' for t in n.targets)]
 assert len(predicates)==1
 spans=namespace['original_spans'](row)
 line_addresses=[namespace['address'](x.get('addr')) for x in row['asm']['lines']]
 predicate_scope={'a':namespace['va'](row.get('addr')),'end':namespace['address'](row.get('end_exclusive')),'spans':spans,'row':row,'line_addresses':line_addresses}
 range_valid=eval(compile(ast.Expression(predicates[0]),str(parser_path),'eval'),namespace|predicate_scope)
 assert range_valid is True and len(line_addresses)==6 and sum(len(b) for _,b in spans)==19
 range_check={'recordedRangeValidated':range_valid,'observedInstructionCount':len(line_addresses),'recordedByteCount':sum(len(b) for _,b in spans),'parserSha256':digest(parser_path.read_bytes()),'method':'Actual valid_range AST expression plus unchanged original_spans/address/va helpers; no global coverage run'}
 deps=read(H/'dependencies.json')['dependencies'];sourcecache={}
 for dep in read(H/'dependencies.json')['contextDependencies']:
  assert digest((ROOT/dep['path']).read_bytes())==dep['sha256'],dep['path']
 for dep in deps:
  p=ROOT/dep['path'];assert digest(p.read_bytes())==dep['sha256'],str(p)
  sourcecache[dep['path']]=read(p)
 cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
 instructions={};bodyresults=[];totalbytes=0
 for f in fs:
  start=a(f['addr']);raw=bs(f['originalBytes']);size=f['size']
  assert len(raw)==size and digest(raw)==f['sha256'] and raw==original(start,size)
  lines=f['disassembly']['asm']['lines'];pages=f['pages'];assert pages[-1]['cursor']['done']
  gathered=[l for p in pages for l in p['asm']['lines']]
  assert lines==gathered and len({l['addr'] for l in lines})==len(lines)
  assert f['disassembly']['total_instructions']==len(lines)
  for p in pages:assert p['instruction_count']==len(p['asm']['lines']) and p['total_instructions']==len(lines)
  pp=f['pseudocode']['pages'];assert pp[-1]['cursor']['done']
  assert all(not p.get('truncated',False) for p in pp)
  assert sum(p['line_count'] for p in pp)==pp[-1]['total_lines']
  assert f['pseudocode']['code']=='\n'.join(p['code'] for p in pp)
  if f['freshCapture']:
   dis=unwrap(read(H/f['source']));dec=unwrap(read(H/('root-decompile-'+f['addr']+'.json')))
   assert pages==[dis] and pp==[dec]
   matches=[]
   for bp in H.glob('root-bytes*.json'):
    matches += [bs(x['data']) for x in unwrap(read(bp))['result'] if a(x['addr'])==start]
   assert matches and all(x==raw for x in matches)
  else:
   path,fragment=f['source'].split('#');sf=next(x for x in sourcecache[path]['functions'] if a(x['addr'])==start)
   sa=sf.get('disassembly',{}).get('asm',sf.get('asm'));sl=sa if isinstance(sa,list) else sa['lines'];assert sl==lines
   sb=sf.get('originalBytes',sf.get('bytes'))
   if sb is None:sb=b''.join(bs(c['data']) for c in sorted(sf['original_bytes'],key=lambda c:a(c['addr'])))
   else:sb=bs(sb)
   assert sb==raw and sf['size']==size
  covered=set();local=[]
  for l in lines:
   at=a(l['addr']); assert start<=at<start+size
   ins=next(cs.disasm(raw[at-start:],at,count=1),None);assert ins is not None
   assert at+ins.size<=start+size
   span=set(range(at,at+ins.size));assert not covered&span
   covered|=span;instructions[at]=(ins,l,f['addr']);local.append(ins)
  missing=sorted(set(range(start,start+size))-covered);gaps=[]
  for at in missing:
   if gaps and at==gaps[-1][1]:gaps[-1][1]+=1
   else:gaps.append([at,at+1])
  bodyresults.append({'addr':f['addr'],'kind':'code_range' if f['addr']=='0x14039dee0' else 'function','freshCapture':f['freshCapture'],'size':size,'instructionCount':len(local),'decodedInstructionBytes':len(covered),'unrenderedSpans':[{'addr':hex(x),'size':y-x,'originalBytes':original(x,y-x).hex(' ')} for x,y in gaps]})
  totalbytes+=size
 # Concrete semantic anchors, independently decoded from original bytes.
 selected={
 0x39CC89:'reference increment',0x39DA46:'reference decrement',0x39D855:'planned destination store',
 0x39E768:'pending cache state',0x39E773:'cache submit',0x39E8A0:'equal bases before async completion',
 0x39E794:'unfixup before synchronous copy',0x39E832:'forward copy store',0x39E871:'backward copy store',0x39E87F:'postmove fixup',
 0x3A0754:'first queue publication',0x3A0775:'nonempty queue publication',0x3A0BF7:'submit can be suppressed',
 0x3A0C22:'destination after enqueue',0x3A0C26:'callback after enqueue',0x3A0C2A:'context after enqueue',
 0x3A0CE2:'worker state1',0x3A0CFA:'default reader call',0x3A0D08:'worker result',0x3A0D52:'header80',0x3A0D62:'header profile store',0x3A0D76:'prepare before ready',0x3A0D7B:'worker state2',0x3A0D82:'next queue iteration',
 0x3A07EB:'consumer requires state2',0x3A0821:'consumer fixup',0x3A0828:'zero result clears destination',0x3A0841:'callback before unlink',0x3A0853:'head unlink',0x3A08C4:'request free',
 0x39DEE0:'callback zero test',0x39DEE8:'nonzero finalize',0x39DEED:'zero cache failure',0x39EBB2:'ordinary state3',
 0x3A09D0:'worker callback registration',0x3A09E3:'worker creation path',0x3A09EF:'completion registration',0x3A09FE:'scheduler registration',0x16CA0E:'actual CreateThread',0x15ED56:'worker slot callback',
 0x3A6883:'header profile mask',0x3A6889:'special profile exactly40',0x3A688C:'other profiles ordinary',0x3A6901:'packed entry publication',0x3A6955:'type9 constructor',
 0x1C5F20:'payload starts at144',0x1C3847:'payload pointer field',0x1D2629:'Prototype0 vtable',0x1DAFC5:'RAW vtable',
 0x39E02F:'existing node state reset',0x39E128:'new node initialization',0x39E138:'new reservation extent',0x39EA6C:'child previous base',0x39EA70:'child current base',0x39EADD:'parent unlink',
 }
 anchors=[]
 for r,label in selected.items():
  va=imagebase+r;ins,line,body=instructions[va]
  anchors.append({'addr':hex(va),('code_range' if body=='0x14039dee0' else 'function'):body,'meaning':label,'bytes':bytes(ins.bytes).hex(' '),'ida':line['instruction'],'independentDecode':ins.mnemonic+' '+ins.op_str})
 # The two complete planner/mover bodies have no WORD memory access at displacement2.
 no_ref=[]
 for r in [0x39D590,0x39E690]:
  target=hex(imagebase+r);isns=[i for i,l,b in instructions.values() if b==target]
  hits=[hex(i.address) for i in isns for o in i.operands if o.type==X86_OP_MEM and o.size==2 and o.mem.disp==2]
  assert not hits;no_ref.append(target)
 # Mechanically assert the local completion-store order and immediate tail.
 def it(r):return instructions[imagebase+r][0]
 assert it(0x3A0D7B).mnemonic=='mov' and it(0x3A0D7B).op_str=='dword ptr [rbx + 4], 2'
 assert it(0x3A0D82).mnemonic=='jmp' and it(0x3A0D82).operands[0].imm==imagebase+0x3A0C70
 assert it(0x3A6889).mnemonic=='cmp' and it(0x3A6889).operands[1].imm==0x40
 assert it(0x1C5F20).operands[1].mem.disp==144
 assert it(0x1C3847).operands[0].mem.disp==8
 # Original branch/table bytes are retained as extent bytes, not counted as code.
 result('anchors.json',{'anchors':anchors,'noWordRefcountAccessBodies':no_ref,'scope':'Selected instruction anchors + full extent byte comparison; not native execution.'},write)
 result('model-results.json',models.run(),write)
 refs=0
 for claim in read(H/'report.json')['claims']:
  assert {'addr','Finding','Evidence','Limitations'}<=claim.keys()
  assert claim['addr'] in {f['addr'] for f in fs}
  for ref in claim['Evidence']:
   file,sep,frag=ref.partition('#');assert (H/file).is_file(),ref
   if sep:
    m=re.fullmatch(r'(functions|code_ranges)\[addr=(0x[0-9a-f]+)\]',frag);assert m,ref
    assert m.group(2) in {f['addr'] for f in read(H/file)[m.group(1)]}
   refs+=1
 out={'status':'PASS','originalSha256':EXPECTED,'functions':len(ev['functions']),'codeRanges':len(ev['code_ranges']),'bodyCount':len(fs),'coverageRangeValidation':range_check,'freshCaptures':sum(f['freshCapture'] for f in fs),'explicitlyReusedBodies':sum(not f['freshCapture'] for f in fs),'extentBytes':totalbytes,'instructions':len(instructions),'instructionBytes':sum(x['decodedInstructionBytes'] for x in bodyresults),'anchors':len(anchors),'claims':len(read(H/'report.json')['claims']),'resolvedEvidenceReferences':refs,'models':{k:v for k,v in models.run().items() if k in ['traceCount','stateObservations','profileCases']},'bodies':bodyresults,'limits':['No IDA mutations or readiness completion.','Capstone checks boundaries/bytes; manual ASM interpretation supplies the semantic claims.','Models are small policy counterexamples, not native execution or a live gate test.','Existing evidence reuse is not new-function coverage.']}
 result('verification.json',out,write)
 if (H/'manifest.json').exists() and not write:
  m=read(H/'manifest.json');members=m['files'];actual={p.relative_to(H).as_posix() for p in H.rglob('*') if p.is_file() and p!=H/'manifest.json'}
  assert actual=={x['path'] for x in members},'manifest file set'
  for x in members:
   p=H/x['path'];assert p.stat().st_size==x['bytes'] and digest(p.read_bytes())==x['sha256'],x['path']
 print(json.dumps({k:v for k,v in out.items() if k!='bodies'},indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--write',action='store_true');ap.add_argument('--check',action='store_true');main(ap.parse_args().write)
