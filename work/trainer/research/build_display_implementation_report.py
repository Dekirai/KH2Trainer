"""Rebuild DisplayFeatures implementation metadata; no game/process access."""
import hashlib
import json
from pathlib import Path

here=Path(__file__).resolve().parent
root=here.parents[2]
paths=['trainer/Native/DisplayFeatures.inl','work/trainer/tests/DisplayGuardTests.cpp',
       'work/trainer/tests/DisplayProductionCompile.cpp','work/trainer/tests/build_display_tests.cmd',
       'work/trainer/research/display_features.json','work/trainer/research/display_code_bytes.json']
hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest().upper() for p in paths}
catalog=json.loads((here/'display_features.json').read_text(encoding='utf-8'))
assert [f['CapabilitySlot'] for f in catalog]==[304,305,306]
assert [f['CommandId'] for f in catalog]==[1304,1305,1306]
assert all(not f['RequiresScene'] and not f['ChangesProgression'] for f in catalog)
report={
 'title':'Native display previews: implementation and isolated validation',
 'date':'2026-10-04',
 'target_sha256':'9002B2DE6A1F91A790BD0673DE125D1CF833F7942BFEC827CDCF6BA64D5849ED',
 'scope':'Only the new DisplayFeatures module, its catalog, tests and new research artifacts were written. No shared bridge/Core/UI file, frozen v0.6 artifact, IDB or game process was changed.',
 'files_sha256':hashes,
 'api':['DisplayHandle(const TrainerContext&, unsigned slot, const double args[8], TrainerResult&)',
        'DisplaySnapshot(const TrainerContext&)', 'DisplayCapabilities()',
        'DisplayTick(const TrainerContext&)', 'DisplayReset(const TrainerContext&)'],
 'slots':[
   {'slot':304,'command':1304,'kind':'Number','arguments':'Integer brightness -50..50','snapshot':'Current GX+716 times50, available independently of Sora scene state','profile':'Explicit profile application may issue this one-time preview.'},
   {'slot':305,'command':1305,'kind':'Action','arguments':'None','snapshot':'None','profile':'Not saved in profiles.'},
   {'slot':306,'command':1306,'kind':'Action','arguments':'Integer type0..3 and integer severity1..10; type0 normalizes the native severity to0','snapshot':'None; existing192..194 provide the previously implemented diagnostics','profile':'Not saved in profiles: current profile model stores one scalar per feature.'}],
 'reserved':'307..311 remain unsupported and unpublished.',
 'native_calls':[
   'Brightness preview: RVA5061A0, void __fastcall(int16_t), input CX; downstream1268C0 takes float XMM0.',
   'Color preview: RVA5061F0, void __fastcall(int16_t,int16_t), CX/DX; downstream125D00 takes ECX/EDX.',
   'Game _Mtx_lock/_Mtx_unlock targets are read from IAT57B458/57B450 only after matching the loaded MSVCP140 exports. Original stubs43AD04/43AD0A are byte-checked. Calls use captured verified targets to preserve matching unlock even if the IAT changes.',
   'The mutex receiver is fixed GX8A0970+30848. __finally performs one captured unlock after each successful lock, including a guard rejection or setter SEH. Nonzero unlock status latches this module unavailable until game restart.'],
 'preflight':[
   'Exact supported executable SHA was freshly reconfirmed from disk. Bridge initialization already validates the game build; module pins complete preview/getter/callee bodies and both import stubs, plus native constants50.0 and2.2.',
   'Require bridge enabled, fresh nonzero heartbeat, current game thread, matching base, selected app vtable and a completed singleton epoch (neither0 nor-1).',
   'Require fixed renderer vtable, readable device/root objects, writable preview fields and opaque mutex storage. App global must match GX+1000 and App+4752 must be negative; renderer stop808 must be0.',
   'Application handle+784 must identify the current game thread. Timing handle+792 must identify a distinct live thread belonging to this process.',
   'After acquiring the mutex, repeat all preflight checks and compare app/device/root/thread-handle/runtime-target identities against the original lease. Rejection executes no native preview.',
   'Root OnFrame already rejects original Update results other than0 before dispatch. This was verified in current TrainerBridge.cpp; integration must preserve that gate.'],
 'restore':[
   'Validate loaded SET- header version8 size508. Read brightness/type/severity as signed16 fields at715364+12/+16/+18 into one local plan.',
   'Validate all enabled ranges before either setter. Disabled loaded type ignores its unused stored severity and sends0.',
   'Apply brightness and color once using that immutable plan. No configuration, save, PSO, command-list, upload or presentation helper is written/called.',
   'Tick and Reset are deliberate no-ops. No automatic restoration or ongoing override is registered; normal game settings can replace a completed preview.'],
 'validation':{
   'command':'cmd /c work\\trainer\\tests\\build_display_tests.cmd',
   'compiler':'MSVC x64 /std:c++17 /O2 /W4 /MT /EHsc; no warnings',
   'production_compile':'DisplayProductionCompile.cpp compiled the non-test branches with /c; never linked or executed game addresses.',
   'observed_stdout':['DisplayProductionCompile.cpp','DisplayGuardTests.cpp','DisplayGuardTests: 1633 checks, 0 failures'],
   'source':'Observed tool execution output, recorded here; root release build may create its own separate validation log.',
   'coverage':[
     'All101 allowed brightness levels and all40 input mode/severity pairs; correct native short arguments and one-time behavior.',
     'Boundary, fraction, infinity and NaN rejection before mutex acquisition.',
     'Missing/wrong thread, app, singleton epoch, vtable, device/root, handles, heartbeat, memory/code/constants/imports and pending shutdown.',
     'Changes while acquiring the mutex: renderer resource replacement, stop/exit, runtime IAT, byte signature, host loss and bridge disable.',
     'Successful acquisition always unlocks once; lock failure never unlocks; SEH from either restore setter unlocks without replay.',
     'Unlock failure is reported and permanently gates the module, including after Reset.',
     'Restore validates every field/header before mutation, keeps config bytes unchanged and uses the original snapshot if settings change during the first mocked setter.',
     'Snapshot bounds, unavailable-value omission, static three-slot capabilities and pass-through of unowned commands.'],
   'not_performed':['No live injection or display/game test.','No timing/latency measurement of native mutex waits.','No driver/device-loss or arbitrary-mod compatibility run.']},
 'limits':[
   'Native _Mtx_lock may wait for presentation; no bounded try-lock ABI is introduced. The implementation holds it only across validation, native preview calls or one scalar snapshot.',
   'Exact address reuse without a generation counter is not generally detectable. This module does not retain scene pointers between frames; its native renderer/app identity and stop/thread gates follow the demonstrated application lifecycle.',
   'A fault during the second restore setter can leave brightness already applied. The SEH propagates after unlocking to the bridge exception policy; there is no unsafe retry or rollback.',
   'These are final-image brightness/color-vision previews. Wireframe, fog, background/effect visibility and debug geometry are not implemented by this module.'],
 'evidence':['work/trainer/research/render_controls_deep.json','work/trainer/research/render_controls_deep_data.json','work/trainer/research/display_code_bytes.json']}
(here/'display_implementation.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
lines=[report['title'].upper(),'='*72,report['scope'],'',
       'Slots304/305/306: brightness, restore loaded display settings, paired color-vision preview.',
       'Slots307..311 are reserved. No new render readouts duplicate192..194.',
       'DisplayHandle/Snapshot/Capabilities/Tick/Reset are ready for root integration.']
for key in ['native_calls','preflight','restore','limits']:
    lines+=['',key.upper()]+['* '+x for x in report[key]]
lines+=['','VALIDATION',report['validation']['compiler'],'Production branch compile: success. Isolated harness:1633 checks,0 failures.']
lines+=['* '+x for x in report['validation']['coverage']]
lines+=['* '+x for x in report['validation']['not_performed']]
lines+=['','SOURCE HASHES']+[v+'  '+p for p,v in hashes.items()]
(here/'display_implementation.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'catalog_entries':len(catalog),'source_sha256':hashes[paths[0]],'checks':1633,'failures':0}))
