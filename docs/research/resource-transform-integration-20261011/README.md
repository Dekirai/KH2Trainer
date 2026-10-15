# Ressourcen, Größenänderung und Kollisionsgeometrie

## Neue Ergebnisse

Diese Runde führt die Analyse nach v0.12.18 fort. Vier Studien schließen konkrete
Lücken für weitere Mod-Funktionen. Der aktuelle Trainer enthält diese neuen
Laufzeiteingriffe noch nicht; die fertige EXE bleibt v0.12.18. Der Asset Browser
bleibt entfernt.

### Körpergrenzen: überraschendes Verhalten im Originalcode

Der Helfer `40AC20` verwendet bei mehreren Körpern sowohl für Untergrenzen als
auch für Obergrenzen `MINSS`. Zwei Körper mit Radius 1 bei X=0 und X=100 ergeben
dadurch X=−1 bis 1. Eine umschließende Box müsste bis 101 reichen. Drei unveränderte
Originalfunktionen wurden dafür in einem privaten Testprozess mit künstlichen
Daten ausgeführt; ein unabhängiger Review bestätigte die ausgewählten Ergebnisse.

Das belegt das Verhalten dieses Helfers. Die tatsächlich betroffenen Szenen sind
noch offen: Der Modellpfad in `3CBFE0` verwendet eine andere Berechnung. Ein
optionaler Fix wäre denkbar, sobald die nachfolgenden Nutzer und betroffenen
Ressourcenfälle geklärt sind.

Auch die Reihenfolge ist jetzt genauer belegt. `3CCB90` baut den Körperpuffer
Actor+2560 schon vor seiner Rückkehr auf. Ein nachträgliches Skalieren fertiger
Matrizen käme dafür zu spät. Ressourcenradien und -höhen werden in `3C9C00`
unverändert übernommen; veränderte Mittelpunkte bedeuten keine vollständig
mitskalierte Kollision.

[Studie und native Probe](../actor-body-bounds-20261011/report.md)

### Motiondaten: ein begrenzter Weg zur nativen Anbindung

Die Motionbindung ist bis zum Ressourcen-Cache verfolgt. Ein belegter
Reservierungsumfang bei Cache+80 kann die äußere Speichergrenze liefern. Die
Länge des tatsächlich ausgewählten Type-9-BAR-Eintrags liefert zusätzlich die
innere Grenze. Für den untersuchten normalen Payloadpfad muss außerdem
`Motion+8 == Motion+144` gelten. Der vorhandene Coreparser kann anschließend
eine begrenzte Kopie auswerten.

Pointergleichheit genügt nicht: Der Cache kann Unterbereiche als eigene Knoten
veröffentlichen, Speicher umziehen und Deskriptoren wiederverwenden. Die Studie
benennt deshalb konkrete Ereignisse, vor denen die Trainerbindung ungültig
werden muss. Bei `3C8CD0` erfolgen Kontextstores bereits vor `3C8A40`; letzteres
verwendet die neue Motion ebenfalls noch vor seiner Rückkehr.

Der nächste Implementierungsschritt ist konkret: ein typisierter Eintritts-
Wrapper für `3C8CD0` mit synchroner Benachrichtigung vor dem Original. Die
Argument-ABI ist bekannt. Die passenden kopierten Originalinstruktionen,
Fortsetzungsadresse und Unwinddaten müssen als eigene Motiondefinition geprüft
werden. Danach folgt die begrenzte Payloadkopie samt beobachteter Reservierung.

[Motionstudie](../motion-resource-binding-20261011/report.md) ·
[Konkrete Quellanschlüsse](scale-next-implementation.md)

### Stitch: Aufruf des nativen Größenresets gefunden

Der zuvor offene Dispatch ist jetzt belegt: BDX **10:4** führt über `5364B0` und
die Personality bei Actor+3576 zum virtuellen Slot+80. Bei der originalen
Stitch-Vtable ist das `1C7E00`. Diese Funktion schreibt den Größenwert des
zwischengespeicherten Actors bedingungslos auf 1.0, auch wenn er schon 1.0 ist.
Ein bloßer Vergleich des Zahlenwerts erkennt daher nicht jede native Übernahme.

BDX **10:3** führt zum Setup; **7:26** erreicht einen gespeicherten Callback.
Die Initialisierung seiner Aktionstabelle und tatsächlich verwendende
Spielscripts bleiben offen. Diese Befunde erlauben noch keinen beliebigen
Aufruf der gefundenen Aktionen. Sie geben konkrete Ansatzpunkte, damit ein
künftiger Größen-Mod mit dem nativen Reset zusammenarbeitet.

[Stitch-Dispatchstudie](../stitch-scale-dispatch-20261011/report.md)

### Kollisionsabfrage: kein Treffer beweist keine freie Strecke

`173B30` prüft ein gerichtetes Segment. Der Collector nimmt höchstens **1.023
Kandidaten** auf. Ein vollständiges Instruktionsmodell mit 1.024 akzeptierten
Polygonen verfehlt das einzige schneidende Polygon am Ende der Liste. Dasselbe
Polygon trifft, wenn es allein abgefragt wird.

Die Studie klärt außerdem Richtung, Endpunkte, nächstgelegenen Treffer,
Matrixannahmen und Rückgabemarker. Bei gleicher Entfernung kann der statische
Treffer einen zuvor ermittelten beweglichen Treffer ersetzen. Einige Wrapper
lassen bei Fehlschlag alte oder ersatzweise plausible Koordinaten stehen; der
Rückgabewert muss ausgewertet werden.

Für eine spätere Teleportation oder Platzierung fehlen weiterhin die Bindung
der Geometriedaten, eine Prüfung des benötigten Körpervolumens und der finale
Bewegungsschreiber. `1752E0` und `3D1960` sind konkrete nächste Ansatzstellen.
Die Modelle mit künstlichen Daten belegen keine Fehler in einer bestimmten
Spielsituation.

[Kollisionsstudie](../collision-query-geometry-20261011/report.md)

## Nachweise und Stand

Alle vier Studien enthalten vollständige lokale IDA-Funktionsansichten und
Vergleiche mit der unveränderten Original-EXE. Wiederholt erfasste Funktionen
werden nicht als neu verstandene Funktionen gezählt. Die globale semantische
Vollständigkeit bleibt unbewiesen; auch IDAs globale Analyse meldet weiterhin
`auto_analysis_ready=false`.

Die unabhängigen Reviews sind mit ihren Quellen in `reviews/` gesichert.
[integration.json](integration.json) pinnt Studien, Reviews und die
Quellstandprüfung. Der globale Coverage-Bericht wird nach diesem Freeze separat
reproduzierbar erzeugt; seine Hashes stehen im externen Fortschrittscheckpoint,
damit keine gegenseitige Hashabhängigkeit entsteht.

In dieser Runde gab es keinen Spielstart, Attach, Live-Hook, GUI-Eingriff,
Spielstand-/Mod-Schreibzugriff oder Twitch-Aufruf. Die native Körperprobe läuft
ausschließlich in privatem Speicher. Produktquellen und das ausgelieferte Paket
werden gegen den Stand von v0.12.18 geprüft. Eine neue EXE ist für diese
Dokumentationsrunde nicht erforderlich.
