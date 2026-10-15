# Tiny/Giant: nächster konkreter Implementierungsschritt

Stand: 11.10.2026, lesender Abgleich der aktuellen Quellen mit der eingefrorenen Motionstudie. Keine Produktänderung, kein Build, kein Livezugriff.

## Entscheidung

**Als nächste kleine Implementierung einen Motion-spezifischen Eintrittsplan und typisierten Wrapper für RVA `3C8CD0` bauen und isoliert prüfen.** Der Wrapper muss vor dem Original einen synchronen `BeforeContextChange(controller)`-Aufruf ermöglichen, danach das Original mit unveränderten Argumenten/Ergebnis ausführen. Anfangs beobachtet er ausschließlich Revision/Eintritt; er aktiviert noch keinen Scale. Das schließt die tatsächlich fehlende native Anschlussstelle für den Normalpfad und liefert eine überprüfbare Basis für den Scale-Widerruf.

Ein zusätzlicher Check in `TrainerFrame` schließt diese Lücke nicht: [TrainerBridge.cpp:780](C:/Users/shinz/source/repos/KH2Trainer/src/KH2Trainer.Bridge/TrainerBridge.cpp:780) führt das Original-Update aus und ruft erst danach `OnFrame`; der Spielthread wird bei [Zeile615](C:/Users/shinz/source/repos/KH2Trainer/src/KH2Trainer.Bridge/TrainerBridge.cpp:615) bestätigt. Die Installation/Beobachtung neuer Motion-Observer kann nach der Actor-Beobachtung bei [Zeile388](C:/Users/shinz/source/repos/KH2Trainer/src/KH2Trainer.Bridge/TrainerBridge.cpp:388) angebunden werden. Der eigentliche Widerruf muss aus dem nativen Eintritt kommen, nicht aus diesem späteren Tick.

## Welche Infrastruktur wirklich vorhanden ist

| Anschlussstelle | Wiederverwendbarer Mechanismus / konkrete Grenze |
|---|---|
| `ActorLifetimeSupport.inl:251` | Birth-/Death-Wrapper benachrichtigen vor dem Original. Sie beobachten Actor-Lebensdauer, nicht Motion-Kontext; die Slot-Swaps bei188ff erfassen direkte Calls auf3C8CD0 nicht. |
| `StatusBreakpointRouter.h:79`, `:112`, `:148` | Residentes INT3-Eintrittsrouting, Vollkörperfingerprints, CAS, Module-Pin. `EntryCount=5` und ein statischer aktiver Router sind fest; keine generische bereits integrierte Motion-Hook-API. |
| `StatusEntryPlan.h:177`, `:239` | Originalpräfix, Instruktionsgrenzen, Fortsetzungsadresse und Unwinddaten für genau fünf STATUS-Körper. R11-Scratchannahme gilt ausdrücklich nur für diese Körper. |
| `StatusOriginalTrampolines.h:80`, `:111` | RX-Trampoline, Cacheflush, `RtlAddFunctionTable`, unveränderliche Originalpointer und Prozesslebensdauer nach Veröffentlichung. Für Motion fehlen die eigenen Definitionen/Bindings. |
| `StatusObserverSupport.h:119`, `:230` | Before/After-Ticket, Reentranzzählung, Exceptions und LastError-Erhaltung. Das Before führt eine STATUS-Ledgeraktion aus; es bietet noch keinen Scale-Restorecallback. |
| `StatusObservationRuntime.h:120`, `:159` | Bestätigter Besitzerthread, Einstiegssperren und spätere Drain-/Arm-Phase. Im `TrainerBridge.cpp` derzeit nicht eingebunden; nicht durch Einschalten des STATUS-Runtimes für Motion wiederverwenden. |

Bestehende Testvorlagen sind `StatusEntryPlanTests.cpp`, `StatusOriginalTrampolinesTests.cpp`, `StatusBreakpointTests.cpp` und `StatusObservationRuntimeTests.cpp` unter `tests/KH2Trainer.Bridge.Tests`. Sie liefern Infrastrukturbeispiele; ihre früheren PASS-Zahlen gelten nicht für die neue Motiondefinition.

## Welche ABI fehlt – und welche bereits bekannt ist

Für **3C8CD0** ist der Aufrufvertrag im Original-ASM bereits klar: `RCX=Controller`, `EDX=aufgelöste Auswahl-ID`, `XMM2=Blendparameter`, `XMM3=Start-/Zielframe`, Ergebnis `AL`. Der passende Kandidat ist `uint8_t (__fastcall*)(uintptr_t, int32_t, float, float)`. Das ist kein Argument für weitere allgemeine Motionanalyse.

**Es fehlen die geprüften Original-Call-Trampolin- und Wrapper-Definitionen für genau diesen Eintritt:** kopiertes Präfix mit Fortsetzungsgrenze, dafür passende AMD64-Unwinddaten und Nachweis, dass der gewählte Scratchregistergebrauch keine Eingangswerte zerstört. Der vorhandene STATUS-Plan kopiert nur seine fünf fest definierten Präfixe und registriert deren Unwindtabellen. Bloßes Austauschen der RVA bzw. Umdeuten auf `uintptr_t`-Argumente würde insbesondere XMM2/XMM3 nicht korrekt weiterreichen.

Der kleinste aussagekräftige Test ruft den echten kompilierten Wrapper über eine isolierte, nicht im Spiel installierte Eintrittsroute auf: unterschiedliche bitgenaue XMM2/XMM3-Werte, negative ID, AL=0/1, ein synchrones Before-Protokoll und ein verschachtelter Eintritt; zusätzlich Ausnahme/Unwind durch das weitergeleitete Original. Das Before muss nachweislich vor dem ersten Kontextstore liegen. Keine aufgerufene Native-Gamefunktion ist dafür erforderlich.

Die Reihenfolge ist bereits belegt: **3C8D0D** schreibt Rootcontext C+328, **3C8D14/1B** löschen C+344/+352, erst **3C8D5B** ruft3C8A40. Letzteres konsumiert die neue Motion schon an **3C8B09**, optional **3C8BD3/3C8CA6**. Ein Return-Hook oder ausschließlich3C8A40-Eintritt kommt für den alten Rootcontext zu spät. Beleg: `motion-resource-binding-20261011/evidence.json#functions[addr=0x1403c8cd0]` und `#functions[addr=0x1403c8a40]`.

## Unmittelbar danach: lesende Payloadanbindung

Der native Bound-Reader kann als separater kleiner Baustein entwickelt werden: `TryCopyBoundMotion(context, reservationToken, ...)` verwendet die belegte Cache-Reservation+80 als äußere Grenze und den Type-9-BAR-Eintrag+12 als innere Grenze, verlangt `Motion+8 == Motion+144` und gibt ausschließlich eine begrenzte Kopie zurück. Die Behandlung des Reservierungstokens bleibt ausdrücklich Teil des Observervertrags; Unterbereichsknoten aus39E900 dürfen nicht allein aufgrund Zustand3/+88==+96 zugelassen werden.

Aktuell prüft [MotionFeatures.inl:56](C:/Users/shinz/source/repos/KH2Trainer/src/KH2Trainer.Bridge/MotionFeatures.inl:56) nur kleine Header; bei [Zeile71](C:/Users/shinz/source/repos/KH2Trainer/src/KH2Trainer.Bridge/MotionFeatures.inl:71) sind es96/160Bytes. [TrainerBridge.cpp:93](C:/Users/shinz/source/repos/KH2Trainer/src/KH2Trainer.Bridge/TrainerBridge.cpp:93) liefert geprüfte Lesbarkeit, keine Ressourcenownership. Die vorhandenen Parser [MotionPayloadReader.cs:10](C:/Users/shinz/source/repos/KH2Trainer/src/KH2Trainer.Core/MotionPayloadReader.cs:10)/`:15` und die Spanprüfung`:34` nehmen die fertige Kopie entgegen. Ein neuer Offlineparser ist unnötig.

**Grenze dieser nächsten Implementierung:** Ein einziger Normalpfad-Wrapper ist noch keine Tiny/Giant-Freigabe. Derselbe eng geprüfte Mechanismus muss anschließend die in der Studie benannten Cleanup-/Alternativ-/Cacheereignisse abdecken. Der synchrone Scale-Widerruf muss außerdem den getrennten Bodycache-/Scalarvertrag erfüllen. `movement_tx::Tick`/`CompleteRelease` (`MovementTransactionSupport.inl:117,133`) restaurieren vier Movementfelder und sind kein fertiger Vor-Kontextwechsel-Restore für Actor+60. Erst danach folgen Scale-Transaktion und Bedienung; ein Pre-Event-Revisionszähler allein darf keinen unzulässigen Scale bis zum nächsten Tick stehen lassen.

## Evidenzstand

- `artifacts/motion-resource-binding-20261011/manifest.json`: `a08b49891738bf8281a7a0fc1f41dc8cd7e0718d5351cda6a1c4e75a234d668b`; Reportabschnitte2–5 und kanonische Claims zu3C8CD0/3C8A40/39D590/39E690/39E900.
- `docs/research/scale-implementation-map-20261011/map.md`: vorhandener Core-/Actor-/Transaktionsunterbau, noch fehlende native Bindung.
- Quellzeilen oben beziehen sich auf den beim Schreiben vorhandenen Stand. Diese Notiz behauptet keinen neuen Testpass und verändert die eingefrorenen Studien nicht.
