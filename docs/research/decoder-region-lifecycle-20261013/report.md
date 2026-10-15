# Lebensdauer der Ptr32-Regionstabelle

## Ergebnis

Die normale Zeigerkodierung verwendet **64 Regionsbasen mit jeweils 32 MiB Adressspanne**. Der untersuchte Encoder findet eine passende Basis oder belegt den ersten freien Platz. In diesen ausgewählten Routinen gibt es keinen normalen Pfad, der belegte Plätze wieder freigibt. Bei voller Tabelle ohne passende Basis erzeugt der Encoder trotzdem einen Wert: Dessen Regionsindex wird beim Dekodieren zu **0**. Ein solcher Zustand im laufenden Spiel wurde hier nicht beobachtet.

Die einmalige Initialisierung besitzt ein eigenes Guard-Protokoll und einen registrierten Abbruchpfad. Dessen Schutz erstreckt sich nicht automatisch auf die späteren Encoderaufrufe. Diese Unterscheidung schränkt die bislang allgemeine Frage nach Änderungen an der Decodertabelle ein.

## 1. Initialisierung und Veröffentlichung

`4AD2C0` vergleicht den globalen Guard `2B0D920` mit dem TLS-Wert bei `+16`. Der langsame Pfad ruft `439F50` auf. Nur wenn der Guard anschließend `-1` ist, werden **achtmal acht QWORDs** ab `2B0D720` auf `UINT64_MAX` gesetzt. `439EF0` veröffentlicht danach den erhöhten globalen Epochwert im Guard und im TLS-Feld.

`439F50` setzt einen noch nullen Guard unter einer gemeinsamen Critical Section auf `-1`. Bei bereits laufender Initialisierung wartet es mit `43A028(100)` und prüft erneut. Die Critical Section wird vor der Rückkehr verlassen. Die folgenden Tabellenstores laufen somit nicht innerhalb einer vom Aufrufer weiterhin gehaltenen Critical Section; der Guard kennzeichnet ihren laufenden Zustand.

Der Abschlusshelfer erhöht einen DWORD-Epochwert ohne eigenen Überlaufcheck. Die Untersuchung belegt die vorhandenen Operationen, keine universelle Korrektheit des CRT oder aller Betriebssystemaufrufe.

## 2. Fehlerbehandlung ist ein eigener Pfad

Die Original-PE enthält für `4AD2C0` den Runtimeeintrag `[4AD2C0, 4AD386, 6FB948]`. Die Handlerdaten verweisen auf `5FA7C0`; dessen Unwindmap bei `6FB918` enthält die Aktion `5707A0`.

Diese Aktion lädt die Adresse des Ptr32-Guards und springt zu `439EC0`. Der Helper löscht den Guard unter der Critical Section und benachrichtigt Wartende. **Er löscht keine Regionseinträge.** Ein erneuter Initialisierungsversuch kann anschließend den Sentinel-Durchlauf wieder ausführen. Daraus folgt weder, dass ein solcher Fehler im Spiel auftritt, noch dass andere Threads eine teilweise initialisierte Tabelle verwenden dürfen.

Die vollständige Sprach- und Betriebssystembehandlung von Exceptions ist nicht Bestandteil dieses Befunds. Die konkrete Verknüpfung der PE-Metadaten und die Instruktionen der ausgewählten Aktion sind bytegenau geprüft.

## 3. Encoder: vorhandene Basis, freier Platz, volle Tabelle

`4AD390` bildet aus dem Eingabepointer:

```
Basis  = pointer & ~0x01ffffff
Offset = pointer &  0x01ffffff
```

Der lineare Scan prüft bis zu 64 QWORDs:

| Zustand | Lokale Folge |
|---|---|
| Eintrag ist `UINT64_MAX` | Basis wird in diesen Platz geschrieben; Index und Offset werden kodiert. |
| Eintrag stimmt mit der Basis überein | Derselbe Index wird ohne Tabellenstore verwendet. |
| Alle 64 sind belegt und verschieden | Rückgabepfad mit Indexwert 64; kein Tabellenstore, kein expliziter Fehler. |

Im letzten Fall führt der 32-Bit-Shift `64 << 25` zu `0x80000000`. Das zusätzliche Setzen von Bit 31 ändert daran nichts. Der Decoder entfernt dieses Markerbit vor der Indexbildung und verwendet daher **Tabellenplatz 0 mit dem ursprünglichen niedrigen Offset**. Die Rechnung folgt dem vollständig geprüften Instruktionspfad. Sie ist kein durchgeführter nativer Ausführungstest.

## 4. Welche Synchronisierung ist tatsächlich gezeigt?

Die zwei aufgezeichneten direkten Encoderaufrufer `4AD240` und `4AD280` rufen zuerst den Initialisierer auf und springen danach zum Encoder. Der Guard schützt die Initialisierung; die gezeigte Encoderroutine selbst enthält weder einen Lock noch eine atomare Reservierung des freien Platzes.

Ein tatsächliches konkurrierendes Fehlverhalten ist damit nicht nachgewiesen. Dafür wären die relevanten Aufrufer und ihre Threadzuordnung nötig. Die Frage lässt sich nun konkret auf die Encoderaufrufe und andere wirkliche Tabellenwriter richten, statt die einmalige Initialisierung mit laufender Registrierung gleichzusetzen.

Die Abfrage aller 64 Slotadressen fand nur drei direkte Verweise auf die Tabellenbasis: Initialisierer, Encoder und Decoder. Das ist ein vollständiger Befund für diese IDA-Abfragen, **kein Beweis gegen beliebige indirekte Schreibzugriffe**.

## 5. Bedeutung für den Trainer

- Ein voller Encoder kann keinen verlässlichen neuen Pointer liefern. Ein späterer Anbieter muss Herkunft und passende Regionseinträge belegen; die bloße Existenz eines kodierten Werts genügt nicht.
- Die Regionstabelle beschreibt Adressbereiche. Gleiche Tabellenbytes schließen eine Freigabe und erneute Belegung innerhalb derselben 32-MiB-Region nicht aus. Die Ressourcen- und Actor-Lebensdauer braucht weiterhin eigene Belege.
- Ein Beobachter für Decoderänderungen muss Initialisierung einschließlich Abbruch/Wiederholung von normalen Encoderstores unterscheiden. Einen gewöhnlichen Slotfreigabepfad zeigen die ausgewählten Körper nicht.
- `MotionPayloadCopy` ruft bereits keine native Encoder-/Decoderfunktion auf und prüft die fremd gelieferte Regionstabelle. Dieser Befund allein liefert noch keinen produktiven `ReadScope`; deshalb wurde keine unfertige Anbindung aktiviert.

## Prüfung und Grenzen

**12 vollständige Körper, 211 aufgezeichnete Instruktionen, 891 Originalbytes**: sieben frische Körper und fünf bytegenau wiederverwendete Körper. Vier zusätzliche Alignmentbytes innerhalb dieser Körper sind getrennt ausgewiesen. Dazu kommen 116 Bytes PE-Metadaten und 33 konkrete Instruktionsanker. Alle Daten wurden gegen die Original-EXE mit SHA256 `9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed` geprüft.

`verify.py --check` prüft Körper, Instruktionsgrenzen, Metadaten, vollständige Xref-Ergebnisse und die gespeicherten Ableitungen. Die neun Funktionsclaims sind lokal begrenzt. Es wurden keine Spielfunktionen ausgeführt, keine Spielstände geändert und kein neues Release gebaut.


## Documentation import and independent review

The frozen study and independent review, including both manifests, are preserved byte-for-byte in `evidence.zip`. `provenance.json` maps each normalized body to its archived source. Existing complete IDA instruction lists are wrapped as one page; the original bytes, data and alignment spans remain separate from instruction counts. No new capture or semantic assertion is added.

The imported report contains 9 bounded claim records backed by 12 complete bodies, including reused evidence. These are occurrence counts; global coverage deduplicates by function address. `EvidenceNormalization` records every link adaptation, including sections preserved in `evidence.json` and raw files retained inside the archive. Run `verify.py --check` for read-only archive, original-PE, normalization and reference checks. The archived scripts retain their original paths.
