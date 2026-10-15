"""Original-PE/ASM reproduction for a bounded native-copy contract. No IDA/game access.
--write regenerates derived evidence; --native executes ONLY the 89-byte call-free
BAR lookup in this Python process on deliberately bounded synthetic tables.
"""
import argparse, ctypes, hashlib, json, pathlib, struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

HERE = pathlib.Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'src/KH2Trainer.Core').is_dir())
ORIGINAL = pathlib.Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
EXPECTED = '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
BASE = 0x140000000
SOURCES = {
 'motion-resource-binding-20261011': [0x1c3840, 0x1c5f20, 0x1d2610, 0x1dafb0, 0x3a6840,
   0x3c8a40, 0x3c8cd0, 0x3c88c0, 0x40d7a0, 0x40d7d0, 0x40d7f0],
 'voice-origin-resources-20261011': [0x3a6420],
 'voice-resource-teardown-20261011': [0x3a6120, 0x3a62b0],
 'actor-lifetime-20261007': [0x4ad240, 0x4ad270, 0x4ad2c0, 0x4ad390, 0x4ad3f0],
 'drive-skeleton-guard-20261007': [0x3c7c50],
}
def sha(b): return hashlib.sha256(b).hexdigest()
def enc(v): return (json.dumps(v, ensure_ascii=False, indent=2) + '\n').encode()
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def raw(s):
 if isinstance(s,list):
  assert len(s)==1
  s=s[0]['data']
 return bytes(int(x, 16) for x in s.split())

class PE:
 def __init__(self):
  self.data = ORIGINAL.read_bytes()
  assert sha(self.data) == EXPECTED
  p = struct.unpack_from('<I', self.data, 0x3c)[0]
  assert self.data[p:p+4] == b'PE\0\0'
  n = struct.unpack_from('<H', self.data, p+6)[0]
  z = struct.unpack_from('<H', self.data, p+20)[0]
  assert struct.unpack_from('<H', self.data, p+4)[0] == 0x8664
  assert struct.unpack_from('<Q', self.data, p+48)[0] == BASE
  self.sections = [struct.unpack_from('<8sIIII', self.data, p+24+z+40*i) for i in range(n)]
 def bytes(self, va, n):
  rva = va - BASE
  for name, vs, rv, rs, fo in self.sections:
   if rv <= rva and n <= rs - (rva-rv):
    return self.data[fo+rva-rv:fo+rva-rv+n]
  raise AssertionError(f'not file backed: {va:x}+{n:x}')

def listing(f):
 d = f.get('disassembly', f.get('disasm', f.get('asm')))
 if 'asm' in d: d = d['asm']
 return d['lines']

def collect(pe):
 md = Cs(CS_ARCH_X86, CS_MODE_64)
 functions, dependencies = [], []
 totals = {'reusedFunctions': 0, 'newSemanticFunctions': 0, 'freshCrosschecks': 0,
           'instructions': 0, 'extentBytes': 0, 'separateDataOrPaddingBytes': 0}
 for study, wanted in SOURCES.items():
  p = ROOT / 'docs/research' / study / 'evidence.json'
  dependencies.append({'path': p.relative_to(ROOT).as_posix(), 'sha256': sha(p.read_bytes())})
  source = read(p)
  for rva in wanted:
   addr = BASE + rva
   f = next(x for x in source['functions'] if int(x['addr'],16) == addr)
   b = raw(f.get('originalBytes', f.get('original_bytes')))
   assert len(b) == f['size'] and pe.bytes(addr, len(b)) == b
   lines = listing(f)
   assert int(lines[0]['addr'],16) == addr
   covered, decoded = set(), []
   previous = addr-1
   for line in lines:
    ea = int(line['addr'],16)
    assert previous < ea < addr+len(b)
    previous = ea
    i = next(md.disasm(b[ea-addr:], ea, count=1))
    assert i.address == ea and i.size > 0
    span = set(range(ea-addr, ea-addr+i.size))
    assert not span.intersection(covered) and max(span) < len(b)
    covered.update(span)
    decoded.append({'addr':hex(ea),'bytes':i.bytes.hex(' '),'mnemonic':i.mnemonic,'operands':i.op_str})
   pages = f.get('pages', [])
   assert pages and all(x.get('cursor',{}).get('done') or x.get('cursor',{}).get('next') is not None for x in pages)
   assert pages[-1]['cursor'].get('done')
   gaps=[]; pos=0
   while pos < len(b):
    if pos in covered: pos+=1; continue
    start=pos
    while pos < len(b) and pos not in covered: pos+=1
    gaps.append({'addr':hex(addr+start),'size':pos-start,'bytes':b[start:pos].hex(' '),
                 'kind':'separate unlisted bytes in IDA extent; not instruction credit'})
   functions.append({'addr':hex(addr),'size':len(b),'originalBytes':b.hex(' '),'sha256':sha(b),
      'source':{'path':p.relative_to(ROOT).as_posix(),'role':'reused full function; no novelty credit'},
      'pages':pages,'disassembly':{'asm':{'start_ea':hex(addr),'lines':lines},'cursor':{'done':True}},
      'pseudocode':f.get('pseudocode',f.get('decompile')),'independentDecode':decoded,'noninstructionSpans':gaps})
   totals['reusedFunctions']+=1; totals['instructions']+=len(decoded)
   totals['extentBytes']+=len(b); totals['separateDataOrPaddingBytes']+=len(b)-len(covered)
 freshbytes={int(x['addr'],16):raw(x['data']) for x in read(HERE/'root-ida-bytes.json')['result']}
 crosschecks=[]
 for x in read(HERE/'root-ida-lookup.json')['result']:
  assert x['error'] is None
  addr=int(x['fn']['addr'],16); size=int(x['fn']['size'],16)
  f=next(f for f in functions if int(f['addr'],16)==addr)
  d=read(HERE/f'root-ida-disasm-{hex(addr)}.json')
  p=read(HERE/f'root-ida-decompile-{hex(addr)}.json')
  assert d['cursor'].get('done') and p['cursor'].get('done') and not p.get('truncated')
  assert d['instruction_count']==d['total_instructions']==len(d['asm']['lines'])
  assert [(int(l['addr'],16),l['instruction']) for l in d['asm']['lines']] == [(int(l['addr'],16),l['instruction']) for l in listing(f)]
  assert size==f['size'] and freshbytes[addr]==raw(f['originalBytes'])==pe.bytes(addr,size)
  totals['freshCrosschecks']+=1
  crosschecks.append({'addr':hex(addr),'size':size,'sha256':sha(freshbytes[addr]),'role':'fresh recapture agrees with prior full original evidence'})
 constants=[{'addr':hex(BASE+0x5c5d38),'role':'four four-byte variant priority rows used by3C7C50',
             'bytes':pe.bytes(BASE+0x5c5d38,16).hex(' ')}]
 return {'schemaVersion':1,'originalExeSha256':EXPECTED,'functions':functions,'constants':constants,
         'freshCrosschecks':crosschecks}, dependencies, totals

def check_anchors(evidence):
 bodies={int(f['addr'],16)-BASE:f for f in evidence['functions']}
 def at(rva,ea,mnem,operand):
  i=next(x for x in bodies[rva]['independentDecode'] if int(x['addr'],16)==BASE+ea)
  assert i['mnemonic']==mnem and operand in i['operands'],(hex(ea),i)
 # Explicit decoded operation checks, separate from original-byte equality.
 at(0x3a6420,0x3a6425,'movsxd','[rcx + 4]')
 at(0x3a6420,0x3a6438,'cmp','edx, -1')
 at(0x3a6420,0x3a6448,'dec','r8d')
 at(0x3a6420,0x3a6455,'add','r9, 0x10')
 at(0x40d7a0,0x40d7ac,'call','0x1403a6420')
 at(0x3c8cd0,0x3c8d67,'mov','[rdi + 0x2c]')
 at(0x3c8a40,0x3c8aff,'mov','[rbx + 0x18]')
 at(0x1c5f20,0x1c5f20,'lea','[rcx + 0x90]')
 at(0x1c3840,0x1c3847,'mov','[rcx + 8]')
 at(0x4ad3f0,0x4ad3fd,'btr','ebx, 0x1f')
 at(0x4ad3f0,0x4ad40c,'shr','rax, 0x19')
 at(0x4ad3f0,0x4ad410,'and','ecx, 0x1ffffff')
 at(0x4ad3f0,0x4ad41a,'or','rax, rcx')
 at(0x3a6840,0x3a6903,'test','1')
 return 14

def native_find(pe):
 assert ctypes.sizeof(ctypes.c_void_p)==8
 body=pe.bytes(BASE+0x3a6420,89)
 md=Cs(CS_ARCH_X86,CS_MODE_64)
 for i in md.disasm(body,BASE+0x3a6420):
  assert i.mnemonic!='call'
  if i.mnemonic.startswith('j'):
   assert BASE+0x3a6420 <= int(i.op_str,16) < BASE+0x3a6420+len(body)
 k=ctypes.WinDLL('kernel32',use_last_error=True)
 k.VirtualAlloc.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_ulong,ctypes.c_ulong];k.VirtualAlloc.restype=ctypes.c_void_p
 k.VirtualProtect.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_ulong,ctypes.POINTER(ctypes.c_ulong)];k.VirtualProtect.restype=ctypes.c_int
 k.VirtualFree.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_ulong];k.VirtualFree.restype=ctypes.c_int
 k.GetCurrentProcess.restype=ctypes.c_void_p
 k.FlushInstructionCache.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t];k.FlushInstructionCache.restype=ctypes.c_int
 code=k.VirtualAlloc(None,len(body),0x3000,4); assert code
 results=[]
 try:
  ctypes.memmove(code,body,len(body)); old=ctypes.c_ulong()
  assert k.VirtualProtect(code,len(body),0x20,ctypes.byref(old))
  assert k.FlushInstructionCache(k.GetCurrentProcess(),code,len(body))
  fn=ctypes.WINFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int32,ctypes.c_int32)(code)
  entries=[(16,0,9,0,0),(9,1,0x41414141,0,0),(9,0,0x42424242,0x80000000,148)]
  # All native memory reads stay inside this owned 64-byte fixture.
  cases=[('negative count',-1,-1,0,None),('zero count',0,-1,0,None),
   ('wildcard ordinal includes other type',3,-1,0,0),('wildcard ordinal2',3,-1,2,2),
   ('first type9 ignores bad link/pointer/length',3,9,0,1),('second type9 occurrence',3,9,1,2),
   ('unmatched types do not consume occurrence',3,16,0,0),('missing type',3,17,0,None),
   ('ordinal at count',3,-1,3,None),('negative occurrence',3,9,-1,None)]
  for name,count,kind,occ,expected in cases:
   blob=bytearray(64);struct.pack_into('<IiII',blob,0,0x01524142,count,0,0)
   for n,e in enumerate(entries):struct.pack_into('<HHIII',blob,16+n*16,*e)
   table=ctypes.create_string_buffer(bytes(blob));base=ctypes.addressof(table)
   got=fn(base,kind,occ);got=None if got is None else (got-base-16)//16
   assert got==expected,(name,got,expected)
   results.append({'name':name,'count':count,'type':kind,'occurrence':occ,'entryIndex':got,'expected':expected,'pass':True})
 finally:
  assert k.VirtualFree(code,0,0x8000)
 return {'scope':'Original call-free89-byte Find body, private process/private buffers only; no game or engine globals',
         'originalBodySha256':sha(body),'scriptSha256':sha(pathlib.Path(__file__).read_bytes()),'cases':results,'pass':True}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--write',action='store_true');ap.add_argument('--native',action='store_true');a=ap.parse_args()
 pe=PE();evidence,deps,totals=collect(pe);anchors=check_anchors(evidence)
 provenance=read(HERE/'root-session-provenance.json')
 session_results={x['tool']:x['value']['structuredContent'] for x in provenance['results'] if x['status']=='fulfilled'}
 health=session_results['server_health']
 assert health['status']=='ok' and health['hexrays_ready'] is True and health['auto_analysis_ready'] is False
 assert any(x['session_id']=='28e14b48' and x['pid']==71984 and x['is_analyzing'] is False for x in session_results['idb_list']['sessions'])
 if a.native:
  assert a.write,'--native requires --write; default verification executes no native bytes'
  (HERE/'native-find-results.json').write_bytes(enc(native_find(pe)))
 n=read(HERE/'native-find-results.json')
 assert n['pass'] and len(n['cases'])==10 and all(x['pass'] and x['expected']==x['entryIndex'] for x in n['cases'])
 assert n['originalBodySha256']==sha(pe.bytes(BASE+0x3a6420,89))
 assert n['scriptSha256']==sha(pathlib.Path(__file__).read_bytes())
 verification={'result':'PASS','originalExeSha256':EXPECTED,**totals,'meaningfulInstructionAnchors':anchors,
 'originalFindCases':10,'nativeCasesExecutedThisRun':a.native,'limitations':['No production reader implementation or game execution','No source-admission/lifetime proof','All functions are reused; fresh captures are crosschecks','IDA auto_analysis_ready was false; no analysis requested']}
 # Execution is recorded by the native receipt. Keep the ordinary derived result reproducible.
 verification['nativeCasesExecutedThisRun']=False
 for name,obj in [('evidence.json',evidence),('dependencies.json',{'files':deps}),('verification.json',verification)]:
  b=enc(obj)
  if a.write:(HERE/name).write_bytes(b)
  else:assert (HERE/name).read_bytes()==b,name
 if not a.write:
  manifest=read(HERE/'manifest.json');actual={p.name for p in HERE.iterdir() if p.is_file() and p.name!='manifest.json'}
  assert actual=={x['path'] for x in manifest['files']}
  for x in manifest['files']:assert sha((HERE/x['path']).read_bytes())==x['sha256'],x['path']
 print(json.dumps(verification,ensure_ascii=False))

if __name__=='__main__':main()
