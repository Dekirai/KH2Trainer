# Resource-Lookups und gespeicherte Texture-Aliase

## Ergebnis

Alle sieben aufgezeichneten direkten Aufrufer von `12E180` setzen das zweite Argument auf null. Damit lösen sie den gefundenen ResourceEntry **nicht** aus seiner Registrierungsliste. Die untersuchten Texture-Pfade speichern dennoch echte Bufferaliase: `Texture+128` enthält den übergebenen ursprünglichen Pointer, der auch innerhalb des registrierten Bereichs liegen kann. Ein Klon kopiert diesen Pointer erneut.

Der an die Konstruktoren weitergereichte Pointer `ResourceEntry+520` wird dort als Quelle für zwei QWORD-Kopien nach `Texture+88/+96` verwendet. Diese beiden Werte sind kein gespeicherter ResourceEntry-Zeiger. Daneben liefert die Namensfunktion geliehene Zeiger in den ResourceEntry und kann dessen Metadaten ändern. Diese drei Formen sind getrennt zu betrachten: Bufferzeiger, kopierte Identifikationswerte und geliehene Namenszeiger.

Die Ergebnisse schließen die ausgewählten direkten Argument- und Speicherpfade. Sie schließen **keine globale MSET-Lebensdauergarantie**: Die direkten Aufrufer gehören zu Texture-Pfaden; ein MSET-spezifischer Motionconsumer ist damit nicht bewiesen.

## Die sieben direkten Lookup-Kanten

| Aufrufer | Lookup-Kante | Konkrete Nutzung des Ergebnisses |
| --- | --- | --- |
| `12A200` | `12A367` | Kopiert Entry+520/+528 nach Texture+88/+96 und kann einen Replacement-Knoten mit Rückverweis auf die Textur einhängen. Gibt die Textur zurück. |
| `12A7C0` | `12A800` | Nutzt Entry+16 für Namen/Index und reicht den Entry als Argument6 an `12A4C0` weiter. |
| `12AA20` | `12AA6F` | Vergleichbarer Entry-/Metadatenpfad; reicht den Entry als Argument6 an `12A4C0` weiter. |
| `12B1C0` | `12B343` | Sucht über den zuvor in einen Klon kopierten Texture+128-Pointer. Ändert Entry+1616 für Klon-/Namensverwaltung und kann einen Rückverweis zum Klon einhängen. |
| `12B770` | `12B7E2` | Vergleicht den frischen Primary-Lookup mit dem frischen Zwei-QWORD-Lookup `12E230`. Liefert eine Entscheidung zurück. |
| `12BA80` | `12BB46` | Führt den entsprechenden Vergleich in einer durch einen Zeitvergleich gestarteten Listeniteration aus; ausgewählte Entfernungspfade rufen `12AD50` auf. |
| `12C5A0` | `12C5A2` | Zweibefehl-Wrapper: `xor edx,edx` und Tailjump. Gibt den rohen Entry zurück; keine aufgezeichneten eigenen Aufrufer. |

Für jede Kante wurden der tatsächliche XOR-Befehl und alle Instruktionen bis zur Übergabe geprüft. Dazwischen gibt es weder einen RDX-Schreiber noch einen Call/Sprung. Direkte Sprünge innerhalb desselben Körpers überspringen den XOR nicht. Dies ist ein Beweis für diese direkten Kanten; indirekte Aufrufe und veränderte Laufzeitdaten bleiben außerhalb des Umfangs.

## Was die Texture-Objekte behalten

`12A4C0` übergibt zwei unterschiedliche Werte an seine Konstruktoren:

- Den ursprünglichen Lookup-Pointer als Rawbufferwert für `Texture+128`.
- `Entry+520` als Adresse zweier Identifikationswerte. `12B650` kopiert deren Inhalt nach `Texture+88/+96`; der Adresse selbst wird dort kein Handle-Slot zugewiesen.

Zusätzlich gelangt `ReplaceEntry+96` als Payload nach `Texture+104`. Nach Rückkehr durch den Upload-Wrapper und der Listenveröffentlichung speichert `12A4C0` die Textur in `ReplaceEntry+112` und leert die Quellzelle `ReplaceEntry+96`. Diese lokale Abfolge gilt für die geprüften erfolgreichen Pfade; sie beweist keine komplette GPU- oder Allocatorlebensdauer.

Der allgemeine Erzeuger `14BB10` schreibt am gemeinsamen erfolgreichen Ende die beiden ursprünglichen Descriptorpointer nach `Texture+128/+136`, auch wenn zuvor ein temporär konvertierter Buffer verwendet und wieder freigegeben wurde. Bei `12A200` kann ein expliziter Lookup-Override vom Descriptorpointer abweichen. Der Lookup-Pointer und das später gespeicherte Descriptorfeld sind deshalb nicht allgemein identisch.

`12B1C0` erzeugt ein weiteres Objekt mit Kopien von `+104`, `+128`, `+136` und den Identifikationswerten. Es setzt Byte+152 auf1. Die passende lokale Bereinigung `12AD50` ruft `_aligned_free(Texture+104)` nur bei Byte+152 gleich0 auf. Der Klon überspringt damit diesen konkreten Free-Aufruf. Ein allgemeiner Besitz- oder Sicherheitsbeweis folgt daraus nicht.

## Geliehene Namen sind eigene Aliase

Die Aufrufer geben `M=Entry+16` an `12C220` weiter. Der Rückgabewert zeigt auf `M+16` oder `M+80`, also `Entry+32` oder `Entry+96`. Diese Funktion kann außerdem den Zähler `Entry+536` und die Tabelle ab `Entry+540` ändern. Sie ist kein reiner Getter.

Diese Metadaten sind von den Identifikationswerten bei `Entry+520/+528` zu unterscheiden. Die vollständigen kleinen Helfer `12C530` und `12C4E0` lesen die Tabelle für einen skalaren Offset/Index beziehungsweise eine Zwei-Bit-Klassifikation. Sie speichern den übergebenen Metadatenzeiger lokal nicht dauerhaft.

## Bereinigung und verbleibende Grenze

Die Texture-Bereinigung verwendet frische Lookups: `12E230` vergleicht die zwei gespeicherten Werte; `12E180` sucht erneut über `Texture+128`. Stimmen die beiden Entry-Adressen nicht überein, wählen die untersuchten Pfade eine Entfernung beziehungsweise liefern die entsprechende Entscheidung. Das ist ein konkreter Zuordnungscheck, aber weder ein Generationstoken noch eine Sperre gegen gleichzeitige Veränderungen.

Entry-Retirement in `12E460` prüft `Entry+1616` nicht als Sperre. Auf dem Benachrichtigungspfad markiert es zugehörige Texturen mit `+184=0`, `DWORD+176=10` und `DWORD+180=1`, sofern deren Zustand+180 nicht-1 ist. Danach kann der ResourceEntry entfernt und zerstört werden. Der lokale Code wartet dabei nicht auf die spätere Texture-Listenbereinigung. Der Entry, seine Texturen und ihre Buffer haben damit getrennte lokale Verwaltungspfade.

`12AD50` gibt lokal den Payload+104 unter dem genannten Flag frei, bereinigt weitere Handles, entfernt die Textur aus ihrer Managerliste und ruft den virtuellen Destruktor auf. Seine eigenen Instruktionen übergeben die Rohpointer+128/+136 nicht an `_aligned_free`. Die aufgerufenen Renderer-, Handle- und virtuellen Destruktorfunktionen sind ausdrücklich weitere Grenzen; ihre vollständigen Nebenwirkungen werden nicht ausgeschlossen.

**Folgerung:** Ein leerer Resource-Index oder der Verzicht auf den Detach-Modus beweist nicht das Ende aller Bufferaliase. Diese Studie liefert konkrete Texture-Aliase und einzelne spätere Zuordnungsprüfungen. Für dynamischen MSET-Austausch ist weiterhin ein eigener Nachweis der tatsächlichen Motionconsumer und ihrer Lebensdauer nötig. Es wurde keine Änderung am Trainer daraus abgeleitet.

## Originalprüfung und Provenienz

- Original-EXE SHA256: `9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed`.
- 17 frische vollständige Körper: 1.889 Instruktionen, 7.298 Bytes, darin 66 explizite Nichtinstruktionsbytes.
- 6 wiederverwendete vollständige Körper: 791 Instruktionen, 3.045 Bytes, erneut gegen das Original geprüft.
- Insgesamt 23 Körper, 2.680 Instruktionen und 10.343 Bytes. Diese Zahl ist keine Zahl neu entdeckter Funktionen.
- 61 exakt verglichene Operandenanker, 7 geprüfte direkte Lookup-Kanten, 13 begrenzte Claims und 52 auflösbare Belegreferenzen.

`caller-instructions.json` enthält beim ersten Capture nur10 Vorschauzeilen pro größerem Körper trotz vollständiger Metadatenzähler. Es bleibt als **überholte Provenienz** erhalten und wird nicht zur Vollkörperprüfung verwendet. Die vollständige Ersatzdatei und alle Helper-Captures werden auf `count==scanned==matches.length`, abgeschlossene Cursor und originalgetreue Bytes/Instruktionsgrenzen geprüft.

Keine native Ausführung, keine Simulation, keine Änderung an Spiel, GUI, Twitch, Save, Produkt, Dokumentation, globaler Coverage oder Paketen. Die globale IDA-Analysebereitschaft wurde nicht unabhängig beobachtet. `report.json` enthält die einzelnen Voraussetzungen und Grenzen; `verify.py --check` prüft die Originalbindung und den eingefrorenen Manifeststand.


## Documentation import and independent review

The frozen study and independent review, including both manifests, are preserved byte-for-byte in `evidence.zip`. `provenance.json` maps each normalized body to its archived source. Existing complete IDA instruction lists are wrapped as one page; the original bytes, data and alignment spans remain separate from instruction counts. No new capture or semantic assertion is added.

The imported report contains 13 bounded claim records backed by 23 complete bodies, including reused evidence. These are occurrence counts; global coverage deduplicates by function address. `EvidenceNormalization` records every link adaptation, including sections preserved in `evidence.json` and raw files retained inside the archive. Run `verify.py --check` for read-only archive, original-PE, normalization and reference checks. The archived scripts retain their original paths.
