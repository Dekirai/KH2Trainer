"""Regenerate this bounded report index and manifest; never modifies product code."""
from pathlib import Path
import hashlib
import json
import re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def write(name, value):
    (HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    claims=[]
    def claim(rva, finding, limitations, related=(), helper=False):
        file='helper-evidence.json' if helper else 'evidence.json'
        addr=f'0x{0x140000000+rva:X}'
        claims.append({'addr':addr,'Domain':'native','Finding':finding,
                       'Evidence':[f'{file}#functions[addr={addr}]',*[f'evidence.json#functions[addr=0x{0x140000000+x:X}]' for x in related],
                                   'verification.json','AllocatorProbe.cpp','probe.log'],
                       'Limitations':limitations})
    claim(0x19C3A0,'Constructor aligns the supplied region to 16 bytes, reserves a 128-byte prefix, and requires end > aligned base+176. A 177-byte region can be constructed but cannot fit an ordinary minimum 64-byte block. Multiple instances reuse the global AC0FD8 semaphore wrapper without an instance count in this body.',
          'Valid caller-provided memory and native helper contracts remain prerequisites. Simulated helper creation failure is not a live Windows failure.')
    claim(0x19C2B0,'Allocation rounds payload to 16 bytes and adds 48 bytes: a 32-byte linked header and two 8-byte trailer markers. It prefers the cached predecessor gap, then first-fit from the sentinel; gaps use DWORD arithmetic. Wait result and size overflow are unchecked, including a reproduced UINT64_MAX wrap to a 48-byte block.',
          'Executed privately with recorded dependencies. No real retail oversized request or malformed caller is established.')
    claim(0x19C470,'Locked Free unlinks the block, updates accounting/cursor, fills DWORDs with EFACCAFE and then clears header+8. NULL still waits/releases. Freed addresses can be immediately reused. No owner/trailer validation appears in this body.',
          'The free dependency 3A08F0 is recorded by a stub in the probe; its actual traversal is separately analyzed. This semaphore is not a universal Actor lifetime lock.')
    claim(0x19C230,'This complete body performs the unlink/accounting/poison operation without allocator semaphore calls. Its incoming references are pdata/chained-unwind records; CHAININFO is not evidence of an EH finally handler.',
          'No direct retail caller is recorded; isolated invocation establishes body behavior only.')
    claim(0x19C510,'The capacity getter returns allocator end(+72) minus block-region start(+64), without acquiring a lock. It is independent of used bytes and largest contiguous free gap.',
          'A live caller must separately ensure lifetime and a consistent snapshot.')
    claim(0x19C520,'The used-byte getter returns QWORD+80 without acquiring a lock. Allocation adds rounded payload plus 48-byte overhead and free subtracts the stored DWORD block extent.',
          'This is allocator accounting, not raw payload use or system-process memory consumption.',[0x19C2B0,0x19C470])
    claim(0x19C530,'Reset rebuilds the sentinel and clears used/cached fields without semaphore, per-block free dependency, or poisoning; it allows prior addresses to be reused.',
          'No recorded direct code references; actual retail invocation and concurrent validity remain unproved.')
    claim(0x19C6E0,'The sixth primary vtable method clears only cached predecessor+88. The following allocation falls back to a sentinel-first search.',
          'No allocator lifetime or synchronization guarantee is added.',[0x19C2B0])
    claim(0x19C050,'The nondeleting destructor resets vtables, destroys and nulls the shared AC0FD8 wrapper when present, and cleans its CThread subobject at this+8. It does not acquire the allocator semaphore or reference-count peer instances.',
          'Artificial overlapping allocator instances confirm the local effect; actual unsafe retail overlap is not established.')
    claim(0x19C0C0,'The scalar-deleting destructor performs the same shared-wrapper and thread cleanup, additionally calls j_j_free(this) iff flag bit0 is set, and returns this.',
          'Free and CloseHandle are recording stubs in the private probe. Destruction does not establish all object owners have stopped.')
    claim(0x19C0AC,'The secondary-vtable entry subtracts eight from RCX and tail-jumps to the scalar-deleting destructor, preserving the flag argument.',
          'The pdata reference also pointing at this address is a preceding function EndAddress, not a code call.',[0x19C0C0])
    claim(0x19C560,'Global allocator replacement calls the old AC0FD0 virtual deleting destructor first, then constructs/publishes the supplied region. A too-small new region publishes null after the old instance has already been destroyed.',
          'Only pdata references were recorded; no complete live caller/lifetime contract or semantic return value is established.')
    claim(0xFDA70,'Semaphore-wrapper destruction ignores NULL wrappers; otherwise it calls imported CloseHandle on wrapper+8 and j_j_free(wrapper). The PE import identity is independently verified.',
          'Wrapper validity is assumed; CloseHandle outcome is unused and kernel/resource behavior is replaced in the probe.',helper=True)
    claim(0xFD950,'CThread destruction sets its vtable, closes and nulls nonzero handle fields +24 and +8, and clears DWORD+48 when +8 was nonzero. As Allocator+8 subobject these map to allocator+32,+16,+56.',
          'Return-register contents have no demonstrated semantic contract; asynchronous thread completion is not established.',helper=True)
    write('claims.json',{'schemaVersion':1,'date':'2026-10-08','Domain':'native','claims':claims})
    verification=json.loads((HERE/'verification.json').read_text(encoding='utf-8-sig'))
    match=re.search(r'AllocatorProbe checks=(\d+) failures=(\d+)',(HERE/'probe.log').read_text(encoding='utf-8-sig'))
    assert match and int(match[2])==0
    write('report.json',{'schemaVersion':1,'date':'2026-10-08','scope':'Bounded allocator body semantics and isolated native-code probe; no product/runtime installation.',
                        'staticVerification':{k:verification[k] for k in ['completeBodies','instructions','bodyBytes','dataBytes','incomingXrefs']},
                        'probe':{'checks':int(match[1]),'failures':int(match[2]),'originalBodiesExecuted':14,'sequenceOperations':1200,
                                 'stubs':['0FD9C0','0FDD90','0FDC90','3A08F0','4390A0','CloseHandle IAT'],
                                 'scope':'Private process, relocated data, original body bytes, normal no-fault paths. No actual semaphore, game resources, threads or live game.'},
                        'useCases':['Consistent allocator accounting/fragmentation diagnostics after lifetime admission is proved.',
                                    'Address-reuse evidence for Actor/STATUS identity and cancellation design.'],
                        'limits':['No complete transitive caller or lifetime proof.','No live-game test.','No shipment or release rebuild in this research step.'],
                        'claimsFile':'claims.json','reportFile':'report.txt'})
    paths=[p for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='manifest.json']
    write('manifest.json',{'schemaVersion':1,'date':'2026-10-08','scope':'Allocator research, isolated probe sources and recorded results',
                          'files':[{'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]})
    print(json.dumps({'claims':len(claims),'checks':int(match[1]),'failures':int(match[2]),'manifestFiles':len(paths)}))


if __name__=='__main__':
    main()
