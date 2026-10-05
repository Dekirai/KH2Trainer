"""Verify the complete round7 Actor bodies against the untouched original PE."""
from pathlib import Path
import hashlib, json, sys
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'work/pe/deps'))
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
original = Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
raw = original.read_bytes()
digest = hashlib.sha256(raw).hexdigest()
assert digest == '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
pe = pefile.PE(data=raw, fast_load=True)
decoder = Cs(CS_ARCH_X86, CS_MODE_64)
path = HERE/'actor_ai_round7_complete_evidence.json'
evidence = json.loads(path.read_text(encoding='utf-8-sig'))
rows = []
seen = set()
for f in evidence['functions']:
    addr = int(f['addr'], 16)
    assert addr not in seen
    seen.add(addr)
    size = int(f['analysis']['size'], 16)
    saved = bytearray()
    for region in f['bytes']:
        assert int(region['addr'], 16) == addr+len(saved)
        saved.extend(int(value,16) for value in region['data'].split())
    actual = pe.get_data(addr-pe.OPTIONAL_HEADER.ImageBase, size)
    assert len(saved) == size and saved == actual
    lines = []
    for p in f['pages']:
        assert p['offset'] == len(lines) and p['instruction_count'] == len(p['asm']['lines'])
        lines.extend(p['asm']['lines'])
        assert not p['cursor'].get('cancelled')
        if p['cursor'].get('done'):
            assert p is f['pages'][-1] and p['cursor'].get('next') is None
        else:
            assert p['cursor']['next'] == len(lines)
    assert f['pages'][-1]['cursor']['done']
    assert all(p['total_instructions'] == len(lines) for p in f['pages'])
    decoded = list(decoder.disasm(actual, addr))
    assert [i.address for i in decoded] == [int(x['addr'],16) for x in lines], f['addr']
    assert sum(i.size for i in decoded) == size
    for kind in ('caller','callee'):
        a = f['analysis']
        assert not a[kind+'s_truncated'] and a[kind+'_count'] == len(a[kind+'s'])
    rows.append(dict(address=f['addr'], bytes=size, instructions=len(lines),
                     sha256=hashlib.sha256(actual).hexdigest(),
                     originalBytesEqual=True, instructionBoundariesEqual=True))
# All three descriptor callbacks pass the second argument directly to the VM/action update.
for address in (0x3DB4C0,0x411420,0x41A560):
    code = pe.get_data(address, 8)
    assert code[:4] == bytes.fromhex('488bcae9')
    assert address+8+int.from_bytes(code[4:], 'little', signed=True) == 0x3B4460
report = dict(success=True, functions=rows, functionCount=len(rows),
              instructions=sum(r['instructions'] for r in rows),
              originalBytes=sum(r['bytes'] for r in rows),
              originalSha256=digest, evidenceSha256=hashlib.sha256(path.read_bytes()).hexdigest(),
              liveGameAccess=False, limitations='Instruction boundaries and concrete static claims; no runtime reachability or general AI-freeze proof.')
(HERE/'actor_ai_round7_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ('success','functionCount','instructions','originalBytes','liveGameAccess')}))
