# Native Motion-Payloadkopie: begrenzter Vertrag

Der konkrete Implementierungsvertrag steht in **contract.md**. Die wichtigste Auswahlregel: C+44 ist der physische äußere BAR-Tabellenindex; innen zählt der erste Type9, unabhängig von dessen Link-/Größenfeldern. Die Payload beginnt144 Bytes hinter dem Type9-Datenpointer. Entry+12 begrenzt sie innerhalb einer vom Aufrufer belegten äußeren Reservation. Header+12 ist keine Länge.

## Belege

20 vollständige bereits erfasste Funktionen werden als Abhängigkeiten verwendet:849 Instruktionen,3335 Extentbytes;233 weitere Bytes innerhalb der IDA-Bereiche sind gesondert als Tabellen/Padding ausgewiesen. Es gibt **keine neuen semantischen Funktionsclaims**. Fünf vom Root frisch erfasste vollständige Funktionen stimmen mit diesen Originalbytes und ASM-Zeilen überein. Vierzehn konkret benannte Instruktionsanker prüfen die entscheidenden Count-/Index-/Store-/Pointeroperationen.

Jeder Bytebereich wurde direkt gegen die Original-EXE mit SHA256 `9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed` geprüft und jede aufgeführte ASM-Instruktion zusätzlich mit Capstone dekodiert. Provenienz und vollständige Quellen stehen in evidence.json/dependencies.json. Der Reviewer-Handle zur aktuellen IDA-Session war nicht verfügbar; es wurde keine neue Session geöffnet. Roots Gegenprüfung erfolgte in28e14b48/PID71984. Der gespeicherte Healthcheck zeigt Hex-Rays bereit, keine laufende Analyse, aber `auto_analysis_ready=false`. Das ist keine globale Vollständigkeitsgarantie der IDB.

## Enger Ausführungsnachweis

`native-find-results.json` hält zehn Fälle fest, die den unveränderten89-Byte-Körper von3A6420 in diesem privaten Python-Prozess ausführen. Diese Funktion enthält keinen Call, keine globalen Datenzugriffe und nur lokale Sprünge. Jede Eingabetabelle ist ein eigener64-Byte-Puffer. Geprüft werden signed negative/zero Counts, Wildcardordinal über andere Typen, typed occurrence, fehlender Typ, Index am Ende und negativer occurrence. Der native erste Type9 bleibt auch mit Linkbit, null Pointer und null Länge der erste Treffer. Ein späterer gültiger Eintrag wird nicht als Ersatz gewählt.

Der Nachweis führt keine Spiel-/Enginefunktion mit Globals, keinen Decoder, Konstruktor oder Binder aus. Er testet den originalen Auswahlprimitive, **keinen fertig implementierten Kopierer**. Die zusätzliche Admission-/Lebensdauerabsicherung und Kopierfehler müssen in den künftigen Produkttests separat geprüft werden. Das Testskript und seine Originalbytes sind im Ergebnis gepinnt.

## Reproduktion

```
py -3 -B artifacts/motion-native-copy-contract-20261011/verify.py
```

Der Standardlauf prüft Originalbytes, ASM, Quellenpins, Gegen-Captures, gespeicherten engen Ausführungsnachweis und exaktes Manifest ohne nativen Code auszuführen. Er benötigt Python und Capstone.

Eine erneute bewusste Ausführung des isolierten Primitivs unter Windows x64:

```
py -3 -B artifacts/motion-native-copy-contract-20261011/verify.py --write --native
```

`--write` regeneriert nur abgeleitete Dateien dieses Ordners. Das Manifest ist nach einer Änderung neu zu erstellen. Produktquellen, Docs, v0.12.19, Spiel und IDB werden von dieser Studie nicht verändert.
