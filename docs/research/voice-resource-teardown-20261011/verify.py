"""Reproduce bounded static evidence from original PE bytes. --check is read-only."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'src/KH2Trainer.Core').is_dir())
TARGET=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
BASE=0x140000000
ORIGINAL='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(p.read_bytes())
def dump(p,j):p.write_text(json.dumps(j,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def need(ok,msg):
 if not ok:raise AssertionError(msg)
def build():
 raw=TARGET.read_bytes();need(sha(raw)==ORIGINAL,'original EXE SHA256')
 pe=struct.unpack_from('<I',raw,60)[0];opt=pe+24
 need(raw[:2]==b'MZ' and raw[pe:pe+4]==b'PE\0\0','PE')
 need(struct.unpack_from('<H',raw,opt)[0]==0x20b and struct.unpack_from('<Q',raw,opt+24)[0]==BASE,'PE64 base')
 size=struct.unpack_from('<H',raw,pe+20)[0];n=struct.unpack_from('<H',raw,pe+6)[0]
 sections=[struct.unpack_from('<III',raw,opt+size+40*k+12) for k in range(n)]
 def read(a,n):
  r=a-BASE
  for va,sz,off in sections:
   if va<=r and r+n<=va+sz:return raw[off+r-va:off+r-va+n]
  raise AssertionError(('not file backed',hex(a),n))
 cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
 out=dict(schema=1,Domain='native',originalSha256=ORIGINAL,imageBase=hex(BASE),functions=[],dependencies=[],data=[],anchors=[],switches=[],positiveRefs=[])
 insns={};fresh_count=0;instruction_bytes=0
 def body(f,fresh,source):
  nonlocal fresh_count,instruction_bytes
  a=int(f['addr'],16);b=bytes(int(x,16) for x in f['idaBytes'].split()) if fresh else bytes.fromhex(f['originalBytes'])
  need(len(b)==f['size'] and b==read(a,len(b)),'full original body '+hex(a))
  if fresh:
   fresh_count+=1;pages=f['pages'];rows=[]
   for p in pages:
    need(p['offset']==len(rows) and p['instruction_count']==len(p['asm']['lines']),'ASM page offset/count')
    rows+=p['asm']['lines']
   need(pages[-1]['cursor']=={'done':True} and rows==f['disassembly']['asm']['lines'],'ASM final cursor/join')
   need(all(p['total_instructions']==len(rows) for p in pages),'ASM total')
   pp=f['pseudocode']['pages'];code='\n'.join(p['code'] for p in pp);offset=0
   need(code==f['pseudocode']['code'] and pp[-1]['cursor']=={'done':True},'pseudocode cursor/join')
   for p in pp:
    need(not p.get('truncated') and p['offset']==offset and p['line_count']==len(p['code'].splitlines()),'pseudocode offset/count')
    need(p['total_lines']==len(code.splitlines()),'pseudocode total');offset+=p['line_count']
  else:rows=f['asm'];need(sha(b)==f['sha256'],'dependency SHA')
  covered=set();decoded=[]
  for row in rows:
   pc=int(row['addr'],16);need(a<=pc<a+len(b),'bounded instruction')
   i=next(cs.disasm(b[pc-a:],pc,count=1),None);need(i is not None,'decode')
   span=set(range(pc,pc+i.size));need(not span&covered and pc+i.size<=a+len(b),'nonoverlap')
   need(pc not in insns,'unique instruction');insns[pc]=i;covered|=span
   if fresh:instruction_bytes+=i.size
   ida=row['instruction'].split(';')[0].split()[0].lower()
   aliases={'retn':'ret','jz':'je','jnz':'jne','jnb':'jae','jna':'jbe','jnbe':'ja','jnl':'jge','jng':'jle','jnle':'jg','setnz':'setne','setz':'sete','cmovz':'cmove','cmovnz':'cmovne','repe':'repz','repne':'repnz','sal':'shl'}
   need(aliases.get(ida,ida)==aliases.get(i.mnemonic.split()[0],i.mnemonic.split()[0]) or (ida=='xchg' and i.mnemonic=='nop' and i.bytes.hex() in ['90','6690']),'IDA/Capstone opcode '+hex(pc)+' '+ida+' '+i.mnemonic)
   decoded.append(dict(addr=hex(pc),size=i.size,bytes=i.bytes.hex(),mnemonic=i.mnemonic,operands=i.op_str,idaText=row['instruction']))
   targets={o.imm for o in i.operands if o.type==X86_OP_IMM}|{pc+i.size+o.mem.disp for o in i.operands if o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP}
   for r in row.get('refs',[]):
    if int(r['addr'],16) in targets:out['positiveRefs'].append(dict(site=hex(pc),target=r['addr'],fresh=fresh))
  missing=set(range(a,a+len(b)))-covered;tail=[]
  if missing:
   lo=min(missing);need(missing==set(range(lo,a+len(b))),'contiguous trailing data')
   tailbytes=b[lo-a:]
   if a==BASE+0x3a6120:need(lo==BASE+0x3a625a and len(tailbytes)==80 and tailbytes[:2]==b'\x66\x90','alignment + switch tables');kind='2-byte alignment NOP, eight DWORD target RVAs, 46-byte case map'
   elif a==BASE+0x3a62b0:need(lo==BASE+0x3a6360 and len(tailbytes)==66,'switch tables');kind='five DWORD target RVAs, 46-byte case map'
   elif a==BASE+0x3a6a10:kind='prior BAR-release trailing switch tables/alignment, bytes rechecked; interpretation pinned to prior study'
   else:need(tailbytes==b'\xcc'*len(tailbytes),'explicit trailingCC');kind='trailing INT3 padding'
   tail=[dict(addr=hex(lo),size=len(tailbytes),hex=tailbytes.hex(),classification=kind)]
  record=dict(addr=hex(a),size=len(b),sha256=sha(b),originalBytes=b.hex(' '),instructions=decoded,trailingData=tail,source=source,freshCapture=fresh)
  record.update(disassembly=f['disassembly'],pages=f['pages'],pseudocode=f['pseudocode'])
  if fresh:
   capture=load(HERE/source)
   record['sourceMetadata']=dict(captureFile=source,captureSha256=sha((HERE/source).read_bytes()),document={k:v for k,v in capture.items() if k!='functions'})
  else:record['sourceMetadata']=f['sourceMetadata']
  out['functions' if fresh else 'dependencies'].append(record)
 for name in ['capture.json','capture-2.json']:
  j=load(HERE/name);need(j['originalSha256']==ORIGINAL and j['databaseHealth']['auto_analysis_ready'] is False,'capture identity/readiness')
  for f in j['functions']:body(f,True,name)
 for f in load(HERE/'dependencies.json')['functions']:body(f,False,f['source'])
 need(fresh_count==19 and len(out['dependencies'])==16,'body counts')
 # Verify all case values in both original switch maps, not only decompiler comments.
 for start,jpt,mapping,targets in [(0x3a6120,0x3a625c,0x3a627c,[0x3a61d3,0x3a61dd,0x3a61ea,0x3a620c,0x3a61ff,0x3a6219,0x3a6226,0x3a622e]),(0x3a62b0,0x3a6360,0x3a6374,[0x3a631a,0x3a6324,0x3a632e,0x3a6338,0x3a6340])]:
  actual=list(struct.unpack('<'+'I'*len(targets),read(BASE+jpt,4*len(targets))));need(actual==targets,'switch target vector')
  m=read(BASE+mapping,46);cases=[]
  for t,c in enumerate(m,1):
   need(c<len(targets),'case index');dest=targets[c]
   expected=targets[-1]
   if t in [1,17,20,30,46]:expected=targets[0]
   elif t==4:expected=targets[1]
   elif t==34:expected=targets[-2]
   elif start==0x3a6120 and t in [7,8,9,18]:expected={7:0x3a61ea,8:0x3a620c,9:0x3a61ff,18:0x3a6219}[t]
   elif start==0x3a62b0 and t==9:expected=0x3a632e
   need(dest==expected,'BAR type dispatch');cases.append(dict(type=t,target=hex(BASE+dest)))
  out['switches'].append(dict(function=hex(BASE+start),caseMap=read(BASE+mapping,46).hex(),targets=actual,cases=cases))
 # Resolve actual resource/replace virtual destructors from PE vtable cells.
 for cell,target in [(0x5aa190,0x12d8e0),(0x5aa090,0x129d30)]:
  b=read(BASE+cell,8);need(struct.unpack('<Q',b)[0]==BASE+target,'virtual destructor target')
  out['data'].append(dict(addr=hex(BASE+cell),hex=b.hex(),target=hex(BASE+target)))
 anchors=load(HERE/'anchors.json');need(len(anchors)==140,'fixed semantic anchor count')
 for row in anchors:
  i=insns[int(row['addr'],16)];need((i.mnemonic,i.op_str)==(row['mnemonic'],row['operands']),'semantic anchor '+row['addr'])
  out['anchors'].append(dict(**row,bytes=i.bytes.hex()))
 for dep in load(HERE/'provenance.json')['dependencies']:need(sha((ROOT/dep['path']).read_bytes())==dep['sha256'],'pinned dependency '+dep['path'])
 return out,insns
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--write',action='store_true');ap.add_argument('--check',action='store_true');args=ap.parse_args();need(args.write!=args.check,'choose --write or --check')
 evidence,insns=build()
 import model
 models=model.run(insns,evidence)
 report=load(HERE/'report.json');need(report['claims'] and all(c['limits'] and c['evidence'] for c in report['claims']),'claim evidence/limits')
 for c in report['claims']:need(int(c['address'],16) in insns,'claim body')
 verification=dict(status='PASS',originalSha256=ORIGINAL,freshBodies=len(evidence['functions']),explicitlyReusedBodies=len(evidence['dependencies']),freshBytes=sum(x['size'] for x in evidence['functions']),freshInstructions=sum(len(x['instructions']) for x in evidence['functions']),anchors=len(evidence['anchors']),verifiedSwitchCases=92,modelCases=models['cases'],claims=len(report['claims']),freshCaptureAlreadyInPriorEvidence=5,autoAnalysisReady=False,liveExecution=False,independentReviewComplete=False,scope='Selected complete static bodies, exact original PE bytes, paginated ASM/decompiler completion, selected semantic anchors, bounded synthetic models. No global lifetime, concurrency, callback completion, asset correctness or complete-analysis guarantee.')
 for name,j in [('evidence.json',evidence),('model-results.json',models),('verification.json',verification)]:
  if args.write:dump(HERE/name,j)
  else:need(load(HERE/name)==j,'reproducible '+name)
 if args.check:
  manifest=load(HERE/'manifest.json')['files'];need(set(manifest)=={p.name for p in HERE.iterdir() if p.is_file() and p.name!='manifest.json'},'manifest exact scope')
  for name,pin in manifest.items():
   b=(HERE/name).read_bytes();need(len(b)==pin['bytes'] and sha(b)==pin['sha256'],'manifest '+name)
 print(json.dumps(verification,sort_keys=True))
if __name__=='__main__':main()
