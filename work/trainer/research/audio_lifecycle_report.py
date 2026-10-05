"""Build the audio lifecycle findings from retained read-only IDA evidence."""
import json,hashlib,pathlib
root=pathlib.Path(__file__).resolve().parents[3]
dest=root/'work/trainer/research'
sources=['audio_lifecycle_evidence.json','audio_lifecycle_settings_evidence.json']
functions={}
proofs={}
for name in sources:
    doc=json.loads((dest/name).read_text(encoding='utf-8'))
    for entry in doc['functions']:
        functions[entry['addr']]=entry
        proofs[entry['addr']]='work/trainer/research/'+name
findings={
'121d90':('Orders application Init virtual+8, repeated Update virtual+32, and Shutdown virtual+40 on the same call stack. Update must finish before shutdown is invoked.','Covers the observed native application loop; does not authorize calls from arbitrary trainer workers or DLL detach.'),
'14ed40':('Application initialization calls13C910 when required, then builds the engine task manager; audio initialization precedes ordinary update frames.','The caller must retain the verified application identity.'),
'14eb70':('Runs the outer task manager and returns0 for continued frames or2 to leave the loop. Existing trainer post-update can reject nonzero returns.','The audio contract requires the continued-frame branch and known engine thread.'),
'14eb00':('Application shutdown reaches13C7C0 and returns1, preventing another ordinary frame in this native shutdown sequence.','No trainer operation is valid during this callback.'),
'13c910':('Creates the sound manager only when global8BBD08 is null, first calling1437B0 to construct the sound backend.','A singleton nonnull test alone is not a lifetime proof.'),
'13c7c0':('Destroys/nulls sound manager8BBD08, clears game sound-bank lists/configuration, and calls143770 for backend shutdown.','Some destruction occurs outside global Sound CS; the application-loop ordering is essential.'),
'1437b0':('Initializes audio once, loads configuration, creates sound backend through076E50, starts two timer workers07B220/07B450, and publishes8BBDA8.','Not an arbitrary runtime reset API.'),
'143770':('Conditionally enters077BE0 from normal manager teardown and frees initialization storage.','Alternate initialization mode8BBDA0 changes this branch.'),
'076e50':('Runs audio configuration/backend initialization and reaches076F20; failure paths set silent/failure flags.','Graph validation remains necessary even after application initialization.'),
'076f20':('Allocates SoundDriver only when2B81DE0 is null and publishes auxiliary backend objects.','No observed ordinary frame caller replaces a live driver through this function.'),
'091250':('Constructs104-byte SoundDriver, initializes its instance CS, constructs buses via08D720, and finally writes BYTE(driver+52)=1.','The earlier DWORD(driver+52)=0x10000 includes adjacent flags; the readiness field itself is one byte.'),
'08d720':('Clears audio roots, constructs MasterXA2 and normal buses, and binds master+336 to bus-list2B811C8 and master+344 DWORD to count2B811A4.','Initialization code; do not call to implement a mixer reset.'),
'4edf50':('Settings/menu initialization can call13C910, whose singleton guard preserves an already initialized backend.','This does not demonstrate a hot audio device reset.'),
'136640':('Alternative initialization configuration calls076E50 and sets8BBDA0.','Only unwind metadata references were found; no runtime entry through normal callers, PE pointers, CLR methods or exports was established.'),
'137bb0':('Alternative shutdown stops both workers, calls077BE0, then frees sound configuration.','Only unwind metadata references were found in the current image.'),
'077480':('Wrapper reaches076F20 to construct absent backend objects.','Its only normal caller is077500; no live runtime entry to that wrapper was identified.'),
'077500':('Thin wrapper calls077480.','No normal callers or static PE/CLR/export entry were identified; metadata occurrence is not a callback.'),
'08db30':('Allocates a new MasterXA2 and replaces master-root2B811D0. Its sole RVA data occurrence is the .pdata RUNTIME_FUNCTION08DB30..08DC78 with unwind6975B0.','No direct code caller, full-VA pointer, CLR MethodDef or export was found. This is absent observed reachability, not a mathematical proof against computed calls or external mods.'),
'077be0':('Stops/joins both timer workers, drains voices, destroys helper objects and driver, then nulls driver2B81DE0 after its deleting destructor.','The driver root remains nonnull during destructor execution; global CS alone cannot justify an arbitrary-thread read.'),
'077a30':('Alternate cleanup joins workers and releases the same backend roots.','No runtime caller was established; retained for cold/error-path completeness.'),
'091670':('Nondeleting SoundDriver destructor disables BYTE+52, destroys pools/buses via08FA20 and deletes the instance CS.','Only metadata references were identified for this exact variant; normal deletion uses the matching deleting destructor091470 documented earlier.'),
'08fa20':('Frees normal buses, bus-list allocation and master but does not clear every corresponding root/count.','Dangling root values are real during teardown; safe access depends on the normal post-update lifetime proof plus fresh graph checks.'),
'07b5b0':('Signals timer-worker exit at+96, waits indefinitely for its thread, closes handles and frees/nulls the worker.','Shutdown can block waiting for the callback; trainer must not invoke shutdown while holding the audio CS.'),
'07b380':('Signals and joins the other timer worker before freeing its storage.','Same joining/lifetime restriction as07B5B0.'),
'07b220':('Constructs a104-byte periodic worker with callback07B210, starts0FB040 and publishes active worker state.','Timer callback is not the game thread.'),
'07b450':('Constructs the second periodic worker with callback07B440 and0FB040 thread entry.','Actual scheduling latency is platform dependent.'),
'0fb040':('Timer thread waits on its semaphore and invokes object callback+16 until exit-byte+96 is set; then destroys timer/semaphore resources.','The static body proves callback ownership, not exact callback frequency under load.'),
'07b210':('Timer callback calls0784C0.','No trainer call should be injected into the timer callback.'),
'07b440':('Timer callback calls077FC0 with elapsed-time sentinel-1.','No trainer call should be injected into the timer callback.'),
'0784c0':('Acquires global Sound CS before backend/pool updates and releases it after the complete update.','It does not by itself serialize teardown outside that lock.'),
'077fc0':('Acquires global Sound CS at078004 and holds it across08FE90 at0783F5; releases at078407 after bus/master envelopes are updated.','This outer lock closes the apparent unlocked DynamicValue writes inside bus update; caller must use the same CS.'),
'08fe90':('Updates each normal bus through vtable+8 and then master through vtable+8. All identified native entry paths are under outer global Sound CS.','The function itself does not acquire that outer lock; calling it directly would violate the demonstrated contract.'),
'092d10':('SoundDriver virtual update implementation also reaches08FE90 and is dispatched inside077FC0 locking.','Only validated native driver dispatch is covered.'),
'093080':('Combined SoundDriver update variant reaches08FE90 through driver virtual+88.','Its observed public wrapper0787C0 supplies global locking.'),
'0787c0':('Holds global Sound CS while dispatching driver virtual+88, closing the alternative093080 bus-update route.','No direct use of the virtual implementation is authorized.'),
'077f80':('Returns the raw global driver pointer.','No callers were found; a raw pointer is not an ownership lease.'),
'13b560':('Exposes the0784C0 update wrapper, which takes global Sound CS.','No additional caller was found for this thunk.'),
'13b580':('Exposes the077FC0 timed update wrapper, which takes global Sound CS.','No additional caller was found for this thunk.'),
'0a4f70':('Normal bus update holds bus-local CS and advances DynamicValue stages at+24/+64/+104; outer077FC0/0787C0 global CS remains held across all interpolation writes.','The internal temporary global lock around individual voice tests is recursive and is not the full synchronization boundary.'),
'0a88c0':('MasterXA2 update advances its gain envelope and applies resulting volume to the audio backend under its callers outer global CS.','Reported gain stage is not a measurement of audible output.'),
'07fad0':('BusController setter resolves controller ID0 to master or ID1..count to list[id-1], dispatching vtable+24 with RCX=bus,XMM1=gain,R8D=duration-ms under global CS.','Use duration1ms to avoid the zero-duration voice-list paths; this is gain, not stop or pause.'),
'079c90':('Constructs a24-byte BusController through driver factory+152 under global CS; null-driver fallback returns an invalid ID-1 controller.','Validate the constructed controller before calling setters.'),
'07f7e0':('BusController destructor only rewrites its vtable and does not own/free the referenced backend.','Controller is temporary nonowning storage.'),
'138e80':('Game pause mode1 pauses existing music entries and buses; mode2 ducks music entry gain to half stored baseline; mode0 resumes or restores those entries. Manager+68 records active pause/duck ownership.','The boolean does not encode exact pause mode. These paths leave the first bus gain stage separate from per-entry ducking.'),
'1df710':('Forwards game pause/duck mode to138E80.','No independent lifetime guarantee in this wrapper.'),
'1dcbf0':('Pushes a pause mode into the game mode stack and applies it through1DF710.','Stack capacity was not established for a new trainer feature; do not call as an unbounded API.'),
'1dcbc0':('Pops game pause-mode stack and reapplies previous mode or0.','Trainer does not own this stack.'),
'1dc190':('Scene/music cleanup unwinds game audio pause mode and reapplies the prior stack state.','Audio pause ownership can change through scene transitions.'),
'1dc650':('Cleanup variant similarly restores the prior audio pause mode.','No automatic trainer restore should overwrite this native ownership.'),
'07fdf0':('BusController pause wrapper resolves bus under global CS and calls virtual+40, forwarding native layout pause where present.','Its duration argument is a native time pointer, not a direct millisecond integer.'),
'07ff90':('BusController resume wrapper accepts a native duration pointer and resolves/dispatches under global CS.','138E80 uses direct-millisecond080060 for resume instead.'),
'080060':('Direct-millisecond BusController resume wrapper used by game pause restoration.','This is an independent pause API, outside the one-time gain feature.'),
'0a56a0':('Normal bus pause walks voice controllers under local CS and sets bus bytes+332/+333.','Does not establish trainer ownership of ongoing voices.'),
'0a5780':('Normal bus resume walks voices and clears pause bytes+332/+333.','Gain-stage snapshots must not be presented as a paused-state override.'),
'0c4cd0':('Generic master pause propagates to child buses and sets master pause bytes.','Not used by the proposed gain-only feature.'),
'0c4d60':('Generic master resume propagates to children and clears its pause bytes.','Not used by the proposed gain-only feature.'),
'505d00':('Native ApplyAll reads GetFields ushort offsets20/22/24/26 and dispatches137F50/137D50/138290/138440 respectively.','The executable does not provide direct English text labels for the last three groups in this evidence.'),
'506180':('Menu callback reapplies GetFields ushort+22 through137D50.','Named Music from routing, not from a recovered localization label.'),
'506c10':('Menu callback reapplies GetFields ushort+24 through138290.','Named Effects from routing, not from a recovered localization label.'),
'506c70':('Menu callback reapplies GetFields ushort+26 through138440.','Named Voice from routing, not from a recovered localization label.'),
'137dc0':('Writes routing selector DWORD8BBD14 used to swap bus2/3 settings groups.','Initializer caller4EDF50 sets this; no extra thread writer was identified.'),
'137f50':('For level1..10, loads float gain table5AB960[level] intoXMM0 and tailcalls079B00 with duration0.','Reset should use the saved master level at+20, not assume100percent.'),
'079b00':('Global master-gain wrapper takes Sound CS and for native SoundDriver dispatches current master virtual+24 with float gain inXMM1.','Trainer uses the common validated BusController ID0 path with1ms instead of this0ms wrapper.'),
'137d50':('For valid saved level1..10, constructs BusController ID1 and applies the table gain.','The semantic Music label is routing inference; bus1 identity and settings field+22 are exact.'),
'138290':('For saved level1..10, applies gain to bus(8BBD14?3:2), then buses4..8.','This group is used as Effects; all six targets need preflight before any trainer write.'),
'138440':('For saved level1..10, selects bus(8BBD14?2:3); if unswapped and8BBD18 is set, multiplies gain by float5AAA40=0.9.','Read the current routing flags and factor with the gain transaction.'),
'138ab0':('BGM playback path has explicit Play BGM/BGM diagnostic strings and tracks active entries of kind1.','This supports a music subsystem label but is not itself a complete proof that every bus1 producer is music.'),
'0936a0':('SoundDriver factory builds controller.vtable61ACD0, controller.id at+8 and nonowning backend pointer2B81DE8 at+16.','Does not validate bus ID; ApplyPlan must validate target buses independently.'),
}
claims=[]
for rva,(finding,limit) in findings.items():
    addr=hex(0x140000000+int(rva,16))
    assert addr in functions,addr
    claims.append({'addr':addr,'rva':hex(int(rva,16)),'Finding':finding,'Evidence':[proofs[addr]],'Limitations':limit,'strength':'fresh complete pseudocode and assembly; inference boundaries stated'})
checks=[]
for addr,e in functions.items():
    a=e['assembly']; c=e['code']
    checks.append({'addr':addr,'codeComplete':bool(c.get('cursor',{}).get('done')),'assemblyComplete':bool(a.get('cursor',{}).get('done')) and a.get('instruction_count')==a.get('total_instructions'),'instructions':a.get('instruction_count')})
assert all(x['codeComplete'] and x['assemblyComplete'] for x in checks)
contract={
'thread':'Only the existing validated application post-Update hook on the recorded engine thread, after originalUpdate returns0. Never worker thread, shutdown callback or DLL detach.',
'serialization':'TryEnterCriticalSection(base+2B81278); retain lock through graph validation, temporary controllers, every gain setter and readout copies. Always Leave in finally. Busy means retry/invalid snapshot.',
'lifetime':'121D90 sequences Init/Update/Shutdown on one thread. Shutdown joins both timer workers before08FA20. Graph nonnull checks alone are insufficient outside this call site.',
'roots':{'driver':'[base+2B81DE0], vtable61B760, BYTE+52 ready','master':'[base+2B811D0], vtable61DA28 or621998; child list+336/count DWORD+344 must match globals','busList':'[base+2B811C8], count DWORD2B811A4, IDi atlist[i-1]','lock':'base+2B81278, process static initialization001000 / exit571EB0 documented in audio_independent'},
'setter':'Construct079C90(Controller*,unsignedID); verify24-byte result;07FAD0(Controller*RCX,floatGainXMM1,unsignedDurationR8D=1); destroy07F7E0. Gain finite0..1. No new arbitrary function pointer call.',
'slots':{'144':'Master one-time0..100%','145':'Bus1/Music one-time0..100%','146':'Effects native group, one-time0..100%','147':'Voice native group with current0.9 factor, one-time0..100%','148':'Apply all four loaded Settings ushort+20/+22/+24/+26, each1..10, through native gain table; no settings/file write','149':'Bus count','150..158':'Current first gain stage of IDs0..8 in percent','159':'Audio graph ready'},
'groupMapping':{'master':0,'music':1,'effects':'(8BBD14?3:2),4,5,6,7,8','voice':'8BBD14?2:3; multiply gain by0.9 only when!8BBD14&&8BBD18'},
'readouts':'Copy under the same outer CS: stage+32 current,+36 target,+44 remaining. Pause bytes+332/+333 may be added separately. Gain is not audible loudness.',
'ownership':'One-time change. Native later settings/fades remain authoritative. No permanent override, observer hook, automatic restore or pause/stop/Jukebox action.',
'labels':'Master and bus routing exact. Music/Effects/Voice are subsystem/routing labels; no direct English localization label for the last three saved fields was recovered here.',
'limitations':['No live audio/game test in this research.','An external mod invoking private teardown/reset from another thread is outside the validated native-lifecycle contract.','08DB30 has no identified runtime entry in this image; arbitrary computed calls cannot be disproved by finite static scans.','Graph snapshots are coherent under the lock, but the game may change gain immediately after lock release.']}
report={'title':'Audio lifetime and global-lock closure','date':'2026-10-04','buildSha256':'9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed','conclusion':'Normal native application lifetime and all identified bus-update paths support one-time gain actions and coherent snapshots at the existing post-update hook under global Sound CS. This closes the earlier audio_independent lifetime blocker for that specific call site.','scope':'Read-only IDA, complete dedicated assembly, pseudocode, xrefs and raw PE/CLR/export audit. No product changes, game calls or live observations.','contract':contract,'claims':claims,'completeBodyChecks':checks,'evidenceHashes':{n:hashlib.sha256((dest/n).read_bytes()).hexdigest() for n in sources+['audio_lifecycle_indirect_audit.json','audio_lifecycle_driver_xrefs.json']}}
(dest/'audio_lifecycle.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
lines=[report['title'],report['conclusion'],'',f"{len(claims)} scoped claims; {len(checks)} fresh complete function bodies and dedicated disassemblies.",'','CORE CONTRACT']
for k,v in contract.items(): lines.append(k+': '+(v if isinstance(v,str) else json.dumps(v,ensure_ascii=False)))
lines+=['','REACHABILITY AUDIT','08DB30 has no normal code caller, raw full-VA pointer, CLR MethodDef or export. Its sole32-bit RVA occurrence is the .pdata RUNTIME_FUNCTION descriptor08DB30..08DC78/unwind6975B0. This is a narrow static result, not a proof against arbitrary computed/external calls.','','FUNCTION FINDINGS']
for c in claims: lines.extend([c['addr']+' '+c['Finding'],'  Limit: '+c['Limitations'],'  Evidence: '+', '.join(c['Evidence'])])
lines+=['','VALIDATION','All included decompiler cursors and dedicated assembly cursors are complete; instruction_count equals total_instructions. Earlier baseline001000/571EB0/091470 is retained in audio_independent_evidence.json. No live tests were performed.']
(dest/'audio_lifecycle.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'claims':len(claims),'fullFunctions':len(checks),'output':['audio_lifecycle.json','audio_lifecycle.txt']},indent=2))
