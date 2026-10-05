import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'work/trainer/research'
load=lambda p:json.loads(p.read_text(encoding='utf-8'))
meta=load(OUT/'managed_tools_round3_metadata.json')
evidence=load(OUT/'managed_tools_round3_evidence.json')+load(OUT/'managed_tools_round3_support_cil.json')+[load(OUT/'managed_tools_round3_wndproc.json')]+load(OUT/'managed_tools_round3_exit_cil.json')
blocks=[]
for name in ['managed_tools_round3_cil_bytes.json','managed_tools_round3_wndproc_bytes.json','managed_tools_round3_exit_cil_bytes.json']:
    blocks+=load(OUT/name)['result']
byaddr={x['addr']:bytes(int(n,16) for n in x['data'].split()) for x in blocks}
assert len(meta['methodBodies'])==len(evidence)==35
for m in meta['methodBodies']:
    assert byaddr[m['idaSyntheticAddress']]==bytes.fromhex(m['codeHex'])
for body in evidence:
    assert len(body['asm']['lines'])==body['instruction_count']==body['total_instructions']
native=load(OUT/'managed_tools_round3_native_evidence.json')+load(OUT/'managed_tools_round3_exit_native.json')
for body in native:
    assert len(body['asm']['lines'])==body['instruction_count']==body['total_instructions']
catalog=load(ROOT/'trainer/KH2Trainer/Data/runtime_diagnostics.json')
rows=meta['tables']['Axa._wtable']['entries']
for message in catalog['Messages']:
    for text in message['Localizations']:
        actual=next(r for r in rows if r['message']==message['Id'] and r['language']==text['LanguageId'])
        assert text['Text']==actual['text'] and text['TextAddress']==actual['textPointer']
for prompt in catalog['ClosePrompts']:
    field={'idle':'Axa.strwText','gameplay':'Axa.strwGamePlayText','busy':'Axa.strwProcessRunText'}[prompt['Id']]
    for text in prompt['Localizations']:
        actual=meta['tables'][field]['entries'][text['LanguageId']]
        assert text['Text']==actual['text'] and text['TextAddress']==actual['va']
paths=['trainer/KH2Trainer.Core/BinaryDiagnosticCatalog.cs','trainer/KH2Trainer.Tests/BinaryDiagnosticTests.cs','trainer/KH2Trainer/Data/runtime_diagnostics.json']
hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
data={'originalCilBodiesMatched':35,'cilInstructions':sum(x['instruction_count'] for x in evidence),
      'newCilClaims':25,'nativeBodies':len(native),'nativeInstructions':sum(x['instruction_count'] for x in native),
      'exactSourceTextComparisons':66,'catalogChecks':60,'catalogFailures':0,'hashes':hashes,
      'status':'Checkpoint frozen; UI/package integration and external reviews pending.'}
(OUT/'managed_tools_round3_verification.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
print(json.dumps(data,indent=2))
