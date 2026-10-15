# Gewöhnliche MSET-Reservation: Cache- und Completionvertrag

## Ergebnis und Geltungsbereich

Ein gehaltenes Cache-ReadScope lässt sich für **beobachtete gewöhnliche Reservationen** begrenzen. Der Referenzzähler allein verhindert Relocation nicht. Die neue, konkrete Asyncgrenze reicht von der Veröffentlichung eines Ladeauftrags bis **nach** Fixup, Cachecallback und dessen anschließender Entfernung aus der Queue. Unter einem gemeinsamen Gate können `activeNative == 0` und Queuehead `2A0D628 == 0` die ausstehenden Writes ausschließen, wenn alle unten bezeichneten Eintritte und die Bootstrapgeschichte tatsächlich erfasst sind **und der zugelassene Provider seine Zielwrites vor Readerreturn abschließt sowie keine späteren Aliaswriter zurückbehält**. Die Workerbody-Reihenfolge allein beweist diese zusätzliche Providerbedingung nicht. Dies ist der native Vertrag für einen Provider, keine bereits implementierte Live-Admission.

Die Belege betreffen Kind0, gewöhnliche nichtnegative Kategorien unter10000 und unabhängig begrenzte MSET-Spannen. Kind1-Audiocompletion, Kind2-Containerunterbereiche, fremde Aliaswriter und unaufgeklärte bestehende Knoten bleiben außerhalb dieses ersten Pfads. Auch eine syntaktisch gültige BAR-Tabelle macht daraus keinen Besitzbeweis.

## Konkrete Reihenfolge

1. `39E000` registriert oder verwendet einen Cacheknoten erneut. Neu angelegte Knoten erhalten kind0/state0, Umfang+80, Basis+88/+96 zunächst0. Frühere gleichnamige bzw. umkategorisierte Knoten können zurückgegeben werden. **Return allein beweist keinen neuen Knoten.**
2. `39D590` plant Zieladressen und schreibt +88; die Entscheidung liest WORD+2 nicht. `39D460` ruft den Planer, verwirft über die Arena hinausreichende Knoten oder ruft `39E690`. Die frischen Xrefs zeigen auch direkte Planercaller in `2B3D90` und `2B4C60`; ausschließlich `39D460` zu beobachten wäre unvollständig.
3. `39E690` kann rekursiv überlappende Knoten bearbeiten. Für Umzüge mit Quelle: state1, Unfixup `3A62B0`, gerichtete16-Byte-Kopie, Fixup `3A6120`, `39E900`, Basis+96=+88. Für Neuladen: state1, `3A0BD0(name,destination,39DEE0,node)`, dann ebenfalls +96=+88, **obwohl der Read noch aussteht**.
4. `3A0BD0` kann nach `154B40` vor Enqueue aussteigen. Sonst allokiert es96Bytes, ruft `3A0710(type1,name)` und speichert danach Ziel+56/Callback+64/Context+72. `3A0710` hat die Anfrage zu diesem Zeitpunkt schon als state0 verkettet. Es ist deshalb weder die Grenze vollständiger Submitinitialisierung noch die Ladecompletion.
5. Worker `3A0C60`: state0 auswählen → state1 → Readeraufruf ausführen und dessen Rückkehr abwarten → result+80 schreiben → namensabhängige Headerflags schreiben → für type1 und result!=0 `3A64F0` → state2 → nächste Queue-Suche. **Nach state2 folgt für diese Anfrage kein weiterer Payloadstore in diesem Körper.** Der Worker ist eine Endlosschleife; ein Eintrittszähler über seine gesamte Laufzeit wäre dauerhaft belegt.
6. Endlicher Consumer `3A0790`: nur state2; eventuell durch `79CF00+4752` verzögert. type1 und result!=0: `3A6840` vor Callback. result0: Ziel+56=0. Callback erhält RCX=Ziel, RDX=result, R8=Context. Anschließend Requestunlink und Freigabe. Der Request bleibt während des Callbacks verkettet.
7. `39DEE0`: result0 → stateFF; result!=0 → `39E900(node)`. Gewöhnliches kind0 wird state3. Kind1 kann eine zweite Audiocompletion anstoßen; Kind2 erzeugt Childalias-Knoten und entfernt den Parent. Beide sind für diese Admission ausgeschlossen.

`result!=0` ist exakt die native Bedingung: die QWORD-Vergleiche verwenden unsigned JBE gegen0 und der Cachecallback TEST. Ein signierter positiver Wert oder eine gültige Dateilänge wird damit nicht bewiesen. Die Scopegrenze bleibt der belegte Reservierungsumfang plus die geprüften Childspannen; Formatvalidierung kommt danach auf der Kopie.

## Ereignisse für den gewöhnlichen Pfad

Alle aufgeführten **Before**-Callbacks müssen vor dem Original in denselben kurzen Gate eintreten, die gemeinsame Ära widerrufen und einen endlichen aktiven Aufruf zählen. Originale laufen außerhalb des Gates. **After** muss bei normaler Rückkehr wie bei Unwind zuverlässig schließen; ein abnormaler oder unbekannter Abschluss schließt Read-Admission dauerhaft. Verschachtelte Aufrufe bleiben bis zum äußersten After aktiv.

| Ereignis | Konkrete Grenze | Zweck / Abschluss |
|---|---|---|
| Cacheanlegen/Wiederverwendung | Before/After `39E000` | Ursprung/Reuse unterscheiden; State0 ist noch kein geladener Bereich. |
| Reservierungsplanung | Before/After `39D590` | Ziele können bei gehaltenem Refcount wechseln; direkte Caller werden mit erfasst. |
| Gesamte Platzvergabe mit Retirement | Before/After `39D460` | Umfasst Arena-Prüfung, Freigabe und nachfolgende Listeniteration. Kann yielden; keinen Lock über das Original halten. |
| Byteumzug oder Cache-Submit | Before/After `39E690` | Rekursive Überschneidungen, Unfixup/Kopie/Fixup und vollständiger3A0BD0-Aufruf bleiben aktiv. Return nach Submit beendet Asyncbusy nicht. |
| Jede Queuepublikation | Before/After `3A0710` | Schließt auch andere native Queueproducer ein. After kennzeichnet nur Initializerreturn. Queue bleibt Busy bis konsumiert. |
| Cache-Submitdiagnose | Before/After `3A0BD0` | Ordnet Ziel/Callback/Context zu und erkennt fehlende Veröffentlichung. Für den geschachtelten normalen E690-Pfad ist dieser zusätzliche Zähler redundant; er macht den konkreten Submitvertrag explizit. |
| Endliche Completion | Before/After `3A0790` | Umfasst Fixup, reentranten Callback, Unlink/Free. Erst äußerstes After plus leere Queue kann Asyncbusy beenden. |
| Cachefinalisierung/Containerersatz | Before/After `39E900` | Aktualisiert Abschlussgeschichte; kind1/2 widerrufen gewöhnliche Admission. |
| Kategorien/Retirement | Before/After `39CCA0`, `39E2A0`, `3A6A10` | Kategorie oder Mitgliedschaft kann entfallen; BARcleanup geschieht vor manchen Unlinks. Ein bloßer Unlinkhook kommt für Ressourcenwrites zu spät. |

Das ist der konkrete Kandidatensatz für diese Kette. Direct-Fixup-/Unfixup-/Prepare-Eintritte `3A6840`, `3A6120`, `3A62B0`, `3A64F0` müssen denselben Gate zusätzlich verwenden, **wenn ihre direkten Aufrufe auf zugelassene MSET außerhalb der obigen Callclosure nicht ausgeschlossen sind**. Die vorhandenen Bodies belegen die geschachtelte Cachefolge, nicht die globale Abwesenheit aller anderen Writer. Für das kleinste globale Cachemodell dürfen auch diese vier Eintritte konservativ jede Cacheära widerrufen. Eine neue allgemeine Engineanalyse ist dafür nicht erforderlich; die vier Routen sind konkrete Anschlussstellen.

`39DEE0` braucht im belegten Asyncpfad keinen separaten Gate, wenn der gesamte3A0790-Consumer geschützt ist (frische Xrefs: nur als Callback in39E690 publiziert). Als beobachtete Completion kann es Ergebnis/Node identifizieren; sein Return allein beendet Busy niemals. `39CC40`/`39DA10` sind keine Bytelease und dürfen nicht als Admissionersatz verwendet werden.

## Beginn und Ende von Busy

- Vor Queuepublikation zählt mindestens der Submit-/Cacheeintritt. Danach hält die verkettete Anfrage den globalen Busy-Zustand über state0, state1 und state2 hinweg.
- Der Worker schreibt nur aus einer verketteten state0-Anfrage; state2 folgt auf seine letzten eigenen Payloadänderungen und die Rückkehr der aufgerufenen Hilfsfunktionen. Dass ein Provider danach keine weiteren Zielwrites ausführt, bleibt eine separate Voraussetzung. Der Consumer entfernt nur state2 und erst nach Fixup/Callback. Während dessen hält der endliche Consumerzähler die Admission geschlossen, auch wenn er das letzte Queueelement bereits entfernt hat.
- Eine neue Anfrage aus einem reentranten Callback hält Queuebusy aufrecht. Ein frühes Consumerreturn wegen der nativen Sperre lässt die Anfrage verkettet. Ein fehlender Abschluss wird nicht durch Zeitablauf als fertig eingestuft.
- Fehlerresult0 wird stateFF. Danach darf die Queue leer werden, aber dieser Knoten bleibt unzulässig. Bei unterdrücktem Start kann state1 ohne Request stehenbleiben; auch das ist kein Erfolg.
- **Kein erfolgreicher Cancelabschluss ist in der geprüften Kette belegt.** Ein beobachteter Abbruch/fehlender Request kann die Zulassung nicht wiederherstellen. Unbekannte oder widersprüchliche Abschlussgeschichte ist Fault bzw. dauerhaft ausgeschlossener Knoten.

Eine gewöhnliche Reservation wird erst wieder zulässig, wenn unter gehaltenem Gate sämtliche Ereignisse beendet, Queue und ausstehende bekannte Geschichte leer und gesund sind, und genau diese Nodeära **nach** beobachteter vollständiger Platzvergabe/Completion gültig ist: kind0, category0..9999, state3, nichtretired, gleicher +88/+96, positiver begrenzter/alignt passender +80-Umfang, ohne Overflow innerhalb belegter Arena, keine überlappenden zugelassenen Bereiche, eindeutiger gewöhnlicher Ursprung. Eine Wiederverwendung derselben Adresse verlangt eine neue Ära. Ein vorgefundenes oder zurückgegebenes unbekanntes Child wird damit nicht automatisch aufgewertet.

## Ursprung, Thread und Bootstrap

Ein Provider muss die Originentscheidung tatsächlich aus beobachteter Entstehungs-/Reusegeschichte führen. Beispielsweise: nach geprüftem Bootstrap bestehende Knoten als unbekannt markieren; nur einen belegten Neuanlagepfad von39E000 (inklusive neuer Initialisierung und39DD70-Insertion) übernehmen; spätere Entfernung und Wiederverwendung verfolgen. Die Funktion kann auch alte Knoten zurückgeben: ein bloßes After39E000 mit `kind0 && state0` reicht nicht. Der Beobachter muss dafür vorherige Mitgliedschaft und Reuse sicher unterscheiden oder den Knoten weiter ausschließen. Ein nachfolgender beweisbarer neuer eigenständiger Reservationsvorgang kann separat eine neue Herkunft etablieren; das ist keine stillschweigende Erlaubnis für alte Childaliases.

`3A09C0(-1)` richtet den Worker über15EC70 →16C9D0 →CreateThread →16C9B0/15ED20 ein.3A0790 wird getrennt über14F770 in den Scheduler eingehängt. IO, Headerflags und3A64F0 laufen damit auf einem Windowsworker; Completionfixup und Cachecallback auf der Schedulerdispatchseite. **Schedulerthread==Trainer-Spielthread ist nicht statisch bewiesen.** Before muss auf jedem möglichen tatsächlichen Callerthread wirken; eine fremde Threadklasse einfach nicht zu zählen wäre falsch.

Vor Ready müssen bereits laufende ungezählte Mutatoren und Altrequests ausgeschlossen oder abgeschlossen sein. Queuehead0 und activeNative0 nach nachträglich installierten Routen beweisen das allein nicht. Die vorhandene STATUS-Drainroutine ist ein Muster, keine unveränderte Motionlösung. `39E340` kann durch150060 →135470 yielden; sie akzeptiert teils state0 und darf weder unter gehaltenem Gate aufgerufen noch als Herkunftsnachweis missverstanden werden.

## Konkrete Providergrenze

Der normale `3A0BD0`-Auftrag wird mit WORD+94=0 initialisiert und wählt damit3F9850. Der alternative3F99E0-Pfad ist in dieser gewöhnlichen Admission ausgeschlossen. Eine spätere unbekannte Änderung des Selectorfelds macht die Historie unzulässig.

Die vollständigen wiederverwendeten Körper3F9850,106700,12F070 und12E5C0 zeigen:3F9850 wartet im Kontrollfluss auf106700 und ruft die Resourceentry-Registrierung auf; diese kann registrierte Handler ausführen. Die frühere Studie `docs/research/drive-provider-binding-20261007/report.md` belegt bereits, dass die Providersemaphore keine Payloadlease oder stabile externe Dateien erzwingt. Sie beweist insbesondere nicht für beliebige Handler, dass diese nach ihrer Rückkehr keine Aliaswrites mehr ausführen.

Daher lautet der enge belastbare Abschluss: **alle in3A0C60 sichtbaren direkten Writes und seine unmittelbaren Callees sind zurückgekehrt, bevor state2 publiziert wird; alle im Consumer sichtbaren Fixups/Callbacks sind zurückgekehrt, bevor dieser die Anfrage entfernt.** Ob ein zugelassener tatsächlicher Provider synchron abgeschlossen und aliasfrei ist, muss dessen konkreter106700/Package-ReadBase- und12E5C0-Handlerpfad liefern. Ein Queue0-Snapshot kann diesen fehlenden Beleg nicht ersetzen. Die Gatestruktur ist damit konkret, aber noch kein hinreichender Liveprovider. Die nächsten Anschlussstellen sind der tatsächliche Readerdispatch und die registrierten Resourcehandler, nicht ein pauschaler Gesamtcache-Review.

## Getrennter Header80-Zusatz zum eingefrorenen Copyvertrag

Der alte Vertrag bleibt unverändert. Die Originalfolge belegt, dass BYTE3-Flag80 des `obj/P_EX100`-Präfixpfads durch normale BAR-Fixups geht. `3A6840` testet `(BYTE3 & C0)==40`, nicht `!=0`; Type9 führt anschließend zu1C5F20, Motion+144, den bekannten kind0/1-Konstruktoren und Payloadpointer+8. Bits10/20 werden in den Metadaten verarbeitet, ohne das gewöhnliche Tabellenlayout zu ersetzen.

Eine weiterhin engere Copierpolicy kann zulassen: `(byte3 & 0x0F)==1 && (byte3 & 0x40)==0`, also Profile01/11/21/31/81/91/A1/B1. Alle bit40-Profile bleiben ausgeschlossen, auch C1, obwohl der native Fixer beiC0 die normale Branchwahl hat. Marker-/Regionwitness-, Elternspan-, Linkwort-, Variant-, Konstruktor-/Payload- und Limitprüfungen bleiben erforderlich. Keine Decoderaufrufe auf ungeprüften Daten und keine native Ressourcenfreigabe durch den Copier.

Die Belegkette zeigt die konkrete Relevanz für den `obj/P_EX100`-Namenspfad. Ohne Livezugriff wird nicht behauptet, dass die momentan geladene Sora-MSET genau diesen Ursprung hat oder eine bestimmte Datei bereits erfolgreich kopiert wurde.

## Unabhängige Bindinggrenze

Dieser Cacheabschluss ersetzt den Actor-/Controller-Lebensdauerschutz nicht. Als konkret bekannte Abhängigkeit folgt im bereits erfassten3C88C0 auf3C8CD0 bei3C8A08/testAL noch der Store3C8A11 `[rbx+28h]=esi` (C40). Ein After des normalen Bindeaufrufs allein schließt daher nicht alle späteren Controlleränderungen seines Callers. Dieser Hinweis stammt aus der vorhandenen Bindingstudie/Root-Nachprüfung; er wird hier nicht als neuer Funktionsclaim gezählt. Ebenso bleiben Decoderrevision, Actorretirement und andere Bindewege separate Gateeingänge.

Keine Speicherallokation/-freigabe, kein Enginecallout und kein Warten unter dem eigentlichen Copy-Gate. Der vorbereitete Kopierer ist die passende getrennte Implementierung; Coreparsing geschieht nach Freigabe an der privaten Kopie. Diese Studie installiert keine dieser Routen und bestätigt keine Live-Scope-Sicherheit.
