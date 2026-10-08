"""Verify original code bytes, complete IDA pages and worker-to-VM callsites."""
from pathlib import Path
import hashlib,importlib.util,json,struct,sys
sys.dont_write_bytecode=True
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('retail_evidence',HERE.parent/'actor-scale-contract-20261007/verify.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

def main():
    raw=(HERE/'evidence.json').read_bytes();e=json.loads(raw)
    result=base.validate(e,base.DEFAULT_EXE.read_bytes())
    md=Cs(CS_ARCH_X86,CS_MODE_64)
    bodies={int(f['addr'],16):f for f in e['functions']}
    decoded=0; embedded=0
    for f in e['functions']:
        start=int(f['addr'],16);b=base.octets(f['originalBytes']);rows=f['asm']['lines']
        for index,row in enumerate(rows):
            pc=int(row['addr'],16);instruction=next(md.disasm(b[pc-start:],pc,count=1),None)
            assert instruction is not None,hex(pc)
            end=int(rows[index+1]['addr'],16) if index+1<len(rows) else start+len(b)
            actual_end=instruction.address+instruction.size
            if actual_end!=end:
                # The VM ends in RET followed by one 3-byte NOP and 57 DWORD
                # switch targets. These are original data bytes in IDA's extent,
                # not 231 extra code bytes or unexamined arbitrary gaps.
                assert (start,actual_end,end)==(0x14041B400,0x14041C5A1,0x14041C688),(hex(pc),instruction.mnemonic,end)
                tail=b[actual_end-start:]
                assert tail[:3]==bytes.fromhex('0f1f00') and len(tail)==231
                valid={int(r['addr'],16) for r in rows}
                assert all(0x140000000+target in valid for (target,) in struct.iter_unpack('<I',tail[3:]))
                embedded+=len(tail)
            decoded+=1
    calls={
        0x1403BF4E0:[0x1403BFAB0],
        0x1403BFAB0:[0x1403C6AA0],
        0x1403C6AA0:[0x1403B5E80],
        0x1403B5E80:[0x1403E1840],
        0x1403E1840:[0x1403E1C80],
        0x1403E1C80:[0x14041B400],
        0x140431200:[0x1403C2650],
        0x1403BEEC0:[0x14012FDB0,0x140130130]
    }
    for function,expected in calls.items():
        f=bodies[function];b=base.octets(f['originalBytes']);targets=set()
        for row in f['asm']['lines']:
            pc=int(row['addr'],16);o=pc-function
            if b[o] in (0xe8,0xe9):targets.add(pc+5+struct.unpack_from('<i',b,o+1)[0])
        assert all(t in targets for t in expected),hex(function)
    data={int(d['addr'],16):base.octets(d['originalBytes']) for d in e['data']}
    assert struct.unpack_from('<QI',data[0x1407566E0])==(0x140431200,3)
    rows=bodies[0x1403B5E80]['asm']['lines']
    text=[r['instruction'] for r in rows]
    assert 'mov r9d, 3' in text and 'lea edx, [r9+18h]' in text,'motion event id27'
    result.update(evidenceSha256=hashlib.sha256(raw).hexdigest(),capstoneInstructions=decoded,
        callGraphChecks=len(calls),embeddedSwitchAndPaddingBytes=embedded,failures=0,liveGame=False,
        scope='Original PE bytes, complete ASM, every instruction boundary and selected direct-call edges. Asset-specific execution of STATUS writes on a worker is not established.')
    (HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('bodies','data')}))

if __name__=='__main__':main()
