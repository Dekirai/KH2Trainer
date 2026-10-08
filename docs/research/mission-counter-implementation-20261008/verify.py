"""Read-only original-PE/source/receipt verifier; never maps or executes game code.
Python 3 + capstone. --check also checks the immutable study manifest.
--repo optionally checks the current source checkout against the pinned copies.
"""
import argparse, hashlib, json, re, struct
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

HERE=Path(__file__).resolve().parent
BASE=0x140000000
SHA='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
DEFAULT_EXE=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def encoded(v): return (json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
def blob(s): return bytes(int(t,16) for t in s.split())

class PE:
 def __init__(self,path):
  self.raw=path.read_bytes();assert hashlib.sha256(self.raw).hexdigest()==SHA
  off=struct.unpack_from('<I',self.raw,0x3c)[0];assert self.raw[:2]==b'MZ' and self.raw[off:off+4]==b'PE\0\0'
  n=struct.unpack_from('<H',self.raw,off+6)[0];sz=struct.unpack_from('<H',self.raw,off+20)[0];opt=off+24
  assert struct.unpack_from('<H',self.raw,opt)[0]==0x20b and struct.unpack_from('<Q',self.raw,opt+24)[0]==BASE
  self.sections=[struct.unpack_from('<IIII',self.raw,opt+sz+i*40+8) for i in range(n)]
 def read(self,a,n):
  r=a-BASE
  for virtual_size,va,size,ptr in self.sections:
   if va<=r and r+n<=va+size:return self.raw[ptr+r-va:ptr+r-va+n]
  raise AssertionError(('not file-backed',hex(a),n))

def derive(exe,repo=None):
 pe=PE(exe);ev=load(HERE/'imported-evidence.json');cs=Cs(CS_ARCH_X86,CS_MODE_64)
 assert ev['Domain']=='native' and ev['originalSha256']==SHA
 ins={};bodies=[]
 for f in ev['functions']:
  a=int(f['addr'],16);raw=blob(f['originalBytes']);assert len(raw)==f['size'] and pe.read(a,len(raw))==raw
  ida=f['idaBytes'];assert blob(ida if isinstance(ida,str) else ida['result'][0]['data'])==raw
  lines=f['disassembly']['asm']['lines'];pages=f['pages'];dec=f['decompile']
  assert f['disassembly']['cursor']['done'] and len(lines)==f['disassembly']['total_instructions']==f['disassembly']['instruction_count']
  assert pages[-1]['cursor']['done'] and [line for page in pages for line in page['asm']['lines']]==lines
  for i,page in enumerate(pages):
   assert page['instruction_count']==len(page['asm']['lines'])
   if i+1<len(pages):assert page['cursor']['next']==sum(p['instruction_count'] for p in pages[:i+1])
  assert dec['cursor']['done'] and not dec['truncated']
  decoded=list(cs.disasm(raw,a));assert sum(i.size for i in decoded)==len(raw)
  assert [i.address for i in decoded]==[int(line['addr'],16) for line in lines]
  ins.update({i.address:(i.mnemonic,i.op_str) for i in decoded})
  bodies.append({'addr':f['addr'],'bytes':len(raw),'instructions':len(decoded)})
 assert len(bodies)==16
 anchors={
  0x3fa7b6:('mov','dword ptr [rbx + 0x38], edx'),0x3fa7c1:('mov','dword ptr [rbx + 0x50], edx'),
  0x3fa7ea:('movss','dword ptr [rbx + 0x54], xmm6'),0x3fa82b:('jbe','0x1403fa856'),
  0x3fa82d:('subss','xmm0, dword ptr [rip + 0x31cc4b]'),0x3fa838:('movss','dword ptr [rcx + 0x54], xmm0'),
  0x3fa84c:('mov','dword ptr [rcx + 0x38], eax'),0x3fa86d:('mov','dword ptr [rcx + 0x38], eax'),
  0x3fa8be:('mov','dword ptr [rcx + 0x50], edx'),0x3fb62b:('mov','eax, dword ptr [rax + rbx + 0x38]'),
  0x3fb77b:('mov','eax, dword ptr [rax + rbx + 0x50]'),0x3fa269:('call','0x1403aabe0'),
  0x3fa293:('call','0x1403aabe0'),0x3fa2f3:('mov','dword ptr [rbx + 0x38], edi'),
  0x3fbb90:('lea','r8d, [r8 + r8*4]'),0x3fbba1:('idiv','r8d')}
 for rva,expected in anchors.items():assert ins[BASE+rva]==expected,(hex(rva),ins[BASE+rva],expected)
 assert struct.unpack('<7Q',pe.read(BASE+0x5C9DF8,56))==tuple(BASE+x for x in [0x3FA6D0,0x3FA0D0,0x3FA730,0x3F9F80,0x3FA4C0,0x3FA880,0x3FA440])
 pins=load(HERE/'source-snapshots.json');signatures=[]
 for original,pin in pins.items():
  p=HERE/pin['snapshot'];assert digest(p)==pin['sha256'] and p.stat().st_size==pin['bytes']
  if repo:assert digest(repo/original)==pin['sha256'],original
  if original.endswith(('MissionFeatures.inl','MissionEventFeatures.inl')):
   text=p.read_text(encoding='utf-8-sig')
   arrays={name:bytes(int(t.strip(),16) for t in raw.split(',')) for name,raw in re.findall(r'constexpr BYTE (code\d+)\[\]=\{([^}]+)\}',text)}
   rows=re.findall(r'\{(0x[0-9a-fA-F]+),(code\d+),sizeof\(\2\)\}',text)
   assert len(rows)==(23 if original.endswith('MissionEventFeatures.inl') else 8)
   for rva,name in rows:
    raw=arrays[name];assert pe.read(BASE+int(rva,16),len(raw))==raw
    signatures.append({'source':original,'rva':rva,'bytes':len(raw)})
 tests=load(HERE/'test-results.json')
 for suite,row in tests['suites'].items():
  text=(HERE/row['log']).read_text(encoding='utf-8-sig')
  assert re.search(rf"{row['checks']} checks, 0 failures",text),suite
 assert sum(row['checks'] for row in tests['suites'].values())==15451
 claims=load(HERE/'claims.json')['claims'];addresses={f['addr'] for f in ev['functions']}
 for claim in claims:
  assert claim['addr'] in addresses and claim['Domain']=='native'
  for ref in claim['Evidence']:
   m=re.fullmatch(r'imported-evidence.json#functions\[addr=(0x[0-9a-f]+)\]',ref)
   assert m and m[1] in addresses
 return {'success':True,'originalSha256':SHA,'bodies':bodies,'fullBodies':len(bodies),
  'instructions':sum(b['instructions'] for b in bodies),'bodyBytes':sum(b['bytes'] for b in bodies),
  'semanticAnchors':len(anchors),'runtimeSignatureRecords':len(signatures),'runtimeSignatureBytes':sum(s['bytes'] for s in signatures),
  'sourceSnapshots':len(pins),'nativeTestChecks':15451,'failures':0,
  'scope':'Source/hash and complete original-byte revalidation plus recorded isolated synthetic tests. No game execution, live installer, blanket lifetime proof or wall-clock conversion.'}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--exe',type=Path,default=DEFAULT_EXE);ap.add_argument('--repo',type=Path);ap.add_argument('--check',action='store_true');args=ap.parse_args()
 receipt=derive(args.exe,args.repo)
 if args.check:
  assert (HERE/'verification.json').read_bytes()==encoded(receipt)
  manifest=load(HERE/'manifest.json');actual={p.relative_to(HERE).as_posix() for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json'}
  assert actual==set(manifest['files'])
  for rel,pin in manifest['files'].items():assert digest(HERE/rel)==pin['sha256'] and (HERE/rel).stat().st_size==pin['bytes'],rel
 else:(HERE/'verification.json').write_bytes(encoded(receipt))
 print(json.dumps({k:v for k,v in receipt.items() if k!='bodies'},indent=2))
if __name__=='__main__':main()
