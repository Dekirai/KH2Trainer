# Körpergrenzen und Reihenfolge der Transformberechnung

## Ergebnis

Der native Helfer `40AC20` berechnet für mehrere Körper **keine allgemein umschließende Box**. Er verwendet für die unteren und oberen Koordinaten jeweils `MINSS`. Drei unveränderte Originalfunktionen wurden dazu in einem eigenen Testprozess mit künstlichen Daten ausgeführt. Bei zwei Körpern mit Radius 1 und X-Mittelpunkten 0 und 100 liefert der Helfer X = −1 bis 1. Eine umschließende Box müsste bis 101 reichen.

Das Ergebnis ist eine nachgewiesene Eigenschaft dieses Helfers. Ob ein konkreter Spielszenenfehler daraus entsteht, ist offen. `3CBFE0` nutzt ihn nur in seinem Fallback bei fehlendem Actor+2696 und vorhandenem Körperpuffer. Der alternative Modellpfad transformiert acht Ecken und führt getrennte Vergleiche für Unter- und Obergrenzen aus. Eine pauschale Aussage über alle Charaktere wäre falsch.

## Weitere konkrete Verwendungen

- `55BAF0` nutzt den zweiten Körperpuffer bei Actor+1600 für eine Mittelpunktberechnung und setzt danach die Z-Komponente auf null.
- `562C50` berechnet daraus ebenfalls einen Mittelpunkt, bevor der folgende Erzeugungsablauf den vorbereiteten Vektor an erfolgreiche Ergebnisse weitergibt. Die vollständige Bedeutung dieses Ablaufs bleibt offen.
- `3B6310` bindet die Ressource bei Actor+2744 und erzeugt getrennte Puffer für Kind 1 bei +2560 und Kind 2 bei +1600.
- Ein Puffer besitzt einen 24-Byte-Kopf und 40 Byte pro vorberechnetem Eintrag. `40A9E0` reserviert den Platz anhand der Ressourcenanzahl; `40B140` setzt die aktive Anzahl zurück und füllt nach dem aktuellen Zustandsfilter neu.

## Bedeutung für Größen-Mods

Ein nachträgliches Skalieren fertiger Matrizen wäre kein gleichwertiger Ersatz für den nativen Größenpfad: `3CCB90` veröffentlicht zunächst Actor+64, baut den Körperpuffer +2560 bereits innerhalb der Funktion neu auf und veröffentlicht erst danach Actor+2056. Ein Hook am Funktionsende käme für diese erste Cacheberechnung zu spät. `3BFAB0` berechnet den zweiten Puffer +1600 nach dem Model-/Motion-Aufruf neu.

Die Ressourcenradien und -höhen werden in `3C9C00` weiterhin direkt übernommen, während sich die transformierten Mittelpunkte ändern können. Tiny/Giant braucht deshalb eine Prüfung vor der tatsächlichen Verwendung des Transformkontexts. Ein Modellskalierungs-Hook am Ende darf nicht als vollständig gleichwertige Größenänderung ausgegeben werden.

Für einen späteren optionalen Fix der Körpergrenzen sind die drei oberen `MINSS`-Stellen konkrete Kandidaten. Zuerst müssen die nachfolgenden Nutzer und betroffenen Ressourcenfälle geprüft werden. Diese Studie aktiviert keinen globalen Enginepatch und ändert keine Trainerfunktion.

## Prüfung und Grenzen

13 vollständige IDA-Funktionsansichten, 4.966 Originalbytes und 1.057 Instruktionen wurden gesichert und gegen die unveränderte EXE geprüft. Das IDB meldete `auto_analysis_ready=false`; es wurde weder verändert noch eine neue Analyse ausgelöst. Vollständige lokale Bodies sind keine vollständige IDB-Analyse.

Der native Probe führt nur `40AC20`, `184270` und `184940` in privatem Speicher aus. Er verwendet keine Stubs und greift auf keine Spielglobals zu. Zwölf Fälle decken leere, einzelne, identische, verschachtelte, getrennte und vertauschte Körper sowie Bruchwerte ab. Acht dieser ausgewählten Fälle weichen von einer umschließenden Union ab. Das ist keine statistische Fehlerrate. Eingaben sind endlich, Dimensionen nichtnegativ, Anzahl 0 bis 3. Guardpages und Canaries prüfen die Grenzen dieser Aufrufe; allgemeine Speichersicherheit wird nicht behauptet.

```powershell
py -3 -B artifacts/actor-body-bounds-20261011/verify.py --check
# Optional: Originalcode erneut ausschließlich im eigenen Testprozess ausführen:
py -3 -B artifacts/actor-body-bounds-20261011/verify.py --run-native
```

Die gespeicherten Belege sind `capture.json`, `discovery.json`, `evidence.json`, `claims.json`, `native-probe.json` und `verification.json`. Wiederholte Funktionsaufnahmen erhöhen nicht automatisch die Zahl neu verstandener Funktionen. Kein Spielstart, Attach, GUI-Eingriff, Save-/Mod-Schreibzugriff oder Twitch-Aufruf fand statt.
