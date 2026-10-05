"""Save the independent read-only implementation review with exact file hashes."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
P = ROOT / 'work/trainer/research'
files = [
    'trainer/Native/RendererDiagnostics.inl',
    'trainer/Native/DisplayFeatures.inl',
    'work/trainer/tests/RendererDiagnosticsTests.cpp',
    'work/trainer/tests/build_renderer_diagnostics_tests.cmd',
    'work/trainer/tests/renderer_diagnostics_test_run.log',
    'work/trainer/research/renderer_diagnostics_features.json',
    'work/trainer/research/renderer_round5_implementation.json',
    'work/trainer/research/renderer_round5_contract.json',
    'work/trainer/research/gummi_round5_renderer_contract_review.json',
    'work/trainer/research/renderer_round5_verification.json',
]
report = dict(
    date='2026-10-04', reviewer='/root/managed_tools',
    status='Independent static implementation review complete; no remaining blocking finding.',
    scope='Read-only review of the complete RendererDiagnostics source and synthetic test source, the shared Display dependency, native contract and selected saved full assembly. No product edits, build, live rendering or process access by this reviewer.',
    findings=[],
    resolved_root_finding='The final source latches both renderer_diagnostics::faulted and display_preview::faulted when the shared outer mutex unlock returns an error or raises SEH. Nested finally records uncertain release even when capture itself completed. Tests prohibit either Display or Renderer from retrying, and normal reset preserves both latches.',
    confirmations=[
        'Outer presentation mutex is acquired through the captured exact imported runtime functions. Ready/Same are repeated after waiting; the application thread, native exit/join contract, device, root and thread handles remain required. Initialization epoch is not treated as an object generation.',
        'Writable history CS storage is checked before TryEnter. Captured inner and outer addresses are released in finally, inner first. Values publish only after release; an inner-busy result preserves twelve scalar/resource observations while omitting four timelines.',
        'All counted nodes are checked, including the oldest: bounded capacity, full node span, unique address, reciprocal predecessor, exact final sentinel and recorded tail. Empty lists require both sentinel links. The newest payload is accepted only after the full chain passes.',
        'Native payload copies put GPU/fence/Present times at node+16/+24, but render recording times at node+32/+40. Seven selected saved full ASM bodies were read again; no new native semantics are claimed by this implementation review.',
        'Positive ordered signed64 timestamps permit end-begin and now-end without overflow; frequency<=INT64_MAX/10 protects policy multiplication. Integer subtraction precedes double conversion. QPC is sampled after capture and compared with the recorded game frequency.',
        'Ten-second duration/age and one-second GPU future tolerance are explicit diagnostic policies. CPU future timestamps are rejected. Different timing events are not interpreted as additive frame cost or FPS.',
        'Each fixed resource pool has a checked 4712-byte span, exact binding and vtable. Only 64 QWORD references at stride72 are counted; COM pointers are never dereferenced. Dimensions, AA samples, level and heap values are independently bounded.',
        'Zero duration, zero AA level and zero pool occupancy remain valid. Missing, busy, corrupt or out-of-policy values remain invalid. The common collector must continue clearing validity for each snapshot.',
        'Reset is a no-op because no game effect, retained pointer or restore lease exists. FailureReset retains a local fault latch. No game-code callback, renderer getter, resource constructor or GPU fence wait is introduced.'
    ],
    tests=dict(author_reported_checks=21962, failures=0, warnings=0,
        log='work/trainer/tests/renderer_diagnostics_test_run.log',
        independent_execution=False,
        reviewed_cases=['All bounded history lengths and malformed links/counts/spans.',
            'Outer acquisition failure, inner busy, exceptions before/inside capture, outer unlock return failure and unlock exception, shared fault latches.',
            'Root/handle/host/runtime identity mutation during acquisition, writable lock storage.',
            'QPC freshness, very large timestamps with small deltas, signed extrema, frequency disagreement, native padding ignored.',
            'Independent resource bounds, every pool occupancy0..64, poison COM references, zero versus invalid, exact capability range and byte equality.']),
    saved_full_asm_read=['0x140107D00','0x140107D40','0x140107DB0','0x140107E70','0x14010EE00','0x14010EEA0','0x14010EF90'],
    evidence=['renderer_round5_evidence_1.json','renderer_round5_verification.json','gummi_round5_renderer_contract_review.json'],
    limitations=[
        'Static review and author synthetic tests do not establish observed live GPU behavior.',
        'Outer runtime mutex acquisition can wait for native render work; the contract deliberately retains the verified native runtime ABI.',
        'Normal native application-thread and join ordering supplies lifetime. Foreign-thread destruction or unsupported renderer replacement is outside the established contract.',
        'Saved original-byte verification was read, not independently rerun for all82 renderer bodies in this review.'
    ],
    hashes=[dict(path=f,sha256=hashlib.sha256((ROOT/f).read_bytes()).hexdigest()) for f in files])
(P/'renderer_round5_implementation_review.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
text = '''Renderer diagnostics — independent implementation review
========================================================
Status: complete, no remaining blocking finding.
Reviewer: /root/managed_tools, 2026-10-04.

Read the full module and test source, shared Display dependency, native contract
and selected saved assembly. This review changed no product file and did not run
a build or access the game. The author's final log reports 21,962 checks, zero
failures and no warnings; this is not a second independent execution.

The final shared-mutex correction is present: unsuccessful outer unlocks and
unlock exceptions latch both Renderer and Display. The regression tests prevent
later access by either component, including after a normal reset.

Outer-before-inner locking, captured finally releases, revalidation after the
outer wait, full bounded history traversal and publication after release match
the contract. The four native histories retain their distinct event meanings.
Checked integer deltas precede millisecond conversion, and QPC comparison time is
sampled after capture. The fixed pool arrays are bounded and COM references are
counted without dereferencing them. Invalid values remain distinct from valid
zero durations, AA levels and pool counts.

Normal native application-thread/join ordering remains essential. Initialization
epoch is not a generation token; private foreign-thread destruction is outside
the verified contract. The outer mutex may wait for native rendering. No live
GPU behavior or FPS equivalence is established.

Exact reviewed source, test, catalogue, dependency and evidence hashes are in
renderer_round5_implementation_review.json. No new native-function coverage is
claimed by this review.
'''
(P/'renderer_round5_implementation_review.txt').write_text(text,encoding='utf-8')
print('Renderer implementation review saved; no blocking finding.')
