# Unabhängiger Vergleich des Audioinspektors

Der neue Produktparser besteht **6.005 Vergleiche** mit den eingefrorenen Retail-Metadaten: 13 SCD-Instanzen und drei ORIGIN-Wrapper wurden jeweils durch Archiv- und Loose-Locators gelesen, insgesamt 32 Inspektionen. Die ausgewählten Dateien gehören zu zwölf bereits untersuchten Archivrecords. Es wurden keine Audiodaten exportiert.

Verglichen wurden Headerprofil, Version, Bank-ID, Counts, physische/deklarierte Länge, Tabellenbasen, negative und Nullziele, Offsetextrema und Mehrfachvorkommen, minimale Zielspannen sowie jede zuvor erfasste Sound-ID und Trackanzahl. ORIGIN-Namen und DWORD +12 stimmen ebenfalls überein. Der Produktreader übernimmt die Quellenidentität und die Grenzen verschachtelter BARs. Die frühere Studie belegt den damaligen vollständigen Archiv-/Loose-Bytevergleich; dieser neue Lauf behauptet keinen erneuten Vergleich sämtlicher Payloadbytes.

Zusätzlich verarbeitete der tatsächliche Parser **4.096 deterministische synthetische Eingaben** mit verschiedenen Versionen, Profilen, Counts, Offsets und Lesebudgets. Ein separat geschriebener Stream lehnt jeden Seek oder Read außerhalb seines Bytebereichs ab. **32.768 Prüfungen** bestätigen unveränderte Eingabebytes, begrenzte Ausgaben, korrekte Readzählung und die Trennung von lesbaren Sequenzheadern und ungeprüften Zielen. Diese endliche Stichprobe beweist keine allgemeine Fehlerfreiheit.

Die Probe verlinkt fünf aktuelle Coredateien direkt. Sie baut in einem eigenen bin/obj-Verzeichnis und führt weder einen Spielprozess noch native Spielfunktionen aus. Package-Dekodierung kann den vollständigen gewählten Payload innerhalb der 64-MiB-Grenze lesen; das 1-MiB-Metadatenbudget des Inspektors umfasst diese Arbeit nicht.

`review.json` enthält Ergebnisse und Quellhashes. `Program.cs` prüft die öffentliche Locator-API, `Fuzz.cs` prüft den internen begrenzten Streamparser. Die Eingaben der synthetischen Probe sind reproduzierbar; ein Erfolg gilt ausschließlich für die gepinnten Quellen und diesen Umfang.

```powershell
dotnet run --project artifacts/audio-inspector-retail-20261011/Probe.csproj -c Release -- "E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-"
py -3 -B artifacts/audio-inspector-retail-20261011/verify.py
```

Der Verifier prüft gespeicherte Ergebnisse und Hashes. Er liest keine Spieldateien und führt den Vergleich nicht erneut aus. Generierte bin/obj-Dateien sind kein Teil des Manifests.
