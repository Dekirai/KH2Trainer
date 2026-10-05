"""Reproduce implementation metadata from the frozen source/test/catalog and own test log."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def digest(path):return dict(path=path,sha256=hashlib.sha256((ROOT/path).read_bytes()).hexdigest())
def main():
    source='trainer/Native/WindowDisplayFeatures.inl'
    tests='work/trainer/tests/WindowDisplayTests.cpp'
    log='work/trainer/tests/window_display_test.log'
    raw=(ROOT/log).read_bytes()
    text=raw.decode('utf-16') if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else raw.decode('utf-8-sig')
    m=re.search(r'Window display checks: (\d+); failures: (\d+)',text);assert m and int(m[2])==0
    assert 'warning C' not in text and 'error C' not in text
    review=HERE/'renderer_round7_window_implementation_review.json'
    report=dict(status='FROZEN_SOURCE_TESTS_AND_INDEPENDENT_REVIEW_COMPLETE' if review.exists() else 'SOURCE_AND_TESTS_COMPLETE_REVIEW_PENDING',scope='v0.11 native window requests; slots431..438',
        contract='work/trainer/research/renderer_round6_contract.json',
        evidence='work/trainer/research/renderer_round7_window_evidence.json',
        original_byte_verification='work/trainer/research/renderer_round7_window_validation.json',
        source_hashes=[digest(p)for p in [source,tests,'work/trainer/tests/build_window_display_tests.cmd','work/trainer/research/window_display_features.json']],
        interfaces=['WindowDisplayHandle(const TrainerContext&,unsigned,const double[8],TrainerResult&)',
                    'WindowDisplaySnapshot(const TrainerContext&)','WindowDisplayCapabilities()',
                    'WindowDisplayReset(const TrainerContext&)','WindowDisplayFailureReset(const TrainerContext&)'],
        integration=['Include after both DisplayFeatures.inl and RendererDiagnostics.inl.',
                     'Dispatch slots431/432, publish six snapshot slots433..438, initialize all eight capability bits.',
                     'Call Reset for ordinary disconnect/disable and FailureReset after bridge failures. There is no Tick, profile application or automatic restoration.',
                     'Merge only window_display_features.json and add build_window_display_tests.cmd to the parent-owned test pipeline.'],
        native_abi=dict(rva='0x124FE0',signature='void __fastcall(void* GX,const float dimensions[2],int mode)',registers='RCX=GX,RDX=private immutable stack pair,R8D=0 or2; return ignored',
                        mode0='Native float32 width*9 versus height*16; fit16:9 then signed32 truncation. Request copied synchronously.',
                        mode2='Dimensions unchanged; queues native maximized-window mode and clears requested fullscreen.',
                        native_calls_in_selected_branches=['EnterCriticalSection(GX+31432)','LeaveCriticalSection(GX+31432)','__security_check_cookie'],
                        excluded='Mode1 enumeration, direct GPU/COM/resource/fence operations, configuration writes.'),
        guards=['Exact game/application thread, fresh host heartbeat, current App/vtable/device/root/thread handles, initialized epoch and Display code/runtime guards.',
                'Full590-byte setter and33-byte normal cookie checker pinned; float constants9/16/0.0625 checked; current cookie is readable/nonzero with high16zero; game Enter/Leave IAT entries equal resolved trusted kernel32 exports.',
                'Native HWND must exist and belong to this process. Its owner thread can differ from the application update thread; handle and owner thread are part of the captured lease.',
                'Acquire trusted outer mutexGX+30848; revalidate. TryEnter resizeCS+31432; revalidate a third time and copy native state. Writable request20bytes andCS40bytes are required.',
                'Keep the explicitly acquired resize recursion across the native setter. The selected original branches only enter/leave that same recursive CS and cannot call GPU/COM/window callbacks.',
                'Reject pending dirty1024/active dirty1044/positive retry1040/current transition1072/nonzero size-handler suppression1064. Do not overwrite a competing pending request.',
                'Native flags must be0/1, both modes0..2, dimensions1..16384, retry finite0..60, transition0..3. Invalid state omits the complete six-field snapshot.',
                'Finally releases only the one resize recursion owned by this module, then the captured outer mutex. No old game data is reread after the native call; copied snapshot values publish only after both releases.',
                'Setter exception, read/lock exception or failed/uncertain unlock latches window_display, display_preview and renderer_diagnostics unavailable until restart. Ordinary Reset cannot clear the latches.'],
        behavior=['Commands acknowledge a request queued once, not a successful resize. Native119E90 later fence-waits, releases/rebuilds attachments and invokes normal window sizing.',
                  'Input bounds640..7680 and360..4320 are explicit UI policies, not inferred native ABI limits. Dimensions are exact whole pixels; output fits16:9 and can be reduced by desktop/heap limits.',
                  'Slots433/434 are actual render dimensions.435 is the consumed native mode field, not an independent OS-window/fullscreen success probe.436 combines pending or blocked native fields.437/438 are last stored request dimensions and remain unchanged for maximization.',
                  'No settings/save write, borrowed pointer retention, auto replay, profile action, detach undo or direct GPU resource mutation. Later game settings/requests may supersede the command.'],
        tests=dict(checks=int(m[1]),failures=0,warnings=0,production_branch_compile=True,log=log,
                   execution='Own isolated executable only. Original mode0/2 setter and cookie-check bytes copied into synthetic RX pages; their CS imports target compiled test mocks. No game process, COM, GPU, window or save operation.',
                   coverage=['Original-body Win64 ABI, native16:9 float32 branch/truncation, maximum/minimum/odd-aspect cases, mode0/2 from every current0/1/2 mode, identical request no-op, mode2 dimension retention, exact neighboring request-byte changes.',
                             'Three-point lifetime/thread/window/IAT/cookie validation, every623 pinned byte, invalid/inaccessible dependencies, writable storage, heartbeat rollover, native state ranges, pending and busy locks.',
                             'One outer mutex and owned resize recursion; one additional original setter enter/leave; no duplicate native call. Compiler fault seams simulate before/inside/after dispatch failures including an unknown surviving native recursion.',
                             'Shared fault latches prevent Display/RendererDiagnostics from reusing the mutex. Reset remains inert, failure reset persistent. Six readout units, invalid-vs-zero, exact capability bits and publication after release.']),
        independent_review=('Pending; '+str(review.relative_to(ROOT)).replace('\\','/') if not review.exists() else 'See '+str(review.relative_to(ROOT)).replace('\\','/')),
        limitations=['No live graphics/window or monitor/device-loss validation. The normal game driver/allocation path is not transactional and may fail after a queued acknowledgement.',
                     'No fullscreen activation: native11C970 empty-mode recursion remains unresolved. Moving from existing fullscreen to windowed/maximized uses only the native normal-mode request branches.',
                     'The initialization epoch is not a generation token. Lifecycle safety inherits the reviewed original application-thread shutdown exclusion; arbitrary modded renderer lifetimes are unsupported.',
                     'The copied native test bodies have no registered C++ xdata. Normal original paths execute; faults are injected in compiled fixture seams so test unwinding does not claim to emulate every native exceptional cleanup.',
                     'A native fail-fast or corrupted process cannot be made recoverable by SEH. Fault handling blocks further trainer renderer operations; it does not promise to undo a partially queued request or unknown native recursion.'],
        claims=[dict(addr='0x140124fe0',Finding='Complete original Mode0/2 paths only recurse into resizeCS, copy a request and run the compiler cookie check; isolated execution confirms float32 fitting, mode2 dimension retention, native dirty comparison and exact ABI. Holding the inspection recursion through this setter closes the pending-request check/call gap.',
                     Evidence=['work/trainer/research/renderer_round7_window_evidence.json','work/trainer/research/renderer_round7_window_validation.json','work/trainer/tests/WindowDisplayTests.cpp'],
                     Limitations='Static original-body and isolated fixture evidence; no live GPU/window outcome or general third-party-hook compatibility claim.'),
                dict(addr='0x140439a60',Finding='The normal compiler helper compares the supplied cookie against RVA7591F8 and requires its high16bits to be zero. The native request preflight pins this complete33-byte body and checks the current global cookie before dispatch.',
                     Evidence=['work/trainer/research/renderer_round7_window_evidence.json','work/trainer/research/renderer_round7_window_validation.json'],
                     Limitations='This is a guard on the selected native request, not a claim that all process fail-fast paths can be caught.')])
    (HERE/'renderer_round7_window_implementation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    lines=['Window and Resolution: implementation contract, round7','====================================================',report['status'],'',
           'Actions431/432 queue native windowed/maximized requests exactly once. Fullscreen activation is excluded.',
           '431 arguments: whole width640..7680 and height360..4320. Native16:9 fit, desktop/heap clamp and later resize apply.',
           '433/434 actual render pixels;435 native consumed mode0/1/2;436 pending/blocked0/1;437/438 stored request pixels.',
           'No profile, auto replay, disconnect restoration, configuration/save write or direct GPU operation.','',
           'ABI: void124FE0(GX RCX,const float[2]* RDX,int R8D). The stack pair is copied, never retained.',
           'Locks: trusted native mutex30848 -> TryEnter resizeCS31432 -> native recursive CS entry/exit -> owned CS leave -> captured outer unlock.',
           'Readiness is checked before either lock, after the outer lock and under both locks. A pending native action is rejected.',
           'Setter/lock/unlock uncertainty permanently latches Window + Display + RendererDiagnostics; Reset does not clear it.','',
           f"Validation: {report['tests']['checks']} isolated checks,0 failures,0 compiler warnings. Production branch separately compiled.",
           'The original590-byte setter and33-byte cookie helper execute against synthetic memory/RX pages and mock CS imports.',
           'The exact623bytes/153instructions plus native float constants match the original EXE. No game process was accessed.','',
           'Limits: queued is not completed. The driver/device-loss/window-callback outcome is live untested. Native failures may leave a pending change.',
           'Snapshot modes reflect native state, not a fresh OS completion probe. Epoch is an initialization gate, not a generation counter.',
           'Exception tests use compiled seams; copied code has no synthetic registration of native C++ unwind metadata.','',
           'Integration: include after DisplayFeatures+RendererDiagnostics; Handle/Snapshot/Capabilities/Reset/FailureReset; no Tick.',
           'Source hashes:']
    lines += [x['sha256']+'  '+x['path'] for x in report['source_hashes']]
    lines += ['',report['independent_review']]
    (HERE/'renderer_round7_window_implementation.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(checks=report['tests']['checks'],source_hashes=report['source_hashes'])))
if __name__=='__main__':main()
