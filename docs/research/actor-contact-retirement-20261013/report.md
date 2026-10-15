# Actor-Kontaktzähler und verzögerte Freigabe

## Ergebnis

Für den untersuchten ursprünglichen Descriptorpfad gibt es eine konkrete Zulassung vor der späteren Actorfreigabe: **Der Actor-Update prüft den Zähler bei +1464, bevor er den Actor für die Dead-List markiert.** Auf diesem Zulassungspfad findet der Test bereits im Update statt; der früher untersuchte Destruktor `3D2720` enthält keinen lokalen Countertest. Das ist ein belegter Teilpfad, keine Garantie für sämtliche direkten, abgeleiteten oder Bulk-Freigaben.

Die Attack-Markierung `0x800` hat ebenfalls einen konkreten Verbraucher. Der registrierte Kontakt-Update `3CFF40` ruft für markierte Einträge den virtuellen Destruktor mit Löschflag1 auf. Damit erreicht der ursprüngliche `ATTACK_OBJ`-Typ den bereits belegten Pfad, der seine äußere Ownerzelle leert und die zwei Actorreferenzzähler dekrementiert.

## Belegte Reihenfolge

1. `3D2850`, Slot+56 der untersuchten Tabelle, ruft `3D24B0(actor+3088)` auf, solange Actor-Flag `0x10000000` noch nicht gesetzt ist. Der Manager ruft für belegte seiner acht Zellen die Markierungsfunktion auf und leert die Zellen. Die Markierungsfunktion `3D0EB0` setzt `0x800` nur bei aktivem Kontaktlisten-Byte und einem in der globalen Kontaktliste gefundenen Objekt; sie kann ohne Markierung zurückkehren. Danach ruft `3D2850` den Helper `3B4700(actor)` auf. Dieser setzt `0x10000000` nach vorbereitender VM-/Motionarbeit.
2. `3BFD30` prüft dieses Flag. Bei gesetztem Flag ruft es Descriptor-Slot+64 auf. Nur wenn der Rückgabewert wahr ist, ruft es Slot+72 auf.
3. Für die Originaltabelle `5C6250` lautet Slot+64 `3D28B0`, ein Zwei-Instruktionsadapter zu `3DAC30(actor)`. `3DAC30` verlangt zuerst Erfolg von `3B4420(actor)`. Letzterer gibt genau dann wahr zurück, wenn DWORD `actor+1464 == 0` ist. Wenn beide Bindungen bei +128 und +152 nicht null sind, verweigert `3DAC30` die Zulassung ebenfalls. Eine noch aktive Voice kann sie zusätzlich verzögern.
4. Slot+72 lautet `3D28C0`, ein Zwei-Instruktionsadapter zu `3B45C0(actor)`. Nach seinen Bereinigungen löscht diese Routine `0x10000000` und setzt `0x80000` in Actor-DWORD+288. Sie prüft den Zähler nicht erneut. Der verwandte Basisadapter `3B2ED0` enthält dieselbe lokale Folge mit Actor in seinem zweiten Argument.
5. `3BF300` zerstört zunächst die bereits vorhandene Dead-List über Descriptor-Slot0. Erst danach verschiebt es mit `0x80000` markierte Actors aus der aktiven Liste auf die neue Dead-List. Ein auf diesem Weg gerade verschobener Actor wird daher erst bei einem späteren Aufruf dieses Verbrauchers zerstört. Das ist keine feste Zeit- oder Framegarantie.
6. Für einen Actor mit aktuellem Descriptor `74C380 → 5C6250` führt Slot0 zu `3D2720`. Der Basis-Konstruktor `3D2DA0` schreibt diesen Descriptor nach dem Initialisieren des eingebetteten Managers. Abgeleitete Konstruktoren können ihn danach ersetzen; ihre endgültigen Tabellen werden hier nicht allgemein gleichgesetzt.

Die originalen Tabellen `5C5EF0`, `5C60A0` und `5C6250` enthalten dieselben hier betrachteten Slots0/+56/+64/+72. Nur für `74C380 → 5C6250` wird hier zusätzlich eine konkrete Descriptorzelle und deren Konstruktorstore verbunden. Statische Vtablegleichheit ersetzt keinen Nachweis des aktuellen Objekttyps.

## Was markierte Angriffe tatsächlich zerstört

`3D0110` setzt die globale Kontaktliste zurück und registriert `3CFF40` mit `1506B0(1,21000,callback)`. Der Forwarder verwendet den Feld-Taskmanager aus `716868`; der erneut geprüfte `14F770` speichert Callback, Flags und Priorität in einem Task und fügt ihn nach aufsteigender Priorität ein. Sein Kontextzeiger+112 ist null. Der erneut geprüfte Scheduler `14FD60` ruft Tasks mit null Kontext direkt auf; Tasks mit Kontext benutzen einen getrennten Fiberpfad.

`3BF810` registriert im selben Feld-Taskmanager `3BF550` mit Priorität 20000 und den Dead-List-Verbraucher `3BF300` mit Priorität 91000. Damit liegt der Kontakt-Task mit Priorität 21000 vor dem Dead-List-Task mit Priorität 91000, wenn beide im gewöhnlichen passenden Scheduler-Durchlauf vorhanden und unverändert sind. Die vollständige Brücke von `3BF550` zum separat angelegten Actor-Taskmanager wird hier nicht behauptet: Die Registrierung seines Tasks `3BF5E0` mit Priorität 5 ist erfasst, dessen Aufrufumgebung nicht vollständig geschlossen. Die numerischen Prioritäten sind daher keine allgemeine Frame- oder Wartezeitgarantie.

Beim Dead-List-Task trägt `3BF810` außerdem `3BF4C0` in Task+104 als Cleanupcallback ein. Dieser ruft `3BF300` zweimal hintereinander auf (Call und Tailcall). Dadurch können im ersten Durchlauf auf die Dead-List verschobene Actors bereits im zweiten Durchlauf desselben Callbacks zerstört werden. „Späterer Aufruf“ bedeutet deshalb nicht zwingend „späterer Frame“. Die genaue Schedulerbedingung, die den Cleanupcallback auslöst, ist hier nicht vollständig verfolgt.

Im Kontakt-Update wird der nächste Packed-Link+196 vor dem Aufruf gespeichert. Für Objekt-DWORD+8 mit `0x800` folgt `virtual0(object,1)`, sonst `virtual+24(object,scratch)`. Bei der ursprünglichen `ATTACK_OBJ`-Vtable führt der erste Pfad zu `40F4C0`:

- Die gespeicherte äußere Zelle hinter Objekt-QWORD+720 wird auf null gesetzt.
- `3CFB10` dekrementiert DWORD+1464 für die nichtnull dekodierten Felder Objekt+12 und Objekt+20 und entfernt das Objekt aus seinen Listen.
- Der löschende Wrapper gibt anschließend die Allocation frei.

Aliasing der beiden Actorreferenzen bedeutet weiterhin zwei lokale Dekremente. Die Arithmetik ist ungesättigte DWORD-Arithmetik. Die zuvor festgestellte Markierung allein war kein Destruktor; dieser Verbraucher ist das fehlende konkrete Bindeglied.

`3CFED0` ist ein anderer Pfad: Er zerstört alle Einträge der globalen Kontaktliste über virtual0 mit Löschflag1, ohne `0x800` vorauszusetzen, und deaktiviert anschließend das Kontaktlisten-Byte. Seine zwei aufgezeichneten direkten Caller sind `39C830` und `3BF8F0`. Deren vollständige transitive Freigabeabfolge ist nicht Teil dieser Studie.

## Späterer Austausch des Callbackempfängers

Die frühere Untersuchung belegte zunächst nur die Konstruktorherkunft von Objekt+16. Jetzt ist ein konkreter späterer Writer erfasst: `3D06E0(old,new)` läuft durch die globale Kontaktliste und ersetzt genau die +16-Verweise, deren dekodierter Wert `old` entspricht. Diese Routine ändert weder +12/+20 noch Actor+1464.

Der erneut geprüfte Drive-Pfad `40D000` ruft diesen Helper bei `40D448` mit altem und neu konstruiertem Actor auf. Das geschieht vor seinem Warten auf die Entfernung des alten Actors aus der aktiven Liste. Somit ist +16 nicht nur ein Konstruktorwert und kann bei diesem Austausch auf den neuen Callbackempfänger zeigen, während die separat gezählten Felder weiterhin ihre bisherige Herkunft haben. Die Laufzeitgültigkeit beliebiger anderer Verweise folgt daraus nicht.

## Grenzen und sinnvolle Nutzung

- Die Counterprädikate `3B4420` und `3B2E90` sind keine reinen Abfragen: Sie führen bei vorhandenem Actor+1456 zuerst `YSVM_UpdateTree(...,0)` und gegebenenfalls `3CA550` aus. Eine Diagnoseanzeige sollte den Zähler lesen und nicht diese Routinen als Getter aufrufen.
- Die hier verbundene Zulassung betrifft den normalen Descriptor-Updatepfad. Direkte Aufrufe von `3B45C0`, bereits gesetzte Dead-List-Flags, andere Descriptoren, Taskabbrüche und ganze Heap-/Ressourcenfreigaben benötigen eigene Belege. Der Dead-List-Verbraucher prüft den Zähler nicht nochmals.
- Die Reihenfolge erklärt den beobachteten normalen Aufschub. Sie beweist weder einen universellen Referenzzähler noch atomare Konkurrenzsicherheit oder den Ausschluss aller späteren Zählerwriter.
- Der Manager darf seine Zellen bereits beim Anfordern der Beendigung leeren, während der umgebende Actor auf Zulassung wartet. Der spätere Attack-Destruktor leert seine gespeicherte Zelle erneut. Eine allgemeine Identitätsgarantie für inzwischen wiederverwendete Managerzellen wird damit nicht eingeführt.
- Es wurde kein Use-after-free im normalen Spiel bewiesen. Ebenso wurde keine neue rohe Free-/Delete-Funktion für den Trainer freigegeben.

Die Ergebnisse eignen sich für eine spätere Diagnose der verzögerten Actorfreigabe: Anzahl gezählter Referenzen, markierte Kontakte und aktuelle Beendigungsphase lassen sich getrennt darstellen. Eine gezielte Attack-Abbruchfunktion müsste den nativen Markierungs-/Verbraucherpfad respektieren und zusätzlich die konkrete Owner-/Taskidentität prüfen.

## Nachweis und Reproduktion

`evidence.json` enthält die vollständigen Originalbytes und unabhängig mit Capstone dekodierten Instruktionen der ausgewählten Körper: **14 frisch erfasste Körper mit 433 Instruktionen und 1828 Bytes** sowie **16 ausdrücklich wiederverwendete Abhängigkeiten mit 1086 Instruktionen und 4331 Bytes**. Insgesamt sind das 30 Körper, 1519 Instruktionen und 6159 Körperbytes. Alle Bytes sind Instruktionsbytes; es gibt in diesen ausgewählten Körpern keine separat gezählten Nichtinstruktionsbytes. Die vollständigen Funktionsgrößen werden mit dem bestehenden Inventar verglichen. `original-tables.json` enthält zusätzlich 360 direkt aus der Original-EXE gelesene Datenbytes für vier Tabellen und eine Descriptorzelle. „Frisch erfasst“ bezeichnet die Herkunft dieser Aufnahme und ist keine Behauptung, dass sämtliche Funktionen erstmals entdeckt wurden.

Die begrenzte Literal-Suche nach `5B8h` im Bereich `3A0000..3E0000` lieferte 14 Treffer; der Treffer mit Offset `C5B8h` wird verworfen. Die beiden konkreten CMP-Stellen `3B2EBC` und `3B444C` liegen in vollständig geprüften Körpern. Diese Suche ist weder ein binärweites Verzeichnis aller Writer noch ein Nachweis über berechnete Aliase. Explorative Decompiles weiterer Funktionen zählen nicht zu den 30 geprüften Körpern.

Root lieferte die frischen Aufnahmen aus der bereits vorhandenen IDA-Sitzung `9d62332c`, weil diese Sitzung in der separaten Reviewer-Sicht nicht auffindbar war. Es wurde kein zweiter Worker gestartet. Vollständige Einzelabfragen und Originalbytes belegen diese Körper; eine abgeschlossene globale Autoanalyse wird nicht behauptet.

```powershell
py -3 -B docs/research/actor-contact-retirement-20261013/verify.py --check
```

Die ursprüngliche Studie schrieb nur Artefakte. Diese Übernahme ergänzt die Forschungsdokumentation; Produkt, Releasepaket, Spiel, GUI, Injection, Saves und Twitch bleiben unverändert.

## Dokumentationsübernahme und Belegarchiv

Die sechs zusammenhängenden Ergebnisse des unveränderten Originalberichts sind in `report.json` als 24 begrenzte Funktionsbefunde mit auflösbaren Referenzen erfasst. Sechs weitere Körper bleiben reine Belege. Die 30 Körper sind keine Behauptung von 30 neu verstandenen Funktionen; die globale Abdeckung dedupliziert die konkreten Funktionsadressen gegen den bisherigen Bestand. Vollständige Semantik ist nicht behauptet.

`evidence.zip` bewahrt alle 49 Dateien der eingefrorenen Studie unter `study/` und alle vier Dateien der unabhängigen Prüfung unter `review/`, jeweils bytegenau einschließlich der Manifeste. `provenance.json` enthält die Hashbelege jedes Archivmitglieds und beider eingefrorener Manifeste. Der unveränderte Originalbericht und die ursprünglichen Prüfskripte bleiben dort erhalten.

`evidence.json` stellt dieselben 30 vollständigen Instruktionslisten im gemeinsamen Dokumentationsschema dar. Die normalisierte Seite pro Funktion ist keine neue IDA-Abfrage. Originalbytes sind lediglich mit Leerzeichen formatiert. Die fünf Datenbereiche umfassen weiterhin 360 Bytes. Die vorher belegte ATTACK_OBJ-Tabelle 0x1405CE6C0 bleibt eine explizite Abhängigkeit und wird diesen 360 Bytes nicht hinzugerechnet.

Der lokale Prüflauf kontrolliert Archivhashes, Ursprungsmanifeste, Abhängigkeiten, Original-PE-Bytes und Instruktionsgrenzen sowie die Normalisierung. Er führt weder Spielcode noch eine semantische VM aus. Die semantischen Aussagen beruhen auf der begrenzten manuellen Prüfung in der archivierten Studie und dem unabhängigen Review.
