# Kontaktreaktion hinter dem virtuellen Slot+216

## Ergebnis

Der offene Aufruf aus `3D1960` ist für drei konkrete native Deskriptoren aufgelöst. Bei Sora und Mickey führt er über zwei kurze Thunks zur selben Kontaktreaktion. Sie setzt ein Actor-Flag, reduziert einen nichtnull Bytezähler und wählt anschließend Motion-Codes sowie weitere Richtungs-/Skalarhelfer. Beim Basisdeskriptor `OBJ` ist der Slot ein leerer Callback. Er setzt keinen Rückgabewert auf null.

Damit ist `3D1960` weiterhin keine freigegebene Teleport-Funktion. Seine direkte Punktkopie geht nach **Kontaktobjekt+180**. Die geprüfte Aufrufkette gehört konkret zu einem **`YS::ATTACK_OBJ`**. Weitergehende Änderungen des Actors durch die Motion- und Richtungshelfer bleiben möglich und wurden nicht als sicherer Positionsschreiber ausgelegt.

## Konkrete Kette

| Schritt | Originalbeleg |
|---|---|
| Abgeleiteter Konstruktor | `40F1C0` ruft zuerst `3CF830`, setzt danach die `ATTACK_OBJ`-Vtable `5CE6C0` und initialisiert 32 Float4-Historienzeilen ab Objekt+208. |
| Virtuelles Update | Vtable+24 enthält `40F610`. Ein passender erster Geometrieeintrag und Objektflag `0x04` führen zum bekannten `3D0BB0`. |
| Kontaktpunkt | `3D0BB0` ruft bei seinem Querytreffer `3D1960`; letzterer schreibt den Punkt nach Objekt+180. |
| Virtueller Empfänger | `record = Decode32(object+16)`; `descriptor = Decode32(*record)`; Aufruf `descriptor.vtable[216](descriptor, record, object)`. |
| Sora | Deskriptor `750300` → Vtable `5CBA28` → Slotzelle `5CBB00` → Thunk `404EB0`. |
| Mickey | Deskriptor `7523B8` → Vtable `5D15A0` → Slotzelle `5D1678` → Thunk `4153E0`. |
| Gemeinsamer Callback | Beide Thunks verwerfen den Deskriptorparameter und springen zu `3D63E0(record, object)`. |
| Basis-OBJ | Deskriptor `74AF78` → Vtable `5C4F10` → Slotzelle `5C4FE8` → `1AFE10`, nur `RET 0`. |

RTTI-Namen, Deskriptorzeiger und Slotzellen wurden direkt gegen die gepinnte Original-EXE geprüft. Die drei Deskriptoren sind eine gezielte Auswahl; andere Klassen und überschriebene Vtables sind nicht abgedeckt.

## Wirkung der ausgewählten Player-Callbacks

`3D63E0` setzt an Actor+288 die Maske `0x02000000`. Actor+3444 wird nur bei einem Wert größer null um eins reduziert. Danach folgt `3D4650(actor, contact, 0, -1, -1.0f)`.

`3D4650` überspringt seine Helfer, wenn Kontaktflags+8 bereits `0x40` enthalten. Der Rückgabewert ist in diesem Fall `flags >> 6`. Bei Action-Record-Code 23 delegiert er an `403940`. Dieser Sonderpfad setzt den gewöhnlichen lokalen Verarbeitungsmarker nicht.

Im gewöhnlichen Pfad ersetzt ein negativer Motion-Code sich je nach Zustand durch 41 oder 43. Die Routine nutzt Actor+344 und die Modi 0 beziehungsweise 4. Ein negativer Skalar wird zu 50. Bei einem positiven Skalar wird ein gelieferter Float4-Vektor vollständig mit −1 multipliziert und mit dem Skalar an `3D4960` beziehungsweise `3D4800` weitergegeben. Abschließend setzt die Routine Kontaktmaske `0x40`. Null und ein ungeordneter NaN-Wert überspringen im geprüften Pfad den Richtungs-/Skalaraufruf.

Diese Aussagen beschreiben tatsächliche Argumente, lokale Schreibzugriffe und Aufrufreihenfolgen. Eine bestimmte Animation, Geschwindigkeit, Rückstoßdistanz oder kollisionsfreie Endposition wird daraus nicht zugesagt. Die Folgehelfer und der Action-23-Pfad wurden als offene Engine-Grenzen belassen.

## Herkunft und verbleibende Lücken

Der abgeleitete Konstruktor `40F1C0` schreibt **Objekt+16 nicht selbst**. Dieser Wert kommt aus dem noch nicht vollständig aufgenommenen Basiskonstruktor `3CF830`. Auch die Herkunft und Lebensdauer von Objekt+20 bleibt dort zu klären. Die Modellfälle binden diese beiden Verweise ausdrücklich über Fixtures; sie beweisen keine native Besitzgarantie.

Die engsten nächsten Ziele sind daher:

1. `3CF830`: Zuweisung, Ersatz und Gültigkeitsdauer der beiden Actor-Verweise.
2. Bei einer späteren Platzierungsstudie die noch getrennte Verbindung zwischen einem `16FEC0`-Zustandsdatensatz und dem tatsächlich besitzenden Actor.
3. Nur wenn für eine konkrete Funktion nötig: Wirkungen von `3D4800`, `3D4960` oder `403940`. In dieser Studie bleiben sie offene Folgeaufrufe.

Der zweite bekannte `3D0BB0`-Caller `4376B0` wurde nicht weiter aufgenommen. Die frühen PE-Callmusterdateien enthalten ausdrücklich nur Kandidaten; die bestätigten Grenzen stammen aus den frischen IDA-Aufnahmen. Die PE-Runtime-Spannen der ersten Suche waren Teilstücke der von IDA ausgewiesenen Funktionen und werden nicht als vollständige Bodies ausgegeben.

## Prüfung und Reproduktion

Sieben neue vollständige IDA-Ansichten wurden von `/root` über die vorhandene Sitzung `28e14b48` aufgenommen. Vier vollständige Bodies stammen ausdrücklich aus der eingefrorenen Vorstudie. Zusammen sind das **2.873 Originalbytes und 621 Instruktionen**. Die 20 Datensätze umfassen Deskriptoren, Slots, RTTI und die konkrete Skalar-Konstante.

**89 synthetische Fälle** interpretieren Originalinstruktionen, insgesamt 5.500 Schritte und 313 unterschiedliche Instruktionen. Sie prüfen beide Player-Thunks, den leeren Basis-Callback, Unterdrückungsflags, Zählergrenzen, die gewöhnlichen und speziellen Rückgabewege, Argumente und Reihenfolge sowie die 32 Historienzeilen des Konstruktors. Zwölf Fälle laufen durch den tatsächlichen `3D1960`-Dispatch mit originalen Vtablezellen bis in die ausgewählten Callback-Bodies.

Der Interpreter stammt aus der Vorstudie; die einzige Änderung ergänzt die `JS`-Bedingung für `CMOVS`. Engine-Aufrufe, Ptr32-Zuordnungen und der Basiskonstruktor besitzen benannte Stubs. Synthetische Speichergrenzen, anfänglich nullgesetzte Register und Float32-Einstellungen sind Modellbedingungen. Sie sind keine im Spiel bewiesenen Schutzmaßnahmen, keine Konkurrenzanalyse und kein Lebensdauerbeweis.

```powershell
py -3 -B artifacts/collision-position-dispatch-20261011/verify.py --check
```

Der Verifier prüft die Original-EXE, vollständige ASM-Seiten, Instruktionsgrenzen und Bytes, alte Dependency-Pins, Tabellenbindungen, Modelle und die exakte rekursive Manifestmenge. Der unveränderte Coverageparser löst alle kanonischen Belegverweise auf. Root meldete `auto_analysis_ready=false`; es wurde keine Autoanalyse angefordert. Keine Produktdatei, globale Forschungsdatei oder Paketdatei wurde geändert. Es gab keinen Spielstart, Attach, Injection, GUI-Eingriff, Save-, Mod- oder Twitch-Zugriff.
