# ATTACK_OBJ: Herkunft der Actor-Verweise und Cleanup

## Ergebnis

Die offene Herkunft aus der vorigen Kontaktstudie ist konkret aufgelöst: **Der Callbackempfänger muss nicht der ursprüngliche Owner sein.** Der Basiskonstruktor `3CF830` schreibt zunächst denselben übergebenen Actor in die komprimierten Felder `+12` und `+16`. `+20` erhält den separat übergebenen Actor. Wenn Parameterbyte `+8` den Wert 1 hat, ersetzt der Konstruktor allein `+16` durch den globalen Zeiger `2A105D0`.

Die sichtbare Zählerführung folgt `+12` und `+20`: Der Konstruktor erhöht deren DWORD `+1464`, der zu `ATTACK_OBJ` gehörende Cleanup senkt beide wieder. Für den gegebenenfalls abweichenden `+16`-Empfänger gibt es in diesen Körpern keine eigene Zähleränderung. Stimmen die beiden gezählten Actor-Adressen überein, erfolgen zwei Änderungen. Die Arithmetik ist nicht gesättigt; Über- und Unterlauf bleiben DWORD-Arithmetik.

Das schließt die frühere Fixture-Lücke bei der Herkunft, **beweist aber keine allgemeine Lebensdauergarantie**. Der konkrete Zusammenhang zwischen Zähler `+1464` und einer späteren Actorfreigabe bleibt offen.

## Die drei Verweise

| Feld | Konkrete Herkunft und Verwendung |
|---|---|
| `+12` | `Encode(arg2)`; die hier beobachtete ursprüngliche Actorreferenz wird erhöht und beim Cleanup gesenkt. |
| `+16` | Zunächst `Encode(arg2)`, bei Parameterbyte `+8 == 1` durch `Encode(global2A105D0)` ersetzt. Die Vorstudie verfolgt genau diesen Wert bis zum virtuellen Callback in `3D1960`. |
| `+20` | `Encode(arg3)`; separat gezählte Referenz und Geometriequelle des erfassten abgeleiteten Pfads. Ihre Gleichheit mit `arg2` ist nicht vorausgesetzt. |

`+40` ist eine weitere abgeleitete Referenz: zuerst `arg2+128`, bei Parameterflag `0x02` das Ergebnis von `3D8A40`, sonst bei Flag `0x08` `QWORD(receiver+688)+128`. Der bereits erfasste abgeleitete Konstruktor `40F1C0` ersetzt sie ohne beide Flags durch `Decode(+20)+128`. Diese Zuweisungen beweisen die Herkunft; sie machen die Zieladressen nicht automatisch gültig. Die genannten Overridepfade weisen einen dekodierten Nullzeiger nicht lokal zurück.

## Tatsächlicher Cleanup des abgeleiteten Objekts

Die originale `ATTACK_OBJ`-Vtable `5CE6C0` enthält in Slot 0 `40F4C0`. Diese Routine sowie der kürzere Nichtlöschpfad `40F4A0` löschen zuerst die äußere Zelle hinter `QWORD(object+720)`. Der Zeiger stammt aus Argument 5 von `40F1C0`; ein lokaler Nullguard fehlt. Erst danach folgt der gemeinsame Basiscall `3CFB10`.

`3CFB10` führt in dieser Reihenfolge aus:

1. Die Zähler hinter `+12` und `+20` dekrementieren.
2. Das Objekt aus der Kontaktliste `2A24B40/2A24B48` mit Next-Feld `+196` entfernen; Kopf und Ende anpassen; den entfernten Next-Verweis auf kodiertes Null setzen.
3. Ohne Objektmaske `0x400`: die durch `3D2E50` gelieferten Records bearbeiten, ein Kontakt-ID-Bit bei `record+3224` löschen und `record+3320` nur bei exakter Zeigergleichheit leeren. Dasselbe ID-Bit aus den verbleibenden Kontakten löschen und `3CF3A0(object+32)` aufrufen.
4. Den eingebetteten Knoten `object+60` über `3CF190` aus einer zweiten Liste entfernen.

Maske `0x400` überspringt nur den Sweep und die IDfreigabe. Zählerdekremente und beide Listenentfernungen bleiben erhalten. Der Konstruktor setzt diese Maske bei einem explizit gelieferten nichtnegativen IDargument.

Die drei Actorfelder `+12/+16/+20` bleiben durch die lokalen Cleanupstores unverändert. Der Cleanup setzt somit nicht jede erreichbare Referenz auf Null. Außerdem setzen beide Listenroutinen gültige Mitgliedschaft voraus; sie haben keinen belegten sicheren Pfad für ein bereits entferntes oder unbekanntes Objekt.

`3CF7F0` ist ein Bithelfer: `id = DWORD(contact+32)`, Wortadresse `table+4+4*(id>>5)`, zu löschendes Bit `id&31`. Er liefert die Löschmaske zurück. Eine Tabellenlänge oder ein lokaler Bereichstest ist nicht vorhanden.

Der separate Basis-Vtableslot `5C5E78 → 3CFCB0` enthält eine entsprechende löschende Variante. Er ist nicht der abgeleitete `ATTACK_OBJ`-Pfad. Die beiden löschenden Wrapper geben den Objektzeiger zurück und können abhängig von den Löschflags `152570` oder `nullsub_1` aufrufen; die Größenargumente sind 200 beim Basisobjekt und 728 beim abgeleiteten Objekt. Der Nichtlöschpfad reicht das rohe Ergebnis der eingebetteten Listenentfernung weiter.

## Grenzen und nächster konkreter Anschluss

- Belegt sind die anfänglichen Stores, genau eine parameterabhängige Ersetzung von `+16` und die ausgewählten Cleanups. Spätere Ersatzwriter außerhalb dieser Körper sind nicht vollständig erfasst.
- Zähler `+1464` wird durch Originalinstruktionen geändert. Ob und wann er Actorfreigabe verhindert, ist der nächste konkrete Anschluss. Der globale Ersatzempfänger und die äußere Ownerzelle brauchen ebenfalls einen eigenen Lebensdauerbeleg.
- Die Actoriteration, IDfreigabe, Allocatoraufrufe und weitere Konstruktorhelfer bleiben externe Grenzen. Aus dem Sweep folgt keine Garantie, dass alle externen Pointer verschwinden.
- `3D1960` bleibt eine Kontaktreaktion mit Callback. Diese Studie gibt keine Teleport- oder Platzierungsfunktion frei.

## Reproduktion

Sieben frische vollständige IDA-Aufnahmen plus drei ausdrücklich wiederverwendete Körper ergeben **3.786 Originalbytes und 867 Instruktionen**. Zwei originale Vtablebereiche liefern weitere 64 Datenbytes. Alle zehn Körper stimmen mit dem bisherigen Funktionsinventar überein; es wird keine zusätzliche Range als Funktion gezählt. Frische Aufnahme bedeutet nicht zuvor unbekannte Funktion.

**115 synthetische Originalinstruktionsfälle** prüfen Feldherkunft, Empfängerersatz, aliasierende Actorargumente, DWORD-Wrap, Kopf/Mitte/Ende beider Listen, Maske `0x400`, Löschflags und Bitgrenzen. Sie umfassen 14.761 interpretierte Schritte und 449 verschiedene ausgeführte Instruktionen.

Die Ptr32-Zuordnung, Actoriteration, Allokatorgrenzen und der eingebettete Listeninitializer sind ausdrücklich benannte Fixtures. Der Interpreter weist Speicherzugriffe außerhalb der zugeteilten Fixturebereiche zurück; das ist eine Modelleigenschaft und kein bewiesener Spielschutz. Die einzigen Änderungen am gepinnten Interpreter ergänzen `NOT` und registerbasiertes `BTS`. Es gibt keine native Ausführung und keinen Konkurrenz- oder Lebensdauerbeweis.

```powershell
py -3 -B artifacts/attack-object-ownership-20261011/verify.py --check
```

Die Aufnahmen stammen von Root aus der vorhandenen Sitzung `28e14b48`; `auto_analysis_ready=false` blieb unverändert. Keine Produkt-, globale Forschungs- oder Paketdatei wurde geändert. Es gab keine Spiel-, GUI-, Attach-, Injection-, Save- oder Twitch-Aktion.
