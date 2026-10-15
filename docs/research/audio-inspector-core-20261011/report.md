# Audioinspektor: Coreimplementierung

## Ergebnis

Der lesende ORIGIN-/SCD-Metadateninspektor ist implementiert. Der isolierte Corelauf besteht mit **172 Prüfungen, 0 Fehlern**. Er verwendet ausschließlich synthetische Daten und tatsächlich verlinkte Produktquellen. Die Gesamtprojekt- und UIprüfung werden getrennt koordiniert.

Geänderte Produktdateien:

- `src/KH2Trainer.Core/AudioBankInspection.cs`: neue Modelle und neuer Reader.
- `src/KH2Trainer.Core/AssetArchiveReader.cs:164`: zwei reine Magic-Erkennungen.
- `tests/KH2Trainer.Core.Tests/AudioBankInspectionTests.cs`: neue synthetische Prüfungen.
- `tests/KH2Trainer.Core.Tests/Program.cs:213`: Registrierung im bestehenden Runner.

Der öffentliche Einstieg ist `AudioBankInspector.ReadAsync(AssetArchiveReader, AssetPayload, AudioBankReadLimits?, CancellationToken)`. Der UI-Agent verwendet den gleichen Modellvertrag. Kein weiterer Produktpfad und keine Version, Dokumentationsstudie oder Paketdatei wurde durch diese Arbeit geändert.

## Verhalten und Grenzen

- Die öffentliche API öffnet ausschließlich den behaltenen AssetPayload über den bestehenden Archivreader. Dabei bleiben Dateiidentität, HED-/Recordhashes, Eltern-BAR-Hash und Kindspannen wirksam. Das Ergebnis enthält schreibgeschützte Listen und Vorschau-Bytes; Streams werden wieder freigegeben.
- Quellenfehler, tatsächliches vorzeitiges Streamende und Cancellation bleiben Exceptions. Erkannte, aber verkürzte oder nicht unterstützte Formate sind eigene Dokumentzustände. Ein vollständiger Metadatenlauf ist keine Aussage über die vollständige Dateigültigkeit.
- ORIGIN braucht 48 verfügbare Bytes. Der Name wird ausschließlich innerhalb 16..47 gelesen, mit Byte-Escapes dargestellt und mit Abschlusszustand ausgegeben. DWORD +12 bleibt gespeicherte Metadaten. Die Bytes +32/+40 werden nicht als Zeiger dereferenziert oder als separate Runtimefelder dargestellt.
- SCD-Details beschränken sich auf Little-Endian-Versionswerte 3/4 und die beobachteten Rohprofilbytes +12=0/+13=4. Anderen Werten wird keine vermutete Flagsemantik gegeben.
- Headeroffset ist WORD, Tabellenbasen sind unsigned DWORD und Ziele signed DWORD. Tabellen- und Zielspannen werden vor Reads in breiter Arithmetik gegen die tatsächliche begrenzte Streamlänge geprüft. Größenfeld +16 wird unabhängig angezeigt; Differenzen sind Beobachtungen.
- Der Sequenzheader braucht 16 Bytes für V3 bzw. 32 für V4. Erst danach werden Sound-ID +12 und Trackanzahl +0 gelesen. B/C erhalten nur eine Ein-Byte-Erreichbarkeitsbeobachtung, Aux eine 128-Byte-Beobachtung. Deren Inhalte werden nicht interpretiert. Null- und negative Ziele werden nicht verfolgt.
- Doppelte IDs und Ziele behalten ihre Ordinalzeilen. Zielüberschneidungen mit bekannten Metadatenspannen sind Beobachtungen. B/C- oder Aux-Objektgrößen, Codec, optionale Sequenzabschnitte, Trackbytecode, hörbare Dauer und Runtimebesitz werden nicht validiert.

## Budgets

Defaults: 4096 Einträge pro Tabelle, 8192 Zeilen insgesamt, 1 MiB Inspectorreads, 128 gespeicherte Diagnosen und 64 MiB Package-Decodes. Konfigurierbare Grenzen werden gegen feste Maxima validiert.

Die 64-MiB-Grenze wird **vor** OpenReadAsync auf jeden Paketvorfahren des Payloads angewendet. Ein kleiner BAR-Kindbereich kann daher nicht unbemerkt einen größeren Paketdecode auslösen. Das strengere bestehende Readerlimit gilt ebenfalls. Bei diesem Preflight-Limit wird keine Quelle geöffnet; das Dokument sagt dies ausdrücklich und enthält keine Vorschau.

Das Metadatenbudget zählt die Vorschau und spätere echte Inspectorreads. Die Vorschau wird für darin bereits enthaltene Headerfelder wiederverwendet, ohne nochmals aus dem Stream zu lesen. Package-Dekodierung und die bestehenden HED-/BAR-Strukturprüfungen werden **nicht** als Teil dieses 1-MiB-Budgets behauptet. Ein gewöhnliches Browse-Open verwendet weiterhin seine bisherigen Readerlimits.

Ein Tabellen-/Gesamtzeilenlimit liefert die Headerzusammenfassung ohne Tabellenenumeration. Ein späteres Readlimit erhält bereits gelesene Zeilen und kennzeichnet die unvollständige Tabelle sowie ggf. deren gerade erreichten Zielheader als nicht untersucht. Das Diagnosecap zählt unterdrückte Meldungen separat.

## Prüfnachweise

Der isolierte Runner in `Probe.csproj` verlinkt fünf Coredateien plus die neue Testdatei direkt; er nutzt eigene lokale bin/obj-Verzeichnisse. `test-output.txt` enthält die Konsolenausgabe, `test-output/result.json` alle Einzelergebnisse. Seine Testdaten sind synthetisch.

Geprüft wurden insbesondere:

- Alle ORIGIN-Verkürzungen 0..47 und SCD-Verkürzungen 0..19; vollständige/falsche Magic, Namensabschluss am Rand, Escapes, gespeicherte Bytes an späteren Runtimefeldpositionen.
- Versionen und rohe Headerprofile, beide Sequenzheadergrößen, negative/Null-/Grenz-/sehr große Ziele, unsigned Tabellenbasen bis 0xffffffff sowie virtuelle Streamlänge über 4 GiB ohne große Allocation.
- Größenfeld kleiner/gleich/größer als verfügbare Länge, Ziele innerhalb nur einer dieser Grenzen, getrennte B/C/Aux-Mindestspannen, unabhängig fehlerhafte Tabellen, doppelte IDs/Ziele und Metadatenüberschneidung.
- Exakte Tabellen- und Gesamtzeilenlimits, Diagnosecap, Readlimit vor Tabelle bzw. Sequenz, exakt ausgenutztes Readbudget, wiederholte Ein-Byte-Reads, Abbruch nach Prefix/Tabellenheader/Offsettabelle/Sequenzread und echte EOF-/I/O-Ausnahmen.
- Öffentliche API durch lose Dateien, verschachtelte BARs, Package-BARs, explizite Remaster und Alias-Records. Ein Ziel außerhalb des Kindes wird trotz vorhandener Elternbytes abgelehnt.
- Dateiänderung, Ersatzdatei mit gleicher Länge/Zeit, HED-/Record-/BAR-Metadatenmutation mit wiederhergestellter Zeit; Freigabe von Handles nach Erfolg und fehlgeschlagenen Quellenprüfungen.
- Vorfahren-Decodegrenze vor dem Öffnen durch eine absichtlich exklusiv gesperrte Packagequelle; exakt passendes Limit und strengeres Archivreaderlimit.

Reproduktion aus dem Repository:

```powershell
py -3 -B artifacts/audio-inspector-core-20261011/verify.py
dotnet run --project artifacts/audio-inspector-core-20261011/Probe.csproj -c Release -- artifacts/audio-inspector-core-20261011/test-output
```

Der Verifier prüft Sourcepins, eingefrorene Snapshots, Manifest und gespeicherte Testergebnisse. Er führt die Produkttests selbst nicht aus. Generierte bin/obj und synthetische Quelldateien unter test-output sind bewusst außerhalb des Metadatenmanifests; der Ergebnisbericht ist darin enthalten.

## Belegstellen

Die akzeptierte ORIGIN-Studie (`docs/research/voice-origin-resources-20261011`) belegt mit 36D8B0 die gespeicherte 48-Byte-Form, mit 1DFD70 die spätere Veränderlichkeit von +12 und mit 09FBD0/09FD20 Header-/Tabellenfelder. Der Inspektor verwendet die Dateiform, ohne ihre Runtimeänderungen nachzubauen.

Die eingefrorene Formatstudie (`docs/research/audio-bank-format-20261011`) belegt signed Offsets in 09FDB0/09FDE0/09FEA0, Sound-ID-Suche WORD+12 in 0A0010/0A0110/0A0230, Basisgrößen in 0A4080 und Trackanzahl BYTE+0 in 0A45B0. Die Aux-Mindestspanne 128 folgt der ausgewählten Kopie in 0A0390; die vollständige Aux-Semantik bleibt offen.

Die eingefrorene Retailprobe (`docs/research/audio-retail-witness-20261011`) zeigt in 13 SCD-Instanzen die Rohprofile 0/4 und acht physisch/deklarierte Längendifferenzen. Das rechtfertigt die getrennte Anzeige und konservative Produktgrenze. Die neue Implementierung kopiert nicht die unbeschränkte byte[]-Probe.

Diese Corearbeit hat keine Retaildatei erneut geöffnet. Der vom Hauptagent getrennt durchgeführte Retailvergleich wird in dessen eigenem `artifacts/audio-inspector-retail-20261011` dokumentiert und zählt nicht zu den 172 eigenen synthetischen Prüfungen.

## Offene Grenzen

Die Locatoridentität ist kein Hash aller Payloadbytes. Gleichlange In-Place-Änderungen außerhalb gehashter Strukturbereiche mit restaurierten Dateimetadaten können vor dem Öffnen unbemerkt bleiben. Ein bereits dekodierter MemoryStream ist ein Snapshot, keine Zusage unveränderter On-Disk-Daten bis zur UI-Veröffentlichung oder zum Spielstart.

Keine Wiedergabe, Pfadauflösung aus ORIGIN, Imports, Assetexports, Spielprozesse, GUI, Injection, Savezugriffe oder native Ausführung wurden hier vorgenommen. Kein Commit wurde erstellt. Vollständige UI-/Produktintegration und ein finaler unabhängiger Diffreview bleiben Schritte der übergeordneten Arbeit.
