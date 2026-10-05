"""Record the independent read-only review against the final author-frozen AA files."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
EXPECTED={
 'trainer/Native/RendererAaFeatures.inl':'af7adcbaed5a611d18368035bae8b2f6bf83fa1ede469fe19f669fce38dd779c',
 'work/trainer/tests/RendererAaTests.cpp':'56f588e28c584809bace2ce98d30146116d91c43ea7a707c3bfd1176fe805841',
 'work/trainer/research/renderer_aa_features.json':'f665c669c18967d23589fe574941a21564bd9dbfc0be7484d4b7ad4717ddcc5c'}
def main():
    inputs=[]
    for p,expected in EXPECTED.items():
        actual=hashlib.sha256((ROOT/p).read_bytes()).hexdigest();assert actual==expected
        inputs.append(dict(path=p,sha256=actual))
    log='work/trainer/tests/renderer_aa_build.log';raw=(ROOT/log).read_bytes()
    text=raw.decode('utf-16')if raw.startswith((b'\xff\xfe',b'\xfe\xff'))else raw.decode('utf-8-sig')
    match=re.search(r'Renderer AA: (\d+) checks, (\d+) failures',text);assert match and match[2]=='0'
    report=dict(status='PASSED_FINAL_STATIC_IMPLEMENTATION_REVIEW',reviewer='/root/pe_inventory',inputs=inputs,
        scope='Native callsite/relay installation, six-argument ABI, lifetime policy, rollback/SEH, readouts and test-source review. No reviewer build or game access.',
        contract='work/trainer/research/renderer_aa_round7_contract.txt',
        evidence=['work/trainer/research/renderer_aa_round7_evidence0.json','work/trainer/research/renderer_aa_round7_evidence1.json',
                  'work/trainer/research/renderer_aa_round7_verification.json','work/trainer/research/renderer_round6_contract.json'],
        findings=[],
        resolved_findings=[dict(issue='An exception from rollback CAS/Flush inside the first Install-finally design could skip the remaining protection-restoration work.',
            resolution='Final Protect/Flush/Cas wrappers catch their own SEH into Fault. RollbackOwn separately checks the current page state and owned operand, catches exceptional cleanup, and permits the outer finally to restore protection. The exposed flag survives an uncertain CAS that may already have committed.',
            regression='TestTransactions injects protection exceptions before/after changes, image/rollback cache-flush exceptions and CAS exceptions before/after publication/rollback; asserts restored RX where the platform succeeds, fault/off state, captured mutex release and no reachable relay free.')],
        confirmations=[
            'Quiescence comes from the exact normal post-MyApp.Update call topology and native outer mutex30848. The patch is only aligned DWORD11A150; atomicity alone is not treated as an execution-safety proof. Startup128100 precedes worker creation; timing replay bypasses the normal decision.',
            'Twenty complete pinned native bodies include the original history decision and normal/replay/update/lifetime paths. The E8 opcode is preserved; unexpected site/body state is rejected. The resident relay and immutable original target are prepared before exposure.',
            'The relay is exactly FF25+RIP0+64bit destination, with no stack change. The compiled noinline six-argument Policy has normal PE unwind data. The native decision is called once with unchanged register/stack arguments outside the trainer-read SEH handler; native exceptions are never retried.',
            'Both policy choices are bounded to original caller/current/history/min/max and current native sample/vendor limits. Fixed returns min(requested,max); Maximum additionally retains lower native proposals. No direct resource setter, history rewrite, negotiated-capability mutation or replay override occurs.',
            'Initial and retained leases compare Display identity plus exact initialization epoch and thread creation times. Later lifetime replacement permanently faults. Host/disable loss clears policy to resident pass-through; it does not unpatch, free the relay or force immediate GPU restoration.',
            'Relay allocation is RW then RX with cache flush. The original image page has a documented temporary RWX window because making unrelated code nonexecutable would be unsafe. Partial failures retain exposed code, roll back only a still-owned operand, restore the original page protection, and fail closed.',
            'The final valid Apply first clears a previous policy, so a rejected replacement cannot silently leave the old policy enabled. Pending resize is a transient decision bypass; reset and failure reset make no resource or patch write.',
            'Catalog/action units distinguish requested samples, native limit, current samples and last native/policy decisions. Missing observations are invalid rather than invented zero. Slots447..455 and no-profile contract are consistent.'],
        tests=dict(author_reported_checks=int(match[1]),author_reported_failures=0,log=log,log_sha256=hashlib.sha256(raw).hexdigest(),
            reviewer_ran_build=False,source_reviewed=True,
            notable_cases=['Full2x4x4x4x4x2 policy/current/proposal/capability/vendor matrix with original-once assertions.',
                           'Actual RX relay to compiled wrapper ABI and exception propagation, plus actual patched E8 in a synthetic caller preserving all six arguments/return.',
                           'Boundary rel32 distances, mitigation/pin/query rejection, foreign CAS ownership, before/after-write exceptions, persistent restore failure, and no postpublication free/retry.',
                           'Freshness, creation-time/epoch/device replacement, original native exception, own post-native read exception, rollback and shared Display mutex-fault latching.']),
        limitations=['No live game, graphics output, GPU/driver failure or arbitrary third-party patcher validation.',
                     'The author fixture executes a synthetic caller/relay and mocked original decision; the full game render loop is not reproduced.',
                     'Persistent OS protection failure remains a reported restart-required state. No static review can promise to repair an uncooperative or corrupted process.',
                     'Raw-body counts are evidence coverage, not a claim of complete renderer semantics.'])
    (HERE/'renderer_aa_round7_implementation_review.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    lines=['Renderer AA round7: independent implementation review','===================================================',
           'PASSED: no remaining blocking finding in the frozen source/test/catalog.','',
           'Checked native quiescence, aligned operand ownership, resident RX relay, six-argument original-once ABI, lifetime identity, bounded policies and failure cleanup.',
           'Resolved finding: SEH in rollback must not skip image protection restoration. The final wrappers catch per-operation SEH; RollbackOwn is separately guarded and handles uncertain committed CAS writes. Regression cases cover these phases.','',
           f"Author log inspected: {match[1]} checks, 0 failures. Reviewer did not rebuild or access a game process.",
           'Tests execute the real relay and a synthetic patched E8 caller, including compiled-wrapper unwind checks. They do not execute the full native renderer.','',
           'Live graphics, device-loss and arbitrary concurrent code-patcher behavior remain untested. Partial failure can require restart.','',
           'Frozen input hashes:']+[x['sha256']+'  '+x['path']for x in inputs]
    (HERE/'renderer_aa_round7_implementation_review.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('AA independent review saved: '+match[1]+' author checks, no remaining blocker.')
if __name__=='__main__':main()
