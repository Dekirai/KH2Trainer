"""Assemble the actual reviewed feature contracts and local English catalogs."""
from pathlib import Path
import json
import shutil

root = Path(__file__).resolve().parent
research = root.parent / 'work' / 'trainer' / 'research'
data = root / 'KH2Trainer' / 'Data'
data.mkdir(parents=True, exist_ok=True)
features = []
for domain in ('player', 'world', 'progression', 'combat', 'drive', 'gummi', 'audio', 'motion', 'rescue', 'render', 'missions', 'cameraextra', 'damagetuning', 'display', 'missionevents', 'gummi_extra', 'actormovement', 'loot', 'gummi_projectile', 'targeting', 'collision', 'renderer_diagnostics', 'spatial_audio', 'gummi_editor', 'window_display', 'renderer_aa'):
    path = research / f'{domain}_features.json'
    if not path.exists() and domain == 'progression':
        path = root / 'KH2Trainer.Core' / 'progression_features.json'
    features.extend(json.loads(path.read_text(encoding='utf-8-sig')))
for feature in features:
    if feature['Category'] == 'Combat practice':
        feature['Category'] = 'Combat Practice'
    if feature['Id'].startswith('drive.'):
        feature['Category'] = 'Drive and Forms'
for slot, ident, name, description, scene in (
    (112, 'developer.show', 'Show developer tools', 'Open the native developer desktop. Hold right Ctrl while using its mouse controls; F10 toggles visibility.', True),
    (113, 'developer.hide', 'Hide developer tools', 'Hide the native developer desktop and suppress its hidden debug shortcuts.', False),
    (114, 'trainer.reset', 'Disable all effects', 'Disable continuous trainer effects and restore owned temporary camera, timing, animation and rendering changes. Completed one-time actions remain applied.', False),
):
    features.append(dict(Id=ident,Category='Developer Tools',Name=name,Description=description,Kind='Action',CommandId=1000+slot,ValueSlot=-1,CapabilitySlot=slot,Minimum=0,Maximum=0,DefaultValue=0,RequiresScene=scene,CanSaveInProfile=False,ChangesProgression=False,RestoreBehavior='',Evidence=[dict(Address='TrainerBridge.cpp / RVA 0x41FCD0',Finding='Validated game-thread bridge command; native debug root initialized once and guarded during scene changes.',Level='Implementation tested with isolated fixtures; live integration pending')]))
features.append(dict(Id='trainer.shortcuts',Category='Keyboard Shortcuts',Name='Enable training shortcuts',
    Description='While KH2 has focus, hold Ctrl: F5 disables effects and shortcuts; F6 restores HP/MP; F7 bookmarks; F8 returns; F9 freezes actors/effects; F11 pauses the field; F12 steps it. F10 controls the developer desktop separately.',
    Kind='Toggle',CommandId=1118,ValueSlot=118,CapabilitySlot=118,Minimum=0,Maximum=1,DefaultValue=0,
    RequiresScene=False,CanSaveInProfile=True,ChangesProgression=False,
    RestoreBehavior='Disabled on disconnect, heartbeat expiry, or Disable all effects. Actions use the same scene and object checks as the trainer buttons.',
    Evidence=[dict(Address='ShortcutFeatures.inl / TrainerBridge.cpp',Finding='Game-thread key edges, foreground and heartbeat gates; existing validated Player/World handlers perform actions.',Level='Isolated input-state tests; live integration pending')]))
ids = [x['Id'] for x in features]
slots = [x['CapabilitySlot'] for x in features]
assert len(set(ids)) == len(ids), 'Duplicate feature IDs'
assert len(set(slots)) == len(slots), 'Duplicate capability slots'
assert all(0 <= s < 512 for s in slots)
features.sort(key=lambda x:x['CapabilitySlot'])
(data/'features.json').write_text(json.dumps(features,ensure_ascii=False,indent=2),encoding='utf-8')
shutil.copy2(research/'item_catalog_en.json',data/'items.json')
shutil.copy2(research/'ability_catalog_en.json',data/'abilities.json')
shutil.copy2(research/'character_catalog_en.json',data/'characters.json')
print(f'Assembled {len(features)} evidenced feature entries across {len(set(x["Category"] for x in features))} categories.')
