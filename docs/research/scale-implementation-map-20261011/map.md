# Tiny/Giant: vorhandene Bausteine und nächster Implementierungsschritt

Stand: 11.10.2026, nach Auslieferung von v0.12.17. Dies ist eine lesende Bestandsaufnahme. Keine Produktänderung, kein Build, kein neuer IDA-Capture und kein Spielzugriff.

## Empfehlung

Als nächstes eine durchgängige **Scale-Transaktion für den aktuellen Spieler** umsetzen: Tiny (absoluter Faktor 0,5), Giant (2) und bedingtes Reset, anschließend dieselbe Transaktion für zeitlich begrenzte Rewards verwenden. Die Kontrollen gehören in die bestehende Sora-/Effektoberfläche. Ein Assetbrowser ist dafür weder erforderlich noch vorgesehen.

Das Ziel ist noch nicht durch einen zusätzlichen Float-Store erreicht. Vor der ersten Produktfreigabe braucht diese Transaktion zwei konkrete neue Verträge: eine belegte Bindung an die aktuell verwendete Motion-Ressource und einen Scale-spezifischen Kontext-/Ownership-Stempel. Diese Arbeit kann eng um den vorhandenen Consumer und die vorhandenen Actor-Beobachter erfolgen. Offlineparser, Providerreihenfolge, generelle Actor-Generationen und Lost-ACK-Transport müssen nicht neu erfunden werden.

Die Skalarwerte und der vorgeschlagene Ausgangsbereich 0,25 bis 4 sind Produktentscheidungen aus der älteren Studie; keine vom Spiel belegten sicheren Grenzwerte. Als erste Implementierung bietet sich kontrollierbarer, lebender, nicht angehängter Basis-Sora an. Weitere Rollen/Forms kommen nach ihren gezielten Tests hinzu. Die bereits verifizierte Rollenprüfung unterstützt grundsätzlich auch Roxas und Mickey; das ist keine neue Forschungsaufgabe.

## Was bereits vorhanden ist

| Baustein | Konkrete Implementierung | Bereits gelöst | Verbleibende Grenze |
|---|---|---|---|
| Effektive Assetbytes | `EffectiveAssetManifest.VerifyAsync`, `AssetEffectiveByteReader.ReadAsync` | Verifizierte EXE-/Panacea-Profile, deklarierte Providerreihenfolge, Raw/Loose/PKG-Decodierung, Grenzen, Abbruch und Quellenstempel | `OfflineManifestBinding`; keine Entdeckung oder Bindung der Provider eines laufenden Spiels |
| Motionparser | `MotionPayloadReader.ReadType9Entry` / `ReadPayload` | 144-Byte-Prefix, Prototype0 und RAW, begrenzte Tabellen/Indizes/Spannen, unveränderliches Rootmodell | Nur Rootdaten; kein Skeleton/IK, kein Modellbesitz, keine native Allocation-Länge |
| Motionauswertung | `MotionPayload.Evaluate`, `MotionRootEvaluator.Multiply` / `ScaleBasis` | Float32-Zwischenschritte, Kurven/Wrap-Fortschritt, RAW-Interpolation, Matrixreihenfolge | Caller bestimmt Actorzweig und Transformreihenfolge; ein Frame ist keine Aussage über den nächsten Frame |
| Actoridentität | `actor_lifetime::{Install,ObserveCurrent,Resolve,IsRetired,Pin,Unpin}` | Bridge-Nonce, Generation, Birth/Death-Beobachtung, Address-Reuse, gepinnte Beobachtungstoken | Pin hält keine native Referenz. Keine Motion-, Parent-, Achsen- oder Scalarrevision |
| Rollen/Steuerbarkeit | `player_role::Inspect`, `actor_movement::MovementReady`, `gameplay_state::Inspect` / `InspectNative` | Rollen/Backlinks/Liste, Scene-/Input-/Transition-Gates, Host-unabhängiger Cleanup-Check | Scale braucht zusätzliche konkrete Transform-/Resourcebedingungen |
| Native Transaktionen | `movement_tx::{Execute,Preflight,Commit,CompleteRelease,Tick}` | Bitgenaue Expected-Werte, Journal vor Write, reservierter Receipt, Replay, Revision, Deferred Cleanup, eindeutiges Uncertain | Hart auf Walk/Run/Fall/Jump und MOV1 festgelegt; keine Scale-/Kontextrevision |
| Hosttransport | `MovementProtocol`, `BridgeConnection.ExecuteMovementAsync` / `ResolveMovementAsync` | Korrelation, binäre UInt64/Float32-Bits, keine neue Mutation hinter mehrdeutigem Ergebnis | Kein Scale-Paket/Hostpfad vorhanden |
| Zeitliche Rewards | `MovementEffectLease`, `EffectEngine`, `EffectModel`, `TwitchGameAdapter` | Retained Leases je Bridge/Actor, Operation-Recovery, ReleaseIntent, Timer/Readiness und Cleanup | Scale benötigt eigene Bereitschaft, Restorebedingungen und Konfliktpolitik |
| STATUS-Unterbau | `status_revision::Ledger`, `status_fields::Journal`, weitere Status-Header | Getestete Beispiele für Feldrevisionen, identische native Writes, Allocation-/Bindingwechsel | Nicht im produktiven `TrainerBridge.cpp` installiert; STATUS-Poolfelder sind nicht Actor+60 |

`TrainerBridge.cpp` bindet ActorLifetime, GameplayState und MovementTransaction tatsächlich ein. `TrainerFrame` installiert/beobachtet den Actor, behandelt MOV1-Pakete und ruft das Journal vor und nach Feature-Ticks auf. Der Post-Original-Update-Hook ist vorhanden. Der alte Kommentar „not active until ... installed“ im Movement-Modul ist eine Integrationsbedingung, kein Beleg dafür, dass der aktuelle Pfad inaktiv sei.

Umgekehrt gibt es außerhalb der Coredefinitionen keine produktive Aufrufstelle von `MotionPayloadReader`, `MotionRootEvaluator`, `AssetEffectiveByteReader` oder `EffectiveAssetManifest` in Bridge/App/Twitch. Ihre vorhandenen Tests beweisen also noch keine Scaleintegration. Weder der Featurekatalog noch der Rewardkatalog bietet Tiny/Giant an.

## Was ausdrücklich nicht erneut gebaut werden muss

- Kein weiterer Offline-Motionparser oder Assetprovider-Resolver. Die später implementierte Studie `effective-asset-reader-20261007` ersetzt den noch als „proposal_not_implemented“ markierten Vorschlag in `drive-effective-bytes-20261007` in genau diesem Offlineumfang.
- Keine neue allgemeine Actor-Generationsverwaltung. Die produktive Implementierung mit 128 Watches kann weiterverwendet werden; beobachtete Retirement und Observer-Fault müssen verschieden bleiben.
- Keine vollständige STATUS-Observerintegration als vermeintliche Scalevoraussetzung. Sie beobachtet einen anderen Speicherbereich und andere Ereignisse. Ihr Revisionsmodell ist ein Vorbild, nicht der fertige Scalarobserver.
- Keine Wiederherstellung des entfernten Browsers. Die vorhandene generische Featureoberfläche und Reward-Engine reichen für die spätere Bedienung.
- Kein vollständiger Reverse-Engineering-Abschluss aller Collision- oder Motionfunktionen als pauschale Vorbedingung. Erforderlich sind die konkreten neuen Eingangs-, Besitz- und Lebensdauerverträge des gewählten Scale-Unterbereichs.

## Die echten Restaufgaben

### 1. Native Motionbindung und frischer Projektionskontext

`motion_features::ReadView` kennt Model/Motion-Pointer, die beiden Vtables, Payloadpointer, einige Headerwerte, logische/aufgelöste IDs und Frame/Blend. Es prüft kleine lesbare Header, keine vollständigen Payloadspannen oder Allocation-Identität. Seine Sora-Gates eignen sich außerdem nicht unverändert für Roxas/Mickey.

Die neue Scale-Zulassungsprüfung braucht ein natives, begrenztes Abbild mit mindestens Actor-Generation, Motion-/Resource-Bindingrevision, nachgewiesener Payloadbasis und -länge, Format, wirksamem Frame/Blend sowie den tatsächlich relevanten Actorzweigwerten. Root-, Parent-, Model- und Custom-Callback-Bindungen dürfen nicht aus Pointergleichheit als Generation abgeleitet werden. Eine geschätzte Länge aus der letzten referenzierten Tabelle ist keine Allocation-Grenze.

Für die Verbindung zur vorhandenen Coreauswertung gibt es zwei sinnvolle technische Wege, die erst nach Prüfung des konkreten Ressourcenbesitzes entschieden werden sollten:

1. Native begrenzte Kopie der gebundenen Rootdaten mit opaque Bindingtoken an den Host; der Host parst diese Kopie mit dem vorhandenen Reader. Beim Commit kontrolliert die Bridge denselben Token und frische Projektionswerte.
2. Enger nativer Parser-/Evaluatorpfad für die gewählte Teilmenge, mit den Corefixtures als Referenz. Das spart Host-Rundreisen, verlangt aber eine neue unabhängige Implementierung der relevanten Float32-Schritte.

Der erste Weg nutzt mehr vorhandenen Code. Er ist jedoch nur sinnvoll, wenn die Native-to-Host-Bindung und ihre Invalidierung belastbar geschlossen werden. Ein vorab auf Disk geprüftes MSET, Dateiname, Modelpointer oder `OwnedAssetBytes.DecodedSha256` allein erfüllt diesen Vertrag nicht. Ein Live-Ressourcenabbild kann die größere Aufgabe einer vollständigen laufenden Providerkonfigurationsaufnahme umgehen; das ist eine Designoption, noch kein bewiesener vorhandener API-Pfad.

Ein erfolgreicher Check von Frame N darf nicht stillschweigend zur Garantie für N+1 werden. Die zulässigen Folgeframes/-zustände müssen entweder durch einen begrenzten geprüften Bereich abgedeckt sein oder die Invalidierung muss vor der nächsten relevanten nativen Verwendung wirken. Ein nachträglicher Post-Frame-Abbruch allein beweist diese Reihenfolge nicht. Genau diese lokale Schedulingfrage ist vor der Freigabe zu schließen; es ist kein Auftrag für einen pauschalen globalen Matrixhook.

### 2. Scale-Kontext und native Übernahme

Der bestehende Vertrag setzt zunächst Parent+1696=0, XYZ+48/+52/+56=1, Ramp+2732=1 und keine Custom-Transform-Callback-Flag voraus. Actor+60 ist das einzige zu schreibende Feld. Actor+2732 ist wegen seiner nativen Cleanupwirkung ausgeschlossen.

Actor-Lebensdauer allein beobachtet keinen Attach→Detach-Zyklus, native gleichwertige Scalar-/Kontextwrites oder Motion-Neubindung. Der konkrete neue Writer-/Attachment-Review des anderen Agents soll festlegen, welche lokalen Revisionen bzw. Invalidierungen benötigt werden. Bis dahin ist eine lediglich pro Frame erneut gemessene Null-Parentadresse kein Beleg für unveränderte Kontextgeschichte.

Zwischenmeldung von `origin_voice_resources`, noch nicht als unabhängig geprüfter neuer Befund übernommen: `1C7E00` schreibt +60 auf 1,0 an `1C7E49`; der Agent ordnet den Writer über RTTI/Vtable `5B3FC8` einem Stitch-Kontext zu und prüft die virtuelle Invocation weiter. Die ältere Aussage „kein zusätzlicher Writer attribuiert“ darf deshalb nicht als aktuelle Exklusivitätsannahme verwendet werden. Summon-/Sonderaktionsgrenzen sind ein konkreter Bestandteil des nächsten Revoke-Reviews.

Für Reset wird der ursprüngliche Skalar unter dem **aktuellen** gültigen Projektionskontext geprüft. Bei einem fremden Scalarwert endet Ownership ohne Store. Bei Kontextänderung wird nicht blind unter einem neuen Parent restauriert. Unklarer Observerzustand wird als Uncertain geführt; bekanntes Retirement beendet ohne Pointerdereferenz. Deferred Cleanup bleibt an den ursprünglichen Actor gebunden und wandert niemals auf den Ersatzspieler.

### 3. Eigenes Journal und eigener Transport

Neue Dateien könnten `ScaleTransactionSupport.inl`, `ScaleProtocol.h`, `ScaleModels.cs`, `ScaleProtocol.cs`, `ScaleTransport.cs` und `ScaleEffectLease.cs` sein. Das sind vorgeschlagene Implementierungspunkte, keine vorhandenen Dateien.

Die Typen sollten Actoridentität, Scale-/Context-/Resource-Stempel, Original-/Expected-/Applied-Float32-Bits, Lease-/Owner-/Operation-ID, Revision und eindeutige Outcome/Reason-Felder transportieren. Die neue Request-/Responsebelegung ist gegen die bestehende Shared-Memory-Belegung abzugleichen; keine ungeprüfte Wiederverwendung des MOV1-Schemas oder von Capabilityslots.

Acquire reserviert Journal und Receipt vor einem vier Byte großen Store. Reapply bewahrt den ursprünglichen Skalar und akzeptiert nur noch besessenen, unveränderten Kontext. ReleaseIntent bestätigt Annahme getrennt von abgeschlossener Restauration. QueryOperation/QueryLease/Acknowledge müssen verlorene ACKs und Verbindungsabbrüche ohne erneutes Acquire auflösen.

Besonders wichtig: `movement_tx::Mutate` übernimmt bei Reapply einen zwischenzeitlich geänderten Feldwert als neue Basis. Das ist die bestehende Movementpolitik. Für Scale verlangt der frühere Vertrag stattdessen Ownership-Ende bei nativer Übernahme. Den Movementcode daher nicht unverändert kopieren.

### 4. Durchgängige Produktintegration

Nach den beiden Nativeverträgen: Scale-Dispatch und Tick/Reset in `TrainerBridge.cpp`, Capability-/Snapshot-/Protokollkontrakt in Core, Sessiontransport, dieselbe typisierte Schnittstelle für manuelle Tiny/Giant/Reset-Bedienung und die Reward-Engine. Bestehende Integrationspunkte sind `GameSession`, `MainViewModel`, `TwitchGameAdapter` in `ViewModels/TwitchViewModel.cs`, `IGameControl` in `Effects/EffectModel.cs` und `Effects/EffectCatalog.cs`.

Tiny und Giant bilden eine gemeinsame Konfliktgruppe; kein multiplikatives Wiederanwenden auf schon skalierte Werte. Der Timer läuft nur bei angewendetem und kontrollierbarem Zustand. Ende/Stop/Disconnect wird in einen ReleaseIntent überführt; eine vom Spiel noch nicht abgeschlossene Bereinigung bleibt sichtbar, statt Erfolg zu behaupten. Bei verlorener Antwort darf weder der Timer vorzeitig starten noch derselbe Effekt mit neuer Operation blind erneut appliziert werden.

Die Produktbeschreibung lautet „Transformgröße“. Joint-/Waffen-/Collisioncenter können sich ändern; die bisherigen Belege zeigen keine proportional vergrößerten Weltradii oder vollständigen Hurt-/Hitboxen. Keine Behauptung „nur kosmetisch“ und keine künstliche Angleichung von Actor+1776/+1780/+1784 im ersten Feature.

## Erforderliche neue Tests

1. **Bindung:** gleiche Adresse mit neuer Actor- oder Ressourcengeneration; Wechsel während Kopie/Hostauswertung/vor Commit; gesperrte, gekürzte oder übergroße Daten; geänderter Provider; abgebrochene Kopie; kein erfolgreicher Commit aus bloß offline validierten Bytes.
2. **Float32/Actorzweige:** bekannte Prototype-/RAW-Fixtures aus `MotionPayloadTests`; beide Scalarwerte; Original-/Kandidatprojektion; Overflow, NaN, Degeneration, Unterlaufgrenzen; Blend-/Frame-/Floor-/Custom-/Parentzweig entweder korrekt modelliert oder ausdrücklich abgewiesen. Ein Current-Matrix-Test ersetzt diese Fälle nicht.
3. **Native Journal:** exakter Vier-Byte-Store; alle ausgeschlossenen Nachbarfelder unverändert; Replay ohne Doppelwrite; unveränderliche Originals; native anderswertige und gleichwertige Takeover; Attach→Detach zwischen zwei Snapshots; OffCurrent mit späterem Cleanup; Retirement gegenüber Fault; Writefault und voll belegtes Journal.
4. **Transport/Rewards:** verlorenes Acquire-/Release-ACK, Querymiss, Reconnect mit gleichem/neuem Bridge-Nonce, Ownerkonflikt, Tiny↔Giant, StopAll, Hosttimeout, Form-/Scenewechsel, ausstehender Cleanup und Timerpause. Vorlagen sind `MovementProtocolTests`, `FakeMovement` und `MovementRewardTests`.
5. **Produkt:** Katalog-/Protocol-/Capabilitykonsistenz, manuelle und zeitliche Kontrollen über dieselbe Transaktion, Offscreen-Featuretests. Erst danach separat abgestimmter Spieltest für die ausdrücklich unterstützten Rollen/States; synthetische Tests ersetzen ihn nicht.

## Bereits vorhandener Testnachweis

Aus den unveränderten v0.12.17-Paketlogs gelesen, hier nicht neu ausgeführt:

| Bereich | Checks, jeweils 0 Fehler |
|---|---:|
| MotionPayload-Core | 2.275 |
| EffectiveAssetReader-Core | 119 |
| ActorLifetime | 6.023 |
| ActorMovementGuard | 2.044 |
| GameplayStateGuard | 1.066 |
| MotionGuard (Tempo-Override, kein Scale) | 454 |
| MovementTransaction | 440 |
| StatusFieldTransaction (nicht produktiv eingebunden) | 1.976 |
| StatusRevisionLedger (nicht produktiv eingebunden) | 930 |
| StatusObservationRuntime (nicht produktiv eingebunden) | 90 |
| StatusBootstrapContract (nicht produktiv eingebunden) | 11.238 |
| StatusThreadDrain (nicht produktiv eingebunden) | 812 |

Die Motionstudie dokumentiert zusätzlich 215 gelesene type9-Einträge aus vier MSETs und 1.075 ausgewählte Frames. Alle beobachteten Einträge waren Prototype0; RAW wurde dort synthetisch geprüft. Diese Stichprobe ist kein vollständiger Animations-/Framebereichsnachweis. Die Größenwerte, Projektionen, nativen Eigentümer und zukünftigen Frames müssen weiterhin für das neue Feature geprüft werden.

## Ergebnis dieser Bestandsaufnahme

Der nächste Auftrag sollte **„ScaleTransaction plus Tiny/Giant/Reset mit gebundener Motion-Prüfung und retained Cleanup“** sein. Zuerst die zwei eng gefassten Nativeverträge schließen, dann denselben vertikalen Pfad bis Katalog und Reward testen. Das ist ein konkreter Produktpfad. Eine erneute allgemeine Parserstudie, ein Diagnosefenster oder eine Wiederherstellung des Assetbrowsers würde die tatsächliche Lücke nicht schließen.

Die Aussagen dieses Dokuments sind anhand der Quellpins und lokal aufgelösten Anker in `inventory.json` nachprüfbar. `verify.py` prüft diese Pins und den vorhandenen Testnachweis; es führt keine Produkt- oder Spieltests aus. Ergänzungen anderer Agents sind als solche zu behandeln, bis deren eigener Reviewstand feststeht.
