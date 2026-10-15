# Unabhängiger Review: Audio-Headerprofile

**Im beschriebenen begrenzten Umfang akzeptiert. Keine offenen Blocker.**

Geprüfter Manifestpin: `20449ff941a9205bbb8edcfe34bb292563100096ecba7f1cc5293d279163f7d7`.

## Eigenständige Prüfung

`check.py` liest die Original-EXE direkt, prüft ihren vollständigen Hash und parst PE-Header, Sections und Importtabellen. Es importiert weder den Authorverifier noch dessen VM. Alle zwölf neuen und drei wiederverwendeten Bodies wurden vollständig gegen Originalbytes geprüft; jede einzelne aufgeführte Instruktion wurde erneut mit Capstone dekodiert und sowohl mit normalisierten Operanden als auch den IDA-Mnemonics verglichen.

ASM- und Pseudocodeseiten besitzen durchgehende Offsets, passende Gesamtzahlen und abschließende Cursor. Der `truncated`-Wert einzelner Pseudocodeseiten wurde nicht als Beleg gegen oder für vollständige Semantik behandelt. Entscheidend sind die erhaltenen Seiten und ihre explizite Gesamtdeckung.

Die nicht als Instruktionen aufgeführten Bytes sind explizit nachvollzogen: drei Bytes NOP plus sechs DWORD-Sprungziele hinter `0A3590`; ein bereits erfasster INT3-Paddingbyte hinter `089390`. Es wurden keine Lücken stillschweigend als Padding akzeptiert.

Importauflösung bestätigt die Critical-Section-Aufrufe und `471A60` als Importthunk für `memcpy`. Die Original-RTTI bestätigt die konkrete ToolBank-Tabelle `61CB70`. Der vollständige Diagnosestring `GetScdHeaderSize` und die ausgewählten VTable-/Callbackzeiger wurden zusätzlich direkt aus dem PE gelesen.

Alle 26 Claimreferenzen werden vom unveränderten Coverageparser aufgelöst; er akzeptiert sämtliche 15 vollständigen ASM-/Originalbyte-Objekte. Die 60 vorherigen Evidence-Dateien entsprechen den angegebenen Pins und enthalten keine der zwölf Adressen in den ausdrücklich inventarisierten function-Arrays. Das ist eine begrenzte Inventaraussage.

Der eigene Lauf umfasst **22.308 technische Checks und 1.679 synthetische Instruktionsfälle**. Die Checkzahl enthält auch wiederholte PE-Spannen-, Importnamen- und Modellassertionen; sie ist kein Maß für vollständige semantische Abdeckung.

| Eigene Fälle | Anzahl |
|---|---:|
| Metadaten-ID mit signed Index/Offset, Magic und variierenden Profilen | 192 |
| Sequenzanzahl-Metadatengetter | 8 |
| Beide Größenhelfer mit unsigned Versionspartition | 20 |
| Flagmaske und voller 32-Bit-Index des Sequenzwrappers | 1280 |
| Enger State-0-Headerzweig, Fortschritt bereits mindestens80 | 144 |
| MOVSXD und anschließender Allocator-/memcpy-Pfad | 12 |
| Standby-Größenarithmetik DWORD minus WORD | 15 |
| Rebind-Reihenfolge und lokale Aliasbedingung | 8 |

Die eigene `selected_machine.py` wurde für diesen Review neu geschrieben. Sie interpretiert ausgewählte, aus Originalbytes dekodierte Integerinstruktionen. Unbekannte Instruktionen/Aufrufe scheitern. Helpers werden an konkreten Callstellen durch dokumentierte, synthetische Rückgaben ersetzt. TLS-Initialisierung, echte Allokation, reale memcpy-Aufrufe, Scheduler und Providerimplementierungen werden nicht ausgeführt.

## Zehn Claims

1. **07AD30:** Die ASM bestätigt SEDB-DWORD, fixed `h+32`, sign-erweiterten Index und Offset sowie `1000*BankWORD + SequenceWORD`. Die Critical Section schützt nicht automatisch den vom Caller gelieferten Dateibereich. Profilvariationen zeigen nur, dass diese lokale Instruktionsfolge jene Bytes nicht auswertet.
2. **07ADA0:** Magicvergleich und `WORD(file+u16(file+14))` sind korrekt. Es gibt keinen behaupteten Vollparser.
3. **0A13B0 / 0A4020:** Version1 liefert16, unsigned `(version-2)<=2` liefert32, andere Werte rufen den Diagnosecallback und liefern bei dessen Rückkehr0. Version0 bleibt von dem getrennten Registriergate zu unterscheiden.
4. **0A2840:** Byteflag0x02 und vollständiger EDX==0 führen zum Tailbranch09FD20. Werte0x100/0x10000 werden nicht auf einen kleinen Index gekürzt. Die beiden behaupteten VTable-Zellen stimmen.
5. **0A3590:** Der Claim gilt dem angegebenen State-0-Ausschnitt. Kapazität `+48` und Fortschritt `+64` beziehen sich hier auf den eingehenden **Subobjectpointer**; die spätere Banklänge befindet sich bei dessen `-112`, also Gesamtbank+48. Magic muss passen, Version/Größe werden vor den Counts geschrieben, die Count-WORDs stehen bei absoluten Datei+52/+48/+50. Die eigenen Modelle beginnen mit Fortschritt80 und schließen Providerread/States1..5 aus. Der vollständig gelesene vorherige ASM-Zweig addiert Providerfortschritt und prüft80 nochmals, ohne hieraus ein korrektes Scheduling abzuleiten.
6. **0A34E0:** Byte Gesamtbank+400 wird1; Critical Section+360; DWORD Gesamtbank+212 wird State. Der Leave-Aufruf hängt anschließend am Byte+400. Die Beziehung zu Subobject+52 bei Gesamtbank+160 ist rechnerisch und durch die Caller-LEA belegt, keine globale Synchronisationsgarantie.
7. **0A2220:** Auf dem beschriebenen ungültig gewordenen Pending-Handlepfad folgen SEDB-Vergleich, Versionkopie und die32-Bit-Subtraktion `DWORD(file+16)-WORD(file+h+28)`. Die Diagnosecallbackrolle bleibt zutreffend offen; die weitere Routine enthält mehr Verhalten als dieser Claim.
8. **0A09A0:** MOVSXD bei0A09C2 ist eindeutig. Der dadurch erzeugte64-Bit-Wert geht in RDX an0F8920 und in R8 an den bestätigten memcpy-Thunk. Er wird nicht stillschweigend als unsigned32-Größe modelliert. Der Offlineinspektor darf den gespeicherten DWORD weiterhin unsigned **anzeigen**; das beschreibt nicht die native Kopierinterpretation. Null-/Riesenallokation und tatsächliches Kopieren werden nicht ausgeführt oder als erreichbar behauptet.
9. **0A0B00:** Unlink, bedingter Cleanup des alten Payloads, Nullsetzen, neue Kopie und bedingter virtual+16-Aufruf sind in dieser Reihenfolge belegt. Der lokale Körper lehnt Source==alter Payload nicht ab. Ein erreichbarer UAF oder Cleanupvertrag folgt daraus nicht.
10. **0896F0 / 0918D0:** Die vollständig gelesenen Wrapper haben entsprechende Kontrollflüsse. Provider+8 erfolgt nur nach nonnull Provider+56; ein exakter bestehender Banktreffer überspringt den ausdrücklichen Provider+64-Aufruf. No-hit-Rückwege führen über+64. Die Claimgrenzen weisen den Virtuals keine unbewiesenen Lock-/Validierungsrollen zu.

## Ergänzende Authorchecks

Der Authorverifier wurde ausschließlich mit `--check` ausgeführt: PASS,8.570 Checks/2.382 Modellfälle. Der separate Integrationscheck besteht ebenfalls und prüft den portablen ROOT. Beide Ausgaben liegen hier; sie sind ergänzende Reproduktionsnachweise und nicht die unabhängige Prüfung.

## Grenzen und Reproduktion

```powershell
py -3 -B artifacts/review-audio-header-profile-20261011/check.py
```

Die Bedeutung der Dateiheaderbytes+12/+13 bleibt ungeklärt. Fehlende Prüfungen in ausgewählten lokalen Körpern beweisen keine Unterstützung anderer Werte. Unbekannte Provider-/Allocatorverträge, diagnostische Callbackwirkung, übrige Streamingzustände, Callerreichweite und globale Lebensdauer bleiben offen.

Nur eigene Reviewdateien wurden geschrieben. Authorstudie, Produkt, Dokumentation und IDB blieben unverändert. Kein Spiel, keine GUI, kein Attach, keine Injection, kein nativer Speicherzugriff auf laufende Prozesse und keine native Funktionsausführung.
