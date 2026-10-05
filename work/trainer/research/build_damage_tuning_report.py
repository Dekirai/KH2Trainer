"""Assemble bounded damage findings and the implemented runtime coefficient catalog."""
from pathlib import Path
import json

root=Path(__file__).resolve().parent
main=json.loads((root/'combat_scaling_deep_evidence.json').read_text(encoding='utf-8'))
extra=json.loads((root/'combat_scaling_deep_additional_asm.json').read_text(encoding='utf-8'))
functions={f['addr'].lower():f for f in main['functions']}
for f in extra['functions']:
    lines=[line for page in f['pages'] for line in page['asm']['lines']]
    assert len(lines)==f['total_instructions']
    functions[f['addr'].lower()]=f
for f in main['functions']: assert f['instruction_count']==f['total_instructions'] and not f['truncated']

findings={
'0x1403a75f0':'Player damage callback grants mode-dependent Drive from negative HP delta before forwarding to the common HP application path.',
'0x1403d3790':'Decodes the actor controller and dispatches the five-argument HP change callback through vtable+232.',
'0x1403d3ba0':'Hit application checks survival conditions before converting computed damage to a negative HP delta. Attack types5/6 keep positive healing deltas.',
'0x1403d5e50':'Common HP path can grant MP from negative damage while outside MP recharge, then dispatches native HP update and effects.',
'0x1403d2eb0':'Applies native HP changes, updates the matching HUD and invokes the controller death callback when primary HP reaches zero.',
'0x1403c0860':'Clamps HP addition between the selected bar native floor and maximum before storing the new integer HP.',
'0x1403d7470':'Returns the actor status modifier block at STATUS+464.',
'0x1403a9cf0':'Dispatches gauge changes according to Drive/form/summon mode, with native MP-charge and pause modifiers.',
'0x1403d3cf0':'Applies MP change through the native MP setter; underflow starts native recharge.',
'0x1403c0ff0':'Positive damage difficulty helper uses separate target-player and source-player branches, upward integer rounding and four difficulty cases.',
'0x1403cf830':'Constructs ATTACK with initial owner references at+12/+16, attack parameters and pooled list links; attack flags may select another stat owner.',
'0x1403c12f0':'Normal hit arithmetic selects source Strength/Magic, applies target Defense and source/target base floors/caps, then power times general and element received coefficients. Difficulty, special-mode counters, Anti, elemental/ability boosts and low-HP modifiers follow. Types5/6 take an earlier healing branch.',
'0x1403ce740':'Builds a hit, computes its damage and stores it at+40. Zero general-times-element coefficient additionally sets hit flag4 and clears reaction field+38.',
'0x1403cee90':'Recomputes an existing hit using current STATUS coefficients, with the same zero-coefficient reaction suppression.',
'0x1403f7d80':'Returns the static three-DWORD state block atRVA2AE7CC8 consumed by special-mode damage scaling.',
'0x1403d7480':'Bounds the actor combo byte+3444 by the signed status modifier byte+513.',
'0x1403d74a0':'Bounds the actor combo byte+3444 by the signed status modifier byte+512.',
'0x1403c0010':'Initializes632-byte STATUS records, base caps99999, floors1, all seven damage coefficients100 and packed references/null state.',
'0x1403c1190':'Equipment contributes stats and multiplies all seven STATUS coefficient bytes by the item rates, rounding upward before a byte store.',
'0x1403c1d90':'Rebuilds saved-character STATUS, resets coefficients to100, applies equipment and refreshes derived ability modifiers.',
'0x1403dcc10':'Animates HP loss only when the HUD controller matches the damaged actor and bar.',
'0x1403d12c0':'Constructs and classifies a hit; the zero-coefficient flag causes an early return before later visual/reaction setup.',
'0x1403c2240':'Enemy STATUS initialization copies low bytes from EnemyParam ushort fields72..84 to STATUS424..430 and derives incoming base caps/floors from HP percentages.',
'0x1403dcbb0':'Animates HP healing only for the matching HUD actor/bar.',
'0x1403ee8a0':'Returns the12-byte battle-level parameter row at table+(id-1)*12.',
'0x1403ee8c0':'Returns the fallback battle-level parameter address atRVA2AE5980.',
'0x1403c10e0':'Special-mode scaling depends on global2A11400 bit0x20000 and counter+8 plus1, dividing for a player-marked target and multiplying otherwise.',
'0x1403c2650':'Native enemy coefficient setter scales against the original ushort EnemyParam value decoded from STATUS+624, then stores a byte. It is unsuitable as a universal player setter.',
'0x1403c2120':'Save synchronization copies HP/MP, recharge and Drive values; none of the seven runtime received-damage coefficients are copied.',
'0x1403c2100':'Synchronizes supported STATUS fields to their save records, then rebuilds STATUS from saved character data.',
'0x140431200':'VM adapter reads status, coefficient index and percentage from three operand slots and tail-calls the enemy-specific coefficient setter.'
}
claims=[]
for addr,finding in findings.items():
    assert addr in functions,addr
    file='combat_scaling_deep_evidence.json' if addr in {f['addr'].lower() for f in main['functions']} else 'combat_scaling_deep_additional_asm.json'
    claims.append(dict(addr=addr,Domain='Combat damage and runtime coefficients',Finding=finding,
        Evidence=f'{file}:{addr}',Limitations='Specific static body/path claim, not complete system or live gameplay validation. Native signed32-bit arithmetic and later scripts remain in force.'))
report=dict(title='Damage calculation and runtime coefficient controls',scope='Fresh complete ASM plus bounded semantic findings; no game execution.',
    completeFunctionBodies=len(functions),actualInstructions=sum(f['total_instructions'] for f in functions.values()),
    claims=claims,elementNames=dict(source='https://openkh.dev/kh2/file/type/00battle.html#enmp',
      provenance='OpenKh primary format documentation names EnemyParam72..84; native3C2240 proves the corresponding runtime byte mapping.',
      names=['Physical','Fire','Blizzard','Thunder','Dark','Light','General']),
    implementation=dict(source='trainer/Native/DamageTuningFeatures.inl',slots='272..285 editable bytes;286..293 base limit diagnostics',
      lifetime='One-time writes to current player or manually locked living enemy. Pool/list/backlink validation; no pointer retained.',
      persistence='No save, source EnemyParam or item table writes. Native rebuilds/equipment/scripts may replace values.',
      exclusions='Attack types5/6 and direct HP/script changes are separate. Zero also suppresses a native hit-response path. This is not guaranteed invulnerability.'),
    openWork=['General outgoing damage controls','Complete meaning/lifecycle of special-mode counter+8','Every native hit-response and script branch','Live runtime validation'])
(root/'damage_tuning.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')

features=[]
for target in range(2):
    who='Target' if target else 'Player'
    for i,name in enumerate(report['elementNames']['names']):
        slot=272+target*7+i
        features.append(dict(Id=f'damage.{who.lower()}.{name.lower()}',Category='Damage Tuning',
            Name=f'{who} {name.lower()} damage received',Kind='Number',CommandId=1000+slot,ValueSlot=slot,CapabilitySlot=slot,
            Minimum=0,Maximum=255,DefaultValue=100,Step=1,Unit='%',RequiresScene=True,ChangesProgression=False,CanSaveInProfile=False,
            Description=(f"Set the {'manually locked living enemy' if target else 'living player'}'s {name.lower()} received-hit factor. "
              +('This general factor combines with the matching element factor. ' if i==6 else 'This factor combines with the general factor. ')
              +'100% is neutral for this factor. Healing and direct scripted HP changes use separate paths; later damage modifiers still apply. Zero also suppresses a native hit response.'),
            RestoreBehavior='Applied once to the current actor. Equipment, scripts, status rebuild or actor replacement can recalculate it. No automatic reset and no profile replay.',
            Evidence=[dict(Address=f'STATUS+{424+i}; RVA0x3C12F0/0x3CE740/0x3CEE90',
              Finding='Validated runtime byte coefficient used before later difficulty/ability modifiers. Current actor and allocated status are resolved for each request.',
              Level='Complete native ASM and synthetic guards; no live test'),
              dict(Address='https://openkh.dev/kh2/file/type/00battle.html#enmp; RVA0x3C2240',Finding='Element naming follows the documented EnemyParam fields and the verified native copy into STATUS.',Level='Primary format documentation plus native field mapping')] ))
    for i,(name,detail) in enumerate([
        ('outgoing base cap','Upper bound contributed by the source status before attack power and received-damage coefficients.'),
        ('outgoing base floor','Lower bound contributed by the source status before attack power and received-damage coefficients.'),
        ('incoming base cap','Upper bound contributed by the target status before attack power and received-damage coefficients.'),
        ('incoming base floor','Lower bound contributed by the target status before attack power and received-damage coefficients.')]):
        slot=286+target*4+i
        features.append(dict(Id=f'damage.{who.lower()}.base_limit{i}',Category='Damage Tuning',Name=f'{who} {name}',
            Kind='ReadOnly',CommandId=0,ValueSlot=slot,CapabilitySlot=slot,Minimum=-2147483648,Maximum=2147483647,DefaultValue=0,
            RequiresScene=True,ChangesProgression=False,CanSaveInProfile=False,Description=detail+' This is not a final HP-damage limit.',
            RestoreBehavior='Current status diagnostic; target requires manual lock-on.',
            Evidence=[dict(Address=f'STATUS+{408+4*i}; RVA0x3C12F0',Finding='Integer clamp input read before the power/coefficient multiplication.',Level='Full ASM verified')]))
(root/'damagetuning_features.json').write_text(json.dumps(features,indent=2)+'\n',encoding='utf-8')
lines=['DAMAGE TUNING — v0.7 IMPLEMENTATION CONTRACT','',f'{len(functions)} complete native bodies; {report["actualInstructions"]} ASM instructions; {len(claims)} specific claims.','']
lines += [f'{c["addr"]}: {c["Finding"]}' for c in claims]
lines += ['', 'Controls: seven unsigned-byte received-hit factors for player and manual enemy target; eight base cap/floor readouts.',
 'Each command revalidates scene, thread, host, current player, full bounded actor list, lock ownership, status backlinks and status-pool allocation/free-list state.',
 'Exactly one coefficient byte is written. Save records, HP, source parameter tables and other fields are untouched.',
 'Types5/6 use separate healing arithmetic. Later modifiers remain. Zero suppresses a hit reaction as well as damage. Extreme modded attack data may overflow native signed32-bit intermediates.',
 'One-time runtime edits have no reset/lease/profile. Rebuilds and scripts may overwrite them.',
 'Element names: '+report['elementNames']['source'],
 'Root synthetic suite:868 checks,0 failures at initial implementation. Independent source review and consolidated release validation recorded separately.',
 'No live gameplay test; complete game semantics remain open.']
(root/'damage_tuning.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(f'{len(features)} features; {len(claims)} claims; {len(functions)} complete bodies; {report["actualInstructions"]} instructions')
