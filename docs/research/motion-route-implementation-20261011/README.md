# Motion-Eintritt: ausführbare Route und gemeinsamer Lebenszyklus

## Ergebnis

Der zuvor geprüfte Motion-Wrapper hat jetzt eine ausführbare Eintrittsroute.
`MotionBreakpointRouter.h` setzt am normalen Eintritt `3C8CD0` atomar ein
INT3-Byte. Der Windows-Exception-Handler leitet diesen Eintritt an den typisierten
Wrapper weiter. `MotionObservationRuntime.h` verbindet die Route mit dem
Originaltrampolin, dessen Unwindregistrierung und den Before-/After-Callbacks.

Beide Komponenten liegen im Produktquellbaum und im normalen nativen Testrunner.
Sie sind noch nicht in `TrainerBridge.cpp` aufgerufen: Die Ressourcenbeobachtung
und die weiteren Kontextwechsel müssen erst gemeinsam umgesetzt werden. Die
ausgelieferte EXE bleibt v0.12.18; Tiny/Giant ist damit noch keine verfügbare
Spielfunktion.

## Veröffentlichung und Lebensdauer

Vor dem ersten veränderten Codebyte sind die Originaladresse und die Callbackbindung
unveränderlich gesetzt. Der Router prüft den vollständigen 287-Byte-Funktionskörper,
die ausführbaren Speicherseiten und deren Modulzuordnung. Quell-, Wrapper-,
Callback- und Handlercode bleiben durch Modul-Pins geladen. Der Besitzer muss
zusätzlich den Callbackkontext und die übrigen veröffentlichten Daten erhalten.

Der Handler wird vor dem Byte-CAS registriert. Er verändert ausschließlich RIP,
wenn Exceptioncode, Flags, Exceptionadresse und RIP zum eigenen Eintritt passen.
Die normale Enginefunktion läuft über den kopierten Anfang und ihre unveränderte
Fortsetzung weiter.

Ein Fehler nach dem CAS löst einen begrenzten Rückbauversuch aus. Das setzt
ausschließlich das eigene INT3-Byte zurück; ein fremder Wert wird nicht überschrieben.
Der Handler und die Originaladresse bleiben trotzdem erhalten. Eine bereits
ausgelöste Exception kann erst nach dem Rückbau beim Handler eintreffen.
Ein Fehlerstatus oder eine momentan leere Aufrufzählung wäre deshalb kein
Nachweis, dass diese Daten freigegeben werden dürfen.

Die Runtime lässt Verwaltungszugriffe nur auf dem zuvor angegebenen, über ein
Threadhandle festgehaltenen Besitzerthread zu. Die nativen Callbacks können auf
anderen Threads eintreffen. Sie müssen ihre eigenen Daten synchronisieren;
die Runtime behauptet keine Freigabe für Enginezugriffe auf diesen Threads.

## Geprüfte tatsächliche Aufrufkette

Der Integrationstest ruft den privaten nativen Eintritt auf:

```text
INT3 → Windows-Handler → typisierter Wrapper → Before
     → Originaltrampolin → unveränderter Originalkörper → After
```

Der vollständige Originalkörper bleibt im privaten Testmodul erhalten.
Lediglich drei direkte Callees werden durch ausdrücklich benannte Testfunktionen
ersetzt: `40D7F0`, `3C8A40` und `40D7D0`. Die originale vollständige
Unwindbeschreibung von `6E6434` wird für den privaten Körper registriert.
Die Testauswahl ist `-1`, die Gruppenadresse und die Kindliste sind leer.
Die synthetische Modelladresse wird auf diesen Pfaden nur arithmetisch verwendet.

Damit werden die tatsächlichen Kontextstores vor `3C8A40`, beide AL-Rückgaben,
der native Blendzweig und die Ausnahmeabwicklung durch den Originalprolog
ausgeführt. Es läuft kein vollständiger Ressourcenbinder: Seine Wirkung wird
durch den benannten Callee ersetzt. Daraus folgt keine Aussage über beliebige
Animationen, Kindlisten oder echte Spielressourcen.

## Prüfungen

- Router-Suite: **544 Prüfungen, 0 Fehler**. Reale INT3-Weiterleitung,
  konkurrierende Aufrufe während der Installation, Seitenschutz, Fehler nach CAS,
  Rückbaufehler und eine tatsächlich verzögerte Exception nach erfolgreichem Rückbau.
- Runtime-Suite: **660 Prüfungen, 0 Fehler**. Zusammengesetzte echte Route,
  unveränderte Fortsetzung, deklarierte native Zweige, Float-Bitmuster, LastError,
  Original-SEH, Besitzerthread und Aufrufe von einem anderen Thread.
- Beide Produktionsvarianten werden ohne die privaten Testfreigaben kompiliert.
- Der unabhängige Review prüft zusätzlich Fehler nach der Originalbindung und
  die Weiterleitung nach einem fehlgeschlagenen Rückbau.

Quellstände, genaue Ergebnisse und Protokolle stehen in
[validation.json](validation.json); die unabhängigen Belege unter `review/`.

## Verbleibende Integration

Die Route beobachtet neue Eintritte. Aufrufe, die bei der Installation bereits
im Originalkörper waren, bleiben unbeobachtet. Die atomare Byteänderung macht
auch keine fremden gleichzeitigen Änderungen am restlichen Funktionskörper sicher.
Die unveränderte Originalfortsetzung ist eine ausdrückliche Voraussetzung.

Als Nächstes sind die konkreten Callbackdaten und die übrigen normalen, geliehenen,
Cleanup-, Bank- und Cachewechsel zu verbinden. Vor einer Ressourcenkopie muss
deren gültiger Umfang aus beobachteter Reservierung und BAR-Eintragsgrenzen
feststehen. Erst danach kann eine Größenänderung dieselben Widerrufsregeln nutzen.

Der Asset Browser bleibt entfernt. Diese Runde enthält keine Installation im
laufenden Spiel, keinen GUI-Test und keinen Save-, Mod- oder Twitch-Schreibzugriff.
