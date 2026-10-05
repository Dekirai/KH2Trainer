"""Rebuild the camera report from saved, read-only IDA evidence."""
from pathlib import Path
import json, hashlib

root = Path(__file__).resolve().parents[3]
research = root / 'work/trainer/research'
evidence = {}
exports = []
for path in sorted(research.glob('camera_deep_evidence_*.json')):
    data = json.loads(path.read_text(encoding='utf-8'))
    for fn in data['functions']:
        a = fn['addr'].lower()
        asm, code = fn['assembly'], fn['code']
        assert asm['cursor'].get('done') and asm['instruction_count'] == asm['total_instructions'], a
        assert code['cursor'].get('done'), a
        evidence.setdefault(a, []).append(path.relative_to(root).as_posix())
        exports.append({'addr':a,'file':path.relative_to(root).as_posix(),'instructions':asm['instruction_count']})

# Findings are manually reviewed semantic statements, not inferred from exports.
rows = '''
19CE70|Returns the distinct camera owner DWORD at RVA AC1528. This is not the bank index or field-controller submode.|19DDA0,166100,1780D0|Observed owner values are not an exhaustive enum.
19DDA0|Copies AC1528 to previous-owner AC152C, then stores ECX as new owner. No scene or actor validation.|19CE70|Do not force mode zero to steal script control.
166100|With a nonnull borrowed actor at controller+80, advances only when forced or owner==0. Dispatches controller+72 modes 0..10, consumes snap byte+64, consumes event handoff, then interpolates/publishes pose.|165110,165700|Forced entry performs a second update and is unsuitable as a trainer getter.
164860|Parameterless scheduled callback calls 166100(static controller RVA718C60,false). No return is used by the scheduler.|164CB0|The task callback can accept an unused node argument under Win64 ABI.
164CB0|Clears handoff, sets owner0, resets follow state and registers 164860 on the current field scheduler: group1, priority26000.|157BB0|Registration is scene initialization, not an on-demand trainer API.
164C60|Stores borrowed actor in controller+80. Except submode7, sets submode0 and preset index+68, initializes the preset using preserved EDX, and returns ownership to0 unless script owner1 is active.|165A70,3AA850,3AAA80|No lifetime retention or preset bounds check. Reject arbitrary actor retargeting.
165A70|Copies one six-float preset row from RVA718C00 using signed EDX index: FOV+224, default/current distance+204/+88, parameter+208, lower/upper distance+212/+216, height coefficient+220. Clears roll-related target scalars.|164520,1654D0|Some preset FOV fields are zero until specialized setup; do not treat every row as directly usable.
164CF0|Clears the borrowed followed-actor pointer at718CB0.|3A7120,3AAB00|A nonzero readable address alone is not a lifetime guarantee.
3A7120|Player teardown clears global player2A105D0 and invokes164CF0 before additional player/controller cleanup.|164CF0|Not a complete catalog of actor deletion paths.
3AAB00|Actor cleanup invokes164CF0 and clears its camera/controller state.|164CF0|The trainer must reacquire identity after player/form replacement.
3AA850|Native actor camera binding selects presets0/1/2 and special camera setup using actor/world state before164C60.|164C60|Do not reproduce selection from an unvalidated character label.
3AAA80|Alternate actor setup binds the native field camera with preset selection and specialized follow behavior.|164C60|Only its camera-binding branch is claimed.
164FA0|Resets follow interpolation using borrowed actor heading and position, target height offset170, default distance and desired pose; commits through164D70.|164E90,164520|Requires a live actor; not a pure reset of an isolated camera object.
164E90|Reads the followed actor's forward vector and returns atan2(-forward.x,-forward.z) in XMM0.|165110|Heading sign is established by arithmetic; screen-facing direction was not live tested.
164520|Computes desired eye from target, native follow distance and yaw; eyeY is targetY+150-(distance-minDistance)^2*heightCoefficient. Forced branch snaps history.|1654D0,164D70|Yaw interpolation is timestep-dependent; direct repeated calls would alter natural update behavior.
165110|Normal follow consumes native camera input, can enter submode1, consumes recenter byte+65, restores preset distance/yaw behind actor, then resolves position, collision and desired eye.|165A40,3B5B40|Recenter is a native request consumed during this update, not a full scene reset.
1654D0|RCX controller/RDX input/XMM2 timestep. Native zoom input adjusts controller+88 and clamps it to float bounds+212/+216.|165110|The clamp is an input-path bound, not permission to permanently overwrite distance globally.
165700|Interpolates target, eye and FOV/roll, with timestep and actor-speed dependence. Performs mode-dependent collision correction, then sets horizontal FOV and pose including roll through19D3D0.|19DDE0,19D3D0|Calling it separately adds an extra update; do not expose directly.
164D70|Copies desired pose into current/history pose and FOV/roll; bypasses remaining interpolation for this update.|166100|The unused decompiler RDX parameter is not a required native argument.
165A40|RCX controller; writes exactly byte+65=1 and returns. Native recenter request setter.|165110|Requires prompt consumption in the normal follow update.
165BC0|RCX controller; writes exactly byte+64=1 and returns. Native snap request setter.|166100|Existing pending native requests must not be overwritten or restored blindly.
430B60|Parameterless VM wrapper gets static controller164E70 and tailcalls165A40; VM bank1 index295 has zero args and no value.|165A40,164E70|The table provenance is from existing scan plus fresh raw entry bytes.
430B40|Parameterless VM wrapper gets static controller164E70 and tailcalls165BC0; VM bank1 index193 has zero args and no value.|165BC0,164E70|Use at the native follow boundary, not a second forced camera update.
164E70|Returns address of static field controller718C60.|166100|Static storage survives scenes; its borrowed fields do not.
1648C0|Helper consumes recenter byte+65, restores distance and behind-actor yaw, copies desired eye into current eye and reports a snap request.|165110|Not used as the trainer API; the current normal path inlines this logic.
1656F0|Returns controller submode to2 when byte+67 is set, otherwise0.|176380,177960|This does not clear every specialized camera's borrowed pointer.
164870|With a followed actor and submode1, updates actor state at+2576 and returns controller submode to0.|1783E0|Leaving this mode affects the actor, so a generic mode write is insufficient.
1783E0|Script camera acquire clears handoff, exits native submode1, sets owner1 and copies current controller target/eye/FOV/roll into event interpolation buffers.|2CB5D0|Do not call from the trainer to bypass event ownership.
2CB5D0|Event fiber acquires the script camera through1783E0 when event-camera ownership flagB64FA8 is1 while entering its camera-active state.|1783E0|Only camera acquisition branches are claimed; the whole event fiber is not semantically decoded.
1780D0|Script pose writer acts only under owner1, applies optional collision and interpolation, writes eye/target/roll via19D3D0 and FOV via19DDE0.|19D3D0,19DDE0|RCX eye,RDX target,XMM3 FOV; additional stack flags are event-specific and not a trainer API.
2D37B0|Event timeline selects active camera rows, resolves transforms, selects camera bank(s), calls1780D0 and returns bank selection to0.|1780D0,19DDD0|Timeline/resource formats and all events remain outside this contract.
2CC0B0|Event release invokes177F20 when camera ownership flagB64FA8 is1 and restores split-bank field task configuration when needed.|177F20|Only the camera release branch is claimed.
177F20|Releases owner to0, derives native follow state with164F00, and optionally captures current eye/target/FOV/roll into the handoff buffer with ABE710=1.|166100|It has broad native side effects; do not replace it with a raw owner write.
164F00|Temporarily sets controller submode0, resets and forces a complete update to obtain a follow pose, then restores previous submode.|166100,164FA0|Despite output-vector parameters this is not a side-effect-free getter.
1783D0|Clears the one-shot script-to-follow handoff flagABE710.|166100|Never clear independently during an active script transition.
164D00|Copies saved event handoff pose/FOV/roll into controller current state and clears the handoff flag.|177F20|No ordinary native caller established; helper evidence only.
5423A0|Ti::MGOarashi setup explicitly sets owner2, proving specialized/minigame camera ownership outside normal0 and script1.|19DDA0|This does not assign a universal meaning to every owner2 state.
19CE40|Returns one 128-byte camera bank entry; current flag or selectorAC183C choosesAC1020, otherwiseAC1B50; index is signedAC1838.|19CBA0|Getter has no index bounds check; trainer restricts bank0.
19CFC0|Returns one388-byte projection entry atAC1840 orAC1220, selected by current flag/AC183C and indexed byAC1838.|19CBA0|Trainer must not confuse current and previous projection banks.
19DDD0|Stores the bank index atAC1838 without validation.|2D37B0|Trainer must not change the index to override event bank selection.
19D050|Resets owner, bank index and selector; initializes both projections, eye/target/up and zero roll; restores horizontal FOV1.5rad.|150770,157BB0|Called on field and event-specific projection setup; static addresses do not imply scene persistence.
150770|Creates the field scheduler716868, initializes field systems, and calls camera/projection reset19D050 before scene load setup.|19D050|Only scheduler/camera initialization relationship is claimed.
157BB0|Room setup registers native follow task via164CB0 and installs room-specific clipping values before19D050.|164CB0,19D050|Room-specific exceptions prevent a single universal near/far preset.
157850|Event-specific room cases such as tt_event_907/hb_event_417/hb_event_420 change projection constraints and rerun19D050.|19D050|Script ownership can change within the same room and scheduler lifetime.
19CBA0|Copies current camera/projection to previous banks; builds view from eye/target/up, then reads Camera+120 into XMM1 and applies1AADC0; finally submits view. Invalid NaN basis triggers identity fallback.|1AADC0,19D340|The +120 argument is missing from some decompiler calls; full ASM is authoritative.
19D340|RCX camera,RDX eye,R8 target,R9 up: copies vectors to+72/+88/+104 and sets eye.w1; leaves+120 unchanged.|19CBA0|Setting an up-vector roll while retaining native roll can compose two rotations.
19D3D0|RCX camera,RDX eye,R8 target,XMM3 roll radians: copies pose, sets eye.w1, writes float+120.|1AADC0,165700|This does not update up; combine deliberately with19D340 for held free camera.
19D000|Returns the native roll scalar atCamera+120 in XMM0.|19CBA0|This excludes any rotation already embedded in the Up vector.
1AADC0|For nonzero XMM1 angle, normalizes it, constructs a Z-axis rotation matrix and multiplies the existing view; writes result back.|1A90C0,141320,13F850|This confirms additional view-axis roll, not a world-Y orbit.
1A90C0|Normalizes an XMM0 angle by repeated plus/minus2pi into[-pi,pi].|1AADC0|Huge/infinite inputs can fail to make progress; trainer must reject nonfinite and bound input first.
141320|RCX output/XMM1 radians produces a Z-axis rotation matrix with cosine/sine in XY entries and unchanged Z/W axes.|13F850|Memory layout and signs are established statically; screen clockwise direction remains a live check.
13F850|Transforms each vector of the right matrix through the left matrix using13F900; returns output in RAX.|1AADC0,13F900|Narrow matrix-composition finding only.
13F900|RCX matrix,RDX output,R8 vector: computes the linear combination of all four matrix vectors, including homogeneous component.|13F850|General math helper, not independently a camera API.
19D420|RCX camera/XMM1 side/XMM2 up translates both eye and target in a normalized camera basis.|19D340|Already functionally covered by trainer local-move slot73; no duplicate feature recommended.
19D5A0|RCX camera/EDX axis/XMM2 radians: axis0 orbits eye around target in XZ; axis1 rotates eye-target about normalized cross(eye-target,up); other axes do nothing.|1A9130|Native helper is not directly called by ordinary field code; use only validated held pose if exposed.
1A9130|Builds an axis-angle matrix from XYZ and angleW after normalizing the XYZ axis.|142080|Zero or parallel camera basis is not made safe by this helper alone.
142080|Normalizes vector XYZ when its Euclidean length is nonzero; leaves zero vector unchanged.|1A9130,19CBA0|NaN/Inf are not rejected; trainer must validate separately.
19DF80|RCX camera/XMM1 fractional radial change: scales eye-target by1+delta and updates eye if resulting distance>=1e-5.|13FCC0,140F50|Pseudocode omitted XMM1. Negative scale can cross the target; not a bounded dolly API.
13FCC0|RCX vector/XMM1 scalar multiplies all four float components, confirmed by SSE shuffle/mulps.|19DF80|Decompiler double annotation is incorrect for this caller.
140F50|Returns sqrt(x*x+y*y+z*z) for vector atRCX.|19DF80|No nonfinite or overflow protection.
19DDE0|RCX projection/XMM1 radians/R8D vertical flag updates focal+64 and horizontal/vertical FOV+68/+72 using scales+76/+80.|19CAD0|Already implemented horizontal FOV; invalid scales or extreme angles must be rejected.
19DF00|RCX projection/XMM1 focal sets focal+64 and recalculates both FOVs from projection scales.|19DDE0|Equivalent zoom control, not a new independent visual feature.
19CE90|Reads projection FOV float at+68+4*EDX; indices0/1 are horizontal/vertical.|19DDE0|No bounds check; trainer should not accept arbitrary index.
19D010|Returns focal scalar projection+64.|19DF00|A readout is possible; unit is native projection units, not millimeters.
19DC50|Initializes projection focal/scales/offsets/depth planes and clamped planes, then builds matrices via19CAD0.|19CAD0,157BB0|Many ABI float arguments are on stack; this broad initializer is not a trainer FOV setter.
19CAD0|Rebuilds projection and auxiliary matrices using current focal/scales/clamped planes.|19CBA0|Do not call from a UI/worker thread.
19D750|Restores both camera/projection banks from static native backup banks.|19D980|No ordinary caller or ownership/lifetime contract; do not use as bookmark restore.
19D980|Copies both current camera/projection banks into static native backup banks.|19D750|Would share engine global backup state; trainer bookmarks should own scalar copies.
157AD0|Writes the global near-clamp state71C658 as -1 or8 depending on a boolean.|19DC50|This is shared projection state, not an isolated camera control.
18A910|Rendering setup consumes shared clipping globals71C658/71C65C when configuring rendering depth behavior.|19DC50|Shows broader consumers; no full rendering-subsystem claim.
176310|Enters field submode3 and copies a20-byte target descriptor intoABE4F0.|176380|Descriptor ownership/encoding is not fully proven; no arbitrary target writes.
176380|Submode3 validates its target descriptor and actor conditions, returns to fallback on loss, otherwise resolves target and updates tracking/input/collision.|176310,1656F0|Useful future lock-camera lead; descriptor construction still required.
176210|Enters submode4, copies a20-byte target descriptor and initializes mode flags.|1762E0|Not equivalent to a generic hold-camera action.
1762E0|Submode4 performs first-frame setup and native collision work.|176210|Its setup lifetime was not fully decoded.
1762B0|Task callback requests snap, restores submode2/0, then removes its own task.|165BC0,1656F0|Requires a real task node; never call as a parameterless action.
1778D0|RCX actor/XMM1 height selects mode7 and stores a borrowed actor pointerABE5D0 and height, plus native interpolation defaults.|1779C0|No lifetime retention; unsafe as arbitrary-enemy follow API.
1779C0|Mode7 update dereferences the borrowed actor through3B5B40 and derives eye/target from its position and saved height/pivot.|1778D0|No null/lifetime check in the observed path.
177960|When in mode7 returns to fallback via1656F0; does not clear the borrowed pointerABE5D0.|1778D0,1656F0|Mode change alone does not establish pointer safety.
178760|Enters submode9, records borrowed actor/object pointers and invokes specialized initialization.|166100|Purpose and lifetime are not sufficiently proven for a trainer command.
176A00|Submode2 exit validates a packed target, clears an actor flag, resets controller mode-selection state and falls back.|1656F0|Camera mode operations can alter gameplay actor state; raw mode writes are insufficient.
3B5B40|RCX actor: selects position at+112 when decoded packed field+1696 is present, otherwise+1648.|3DA520|Do not assume one actor position offset for all forms/states.
3DA520|Decodes packed actor+1696 and returns whether it is nonnull.|3B5B40|It is a presence test, not general pointer validity.
3B6F20|Angle normalizer accepts float in XMM0 and uses fmodf to wrap into a pi-centered range.|165A70,165110|Decompiler aliases it to unrelated integer parameters at several call sites.
'''
claims=[]
for row in rows.strip().splitlines():
    addr,finding,refs,limits=row.split('|')
    addresses=['0x140'+addr]+['0x140'+x for x in refs.split(',') if x]
    paths=sorted({p for a in addresses for p in evidence.get(a.lower(),[])})
    assert addresses[0].lower() in evidence, addresses[0]
    if addr in ('430B40','430B60','165A70','141320'):
        paths.append('work/trainer/research/camera_deep_data.json')
    if addr in ('430B40','430B60'):
        paths.append('work/vm_tables_scan_with_holes.json')
    claims.append({'addr':addresses[0],'Finding':finding,'Evidence':paths,'Limitations':limits,
                   'strength':'fresh complete body + dedicated complete assembly; static semantic review'})

features=[
 {'id':'camera.roll','slot':240,'kind':'Number','range':[-180,180],'unit':'degrees','api':'WorldCameraExtraSetRoll(radians); existing held-camera callback applies19D340 then19D3D0(camera,eye,target,roll).','gates':'Only current held normal-follow camera; owner0/submode0, current bank0, stable scene and fresh engine-thread heartbeat.','restore':'Trainer drops held pose on ownership/scene loss. Native producer resumes; never replay an old camera bank.','status':'implemented in CameraExtraFeatures and Root-owned World integration; static/synthetic verification only'},
 {'id':'camera.owner','slot':241,'kind':'ReadOnly','rva':'AC1528','type':'int32','values':'0=normal follow;1=script;2=observed minigame owner. Other values remain unknown.'},
 {'id':'camera.controller_mode','slot':242,'kind':'ReadOnly','rva':'718CA8','type':'int32','values':'0..10 native field-controller branches; only mode0 accepted for new actions.'},
 {'id':'camera.recenter','slot':243,'kind':'Action','api':'void430B60(); setter165A40(controller) writes+65.','gates':'Queue is bound to scheduler/scene heap/full10-byte map target/player/status/actor controller; owner0/submode0, no field pause/menu/event/transition/freecam. Consume before existing follow task164860 once; no second update.','restore':'Cancel before dispatch on timeout/heartbeat/identity/ownership loss. Native flag must be consumed in that same ordinary update.'},
 {'id':'camera.snap','slot':244,'kind':'Action','api':'void430B40(); setter165BC0(controller) writes+64.','gates':'Same as recenter; reject existing native pending flags.','restore':'One ordinary update; never restore a whole controller or camera bank.'},
 {'id':'camera.pending','slot':245,'kind':'ReadOnly','values':'0=none,1=recenter queued,2=snap queued'},
 {'id':'camera.follows_player','slot':246,'kind':'ReadOnly','rva':'718CB0','type':'boolean equality with freshly validated current player'},
 {'id':'camera.follow_distance','slot':247,'kind':'ReadOnly','rva':'718CB8','type':'float native distance parameter','limits':'Not equal to the final collision-adjusted eye-to-target distance.'},
 {'id':'camera.focus_distance','slot':248,'kind':'ReadOnly','rva':'AC1020+72/+88','type':'Euclidean distance of eye and target','limits':'Geometric pivot distance; not optical depth of field.'}
]
report={
 'scope':'Native field camera/projection ownership and missing trainer functions. Research plus isolated trainer implementation; no game/UI/process access or IDB edits.',
 'image_sha256':'9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed','image_base':'0x140000000','ida_session':'1fc84ea8',
 'method':'Existing WorldFeatures/world_camera read first. Fresh full pseudocode plus dedicated paginated assembly; all saved cursors complete. Claims are manually reviewed and are not a completeness claim for the entire camera subsystem.',
 'corrections':['Camera+120 is native additional view-axis roll. At19CD55 the hidden XMM1 argument feeds1AADC0; a prior interim interpretation as unused was incorrect.', '19DF80 accepts XMM1 fractional radial change although pseudocode omitted it.', '164C60 preserves preset EDX into165A70 although pseudocode omitted the argument.', '19D5A0 axis0 rotates eye in XZ around target (world Y axis).'],
 'flow':['Scene150770/157BB0 ->19D050 reset and164CB0 task registration','Follow task164860(group1/26000)->166100(owner0)->165110(mode0)->165700->19D3D0/19DDE0','Event2CB5D0->1783E0 owner1;2D37B0->1780D0;2CC0B0->177F20 owner0 plus saved handoff consumed by166100','Render task19CBA0 copies previous banks, builds view from eye/target/up, composes native roll, submits renderer'],
 'scene_contract':{'persistent_storage':['camera banks AC1020/AC1B50','projection banks AC1840/AC1220','controller718C60'],
  'lease':['field scheduler716868','scene heap9BA920','full10-byte target717008','player2A105D0','status backlink','actor controller decoded atactor+0','ownerAC1528==0','submode718CA8==0','bankAC1838==0 and selectorAC183C==0'],
  'yield':['sceneReady9BA8D0!=1','eventOnly9BA8D1','pending9BA928','module716884!=1','menu9006B0','eventAC0F48','heartbeat timeout','owner/submode/actor replacement'],
  'limitation':'Exact same-address ABA after an entirely unobserved teardown/recreation cannot be proven absent without a generation token. Observe every native follow boundary and any unavailable tick; never keep task-node addresses after the callback.'},
 'features':features,'not_duplicated':['XYZ/yaw/pitch/freecam/FOV/local movement already exist in WorldFeatures slots49..56/73/74.'],
 'future_candidates':['Orbit about target/pivot using held vectors and validated native19D5A0 semantics','Explicit target-point controls and trainer-owned same-scene camera bookmark','Target-lock mode3 after20-byte descriptor construction/lifetime is fully decoded'],
 'not_recommended':['Raw owner/submode forcing','Borrowed arbitrary-actor retarget through164C60/1778D0','Native global backup banks19D750/19D980 as bookmarks','Shared global near/far clipping writes','A second forced166100 call for a trainer action'],
 'implementation':{'source':'trainer/Native/CameraExtraFeatures.inl','catalog':'work/trainer/research/cameraextra_features.json','tests':'work/trainer/tests/CameraExtraGuardTests.cpp','validation':'work/trainer/research/camera_extra_validation.json','integration':'work/trainer/research/camera_extra_integration.txt','profile_policy':'All new camera entries are excluded from automatic profile application; active scene and held camera ownership are required.','post_update_flags':'The trainer performs no post-call flag cleanup. Value1 alone cannot distinguish its own old flag from a newly written native request.'},
 'claims':claims,'evidence_inventory':exports,
 'coverage':{'unique_full_function_exports':len(evidence),'reviewed_function_claims':len(claims),'interpretation':'Only each written Finding is claimed. Exported surrounding code is not implicitly understood.'},
 'live_validation':'Not performed. Rotation direction, transition visuals, mod interactions and user-facing usefulness require later supervised live validation.'}
(research/'camera_deep.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
lines=['CAMERA DEEP RESEARCH — native field camera and projection','',report['scope'],'Build SHA256: '+report['image_sha256'],'',
       'Main findings','- Native roll is Camera+120 in radians; complete ASM supplies the missing XMM1 argument.','- Owner AC1528, bank AC1838 and controller mode718CA8 are separate states.','- Script acquire/release includes pose history and smoothing; never steal owner0.','- Native recenter430B60 and snap430B40 can run at the existing follow-task boundary.','- Borrowed follow actors are explicitly cleared during player/form teardown.','',
       'Existing controls: '+report['not_duplicated'][0],'','Proposed feature contract (slots240..248)']
for f in features: lines += [json.dumps(f,ensure_ascii=False),'']
lines += ['Scene/lifetime contract',json.dumps(report['scene_contract'],indent=2),'','Control flow']+report['flow']
lines += ['','Corrections']+report['corrections']+['','Function findings (narrow claims only)']
for c in claims: lines += [c['addr']+' — '+c['Finding'],'Evidence: '+', '.join(c['Evidence']),'Limit: '+c['Limitations'],'']
lines += ['Coverage: '+json.dumps(report['coverage']),'Future work: '+'; '.join(report['future_candidates']),report['live_validation']]
(research/'camera_deep.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
for c in claims:
    for p in c['Evidence']: assert (root/p).is_file(),p
print(json.dumps(report['coverage']))
