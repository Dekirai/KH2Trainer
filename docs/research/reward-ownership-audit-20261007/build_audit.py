"""Generate the reviewed 59-row classification; not a product/catalog generator."""
from pathlib import Path
from collections import Counter
import hashlib, json, re
from zipfile import ZipFile

folder=Path(__file__).resolve().parent; root=folder.parents[2]
archive_path=root/'artifacts/packages/KH2_Trainer_v0.12.4/Source.zip'
archive=ZipFile(archive_path)
# Bind the classification to the shipped pre-fix baseline. Concurrent follow-up
# edits (including this turn's Ghost Walk and native generation fixes) are separate receipts.
def read(p): return archive.read(p).decode('utf-8-sig')
def sha(p): return hashlib.sha256(archive.read(p)).hexdigest()
catalog=json.loads((folder/'catalog-runtime.json').read_text(encoding='utf-8-sig'))
features={x['Id']:x for x in json.loads(read('src/KH2Trainer/Data/features.json'))}
catalog_path='src/KH2Trainer.Twitch/Effects/EffectCatalog.cs'
model_path='src/KH2Trainer.Twitch/Effects/EffectModel.cs'
cs=read(catalog_path)
groups={}
def add(keys, scope, restore, native, role, gaps, priority='P2'):
    for key in keys.split():
        assert key not in groups
        groups[key]=dict(storageScope=scope,restoration=restore,nativeSources=native.split(),
                         roleAssessment=role,limitations=gaps,priority=priority)
add('heal restore-mp full-restore one-hp','current_actor_status_one_shot','No timed inverse. HP/MP call validation occurs again on the game thread.',
    'PlayerFeatures.inl PlayerHealthSupport.inl','Already FieldPlayers, with native coherent Sora/Roxas/rescue-Mickey checks and HP/HUD/MP prerequisites.',
    'HP+MP and the one-hp autoheal-disable command are separate effects, not an atomic host transaction. No old HP/MP is restored.', 'P3')
add('regen infinite-mp','bridge_policy_current_actor','OwnedValue restores the bridge boolean; the native policy resolves the current actor each tick.',
    'PlayerFeatures.inl PlayerHealthSupport.inl','Already FieldPlayers. Infinite MP has dynamic MP-gauge ActiveCheck; no usable gauge pauses duration.',
    'Boolean ownership remains value-based against other manual writers; this is not an old STATUS-pointer restore. HP already healed is intentionally retained.', 'P2')
add('refill-drive drain-drive','current_actor_status_one_shot','No inverse; gauge mode and limits checked natively.',
    'PlayerFeatures.inl','Keep Sora: exposing a Drive gauge on another role is not proved by common STATUS layout.',
    'Drain bars and fraction are separate awaited writes; role or gauge can change between commands. Native per-command guards remain.', 'P2')
add('care-package megalixir mystery-gift potion-thief','save_inventory_one_shot','Persistent stock mutation; no timed original/restore.',
    'ProgressionFeatures.inl','Sora-only host policy is stricter than native SaveReady. Roxas is a plausible shared-save candidate; Mickey and native item side effects need their own call-path proof.',
    'Host reads selected stock then sets a quantity; concurrent inventory/selected-item changes can race. Multi-item gift deliberately keeps partial success.', 'P2')
add('munny-gift pickpocket','save_scalar_one_shot','Persistent int32 Save+9280 write; no inverse.',
    'ProgressionFeatures.inl','Native slot80 checks SaveReady, not character1. FieldPlayers extension is structurally plausible for the shared save; clarify persistent-save meaning before admission.',
    'Host read-modify-set is not atomic with gameplay munny changes.', 'P2')
add('exp-gift','save_progression_one_shot','Native3ECF30 adds global EXP and level rewards; no inverse.',
    'ProgressionFeatures.inl','Keep current policy pending complete reward/HUD/resource proof for all roles. CanRefresh rejects unsupported form-save rebuilds.',
    'Generic save arithmetic does not prove every character-specific reward callback is safe.', 'P3')
add('power-boost','character_save_one_shot','Native3C09D0 increments the freshly resolved character Strength boost; no timed inverse.',
    'PlayerFeatures.inl ProgressionFeatures.inl','Potential Roxas shares CharacterIndex14→1, but current save/backlink/type guards must be proved for the intended role. No blanket Mickey expansion.',
    'Persistent boost ownership differs from temporary runtime modifier ownership.', 'P3')
add('invincible','native_damage_callback_policy','Native GuardLease captures player/status/scene pointers and patches one callback slot.',
    'CombatFeatures.inl PlayerRoleSupport.inl','Confirmed blocker: guard requires descriptor74A518 while Sora/Roxas750300 and Mickey7523B8 use different callback slots.',
    'Current supported roles cannot satisfy StartGuard. A repaired guard also needs ActorGeneration; pointer equality alone cannot detect same-address reconstruction.', 'P1')
add('lucky-streak magnet tax-collector','actor_status_scalar_restore','OwnedValue with approximate value comparison; no ActorGeneration or STATUS-rebuild receipt.',
    'LootFeatures.inl DamageTuningFeatures.inl CombatFeatures.inl','Native path already lacks character1 restriction, with pool/list/backlink checks. Candidate for FieldPlayers only after atomic generation-bound STATUS transaction.',
    'Same-value new actor can receive an old original. Same actor STATUS rebuild resets these values (3C1D90→4016B0). Lucky pair uses separate awaits; missing starting values default to0.', 'P1')
add('glass-cannon','actor_status_scalar_restore','OwnedValue saves/restores BYTE STATUS+430 using the current actor at each generic command.',
    'DamageTuningFeatures.inl CombatFeatures.inl','Generic allocated STATUS path is a plausible FieldPlayers candidate after typed ownership, not a safe policy-only change.',
    '250 is a received-hit coefficient, not a final-HP multiplier. Same-value actor/rebuild replacement can receive stale original; host read→write is non-atomic.', 'P1')
add('super-speed snail moon-jump','actor_generation_transaction','Protocol4 MOV1 native journal: atomic mask, exact Float32, pinned ActorGeneration, receipts and deferred release.',
    'MovementTransactionSupport.inl ActorLifetimeSupport.inl ActorMovementFeatures.inl','Already FieldPlayers. These three are the solved reference rows, not remaining scalar-restoration findings.',
    'Observer loss or ambiguous acknowledgement freezes ownership/ordinary mutations until a provable resolution. Inherited external same-value writes are not inferred as ownership.', 'P3')
add('eagle-eye short-sighted','global_coupled_scalar_restore','OwnedValue observes only scale; native setter also rewrites the independent break-distance global.',
    'TargetingFeatures.inl ActorMovementFeatures.inl','Current native TargetingReady deliberately uses legacy Sora-only Ready. Role-independent storage alone does not remove player lock-on prerequisites.',
    'Scale2A1141C and break distance2A11420 form a coupled pair. End can overwrite a manual break-distance change while scale stayed unchanged. Needs native atomic pair compare/apply.', 'P1')
add('enemy-glass-cannon heal-enemy enrage-enemy','fresh_manual_target_one_shot','No retained target or inverse. Each command validates bounded live list, target/current backlinks and live HP.',
    'CombatFeatures.inl DamageTuningFeatures.inl','Sora-only host policy; native GetTarget is not char1-specific. Roxas/Mickey potential requires proving their LockRva owner/input path, not merely a common actor.',
    'The enemy under lock when the command executes can differ from host snapshot. HP/revenge/coeff edits intentionally remain.', 'P2')
add('valor wisdom limit master final antiform roulette','sora_transition_and_bridge_policy','Native queued Revert→Form lifecycle plus OwnedValue for formtimer. End conditionally requests Revert.',
    'DriveFeatures.inl DriveWeaponSupport.inl PlayerFeatures.inl','Sora only by native transition contract; do not expand Roxas/Mickey.',
    'Host completion observes form/phase/result/requested, without a per-redemption transition receipt. Another same-form transition may be indistinguishable. Native context/source/task binding protects queued steps; formtimer is a shared bridge policy.', 'P2')
add('revert','sora_transition_one_shot','Native Revert lifecycle; no timed inverse.',
    'DriveFeatures.inl','Sora only. Other roles explicitly rejected natively.',
    'Queued acceptance is not immediate completion; cancellation stops trainer follow-up, not an already running native fiber.', 'P3')
add('gummi-repair gummi-clear','gummi_current_lifetime_one_shot','Native command with freshly compared ship/module or pool/task owner; no inverse.',
    'GummiFeatures.inl GummiProjectileFeatures.inl','Field role admission deliberately disabled; Gummi module/mission readiness governs.',
    'Clear removes hostile projectiles, not an undoable effect. Current guards exclude destroying pool members and stale cleanup owners.', 'P3')
add('reload-room','scene_transition_one_shot','Native434CF0 with current full10-byte MapTarget; no inverse.',
    'WorldFeatures.inl','No native char1 prerequisite in handler. Possible controlled FieldPlayers extension after auditing scene/mission consequences.',
    'Room transition intentionally replaces actors/resources and may affect scripts/checkpoints.', 'P3')
add('fast-forward slow-mo','bridge_timing_policy','OwnedValue restores shared multiplier; task hook keeps native timing/step semantics.',
    'WorldFeatures.inl','No character-specific native timing path; strongest low-complexity FieldPlayers admission candidates.',
    'Not actor memory. Value-only ownership can overwrite a same-valued manual policy; no owner token. Gameplay and mission effects of time scaling still apply.', 'P2')
add('fisheye tunnel-vision','scene_camera_policy','Captures FOV/enabled, native camera scene lease; customEnd requires enabled+matching FOV before restore.',
    'WorldFeatures.inl','Normal owner0/submode0 follow camera required, without char1 gate. FieldPlayers plausible after role camera fixture checks.',
    'Host restore is read→command, not atomic pair compare. Native scene loss clears the override, but a new same-valued override is not a host ownership receipt.', 'P2')
add('camera-glitch','scene_camera_policy','OwnedValue for free-camera and roll; native renderer owns eye/target/up held state under scene lease.',
    'WorldFeatures.inl CameraExtraFeatures.inl','No direct char1 requirement for held camera. Role camera availability still gates.',
    'Restoring a free-camera boolean may recapture pose rather than restore the original held pose. Roll and free-camera are separate commands; shared manual camera state has no reward owner.', 'P2')
add('slowpoke hyper','actor_motion_native_lease','Bridge desired speed plus pointer/scene/model-bound native override; VM42FCE0 observer revokes even same-float script writes.',
    'MotionFeatures.inl','Native ActorReady explicitly Sora-only. Common constructor/storage alone does not prove alternate-role motion resources/ABI.',
    'Native lease has no ActorGeneration. Host sustain re-enables override after script/native revocation, so one-shot native ownership policy can be overridden by CC. Desired value restoration is global and separate from actor baseline.', 'P1')
add('color-chaos','global_color_atomic_compare','Native464 atomically compares complete mode/severity pair under validated GX mutex and applies only color.',
    'DisplayFeatures.inl','Already FieldPlayers, renderer-driven independent of actor.',
    'Changed pair yields successful no-op. Same-value ABA/manual rewrite cannot be distinguished without a writer token; this limit is explicit.', 'P3')
add('silence mute-voices','global_audio_scalar_restore','OwnedValue scalar target-gain restore; each native command locks and revalidates the current audio graph.',
    'AudioFeatures.inl','Already FieldPlayers; audio graph and thread/lifetime gates independent of character.',
    'Host compare and setter occur separately. Graph replacement or same-value other writer can receive old target; voice logical bus routing can change.', 'P2')
add('ghost-walk','actor_position_and_collision_lease','Bookmark plus collision pointer lease; host tries native return then raw XYZ fallback, then room reload.',
    'PlayerFeatures.inl','Keep role policy until native ActorGeneration ownership and callback path are complete. Sora-only does not prevent Sora→Sora.',
    'Confirmed unsafe bypass: same world/room is weaker than rejected native bookmark identity. Both XYZ and reload fallback must be removed. Bookmark is globally shared and can be replaced manually.', 'P1')
add('deja-vu','actor_position_bookmark_lease','Only native bookmark/return, charged after successful cleanup.',
    'PlayerFeatures.inl','Same actor/scene identity required. Potential all supported roles after generation-bound bookmark and native position-call proof.',
    'Current bookmark pointer/status/room lease has no generation and no reward owner ID; a same-actor manual bookmark can replace the reward origin.', 'P1')
add('hacker-mode','global_debug_desktop','Custom show then unconditional hide; no original visibility capture or owner receipt.',
    'TrainerBridge.cpp','Native menu dependencies are global, but developer actions can be Sora-specific. Do not broadly extend merely because desktop can draw.',
    'End may hide a preexisting/manual desktop; hidden desktop task guard still prevents unsafe update while unavailable.', 'P2')
add('time-stop freeze-frame','native_scene_pause_policy','OwnedValue restores bridge-owned pause bit/phase; native lease compares scene and preserves known foreign ownership.',
    'WorldFeatures.inl','Field/global scheduling, no char1 gate. FieldPlayers is plausible with matching controlled-role readiness and own-pause exception tests.',
    'Scene witness consists of pointer/map values, not a full scene generation. Same-value manual takeover has no owner token. Actor freeze and field pause have different timing scope.', 'P2')
add('pause-menu','global_menu_action','Native context/menu request; no inverse.',
    'WorldFeatures.inl','Native pause prerequisites are global, not character1. Candidate after targeted alternate-role scene/menu tests.',
    'Player-control snapshot can change before command; native guards are the final admission.', 'P3')
add('lights-out flashbang','global_brightness_scalar_restore','OwnedValue saves original brightness; native brightness-only setter under GX mutex.',
    'DisplayFeatures.inl','Already FieldPlayers.',
    'Unlike color compare/apply, native setter is unconditional after host value check; same-value writer and check→write race remain. Does not restore loaded color settings.', 'P2')
add('no-subtitles','global_flag_bit_restore','OwnedValue for shared bit; native SetBit preserves unrelated flag bits and records bridge ownership.',
    'WorldFeatures.inl','Already FieldPlayers; no actor pointer is restored.',
    'Cannot attribute same-valued changes by another owner to a particular reward.', 'P3')
assert len(catalog)==len(groups)==59 and {x['Key'] for x in catalog}==set(groups)
rows=[]; paths={catalog_path,model_path,'src/KH2Trainer/Data/features.json'}
for r in catalog:
    k=r['Key']; g=groups[k]; line=next((i+1 for i,s in enumerate(cs.splitlines()) if '"'+k+'"' in s),None)
    native=[]
    for filename in g.pop('nativeSources'):
        p='src/KH2Trainer.Bridge/'+filename
        if p not in archive.namelist(): raise AssertionError(p)
        paths.add(p); native.append(p)
    ff=[]
    for fid in r['Features']:
        f=features[fid]
        ff.append({x:f.get(x) for x in ['Id','CommandId','ValueSlot','CapabilitySlot','Kind','Minimum','Maximum','RequiresScene','ChangesProgression']})
    rows.append({'key':k,'title':r['Title'],'durationSeconds':r['DurationSeconds'],'group':r['Group'],
       'roleMask':r['AllowedRoles'],'roles':['Sora','Roxas','Mickey'] if r['AllowedRoles']==7 else ['Sora'],
       'requiresPlayerControl':r['RequiresPlayerControl'],'chargeAfterEnd':r['ChargeAfterEnd'],
       'isExistingJournalReference':k in {'super-speed','snail','moon-jump'},**g,
       'features':ff,'sourceAnchor':{'path':catalog_path,'line':line},'nativeSources':native})
snapshot={'schemaVersion':1,'date':'2026-10-07','status':'STATIC_SOURCE_AUDIT_BASELINE_BEFORE_FOLLOWUP_FIXES',
 'baselineArchive':{'path':str(archive_path.relative_to(root)).replace('\\','/'),'sha256':hashlib.sha256(archive_path.read_bytes()).hexdigest()},
 'scope':'59 total rewards in the shipped source catalog; 3 movement journal reference rows and 56 remaining rewards. Classification is not a claim of exhaustive native semantics or live validation.',
 'counts':{'total':59,'existingJournalReferences':3,'remaining':56,'timed':sum(r['durationSeconds']>0 for r in rows),
           'priority':dict(Counter(r['priority'] for r in rows))},
 'commonLimitations':['Sora-only admission is not an actor-lifetime proof. A same-role actor may be reconstructed.',
 'OwnedValue uses Near tolerance, separate host reads and generic awaited writes; it does not bind an ActorGeneration or native compare receipt.',
 'One-shot save, HP, enemy and menu operations have no old-original restore and must not be conflated with temporary actor leases.',
 'Role potential is a scoped design candidate, not an implemented role allowlist. Existing downstream gates continue to decide native availability.'],
 'sources':[{'path':p,'sha256':sha(p)} for p in sorted(paths)],'rewards':rows,
 'freshNativeEvidence':'native-evidence-full.json','nativeOriginalValidation':'native-validation.json'}
(folder/'rewards.json').write_text(json.dumps(snapshot,indent=2)+'\n',encoding='utf-8')
extract=[]
for p,needle,n in [(catalog_path,'Key = "ghost-walk"',37),(model_path,'public async Task SetAsync',77),
 ('src/KH2Trainer.Bridge/CombatFeatures.inl','bool StartGuard',18),('src/KH2Trainer.Bridge/PlayerFeatures.inl','void PlayerTick',14)]:
    lines=read(p).splitlines(); start=next(i for i,l in enumerate(lines) if needle in l)
    extract.append({'path':p,'sha256':sha(p),'firstLine':start+1,'lines':lines[start:start+n]})
(folder/'baseline-source-excerpts.json').write_text(json.dumps(extract,indent=2)+'\n',encoding='utf-8')
lines=['59-reward ownership and role audit (static baseline, 2026-10-07)',
       '59 total = 3 generation-journaled movement rewards + 56 other rewards. No game execution.',
       'Detailed machine-readable schema, native sources and source hashes: rewards.json.','']
for r in rows:
    lines += [f"{r['key']} [{r['priority']}; {r['storageScope']}; roles={','.join(r['roles'])}]",
              '  Restore: '+r['restoration'],'  Role: '+r['roleAssessment'],'  Limit: '+r['limitations'],'']
(folder/'rewards.txt').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps(snapshot['counts']))
