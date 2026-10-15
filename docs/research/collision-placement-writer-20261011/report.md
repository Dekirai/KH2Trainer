# Kollisionskorrektur und Kontaktpunkt-Schreiber

## Ergebnis

`3D1960` ist kein belegter einfacher Actor-Positionssetter. Er schreibt den übergebenen Punkt nach **Objekt+180**, setzt Kontaktflags und kann anschließend weitere native Routinen sowie einen virtuellen Aufruf an Slot+216 ausführen. Die konkrete virtuelle Implementierung und deren Transformänderungen bleiben offen. Sein Rückgabewert ist je nach Pfad `flags >> 8` oder das Ergebnis des virtuellen Aufrufs. Der bekannte Caller `3D0BB0` setzt nach normaler Rückkehr selbst `AL=1`, auch wenn der virtuelle Aufruf null zurückgibt.

`1752E0` verwendet einen eigenen Zustandsdatensatz mit Start, Verschiebung, Radius und Y-Offset. Der Datensatz ist hier kein nachgewiesener kompletter Actor-Körperpuffer. Er wird von `1638F0` für bewegliche Kontexte und `16FEC0` für den statischen globalen Kontext weitergereicht. Die Verbindung zu Actor+2560/+1600 aus der Körpergrenzenstudie ist damit noch nicht geschlossen.

## Was die Volumenabfrage tatsächlich beantwortet

- Rückgabe `0` kann bedeuten, dass keine Kandidaten vorliegen und trotzdem das bewegte Ziel ausgegeben wird.
- Rückgabe `0` kann nach dem abschließenden gerichteten Segmenttest auch bedeuten, dass die Ausgabe auf den ursprünglichen Start zurückgesetzt wurde.
- Bei vorhandenen Kandidaten kann die Einzelabfrage ein zuvor gesetztes Statusbit übernehmen. Erst `16FEC0` löscht dieses vor der Folge aus beweglichen und statischen Abfragen.
- Matrix+164 transformiert Start und Ziel in den lokalen Kontext. Matrix+100 transformiert das Ergebnis zurück. Ein inverses affines Matrixpaar wird lokal nicht geprüft. Der Radius bleibt beim Aufruf des Korrekturhelfers unverändert; eine Matrixskalierung skaliert diesen Parameter hier nicht mit.
- Die Schrittzahl entsteht aus `CVTTSS2SI(lokale Länge / Radius) + 1`. Radius null und Endlichkeit werden nicht lokal geprüft. Ein begrenzter synthetischer Nullradiusfall überspringt die Schleife und lässt alte Ergebniskoordinaten stehen.

Die Kandidatenbegrenzung und die gerichtete Geometrie aus `collision-query-geometry-20261011` bleiben gültige Einschränkungen. Diese Studie ersetzt ihre fehlenden Besitzer-/Längenverträge nicht. Die frühere MINSS-Körpergrenzenabweichung betrifft einen anderen Helfer und ist kein Beleg für die tatsächliche Form dieses Zustandsdatensatzes.

## Punkt- und Metadatenherkunft bei 3D1960

Ein null Nodepointer wählt den statischen Kontext `ABD448`; andernfalls kommt der Kontext aus Node+8. Polygon+10 wählt einen Normaleneintrag aus Kontext+48; Polygon+14 wählt ein Attribut aus Kontext+40. Die Normalenroutine entfernt die Translation aus der verwendeten Matrix und normalisiert XYZ. Sie verwendet keine nachgewiesene allgemeine inverse transponierte Normalenmatrix.

Die Reihenfolge ist lokal fest: Normalen-/Attributzugriff, Flagschreiben, Punktkopie nach Objekt+180, optionale weitere Aufrufe, gegebenenfalls virtueller Slot+216. Ein sicherer Teleport müsste weiterhin den tatsächlichen Actor-Schreiber, dessen Voraussetzungen und Ressourcenbesitz belegen. Ein direkter Aufruf dieses Kontaktpfads wäre derzeit keine begründete Umsetzung.

## Belege und Reproduktion

Acht frische vollständige IDA-Ansichten wurden durch den Root-Agenten aus seiner bestehenden Sitzung erfasst. Meine lokale Toolansicht zeigte eine andere, nicht adoptierte Workerinstanz; `session-list-local.json` hält das fest. Ich habe keine Sitzung geöffnet, keinen Worker neu gestartet und keine Autoanalyse oder IDB-Mutation ausgeführt. Die Root-Captures bleiben unverändert.

Der Verifier vergleicht sämtliche IDA-Originalbytes mit der gepinnten Retail-EXE, dekodiert jede Instruktion separat mit Capstone und prüft vollständige ASM-Seiten. 18 ältere vollständige Bodies sind als Abhängigkeiten gekennzeichnet; frische Aufnahme bedeutet nicht automatisch neue Funktion oder vollständig neue Semantik.

60 gezielte Fälle interpretieren Originalinstruktionen. Vektor-, Matrix-, Bounds-, Quantisierungs- und Retryhelfer laufen als Instruktionsmodelle. Kandidatenliste, eigentliche Polygonkorrekturen, abschließender Segmenttest und opaque Engine-Callbacks besitzen ausdrücklich benannte Effektstubs. Das Modell ist keine vollständige Volumenphysik. Float32 verwendet maskierte Ausnahmen und Rundung zur nächsten Zahl ohne DAZ/FTZ. Speichersperren des Interpreters sind Testgrenzen, keine Schutzprüfungen des Spiels.

```powershell
py -3 -B artifacts/collision-placement-writer-20261011/verify.py --check
```

Es wurden keine Produktdateien, globalen Forschungsdokumente oder Pakete verändert. Kein Spielstart, Attach, Injection, GUI-Eingriff, Save-, Mod- oder Twitch-Zugriff fand statt. Es gibt weder einen gemessenen Spieleffekt noch eine Freigabe für sichere Platzierung.

## Nächste begrenzte Lücken

1. Aufbau/Übernahme des Zustandsdatensatzes durch einen der zehn erfassten direkten `16FEC0`-Caller; die konkrete Liste steht in `root-ida-xrefs-16fec0.json`.
2. Konkrete virtuelle Slot+216-Implementierung auf dem von `3D1960` dekodierten Empfänger und ihr tatsächlicher Transformschreiber.
3. Lebensdauer der beweglichen Listenknoten, beider Matrizen und der Tabellen über die gesamte Korrekturfolge.
4. Vollständige geometrische Bedeutung der gewählten Korrekturmodi sowie die Beziehung zu den beiden Actor-Körperpuffern. Diese Fragen bleiben von den hier geprüften lokalen Schreib-/Rückgabeverträgen getrennt.
