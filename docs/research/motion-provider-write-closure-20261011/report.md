# Gewöhnlicher MSET-Provider: Schreibabschluss und gespeicherte Aliase

## Ergebnis

Für den unveränderten Retail-Startpfad lässt sich die bisher offene Handlerfrage konkret eingrenzen: `14F1E0` übergibt `RCX=0` an `12EE70`; diese Funktion enthält den einzigen direkten Schreibzugriff auf die Handlerliste `8AEF38` in den frischen, ungekürzten Xrefs. `12E5C0` überspringt bei null die gesamte Handlerauswahl. Der beim Konstruktor gesetzte Handlerindex `-1` bleibt erhalten und überspringt auch den Tabellen-Unloadcallback. Für diesen Pfad muss daher kein unbekannter registrierter MSET-Handler als zusätzlicher asynchroner Writer angenommen werden.

`107620` liest über den original importierten CRT-`_read` und führt gegebenenfalls Präfixtransformation und Dekompression innerhalb seiner Aufrufkette aus. Seine sichtbaren Zielzugriffe enden vor der Rückkehr. Das gilt unter den normalen CRT-/Codec-Verträgen; deren gesamte Implementierungen wurden hier nicht auditiert. Der Rückgabewert ist in allen drei Zweigen die nominelle Paketlänge. Er belegt weder einen vollständigen Read noch erfolgreiche Dekompression.

**Die Ressource wird dadurch nicht aliasfrei.** `ResourceEntry+16` und `+1624` behalten die Primary-Adresse. Der nun vollständig erfasste `12E180` kann einen Entry aus der Liste lösen und ihn mit beiden unveränderten Aliaszeigern zurückgeben. Eine leere Liste ist deshalb kein Freigabe- oder Schreibabschlussbeweis. Die Studie schließt die konkrete registrierte Handlerlücke, aber weder indirekte/externe Writer noch sämtliche späteren Verbraucher eines ausgeliehenen Entry-Zeigers.

## Belegter Pfad

1. Der gewöhnliche Cacheauftrag mit Selector `WORD+94=0` wählt laut eingefrorener Cache-Vorstudie `3F9850`. Für diese Ergänzung bleiben Mode3, gewöhnliche Kind0-Reservation und der `obj/P_EX100`-MSET-Pfad Voraussetzungen. Es wird kein aktuell geladenes Spielobjekt untersucht.
2. `3F9850` ruft zuerst die Overlap-Retirementfunktion `12EF30(destination,destination+16,0)`. Danach hält es die bekannte Providersemaphore um `106700`, aber nicht um die gesamte Ressourcenlebensdauer.
3. `106700` wählt ein Paket mit `106940`, ruft direkt `107620` und registriert bei seinem nominellen Erfolg über `12F070(name RCX,length EDX,destination R8)`.
4. `107620` hat drei Pfade: Raw-Read direkt in das Ziel; gespeicherter/präfixtransformierter Read direkt ins Ziel; oder Read in einen temporären Puffer, Präfixtransformation und Codec-Aufruf ins Ziel. Der temporäre Puffer wird vor Rückkehr freigegeben. `4696F0` legt den Codec-Kontext lokal auf dem Stack an und ruft nach erfolgreicher Initialisierung auf beiden Ergebniswegen Streamcleanup auf. Die beobachtete Versionszeichenfolge ist `1.2.5`; daraus folgt kein vollständiger Identitätsnachweis aller Codec-Helfer.
5. `12E5C0` konstruiert und verkettet den ResourceEntry. Bei der tatsächlich null initialisierten Handlerliste wird kein Tabellen-Loadcallback aufgerufen. `3F9850` nimmt in Mode3 den bereits erzeugten `currentEntry` und schreibt dessen kodierten Zeiger in die BAR-Metadaten, bevor es zurückkehrt.
6. Erst danach folgen die getrennt belegten Worker-/Consumerfixups. Der Original-Switch von `3A64F0` schickt Type17 in rekursive BAR-Vorbereitung. Type9 nimmt den Defaultpfad ohne speziellen Replacementcallback. Die spätere Type9-Konstruktion/Fixup aus der Cache-Vorstudie bleibt ein Writer und wird dadurch nicht aus dem Gate entfernt.

Die Microsoft-Dokumentation zu [`_read`](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/read?view=msvc-170) beschreibt die Rückgabe der tatsächlich gelesenen Menge, einschließlich kurzer Reads und Fehler. Das Original lädt diesen Wert unmittelbar vor der Rückkehr durch `package+300` neu. Die vier gezielten Ergebnisfälle veranschaulichen genau diese Überschreibung; sie führen keine Dateioperation aus. Der allgemeine [zlib-Vertrag](https://zlib.net/manual.html) beschreibt die In-Process-Streamarbeit; das aktuelle Handbuch ist keine Quellenidentifizierung der beobachteten älteren Binärversion.

## Aliase und spätere Zustandswechsel

| Funktion | Tatsächliches Verhalten | Bedeutung für Read-Admission |
|---|---|---|
| `12CD80` | Speichert Primary in Entry+16/+1624, Längen in +24/+1600. | Registrierung ist kein Besitztransfer der Primary-Reservation. |
| `12DF90` → `39E690` | Findet Entry anhand Name und exakter alter Primary-Adresse; Relocation aktualisiert beide Aliasfelder vor der Bytekopie. | Bereits belegter Cache-Mutator muss vor der ersten Änderung widerrufen. |
| `12E180` | Sucht Primary-Intervall; bei EDX!=0 entfernt es den Listenknoten und gibt ihn lebend zurück. | Detach widerruft Registryprovenienz. Weiterhin gespeicherte Aliase sind nicht über Head/Count auffindbar. |
| `12E460`, `12EF80` | Optionaler Tabellen-Unloadcallback, Unlink und Entrydestruktion. Bei Index -1 kein Tabellen-Unloadcallback. | Vor Retirement widerrufen; negative Handlerindexprüfung ersetzt keine übrige Lebensdauergrenze. |
| `12EEA0` | Kann einen separat übergebenen Callercallback vor Retirement aufrufen. | Dieser Callback wird durch die null Handlerliste nicht ausgeschlossen. Abdeckung der ganzen Routine oder ausdrücklicher Ausschluss erforderlich. |
| `12D8E0` / `12D5A0` | Replacementobjekte zerstören, Metadaten an bedingten Disk-Nametablewriter geben, Entry selbst freigeben. | Kein neuer Read-Scope und kein Beleg, dass alle externen Primäraliasnutzer erloschen sind. |
| `12E860`, `12EA20` | Primärliste lösen und Kontext freigeben bzw. neuen Kontext publizieren. | Kontextwechsel widerruft alle darauf beruhenden Zeugen. |
| `12EB70`, `12E980` | RootFileData-/Dependency-Namen eintragen bzw. finden. | In den erfassten Bodies kein verdeckter Primary-Reload. |
| `12DDA0`, `12DE20`, `12E230`, `12E310` | Lookups nach Replacementspan, normalisiertem Namen, 16-Byte-Hash oder Replacementtyp/-name. | Rückgabe ausgeliehener Entry-Zeiger; downstream Nutzung wird damit nicht begrenzt. |

Alle 29 direkten Xrefs von `8AEF30` sind eingeordnet. 28 liegen in vollständig enthaltenen Bodies. Der übrige Zugriff `3F9B15` gehört zum ausdrücklich ausgeschlossenen alternativen Reader `3F99E0`; seine einzelne Instruktion wurde ebenfalls aus dem Original dekodiert. Von den direkten Zugriffen schreiben nur Kontextkonstruktor/-destruktor den Globalwert selbst. Das ist eine Aussage über direkte globale Referenzen, keine vollständige Suche nach indirekten Stores durch zuvor geladene Zeiger.

## Konkrete nächste Implementierungsgrenze

Der vorbereitete private Kopierer kann weiterhin verwendet werden. Ein Liveprovider muss davor die bestehende Cache-/Bindinggeschichte und die in [contract.md](contract.md) bezeichneten Voraussetzungen führen. Für unveränderte Mode3-Provenienz kann die allgemeine unbekannte Tabellen-Handlerbedingung durch den konkreten Nulltabellen-/Index-Nachweis ersetzt werden. Ein einmaliger später Nullsnapshot reicht dafür nicht, wenn vorherige Registrierung oder fremde Provider nicht ausgeschlossen sind.

Die jetzt konkrete offene Grenze ist **die Herkunft und vollständige Mutationserfassung von retained Entry-/Primary-Aliasen**, einschließlich Detach/Retirement/Kontextwechsel. Das ist nicht mit der Providersemaphore, Refcount, Queuehead0 oder einem erfolgreichen nominellen Read gelöst. Diese Studie installiert keine Hooks, behauptet keine beobachtete Bootstrapgeschichte und erteilt kein Live-Scope-Go.

## Reproduktion und Umfang

```powershell
py -3 -B artifacts/motion-provider-write-closure-20261011/verify.py --check
py -3 -B artifacts/motion-provider-write-closure-20261011/freeze.py --check
```

`prepare.py` reproduziert die Normalisierung aus gepinnten älteren Evidence-Dateien und unveränderten Root-Captures. 33 vollständige Funktionskörper: 10 frische Captures, 23 ausdrücklich wiederverwendete. Originalvergleich: 12.509 Extentbytes, 3.189 Instruktionen und 12.278 Instruktionsbytes. Die übrigen 231 Bytes sind die ausgewiesenen NOP-/Switchtabellentails der drei BAR-Funktionen. 47 Anker, 10 begrenzte Claims, 44 auflösbare Referenzen. 16 gezielte Fälle, davon 335 interpretierte Originalinstruktionen; keine umfangreichen Sweepzahlen und keine nativen Spielaufrufe.

IDA meldete in dieser Arbeitsrunde laut Root weiterhin `auto_analysis_ready=false`. Vollständige Pagination bedeutet vollständige gelieferte Bodies, nicht abgeschlossene globale Autoanalyse. Die Originaldatei ist bytegeprüft. Produkt, IDB, Pakete, globale Forschungsdateien und Spielstände wurden nicht verändert.
