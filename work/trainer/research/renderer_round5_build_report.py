"""Build only the new round-5 renderer research artifacts; no audit/product edits."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'work/trainer/research'
evidence = {}
raw = {}
for index in range(4):
    path = OUT / f'renderer_round5_evidence_{index}.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    for row in data['functions']:
        pages = row['pages']
        lines = [line for page in pages for line in page['asm']['lines']]
        assert pages[-1]['cursor']['done'] is True
        assert len(lines) == pages[0]['total_instructions']
        assert len({line['addr'] for line in lines}) == len(lines)
        assert int(pages[0]['asm']['start_ea'], 16) == int(row['addr'], 16)
        assert int(lines[0]['addr'], 16) == int(row['addr'], 16)
        evidence[row['addr']] = str(path.relative_to(ROOT)).replace('\\', '/')
        raw[row['addr']] = len(lines)

# Each statement below has been read against the saved full body and its callers.
# Exported functions absent here are raw evidence, not additional semantic claims.
findings = [
('001450', 'Initializes the global QPC frequency at RVA79D088 by QueryPerformanceFrequency.', 'The frequency describes the CPU clock, not GPU timestamp units before calibration.'),
('10a270', 'Constructs six independent doubly linked timeline sentinels at GX+864/880/896/912/928/944 with zero counts; initializes history CS+31392, other renderer critical sections and the presentation mutex.', 'Construction and static epoch initialization do not themselves prove a live render session.'),
('10be40', 'Deletes the history critical section before freeing all six timeline lists; releases framebuffer managers, device references, synchronization objects and window/thread handles.', 'This destructor does not provide a lockable lifetime lease. It must be excluded by the live application-thread contract.'),
('11ad80', 'GX exit sets application exit+4752=256, waits for the application thread to finish, closes its handle, then sets GX+808 and joins/closes the timing thread.', 'A trainer callback executing on the verified application thread can finish before this native join completes. Arbitrary third-party destruction remains outside the contract.'),
('107d00', 'Creates a CPU render-interval list node with two link pointers followed by a 40-byte payload copied from GX+960.', 'Payload timestamps0/1 bracket a native timing/wait section, not the whole application update. Timestamps2/3 are the render-recording interval.'),
('107d40', 'Creates a GPU timeline node with two pointers and a 24-byte payload: calibrated start/end QPC ticks, completion marker and command-buffer tag.', 'The marker is final-fence-in-batch, not a verified whole-game-frame ID.'),
('107d80', 'Creates a submission marker node with two links and a 16-byte payload: QPC timestamp, submission ordinal and backbuffer index.', 'This is a point event; it does not measure a duration or count primitive draw calls.'),
('107db0', 'Creates a Present timeline node with a 32-byte payload after its two link pointers.', 'Only the initialized begin/end ticks and three DWORD fields are meaningful; padding is not a diagnostic value.'),
('107e20', 'Copies a 56-byte timing-worker cycle record into a linked-list node, including six QPC timestamps and a state DWORD.', 'Several optional-phase timestamps are conditional; no general-purpose timing plot should assume every timestamp is refreshed on every cycle.'),
('107e70', 'Creates a wait timeline node with a 24-byte payload after two links: QPC begin/end and a native wait category.', 'The final four bytes are padding, not an extra wait field.'),
('114f10', 'Increments GX+58240 per command submission, records QPC time/old ordinal/current backbuffer in GX+928, and removes the oldest node when the list reaches180.', 'This submission ordinal resets per presented frame and is not a GPU draw counter.'),
('11a510', 'On the first close of a recording interval, flushes pending native recording work, writes QPC end at GX+984, copies GX+960..999 into list+880, caps it at30 and sets interlocked GX+58248=1.', 'The recorded interval includes any elapsed wall-clock time between the boundaries; it is not exclusive CPU execution time.'),
('1231e0', 'Brackets the actual swapchain Present1 call with QPC ticks and records it in list+944 (cap30); stores requested interval and actual/prior backbuffer indices. The real Present interval can be0 despite a nonzero recorded request.', 'CPU time inside Present is not GPU frame time, display latency or monitor scanout duration.'),
('123440', 'Appends a24-byte fence/wait record under the supplied critical section, removes the tail at count200, inserts at the head and releases the lock.', 'It copies caller-supplied data; timestamp/category semantics come from the three concrete callers.'),
('129180', 'Waits for a completed native fence, logs its CPU wait, maps completed command-buffer query pairs, converts GPU timestamps through per-buffer GPU/CPU calibration and frequency into CPU QPC units, appends GPU records (cap300), and feeds the adaptive quality history.', 'Fresh ASM uses signed64-bit subtraction/conversion and float32 arithmetic; misleading DWORD casts in pseudocode are not the ABI. Each list record is a command-buffer span, not automatically a full frame.'),
('129560', 'Signals/increments a fence packet, waits when necessary, and appends a category0 CPU wait record to list+912.', 'This function performs real GPU synchronization and must never be called merely to refresh diagnostics.'),
('127370', 'Shifts a fixed64-float history toward older indices and writes its XMM1 sample to index0.', 'Only caller129180 establishes that the sample is GPU time normalized by59.94/QPC-frequency.'),
('113b80', 'Evaluates the64-sample GPU cost history and a frame-period budget. Low headroom can lower AA quality by two levels; sustained high headroom across30 samples can raise it by one; results are bounded by caller limits. It resets history/counters on adjustment.', 'This is adaptive AA policy, not a generic FPS limiter. The XMM2 floating argument is explicit in caller ASM, although the decompiler inferred an integer at the call site.'),
('119e90', 'Consumes resize requests under resize CS+31432; rebuilds resources after a fence wait when needed. Otherwise maps sample capability to an AA exponent limit, calls113B80 with GX+856 in XMM2 and applies a changed level through114D30.', 'The AMD/vendor flag limits the adaptive exponent to0 on this path. Directly freezing30556 would bypass native resource and replay coordination.'),
('114d30', 'Takes GX inRCX, targetID inEDX and sample exponent inR8B; writes target sample count1<<exponent and recreates existing color/depth resources via11B4F0/11B290 when the count changes.', 'This is a resource-creation operation requiring native context/fence ordering, not a safe one-field trainer setter.'),
('128100', 'Begins a recording interval by clearing per-interval state, capturing QPC start at GX+976 and replay flag at+992; normal frames run resize/adaptive policy, while replay restores historical AA levels.', 'A coherent snapshot may still legitimately describe a replayed sample configuration; quality level and displayed frame identity are not interchangeable.'),
('128260', 'Finishes the native presentation pass, submits command lists, consumes completed GPU timing, rotates frame/context indices, presents, then runs GC on all three framebuffer resource managers.', 'Its synchronization and command submission make it unsuitable for a trainer-triggered refresh.'),
('128470', 'Acquires GX presentation mutex+30848 around close/flush/present, deferred release-ring collection, next recording-interval setup and DummyDraw enqueue; unlocks before the final application call.', 'This proves the native lock order presentation mutex then history CS for snapshots that need both.'),
('1287d0', 'The timing worker acquires the same presentation mutex for interpolated/replayed render work; Present, fence-wait and timing-cycle records are also appended through history CS+31392.', 'The worker can present outside the presentation mutex. History CS remains necessary even after the outer mutex is acquired.'),
('1233d0', 'Mode0 captures QPC at GX+960 and mode1 captures at+968 through the GX singleton.', 'Concrete callers154740/1548E0 bracket timing/wait work; the pair must not be labeled total game logic time.'),
('129630', 'Brackets CThread wait0FDD90 with the same GX+960/+968 QPC fields.', 'This alternate writer further rules out calling the first timestamp pair a pure logic-update duration.'),
('1119b0', 'Clamps requested dimensions to at least1, records requested float dimensions atGX+1080/+1084, passes mutable dimensions/sample capability to heap-budget negotiation, then commits resulting swapchain/render size.', 'Requested dimensions and resulting dimensions may differ after memory-budget fallback.'),
('124b50', 'Caches a framebuffer-heap budget from local adapter Budget minus CurrentUsage minus813694976 bytes, aligned down4MiB; estimates requirements, reserves optional128MiB headroom and reduces sample count or dimensions to fit before creating a replacement heap.', 'This cached budget is neither total adapter VRAM nor continuously refreshed free memory. The unsigned arithmetic can yield implausible values; diagnostics should reject unreasonable magnitudes without claiming a confirmed runtime failure.'),
('117ef0', 'Releases the old heap, stores its requested allocation bytes at owner+16, and creates a default render/depth heap with4MiB alignment and native flags132.', 'The stored byte count is not a verified successful allocation unless the live heap pointer is also present.'),
('1145b0', 'Computes native heap requirements with D3D12 GetResourceAllocationInfo for render/depth descriptions and4MiB-or-driver alignment; uses maximums for aliased regions and adds a fixed2048x1088 color surface.', 'The estimator does not include separately committed frame textures, arbitrary game textures or all GPU memory.'),
('11c2b0', 'Binds framebuffer+264/+272/+280 to fixed RenderTarget/DepthStencil/ShaderResource managers at RVAs89D090/89E300/89F570, initializes each once and sets its concrete vtable.', 'These static addresses outlive active renderer sessions as storage; initialized pointers alone are not a live-session gate.'),
('109e70', 'Initializes the common manager layout:64 records of72 bytes beginning at+8 plus four six-entry tracking-index arrays initialized to-1.', 'The first record COM pointer is manager+8, not manager+0, which contains the manager vtable.'),
('11af70', 'Searches the64 resource records for an exact descriptor key; otherwise uses a free COM-pointer slot, copies the key and tracks the current context through125AA0.', 'Returnsfalse for both existing-key reuse and no-free-slot failure. Its boolean is not a general success flag.'),
('125aa0', 'Associates a pool slot with a live frame-context ownership set, or updates per-target current/sample/history indices when context is null.', 'These ownership references protect old resources across replay and queued GPU work; clearing indices independently is unsafe.'),
('123c60', 'When fewer than10 of64 entries are empty, collects occupied pool slots except swapchain target5, currently tracked target/sample/history slots and records whose context-reference set is nonempty.', 'Occupied entries include cached resources, not only currently bound attachments. Pool occupancy is a count, not a byte estimate.'),
('119630', 'Clears all64 COM resource slots, releases each COM reference, resets descriptor identity/reference tracking and invokes the manager-specific slot cleanup.', 'Callers must have completed appropriate GPU lifetime synchronization; this is not a user cache-purge operation.'),
('117ac0', 'Initializes framebuffer color/sample metadata, reserves a4MiB-aligned placed-resource offset in the shared heap cursor and creates the color target through11B4F0.', 'Dimensions and sample descriptor are resource identity, not independent display-preview variables.'),
('117240', 'Initializes depth clear metadata, obtains a depth resource allocation size, reserves its aligned shared-heap offset and creates depth via11B290.', 'Depth and color sample counts must remain coordinated by the native framebuffer path.'),
('11b4f0', 'Resolves/allocates a color pool slot and creates a placed render-target resource (format87, state4) at framebuffer+144 heap offset, then builds the RTV for that slot.', 'A current framebuffer pointer does not own the COM object alone; the shared manager and context tracking govern lifetime.'),
('11b290', 'Creates/reuses a placed depth-stencil resource (format20, initial state16) at framebuffer+152 and writes the matching depth view descriptor.', 'Its shared pool is separately counted from render-target and frame-texture pools.'),
('11b730', 'Creates/reuses single-sample committed FrameTexture resources in the shader-resource pool (format87, state128) and builds SRVs; non-MSAA auxiliary targets can use an alternate color-pool slot.', 'These textures are outside the placed framebuffer heap, so heap bytes are not total renderer memory.'),
('11dca0', 'Rebinds all three swapchain buffers, retains COM references in the render-target pool, creates RTVs, records resource states and selects buffer0 for the resolve framebuffer.', 'This explains the swapchain resources included in pool occupancy. Their count cannot be equated with user-created targets.'),
('11dad0', 'Rebuilds the previous-frame surface view over all three swapchain buffers; releases old descriptor indices and allocates/newly binds three SRVs.', 'Descriptor indices are allocator-owned and can change across resize. They are not stable texture handles for a trainer.'),
('1253d0', 'Selects direct shader-readable target reuse when supported; otherwise transitions source/destination resources and performs CopyResource for samplecount1 or ResolveSubresource for multisampling.', 'Calling this outside the current command-list/pass can corrupt resource-state tracking; readouts do not invoke it.'),
('124d70', 'Transitions current color/depth/frame-texture slots to their expected states, resets resolve counters and recreates attachments when the framebuffer dimensions change.', 'A width/height write alone omits the barrier and resource-creation contract.'),
('119890', 'Releases previous-frame descriptor indices, asks framebuffers to release their state and clears color/depth pools, optionally preserving the shader-resource pool for resize.', 'This is reached after fence synchronization on resize/shutdown, not a lock-free background cleanup.'),
('115230', 'Shutdown first waits for GPU completion, drains four deferred-destruction ring buckets under CS+31352, frees fixed textures/framebuffers/descriptors and closes fence events.', 'The native presentation/history locks cannot substitute for this GPU completion condition when changing resources.'),
('119a60', 'Enqueues a nonnull renderer resource for deferred destruction in the current four-bucket ring under CS+31352.', 'Resource destruction is delayed; storing a pointer outside its owning scope is not made safe by a readable address.'),
('119b00', 'Obtains the GX singleton and enqueues a second resource-interface class in its parallel four-bucket deferred-release ring under CS+31352.', 'The corresponding collector invokes virtual slot+8, unlike the first ring which invokes slot0.'),
('123990', 'Advances the deferred release index modulo4 and destroys the newly reached bucket from both resource rings under CS+31352, retaining vector capacity.', 'The four-cycle delay participates in native GPU lifetime ordering; it is not a reliable external lease duration.'),
('1276f0', 'Closes the previous recording context, switches/rotates command and constant-buffer rings, releases prior retained references, waits/restarts context and ensures target color/depth/frame-texture resources exist.', 'Frame-context and pass ownership prevent safely exposing this as an arbitrary trainer command.'),
('126670', 'Prepares a framebuffer for shader sampling via recorded checkTexture/setFrameTex closures, marks texture bindings dirty and installs the selected framebuffer/SRV in the active slot.', 'No independent persistent hide-layer or wireframe control follows from this binding operation.'),
('117fd0', 'Performs swapchain creation/resize and reinitializes main, resolve and previous-frame resources using negotiated dimensions/sample capability.', 'This is a full resource rebuild. All proposed round5 values are read-only observations.'),
('1138f0', 'Selects the target-specific applyRenderTarget closure, captures depth/color state and dirty flags, and resets the target resolve-prepared flag.', 'This is per-pass state recorded for deferred execution; changing its globals after an application update would not be a stable render override.'),
('113a40', 'Binds either an ordinary shader-resource descriptor or a special previous-frame texture path according to the surface virtual capability and texture-stage selection.', 'A diagnostic texture viewer would still need a native pass/descriptor lifetime contract beyond this binding function.'),
]

baseline = {}
for line in (ROOT/'work/trainer/audit/function_status.jsonl').read_text(encoding='utf-8').splitlines():
    row = json.loads(line)
    if row.get('domain') == 'native': baseline[row['address'].lower()] = row
claims = []
for rva, finding, limitation in findings:
    addr = hex(0x140000000 + int(rva,16))
    assert addr in evidence, addr
    claims.append({'addr':addr,'Finding':finding,'Evidence':[evidence[addr]],'Limitations':limitation,
                   'baseline_evidence_tier':baseline.get(addr,{}).get('evidence_tier'),
                   'previously_without_concrete_claim':not bool(baseline.get(addr,{}).get('claims'))})

features = [
 (392,'GPU last completed command span','ms','GX+896 list; newest node payload QPC begin/end at node+16/+24',0,10000),
 (393,'CPU Present call time','ms','GX+944 list; newest node QPC begin/end at node+16/+24',0,10000),
 (394,'CPU fence wait time','ms','GX+912 list; newest node QPC begin/end at node+16/+24',0,10000),
 (395,'CPU render recording interval','ms','GX+880 list; newest node render begin/end at node+32/+40',0,10000),
 (396,'Main framebuffer MSAA samples','samples','uint32 GX+1504 (MainFB+160)',1,8),
 (397,'Native MSAA capability','samples','uint32 GX+1108; may be reduced by heap negotiation',1,8),
 (398,'Main framebuffer width','px','int32 GX+1352 (MainFB+8)',1,16384),
 (399,'Main framebuffer height','px','int32 GX+1356 (MainFB+12)',1,16384),
 (400,'Swapchain width','px','int32 GX+8, committed by1119B0 and used by117FD0',1,16384),
 (401,'Swapchain height','px','int32 GX+12',1,16384),
 (402,'Framebuffer heap allocation','MiB','uint64 GX+1312; require live heap GX+1296',0,1048576),
 (403,'Cached framebuffer heap budget','MiB','uint64 GX+1320; native cached budget, not total/free VRAM',0,1048576),
 (404,'Adaptive AA level','level','int32 GX+30556',0,3),
 (405,'Render-target pool entries','entries','fixed pool RVA89D090, vtable5A8B70; count nonnullQWORD(pool+8+72*i),i0..63',0,64),
 (406,'Depth-stencil pool entries','entries','fixed pool RVA89E300, vtable5A8B88; same64-record layout',0,64),
 (407,'Frame-texture pool entries','entries','fixed pool RVA89F570, vtable5A8BA0; same64-record layout',0,64),
]
timeline = [
 {'list_offset':880,'count_offset':888,'capacity':30,'node_bytes':56,'payload_bytes':40,'proposed_slot':395,'begin_offset':32,'end_offset':40,'tag_offset':48,'tag':'native replay flag; require0/1'},
 {'list_offset':896,'count_offset':904,'capacity':300,'node_bytes':40,'payload_bytes':24,'proposed_slot':392,'begin_offset':16,'end_offset':24,'tag_offset':32,'tag':'final-fence-in-batch marker0/1; DWORD+36 command-buffer tag'},
 {'list_offset':912,'count_offset':920,'capacity':200,'node_bytes':40,'payload_bytes':24,'proposed_slot':394,'begin_offset':16,'end_offset':24,'tag_offset':32,'tag':'native wait category0/1 in observed callers'},
 {'list_offset':928,'count_offset':936,'capacity':180,'node_bytes':32,'payload_bytes':16,'proposed_slot':None,'begin_offset':16,'end_offset':None,'tag_offset':24,'tag':'submission ordinal and backbuffer index; point event'},
 {'list_offset':944,'count_offset':952,'capacity':30,'node_bytes':48,'payload_bytes':32,'proposed_slot':393,'begin_offset':16,'end_offset':24,'tag_offset':32,'tag':'requested interval DWORD+32, actual backbuffer+36, prior backbuffer+40'},
 {'list_offset':864,'count_offset':872,'capacity':30,'node_bytes':72,'payload_bytes':56,'proposed_slot':None,'begin_offset':None,'end_offset':None,'tag_offset':64,'tag':'timing-worker cycle; optional-phase timestamps require more state interpretation'},
]
contract = {
 'status':'STATIC_CONTRACT_READY_FOR_REVIEW_NO_PRODUCT_IMPLEMENTATION',
 'image_sha256':'9002B2DE6A1F91A790BD0673DE125D1CF833F7942BFEC827CDCF6BA64D5849ED',
 'database_session':'4e3eb336','database_path':'work/trainer/ida/round5_renderer.i64',
 'slots_reserved_by_root':[392,407],'writes':False,'native_renderer_calls':False,
 'features':[{'Slot':s,'Name':name,'Kind':'ReadOnly','Unit':unit,'Source':source,'Minimum':lo,'Maximum':hi,
             'RequiresScene':False,'CanSaveInProfile':False,'ChangesProgression':False,
             'RestoreBehavior':'Read-only snapshot; no effect is applied or restored.'} for s,name,unit,source,lo,hi in features],
 'roots':{'GX_RVA':'0x8A0970','GX_vtable_RVA':'0x5A9028','epoch_RVA':'0x8AEEF0','App_RVA':'0x79CF00',
          'MainFramebuffer_offset':1344,'MainFramebuffer_vtable_RVA':'0x5A8DA8','presentation_mutex_offset':30848,
          'history_critical_section_offset':31392,'QPC_frequency_RVA':'0x79D088'},
 'lifetime_and_locking':[
  'Execute only inside the existing verified application Update hook on g_gameThread, with matching base, active bridge and fresh host heartbeat. RequiresScene=false does not waive renderer lifetime.',
  'Reuse the Display contract: GX epoch initialized (neither0 nor-1), exact GX vtable, GX+1000 matches current selected App, App+4752<0, GX+808==0, live device/root signature and both native thread handles. App handle must name this callback thread; timing handle must be another live thread in this process.',
  'Capture trusted MSVCP140 _Mtx_lock/_Mtx_unlock via the existing validated IAT/export contract, acquire GX+30848, then repeat all identities/lifetime gates. Epoch is an initialization test, not a generation token.',
  'While the outer presentation mutex is held, validate MainFB identity, exact fixed pool bindings/vtables and copied scalar values. The pool structures are static storage but their contents are valid only within this session gate.',
  'Then TryEnterCriticalSection(GX+31392), which must be writable initialized40-byte storage. If busy, skip timeline values for this snapshot. Native code uses the same outer-before-inner order; no reverse nested path was found in the enumerated writers.',
  'Copy only bounded values into private POD storage; never allocate nodes, retain list pointers, invoke COM, map resources, wait fences, flush or call a renderer getter that constructs the singleton.',
  'Release the history critical section in an inner __finally and the captured outer mutex in an outer __finally. An outer unlock failure latches this diagnostic module unavailable until restart.',
  'Only publish copied valid values after both locks are released; invalid/unavailable fields remain invalid rather than being shown as zero.'
 ],
 'timeline_nodes':timeline,
 'timeline_validation':[
  'Native insertion is at sentinel.next (newest); eviction is sentinel.prev (oldest). A list header contains sentinel pointer and uint64 count.',
  'Require count<=capacity; an empty list has both links equal to sentinel. For nonempty lists, use a fixed visited array bounded by capacity, require exact count nodes followed by sentinel, unique nodes and reciprocal next/prev links; all node spans and the sentinel span must be readable. Do not accept early cycles, short/long chains or a foreign sentinel.',
  'Copy the newest validated record only. The implementation can omit full history IPC; future visualizations may copy a separately bounded record array under the same lock without following pointers later.',
  'Compare global QPC frequency to QueryPerformanceFrequency; require positive frequency. Use signed64 timestamps and double(end-start)*1000/frequency after checked subtraction. GPU records are already CPU-QPC calibrated, so do not apply GPU frequency again.',
  'Conservative diagnostic policy: require0<begin<=end, interval<=10seconds and end no more than10seconds old. Permit at most1second positive GPU-calibration skew relative to current QPC, rejecting larger future values. These are presentation-validation limits, not native engine limits.',
  'Validate initialized tags only; ignore structure padding. The four timing readouts come from different native events and must not be summed or presented as a coherent whole-frame decomposition.'
 ],
 'resource_validation':[
  'MSAA counts must be one of1,2,4,8; adaptive exponent0..3. No forced relation between exponent and current sample count, because replay restores historical state.',
  'Framebuffer dimensions are signed integer fields; use1..16384 as a conservative diagnostic bound. Swapchain values are distinct observations even when they normally equal main framebuffer size.',
  'Heap pointer must be nonnull/readable, allocation/budget uint64 values nonzero,4MiB aligned and at most1TiB as a diagnostic sanity bound. Convert using1048576 bytes perMiB. Never label either number total GPU memory or current free VRAM.',
  'MainFB+264/+272/+280 must equal the three fixed pools with their concrete vtables; require readable common4712-byte span. Count only each of64 COM pointer fields at+8+72*i. Do not dereference or AddRef those COM objects for a count.',
  'Counts include cached and swapchain resources; the shader-resource pool represents frame textures, not every loaded game texture. Pool occupancy is unrelated to exact heap allocation bytes.'
 ],
 'mutating_candidates_not_authorized':[
  'Fixed MSAA:114D30 is proved to recreate resources, but a persistent user override would need integration with resize, memory-budget fallback, replay history30560/30564 and queued command-buffer ownership. A raw30556 or1504 write is not a valid implementation.',
  'Framebuffer/previous-frame viewer: consumers113A40/126670 require current native pass, descriptor and resource-state lifetime. No arbitrary texture-display command is established.',
  'Wireframe, permanent fog disable, fullbright or layer suppression: this round establishes no new safe persistent control beyond the already documented per-pass/PSO behavior.'
 ],
 'tests_required_before_product':[
  'Wrong app/thread/epoch/device/selected vtable/exit flag; state change while locking; inner lock busy; outer unlock failure; exactly-once finally releases with injected read fault.',
  'Empty, one-node and full lists at each capacity; count overflow; null/unreadable sentinel; short/long list, repeated non-sentinel node, broken reciprocal links; only newest record chosen; no pointer retained after release.',
  'QPC zero/mismatch, negative/reversed/overflowing ticks, stale/future timestamps, float32-originated calibrated GPU timestamps and fractional-ms conversion; duration distinctions preserved in names.',
  'Every MSAA value, invalid exponent, independent sample/exponent states, zero/negative/oversized dimensions, aligned/unreasonable heap sizes, each wrong pool pointer/vtable and all0..64 occupancy values.',
  'Poison all renderer function pointers and assert none are called; snapshot changes no game scalar/list/resource byte. OS/runtime lock bookkeeping is the only synchronization mutation.'
 ],
 'limitations':['Static evidence only; no game process or UI access and no live verification.',
                'These are specific semantics for the captured paths, not complete semantics of the whole renderer.',
                'Exact memory reuse by unsupported modifications cannot be excluded by an initialization epoch; the native join/thread contract and exact build are required.',
                'Synchronous outer mutex acquisition can wait for native render work. This proposal does not silently introduce a different runtime try-lock ABI.']
}
report = {
 'scope':'GX adaptive antialiasing, framebuffer/resource lifetime and bounded native timing histories; specific claims only',
 'image_sha256':contract['image_sha256'],'private_idb':contract['database_path'],'session':'4e3eb336',
 'complete_asm_functions':len(raw),'complete_asm_instructions':sum(raw.values()),
 'claimed_functions':len(claims),'previously_without_concrete_claim':sum(x['previously_without_concrete_claim'] for x in claims),
 'claims':claims,
 'raw_evidence_only_addresses':sorted(set(raw)-{x['addr'] for x in claims}),
 'contract':'work/trainer/research/renderer_round5_contract.json',
 'new_findings':[
  'Adaptive AA uses completed GPU timestamp history and recreates target attachments rather than toggling a rasterizer scalar.',
  'Memory-budget fallback can reduce AA capability or negotiated dimensions; cached heap accounting excludes committed frame textures.',
  'Native histories permit bounded read-only timing diagnostics without resource mapping, GPU waits or renderer hooks.',
  'Complete64-bit ASM disproves apparent32-bit timestamp truncation in decompiler output; float32 calibration still limits precision.',
  'The CPU Present interval, GPU command slice, CPU wait and CPU recording span are distinct measurements, not components that can be naively added.'
 ],
 'changes':'New research files only; no product, IDB, executable, game or frozen audit modifications.',
 'evidence_files':[{'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(OUT.glob('renderer_round5_evidence_*.json'))],
 'data_evidence':'work/trainer/research/renderer_round5_data.json',
 'original_byte_verification':'work/trainer/research/renderer_round5_verification.json',
 'limitations':contract['limitations']
}
for name,data in [('renderer_round5_deep.json',report),('renderer_round5_contract.json',contract)]:
    (OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

text = [
 'Renderer round5: adaptive AA, resource lifetime and timing diagnostics',
 '==================================================================',
 f'Fresh private IDB4e3eb336: {len(raw)} complete ASM bodies / {sum(raw.values())} instructions.',
 f'{len(claims)} individually scoped findings; {report["previously_without_concrete_claim"]} addresses had no concrete claim in the frozen0.9 audit.',
 'The remaining captured bodies are raw supporting evidence. Capture coverage is not complete semantic coverage.',
 '', 'Principal result',
 'A16-field read-only renderer diagnostic module is now specified for reserved slots392..407.',
 'It needs the live application-thread lease, native presentation mutex, and inner history critical section.',
 'It never calls a renderer function, maps GPU resources, waits a fence or writes render settings.',
 '', 'New native behavior',
 *['- '+x for x in report['new_findings']],
 '', 'Resource/pass sequence',
 '1119B0 negotiates dimensions/capability ->124B50 computes budget/fallback ->117EF0 creates placed heap.',
 '117FD0 recreates swapchain/main/resolve/previous resources.11B4F0 and11B290 create placed color/depth;',
 '11B730 creates separate committed frame textures.1253D0 chooses direct sample, copy or MSAA resolve.',
 '128100 begins recording ->1138F0/113A40 bind pass resources ->128260 submits/presents/collects cached slots.',
 '123990 drains four-cycle deferred queues; resize/shutdown synchronize GPU completion before119890/115230.',
 '', 'Readout contract',
 *[f'{s}: {name} [{unit}] -- {source}' for s,name,unit,source,lo,hi in features],
 '', 'Timing list ABI',
 'GX+880 CPU record(cap30,node56),+896 GPU(cap300,node40),+912 wait(cap200,node40),',
 '+928 submission(cap180,node32),+944 Present(cap30,node48),+864 timing worker(cap30,node72).',
 'All list headers are pointer/count. Two pointer links precede payload. Newest=sentinel.next; oldest=sentinel.prev.',
 'Full node chain/count/backlinks must be checked under CS+31392 and copied before releasing locks.',
 'GPU timestamps are already converted to CPU QPC by64-bit instructions with float32 intermediate arithmetic.',
 'Use end-begin/frequency for milliseconds, never infer FPS or rescale by GPU frequency again.',
 'Slot395 uses only node+32/+40 (GX+976/+984). Earlier CPU timestamp pair brackets native wait/timing work.',
 '', 'Lifecycle and mutation limits',
 *['- '+x for x in contract['lifetime_and_locking']],
 *['- '+x for x in contract['mutating_candidates_not_authorized']],
 '', 'Per-function evidence',
 *[f"{x['addr']}: {x['Finding']}\n  Evidence: {', '.join(x['Evidence'])}\n  Limit: {x['Limitations']}" for x in claims],
 '', 'Validation status',
 'Complete dedicated ASM pages were mechanically checked for matching totals/start addresses and unique instruction addresses.',
 'All82 contiguous function spans (40647 bytes) and selected vtable spans match the original EXE byte for byte; see renderer_round5_verification.json.',
 'No native guard harness, product code, live experiment or global audit regeneration was performed in this research stage.',
 'See renderer_round5_contract.json for exact bounds, gates, proposed tests and exclusions.',
]
(OUT/'renderer_round5_deep.txt').write_text('\n'.join(text)+'\n',encoding='utf-8')
(OUT/'renderer_round5_contract.txt').write_text('\n'.join(text[:text.index('Per-function evidence')])+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ('complete_asm_functions','complete_asm_instructions','claimed_functions','previously_without_concrete_claim')},indent=2))
