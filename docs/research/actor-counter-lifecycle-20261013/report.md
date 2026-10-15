# Actorreferenzen: zusätzliche Kontextpfade

## Ergebnis

Die zusätzliche Stelle `3E1790` setzt das Kontextflag zurück, bevor sie bei einem fehlenden Ereignis die Actorreferenz freigibt. Die frühere Aussage zur Wiederholungssicherheit der Freigabe gilt deshalb weiterhin nur, solange das Freigabe-Bit gesetzt bleibt. Eine zulässige Spielsequenz, die einen bereits freigegebenen Kontext erneut startet und dadurch den Zähler falsch verändert, ist hier **nicht nachgewiesen**.

Außerdem sind die Referenz des übergeordneten Skriptkontexts und die Lebensdauer seiner Unterkontexte getrennt. Jeder neu konstruierte Unterkontext übernimmt den Ownerzeiger und trägt bei nichtleerem Owner seine eigene Referenz zu `Actor+1464` bei. Der übergeordnete Kontext kann seinen Beitrag bereits freigeben, während Kinder noch weiterlaufen.

## Neue Writer- und Startpfade

- `3E1790`: `FindEvent` läuft zuerst. Danach wird `DWORD(context+56)=0` geschrieben. Bei einem Ergebnis `<=0` erfolgt über `QWORD(context+96)` der zusätzliche direkte `DEC DWORD(owner+1464)` an `3E17E3`; anschließend wird Maske `0x2` gesetzt. Der alte Zustand dieser Maske wird nicht geprüft. Bei einem positiven Ergebnis führt ein Tailcall zu `41B320`. Dessen vollständiger Körper setzt den Ausführungseintrag und Stackdaten; er enthält keinen expliziten Counter-Inkrement und keinen Release-Bit-Test.
- `3B5F30` ist ein ausgewählter Aufbaupfad: neuer Kontext mit Actor als Owner, Speicherung in `Actor+1456`, temporäres Ereignis0, dann Start von Ereignis1. Das Ereignis0 kann Skriptcode ausführen, und der Zeiger wird anschließend erneut geladen. Daher ist nicht bewiesen, dass Zustand und Zeiger zwischen Konstruktion und Start unverändert bleiben.
- `3C6150` verwendet einen bestehenden, aus `input DWORD+0` decodierten Kontext für Ereignis21. Ein Kontextneubau oder ein lokaler Test der Freigabemaske fehlt. Ob dieser Kontext zuvor bereits freigegeben wurde, ob Ereignis21 existiert und welche Wirkung der optionale Aufruf `3D7E90` hat, bleibt offen.
- Der getrennte Bereich `3E1810..3E1840` enthält einen weiteren `DEC` an `3E182B` nach demselben Flagreset. Bei positivem `EDX` springt er direkt zu `41B320`. IDA ordnet den Bereich **keiner Funktion** zu und meldet am Anfang keine Xrefs. Er ist daher ein begrenzter Codebeleg, keine neue vollständige Funktion und kein Nachweis erreichbaren Spielverhaltens.

## Kontextaufbau und -abbau

| Körper | Konkreter lokaler Beitrag |
| --- | --- |
| `3E1970` | Allokiert112 Bytes, übernimmt Skript/Shared Data/Owner aus Quellkontext `+0/+88/+96`, konstruiert einen neuen Kontext, setzt Maske1 und Feld+60, bereitet den Einstieg vor und gibt den Kontext zurück. Kein lokales Einhängen in eine Liste. |
| `3E1E30` | Baut auf dieselbe Weise einen Unterkontext und hängt ihn an die Elternliste mit Kopf+72, Ende+80 und gepacktem Next-Link DWORD+68. |
| `3E1C80` | Bearbeitet die Kinder auch bei gesetzter Freigabemaske des Elternkontexts. Nur ein Kindrückgabewert1 führt zu Entfernen, Next-Link-Löschung, Cleanup und Allocator-Aufruf. Der eigene Rückgabewert1 verlangt gesetzte Maske2 **und** leere Kindliste. |
| `3E1F00` | Entfernt Kinder mit `(DWORD(child+60) & arg2)==arg3`, unabhängig vom Update-Rückgabewert. Repariert Kopf/Ende/Links, ruft Cleanup und danach den Allocator auf. |
| `3E1530` | Führt zuerst `3E1410` aus. Nur Maske1 im Argument erlaubt danach den Allocator-Aufruf bei nichtgesetzter Maske4 oder den Aufruf `031DD0(context,112)` bei gesetzter Maske4. Die Wirkung von `031DD0` wird hier nicht aus seinem Namen abgeleitet. |
| `26AE40`, `3E1910`, `3E15A0` | Ein alter Kontext wird in eine globale Liste übernommen; der Slot erhält anschließend einen neu angelegten Kontext ohne Actorowner. Der getrennte Listenabbau ruft je Kontext Cleanup und Allocator auf. Wann dieser Abbau später läuft, ist nicht geschlossen. |

Die maskierte Freigabe innerhalb `3E1410` bleibt an den Kontextzustand gebunden. Der gesamte Destruktor ist nicht wiederholungssicher nachgewiesen: Skripte und Ressourcen werden schon vor dieser Maske behandelt. Listenentfernung und Aufruf des Allocators sind außerdem keine vollständige Prüfung der jeweiligen Allocatorimplementierung.

## Bedeutung für Actor-Retirement und Trainer

Ein angehaltener oder beendeter Elternkontext sagt allein wenig über `Actor+1464` aus: Unterkontexte können weitere Beiträge halten; Angriffe und Commands sind zusätzliche Quellen. Ein Trainer darf diesen Zähler deshalb weder anhand einer Kontextliste neu berechnen noch beim Stoppen eines Skripts pauschal auf null setzen. Die vorhandene reine Diagnose bleibt die passende Anwendung dieser Erkenntnis. Diese Studie ändert kein Produktverhalten.

Die Resetstelle ist eine konkrete Grenze für allgemeine Aussagen wie „Freigeben ist beliebig oft sicher“. Sie ist ein Ausgangspunkt für einen späteren gezielten Aufruferbeweis. Sie belegt für sich keine erreichbare Counter-Unterlauf-, Crash- oder Lebensdauerverletzung.

## Verifikation und Grenzen

- Original-EXE SHA256: `9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed`.
- 4 frische vollständige Körper:116 Instruktionen,432 Bytes.
- 13 wiederverwendete vollständige Körper:716 Instruktionen,2627 Bytes, erneut gegen die Original-EXE geprüft.
- Zusammen17 vollständige Körper:832 Instruktionen,3059 Bytes. Diese Zahl ist keine Zahl neu entdeckter Funktionen.
- Separat48 Bytes ohne IDA-Funktionszuordnung:12 Instruktionen/43 Codebytes und5 Alignmentbytes.
- Vollständige Grenzen, Bytes, Instruktionsanfänge und Mnemonics werden gegen das Original geprüft. Vierzehn kritische Operanden werden zusätzlich ausdrücklich verglichen; vierzig Stellen sind im Beleg als Anker festgehalten.
- Keine native Ausführung, kein Modelltest, keine Veränderung von Spiel, Save, UI, Twitch, Produkt, eingefrorenen Dokumenten, Coverage oder Paketen.
- `3E1790` hat14 Code-Xrefs und eine Datenreferenz im ausgewerteten Root-Capture. Diese Studie schließt nur die ausgewählten Caller und behauptet keine vollständige Aufrufer- oder Writeranalyse.

Maschinenlesbare Claims und Einzelgrenzen stehen in `report.json`; `verify.py --check` prüft Originalbindung, Belegreferenzen und Manifest.


## Documentation import and independent review

The frozen source study and review are preserved byte-for-byte in `evidence.zip`, including their manifests. `provenance.json` pins every archive member and maps every normalized body to its archived original record. Stored IDA lines are wrapped as one complete page and original bytes are spaced for the existing coverage parser. No new capture, runtime behavior or complete-semantics claim is added.

This document contributes 9 bounded per-function claim records and 1 separate range findings, backed by 17 complete bodies. Global coverage deduplicates function addresses against prior work; these record counts are not counts of newly understood functions. Run this folder's `verify.py --check` for read-only archive, original-byte, normalization and reference checks. The archived author scripts retain their original paths.
