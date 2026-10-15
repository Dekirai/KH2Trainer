# Motion-Eintritt: erster nativer Implementierungsbaustein

## Ergebnis und Einsatzgrenze

Der normale Motionwechsel bei RVA `3C8CD0` besitzt jetzt einen eigenen
Eintrittsplan, einen typisierten Wrapper und eine verwaltete Original-Aufrufadresse
mit Windows-Unwindregistrierung. Die Implementierung liegt in drei neuen
Headern unter `src/KH2Trainer.Bridge`; drei isolierte Testsuiten sind im normalen
nativen Testrunner registriert.

Damit ist die in der vorherigen Runde konkret benannte ABI-/Trampolinlücke
geschlossen. Die Bausteine sind noch nicht in `TrainerBridge.cpp` installiert.
Es gibt weiterhin keine neue Tiny-/Giant-Bedienung und keinen aktiven
Größeneingriff. Die ausgelieferte EXE bleibt v0.12.18.

## Originalcode und Aufrufvertrag

Der vollständige Originalkörper umfasst 287 Bytes und 86 Instruktionen.
`RCX` übergibt den Controller, `EDX` die vorzeichenbehaftete Auswahl und
`XMM2`/`XMM3` die beiden Floatargumente; das Ergebnis steht in `AL`.
Der Wrapper verwendet dafür `uint8_t(uintptr_t, int32_t, float, float)`.
Die Float-Bitmuster werden ohne arithmetische Umrechnung weitergereicht.

Die ersten fünf Bytes sind `MOV [RSP+8], RBX`. Dieser vollständige Befehl
wird kopiert, bevor ein absoluter Sprung die Originalfunktion bei `3C8CD5`
fortsetzt. Der gesamte Originalkörper verwendet R11 nicht; der Trampolinsprung
darf es unter dem geprüften Win64-Vertrag als flüchtiges Register verwenden.

Für den kopierten Anfang werden eigene Unwinddaten erzeugt. Die originale
Exception-Tabelle beschreibt auch spätere Stack- und Registeränderungen und
darf dafür nicht unverändert übernommen werden. Windows-Tests prüfen sowohl
die ursprünglichen Prologgrenzen als auch den erzeugten kurzen Anfang.

Der erste native Kontextstore liegt bei `3C8D0D`. Ein Eintritts-Wrapper kann
seine Before-Benachrichtigung davor ausführen. Eine Installation erst nach
Rückkehr wäre weiterhin zu spät. Die vorgeschlagenen Patchbytes werden vom
Planer nur berechnet; die jetzige Implementierung schreibt sie nicht ins Spiel.

## Drei konkrete Bausteine

- **MotionEntryPlan.h:** vollständiger Originalfingerprint, kopierte
  Instruktionsgrenze, Fortsetzung, Patchplan und passende Unwinddaten.
- **MotionObserverSupport.h:** einmalige typisierte Bindung, synchrone
  Before-/After-Benachrichtigung, aufruflokale Tickets und dauerhafter Fehlerstatus.
  Verschachtelte Aufrufe besitzen getrennte Tickets.
- **MotionOriginalTrampoline.h:** private RX-Allokation, Cacheflush,
  Windows-Funktionstabelle und typisierte Originaladresse. Nach Veröffentlichung
  bleiben Code und Unwinddaten für die Prozesslebensdauer bestehen.

Der Besitzer muss die unveränderte Originalfortsetzung, das Observerobjekt und
seine Callbackdaten für alle möglichen Aufrufe erhalten. Eine fehlgeschlagene
Freigabe der Windows-Tabelle darf keinen frei gewordenen Speicher hinterlassen,
auf den die Tabelle noch zeigt. Fehlgeschlagene Bereinigung vor Veröffentlichung
kann daher mit derselben Allokation wiederholt werden.

## Ausnahmen und verschachtelte Aufrufe

Before, Original und After können erneut denselben Wrapper aufrufen. Deshalb
darf ein allgemeiner Exception-Handler um einen Callback dessen Fehler nicht
pauschal unterdrücken: Er würde auch eine native Ausnahme aus einem darin
verschachtelten Originalaufruf abfangen.

- Scheitert Before, wird das Original nicht aufgerufen. After erhält
  `beforeCompleted=false` und `normalReturn=false`; die erste Ausnahme bleibt erhalten.
- Scheitert das Original, erhält After `beforeCompleted=true` und
  `normalReturn=false`; die native Ausnahme bleibt erhalten.
- Kehrt das Original normal zurück, erhält After beide Flags als `true`.
  Eine anschließend von After ausgelöste Ausnahme wird weitergereicht.
- Läuft bereits die Abwicklung einer ersten Ausnahme, wird eine zweite
  Ausnahme aus After abgefangen, damit sie die erste nicht ersetzt.

After wird je gebundenem Aufruf genau einmal versucht. Jeder dieser Fehler setzt
den dauerhaften Fehlerstatus. `beforeCompleted` bestätigt nur die Rückkehr des
Callbacks; ein künftiger Besitzer muss einen erfolgreichen Ressourcenwiderruf
gesondert prüfen. Die Prüfung umfasst direkte Callbackfehler und native Fehler
aus einem verschachtelten Aufruf in Before beziehungsweise After.

Bei normaler Rückkehr erhält das Original den ursprünglichen LastError-Wert;
ein erfolgreicher After-Callback verändert den vom Original hinterlassenen Wert
für den Aufrufer nicht. Bei einer weitergereichten Ausnahme bleibt der dazugehörige
LastError-Wert erhalten, auch wenn After während der Abwicklung selbst scheitert.

## Prüfungen

Die genauen Ergebnisse, Quellhashes und Logs stehen in
[validation.json](validation.json), der unabhängige Review unter `review/`.

| Isolierte Suite | Prüfungen | Fehler |
| --- | ---: | ---: |
| MotionEntryPlanTests | 1.842 | 0 |
| MotionObserverTests | 691 | 0 |
| MotionOriginalTrampolineTests | 119 | 0 |

Der unabhängige Review baut die betroffenen Suiten erneut und prüft zusätzlich
Originalbytes, Windows-Unwindverhalten sowie sechs Fälle der Ausnahmebehandlung.
Die Produktionsvariante der neuen Header wird auch ohne Testhilfen kompiliert.

Die Tests decken unter anderem ab:

- Originalfingerprint, Größen-/Adressgrenzen und unveränderte Ausgabe bei Fehlern;
- echte Windows-Unwindabfragen und eine Gegenprobe mit ungeeigneten Unwinddaten;
- Integerargumente, verschiedene Float-Bitmuster und sämtliche AL-Bits;
- verschachtelte Aufrufe aus Before, Original und After;
- LastError, primäre Ausnahmen und Fehler in nachgelagerten Callbacks;
- Veröffentlichung, Registrierungsfehler und wiederholbare Bereinigung.

Ein Integrationstest führt das echte kopierte Fünf-Byte-Präfix und das erzeugte
Trampolin ausschließlich im privaten Testprozess aus. Nach der Fingerprintprüfung
wird nur in dessen künstlichem Modul die Fortsetzung durch eine Testfunktion
ersetzt. Es laufen weder der vollständige native Motionkörper noch Spielglobals.
Dieser Test belegt die zusammengesetzte Aufrufroute unter diesen Voraussetzungen.

## Weiter zur Größenfunktion

Als Nächstes benötigt die Bridge die tatsächlich installierte Eintrittsroute,
Module-/Callbacklebensdauer und eine belegte Beobachtungsphase auf dem zulässigen
Thread. Danach müssen die bereits benannten normalen, geliehenen, Cleanup-,
Bank- und Cachewechsel denselben Widerrufsvertrag erfüllen. Der einzelne
Normalpfad beweist keine vollständige Ereignisabdeckung.

Die native Payloadkopie soll den beobachteten Cache-Reservierungsumfang mit den
verschachtelten BAR-Eintragsgrenzen verbinden und die bestehende Core-Auswertung
nutzen. Erst der gemeinsame Ressourcen-, Kontext- und Körpercachevertrag erlaubt
eine Scale-Transaktion. Das sind konkrete verbleibende Implementierungsarbeiten.

Der Asset Browser bleibt entfernt. In dieser Runde gab es keinen Spielstart,
Attach, GUI-Eingriff, Save-/Mod-Schreibzugriff oder Twitch-Aufruf.
