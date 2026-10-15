# Performance-Korrektur v0.12.19

## Auslöser und Änderung

Der Nutzer meldete einen Einbruch auf ungefähr 30 FPS nach dem Verbinden.
Der bisherige Bridge-Code sammelte sämtliche Diagnosewerte bei jedem erfolgreichen
Spielupdate. Vier passive Anzeigen nahmen dabei nacheinander denselben, mit dem
Präsentationsthread geteilten MSVCP-Mutex: Display, Rendererdiagnose, Fensterzustand
und MSAA. Das konnte den Spielthread auch ohne eingeschaltete Trainerfunktion
auf den Renderer warten lassen. Die Rendererdiagnose prüfte zusätzlich bis zu
560 Historienknoten pro Abfrage.

Diese vier Anzeigen versuchen die Sperre jetzt ohne Warten. Ist sie belegt oder
der passende Laufzeitexport nicht verfügbar, bleiben die betroffenen Werte für
dieses Sample als nicht verfügbar markiert. Kein alter Messwert wird dabei als
frisch ausgegeben. Explizite Änderungsbefehle behalten ihren bisherigen
Synchronisations- und Prüfpfad.

Die Original-EXE initialisiert diesen Mutex am Konstruktorabschnitt ab RVA
`10AA2D` mit Typ 2 (`_Mtx_try`). Die 17 Originalbytes, der Init-Thunk und die
MSVCP-Importeinträge wurden geprüft. `_Mtx_trylock` wird aus demselben geladenen
MSVCP140-Modul aufgelöst, dessen Lock- und Unlock-Exporte gegen die Importtabelle
geprüft werden. Der Trainer interpretiert keine internen Mutexfelder.

Vollständige Diagnose-Snapshots werden höchstens alle 100 ms gesammelt. Befehle,
Szenen-/Spieler-/Statuswechsel und Wechsel des Verbindungszustands lösen eine
sofortige Aktualisierung aus. Zwischen Samples bleiben Werte, Gültigkeitsmasken
und Zeitstempel zusammen unverändert. Laufende Effekte, Lebensdauerbeobachtung,
Rückbau und Verbindungsüberwachung bleiben bei jedem Spielupdate aktiv.

Tastenkürzel entscheiden Freeze/Pause anhand des aktuellen Zustands auf dem
Spielthread. Ein Tastendruck macht die nächste Veröffentlichung sofort fällig;
schnelle aufeinanderfolgende Tastendrücke verwenden keine veralteten Anzeigewerte.

## Prüfung

Die gezielten Renderer-Suiten bestanden mit 55.611 Prüfungen und ohne Fehler.
Die vier Produktionsvarianten wurden ebenfalls kompiliert. Geprüft wurden
belegte Sperren, fehlender Try-Export, erfolgreicher Lockbesitz sowie Ausnahme-
und Unlockfehler. Passive Aufrufe dürfen keinen wartenden Lockpfad verwenden.

Die neue Performance-Suite führt die tatsächliche `TrainerFrame`-Route in einem
isolierten Prozess mit privatem Speicher aus. Ihre 29 Prüfungen decken Zeitgrenze,
Uptime-Überlauf, bytegleich erhaltene Snapshots, Befehle, laufende Drive-Effekte,
Verbindungsablauf, Kontextwechsel und schnelle Tastenkürzel ab. Die bestehenden
PlayerBridge- und Shortcut-Suiten bestanden mit 665 bzw. 23 Prüfungen.

Vergleich über je zwei Sekunden simulierten Spieltakts, mit denselben aktuellen
Prüfpfaden und privaten Daten, einmal mit vollständiger Messung bei jedem Update:

| Update-Takt | Vollständige Samples vorher → nachher | VirtualQuery-Aufrufe vorher → nachher |
| --- | ---: | ---: |
| 60 Hz | 120 → 20 | 10.440 → 3.040 |
| 120 Hz | 240 → 20 | 20.880 → 4.600 |
| 144 Hz | 288 → 20 | 25.056 → 5.224 |

Der Vergleich misst die reduzierte Abfragearbeit. Die private Fixture enthält
keinen laufenden Renderer und keinen aktiven Actor-Lebensdauerobserver. Daraus
lässt sich keine konkrete FPS-Zahl im Spiel ableiten. Eine Liveprüfung wurde
nicht durchgeführt. Die vollständigen Release-Testprotokolle liegen im
Paketordner unter `Validation/`.

## Nutzung

KH2 und die alte Trainerfassung schließen, dann KH2 und die neue EXE starten
und verbinden. Die zuvor geladene Bridge bleibt bis zum Ende des Spielprozesses
im Speicher; ein bloßes Neuverbinden ersetzt sie nicht.

Der Asset Browser bleibt entfernt. Die noch nicht eingebundenen Motion-
Analysekomponenten werden durch diese Korrektur nicht aktiviert.
