# Audio: fünf geprüfte Teilstudien

Stand: 11. Oktober 2026. Die Ergebnisse erweitern die statische Analyse von KH2. Sie sind keine vollständige Beschreibung des Audiosystems. Die Trainer-Version **0.12.16 bleibt unverändert**; dieses Arbeitspaket enthält Forschung und Dokumentation.

## Was sich daraus lernen lässt

### Ein Audio-Handle bestätigt noch keine Wiedergabe

Die untersuchten Erzeuger reservieren zunächst einen Request und ordnen erst danach dessen Bank zu. Auch ein Request mit fehlgeschlagener Bankzuordnung kann einen Handle zurückgeben. Ein anderer Pfad setzt den Status nach zwei Backend-Aufrufen auf 2, ohne deren Rückgabewerte auszuwerten. Für eine spätere Diagnose müssen Reservierung, Zuordnung und tatsächliche Wiedergabe getrennt beurteilt werden.

Die Abschlusshelfer können die gesamte Request-Verarbeitung aufrufen und dabei verbliebene Requests starten. Sie eignen sich deshalb nicht ohne Weiteres als Befehl zum bloßen Leeren einer Warteschlange. Ein Kopierhelfer führt vier aufeinanderfolgende DWORD-Kopien aus; bei überlappenden Bereichen verhält er sich nicht wie `memmove`.

### Eine erfolgreiche Freigabeprüfung garantiert keine beendete Nutzung

Einige Prüfungen melden Erfolg, wenn die Infrastruktur oder der gesuchte Bankeintrag fehlt. Die konkrete Löschroutine behält auch bei erzwungener Freigabe ihre abschließenden Bedingungen bei. Stoppen und Abbrechen können bereits Zustände verändern, bevor ein späterer Schritt scheitert. Die Operationen sind in den untersuchten Pfaden nicht atomar.

Bei geliehenen Audiodaten überspringt der untersuchte Destruktor sowohl das Freigeben als auch das Leeren des Payload-Zeigers. Vor einem Austausch während des Spiels müssen daher noch alle Besitzer, Leser und Schreiber geklärt werden. Die Befunde beweisen keinen tatsächlich auftretenden Absturz oder eine allgemein sichere Austauschmethode.

### Die Actor-/Voice-Freigabe hat eine nachvollziehbare lokale Reihenfolge

Die untersuchte Actor-Kette stoppt Voice und gibt anschließend Ressourcenreferenzen ab. Der BAR-Pfad behandelt Typ 34 gesondert und kann passende Requests vom Typ 6 stoppen. Ein direkter Retirement-Aufruf und ein Sweep berücksichtigen nicht dieselben Prüfungen. Der globale Kontext wird über gewöhnliche Speicherzugriffe verwaltet; daraus folgt keine gegenseitige Ausschlusssicherung.

Diese Reihenfolge ist lokal belegt. Sie schließt mögliche weitere Referenzen, parallele Zugriffe oder andere Resource-Pfade nicht vollständig ein.

### SCD und ORIGIN lassen sich für eine lesende Metadatenansicht nutzen

Die Formatstudie belegt die ausgewählten Headerfelder, Tabellen, Sound-IDs und Teile der nativen Suche. Zwölf gezielt ausgewählte Archiveinträge lieferten drei gespeicherte ORIGIN-Wrapper und 13 SCD-Instanzen mit elf unterschiedlichen Hashes. Alle zwölf Original-Payloads sowie drei Audio-Remaster stimmen vollständig mit den vorhandenen entpackten Dateien überein.

Die Stichprobe enthält SCD-Versionen 3 und 4. Bei mehreren Dateien ist die physische Länge größer als der Größenwert im Header. Eine solche Abweichung darf deshalb nicht automatisch als beschädigte Datei oder harmloses Padding behandelt werden. Lange gespeicherte ORIGIN-Namen reichen in Bytes hinein, die später als Runtimefelder verwendet werden; diese Dateibytes dürfen nicht als Zeiger interpretiert werden.

## Was man damit bauen kann

Der nächste konkrete Schritt ist eine **lesende Audio-Metadatenansicht im Asset Explorer**: Version, Bank-ID, Sequenzanzahl, Sound-IDs und gespeicherte ORIGIN-Namen. Sie soll dieselben begrenzten Streams, Quellenprüfungen und Abbruchregeln wie die vorhandene Asset-Vorschau verwenden. Unbekannte Versionen, ungültige Bereiche und unvollständig verstandene Strukturen erhalten einen eigenen Status. Die Hexvorschau bleibt verfügbar.

Die native Dauerermittlung reicht noch nicht für eine verlässliche Vorschau. Ein untersuchter Bytecode-Scanner hat keine eigene Längen- oder Iterationsgrenze und kann auf synthetischen Eingaben rückwärts oder ohne Fortschritt laufen. Die erste Ansicht soll daher weder diesen Scanner nachbilden noch Wiedergabe, Import oder Austausch anbieten. Der genaue Entwurf steht in [offline-inspector-design.txt](../audio-bank-format-20261011/offline-inspector-design.txt).

## Umfang und Belege

| Studie | Neu erfasste Funktionskörper in dieser Studie | Begrenzte Aussagen | Schwerpunkt |
|---|---:|---:|---|
| [Bankfreigabe](../audio-bank-retirement-20261011/report.json) | 40 | 22 | Löschbedingungen, Teilwirkungen, Referenzen, Poolaufnahme |
| [Request-Erzeuger](../audio-request-producers-20261011/report.json) | 23, davon einer mit getrenntem Tail | 23 | Reservierung, Bankauflösung, Verarbeitung und Abbruch |
| [Voice-/Resource-Freigabe](../voice-resource-teardown-20261011/report.json) | 19 | 16 | Actor, BAR, Voice und obere Freigabekette |
| [Bankformat](../audio-bank-format-20261011/report.json) | 20 | 20 | Header, Tabellen, IDs, Dauerpfade und Cache |
| [Retail-Stichprobe](../audio-retail-witness-20261011/report.md) | keine | keine neuen Funktionsaussagen | Gespeicherte Felder und Archiv-/Loose-Vergleich |

Erfassungen überlappen mit anderen Studien und vorhandenen Aussagen. Die Zeilen dürfen nicht als neue, unterschiedliche oder vollständig verstandene Funktionen addiert werden. Die globale Übersicht entfernt Mehrfachzählungen und führt getrennte Codebereiche gesondert.

## Integration und Nachprüfung

`integration.json` bindet die fünf Studien, vier unabhängigen Funktionsreviews und den unveränderten Produktstand an ihre Hashes. Die unabhängige Python-Nachprüfung der Retail-Stichprobe liegt in deren eigenem Manifest. Frühere Statusformulierungen in eingefrorenen Autorenberichten bleiben als historische Momentaufnahme erhalten; die Reviewreceipts dokumentieren die spätere Annahme.

`claims.json` übernimmt 58 bereits geprüfte Aussagen aus drei Studien unverändert und normalisiert ausschließlich Feldnamen und Dateiverweise für den bestehenden Coverageparser. Die 23 Aussagen der Request-Studie haben bereits dessen Schema und bleiben in ihrem Ursprungsbericht. Der Parser wurde nicht angepasst. Reviewskripte und Receipts liegen als unveränderte Textkopien unter `review-snapshots`; deren historische Pfade sind keine neuen Analysebelege.

Alle 240 Produktdateien aus `src/` und `tests/` stimmen mit dem Source.zip von v0.12.16 überein. Bestehende Release-Tests wurden deshalb übernommen und hier nicht als neue Testausführung ausgegeben. Das Spiel wurde für diese Arbeit weder gestartet noch verbunden; Spiel-, Save- und Moddateien wurden nicht verändert.

Nachprüfung der eingefrorenen Dateien und normalisierten Aussagen:

```powershell
py -3 -B docs/research/audio-static-integration-20261011/verify.py
```

Zusätzlich gegen den aktuellen Produktstand und das lokale v0.12.16-Paket prüfen:

```powershell
py -3 -B docs/research/audio-static-integration-20261011/verify.py --check-current-product
```

Diese zweite Prüfung schlägt bei späteren Produktänderungen erwartungsgemäß fehl. Die hier dokumentierte Übereinstimmung betrifft den Zeitpunkt dieser Integration. Die aktuellen Coveragezahlen stehen getrennt in [coverage/summary.json](../coverage/summary.json), damit keine gegenseitige Hash-Abhängigkeit entsteht.
