"""Verify round7 capture counts and bytes against the original EXE; write only research results."""
import hashlib,json,pathlib,struct
root=pathlib.Path(__file__).resolve().parents[3]
research=root/'work/trainer/research'
original=pathlib.Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
image=original.read_bytes()
sha=hashlib.sha256(image).hexdigest().upper()
assert sha=='9002B2DE6A1F91A790BD0673DE125D1CF833F7942BFEC827CDCF6BA64D5849ED'
pe=struct.unpack_from('<I',image,0x3c)[0]
sections=[]
for i in range(struct.unpack_from('<H',image,pe+6)[0]):
 off=pe+24+struct.unpack_from('<H',image,pe+20)[0]+40*i
 vs,rva,n,raw=struct.unpack_from('<4I',image,off+8)
 sections.append((rva,n,raw))
def at(va,n):
 rva=va-0x140000000
 for start,size,raw in sections:
  if start<=rva and rva+n<=start+size:return image[raw+rva-start:raw+rva-start+n]
 raise AssertionError(f'unmapped {va:x}')
files=['gummi_round7_phase_evidence.json','gummi_round7_cursor_evidence.json','gummi_round7_draw_evidence.json']
functions=[];stats=[]
for name in files:
 doc=json.loads((research/name).read_text(encoding='utf-8'))
 fs=doc['functions']
 if isinstance(fs,dict):fs=fs.values()
 lines=totalbytes=0
 for f in fs:
  addr=f['addr'];pages=f['pages'];joined=[l for p in pages for l in p['asm']['lines']]
  assert joined==f['asm']['lines'],addr
  assert len(joined)==f['instruction_count']==f['total_instructions'],addr
  assert f['cursor'].get('done') and not f['cursor'].get('cancelled') and f['cursor'].get('next') is None,addr
  off=0
  for i,p in enumerate(pages):
   assert p['instruction_count']==len(p['asm']['lines']),addr
   assert p['total_instructions']==len(joined),addr
   off+=len(p['asm']['lines'])
   if i<len(pages)-1:assert p['cursor'].get('next')==off and not p['cursor'].get('done'),addr
   else:assert p['cursor'].get('done') and not p['cursor'].get('cancelled') and p['cursor'].get('next') is None,addr
  pc=f['decompile'];assert pc['cursor'].get('done') and not pc.get('truncated'),addr
  chunks=f['original_bytes']['chunks'];expected=int(addr,16);b=b''
  for c in chunks:
   cb=bytes(int(t,16) for t in c['data'].split())
   assert int(c['addr'],16)==expected,addr
   expected+=len(cb);b+=cb
  assert len(b)==f['original_bytes']['size'] and b==at(int(addr,16),len(b)),addr
  functions.append(addr.lower());lines+=len(joined);totalbytes+=len(b)
 stats.append({'path':'work/trainer/research/'+name,'functions':len(list(fs)),'assembly_lines':lines,'original_bytes':totalbytes,'sha256':hashlib.sha256((research/name).read_bytes()).hexdigest()})
assert len(set(functions))==len(functions),'duplicate capture'
data_bytes=0
data={"regions":[]}
status={json.loads(l)['address'].lower():json.loads(l) for l in (root/'work/trainer/audit/function_status.jsonl').read_text(encoding='utf-8').splitlines()}
baseline=[{'addr':a,'status':status.get(a,{}).get('semantic_status'),'claim_count':len(status.get(a,{}).get('claims',[])),'evidence_tier':status.get(a,{}).get('evidence_tier')} for a in functions]
report={'original_path':str(original),'original_sha256':sha,'files':stats,'functions':len(functions),'assembly_lines':sum(x['assembly_lines'] for x in stats),'original_code_bytes':sum(x['original_bytes'] for x in stats),'data_regions':len(data['regions']),'data_bytes':data_bytes,'failures':0,'baseline_audit_sha256':hashlib.sha256((root/'work/trainer/audit/function_status.jsonl').read_bytes()).hexdigest(),'baseline_function_status':baseline}
(research/'gummi_round7_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ['baseline_function_status','files']},indent=2))

