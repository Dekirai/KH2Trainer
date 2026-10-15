# Motioncache: Ladeabschluss und gehaltener ReadScope

## Ergebnis

**WORD-Referenzzähler+2 schützt im geprüften Planungs-/Relocationpfad nicht vor Byteverschiebung.** Ein Cacheknoten kann +88==+96 haben, während sein Read noch läuft. Der Worker setzt Requeststate2 nach seinen sichtbaren Stores und der Rückkehr seiner Hilfsfunktionen; der Consumer fixiert das BAR, ruft die Cachecompletion auf und entfernt erst danach den Request.

Damit ist eine konkrete Async-Busy-Grenze belegt. **Queue0 + AfterConsumer schließt jedoch nur die beobachtete Worker-/Consumerfolge.** Dass der tatsächliche3F9850/106700-Provider und die12F070→12E5C0-Resourcehandler nach Rückkehr keine späteren Aliaswrites ausführen, bleibt eine ausdrückliche zusätzliche Voraussetzung. Diese Studie gibt daher noch keinen Live-ReadScope frei.

Der zweite unmittelbar umsetzbare Befund ist unabhängig davon: Headerprofil80 des `obj/P_EX100`-Pfads verwendet die normale Pointerfixup-/Type9-Konstruktorkette. Der Copier kann dieses Profil unter unveränderten Bounds- und Herkunftsprüfungen zulassen. Die vorgeschlagene Trainerpolicy verwirft weiterhin jedes bit40-Profil. Der vorher eingefrorene Vertrag wurde nicht geändert.

## Belege

- **44 vollständige Körper:43 Funktionskörper und ein separater Callback-Codebereich39DEE0.**7 frische Root-Proxyaufnahmen,37 ausdrücklich aus früheren Studien wiederverwendete Körper. Frische Aufnahme bedeutet keinen Anspruch auf erstmalige Funktionsentdeckung; die Threadkette war bereits in der Providerstudie beschrieben.
- **2.754 disassemblierte Instruktionen /10.479 Bereichsbytes**, davon10.168 Instruktionsbytes und311 als nicht dargestellte Instruktionsbytes separat ausgegebene Padding-/Tabellenbereiche. Alle Bereichsbytes gegen die Original-EXE verglichen; jede dargestellte Instruktion zusätzlich mit Capstone dekodiert.
- **55 konkrete ASM-Anker,10 begrenzte Claims,63 auflösbare Claimbelege**. Der Beweis über fehlende WORD+2-Zugriffe prüft beide vollständigen Planungs-/Movebodies.
- Kleine Modelle:7 Ereignisfolgen mit20 Zulassungszeitpunkten sowie16 Headerprofile. Sie zeigen die relevanten Gegenbeispiele, sind weder native Ausführung noch Threadsicherheitstests.
- Original-SHA256 `9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed`.

Die vollständige Ereignistabelle, Fehler-/Cancelgrenze, Herkunftsentscheidung und die konkrete offene Providerabhängigkeit stehen in [contract.md](contract.md). `39DEE0` ist ausdrücklich `code_ranges`-Evidenz und wird nicht als Inventarfunktion gezählt. `report.json` verwendet die kanonischen Felder `addr/Finding/Evidence/Limitations`. Die rohen Proxyantworten bleiben unverändert; bestehende Studien sind per SHA256 gepinnt.

## Praktische Konsequenzen

1. Bei beobachtetem Submit bleibt ein Scope bis nach der gesamten Completionfolge geschlossen. Callbackreturn oder gleiche Basiszeiger genügen nicht. Fehler0 setzt stateFF; unterdrückter Start kann state1 ohne Request hinterlassen; kein belegter Cancelpfad macht das zu Erfolg.
2. Für gewöhnliche MSET müssen Neuanlage und Reuse unterschieden werden. Vorhandene Kind2-Childaliases dürfen nicht durch einen state3-Snapshot als eigene Reservation gelten.
3. Die tatsächlichen Bytewriter laufen auf einem Windowsworker; der Completioncallback wird getrennt im Scheduler dispatcht. Dessen Gleichheit mit dem Bridge-Spielthread ist nicht aus statischen Belegen abzuleiten.
4. Before/After brauchen einen gemeinsamen Gate mit verschachtelten aktiven Aufrufen und geschlossener Bootstrapgeschichte. Kein Lock über Originale oder native Wait-/Yieldfunktionen. Der vorbereitete Copier vermeidet Heaparbeit während des gehaltenen Lesebereichs; dies ist eine getrennte Implementierung.
5. Die noch offene Providergrenze ist konkret:3F9850→106700/Package-ReadBase sowie12F070→12E5C0 und die wirklich registrierten Handler. Der alternative3F99E0-Reader ist ausgeschlossen. Ein allgemeiner Gesamtanalyseauftrag ist daraus nicht abzuleiten.

Die Actor-/Bindinggeschichte bleibt separat. Insbesondere kann der Caller3C88C0 nach dem normalen3C8CD0-Return noch C40 schreiben (3C8A11). Die Normalbindroute allein hält daher keinen vollständigen Controllerleseschutz.

## Provenienz und Reproduktion

Die vorhandene IDB wurde nur über Root gelesen; kein eigener Worker gestartet, keine Autoanalyse erzwungen und keine IDB geändert. Root meldete Session28e14b48/PID71984. Die beigefügte rohe Healthantwort bestätigt Statusok, Hex-Raysbereit und **auto_analysis_ready=false**; sie enthält selbst keine Session-ID/PID. Diese Werte sind als mitgeteilte Proxyprovenienz getrennt dokumentiert.

```powershell
py -3 -B artifacts/motion-cache-read-scope-20261011/verify.py --check
py -3 -B artifacts/motion-cache-read-scope-20261011/freeze.py --check
```

`prepare.py` normalisiert nur die vorhandenen vollständigen Evidencekörper und frischen Rohcaptures. `verify.py --write` regeneriert die abgeleiteten Anker-/Modell-/Verifikationsdateien; Standard/--check prüft sie ohne Änderungen. `freeze.py --check` prüft die exakte rekursive Datei- und Hashmenge; nur das eigene oberste Manifest ist ausgeschlossen. Pfade werden aus dem nächsten Repoancestor aufgelöst, sodass die Studie auch unter docs/research reproduzierbar bleibt.

Keine Produkt-/Paketdatei geändert, kein Spiel gestartet oder gelesen, keine Injection und keine native Originalfunktion ausgeführt. Eine read-only Originaldateiprüfung ersetzt keine Laufzeitvalidierung.
