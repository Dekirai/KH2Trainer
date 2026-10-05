"""Rebuild the renderer-control report from fresh, complete read-only evidence."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DATA = json.loads((HERE / 'render_controls_deep_data.json').read_text(encoding='utf-8'))
functions = {}
for part in DATA['evidence_manifest']:
    path = ROOT / part['file']
    for f in json.loads(path.read_text(encoding='utf-8'))['functions']:
        p, a = f['pseudocode'], f['disassembly']
        assert p['cursor']['done'] and not p.get('truncated'), f['addr']
        assert a['cursor']['done'] and a['instruction_count'] == a['total_instructions'], f['addr']
        assert a['instruction_count'] == len(a['asm']['lines']), f['addr']
        functions[f['addr']] = (part['file'], f)

claims = []
def claim(rva, finding, limitation):
    addr = hex(0x140000000 + int(rva, 16))
    assert addr in functions, addr
    claims.append(dict(addr=addr, Finding=finding,
        Evidence=[functions[addr][0]], Limitations=limitation,
        strength='Fresh complete addressed pseudocode and full ASM; static only'))

claim('5061A0', 'Native brightness preview accepts signed int16 in CX, converts to float, divides by 50 and tail-jumps to 1268C0 with XMM0. It does not write configuration or save data.', 'Return pointer is an implementation detail; callers should ignore it. Range validation belongs to the caller.')
claim('1268C0', 'Writes adjustment to GX+716 and gamma exponent 2.2/(adjustment+2.2) to GX+23360. XMM0 is the input float. Neither native mutex nor a resource allocation is used once the singleton exists.', 'Direct calls must not trigger singleton construction; use the native menu range and established renderer lifetime. Native code itself does not serialize this setter.')
claim('51A3F0', 'The brightness menu updates its numeric label and calls 5061A0 only when the preview argument is nonzero.', 'This UI-object function is evidence for the preview API, not a trainer-call target.')
claim('51A4C0', 'Brightness menu bounds its signed short to -50..50. Preview and cancel/confirm are distinct: configuration field+12 and persistence are changed only in the menu confirm/cancel flow, while 5061A0 changes the display preview.', 'Do not invoke the menu state machine from the trainer. A preview can later be overwritten by ordinary settings application.')
claim('5061C0', 'Reads signed int16 Settings_GetFields()+12 and sends value/50 to 1268C0; this wrapper does not validate the stored value.', 'A trainer restore action must validate the snapshot first; blindly calling this wrapper trusts corrupted or modified config.')
claim('5061F0', 'Native color-vision preview takes signed int16 CX and DX. Type0 writes (0,0); otherwise severity is clamped to1..10 before forwarding to125D00.', 'Type itself is not clamped here. Validate0..3 before calling.')
claim('125D00', 'Copies ECX type and EDX severity to GX+23364/+23368. These are final-pass pixel constants and are two separate stores.', 'No lock or bounds check is present. Do not publish a mismatched pair to a concurrent presentation pass.')
claim('51AE30', 'Actual color-vision menu restricts type0..3 and severity1..10 and calls5061F0 for preview/cancel. Only acceptance writes Settings+16/+18 and schedules the save step.', 'The exact localized names of modes1..3 were not independently decoded in this round; use existing verified labels or neutral mode numbers.')
claim('506240', 'Reads loaded color-vision type at Settings+16 and severity+18. Disabled becomes(0,0), enabled severity clamps1..10; type remains unchecked.', 'Explicit restore should snapshot/validate all three display settings and then call the preview APIs with that immutable snapshot.')
claim('14CDE0', 'Settings getter is a leaf returning fixed VA140715364. Brightness/type/severity are signed16 fields at offsets12/16/18.', 'Loaded configuration is not necessarily the last value written to disk. The proposed action only reads it.')
claim('111AE0', 'Compares and uploads the80-byte PS constant block GX+23300, including gamma at+60 and color-vision type/severity at+64/+68. A changed value is detected by memcmp; no extra dirty-byte write is required for the preview.', 'The uploader also handles other constants and resources. It must not be called directly as a trainer refresh.')
claim('1219F0', 'Final presentation explicitly schedules fillScreen with target5 and program47, transitions swapchain buffers to render-target then present/common, and flushes. This gives the preview a real final-image consumer.', 'A final-image correction also affects UI/compositing, not solely scene illumination or physical exposure.')
claim('11AEF0', 'Fullscreen enqueue captures target/program/source and renderer into a native closure and passes it to119BA0.', 'Borrowed render resources and replay closures prevent safely substituting arbitrary targets from the host.')
claim('128260', 'Frame completion invokes1219F0, submits command lists, advances rings/serial and retires framebuffer resources. Its observed native callers are120ED0,128470 and1287D0.', 'Synchronization is supplied by its outer callers, not by this function itself. Xrefs are finite static evidence, not a proof against external code.')
claim('128470', 'Normal presentation path acquires the in-situ MSVCP mutex at GX+30848 before rendering/replay/frame completion, and unlocks it on the normal return path.', 'Use the same runtime import and native lifecycle. Do not reinterpret the opaque mutex as a Windows CRITICAL_SECTION.')
claim('1287D0', 'Timing thread takes the same GX+30848 mutex around its intermediate-frame replay/completion. It can run while the application update thread is active.', 'Scalar atomicity alone is insufficient for coupled preview fields. Worker lifetime and renderer teardown still need gating.')
claim('120ED0', 'Replay temporarily sets GX+22944, interpolates camera data, invokes stored closures, completes the frame and clears the replay flag.', 'The replay flag is state, not a lock. Polling it is not sufficient to synchronize a write.')
claim('129110', 'Actual timing-thread entry invokes1287D0 then _endthreadex.', 'This disproves an assumption that presentation always shares the engine update thread.')
claim('127ED0', 'Actual application-thread entry invokes121D90, then the managed-close bridge and _endthreadex.', 'The managed callback and process-wide exit flow are outside this narrow control contract.')
claim('121D90', 'The application loop calls app virtual Update at slot+32, repeats on0, invokes draw on1 and otherwise enters shutdown. A post-original Update hook executes in this application thread before that branch.', 'Reject trainer actions when the original Update requested shutdown; do not assume the current host thread is the application thread.')
claim('14EB70', 'Game Update executes the outer task scheduler then returns2 if App+4752 is nonnegative; normal result is0.', 'The proposed module must reject that exit state even if renderer vtable/device pointers remain nonnull.')
claim('11D0A0', 'Renderer startup stores App at GX+1000, creates device/root signature/shaders, sets brightness0 and gamma1, then creates application thread handle+784 and timing-thread handle+792.', 'A singleton address alone is not proof startup finished. Bind to both the live app and application thread.')
claim('10A270', 'GX construction initializes the native mutex at+30848 with _Mtx_init_in_situ(...,2), before worker startup; also clears handles/device and initializes renderer state.', 'The numeric mutex flag is recorded without interpreting undocumented CRT internals.')
claim('10BE40', 'Renderer destruction destroys GX+30848 mutex and PSO/command/resource containers before changing the final base vtable and releasing device+736.', 'Vtable/device checks alone can remain positive partway through destruction; application-thread/exit/lifecycle gates are necessary.')
claim('11AD80', 'Native GX.exit requests App+4752=256, polls application-thread exit, clears handle+784, sets stop flag+808, waits for timing-thread exit and clears+792.', 'Static xrefs identify a CLR-exported native method; the exact managed caller is separate evidence. Do not call this shutdown API from the trainer.')
claim('11C150', 'Singleton getter may initialize fixed GX at RVA8A0970 and register its destructor if not yet constructed.', 'For readiness inspect the fixed object first; do not use the getter to create missing renderer state.')
claim('113590', 'Graphics PSOs are cached by a16-byte key in the GX+22992 tree and created through117710 only on a cache miss; the resulting COM object is bound to the active command list.', 'A wireframe override without a distinct key/cache policy can silently reuse a solid PSO. Cache mutation requires render-context ownership.')
claim('117710', 'PSO construction writes rasterizer FillMode=3 (SOLID) unconditionally at117946. Cull mode is extracted separately from key bits19..20; there is no fill-mode toggle in that inspected key path.', 'A full wireframe mode would require an audited creation/cache intervention and all relevant passes. No ready scalar or native toggle was found.')
claim('119BA0', 'Native closure dispatcher invokes or records/replays draw operations depending on nested/replay/context state; it owns closures and can capture calls into per-frame vectors.', 'Skipping an arbitrary closure or changing render state outside this scope can break command ordering or ownership.')
claim('126600', 'Fog setter copies CL into the current GX state byte+640 without a global override policy.', 'Known GS/material setters overwrite it per primitive. An after-update write is not a durable no-fog feature; those prior consumers are documented in render_deep.')
claim('162F20', 'Normal single-camera field setup registers group3 tasks at ordered priorities, including camera30000,170450 at43000,1633F0 at49999 and2BD830 at60001.', 'A task named or inferred as drawing can also update visibility lists and resource lifetimes. Do not blanket-disable group3.')
claim('162C20', 'Registers2BD730 as a late group1 priority93000 task and assigns its cleanup callback2BD7C0.', 'This task participates in object cleanup, so suppressing it is not a cosmetic layer control.')
claim('170450', 'ABD472==1 skips the whole function. Otherwise it updates spatial/render bookkeeping, visibility lists and calls1A5490 only when ABD471==0, then completes another native update188770.', 'ABD472 is a broad processing gate; ABD471 is a narrower draw gate but has paired object-state writers. Neither is proven to hide only a particular user-facing layer.')
claim('170FE0', 'Sets ABD471=1, then clears mask4 in render-object flags+280 for manager ABD440 children+35472/+35480. Complete ASM includes the discontiguous1893F0 tail.', 'A direct byte write would omit required companion changes. The manager is scene-owned and must never be reused across teardown.')
claim('171550', 'Sets ABD471=0 and ORs mask4 into both manager children+35472/+35480. Complete ASM includes the189960 tail.', 'This is unconditional re-enable, not restoration of a prior owner value; unsuitable as a generic undo operation.')
claim('189470', 'Spatial registration tests RenderObject+280 mask0xC, handles partition bypass0x1000 separately and recursively processes child objects even when the parent is skipped.', 'Clearing bit4 alone does not guarantee invisibility when bit8 or descendants remain active. It is not a collision toggle.')
claim('16FFA0', 'Scene render initialization resets ABD471/472, allocates the0x8AB0 manager stored at ABD440 and a0xB0 companion at ABD478, then constructs further related scene resources.', 'Resources belong to the loaded scene. Fixed global storage does not make the pointees immortal.')
claim('170340', 'Scene teardown destroys/frees the companion and manager, then clears ABD478/ABD440; related resource globals are also freed and nulled.', 'Never auto-restore an old pointer after scene transition, even if a later allocation reuses the address.')
claim('162540', 'Calls170FE0 then iterates a64-bit active-slot mask, invoking162000 and optional2C65A0 per selected slot.', 'Higher-level hide-like wrappers affect multiple systems beyond the two renderer flags; semantics of all children are not yet complete.')
claim('1625F0', 'Calls170FE0 and walks active slots plus optional effect objects; live effect records can receive2BEBB0.', 'Not approved as a drawing-only action. Its paired resume path has its own state transitions.')
claim('162460', 'Calls171550, iterates active slots through16F400 and can invoke2BEA70 for effect objects.', 'No general baseline restore/ownership policy is provided. Native callers include gameplay transitions.')
claim('162A60', 'Calls171550 and reissues per-slot162060/2C7010 operations.', 'This does more than clear a cosmetic flag and must not be used as unconditional trainer cleanup.')
claim('171500', 'Leaf sets ABD472=1; observed code caller is2DB030.', 'No native symmetric code caller to the clear helper1714C0 was found, so a pause-like toggle cannot be inferred.')
claim('1714C0', 'Leaf sets ABD472=0 and has no observed incoming native xrefs.', 'Retained helper availability does not prove ordinary reachability or supported reversal of every caller state.')
claim('2DB030', 'Performs multiple shutdown/transition calls, waits on a fiber-driven condition and finally sets effect gate through2BE190 plus ABD472 through171500.', 'Its use confirms that the broad render gate participates in transition handling, not just display preferences.')
claim('2BD830', 'When its enable gates permit, traverses the effect list, invokes callbacks, updates effect instances, releases completed instances and marks deletion state.', 'Skipping this task can stop resource cleanup or effect progression; do not label it simply Hide Effects.')
claim('2BD730', 'Late effect traversal frees flagged records through their destructor or marks them for later deletion while honoring additional flags.', 'This is a lifecycle consumer, not a pure draw pass.')
claim('435410', 'Registers the retained debug draw descriptor with menu group2; its labels are BG,OBJ,HIT,ATTACK,RC,BBOX,ZONE,STATUS,TARGET,ALL OFF.', 'Menu labels alone are not evidence that all display modes are implemented in this build.')
claim('435430', 'Index9 clears DWORD749818; other indices toggle indexed mask bits without bounds checking.', 'Never call with an arbitrary host index. Only the known menu domain0..9 is meaningful.')
claim('4384E0', 'Tests bit0 of749818, checks the actor predicate3BA940 and may enqueue a shape via438CC0 using actor+1744. Its only observed xref is CLR/native metadata.', 'No normal native caller was found. The debug-mask menu cannot currently be promised to render collision geometry.')
claim('438CC0', 'Allocates an88-byte debug shape, stores geometry descriptor759190 plus matrix/parameters and appends it to2AF9AC8/2AF9AD0. It accepts field or gummi module states1/3.', '759190 is a data descriptor, not a C++ vtable. Queue allocation and consumer lifetime are not a complete overlay contract.')
claim('438F30', 'Walks the debug shape queue, decrements lifetimes, removes expired nodes, frees an owned descriptor when its+32 byte requests it and returns nodes via41F8F0.', 'This is cleanup, not a draw consumer. No actual draw traversal was established in this round.')
claim('439040', 'Would register debug-shape cleanup438F30 at group0 priority89999, but has no observed incoming native xrefs.', 'Invoking this retained initializer alone does not activate a proven renderer for the shapes.')

contract = {
 'status':'Proposed for review; not implemented or live tested',
 'slot_assignment':'Unassigned. Root reserves272..299 for DamageTuning; this report reserves no renderer slots.',
 'proposed_controls': {
   'brightness':'Brightness preview, integer -50..50',
   'restore':'Restore loaded display settings, explicit one-time action',
   'color_type':'Color-vision preview type, integer0..3',
   'color_severity':'Color-vision preview severity, integer1..10; disabled type emits0'},
 'calls': {
   'brightness':{'rva':'0x5061A0','abi':'void __fastcall(int16_t level); CX','writes':'GX+716,+23360'},
   'color_vision':{'rva':'0x5061F0','abi':'void __fastcall(int16_t type,int16_t severity); CX,DX','writes':'GX+23364,+23368'},
   'mutex_lock':{'rva':'0x43AD04','iat_rva':'0x57B458','abi':'int __cdecl(void* mutex); RCX; MSVCP140 _Mtx_lock'},
   'mutex_unlock':{'rva':'0x43AD0A','iat_rva':'0x57B450','abi':'int __cdecl(void* mutex); RCX; MSVCP140 _Mtx_unlock'}},
 'execution':[
   'Only application-thread post-original-Update execution; original normal return0 and App+4752<0. No worker or UI-thread calls.',
   'Validate exact game build and checked wrapper/getter/import bytes; fixed GX base+8A0970 with vtable base+5A9028, live D3D12 device+736/root signature+1144.',
   'Require GX+1000==current App, GX+808==0, application handle+784 and timing handle+792 nonnull; GetThreadId(application handle)==current thread.',
   'Use the game import/runtime, not a newly constructed mutex or another CRT. Acquire _Mtx_lock(GX+30848); abort without setters if its result is nonzero. Release once in __finally only if acquired.',
   'Revalidate identity, exit and input ranges after locking. Snapshot paired type/severity inside the lock; call preview wrapper exactly once with a complete valid pair.',
   'Do not call any flush/present/upload/PSO helper. Existing memcmp constant upload observes the new values naturally.',
   'Short synchronous command only; native _Mtx_lock can wait for the presentation worker. A bounded try-lock API is not imported or proven in this EXE. This latency tradeoff needs implementation review.'],
 'restore':[
   'No automatic baseline restoration and no per-frame override. The game remains free to apply settings or initialize display resources later.',
   'Explicit restore snapshots signed16 fields at fixed Settings715364+12,+16,+18. Validate brightness-50..50, type0..3, enabled severity1..10 (disabled ignores stored severity and applies0).',
   'Apply immutable validated brightness and type/severity using the two preview wrappers while holding the same native mutex. No config-memory writes or save requests.',
   'A profile stores requested preview values; explicit Apply Profile may issue one-time commands. Disconnect/heartbeat loss cancels pending commands and does not undo an already completed preview.'],
 'readouts':'Number slots should expose observed current values (brightness GX+716*50, type+23364,severity+23368), sampled under the same lifetime/thread/mutex checks. Existing slots192..194 already expose raw gamma/type/severity; do not duplicate separate readouts.',
 'scope_limits':[
   'Display brightness is a final-image gamma adjustment, not lighting, HDR nits or scene exposure.',
   'Localized names for color-vision modes are outside this round. Native mode0..3 and severity1..10 are directly proven.',
   'Mutex protects presentation consistency, not unknown external mods or arbitrary process termination. The proposed lifecycle gates follow the unmodified native startup/update/shutdown contract.',
   'No runtime latency, visual result, device-loss transition, driver or injected-mod compatibility test was performed.']}

tests = [
 'Reject wrong thread, mismatched App/GX, bad vtable/device/root signature, missing handles, stop808, nonnegative App+4752 or shutdown Update result before acquiring mutex.',
 'Reject nonfinite/fractional values and each boundary outside brightness[-50,50], type[0,3], severity[1,10] before any call.',
 'Verify int16 ABI sign extension: -50 -> -1.0 adjustment and 2.2/1.2 gamma;0->1;50->2.2/3.2.',
 'Verify lock failure performs no getter/setter/unlock; successful lock invokes one matching unlock on success, guard rejection and SEH.',
 'Simulate renderer/App/exit-state change between first check and lock acquisition; no setter may execute.',
 'Simulate type0 and enabled-mode changes; pair snapshot must never produce nonzero type with invalid severity or partial settings restore.',
 'Mutate loaded settings after snapshot; restore must use only the validated snapshot and must not reread them between setters.',
 'Check exactly one native preview call per requested group; no repeated effect in Tick, no settings writes, no persistence or renderer flush calls.',
 'Document normal-game settings overriding the preview and explicit restore/profile behavior. This requires later authorized live testing; none was attempted.']

rejected = [
 {'candidate':'Wireframe','reason':'FillMode fixed SOLID3; cached16-byte PSO key omits a selectable wireframe state. Requires a separate keyed PSO policy and render-context interception, not a scalar write.'},
 {'candidate':'No fog / fullbright','reason':'Fog belongs to per-primitive desired state and gets overwritten. Lighting vectors are shader/material parameters; no persistent global override was established.'},
 {'candidate':'Hide background / effects','reason':'Field wrapper gates also change render-object flags, visibility bookkeeping, effect progression and destruction. Additional layer semantic and ownership work is required.'},
 {'candidate':'Native collision/debug overlay switches','reason':'Retained menu and queue helpers exist, but no ordinary caller/draw consumer was established for the mask path. Do not advertise working overlays from their labels.'},
 {'candidate':'Disable arbitrary render tasks / group3','reason':'Tasks include camera, effect lifecycle and resource cleanup. Skipping them can change gameplay/lifetimes, not just pixels.'}]

report = dict(title='Renderer controls: preview contract, synchronization and rejected toggles',
 target_sha256=DATA.get('target_sha256','9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'),
 session='1fc84ea8',date='2026-10-04',scope='Read-only static IDA analysis. Frozen v0.6 sources/reports unchanged. No process/UI/game access.',
 summary='The useful bounded extension is one-time native brightness/color-vision preview with explicit restore of loaded settings. It requires the presentation mutex and application-thread lifetime gates. No ready wireframe, no-fog or layer-isolation toggle was proven.',
 contract=contract,rejected_or_deferred=rejected,test_plan=tests,claims=claims,
 coverage={'fresh_complete_functions':len(functions),'narrow_per_function_claims':len(claims),'instructions':sum(v[1]['disassembly']['instruction_count'] for v in functions.values()),'note':'Fresh exports are supporting evidence, not a count of newly discovered semantics. Existing renderer shader findings are revalidated only where needed for the control contract.'},
 evidence_files=[dict(path=p['file'],sha256=hashlib.sha256((ROOT/p['file']).read_bytes()).hexdigest()) for p in DATA['evidence_manifest']],
 extra_evidence=['work/trainer/research/render_controls_deep_data.json','work/trainer/research/render_deep.json','work/pe/methods_compact.json'])
for c in claims:
    for p in c['Evidence']:
        assert (ROOT/p).is_file(), p
(HERE/'render_controls_deep.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
lines=[report['title'].upper(),'='*76,report['summary'],'',report['scope'],'',
 'PROPOSED CONTROL CONTRACT','-------------------------',contract['status']]
lines += [contract['slot_assignment']]
lines += [f'{s}: {v}' for s,v in contract['proposed_controls'].items()]
for heading,key in [('Execution and lifetime','execution'),('Restore and profiles','restore'),('Limits','scope_limits')]:
    lines += ['',heading]+['* '+x for x in contract[key]]
lines += ['',contract['readouts'],'','ABI']
lines += [f'* {name}: RVA {v["rva"]}; {v["abi"]}' for name,v in contract['calls'].items()]
lines += ['','DEFERRED CONTROLS','-----------------']
lines += ['* '+x['candidate']+': '+x['reason'] for x in rejected]
lines += ['','VALIDATION TO PERFORM','---------------------']+['* '+x for x in tests]
lines += ['','EVIDENCE SCOPE','--------------',json.dumps(report['coverage']),
 'Each evidence file includes addressed pseudocode and dedicated full ASM with instruction_count==total_instructions and cursor.done. Metadata-only xrefs do not establish ordinary native reachability.',
 'The narrow claims below distinguish known behavior from unproved feature semantics.']
for c in claims:
    lines += ['',c['addr'],c['Finding'],'Limit: '+c['Limitations'],'Evidence: '+', '.join(c['Evidence'])]
(HERE/'render_controls_deep.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(report['coverage']))
