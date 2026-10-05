"""Independent read-only byte/range verification and scoped listener-contract review."""
from pathlib import Path
import json,sys,hashlib
ROOT=Path(__file__).resolve().parents[3];P=ROOT/'work/trainer/research'
sys.path.insert(0,str(ROOT/'work/pe/deps'))
import pefile
source=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
data=source.read_bytes();sha=hashlib.sha256(data).hexdigest();pe=pefile.PE(data=data)
assert sha=='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
files=['audio_round5_deep.json','audio_round5_full_asm.json','audio_round5_extra_asm.json','audio_round5_original_verification.json','audio_lifecycle.txt','audio_round5_deep.txt']
rows=[]
for fn in files[1:3]:rows+=json.loads((P/fn).read_text())
original=json.loads((P/files[3]).read_text());ranges={int(r['address'],16):r for r in original['ranges']}
seen=set();checks=[]
semantic={0x140071500,0x140071640,0x140072070,0x140073c00,0x140073c20,0x140077fc0,0x1400708b0,0x140070e20,0x1400759b0,0x140075fa0,0x140076640,0x140076f20,0x1400322a0,0x140032390,0x1400710c0,0x140071740,0x140077be0}
for row in rows:
    address=int(row['addr'],16);assert address not in seen;seen.add(address)
    r=ranges[address];raw=pe.get_data(address-pe.OPTIONAL_HEADER.ImageBase,r['bytes'])
    assert len(raw)==r['bytes'] and hashlib.sha256(raw).hexdigest()==r['sha256']
    lines=[]
    for pg in row['pages']:
        assert len(pg['asm']['lines'])==pg['instruction_count'];lines+=pg['asm']['lines']
    assert len(lines)==r['instructions'] and row['pages'][-1]['cursor']['done'] is True
    assert len(lines)==row['pages'][-1]['total_instructions']
    addresses=[int(l['addr'],16) for l in lines]
    assert len(set(addresses))==len(addresses) and addresses==sorted(addresses)
    assert addresses[0]==address and addresses[-1]<address+len(raw)
    checks.append(dict(address=hex(address),bytes=len(raw),instructions=len(lines),sha256=r['sha256'],
        completePageCountVerified=True,originalPeHashMatches=True,semanticallyReadForThisReview=address in semantic,
        originalBytesHex=raw.hex() if address in semantic else None))
assert len(checks)==88 and sum(c['semanticallyReadForThisReview'] for c in checks)==17
result=dict(date='2026-10-04',reviewer='managed_tools',status='No blocking issue in the proposed read-only contract; no implementation or runtime test was reviewed.',
    sourceSha256=sha,scope='All88 supplied body ranges and page counts checked mechanically;17 critical list/selection/update/teardown bodies read in full. Existing app-loop lifetime report and AudioFeatures.ThreadReady/GraphReady read for integration context.',
    inputs=[dict(file=fn,sha256=hashlib.sha256((P/fn).read_bytes()).hexdigest()) for fn in files],
    checks=checks,
    conclusions=[
        'The global Sound CS is held by077FC0 before it calls072070, including the selected-pointer clear before the inner manager lock. Retaining the outer lock is essential.',
        '0322A0/032390 demonstrate global-then-manager lock order and manager-before-global release. TryEnter in that same order with paired cleanup matches the proposed nonblocking snapshot.',
        '071640/071740 remove and free list members without clearing selected+120. Never dereference selected before full validated list membership, enabled-state and current-winner checks.',
        '072070 uses unsigned priority comparisons; later enabled entries win ties. Base/point update return enabled; line update also returns success for enabled listeners even when an endpoint ID is absent.',
        '0710C0 establishes BYTE kind+8, DWORD ID+12, manager backlink+16, QWORD list+768, signed count+24/peak+28/capacity+32 and136/184-byte object sizes. It can insert null after allocation failure, so validating all counted entries is appropriate.',
        '070E20 deletes its own critical section without clearing byte816. The flag is not a live-object generation or a standalone permission to TryEnter. Existing validated app post-Update lifecycle is a required independent condition.',
        '077BE0 joins workers before deleting the listener manager, and clears the global only after destructor return. Root-null checks or the global CS by themselves do not cover arbitrary-thread teardown.',
        'Current max-priority membership makes cached position usable as last native audio update; it cannot prove equality to a newly set matrix or detect every pointer-reuse episode. Existing limitations describe this correctly.'
    ],
    implementationNotes=[
        'Read the type as BYTE+8 and derive labels only from the exact vtable/type pairs. Keep136 bytes for base/point and184 for line.',
        'Capture actual acquired critical-section addresses and release only those, inner then outer, in guaranteed cleanup even after failed validation.',
        'A failed active-selection check should invalidate active ID/type/priority/position together; independently validated structural counts can remain available.',
        'Reject busy locks without native getter/update calls. Do not mutate the native initialized byte to emulate its RAII wrappers.',
        'Do not equate finite cache values with current camera coordinates, freshness in frames, or audible spatialization accuracy.'
    ],
    limitations=['No new direct/native calls, game process access, UI action, product edit or build occurred.',
        'No instruction-decoder independence is claimed: native mnemonic interpretation uses the provided complete IDA exports; original PE byte hashes and range/count consistency were independently rechecked.',
        'No broad audit of every native caller or88 complete function semantics is claimed. Private teardown from foreign threads remains outside the observed application lifecycle.'])
(P/'audio_round5_independent_review.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('Verified88 raw ranges and full page counts;17 critical complete bodies independently read. No blocker in read-only contract.')
