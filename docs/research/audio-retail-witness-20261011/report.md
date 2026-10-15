# Gezielte Retail-Probe: ORIGIN und SCD

Die Probe ist abgeschlossen. Zwölf Archiveinträge ergeben drei gespeicherte ORIGIN-Wrapper und 13 SCD-Instanzen mit elf unterschiedlichen Hashes. Alle zwölf Original-Payloads und drei Audio-Remaster stimmen vollständig mit den bereits vorhandenen entpackten Dateien überein. Es wurden keine Spiel- oder Audiodaten exportiert.

## Stichprobe

| Auswahl | Version | Bank-ID | Sequenzen | Tabelle B / C | Physisch minus deklariert |
|---|---:|---:|---:|---:|---:|
| bgm/music050.win32.scd | 3 | 9999 | 1 | 1 / 1 | 0 |
| bgm/music051.win32.scd | 3 | 9999 | 1 | 1 / 1 | 0 |
| bgm/music530.win32.scd | 3 | 9999 | 1 | 1 / 1 | 0 |
| obj/B_EX120.a.us/se/obj/se265 | 3 | 265 | 53 | 27 / 34 | 176 |
| obj/B_EX120.a.us/voice/battle/us/n_dancer | 4 | 5166 | 34 | 3 / 3 | 0 |
| obj/M_EX950.a.us/se/obj/se271 | 3 | 271 | 36 | 23 / 23 | 192 |
| se/se000.win32.scd | 4 | 0 | 314 | 152 / 215 | 1056 |
| se/se999.win32.scd | 3 | 999 | 155 | 96 / 96 | 880 |
| se/se001.win32.scd | 3 | 1 | 59 | 0 / 0 | 0 |
| voice/us/battle/al0_sora.win32.scd | 3 | 5100 | 34 | 32 / 32 | 192 |
| voice/us/gumibattle/gumi.win32.scd | 4 | 5141 | 31 | 31 / 31 | 192 |

Die zusätzlichen Exemplare von se000 und se999 in kh2_first und kh2_sixth sind bytegleich. Daraus folgt keine Aussage zur Ladepriorität. Längenabweichungen werden als Messwerte erfasst und nicht pauschal als Fehler gewertet.

## Gespeicherte Wrapper

- obj/M_EX950.a.us: Typ31, se/obj/se271, genau ein gleichnamiger SCD-Remaster.
- obj/B_EX120.a.us: Typ31 se/obj/se265 und Typ34 voice/battle/us/n_dancer; beide haben genau einen gleichnamigen SCD-Remaster.
- Alle drei Wrapper sind 48 Byte lang. Das Namensfeld beginnt bei +16. Beim Voice-Wrapper reicht es bis in die späteren Runtimefelder hinein; die Diskbytes bei +32/+40 sind daher keine Runtimepointer.

In sämtlichen 13 erfassten SCD-Instanzen steht Byte15 jedes hier gelesenen Sequenzheaders auf null. Das ist ein Dateibefund. Er belegt keine ausgeführte native Mutation und keinen Spielzustand.

## Methode und Grenzen

Die isolierte Console verlinkt vier unveränderte Core-Dateien des AssetArchiveReader. Sie öffnet Quellen nur lesend, dekodiert ausschließlich die zwölf gezielt ausgewählten Package-Records in Arbeitsspeicher und speichert Headerfelder, IDs, Tabellenstatistiken, Längen und Hashes. Textur-Remaster werden in der finalen Probe nicht dekodiert. Kleine HED-Indizes werden vollständig gelesen; die großen PKGs werden nur an den ausgewählten Records gelesen.

Die unabhängige Python-Nachprüfung besteht mit 1.206 Checks. Sie prüft Original-HED-Zeilen, Record-Header, gespeicherte Record-Hashes, Loose-Dateihashes, 52 Tabellenstatistiken und alle ausgegebenen Sequenzfelder erneut. Sie ist kein zweiter unabhängiger Package-Decoder. Die vollständige Archiv-/Loose-Bytegleichheit liefert der unveränderte Produktreader.

Für Tabelle B und C wird am Ziel nur die Ein-Byte-Schranke geprüft; vollständige Objektlängen bleiben unbekannt. Sequenzheader werden für Version3 mit 16 und für Version4 mit 32 Byte geprüft; Aux-Einträge mit 128 Byte. Physische und deklarierte Schranken bleiben getrennt. Kein Codec, kein Trackbytecode und keine Wiedergabe werden ausgeführt oder als gültig bestätigt.

Die Feldzuordnung folgt dem bereits erfassten 09FBD0-/09FD20-Pfad der ORIGIN-Studie und der parallelen Formatprüfung. Diese Retail-Probe selbst ist kein neuer IDA-Funktionscapture.

inventory.json und InventoryProbe.cs.txt halten die vorausgehende kleine Auswahlprobe fest, einschließlich des negativen P_EX100.a.us-Falls. inspect_loose_bar.py prüft zusätzlich nur die BAR-Metadaten von fünf benannten Dateien. Diese Vorprobe ist nicht Teil der zwölf finalen Records.

## Reproduktion

```powershell
dotnet run --project artifacts/audio-retail-witness-20261011/Probe.csproj -- <Spielordner> <absoluter-Pfad-im-Probeordner>/witness.json
py -3 -B artifacts/audio-retail-witness-20261011/verify.py --check
```

Buildausgaben der isolierten Console liegen nur in ihrem lokalen bin/obj. Sie sind nicht Teil des Metadatenmanifests. Produktquellen, docs, build und Paket bleiben unverändert.
