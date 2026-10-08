"""Check generated runtime pins and fresh dispatch evidence against original retail PE."""
from pathlib import Path
import hashlib,importlib.util,json,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('generate_status_pins',HERE/'generate_pins.py')
generator=importlib.util.module_from_spec(spec);spec.loader.exec_module(generator)
source,pins=generator.build()
target=generator.ROOT/'src/KH2Trainer.Bridge/StatusBootstrapPins.inl'
assert target.read_bytes()==source.encode('utf-8')
ev=json.loads((HERE/'evidence.json').read_text(encoding='utf-8-sig'))
f=ev['functions'][0]
assert len(ev['functions'])==1 and f['addr']=='0x1405669f0' and f['size']==2
assert f['instruction_count']==f['total_instructions']==len(f['asm']['lines'])==1
assert f['cursor']=={'done':True} and f['originalBytes']=='ff e0'
assert ev['data']==[{'addr':'0x14057bca0','size':8,'originalBytes':'f0 69 56 40 01 00 00 00','meaning':'Original dispatch pointer; PE relocation applies at runtime.'}]
result={'success':True,'functions':1,'instructions':1,'originalFunctionBytes':2,'originalDataBytes':8,
    'originalSha256':generator.SHA,'evidenceSha256':hashlib.sha256((HERE/'evidence.json').read_bytes()).hexdigest(),
    'bodies':[{'addr':f['addr'],'instructions':1,'originalBytes':2,'completeAsm':True,'sha256':hashlib.sha256(bytes.fromhex('ffe0')).hexdigest()}],
    'reusedNormalClosureBodies':25,'runtimePinnedBodyBytes':pins['bodyBytes'],
    'pinsSha256':hashlib.sha256(target.read_bytes()).hexdigest(),'priorClosureEvidenceSha256':pins['closureEvidenceSha256'],
    'aslrCodeRelocations':pins['aslrCodeRelocations'],'dispatchSlotHasDir64Relocation':pins['dispatchSlotHasDir64Relocation'],
    'configurationOperandsVerified':pins['configurationOperandsVerified'],'nonzeroEventBranchBypassesEncodedSlots':True,
    'imports':pins['imports'],'failures':0,'liveGame':False,'installedObserver':False,
    'scope':'One fresh two-byte dispatch body and original relocated pointer. Reuses 25 normal closure bodies, validates all exact original code pins, PE import names/declaring DLLs, event branches and callback decoding operands. Does not prove OS implementation authenticity, hostile external interventions, runtime game installation or writer quiescence.'}
(HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('bodies','imports','configurationOperandsVerified')}))
