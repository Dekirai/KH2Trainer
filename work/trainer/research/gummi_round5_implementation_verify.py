"""Offline evidence/pin verification. No product, IDB or game-memory writes."""
import hashlib,json,pathlib,re,struct
root=pathlib.Path(__file__).resolve().parents[3]
research=root/'work/trainer/research'
original=pathlib.Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
image=original.read_bytes()
sha=hashlib.sha256(image).hexdigest().upper()
assert sha=='9002B2DE6A1F91A790BD0673DE125D1CF833F7942BFEC827CDCF6BA64D5849ED'
pe=struct.unpack_from('<I',image,0x3c)[0]
count=struct.unpack_from('<H',image,pe+6)[0]
optional=struct.unpack_from('<H',image,pe+20)[0]
sections=[]
for i in range(count):
 off=pe+24+optional+40*i
 vs,rva,rawsize,raw=struct.unpack_from('<4I',image,off+8)
 sections.append((rva,rawsize,raw))
def at(rva,size):
 for start,n,raw in sections:
  if start<=rva and rva+size<=start+n:return image[raw+rva-start:raw+rva-start+size]
 raise AssertionError(f'unmapped RVA {rva:x}')
source=(root/'trainer/Native/GummiEditorFeatures.inl').read_text()
arrays={n:bytes(int(x.strip(),16) for x in body.split(',') if x.strip()) for n,body in re.findall(r'constexpr BYTE ((?:code|data)_[A-F0-9]+)\[\]=\{([^}]+)\};',source)}
pins=re.findall(r'\{0x([A-F0-9]+),((?:code|data)_[A-F0-9]+),sizeof\(\2\)\}',source)
for rva,name in pins:assert arrays[name]==at(int(rva,16),len(arrays[name])),name
total_lines=0;functions=0;original_bytes=0
for filename in ['gummi_round5_implementation_evidence.json','gummi_round5_implementation_supplement.json']:
 doc=json.loads((research/filename).read_text())
 for addr,f in doc['functions'].items():
  joined=[l for p in f['pages'] for l in p['asm']['lines']]
  assert joined==f['asm']['lines'],addr
  assert len(joined)==f['instruction_count']==f['total_instructions'],addr
  assert f['cursor'].get('done') and not f['cursor'].get('next') and not f['cursor'].get('cancelled'),addr
  for p in f['pages']:
   assert p['instruction_count']==len(p['asm']['lines']) and p['total_instructions']==len(joined),addr
  assert f['pages'][-1]['cursor'].get('done') and not f['pages'][-1]['cursor'].get('next'),addr
  b=b''.join(bytes(int(t,16) for t in c['data'].split()) for c in f['original_bytes']['chunks'])
  assert len(b)==f['original_bytes']['size'] and b==at(int(addr,16)-0x140000000,len(b)),addr
  total_lines+=len(joined);original_bytes+=len(b);functions+=1
paths=['trainer/Native/GummiEditorFeatures.inl','work/trainer/tests/GummiEditorGuardTests.cpp','work/trainer/tests/build_gummi_editor_tests.cmd','work/trainer/research/gummi_editor_features.json']
result=dict(original_path=str(original),original_sha256=sha,pin_count=len(pins),pin_bytes=sum(len(arrays[n]) for _,n in pins),functions=functions,assembly_lines=total_lines,evidence_original_bytes=original_bytes,failures=0,fingerprints={p:hashlib.sha256((root/p).read_bytes()).hexdigest().upper() for p in paths})
(research/'gummi_round5_implementation_validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
