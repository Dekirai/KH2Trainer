import json, pathlib, re, hashlib, collections

ROOT=pathlib.Path(__file__).resolve().parents[3]
OUT=ROOT/'work/trainer/research'
BASE=0x140000000
raw=[]
for name in ['render_deep_evidence_full.json','render_deep_evidence_additional.json','render_deep_evidence_pagination.json']:
    raw += json.loads((OUT/name).read_text(encoding='utf-8'))
raw={r['addr'].lower():r for r in raw}
def hx(s): return hex(int(s,16))
claims=[]
def claim(addr,name,finding,limitations='Static evidence only; no game execution or renderer writes were performed.'):
    addr=hx(addr)
    assert addr in raw,addr
    rec=raw[addr]
    assert rec['pc']['cursor']['done'] and rec['asm']['cursor']['done'],addr
    claims.append(dict(Address=addr,Name=name,Finding=finding,Evidence=[
        'render_deep_evidence_full.json or render_deep_evidence_additional.json: matching addr; complete ASM. For 1121D0/11E1D0 complete pseudocode pages are in render_deep_evidence_pagination.json.',
        f"ASM instructions: {rec['asm']['total_instructions']}"],Limitations=limitations))

core={
'11C150':('GX singleton','Returns the fixed GXDeviceImpl object at VA 0x1408A0970 after C++ thread-safe local-static initialization. Calling this getter before startup can construct the renderer; read-only diagnostics should inspect the fixed object instead.'),
'10A270':('GX ownership initialization','Writes GXDeviceImpl vtable 0x1405A9028, clears D3D12 device at +736 and frame serial +816, creates MainFrameBuffer at +1344, ResolveFrameBuffer at +1632, four other targets at +1960 with stride288, and PrevFrameBuffer at +3112. Initializes command/context/upload containers.'),
'109F50':('GX state defaults','Initializes the 728-byte state block whose receiver is GX+8 in 10A270. The offsets in this function therefore require +8 when interpreted relative to GX; it sets cached/dirty flags and default blend/depth/texture state.'),
'11DF90':('D3D12 root signature','Creates seven root parameters: root0 VS CBV b2; root1 VS CBV b3; root2 VS CBV b4; root3 PS CBV b6; root4 PS sampler descriptor table s0; roots5/6 PS SRV descriptor tables t0/t1. Uses D3D12SerializeRootSignature v1, allows input-assembler layout, and stores the created root signature at GX+1144.'),
'1100E0':('Root signature bind closure','Loads GX from closure+8, gets the active command list, calls SetGraphicsRootSignature at vtable+240 with GX+1144, and SetDescriptorHeaps at +224 with two heaps (SRV manager heap and sampler heap).'),
'11E1D0':('Embedded shader registration','Loads all21 pixel shaders into GX+31560+8*pixelIndex using D3DStripShader flags0. Builds 552-byte shader-program records beginning GX+31736, pairing vertex blobs with pixel blobs and input layouts. Program45 is movie YUV,46 plain texture copy,47 final gamma/color-vision presentation. shader_programs.json contains the recovered mapping.'),
'111830':('Shader program registration helper','RCX GX; RDX layout descriptor {int elementCount,int vertexStride,ptr elements}; R8D programId; R9 ptr{shaderBytes,int size}; stack pixelIndex,flags,textureCount. Record is GX+31736+552*programId: VS+0,PS+8,stride+16,flags+20,textureCount+24,32-byte input descriptors+32,count+544. Does not range-check IDs or counts.'),
'1121D0':('Apply pending GX draw state','Compares desired/current render state, applies viewport, target/depth, textures, sampler descriptors, scissor, blend factor/stencil, uploads changed constants via111AE0 and binds a keyed PSO via113590. It increments GX+58244 on entry and GX+22936 on success. The first counter is also incremented by clear paths and must not be labeled draw calls.'),
'111AE0':('Upload shader constants','Copies changed CPU mirrors to persistently mapped upload memory and calls SetGraphicsRootConstantBufferView at command-list+304. Root0:GX+23008 size144; root1:GX+23464 max3456, shader-dependent prefix; root2:GX+30380 size64 or interpolated camera; root3:GX+23300 size80. Each reservation is aligned to256bytes. Returns false if upload capacity is exhausted.'),
'11AA80':('Shader parameter change detection','Compares current/previous 3456-byte shader-parameter blocks when dirty. The mask points to byte counts for leading float4 vectors, LocalProjection matrices at +384, and matrices at +128. Supports full-block comparison when mask=-1; updates cached copies and dirty-result bytes.'),
'11CF50':('Constant-buffer resource allocation','Creates an UPLOAD-heap buffer of size elementSize*count through ID3D12Device::CreateCommittedResource, initial state2755 (GENERIC_READ), names it ConstantBuffers and maps it persistently. Resource at receiver+0,mappedCPU+8,elementSize+16,count+24.'),
'113590':('PSO lookup/cache','Searches a tree keyed by a16-byte packed render-state descriptor, creates a missing PSO via117710, retains it in the cache, then calls command-list SetPipelineState (+200). COM references are balanced around cache insertion/use.'),
'117710':('Create graphics PSO','Unpacks shader ID from key.low7bits, blend/depth/stencil/cull/topology/sample state into a D3D12_GRAPHICS_PIPELINE_STATE_DESC, fetches VS/PS blobs from the552-byte shader-program record, and calls ID3D12Device::CreateGraphicsPipelineState (+80). Rasterizer FillMode is unconditionally3 (SOLID); a native wireframe toggle is not established.'),
'11A1B0':('DrawInfo submission ABI','RCX DrawInfo, RDX ID3D12GraphicsCommandList*. Sets topology from receiver+28; GPU base from virtual slot0. Vertex buffer uses stride+8,count+20,offset+24. If indexCount+12>0, binds index buffer at offset+16 with DXGI_FORMAT_R16_UINT57 and issues DrawIndexedInstanced(indexCount,1,0,0,0); otherwise DrawInstanced(vertexCount,1).'),
'11A660':('Mesh draw wrapper','RCX DrawInfo*. Obtains GX, requires a selected PS blob, records drawVertexBuffer, applies state; on constant-upload failure increments GX+58232, flushes, starts a new command buffer and retries. Finally dispatches DrawInfo virtual+16 with the active D3D12 command list.'),
'11A330':('Transient draw submission','RCX GX, EDX vertexCount,R8D topology,R9D mode. Finalizes transient DrawInfo through127EF0, applies GX state, flushes/retries on constant-buffer exhaustion, then dispatches virtual+16. Nonpositive count clears/updates transient bookkeeping without drawing.'),
'111970':('Transient vertex allocation wrapper','ECX vertexCount,EDX vertexStride,R8D forwarded reserved argument; obtains GX and forwards to121FF0. The current callee consumes count and stride, reserving count*(stride+6) with4-byte alignment.'),
'121FF0':('Transient vertex allocation','Selects current deferred or main frame vertex arena, reserves vertexCount*(vertexStride+6), returns CPU memory or flushes/restarts and retries when out of capacity. Counts this recovery at GX+58236. A second failure can still return NULL.'),
'11A2F0':('Transient draw public wrapper','ECX vertexCount,EDX topology,R8D mode are preserved across the singleton getter and forwarded to11A330 as EDX/R8D/R9D. The fourth pseudo argument is not an additional meaningful draw parameter.'),
'115E40':('Surface copy with barriers','RCX destination Surface,RDX command list,R8 source Surface. Transitions source to COPY_SOURCE2048 and destination to COPY_DEST1024 through ResourceBarrier(+208), calls CopyResource(+136), transitions destination to PIXEL_SHADER_RESOURCE128 and restores the original source state. Receiver virtual+40/+48 identify destination resource/state; source virtual+24/+32 identify source resource/state.'),
'127AF0':('Begin/restart GX command recording','Selects a fresh or deferred command buffer, records/restores framebuffer dimensions, binds root signature/heaps through1100E0, obtains GPU/CPU calibration data, and forces cached state dirty. This mutates recording state and is not safe as an arbitrary trainer refresh call.'),
'128100':('Begin render frame','Resets target/depth selectors, clears both constant/vertex exhaustion counters at+58232/+58236, sets performance timestamp, resets per-camera interpolation slots and calls127AF0. On a normal frame also resets+58244. Replayed/interpolated frames follow a different branch.'),
'1219F0':('Final presentation pass','Selects a current or previous frame source, transitions the active swap-chain buffer to RENDER_TARGET4, schedules fillScreen(target5,program47,...), returns the buffer to COMMON/PRESENT0 and flushes. Gamma and accessibility operate at this final pass, after scene drawing.'),
'11AEF0':('Fullscreen pass enqueue','RCX GX,EDX targetId,R8D programId,R9 primarySurface,stack secondarySurface. Captures these into the fillScreen closure and queues/runs it through119BA0. Native callers must establish resource/command state first.'),
'128260':('Render-frame completion','Finalizes current target, calls presentation pass1219F0, logs submission timing, executes command lists via121470, resolves timestamp history via129180, advances resource-ring indices and frame serialGX+816, and retires framebuffer resources. Does not itself justify a universal FPS measure.'),
'120ED0':('Interpolated replay frame','Sets GX+22944 replay mode, constructs two interpolated camera matrices from current/previous data, begins a render frame, invokes saved command closures, ends the frame and clears replay mode. This explains why render callbacks/constant state can be replayed independently of simulation ticks.'),
'114F10':('CPU submission history','Increments GX+58240, captures QueryPerformanceCounter with current frame and submission index, appends a record to a critical-section-protected history, retaining at most180 records. It is a submission counter, not polygon count.'),
'129180':('GPU timestamp history','Waits/tests completion and maps timestamp readback resources, converts GPU timing through calibration and performance-counter frequency, updates pacing measurements, and appends bounded history under GX+31392 critical section. Raw linked-list traversal from a trainer needs this ownership protocol.'),
'126600':('Set per-draw fog enable','ECX low byte is copied to GX+640. Apply1121D0 writes it to cbConstantVS+52 at GX+23060. GS decoders472DA0/472E90 set it from primitive bit0x20, so the next material/primitive can immediately overwrite it.'),
'125F00':('Shader-vector setter','ECX selector,RDX float4*,R8D arrayIndex. Selector4097 writes Ambient atGX+23480;4098 writes FogParam at+23496;8192 writes FogColorRGB at+23348. Other selectors writeGX+23464+16*(selector+arrayIndex). No bounds checking; do not expose arbitrary selectors.'),
'126540':('GS fog-color adapter','Takes packed RGB in ECX, extracts low3bytes, converts/scales through13FCC0, writes FogColor at GX+23348. This is color for fogged pixel shaders, not a global lighting field.'),
'472DA0':('Packed GS primitive state','Decodes packed primitive flags subject to top-bit/control gates, then calls texture enable127350,fog enable126600,alpha/color mode125C80 and texture-coordinate mode1271A0. Fog enable is extracted from primitive payload bit0x20 after shifting47.'),
'472E90':('Unpacked GS primitive state','RCX points to primitive-state word; calls texture enable frombit0x10, fog enablefrom0x20, color/alpha modefrom0x40 and coordinate modebit0x100. These material-level updates make an isolated post-update fog write unreliable.'),
'125D00':('Set color-vision shader constants','ECX type,EDX severity are copied to GX+23364/+23368 (PS constant offsets64/68). No range clamp in this low-level setter; the shader uses type/severity to index a matrix table.'),
'1268C0':('Set gamma adjustment','Input is float in XMM0 (confirmed ASM). Writes adjustment atGX+716 and inverseGamma=2.2/(adjustment+2.2) atGX+23360. Values at/below -2.2 are invalid for a sensible gamma exponent; use the native settings path/range for controls.'),
'5061C0':('Apply stored brightness','Fetches settings via14CDE0, sign-extends int16 atoffset12, divides by50.0 and calls1268C0 with floatXMM0. Merely changing renderer gamma does not update persisted settings.'),
'506240':('Apply stored color-vision setting','Fetches int16 settings type at+16 and severity at+18. Disabled type uses(0,0); enabled severity is clamped1..10 before125D00. This wrapper does not clamp the type.'),
'5309C0':('Developer font initialization/bind','Lazily creates and caches a128x128 indexed font texture using16-entry embedded paletteVA1407848C0 and8192-byte imageVA140784900, renderer pointer1408AEEF8, cache142B58DA0. Sets GS texture/depth/blend state for debug drawing. Initialization is tied to a valid render context.'),
'5303F0':('Developer glyph packet generation','ECX x,EDX y,R8 pointer to4int color,R9 zero-terminated text. Produces packed sprite packets; uppercases ordinary glyphs, supports newline, inline@RGBdigits and escaped glyphs, advances9pixels per glyph/line, sends through534080. Not Unicode text rendering and no bounded external string API.'),
'533D40':('Developer packet to PC quads','Converts a GS sprite packet into four28-byte PC vertices per glyph/quad. Calls472DA0, selects program3 via127030, allocates4*count vertices using111970, converts12.4fixed positions/UVs, then calls11A2F0(4*count,6,2). This connects the retained desktop renderer to the same GX pipeline.'),
}
for suffix,(name,finding) in core.items():claim(hex(BASE+int(suffix,16)),name,finding)

leaf={
'115CD0':'Forwards destination/source copy arguments to115E40, then resets receiver+96 to0.',
'119510':'No-operation callback (return only).','119520':'No-operation callback (return only).','119550':'No-operation callback (return only).',
'119530':'If receiver is nonnull, calls its virtual destructor at+8 with deleteFlag1.','119560':'If receiver is nonnull, calls its virtual destructor at+8 with deleteFlag1.',
'119580':'Releases/retire-marks framebuffer allocations through123860, clears cached resource indices to-1, optionally also releases SRV allocation, then calls virtual+88 cleanup.',
'1196B0':'Runs embedded resolve-framebuffer virtual+80 at receiver+288, then ordinary framebuffer cleanup119580.',
'11BEC0':'Returns backing resource pointer from RenderTargetManager+8+72*receiver.index32.',
'11BEE0':'Forwards resource getter to receiver virtual+24.',
'11C0F0':'Returns SRV descriptor index from receiver.manager280+4712+4*index48.',
'11C110':'Returns previous-frame descriptor index from receiver+48 using owner+324 frame-ring index minus1, adjusted by3 when negative.',
'11C130':'Returns zero descriptor index for staging/region surface.','11C140':'Returns texture descriptor index uint32 atreceiver+64.',
'11C720':'Returns framebuffer dimensions from+8/+12; when scaling fields+104/+120 are enabled, rescales byGX scale,+116 and reference sizes+132/+136, truncating toint. No zero-denominator guards in the enabled branch.',
'11C810':'Copies raw uint64 width/height pair fromreceiver+8 toRDX output and returns output pointer.',
'11CD50':'Selects a framebuffer backing resource: render-target allocation when indices+48/+44match and not-1, otherwise shader-resource allocation. Both managers use72-byte slots.',
'11CD90':'Returns previous-frame resource from owner+288+8*previousRingIndex, owner pointeratreceiver+40.',
'11CDC0':'Returns resource pointer atreceiver+32.','11CDD0':'Returns resource pointer atreceiver+40.',
'11CE10':'Calls ID3D12Resource::GetGPUVirtualAddress(+88) for Mesh resourceatreceiver+48.',
'11CE20':'Calls ID3D12Resource::GetGPUVirtualAddress(+88) for VertexResource atreceiver+40.',
'1212F0':'Returns1 to identify the previous-frame surface special path.','121300':'Returns0 for ordinary surface path.',
'1213D0':'Appends command pointer receiver+16 into destination vector+16 when requested selector<=0 or equalsreceiver+8; grows vector on capacity exhaustion.',
'121420':'Iterates a vector of child command lists and calls each virtual slot0 with selector-1.',
'121610':'Iterates the referenced command-list vector and calls each virtual slot0 with the partial-list selectoratreceiver+16.',
'1237A0':'Returns address of resource-state uint32 at RenderTargetManager+16+72*index32.',
'1237C0':'Forwards state-address getter to receiver virtual+32.',
'1237D0':'Returns selected framebuffer resource-state address; same index-selection rules as11CD50 but points to manager slot+16.',
'123810':'Returns previous-frame resource-state address in owner ring atowner+312+4*previousRingIndex.',
'123840':'Returns receiver+40 as state-field address.','123850':'Returns receiver+68 as texture state-field address.',
'124840':'No-operation manager cleanup callback.','124890':'No-operation framebuffer cleanup callback.',
'124850':'Frees an SRV descriptor allocator bit for manager.slotIndices[a2], then sets that index to-1. Requires a valid index and owning allocator.',
'1248A0':'Releases and clears the three cached COM references at receiver+576,+584,+592.',
'471A3C':'Tail jump to CRT _purecall; abstract GX table entries are not callable implementations.'}
for s,f in leaf.items():claim(hex(BASE+int(s,16)), 'GX virtual slot',f)
vts=[v for v in json.loads((ROOT/'work/native_index/vtables.json').read_text()) if 'GX' in v['name']]
known={c['Address'] for c in claims}
for addr in sorted({a for v in vts for a in v['slots']}-known):
    code=raw[addr]['code']
    assert 'j_j_free(' in code,addr
    membership=[v['name'] for v in vts if addr in v['slots']]
    direct=sorted(set(re.findall(r'(?:sub_|kh2_)[A-Za-z0-9_]+\(',code)))
    claim(addr,'GX scalar deleting destructor','Deleting-destructor wrapper for '+', '.join(membership)+'. If deleteFlag lowbit is1 it calls j_j_free(receiver); otherwise it returns after local destruction. Direct helper calls: '+', '.join(direct)+'.','This finding covers deletion dispatch only. It does not claim every transitive allocator/resource operation has been audited.')

ps={
'59AF60':'Samples texture0, optionally replaces texture alpha when PSFLAGS bit24 is set, multiplies vertex RGBA, and executes PSFLAGS-controlled alpha testing.',
'59B6A0':'Uses texture red*1.9921875 as alpha (or external alpha), fixed RGB128/255 multiplied by vertex color, then alpha test.',
'59BE20':'Replicates texture green into RGB, uses sampled/external alpha, multiplies vertex RGBA and alpha tests.',
'59C580':'Computes grayscale with the literal RGB weights(0.299,0.596,0.211), multiplies vertex color, then alpha tests. These unusual coefficients are recorded exactly; they are not normalized Rec.601.',
'59CCF0':'Outputs interpolated vertex RGBA with optional PSFLAGS alpha test, without any texture sampler.',
'59D320':'Implements four texture samples around the half-texel grid with explicit U/V region repeat/clamp rules and bilinear interpolation, then modulates vertex color and alpha tests.',
'59E300':'Samples12 neighboring texture positions using reciprocal RegionU.z/RegionV.z, averages them with1/12 and vertex modulation, then alpha tests. This is a blur/filter variant, not proof of a global antialiasing mode.',
'59EF30':'Texture*vertex RGBA, alpha test, then RGB=(1-fog)*FogColor+fog*RGB using interpolated TEXCOORD0.z; alpha unchanged.',
'59F710':'Grayscale texture with exact weights(0.299,0.596,0.211), vertex modulation, alpha test and interpolated fog-color blend.',
'59FF10':'Texture*vertex RGBA and optional alpha test; no fog or external-alpha override.',
'5A0640':'Discards fragments with modulated alpha<=1.001953125, subtracts1from remaining alpha, applies alpha test and fog. This is one side of a split alpha-range pass.',
'5A0E70':'Texture*vertex RGBA and optional alpha test; instruction stream is equivalent to59FF10 although the embedded blob is separate.',
'5A15A0':'Discards modulated alpha>1.001953125, clamps surviving alpha to1, applies alpha test and fog: complementary low-alpha pass to5A0640.',
'5A1DC0':'Texture*vertex RGBA, alpha test and fog; instruction stream matches59EF30.',
'5A25A0':'Texture*vertex RGBA and optional alpha test; instruction stream matches59FF10.',
'5A2CB0':'Pure vertex-color pass-through: mov o0,v0;ret. No resources/constants or alpha test.',
'5A2E80':'Textured fog variant with optional external-alpha override before vertex modulation, alpha test and fog blend.',
'5A3690':'Interpolates samples from texture0 andtexture1 by multiTextureAlpha, then applies external-alpha override, vertex modulation, alpha test and fog.',
'5A3F40':'Plain texture-copy pixel shader: one texture sample directly to output, ignoring vertex color.',
'5A41B0':'Two-plane film shader: reads Y fromtexture0 andUV fromtexture1, subtracts Y1/16 andUV1/2, converts toRGB with coefficientsR(1.1644,1.7927),G(1.1644,-.2133,-.5329),B(1.1644,2.1124), sets alpha1.',
'5A4550':'Final presentation shader samples texture0, raises RGB to inverseGamma using log/mul/exp, then optionally applies type/severity-indexed color-vision matrix operations; alpha follows the sampled texture. Index parameters require bounded values.'}
vs={
'586160':'2D textured sprite VS: scales UV byTPage, RGBA bycolorScale/alphaScale, subtracts xyOffset, appliesMagicScale, snaps xy byceil(x-0.5), maps toclip coordinates and reversesY.',
'586710':'2D textured sprite VS with the same color/UV/projection fields as586160 but without ceil pixel-grid snapping.',
'586C80':'2D untextured color VS with ceil(x-0.5) pixel-grid snapping; no UV output or sampler dependency.',
'5871B0':'Accepts float4POSITION plusUV andCOLOR, applies 2D offset/scale and color scaling, with conditional clip-position logic; unlike586160 it does not use pixel-grid rounding.',
'58ED60':'Single-index untextured skinning path: matrix index comes from BLENDINDICES.y, LocalProjection matrix thenWorldView/ViewProjection transform; output color isAmbient scaledRGB128/255.',
'58F650':'Six-weight skinned textured path: six BLENDWEIGHT inputs and six indices select/sum LocalProjection transforms, thenWorldView/ViewProjection. Output color derives fromAmbient; NORMAL is declared but unused in this shader.',
'592D00':'Six transformed POSITION vectors with six matrix indices are summed through LocalProjection[48], thenWorldView/ViewProjection; outputsAmbient color withoutUV.',
'59AC40':'Generates fullscreen quad clipXY andUV solely from SV_VertexID bit0andshift1; outputs zero color and z0/w1. No vertex buffer inputs or constants needed.'}
shaders=[]
for item in json.loads((ROOT/'work/pe/shader_inventory.json').read_text()):
    addr=item['va'];p=ROOT/pathlib.Path(item['disassembly'].replace('\\','/'));t=p.read_text();profile=item['profile']
    code=t.split('\n'+profile,1)[1]
    buffers={};current=None
    for line in t.splitlines():
        m=re.match(r'// cbuffer (\w+)',line)
        if m:current=m[1];buffers[current]=[]
        m=re.match(r'//\s+(float\w*|uint)\s+(\w+(?:\[\d+\])?);\s+// Offset:\s*(\d+) Size:\s*(\d+)(.*)',line)
        if m and current:buffers[current].append(dict(type=m[1],name=m[2],offset=int(m[3]),size=int(m[4]),used='unused' not in m[5]))
    suffix=hex(int(addr,16)-BASE)[2:].upper()
    finding=(ps if profile.startswith('ps') else vs).get(suffix)
    if finding is None:
        assert profile.startswith('vs')
        indexed='dynamicIndexed' in code
        used=[b['name'] for values in buffers.values() for b in values if b['used']]
        finding=('Vertex shader computes transformed output using '+', '.join(n for n in used if 'Matrix' in n or 'Projection' in n or 'WorldView' in n)+'. '+('Uses dynamically indexed constant-buffer matrices. ' if indexed else 'Uses fixed-index constant-buffer reads. ')+('FogEnable is consumed in this variant. ' if 'FogEnable' in used else 'FogEnable is declared unused in this variant. ')+('Normal/light math consumes LightMatrix. ' if 'LightMatrix' in used else '')+'Detailed material/boss-specific use remains unassigned.')
    shaders.append(dict(address=addr,domain='shader',profile=profile,finding=finding,evidence=[str(p.relative_to(ROOT)).replace('\\','/')],limitations='Shader arithmetic/signatures verified statically; runtime material or actor ownership is not inferred from a bytecode address.',buffers=buffers,assembly_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),instructions={k:v for k,v in collections.Counter(l.split()[0] for l in code.splitlines() if l and not l.startswith(('//','dcl_'))).items()}))

# Map program records directly from native assignments, including alias output pointers.
t=raw['0x14011e1d0']['code'];t=re.sub(r' /\*0x[0-9a-f]+\*/','',t)
aliases={m[1]:int(m[2]) for m in re.finditer(r'(v\d+) = \([^;\n]*?\)\(a1 \+ (\d+)\);',t)}
ps_offsets={};vs_offsets={}
for m in re.finditer(r'D3DStripShader\(&unk_([0-9A-F]+),\s*(0x[0-9A-Fa-f]+|\d+)u?,\s*0,\s*(.*?)\);',t):
    dest=m[3];dm=re.search(r'a1 \+ (\d+)',dest);offset=int(dm[1]) if dm else aliases.get(dest)
    if offset is None:continue
    (ps_offsets if offset<31736 else vs_offsets)[offset]='0x'+m[1].lower()
programs=[]
for offset,shader in vs_offsets.items():
    idx=(offset-31736)//552
    q=re.search(rf'\*\(_QWORD \*\)\(a1 \+ {offset+8}\) = \*\(_QWORD \*\)\(a1 \+ (\d+)\)',t)
    pso=int(q[1]) if q else (31664 if re.search(rf'\*\(_QWORD \*\)\(a1 \+ {offset+8}\) = \*v15',t) else None)
    programs.append(dict(program=idx,record_offset=offset,vertex=shader,pixel=ps_offsets.get(pso),pixel_index=(pso-31560)//8 if pso else None))
lastshader=None
for l in t.splitlines():
    m=re.search(r'v184 = &unk_([0-9A-F]+)',l)
    if m:lastshader='0x'+m[1].lower()
    m=re.search(r'sub_140111830\(a1, (?:\(unsigned int\))?v\d+, (\d+), .*?, (0x[0-9A-F]+|\d+)u?, (\d+), (\d+)\)',l)
    if m:
        idx=int(m[1]);pi=int(m[2],0);programs.append(dict(program=idx,record_offset=31736+552*idx,vertex=lastshader,pixel=ps_offsets.get(31560+8*pi),pixel_index=pi,flags=int(m[3]),texture_count=int(m[4])))
programs=sorted(programs,key=lambda x:x['program'])
(OUT/'render_shader_programs.json').write_text(json.dumps(programs,indent=2))

constants=[
dict(name='cbConstantVS',gx_offset=23008,size=144,root_parameter=0,hlsl_register='b2',fields=shaders[0]['buffers']['cbConstantVS']),
dict(name='cbShaderParam',gx_offset=23464,size=3456,root_parameter=1,hlsl_register='b3',fields=next(s['buffers']['cbShaderParam'] for s in shaders if 'cbShaderParam' in s['buffers'])),
dict(name='cbViewProjection',gx_offset=30380,size=64,root_parameter=2,hlsl_register='b4',fields=[dict(name='WorldView',offset=0,size=64,type='float4x4')]),
dict(name='cbConstantPS',gx_offset=23300,size=80,root_parameter=3,hlsl_register='b6',fields=next(s['buffers']['cbConstantPS'] for s in shaders if 'cbConstantPS' in s['buffers']))]
for c in constants:
    for f in c['fields']:f.pop('used',None)

features=[]
for slot,name,off,typ,lo,hi,description in [
 (184,'GX frame serial',816,'uint32',0,4294967295,'Advances at completion of a GX render frame; interpolated/replayed frames are included. Not simulation frames or FPS.'),
 (185,'GX selected program',96,'int32',0,47,'Current/last GX shader-program selector, not a whole-scene shader.'),
 (186,'GX target selector',108,'int32',0,5,'Current/last render-target selector;5is final presentation.'),
 (187,'GX state and clear requests',58244,'uint32',0,4294967295,'Sampled current render-frame state-application/clear counter; not draw calls, triangles or completed-frame totals.'),
 (188,'GX constant-buffer retries',58232,'uint32',0,4294967295,'Draw state upload exhausted the constant arena and retried after a flush; resets at render-frame begin.'),
 (189,'GX vertex-buffer retries',58236,'uint32',0,4294967295,'Transient vertex allocation exhausted its arena and retried after a flush; resets at render-frame begin.'),
 (190,'GX replay mode',22944,'int32',0,1,'Renderer command replay/interpolation mode sampled at this instant.'),
 (191,'GX current fog flag',640,'uint8',0,1,'Per-primitive desired fog flag; many shaders ignore it. A diagnostic, not a global fog switch.'),
 (192,'GX gamma exponent',23360,'float32',0.0001,10000,'Current inverseGamma applied by final presentation shader.'),
 (193,'GX color-vision type',23364,'uint32',0,3,'Current final presentation constant;0disables color-vision correction.'),
 (194,'GX color-vision severity',23368,'uint32',0,10,'Current final presentation constant; native enabled setting clamps1..10.')]:
    features.append(dict(Slot=slot,Name=name,Kind='ReadOnly',Offset=off,Type=typ,Minimum=lo,Maximum=hi,Description=description))
contract=dict(status='PROPOSAL_ONLY_ROOT_REVIEW_REQUIRED',writes=False,features=features,
    prerequisites=['Exact supported executable build and normal bridge lifetime gates.','Never call 11C150 to initialize for telemetry. Fixed GX = base+0x8A0970; validate readable memory for the required scalar fields (largest proposed offset 58244+4).','Require exact GX vtable base+0x5A9028, nonnull D3D device at +736 and root signature at +1144, and valid bridge/game thread for snapshot. Only read static GX scalar fields; do not dereference COM objects.','Validate each value range and finite float; publish unsupported/invalid when initialization checks fail.','Fields can change on renderer workers. Each scalar is a sampled diagnostic; reading frame serial before/after does not prove a coherent capture because replay/end paths can mutate fields between phases. Do not compare mixed samples as completed frame statistics.','Use the normal c.sceneReady gate for initial release; no graphics command calls.'],
    excluded=['No simple global NoFog or Fullbright: GS packets/per-material constants overwrite them. Need a proven render-thread interception/restore boundary and replay handling.','No wireframe native option identified: PSO creator hardcodesSOLID, cache key does not encode fillmode. Would require a designed pipeline substitution/cache policy.','No HUD-only selector established:2Dsprite programs are shared with menus/debug/UI. Suppressing program3would remove developer text and other sprites.','Do not expose raw shader indices, generic125F00selectors or resource/state getters as writes.','Gamma/color-vision setters are understood, but persistence and restore ownership should be designed with native settings rather than a competing continuous override.'])
(OUT/'render_feature_contract.json').write_text(json.dumps(contract,indent=2))

report=dict(scope='Read-only static renderer/GX/shader analysis; no UI/game/IDB/source mutation',base=hex(BASE),singleton=hex(BASE+0x8A0970),
 counts=dict(native_fresh_bodies=len(raw),native_claims=len(claims),gx_tables=len(vts),gx_slots=sum(len(v['slots']) for v in vts),gx_distinct_targets=len({a for v in vts for a in v['slots']}),shaders=len(shaders),shader_programs=len(programs)),
 pipeline=['GS/debug packets decode material state and select a shader program.','Vertices allocate in a transient arena or arrive as Mesh/VertexResource.','1121D0 applies cached state;111AE0 uploads changed constants into256-byte-aligned ranges.','113590looks up/creates packed-key PSO;11A1B0 issues D3D12Draw/DrawIndexed calls.','Surface copies/resolves maintain D3D12 resource states through tracked per-allocation fields.','1219F0 schedules final program47 pass then transitions swapchain surface back toPRESENT.','128260 submits/retire resources;120ED0 can replay closures with interpolated camera matrices.'],
 constants=constants,Functions=claims,shaders=shaders,program_mapping_file='render_shader_programs.json',feature_contract_file='render_feature_contract.json',
 boundaries=['All GX table targets now have a narrow concrete recorded behavior; this is not complete semantic coverage of all renderer callees.','Material names/world-specific pass ordering and renderer-worker races are not established by an export alone.','Shader proof is arithmetic/signatures and native registration; no GPU-capture or visual test.','SDK identities verified against localWindows10SDK10.0.26100.0um/d3d12.h; graphics-command offsets and resource state constants match.'])
(OUT/'render_deep.json').write_text(json.dumps(report,indent=2))
summary='''RENDERER / GX / SHADER DEEP REVIEW
================================

The port uses Direct3D12 command lists with embedded Shader Model4.0DXBC. The
resource-state cache, command replay, constant arena and PSO cache are part of
normal rendering. Calling arbitrary GX functions after a game update can disrupt
the active command buffer and renderer workers.

The connected path is now explicit:
GS packed primitives -> per-draw state -> shader record -> constant upload ->
PSO lookup/create -> D3D12 Draw/DrawIndexed -> final fullscreen program47 ->
swapchain PRESENT transition -> submission/fence retirement. Renderer replay
can issue interpolated frames by replaying command closures separately from a
simulation frame.

Useful findings
---------------
* Four constant buffers have exact CPU offsets, HLSL register bindings and
  shader field layouts in render_deep.json. They are uploaded in256byte-aligned
  slots; cbShaderParam contains48 LocalProjection matrices, lighting and fog.
* Shader families include snapped/unsnapped2D sprites, indexed/weighted model
  transforms, alpha-test variants, exact unusual grayscale coefficients,
  four-tap region-aware interpolation, a12sample blur, two-texture blending,
  planar filmYUVconversion, and final gamma/color-vision correction.
* Final program47 pairs the SV_VertexID fullscreenVS with gamma/accessibilityPS.
  Program45converts filmYUV;46is a plain copy. Shader-program IDs are distinct
  from the47embedded blob count and from HLSL register numbers.
* Debug text reaches program3through real28bytevertex quads. The retained128x128
  font atlas is embedded; its text parser handles uppercase ASCII, glyph escapes,
  @color codes and newline. It is not a safe general Unicode overlayAPI.
* Resource getter/state getter pairs in the GX vtables now match CopyResource
  barrier behavior. Framebuffer resource/descriptor IDs are managed allocations,
  and deleting wrappers release ownership. None is a trainer integer knob.

Trainer recommendation
----------------------
Propose read-only GX diagnostics in slots184..194: render serial, selected
program/target, state/clear counter, constant/vertex arena retries, replay flag,
current per-draw fog flag, gamma exponent and accessibility constants. Exact
gates/types/ranges are in render_feature_contract.json. Root review is required
before implementation. These are sampled render values, not coherent completed
frame statistics. No gameplay-save writes are involved.

NoFog/Fullbright: no safe persistent global switch proven. Fog setter126600is
overwritten by GS packet material flags; lighting belongs to shader parameters.
Wireframe:117710hardcodes D3D12_FILL_MODE_SOLID3; changing cull mode is not wireframe.
HUD hide:2Dshader paths include debug text and other UI; no HUD-only global proven.
GPU timing lists:129180maps readback resources and appends records under a native
critical section. Do not traverse these lists unsynchronized from the host.

Evidence and limits
-------------------
Fresh complete addressed pseudocode and ASM are in render_deep_evidence_full.json
and render_deep_evidence_additional.json. Complete large-function pages are in
render_deep_evidence_pagination.json (1121D0 and11E1D0). The earlier render_deep_evidence.json
is a23function checkpoint and is superseded by the full files. Shader assembly
remains in work/pe/shaders; exact native-to-shader record mapping is in
render_shader_programs.json. Every per-function claim states a concrete behavior
and a limit. No claim means every branch/callee/runtime condition is understood.

'''
summary+='COUNTS: '+json.dumps(report['counts'])+'\n\n'
for c in claims:summary+=c['Address']+' '+c['Name']+'\n  '+c['Finding']+'\n  Limit: '+c['Limitations']+'\n'
(OUT/'render_deep.txt').write_text(summary)
print(report['counts'])
print('Programs',[(p['program'],p['vertex'],p['pixel']) for p in programs])
assert len(shaders)==47
assert all(a in {c['Address'] for c in claims} for v in vts for a in v['slots'])
