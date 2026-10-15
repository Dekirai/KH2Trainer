# Ergänzung zur gewöhnlichen Provider-Admission

Diese Ergänzung präzisiert die Providerbedingung aus der eingefrorenen Cache-Studie. Sie ist eine Anforderung an einen künftigen Liveprovider, keine implementierte Lease.

## Zulässiger enger Ursprung

- Hashgeprüfter ursprünglicher Retail-Reader, beobachteter gewöhnlicher Kind0-Cacheauftrag, unveränderter Selector0, Mode3 und bekannte Reservation. Alternate3F99E0, loose/modifizierte Provider, unbekannte Altrequests und beliebige externe Handler bleiben ausgeschlossen.
- Die tatsächlich beobachtete Konfiguration muss zum originalen `14F1E0 → 12EE70(RCX=0)` passen. `8AEF38==0` und Entry+1612==-1 sind Konsistenzbedingungen, kein rückwirkender Beweis der Entstehungsgeschichte.
- `3F9850`/`106700`/`107620` müssen mit normaler Rückkehr abgeschlossen sein. Abweichende Calltargets, Faults, ungeklärte Helperausführung oder unbekannter Kontextwechsel schließen Admission aus. Normale CRT-/Codec-Semantik ist ausdrücklich vorausgesetzt. Die nominelle Paketlänge ist kein Validitätssignal; Kopiergrenzen stammen weiterhin aus belegter Reservation und begrenzten BAR-Childspannen, Formatprüfung aus der privaten Kopie.
- Der bisherige Cache-Gate bleibt erforderlich: Der verkettete Request bleibt über Workerread, Vorbereitung, Completionfixup und Callback bis zum endgültigen Unlink busy. Kein Copy während ausstehender Requests oder aktiver erfasster Mutatoren. Readerreturn beendet die asynchrone Cachephase nicht.

## Zusätzliche konkrete Widerrufspunkte

Alle vorhandenen Cache-/Binding-/Decoder-/Actor-Ereignisse bleiben bestehen. Die folgende Liste ergänzt die nun sichtbaren Provider-/Registryereignisse; sie behauptet keine globale Vollständigkeit für beliebige Aliaskonsumenten.

| Ereignis | Before / Abschluss |
|---|---|
| Reader oder direktes Register `3F9850`, `106700`, `12F070`/`12E5C0` | Vor Zielwrite oder Registryveränderung widerrufen; nested Aufrufe müssen bis zum äußersten After aktiv bleiben. Direkte externe Caller müssen entweder erfasst oder ausgeschlossen sein. |
| Tabellenkonfiguration `12EE70` | Vor Änderung Herkunft widerrufen. Nichtnull-Handlerkonfiguration beendet diese enge Admission. |
| Primary-Detach `12E180` | Konservativ bei jedem Eintritt widerrufen, oder belegten EDX!=0-Zweig berücksichtigen; beide Primary-Aliase können nach Return weiterleben. |
| Retirement `12E460`, `12EEA0`, `12EF30`, `12EF80` | Vor Handler-/Callercallback und Unlink widerrufen. Eine allein nachträgliche Listenbeobachtung ist zu spät. Vollständig geschützte äußere Caller können geschachtelte Routen abdecken; unbewiesene direkte Caller nicht. |
| Kontext `12E860`, `12EA20` | Vor Linkclears/Free bzw. Veröffentlichung widerrufen. Neue Adresse oder gleiche wiederverwendete Adresse verlangt neue Kontextära. |
| Relocation `39E690` | Bestehende Cache-Route deckt Updates von Entry+16/+1624 und nachfolgende Kopie/Fixups ab. |

Für den kleinsten globalen Prototyp können diese Ereignisse jede gewöhnliche Admission widerrufen. Ein etwaiger späterer selektiver Ansatz braucht eine belegte Zuordnung zum exakten Primarybereich; ein Name oder ResourceEntrypointer allein reicht nicht.

## Was noch verhindert, daraus einen vollständigen Liveprovider abzuleiten

`12E180` beweist unmittelbar, dass Registrymitgliedschaft und Aliaslebensdauer auseinanderfallen. Auch die anderen Lookups geben Entrypointer zurück. Die vorliegende Xrefmenge begrenzt direkte Zugriffe auf die Globals, nicht spätere indirekte Nutzung schon ausgegebener Zeiger. Ohne belegte Abdeckung/Ausschluss dieser Nutzung und nachgewiesenen Bootstrap/Drain darf ein gehaltenes ReadScope keine globale Schreibfreiheit behaupten.

Der normale Tabellenhandler ist nun konkret ausgeschlossen. Die verbleibende Arbeit ist deshalb ein tatsächlicher Herkunfts- und Ereignisnachweis für die zugelassene Reservation, einschließlich der genannten Detach-/Retirement-/Kontextpfade sowie der schon bekannten Binding-/Decoder-/Actorgrenzen. Es ist kein Anlass, einen beliebigen neuen Provider oder einen allgemeingültigen Ressourcenschutz zu erfinden. Der jetzige Stand erlaubt weiterhin nur private Gate-/Copyfixtures und Parsing an privaten Kopien.
