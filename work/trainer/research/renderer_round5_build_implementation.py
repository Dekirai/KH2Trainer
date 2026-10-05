"""Create the renderer diagnostic catalog and implementation report only."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'work/trainer/research'
contract=json.loads((OUT/'renderer_round5_contract.json').read_text(encoding='utf-8'))
details=[
 ('gpu_command_ms','Duration of the newest completed GPU command span, calibrated by the game to the CPU clock. This is one command span, not total GPU frame time.','0x140129180'),
 ('present_cpu_ms','CPU time inside the latest swapchain Present call. Blocking here is distinct from GPU rendering time and display latency.','0x1401231E0'),
 ('fence_wait_ms','CPU time spent in the latest recorded native fence wait. A near-zero value can mean the fence was already complete.','0x140123440 / 0x140129560 / 0x140129180'),
 ('recording_interval_ms','Elapsed CPU-clock time between the native render-recording boundaries. Includes elapsed waits; does not measure exclusive CPU execution.','0x140128100 / 0x14011A510'),
 ('main_msaa_samples','Sample count currently assigned to the main framebuffer. Native adaptive quality and replay can change it.','0x140114D30 / 0x14011B4F0'),
 ('msaa_capability','Current native sample capability used by adaptive quality. Memory-budget negotiation can lower it from the device-supported value.','0x140124060 / 0x140124B50'),
 ('framebuffer_width','Width of the current main framebuffer in pixels. Read separately from the swapchain size.','0x140117AC0 / 0x140124D70'),
 ('framebuffer_height','Height of the current main framebuffer in pixels. Read separately from the swapchain size.','0x140117AC0 / 0x140124D70'),
 ('swapchain_width','Current negotiated swapchain width in pixels. Native memory-budget fallback can reduce the requested dimensions.','0x1401119B0 / 0x140117FD0'),
 ('swapchain_height','Current negotiated swapchain height in pixels. Native memory-budget fallback can reduce the requested dimensions.','0x1401119B0 / 0x140117FD0'),
 ('framebuffer_heap_mib','Allocated size of the live shared framebuffer heap, in binary MiB. Excludes separately committed frame textures and other GPU resources.','0x140117EF0 / 0x14011B730'),
 ('cached_heap_budget_mib','Native cached budget for the framebuffer heap, in binary MiB. This is neither total VRAM nor a live free-memory estimate.','0x140124B50'),
 ('adaptive_aa_level','Native adaptive AA exponent from 0 to 3. Replay can restore earlier sample state, so this value is reported separately from actual MSAA samples.','0x140113B80 / 0x140119E90 / 0x140128100'),
 ('render_target_pool','Occupied entries in the fixed 64-slot render-target resource pool. Includes cached resources and retained swapchain buffers.','0x14011C2B0 / 0x14011DCA0 / 0x140123C60'),
 ('depth_pool','Occupied entries in the fixed 64-slot depth-stencil resource pool. Includes cached resources; this count is not a memory-size estimate.','0x14011B290 / 0x140123C60'),
 ('frame_texture_pool','Occupied entries in the fixed 64-slot frame-texture resource pool. Does not count every game texture.','0x14011B730 / 0x140123C60'),
]
catalog=[]
for f,(identifier,description,addresses) in zip(contract['features'],details):
    slot=f['Slot']
    catalog.append({'Id':'renderer.'+identifier,
        'Category':'Renderer Timing' if slot<=395 else 'Renderer Resources',
        'Name':f['Name'],'Description':description,'Kind':'ReadOnly','CommandId':0,
        'ValueSlot':slot,'CapabilitySlot':slot,'Minimum':f['Minimum'],'Maximum':f['Maximum'],
        'DefaultValue':f['Minimum'],'Step':0.001 if slot<=395 else 1,'Unit':f['Unit'],
        'RequiresScene':False,'ChangesProgression':False,'CanSaveInProfile':False,
        'RestoreBehavior':'Read-only observation. No game effect or setting is applied or restored. Unavailable, stale or invalid measurements are omitted.',
        'Evidence':[{'Address':addresses,'Finding':f['Source'],
                     'Level':'Complete native ASM, original-byte comparison and isolated synthetic guards. Live validation is pending.'}]})
(OUT/'renderer_diagnostics_features.json').write_text(json.dumps(catalog,indent=2)+'\n',encoding='utf-8')
paths=['trainer/Native/RendererDiagnostics.inl','work/trainer/tests/RendererDiagnosticsTests.cpp',
       'work/trainer/tests/build_renderer_diagnostics_tests.cmd','work/trainer/research/renderer_diagnostics_features.json']
hashes=[{'path':p,'sha256':hashlib.sha256((ROOT/p).read_bytes()).hexdigest()} for p in paths]
report={
 'status':'FROZEN_SOURCE_TESTS_AND_INDEPENDENT_REVIEW_COMPLETE',
 'scope':'v0.10 read-only renderer diagnostics, reserved slots392..407',
 'source_contract':'work/trainer/research/renderer_round5_contract.json',
 'independent_contract_review':'work/trainer/research/gummi_round5_renderer_contract_review.json',
 'source_hashes':hashes,
 'interfaces':['RendererDiagnosticsSnapshot(const TrainerContext&)',
               'RendererDiagnosticsCapabilities()', 'RendererDiagnosticsReset(const TrainerContext&)',
               'RendererDiagnosticsFailureReset(const TrainerContext&)'],
 'integration':['Include RendererDiagnostics.inl after DisplayFeatures.inl; shared Display Ready/Lease/Same and runtime mutex validation are dependencies.',
                'Call RendererDiagnosticsCapabilities during capability initialization and RendererDiagnosticsSnapshot during snapshot publication.',
                'Call RendererDiagnosticsReset for ordinary disconnect/disable; it intentionally does nothing. FailureReset latches the module unavailable without touching game memory.',
                'No command dispatch or Tick is required. Merge research/renderer_diagnostics_features.json through the root-owned catalog assembler.',
                'Add build_renderer_diagnostics_tests.cmd to the root-owned test pipeline. It compiles the production branches separately and runs only the synthetic fixture.'],
 'implementation_details':[
  'Reuses existing Display lifetime/code/IAT gates, including its conservative preview-related code pins. No preview or renderer setter is invoked.',
  'Acquires native presentation mutex30848, revalidates captured app/device/root/threads, checks current MainFramebuffer vtable and all three exact pool bindings/vtables.',
  'Copies scalar/resource diagnostics under the outer mutex. Under TryEnterCriticalSection31392 it validates every node of each of the four selected lists, bounded by native capacities300/30/200/30, before accepting the newest payload.',
  'Both lock releases use finally. Output publication happens only after both releases. Read exceptions latch this module unavailable. An unsuccessful or exceptional outer unlock also latches the existing Display component, since both use the same mutex. These latches persist until restart; ordinary Reset cannot clear them.',
  'Samples the QPC comparison clock only after capture, under both locks. Requires agreement with the game QPC frequency; preserves64-bit subtraction before double millisecond conversion.',
  'Accepts at most10-second intervals/age and1-second positive GPU calibration skew as explicit diagnostic policies. CPU future timestamps are rejected. Present requested interval is conservatively bounded0..4; backbuffer indices0..2; unused padding is ignored.',
  'Scalar bounds are explicit diagnostic policies: signed32-bit dimensions1..16384; sample counts1/2/4/8; AA exponent0..3; unsigned64-bit heap fields nonzero,4MiB aligned and at most1TiB. Heap allocation and cached native budget are separate quantities, neither total VRAM nor current free memory.',
  'Invalid individual scalar/time values are omitted. A busy history CS omits four timing values while retaining the twelve resource observations. Structural pool/lifetime corruption discards the full snapshot.',
  'No borrowed pointers survive capture. Pool occupancy counts nonnull references without dereferencing COM objects. There is no game-code, GPU map, fence wait, settings write or profile action.'
 ],
 'tests':{'command':'work/trainer/tests/build_renderer_diagnostics_tests.cmd','checks':21962,'failures':0,
          'warnings':0,'production_branch_compile':True,'compiler_options':'MSVC /std:c++17 /O2 /W4 /MT /EHsc',
          'log':'work/trainer/tests/renderer_diagnostics_test_run.log','execution':'Synthetic allocated memory only, no game process or game code executed.',
          'coverage':['All list lengths through each capacity, newest-vs-oldest selection, malformed sentinels/counts/backlinks/cycles/foreign endpoints, inaccessible last bytes and pointer overflow boundaries.',
                      'Lifetime/code/runtime mismatches before and during lock wait; device replacement; busy inner lock; SEH before and inside inner capture; exact release order; unlock failure/exception latch shared with Display, plus blocked Display snapshot and command retries.',
                      'Post-wait QPC freshness, immutable record copies, frequency mismatch/failure, large absolute timestamps with small deltas, signed bounds,10-second limits and GPU-only future tolerance.',
                      'All valid sample counts, replay-independent exponent, separate dimension and heap bounds, binary MiB scale, all pool occupancies0..64 and poisoned COM pointers.',
                      'Capability bits exactly392..407, publication after release, reset/failure reset behavior and whole-fixture byte equality.']},
 'independent_implementation_review':'Completed by /root/managed_tools with no remaining blocking finding. See work/trainer/research/renderer_round5_implementation_review.json and .txt. Parent separately reviewed the shared-mutex fault-latch fix.',
 'limitations':['No live rendering validation.',
                'Time series describe different events and must not be added into a whole-frame total or treated as FPS.',
                'Outer mutex acquisition can wait for native render work. Exact thread/join lifetime follows the reviewed native build, not arbitrary replacement renderer modules.',
                'The reused initialization epoch is not a generation token. Existing Display gates are deliberately preserved rather than edited in shared code.']
}
(OUT/'renderer_round5_implementation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
lines=['Renderer diagnostics implementation','===================================',
       'All16 read-only slots392..407 are implemented. No shared source file was edited.',
       'Own isolated tests:21962 checks,0 failures; production/test branches compile /W4 without warnings.',
       'No live game, GUI, save or complete product-build action was performed.',
       '', 'Integration',*['- '+x for x in report['integration']],
       '', 'Behavior and safety gates',*['- '+x for x in report['implementation_details']],
       '', 'Validation',*['- '+x for x in report['tests']['coverage']],
       'Log: '+report['tests']['log'],
       '', 'Independent implementation review',report['independent_implementation_review'],
       '', 'Limitations',*['- '+x for x in report['limitations']],
       '', 'Source hashes',*[x['path']+' '+x['sha256'] for x in hashes]]
(OUT/'renderer_round5_implementation.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'features':len(catalog),'hashes':hashes},indent=2))
