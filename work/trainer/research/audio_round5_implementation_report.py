"""Build the owned spatial-audio catalogue and implementation checkpoint."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[3];P=ROOT/'work/trainer/research'
common='Read-only sample; native audio updates remain authoritative.'
rows=[
 (408,'ready','Listener graph ready','1 means the audio graph and complete listener list were validated. 0 means unavailable, busy or not ready.',0,1,'0x140121D90 / 0x140077FC0 / 0x140070E20'),
 (409,'count','Registered listeners','Number of listeners in the validated native list. A ready but empty list reports zero.',0,1024,'0x1400710C0 / 0x140071640 / 0x140071740'),
 (410,'capacity','Listener capacity','Allocated capacity of the native listener pointer array. The diagnostic accepts at most 1024 entries.',1,1024,'0x1400708B0 / 0x1400710C0'),
 (411,'peak','Peak registered listeners','Highest registered listener count retained by this native manager.',0,1024,'0x1400710C0'),
 (412,'enabled','Enabled listeners','Registered listeners whose native enabled bit is set. Valid zero means no listener is enabled.',0,1024,'0x140072070 / 0x140075830'),
 (413,'selected_id','Selected listener ID','ID of the registered, enabled listener that matches the native priority winner. Unavailable while selection is stale or cached transforms are invalid.',1,4294967295,'0x140072070 / 0x140071640 / 0x140071740'),
 (414,'selected_kind','Selected listener type','Native listener type: 1 = Base, 2 = Point, 3 = Line. The one-byte type and native class must agree.',1,3,'0x1400710C0'),
 (415,'selected_priority','Selected listener priority','Unsigned 32-bit priority. The largest enabled priority wins; the later list entry wins a tie.',0,4294967295,'0x140072070 / 0x140075910'),
 (416,'position_x','Listener X','X coordinate copied from the last native audio update. It may lag a recent listener change and uses native game coordinate units.',-3.4028234663852886e38,3.4028234663852886e38,'0x140072070 / 0x140071DE0'),
 (417,'position_y','Listener Y','Y coordinate copied from the last native audio update. It may lag a recent listener change and uses native game coordinate units.',-3.4028234663852886e38,3.4028234663852886e38,'0x140072070 / 0x140071DE0'),
 (418,'position_z','Listener Z','Z coordinate copied from the last native audio update. It may lag a recent listener change and uses native game coordinate units.',-3.4028234663852886e38,3.4028234663852886e38,'0x140072070 / 0x140071DE0')]
catalog=[]
for slot,suffix,name,description,minimum,maximum,addresses in rows:
    catalog.append(dict(Id='spatial_audio.'+suffix,Category='Spatial Audio',Name=name,Description=description,
        Kind='ReadOnly',CommandId=0,ValueSlot=slot,CapabilitySlot=slot,Minimum=minimum,Maximum=maximum,
        DefaultValue=0,RequiresScene=False,ChangesProgression=False,CanSaveInProfile=False,RestoreBehavior=common,
        Evidence=[dict(Address=addresses,Finding=description,Level='Static native code and isolated guard tests; live audio behavior not tested.')]))
(P/'spatial_audio_features.json').write_text(json.dumps(catalog,indent=2),encoding='utf-8')
assert [r['ValueSlot'] for r in catalog]==list(range(408,419))
files=['trainer/Native/SpatialAudioFeatures.inl','work/trainer/tests/SpatialAudioGuardTests.cpp',
    'work/trainer/tests/build_spatial_audio_tests.cmd','work/trainer/research/spatial_audio_features.json',
    'work/trainer/research/audio_round5_deep.json','work/trainer/research/audio_round5_independent_review.json',
    'trainer/Native/AudioFeatures.inl']
report=dict(date='2026-10-04',status='Implementation and isolated tests complete; independent static source review passed without blocking findings. Frozen for root integration and package verification.',
    independentSourceReview=dict(reviewer='pe_inventory',report='work/trainer/research/audio_round5_implementation_review.json',
        result='No blocking issue; complete source/test review plus five saved full native assembly bodies,826 instructions. Author1774-check run was not independently rerun by the reviewer.',
        historicalReportHash='ff55376ff6df913b50a75765fae98c28e8b35b87cd32fb984b2d6c3a77a8ab5f',
        hashNote='The independent review records the implementation report at review time. This later status-only refresh records that review outcome; source, test and catalogue hashes are unchanged. The historical report hash is intentionally retained and is not a fingerprint of this follow-up report.'),
    binarySha256='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed',
    module='trainer/Native/SpatialAudioFeatures.inl',namespace='spatial_audio',slots=list(range(408,419)),reservedUnused=list(range(419,424)),
    integration=dict(includeAfter='AudioFeatures.inl',capabilities='SpatialAudioCapabilities()',snapshot='SpatialAudioSnapshot(const TrainerContext&)',
        commands='None',tick='None',reset='None',catalogue='work/trainer/research/spatial_audio_features.json',
        tests='work/trainer/tests/build_spatial_audio_tests.cmd',ownership='No shared Bridge, UI, build pipeline or catalogue assembler files edited.'),
    behavior=[
        'Uses real audio_mix::ThreadReady/GraphReady/SameGraph helpers; requires the validated application post-Update continuation lifecycle. A Sora scene is not required.',
        'Require Writable on each captured CS before TryEnter: outer global Sound CS first, validate manager/layout roots, then manager CS+776. Revalidate roots/host and copy the complete bounded list under both locks.',
        'Pairs captured acquired lock addresses with nested finally cleanup, releasing inner before outer even when validation returns early or a read/release raises SEH.',
        'Checks capacity1..1024, count0..capacity, peak count..capacity, full capacity*8 array range and every counted nonnull unique pointer/nonzero ID, exact vtable/BYTEkind and manager backlink.',
        'Reads member IDs/priorities as uint32; selects greatest enabled priority and later entry on ties. Never dereferences selected+120: it compares that pointer with the already validated winning member.',
        'Active identity/priority/position publish together only when selected matches the winner and cached position4 floats plus both cached matrices are finite. Unknown manager+148 is not used.',
        'No listener getters, creation, updates, observer callbacks or setters are invoked. No persistent trainer state, hook, restore lease or gameplay data write is introduced.',
        'IPC values publish after both locks are released. Slot408 is valid0 on failed readiness; dependent fields remain invalid. Structural counts can be valid even when active selection is unavailable.'
    ],
    tests=dict(command='work\\trainer\\tests\\build_spatial_audio_tests.cmd',compiler='MSVC x64 /std:c++17 /O2 /W4 /MT /EHsc',checks=1774,failures=0,warnings=0,
        coverage=['All three native classes and exact one-byte type versus adjacent padding.',
            'Unsigned high-bit/max priorities, zero priorities, tie order and enabled bit0.',
            'Valid zero coordinates/counts versus unavailable dependent slots; empty list and stale/dangling selected pointer with no dereference.',
            'Full1024-member bound, count/capacity/peak limits, null/duplicate/foreign-owner/type mismatches, full list-span checks and pointer-overflow rejection.',
            'Every cached position and matrix element screened for NaN/Infinity; unverified+148 field ignored.',
            'Real Win32 critical sections held by another thread; both busy outcomes return promptly with correct release pairing.',
            'Readable but read-only outer/inner critical sections are rejected before TryEnter can write them.',
            'Manager/interface destruction, changed driver/layout roots, byte816, backlinks and host expiry after inner acquisition.',
            'SEH injected at every Readable call, late member failure, TryEnter failure and inner-release failure; captured outer cleanup remains guaranteed.',
            'All manager bytes outside the Win32 lock unchanged; only408..418 capabilities;419..423 unused.'],
        limits='Synthetic allocated memory and real OS locks only. No running game, native audio callbacks, UI, save or full package build.'),
    limitations=[
        'Object/CS lifetime relies on normal serialized application Init/Update/Shutdown. Byte816 alone is not sufficient, and foreign-thread private teardown remains unsupported.',
        'The cached position has no frame timestamp and may lag setters. Pointer reuse and arbitrary concurrent corrupt/modded writes cannot be ruled out by the checks.',
        'The duplicate scan is bounded at1024 members and allocates a fixed24KiB Member array on the native stack; no allocator call occurs while the audio locks are held.',
        'This adds diagnostics only; no claim about audible output or speaker-channel semantics is made.'
    ],fingerprints=[dict(file=f,sha256=hashlib.sha256((ROOT/f).read_bytes()).hexdigest()) for f in files])
(P/'audio_round5_implementation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('Catalogue:',len(catalog),'readouts. Implementation report and exact source/test hashes saved.')
