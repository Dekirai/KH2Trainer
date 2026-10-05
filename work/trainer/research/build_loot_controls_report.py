"""Record reviewed loot semantics and the exact implemented trainer contract."""
from pathlib import Path
import json, hashlib

here=Path(__file__).resolve().parent
root=here.parents[2]
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
asm=read(here/'loot_controls_deep_asm.json')['functions']
by={f['addr']:f for f in asm}
for f in asm:
    lines=[line for p in f['pages'] for line in p['asm']['lines']]
    assert len(lines)==f['instructionCount']==f['pages'][0]['total_instructions']
    assert len({line['addr'] for line in lines})==len(lines)
    assert f['pages'][-1]['cursor']['done']
findings={
'0x1404016b0':'Initializes the ability subobject: its owner pointer at+40 is STATUS, Draw+56, Jackpot+104 and Lucky+108 start at0, while munny-retention multiplier+116 starts at1.',
'0x140401730':'Ability405 adds the global parameter+300 to Draw;406 adds+348 to Jackpot;407 adds+352 to Lucky;540 multiplies retention by parameter+368. It also sets the item-defined ability bit.',
'0x1403d7470':'Returns Actor.status at Actor+1472 plus464, proving the absolute STATUS fields520,568,572 and580 used by the loot controls.',
'0x1403c1d90':'Rebuilds character STATUS from saved data and resets/recomputes the ability subobject before applying equipment and enabled abilities; one-time loot edits can be replaced.',
'0x1403c2120':'Copies selected HP/MP/gauge values back to save records; none of the four loot modifier fields is copied.',
'0x1403aba40':'Computes a float32 orb-quantity factor from script base2A11418 plus Jackpot for three listed non-deleting party actors with STATUS. It does not require their HP to be positive.',
'0x1403abab0':'Initializes script orb-quantity base2A11418 to float1 alongside the game-mode flags and adjacent parameters.',
'0x1404308c0':'VM adapter directly copies the first operand float bits to script orb-quantity base2A11418.',
'0x1403d5c50':'Party index0 returns the current player global; later indices call the ally getter with index-1.',
'0x1403c3270':'Returns a QWORD from the ally array2A239B0 indexed by the caller; the getter itself has no bounds check.',
'0x1403ba720':'Accepts an actor only when the live-list membership helper succeeds and Actor.flags288 has neither0x10000000 nor0x80000.',
'0x1403bfb70':'Traverses the packed-next actor list at2A171C8 until the requested actor is found; returns true on membership and false at the end. The trainer adds a bound/cycle check.',
'0x1403dc170':'Loads a24-byte prize-table row, generates nine orb kinds using ceil(base count*party quantity), and applies the product of retention fields to kinds2..4 (munny). Truncated retained count remains munny; the remainder maps to Drive kinds. Outside the special player mode, three item entries roll separately against rate*(1+sum Lucky), subject to the ordinary global suppression flags. ASM proves the RNG dword is zero-extended before float conversion and the quantity is the third XMM argument omitted by older decompilation.',
'0x1403ecef0':'Returns ceilf(unsigned byte prize count at row+2+kind multiplied by third argument XMM2).',
'0x1403ecc70':'Binary-searches24-byte prize rows by ID, falling back to ID72 when absent; it does not prove that a missing fallback is safe.',
'0x1403dc3d0':'Attempts the requested positive number of pooled orb creations using a16-byte kind definition, then assigns randomized initial velocity to successful results.',
'0x1403f8170':'An item drop allocates a3040-byte actor and selects its model from the item icon/type data, initializes pickup state and attaches its actor controller. It creates a world pickup rather than directly granting inventory.',
'0x1403dc500':'Normal pickup testing rejects defeated actors, permits a model flag override, then compares horizontal distance to120+Draw (category4 only)+STATUS452 and vertical distance to30. Explicit positive radius/height arguments override the defaults.',
'0x140413540':'Only pickup-active pooled orbs run the spatial test; their definition height offset adjusts the position before delegating to3DC500.',
'0x1403dc7c0':'The normal orb callback iterates three party actors and applies pickup rules. Non-player actors cannot take Drive kinds7/8, and player Antiform6 is skipped for HP kinds0/1. A larger Draw value does not remove these rules.',
'0x1403dca50':'Applies the per-kind HP,MP,Drive and Munny effects through their native handlers after a pickup. The constant table distinguishes all nine kinds and their amounts.',
'0x1403dc0d0':'Bulk collection walks the current prize pool and selects pickup-active entries, scheduling their collection toward the player and applying effects. It assumes live player/pool/resources and invokes sound paths; this body is documented but not exposed as an unchecked action.',
'0x140413650':'Starts collection movement, stores the target actor and switches the update callback, then plays spatial sound while holding the native sound mutex.',
'0x140411b70':'Returns the pool head when no previous entry is supplied, otherwise decodes the packed next pointer at entry+36.',
'0x140413f00':'Requests a232-byte orb only when the pool reports availability, initializes it and marks a byte at+26. Allocation success is assumed at the later store; arbitrary direct use requires more than an address.',
'0x140414310':'An additional active prize subsystem scales all nine input orb counts using the same Jackpot quantity helper, then uses a separate mapping and pool.',
'0x140414b50':'Another active prize subsystem uses the Jackpot helper and may double its result when its separate counter is positive; it also derives up to six extra prizes from another native counter.',
'0x140415840':'Tests whether the current valid player carries category flag0x2000000, which selects an alternate prize mapping in3DC170.',
'0x1403f7df0':'Item pickup checks player type, pickup state and normal Draw distance, with extra native auto-collection and special-model branches.',
'0x1403f8400':'The companion item update callback uses the same spatial and special auto-collection gates; changing Draw alone does not bypass those gates.'
}
claims=[]
for addr,finding in findings.items():
    assert addr in by,addr
    claims.append(dict(addr=addr,Domain='native',Finding=finding,
        Evidence=[f'loot_controls_deep_asm.json:{addr}'],
        Limitations='Bounded static function/path claim; no gameplay execution and no claim that all downstream resources or scripts are understood.'))
report=dict(title='Loot generation, conversion and collection',completeFunctionBodies=len(asm),
    actualInstructions=sum(f['instructionCount'] for f in asm),claims=claims,
    implementation=dict(slots='352..355 current-player edits;356..359 derived readouts',
        fields={'draw':520,'jackpot':568,'lucky':572,'munnyRetained':580},
        guards='Current stable living player, game thread, fresh host, bounded live actor list, allocated aligned STATUS and owner backlinks; exact4-byte writable range.',
        lifetime='One-time runtime writes, no save/ability inventory changes, hooks or retained pointers. Equipment/abilities/form/actor changes can recompute them.',
        ranges='Trainer input limits, not claimed native limits: Draw0..5000; Jackpot0..9; Lucky0..99; retained Munny0..100%.',
        example='Base item rate5% with party Lucky bonuses0.5 and0.25 compares8.75 against the native random percentage. The three entries are separate rolls.',
        tests='213 isolated checks initially passed. Release package validation records the final run.'),
    limitations=['Collection still uses a vertical threshold and native player/form/mission rules.',
        'Jackpot can affect alternate native prize subsystems as well as normal HP/MP/Munny orbs.',
        'A high Lucky factor does not create missing table entries, remove drop suppression, or prove a guaranteed final item grant.',
        'No direct spawn/collect-all action is implemented until allocation, pool and sound contracts are complete.'],
    sources={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in [
        'trainer/Native/LootFeatures.inl','work/trainer/tests/LootGuardTests.cpp']})
(here/'loot_controls_deep.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
(here/'loot_controls_deep.txt').write_text('\n'.join([
    report['title'], '='*45, 'Fresh complete native evidence; no gameplay test.',
    f'{len(asm)} complete functions / {report["actualInstructions"]} ASM instructions; {len(claims)} specific claims.',
    '', *[f'{k}: {v}' for k,v in report['implementation'].items()], '',
    *report['limitations'],'',*[c['addr']+' '+c['Finding'] for c in claims]])+'\n',encoding='utf-8')

descriptions=[
('draw','Player Draw radius bonus','Adds horizontal world units to the normal pickup radius. The normal vertical threshold, explicit script radii and form-specific collection restrictions remain.',5000,0,10,'units'),
('jackpot','Player Jackpot bonus','Adds to the party orb-quantity factor. 0 adds nothing; 1 adds one extra base quantity. Counts round upward. Some alternate native prize systems also use this factor.',9,0,.25,'+factor'),
('lucky','Player Lucky Lucky bonus','Adds to the party item-drop factor: 1 plus all eligible party bonuses. Each of the three table item slots rolls separately. Normal suppression flags and pickup rules remain.',99,0,.25,'+factor'),
('retained','Player munny retained','The player contribution to the fraction of munny orbs kept as munny. 100% keeps them; 0% converts them to Drive orbs. Party contributions multiply and retained counts round down.',100,100,5,'%')]
features=[]
for i,(name,title,desc,maximum,default,step,unit) in enumerate(descriptions):
    slot=352+i
    features.append(dict(Id='loot.'+name,Category='Loot and Collection',Name=title,Kind='Number',
        CommandId=slot+1000,ValueSlot=slot,CapabilitySlot=slot,Minimum=0,Maximum=maximum,DefaultValue=default,Step=step,Unit=unit,
        RequiresScene=True,ChangesProgression=False,CanSaveInProfile=False,Description=desc,
        RestoreBehavior=report['implementation']['lifetime'],
        Evidence=[dict(Address='RVA0x401730/0x3D7470/'+('0x3DC500' if i==0 else '0x3DC170'),
            Finding=desc,Level='Complete native ASM and isolated fixtures; no live test')]))
for i,(name,title,desc,unit) in enumerate([
    ('radius','Normal pickup horizontal radius','Default horizontal radius including Draw and the current status bonus; explicit native radius overrides and vertical/form gates are separate.','units'),
    ('party_quantity','Party orb quantity factor','Current script base plus eligible party Jackpot contributions, in native float32 order.','x'),
    ('party_lucky','Party item-drop factor','One plus eligible party Lucky contributions. This is a multiplier of each table rate, not a displayed final probability.','x'),
    ('party_retained','Party munny retained','Product of eligible party retention contributions. Each munny count is multiplied and truncated before the remainder becomes Drive orbs.','%')]):
    slot=356+i
    features.append(dict(Id='loot.'+name,Category='Loot and Collection',Name=title,Kind='ReadOnly',
        CommandId=0,ValueSlot=slot,CapabilitySlot=slot,Minimum=-1000000,Maximum=1000000,DefaultValue=0,Unit=unit,
        RequiresScene=True,ChangesProgression=False,CanSaveInProfile=False,Description=desc,RestoreBehavior='',
        Evidence=[dict(Address='RVA0x3ABA40/0x3DC170/0x3DC500/0x3D5C50',Finding=desc,Level='Read-only calculation from validated current actors and STATUS records')]))
(here/'loot_features.json').write_text(json.dumps(features,indent=2)+'\n',encoding='utf-8')
print(f'Loot: {len(claims)} claims, {len(asm)} complete bodies, {len(features)} feature entries.')
