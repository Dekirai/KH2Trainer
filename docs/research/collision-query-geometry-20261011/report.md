# Gerichtete Kollisionsabfrage und Grenzen für Platzierung

## Ergebnis

`173B30` liefert einen ausgewählten Schnittpunkt und einen Polygonindex. Es
liefert keinen Segmentparameter und prüft keinen Actor-Körper. Bei endlichen,
konsistenten Daten und einem passenden affinen Matrixpaar kann man den Punkt
als Schnittpunkt des gerichteten Eingabesegments verstehen. Diese Voraussetzungen
werden in der Funktion nicht geprüft. Die Studie erteilt deshalb keine Freigabe,
die Funktion allein als sichere Teleport- oder Platzierungsprüfung zu verwenden.

Die wichtigste neue Gegenprobe betrifft die Kandidatenliste: Von 1.024 durch den
Collector akzeptierten Polygonen liegt nur das letzte über dem Testsegment. Die
vollständige originale Rechenkette meldet keinen Treffer, weil höchstens 1.023
Kandidaten aufgenommen werden. Wenn dasselbe letzte Polygon allein abgefragt
wird, trifft es. Ein negatives Ergebnis beweist somit keine freie Strecke.

## Punkt, Richtung und Matrixannahmen

Der Eingabepuffer enthält Start und Ende als zwei `float4`. Bei Context-Byte+229=0
werden beide zunächst mit Matrix+164 multipliziert. Erst danach setzt die Abfrage
W von Ursprung und Differenzvektor auf 1. Der primitive Schnitt berechnet mit
Float32-Schritten:

```
dn = dotXYZ(normal, end - start)
t  = (dotXYZ(normal, vertex0) - dotXYZ(normal, start)) / dn
point = start + t * (end - start)
```

Geordnete Werte benötigen `dn < 0` und `0 <= t <= 1`; beide Endpunkte sind
enthalten. Danach folgen gerichtete Kantenprüfungen. Umgedrehte Richtung,
parallele Strecke und Strecke der Länge null haben keine allgemeine symmetrische
Treffergarantie. Die Kantenprüfung benutzt die absolute Float32-Toleranz 0,01
gegen einen Skalar mit dem übergebenen Normalenvektor; dessen Normalisierung ist
hier nicht belegt.

Der nächste ausgewählte Punkt gewinnt nach strikt kleinerer lokaler
XYZ-Quadratdistanz, anfänglich begrenzt durch Float32(1e14). Gleiche Distanz
behält den zuerst gefundenen Kandidaten. Auf Erfolg folgt gegebenenfalls
Matrix+100. Diese Multiplikation verwendet W und dividiert nicht anschließend
durch W. Ein synthetisches inkonsistentes Matrixpaar gibt erfolgreich einen
Punkt außerhalb des ursprünglichen Segments zurück. Ein weiterer Fall zeigt,
dass ein Eingabe-W ungleich 1 die anfängliche Transformation beeinflusst.

Die lokale primitive Ausgabe kann schon vor einem fehlgeschlagenen Kantentest
geschrieben sein. `173B30` verwendet dafür einen temporären Puffer und belässt
die Ausgabe des Aufrufers bei fehlender Auswahl unverändert; den Polygonindex
setzt es auf FFFF. Unter maskierten Gleitkommaausnahmen passieren NaN-Werte die
ungeordneten Primitivvergleiche. Die äußere Distanzauswahl verwirft den im Modell
entstehenden NaN-Punkt. Das ist keine allgemeine Endlichkeitsprüfung.

## Traversal und vorhandene Aufrufer

Die bereits untersuchten Bounds- und Traversalhelfer sind vollständig als
gekennzeichnete Vorarbeiten eingebunden. Der native Collector überprüft weder
Indexgrenzen noch Zyklen. Ein Child-WORD außer FFFF wird vor seiner Verwendung
als Nodeindex vorzeichenerweitert. Negative Indizes und ein Selbstzyklus führen
in der synthetischen Maschine zu deren Speicher- beziehungsweise Rekursionsstopp.
Diese Stopps sind Schutzmaßnahmen des Verifiers und keine Schutzmaßnahmen im
Spiel. Die Quantisierung verwendet den Headerindex ungeprüft und ist keine
allgemeine symmetrisch sättigende Konvertierung beliebiger Koordinaten.

`171090` fragt zuerst bewegliche Collider ab. Der bereits dokumentierte
bewegliche Pfad überschreibt bei Treffern das Segmentende. Danach wird der
statische Kontext `ABD448` mit diesem Segment abgefragt. Ein statischer Treffer
ersetzt auch einen beweglichen Treffer exakt am verkürzten Endpunkt und setzt
die Nodeausgabe auf NULL. Bei statischem Fehlschlag bleibt der bewegliche
Treffer erhalten. Im Modell läuft die komplette statische Kette; der bewegliche
Listenpfad wird ausdrücklich durch seine dokumentierten Ausgabeeffekte ersetzt.
Sein Besitz- und Lebensdauervertrag wird damit nicht geschlossen.

`40C2B0` ist ein konkreter höherer Ergebniswrapper: Er setzt beide Eingabe-W auf 1
und verwendet DWORD+20=-1 als Ungültigkeitsmarker. Flagbit16 wählt den kombinierten
Pfad mit den unteren 16 Bits als Kategorie; sonst geht der volle DWORD an den
statischen Pfad. Koordinaten können nach Fehlschlag alt bleiben.

`3F3CC0` konstruiert die vertikale Strecke von Y-50 nach Y+100, übernimmt jedoch
das Eingabe-W. Nach Fehlschlag gibt es den ursprünglichen Punkt bei weiterhin
falschem Rückgabewert aus. Eine plausibel aussehende Ausgabe ist kein Treffer.
`3D0BB0` besitzt einen weiteren konkreten Kategorie-4-Pfad mit W=1 und optionaler
zweiter Probe ab dem Zielpunkt um einen Resource-Bytewert in positiver Y-Richtung.
Die Semantik seines anschließenden Schreibaufrufs `3D1960` bleibt offen.

## Konsequenz für eine spätere Mod-Funktion

Ein endliches Start-/Zielpaar mit W=1 und ein überprüfter Rückgabewert reichen
noch nicht. Eine praktische Platzierungsfunktion benötigt zusätzlich:

1. Einen belegten aktuellen Besitzer der BAR-/Tabellendaten und einen Vertrag,
   der deren Gültigkeit über die gesamte Abfrage erhält. Ein roher Pointer und
   ein nachträglicher Vergleich ersetzen diesen Vertrag nicht.
2. Geprüfte Tabellenlängen, Indizes, Topologie und Matrixannahmen. Ein negatives
   Ergebnis bei erschöpfter Kandidatenliste muss als unvollständig gelten.
3. Eine Prüfung des benötigten Körpervolumens sowie eine begründete Kategorie-,
   Neigungs- und Freiraumregel. Ein gerichteter Linienschnitt ist dafür allein
   ungeeignet. Bereits erfasste körperbezogene Pfade wie `1752E0` bieten die
   nächste begrenzte Untersuchung; Actor-Radien und Transformcache bleiben Teil
   des Vertrags.
4. Einen belegten finalen Bewegungs-/Transformschreiber. Der lokale Aufruf
   `3D1960` ist eine konkrete offene Anschlussstelle, keine freigegebene API.

Diese Studie ändert kein Produkt und ersetzt den entfernten Asset Browser nicht.
Sie schließt die offene Punktkonstruktion und konkrete Aufruferreihenfolgen,
während die tatsächliche Ressourcenbindung und Volumenprüfung offen bleiben.

## Belege, Neuheit und Reproduktion

13 frische vollständige IDA-Captures enthalten 3.041 Originalbytes und 729
Instruktionen. Zwei davon (`173B30`, `18B4D0`) waren bereits byteidentisch in der
Actor-Query-Studie enthalten. Weitere 18 vollständige Bodies werden ausdrücklich
aus zwei eingefrorenen Docs-Studien wiederverwendet. Insgesamt sind es 31 Bodies,
5.908 Extentbytes und 1.450 Instruktionen; 67 Bytes im Collector-Extent sind
Padding/Sprungtabellendaten und werden nicht als Instruktionen ausgegeben.
Diese Zahlen bedeuten weder 13 neue Funktionen noch vollständige Semantik.

`report.json` enthält 17 begrenzte kanonische Claims. `anchors.json` pinnt 172
ausgewählte Instruktionen einschließlich Operanden und Bytes. Der unveränderte
Coverageparser akzeptiert alle 31 Bodies und alle 57 Referenzen. Er wird nur
lesend importiert; seine Integrationsroutine wird nicht aufgerufen.

```
py -3 -B artifacts/collision-query-geometry-20261011/verify.py --check
```

Der Verifier benötigt Python 3, Capstone 5, die zwei gepinnten Docs-Studien und
die unveränderte Original-EXE am aufgezeichneten Pfad. Er prüft SHA256, PE-Extents,
alle Bytes, IDA-Seiten/Cursor, unabhängige Instruktionsdecodierung, Anker und
Referenzen. Er interpretiert 35 gezielte synthetische Fälle mit 438.101
Instruktionsschritten, darunter 22 komplette Queryfälle. Nur der Security-Cookie-
Check wird bei vollständigen Queryfällen ersetzt. Wrapperfälle nennen ihre
separaten Effektstubs ausdrücklich. Die verwendete Interpreterbasis stammt aus
einem früheren eigenen Review; dies ist kein unabhängiger Peerreview dieser
Studie. IEEE-Float32 wird mit Rundung zur nächsten Zahl und maskierten Ausnahmen,
ohne DAZ/FTZ, modelliert. NaN-Payloads, echtes MXCSR und konkurrierende Änderung
sind nicht belegt.

Die bestehende IDA-Session war gesund und inaktiv; ihre globale automatische
Analyse war nicht als vollständig bereit markiert. Es wurden keine IDB-Mutation,
neue Autoanalyse, Spielausführung oder Prozess-/GUI-/Save-/Modaktion durchgeführt.
Die zusätzlichen Discoveryexports dienen nur der Auswahl und behaupten keine
vollständige Aufrufer- oder Abhängigkeitsabdeckung.
