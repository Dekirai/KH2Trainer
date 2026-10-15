import hashlib,json,shutil,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/research/mission-gummi-implementation-20261008-v01215'
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

changes={
 'src/KH2Trainer/Data/features.json','src/KH2Trainer/KH2Trainer.csproj','src/KH2Trainer.Core/Data/BdxNativeCalls.json',
 'src/KH2Trainer.Bridge/MissionFeatures.inl','src/KH2Trainer.Bridge/MissionEventFeatures.inl',
 'tests/KH2Trainer.Bridge.Tests/MissionEventGuardTests.cpp','tests/KH2Trainer.Bridge.Tests/MissionGuardTests.cpp','tests/KH2Trainer.Bridge.Tests/PlayerBridgeTests.cpp',
 'tests/KH2Trainer.Core.Tests/MissionRescueCatalogTests.cs','tests/KH2Trainer.Core.Tests/BdxNativeCallCatalogTests.cs','tests/KH2Trainer.UiTests/Program.cs'}
new={'src/KH2Trainer.Bridge/MissionCounterSupport.h','tests/KH2Trainer.UiTests/MissionCounterUiChecks.cs'}
extensions={'.sln','.md','.ps1','.props','.cs','.csproj','.xaml','.manifest','.cpp','.h','.inl','.json','.jsonl','.py','.cmd','.html','.zip','.txt'}
excluded={'bin','obj','artifacts','__pycache__','.git','.vs'}
current_names={p.relative_to(ROOT).as_posix() for folder in ('src','tests') for p in (ROOT/folder).rglob('*')
    if p.is_file() and not excluded.intersection(x.lower() for x in p.relative_to(ROOT).parts)
    and (p.suffix.lower() in extensions or p.name.upper() in ('LICENSE','NOTICE'))}
with zipfile.ZipFile(ROOT/'artifacts/packages/KH2_Trainer_v0.12.14/Source.zip') as z:
    names={n for n in z.namelist() if n.startswith(('src/','tests/'))}
    assert current_names==names|new,(current_names-(names|new),(names|new)-current_names)
    assert {n for n in names if not (ROOT/n).is_file() or (ROOT/n).read_bytes()!=z.read(n)}==changes
    previous_features=json.loads(z.read('src/KH2Trainer/Data/features.json'))
    current_features=load(ROOT/'src/KH2Trainer/Data/features.json')
    assert current_features[:len(previous_features)]==previous_features and len(current_features)==358
    sourcePins=[dict(path=n,sha256=sha(ROOT/n)) for n in sorted(names|new)]
snap=OUT/'source-snapshots';snap.mkdir(exist_ok=True)
for path in sorted(changes|new):shutil.copyfile(ROOT/path,snap/path.replace('/','__'))
copies={
 'compiled-probe.json':'artifacts/mission-gummi-review-v01215/result.json',
 'ui-report.json':'artifacts/v01215-ui/report.json',
 'world-missions.png':'artifacts/v01215-ui/FeaturePages/world-missions.png',
 'core-tests.txt':'artifacts/v01215-core-tests.txt',
 'arithmetic-review.json':'artifacts/review-mission-counter-v01215/arithmetic-result.json',
 'ArithmeticReview.cpp':'artifacts/review-mission-counter-v01215/ArithmeticReview.cpp',
 'review-voice.json':'artifacts/review-voice-lifecycle-v01215/review.json',
 'review-mission.json':'artifacts/review-mission-counter-implementation-20261008/review.json',
 'review-bank3.json':'artifacts/review-bdx-bank3-extended-20261008.json',
 'review-integration.json':'artifacts/review-mission-gummi-integration-v01215.json'}
for dest,source in copies.items():shutil.copyfile(ROOT/source,OUT/dest)
# Carry reviewer scripts/results referenced by receipts into the research package.
review_evidence=OUT/'review-evidence';review_evidence.mkdir(exist_ok=True)
for name in ('review-voice.json','review-integration.json'):
    review=load(OUT/name)
    for path,expected in review.get('pins',review.get('sourcePins',{})).items():
        assert sha(ROOT/path)==expected,(name,path)
        if path.startswith('artifacts/'):
            shutil.copyfile(ROOT/path,review_evidence/path.replace('/','__'))
# Keep this standalone arithmetic reproduction buildable inside the package.
p=OUT/'ArithmeticReview.cpp';b=p.read_bytes()
assert b'../../src/KH2Trainer.Bridge/MissionCounterSupport.h' in b
p.write_bytes(b.replace(b'../../src/KH2Trainer.Bridge/MissionCounterSupport.h',b'source-snapshots/src__KH2Trainer.Bridge__MissionCounterSupport.h'))
studies=['mission-counter-implementation-20261008','voice-request-lifecycle-20261008','bdx-bank3-extended-20261008']
pins=[dict(path=f'docs/research/{name}/manifest.json',sha256=sha(ROOT/f'docs/research/{name}/manifest.json')) for name in studies]
write(OUT/'implementation.json',dict(success=True,version='0.12.15',features=358,annotations=256,changedSourceFiles=sorted(changes),newSourceFiles=sorted(new),sourcePins=sourcePins,upstreamManifests=pins,baseline='artifacts/packages/KH2_Trainer_v0.12.14/Source.zip',baselineSha256=sha(ROOT/'artifacts/packages/KH2_Trainer_v0.12.14/Source.zip'),liveGame=False,scope='Two checked Mission counter actions, three read-only combo fields, seventeen Gummi annotations and one bounded Voice description expansion. Other existing src/tests files are byte-identical to the prior source archive.'))
(OUT/'report.txt').write_text('''KH2 Trainer v0.12.15: geprüfte Missionsfunktionen und neue Skriptbeschreibungen

World > Missions bietet zwei zusätzliche Aktionen: einen Zähler um eine ganze Zahl ändern und eine Dezimalstelle ersetzen. Die Berechnung verwendet 64-Bit-Ganzzahlen und lehnt Ergebnisse außerhalb 0..Maximum ab. Beide Aktionen prüfen den aktuellen Missions-, Widget-, Skript- und Ereigniszustand erneut und rufen den vorhandenen absoluten Setter einmal auf. Normale Missionsereignisse und mögliche Belohnungen bleiben aktiv. Profile können diese Aktionen nicht wiederholen.

Drei neue Anzeigen lesen den aktuellen Missions-Combo, seinen gespeicherten Höchstwert und das verbleibende native Zeitfenster. Die Einheit ist noch nicht in Sekunden umgerechnet. Fehlende oder ungültige Beobachtungen erscheinen als unbekannt. Diese Combo gehört zum Missions-Widget und ist von Soras Angriffskombo getrennt.

Der BDX-Katalog enthält 256 beschriebene Einträge bei weiterhin 1.063 unveränderten numerischen Deskriptoren. Die 17 neuen Gummi-Beschreibungen erläutern Schiffbewegung, Reaktionsimpulse, Kameraorientierung und Controller-Vibration. Ein vorhandener Voice-Eintrag beschreibt jetzt auch verworfene Anfragen und die Grenzen der Backend-Zuordnung.

Prüfung: native Tests verwenden synthetischen Speicher und modellierte Callbacks. Die Oberfläche wurde ohne sichtbares Fenster gerendert. Ein zusätzliches unabhängiges Rechenmodell verwendet Dezimalstrings für Ziffernersetzung. Originaldateien wurden ausschließlich gelesen; kein Spiel wurde gestartet oder angefasst.

Die Prüfungen sind keine vollständige Actor-, Ressourcen-, Thread- oder Ausnahmebehandlungsgarantie. Die Studien halten offene Lebensdauer-, Synchronisations- und Backend-Fragen fest. Die Gesamtanalyse des Spiels bleibt unvollständig.
''',encoding='utf-8')
write(OUT/'manifest.json',dict(files={p.relative_to(OUT).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(OUT.rglob('*')) if p.is_file() and p!=OUT/'manifest.json'}))
print(json.dumps(dict(success=True,sourcePins=len(sourcePins),changes=len(changes),newFiles=len(new))))
