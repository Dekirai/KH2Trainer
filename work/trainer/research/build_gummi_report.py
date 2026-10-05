"""Rebuild the Gummi research report from captured read-only IDA evidence."""
import hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'work/trainer/research'
files=['gummi_deep_evidence.json','gummi_deep_round2.json','gummi_deep_gates.json']
captures={name:json.loads((OUT/name).read_text(encoding='utf-8')) for name in files}
drafts=json.loads((OUT/'gummi_claim_drafts.json').read_text(encoding='utf-8'))
claims=[]
for rva,finding,limits in drafts:
    addr=f'0x{0x140000000+int(rva,16):x}'
    references=[]; evidence=[]
    kinds=set()
    for name,blob in captures.items():
        for kind in ('decompile','assembly'):
            for i,record in enumerate(blob.get(kind,[])):
                if int(record.get('addr','0'),16)!=int(addr,16):continue
                if kind=='decompile':
                    assert record.get('code') and record.get('cursor',{}).get('done') and not record.get('truncated')
                else:
                    assert record.get('cursor',{}).get('done')
                    assert record['instruction_count']==record['total_instructions']
                p='work/trainer/research/'+name
                if p not in evidence:evidence.append(p)
                references.append({'file':p,'json_pointer':f'/{kind}/{i}','kind':kind})
                kinds.add(kind)
    assert references,addr
    claims.append({'addr':addr,'Finding':finding,'Evidence':evidence,'EvidenceReferences':references,
                   'Strength':'fresh complete decompilation and complete assembly' if 'assembly' in kinds else 'fresh complete decompilation; critical neighboring ABIs separately verified',
                   'Limitations':limits+' Static evidence only; this analysis did not execute the game.'})
assert len({x['addr'] for x in claims})==len(claims)
phases={0:'mission fiber entry',1:'request resource load',2:'wait for resources',3:'create gameplay/player',4:'start intro',5:'wait for intro',6:'post-intro delay',7:'enter active loop',8:'normal mission',10:'begin death event',11:'wait for death event',12:'begin rebirth event',13:'wait for rebirth event',14:'start goal event',15:'death flow handoff',16:'wait for goal event',17:'restart/teardown',18:'result or module-exit handoff',19:'waiting after handoff'}
fields=[
 ('active_player','0xAF0540','uintptr_t','Active player ship, independent of Sora'),
 ('module_descriptor','0x716C10','GAME_MODE','Native vptr +0, scheduler +8, packed next +20, state +36'),
 ('module_state','0x716C34','int32','1 running,2 suspended,3 stopping; owner150310'),
 ('subsystem_heap','0xAE94F0','uintptr_t','Must equal current module heap9A8780'),
 ('module_heap','0x9A8780','uintptr_t','Created151A50, freed and nulled151980'),
 ('scheduler','0xAD9478','uintptr_t','Must equal module descriptor+8'),
 ('mission_phase','0xAD9474','int32','Writes only permitted in observed normal phase8'),
 ('player_descriptor','P+0','packed pointer','Decode must equal base72A860 whose native vptr is5B52B0'),
 ('ship','P+0x488','embedded object','Its state pointer+200 equalsP+0x570'),
 ('ship_state_backlink','P+0x550','uintptr_t','Must equalP+0x570'),
 ('player_state','P+0x570','embedded PLAYER_STATE','Native vptr5B5E70'),
 ('hp','P+0x578','float32','Authoritative HP, fractional values meaningful'),
 ('max_hp','P+0x57C','int32','Loadout-derived positive maximum'),
 ('gauge_event','P+0x5C0','int32','1 heal,2/3/4 damage severity'),
 ('player_phase','P+0x5D8','int32','0 init,1 inactive,2 active,3 completion,4 stopped/dead,5 rebirth'),
 ('flags','P+0x140C','uint32','0x10 dead,0x40000 rebirth; other flags have independent owners'),
 ('score','0x72B130','uint32','Upper digits ordinary points; ones digit saturated damage-event counter'),
 ('score_additions_locked','0x72B134','byte','Ordinary additions blocked when nonzero'),
 ('medal_progress','0x72B2C0','int32','0..9'),
 ('medal_level','0x72B2C4','int32','0..30; directly indexes31float score table'),
 ('best_medal_level','0x72B2C8','int32','Best attained level'),
 ('medal_flags','0x72B2CC','uint32','1 maximum;2 level-up event;4 hit-penalty event'),
 ('rank_row','0xAF4258','uintptr_t','128byte selected route/mission rank row'),
 ('rank','0xAF4204','int32','Observed limit6 or16 according to mission variant'),
 ('rank_phase','0xAF4260','int32','0 waiting,1 tracking,2 finalizing'),
]
report={'schema_version':1,'title':'Gummi gameplay: ship lifetime, HP, score, medals and mission state',
 'build_sha256':'9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed','image_base':'0x140000000',
 'scope':'Coherent Gummi gameplay core. No claim of complete gb/gm semantics. Editor, weapon/energy, enemy AI, route assets and saving formats remain open.',
 'methods':{'read_only_ida_database':'1fc84ea8','native_source_changes':'Only isolated GummiFeatures.inl and its harness after parent authorization; no IDB, game or UI changes.',
            'complete_claim_functions':len(claims),'asm_claim_functions':sum('assembly' in x['Strength'] for x in claims),
            'all_assembly_pages_checked':True,'live_game_validation':False},
 'evidence_files':[{'path':'work/trainer/research/'+n,'sha256':hashlib.sha256((OUT/n).read_bytes()).hexdigest()} for n in files],
 'fields':[{'name':a,'location':b,'type':c,'meaning':d} for a,b,c,d in fields],
 'mission_phases':phases,'claims':claims,
 'feature_contract':'work/trainer/research/gummi_feature_contract.txt',
 'implementation':{'native':'trainer/Native/GummiFeatures.inl','catalog':'work/trainer/research/gummi_features.json',
                   'test':'work/trainer/tests/GummiGuardTests.cpp','build_test':'work/trainer/tests/build_gummi_tests.cmd','isolated_checks':195,
                   'game_calls_in_tests':False,
                   'independent_review':'work/trainer/research/gummi_independent_evidence.json',
                   'independent_review_result':'No substantial issue found; static ABI, integer limits and ownership gates independently checked.',
                   'notes':'Mock callouts validate ABI arguments. Tests do not execute copied native function bodies. Shared packed-pointer decoding is represented by a synthetic-RVA fixture.'},
 'trainer_limits':['Only living-ship heal/refill and positive multiples-of-ten score additions are mutating actions.',
 'HP recovery does not revive dead or rebirthing ships. No autoheal or invulnerability hook is implemented.',
 'Score additions may affect subsequent native mission ranks, rewards and saved records.',
 'Maximum HP and medal values are read-only. Installed parts recompute derived PLAYER_STATE fields.',
 'Energy semantics and an editor contract were not established; no feature is invented from RTTI names.',
 'Callbacks are fixed RVAs with complete function byte comparisons before invocation; all actions execute on engine thread with fresh heartbeat and immediate context revalidation.',
 'Sora sceneReady is not a Gummi gate. Native GAME_MODE state1 is required for writes; state2 allows readouts only.'],
 'next_analysis':[{'priority':1,'target':'gb weapons/special attacks/shields','reason':'Trace231770/231760/2317F0 and1F8230/1F82F0 into actual resource consumption and cooldown owners.'},
 {'priority':2,'target':'gm editor/save ownership','reason':'Follow selected loadout recordsAEF488/AEF4B0/AEF4D8 through modification, validation and serialization before allowing parts edits.'},
 {'priority':3,'target':'route and mission assets','reason':'Analyze GBX loader1E1A10, rank table207950 and mission-specific AF7146 metric; resource parser validation remains unproved.'},
 {'priority':4,'target':'hit routing and immunity','reason':'Follow all callers1FF340/1FF4F0 and shield paths before proposing a damage guard with restoration.'},
 {'priority':5,'target':'native result/save commit','reason':'Trace2098E0→record processing and2081E0 reward grant to precise persistence boundaries.'}]}
(OUT/'gummi_deep.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
text=[
'GUMMI GAMEPLAY — VERTIEFTE STATISCHE ANALYSE',
'',
'Kernbefund',
'Gummi-Spiel und Soras Feldspiel verwenden eigene Spielerobjekte, Statusfelder und Modulzustände. Ein lebendes Gummi-Schiff lässt sich über den nativen Heilhelfer behandeln; Score kann über den nativen Punktehelfer erhöht werden. Beides benötigt die aktuellen Gummi-Objekt- und Modulprüfungen.',
'',
'Die Einerstelle des Scores zählt maximal neun Schadensereignisse. Reguläre Punkte kommen in Zehnerschritten hinzu. Treffer senken außerdem die Medaillenstufe; späteres Heilen macht diese Folgen nicht rückgängig. Die Rank-Schleife verarbeitet den Score und vergibt beim Abschluss Belohnungen.',
'',
'Belegte Schnittstellen',
'- Player = QWORD[base+AF0540], PLAYER_STATE = Player+570.',
'- HP float32 = Player+578; MaxHP int32 = Player+57C.',
'- Heal2265E0: void(state inRCX,float amount inXMM1); deckelt HP, setzt GaugeEvent=1; kein Revive.',
'- AddScore207A50: void(int amount inECX), kein definierter Rückgabewert; respektiert ScoreLock.',
'- Gummi GAME_MODE716C10: Scheduler+8, packednext+20, State+36. State1 läuft; Pause setztState2.',
'- ModulheapAE94F0 muss9A8780 entsprechen; beide werden beim Abbau genullt. SchedulerAD9478 mussModule+8 sein.',
'- Aktionsfreigabe nur Missionphase8, Spielerphase2, positiverHP und ohne Dead/Rebirthflag.',
'',
'Implementierung und Grenzen',
'Slots128..143 bieten13 Anzeigen und3 Einmalaktionen. RequiresScene=false umgeht ausschließlich die Sora-UI-Sperre; native Gummi-Prüfungen bleiben verpflichtend. Capabilities melden implementierte Funktionen statisch, Value-valid-Bits die tatsächliche Verfügbarkeit.',
'Keine persistenten Effekte, kein Hook, kein MaxHP-/Medalsetter. Vollständige native Heil-/Score-Funktionsbytes werden vor jedem Aufruf geprüft. Bei Pause bleiben Anzeigen möglich, Änderungen werden abgelehnt.',
'195 isolierte Checks bestanden. Die Tests benutzen synthetischen Speicher und Mock-Funktionen; kein Spielcode und kein laufendes Spiel wurden ausgeführt. Live-Verhalten ist noch nicht validiert.',
'',
'Abdeckung',
f'{len(claims)} konkrete Funktionsbefunde, davon{report["methods"]["asm_claim_functions"]} mit vollständiger frischer ASM. Weitere Befunde beruhen auf frischem vollständigem Pseudocode plus benachbarter ASM. Kein Vollständigkeitsanspruch für gb/gm.',
'Nicht abgeschlossen: Energie-/Waffenressourcen, Editor und Schiffbau, gegnerische KI, Route-/GBX-Parser, exakte Save-Commitgrenzen. RTTI und Exportinventar allein wurden nicht als Semantik gezählt.',
'',
'Funktionsbefunde']
for c in claims:
 text+=['',c['addr'],c['Finding'],'Beleg: '+', '.join(c['Evidence']),'Grenze: '+c['Limitations']]
(OUT/'gummi_deep.txt').write_text('\n'.join(text)+'\n',encoding='utf-8')
print(f'Wrote {len(claims)} evidence-linked claims; {report["methods"]["asm_claim_functions"]} include complete ASM.')
