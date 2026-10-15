# Unabhängiger Motion-Entry-Review

**Im dokumentierten Umfang akzeptiert. Keine offenen Befunde.** Der zunächst reproduzierte Fehler bei verschachtelten Callback-Ausnahmen wurde korrigiert und gezielt erneut geprüft. Die Header installieren keinen Hook und geben keine Spiel- oder Ressourcenfunktion frei.

## Originalbytes, ABI und Windows-Unwind

Der lesende Originalabgleich bestätigt für `3C8CD0`:

- 287 Originalbytes, 86 Instruktionen, Runtime-Bereich `[3C8CD0,3C8DEF)`.
- Original-Unwinddaten bei RVA `6E6434`, Prologlänge 34 Bytes, sechs Operationen in zehn Unwindslots. Details und Rohbytes stehen in `original.json`.
- Kopierbarer Einstieg: fünf Bytes `48 89 5C 24 08`, also `MOV [RSP+8], RBX`. RSP bleibt unverändert. Fortsetzung: `3C8CD5`.
- Eigenes Präfix-Unwind: `01 05 02 00 05 34 01 00`. Der gespeicherte RBX liegt bei RSP+8. Der vollständige Originalprolog benötigt dagegen RSP+80. Seine Metadaten können deshalb nicht unverändert für das Präfix übernommen werden.
- R11 wird im vollständigen lokalen Body weder gelesen noch geschrieben. Der absolute Sprung über das nach Win64 volatile R11 passt dazu. Beliebige verdeckte Registerkonventionen anderer Funktionen sind damit nicht geprüft.
- Argumente: RCX=Kontext, EDX=signierte Auswahl, XMM2/XMM3=Float32. Das Ergebnis liegt in AL. Die oberen RAX-Bits sind kein definierter Rückgabepointer.
- Der erste direkte Kontextstore bei `3C8D0D` schreibt C+328 aus C+16 plus 128. Davor liegt bereits der Aufruf `40D7F0`. Die rekursive Bindung ruft wieder `3C8CD0` auf; Aufruflokalität ist deshalb Teil des Wrappervertrags.

`check_original.py` gleicht die eingefrorene IDA-Forschung mit der Original-EXE ab. `fixture.h` stammt aus dieser unabhängigen Extraktion. Das eigene `UnwindReviewTests.cpp` führt **keine Originalinstruktion** aus: Windows liest Bytes in privatem, nicht ausführbarem Speicher und wickelt künstliche Register- und Stackzustände ab. Acht Originalprologgrenzen und drei Präfixgrenzen bestehen; eine Gegenprobe mit unpassenden Gesamtprologdaten scheitert wie erwartet. Ergebnis: 38 Originalprüfungen und 75 OS-Unwindprüfungen ohne Fehler.

## Quellcodereview und korrigierte Ausnahmeregel

Die drei Header und ihre Tests wurden auf den sechs in `review.json` gepinnten Ständen geprüft. Der Plan prüft den gesamten Originalbody, kopiert das Präfix, benutzt dessen eigene Unwinddaten und behandelt nur vollständige Instruktionsgrenzen als gültige Ziele.

Der ursprüngliche Wrapper fing jede Callback-Ausnahme ab. Dadurch verschluckte ein äußerer Before- oder After-Callback auch eine native Ausnahme aus einem inneren `Select`. `initial-wrapper.h` enthält exakt diesen historischen Stand; `NestedCallbackExceptionReview.cpp` und `nested-counterexample.txt` belegen beide Fälle. Die alten positiven Unit-Tests hatten diese Fälle nicht erfasst.

Der korrigierte Vertrag ist ausdrücklich:

- Eine Before-Ausnahme propagiert. Der Originalaufruf entfällt. After läuft einmal mit Ticket 0, `beforeCompleted=false` und `normalReturn=false`.
- Nach normaler Originalrückkehr propagiert eine After-Ausnahme ebenfalls.
- Während eine primäre Ausnahme bereits abgewickelt wird, wird nur die zusätzliche After-Ausnahme abgefangen, damit die primäre erhalten bleibt.
- Die Regeln gelten auch für reentrant ausgelöste native Ausnahmen. Es gibt keine Herkunftsklassifizierung über TLS. LastError folgt dem propagierten Fehler; bei erfolgreichem After bleibt der ursprüngliche Ausgangswert erhalten.
- Fault bleibt dauerhaft gesetzt. Ein späterer Aufruf wird dadurch allein nicht unterdrückt. Der künftige Besitzer muss den Fehlerzustand auswerten.

`CallbackPolicyReviewTests.cpp` prüft sechs unabhängige Fälle: direkte und verschachtelte Before-/After-Ausnahmen sowie direkte und verschachtelte sekundäre After-Ausnahmen bei bestehendem Unwind. Alle 42 Assertions bestehen; Ausnahmecode, fehlender Rückgabewert, Aufrufzahlen, Tickets und Flags stimmen.

Die erneut gebauten Autorensuiten bestehen mit 1.842 EntryPlan-, 691 Wrapper- und 119 Trampolinprüfungen. Nach der Korrektur wurden die betroffenen Wrapper- und Trampolinsuiten sowie der Produktionscompile ohne Testhooks erneut gebaut. Die unveränderten EntryPlan- und OS-Unwind-Läufe wurden nicht wiederholt. Die Trampolinsuite führt die echten fünf kopierten Bytes aus und springt danach in ihre ausdrücklich künstliche typisierte Fortsetzung. Sie führt keinen vollständigen Originalbody aus.

## Lebensdauer und Grenzen

Das Original-Image registriert geschützten privaten Code nach dem Cache-Flush mit der passenden Runtime-Tabelle. Fehlgeschlagenes Deregistrieren verhindert die Freigabe dieser Tabelle. Nach Bind bleiben Code und Unwinddaten für die Prozesslebensdauer erhalten. Der Besitzer muss Vorbereitung und Freigabe serialisieren sowie Originalquelle, Observer und Callbackkontext für jeden möglichen Aufruf gültig halten.

Nicht geprüft oder bereitgestellt sind Spielthread-Zulassung, eine Ressourcenlease, Hook-Installation, Rückroll- und Veröffentlichungspolitik oder Tiny/Giant. Ein zurückgekehrter Before-Callback belegt keine erfolgreiche Scale-Rücknahme. Die untersuchten Header sind im geprüften Stand noch nicht in `TrainerBridge` eingebunden.

## Reproduktion

Aus dem Repositoryverzeichnis:

```
py -3 -B artifacts/review-motion-entry-20261011/check_original.py
artifacts\review-motion-entry-20261011\build-review.cmd
artifacts\review-motion-entry-20261011\build-counterexample.cmd
artifacts\review-motion-entry-20261011\build-policy-review.cmd
```

`build-revised-review.cmd` reproduziert ausschließlich die nach dem Fix neu gebauten Suiten, den Produktionscompile und die sechs unabhängigen Fälle. Der Build schreibt nur in diesen Reviewordner und benötigt den im Skript genannten lokalen MSVC-/Windows-SDK-Pfad. Die erzeugten EXE-/OBJ-Dateien wurden nach den erfolgreichen Läufen entfernt; ihre Hashes stehen in `build-products.json`, die ursprünglichen in `initial-build-products.json`. Quellstände und Protokolle bleiben erhalten. Der Reviewer hat weder Autorenquellen noch Spiel, IDB, Docs oder Pakete geändert.
