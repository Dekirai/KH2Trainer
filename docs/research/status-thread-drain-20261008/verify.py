"""Verify the fresh five-root capture and prerequisites for the conservative stack scan."""
from pathlib import Path
import hashlib,importlib.util,json,sys
sys.dont_write_bytecode=True
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_IMM

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('original_verify',HERE.parent/'actor-scale-contract-20261007/verify.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
evidence=json.loads((HERE/'evidence.json').read_text(encoding='utf-8-sig'))
raw=base.DEFAULT_EXE.read_bytes()
assert hashlib.sha256(raw).hexdigest()==evidence['originalSha256']
original=base.original_reader(raw,int(evidence['imageBase'],16))
results=[]
previous=json.loads((HERE.parent/'status-bootstrap-20261007/evidence.json').read_text(encoding='utf-8-sig'))
old={int(f['addr'],16):f for f in previous['functions']}
assert len(evidence['functions'])==5
assert {int(f['addr'],16) for f in evidence['functions']}=={int(x,16) for x in previous['writerRoots']}
decoder=Cs(CS_ARCH_X86,CS_MODE_64);decoder.detail=True
continuations=[]
for f in evidence['functions']:
    address=int(f['addr'],16);body=base.octets(f['originalBytes'])
    assert len(body)==f['size'] and body==original(address,len(body))
    assert body==base.octets(old[address]['originalBytes'])
    assert f['cursor']['done'] is True and not f['cursor'].get('next')
    decoded=list(decoder.disasm(body,address));rows=f['asm']['lines']
    assert len(decoded)==len(rows)==f['instruction_count']==f['total_instructions']
    assert decoded[-1].address+decoded[-1].size==address+len(body)
    assert [i.address for i in decoded]==[int(r['addr'],16) for r in rows]
    for i in decoded:
        if i.mnemonic=='call':
            assert i.operands[0].type==X86_OP_IMM and i.bytes[0]==0xe8 and i.size==5
            assert address<i.address+i.size<address+len(body)
            continuations.append({'root':hex(address),'call':hex(i.address),'returnPc':hex(i.address+i.size)})
        if i.mnemonic.startswith('j'):
            assert i.operands[0].type==X86_OP_IMM and address<=i.operands[0].imm<address+len(body)
        # The five roots only change RSP through ordinary ABI frame operations.
        if any(i.reg_name(r)=='rsp' for r in i.regs_access()[1]):
            assert i.mnemonic in ('push','pop','sub','add','call','ret')
            if i.mnemonic in ('sub','add'):
                assert i.op_str.startswith('rsp, ') and i.operands[1].type==X86_OP_IMM
                assert i.operands[1].imm%8==0
    assert decoded[-1].mnemonic=='ret'
    results.append({'addr':f['addr'],'instructions':len(decoded),'originalBytes':len(body),
                    'sha256':hashlib.sha256(body).hexdigest(),'completeAsm':True})

# Non-alertable fallback does not opt into ordinary alertable-wait APC dispatch.
wait=old[0x14043a028]
wait_body=base.octets(wait['originalBytes'])
assert wait_body==original(int(wait['addr'],16),len(wait_body))
instructions=list(decoder.disasm(wait_body,int(wait['addr'],16)))
lookup={i.address:i for i in instructions}
assert (lookup[0x14043a081].mnemonic,lookup[0x14043a081].op_str)==('xor','r8d, r8d')
assert lookup[0x14043a084].op_str=='edx, ebx'
assert lookup[0x14043a086].mnemonic=='call'
result=dict(success=True,functions=len(results),instructions=sum(r['instructions'] for r in results),
            originalFunctionBytes=sum(r['originalBytes'] for r in results),
            originalSha256=evidence['originalSha256'],bodies=results)
result.update(
    evidenceSha256=hashlib.sha256((HERE/'evidence.json').read_bytes()).hexdigest(),
    priorClosureEvidenceSha256=hashlib.sha256((HERE.parent/'status-bootstrap-20261007/evidence.json').read_bytes()).hexdigest(),
    rootCallContinuations=continuations,normalRootReturnsStayInsideBodies=True,
    nonAlertableWaitFallback=True,failures=0,liveGame=False,installedObserver=False,
    scope='Five fresh complete root bodies match the prior original-byte-verified native closure. Root calls retain normal aligned Win64 return slots; no external root tail jump. The wider no-fiber/exception/import contract remains conditional, not a whole-process proof.')
(HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('bodies','rootCallContinuations')}))
