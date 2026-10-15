# Unabhängiger Review der Motion-Eintrittsroute

**Im beschriebenen Umfang akzeptiert; keine offenen Produktbefunde.** Geprüft
wurden der neue Router, die Runtime, ihre echten Windows-Tests und die
Registrierung im nativen Testrunner. Der bereits akzeptierte Entry-/ABI-/Unwind-
Review bleibt unverändert und wird als gepinnte Vorarbeit referenziert.

## Ergebnis

- Der Router akzeptiert im Produkt nur den vollständigen 287-Byte-Body an RVA
  `3C8CD0`, RX-Seiten eines MEM_IMAGE und die erwartete AllocationBase. Er hält
  Quell-, Wrapper- und Handlermodule fest. Die Runtime hält die Quelle bereits
  vor dem Erzeugen des Originalimages und pinnt zusätzlich die Callbackmodule.
- Der gebundene Observer und das Originalimage sind vor der atomaren Änderung
  eines Bytes bereit. Active-Pointer und VEH werden zuerst veröffentlicht.
  Der Handler ändert bei exakt passenden Breakpointdaten nur RIP.
- Der Handler prüft absichtlich weder Resident noch Patched: eine bereits
  ausgelöste Exception muss auch nach Fehler und Byte-Rollback noch routen.
  Exposed bleibt konservativ gesetzt. Fremde Bytes werden beim Rückbau nicht
  überschrieben; Rückbaufehler bleiben gesondert sichtbar.
- Es gibt keinen Produktions-Teardown. Die Runtime gibt ein gebundenes Image
  auch bei späteren Fehlern nicht frei. Vor dem Binden fehlgeschlagene Freigaben
  werden auf dem Besitzerthread erneut versucht.
- Management bleibt auf dem über einen retained Handle identifizierten Thread.
  Immutable Eintrittsdaten sind für beliebige native Caller zugänglich;
  Callbackzustand muss sein Besitzer selbst synchronisieren. `observerFault`
  bezeichnet auch einen Originalfehler und behauptet keine Fehlerherkunft.

## Tatsächlich durchgeführte Prüfungen

`run-review.cmd` baut und startet ausschließlich diese beiden Autorensuiten:

| Suite | Ergebnis | Wesentlicher Umfang |
|---|---:|---|
| MotionBreakpointRouterTests | 544 / 0 Fehler | Echtes INT3/VEH, veröffentlichter typed Wrapper, registriertes Originalpräfix, laufende Caller beim CAS, fremde Bytes/Tails, Installations-/Rückbaufehler und verzögerte echte Exception nach Rückbau |
| MotionObservationRuntimeTests | 660 / 0 Fehler | Runtime aus echten Komponenten, kompletter Originalbody, AL0/AL1, Blendzweige, Original-SEH, LastError, Besitzer-/Fremdthread und frühe Fehler |

Beide Produktionsvarianten wurden zusätzlich ohne Testdefines kompiliert.

Der eigene `RuntimeFailureReviewTests.cpp` ergänzt zwei konkrete, zuvor nur
getrennt geprüfte Integrationsfälle: RouterPrepare-Fehler nach dem Binden und
RouterCommit-Fehler mit fehlgeschlagenem Byte-Rollback. Die echte Runtime behält
das gebundene Image über Tick hinweg; AL1 und eine native Exception durchlaufen
die weiterhin installierte Route. Der erste Installationsfehler bleibt erhalten.
Ergebnis: 57 bestandene Assertions, davon 15 neu formulierte Assertions sowie
42 Assertions der ausdrücklich wiederverwendeten Originalbody-Fixture. Die
eigenen Szenarien ersetzen nicht die beiden Autorensuiten.

`check_fixture.py` liest die Original-EXE und vergleicht direkt den vollständigen
Body aus `MotionEntryPlan.h` sowie die 24 Unwindbytes aus dem Runtime-Test. Die
EXE-Identität, der zuständige PE-Runtime-Eintrag, die drei angegebenen Callee-
Stubs und zehn konkrete Branchanker stimmen. Der Body hat 86 Instruktionen.

## Umfang der ausgeführten Originalinstruktionen

Der Routertest ersetzt ausdrücklich die Fortsetzung nach dem echten
Fünf-Byte-Präfix durch eine typisierte Fixture. Die Runtime-Suite und der eigene
Integrationstest führen hingegen den unveränderten vollständigen Originalbody
aus. Nur die Ziele `40D7F0`, `3C8A40` und `40D7D0` sind erklärte Fixturefunktionen.
Die ursprünglichen Implementierungen dieser Hilfsfunktionen werden nicht
ausgeführt. Die Original-Unwinddaten sind separat im privaten Quellmodul
registriert, damit eine Exception aus dem Bindstub den echten Body abwickelt.

Bei Auswahl -1 werden beide `40D7A0`-Aufrufe übersprungen. Bindfalse führt zum
Epilog/AL0; Bindtrue ruft zusätzlich `40D7D0` auf. Dessen Fixture gibt false
zurück, wodurch EAX=-1 den Schreibpfad über Basis+0x120 überspringt. C+216=0
verhindert Kindauflösung und Rekursion. Die sichtbaren Bodywrites sind
C+328/C+344/C+352 vor Bind sowie C+44/C+48 im Erfolgspfad. `ModelBase` ist in
diesem Test ein nicht dereferenzierter Pointerwert für Adressarithmetik; er
repräsentiert keine tatsächlich geladene Spielressource.

## Grenzen und Reproduktion

Die Route beobachtet Eintritte nach ihrer Veröffentlichung. Bereits laufende
Aufrufe werden nicht nachträglich erfasst; ein ThreadDrain ist für diese Aussage
nicht nötig. Es folgen keine Aussagen über alte Writer, vollständige
Änderungshistorie, Ressourcenleases, Scale oder Tiny/Giant. Es gibt noch keinen
Aufruf dieser Runtime aus `TrainerBridge`.

Der atomare Byte-CAS macht keine vollständige Funktionstransaktion. Gleichzeitige
fremde Codeänderungen und Unmapping sind außerhalb des dokumentierten Vertrags.
Die erreichbaren Ownerobjekte, Callbackkontexte, Originalimages und Handler
müssen nach Veröffentlichung für die Prozesslebensdauer bestehen bleiben.
Modulpins ersetzen keine Lease für beliebige Heapobjekte.

```
py -3 -B artifacts/review-motion-route-20261011/check_fixture.py
artifacts\review-motion-route-20261011\run-review.cmd
```

Der Reviewer hat nur diesen Reviewordner beschrieben und private Testprozesse
ausgeführt. Kein Spiel-, GUI-, Attach-, Injection-, IDB-, Save- oder Modzugriff
fand statt. Die erzeugten EXE-/OBJ-Dateien wurden nach der Hashaufzeichnung in
`build-products.json` entfernt. Logs und Quellen sind im Manifest enthalten.
