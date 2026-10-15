# Actor+1464: Referenzen aus Skript- und Befehlsabläufen

## Ergebnis

**DWORD `Actor+1464` wird nicht ausschließlich von Angriffskontakten verändert.** Neben den bereits belegten Angriffspfaden erhöhen und verringern auch ein Skriptkontext-Konstruktor und Befehlsabläufe diesen Wert. Die Anzeige sollte deshalb **Actor references** beziehungsweise **Actor-Referenzen** heißen. Sie ist weder eine Anzahl aktiver Angriffe noch eine vollständige Aufschlüsselung aller Referenzarten.

Die Aussage beruht auf Originalinstruktionen und konkreter Argumentweitergabe. Die vorhandenen IDA-Namen werden nur als Orientierung verwendet. Es wurde kein nativer Spielcode ausgeführt und kein synthetischer Zählerlauf als Beweis für diese zusätzlichen Writer verwendet.

## Herkunft des Actorarguments im Skriptpfad

Die erneut vollständig geprüfte Routine `3B44D0` verwendet denselben Eingabezeiger sowohl für Actorfelder als auch für die Kontexterzeugung:

1. Nach einer Ressourcenabfrage reicht `3B4525/3B452B` den Eingabe-Actor als zweites Argument an `3E1730` weiter.
2. `3E1730` allokiert 112 Bytes und reicht genau sein zweites Argument als viertes Argument an `3E1240` weiter (`3E1759/3E176F`).
3. `3E1240` speichert dieses vierte Argument in Kontext-QWORD+96 und erhöht bei nichtnull Wert dessen DWORD+1464 (`3E126A/3E13EA`).
4. `3B44D0` speichert den erzeugten Kontext in Actor-QWORD+1456 (`3B4533`). Damit ist dieser konkrete Gegenverweis verbunden; die Gleichheit beruht nicht allein auf einem Funktionsnamen.

Der vollständige Caller `3E1840` liefert einen weiteren konkreten Fall: Für einen temporären Kontext auf dem Stack übernimmt er das Feld+96 des übergebenen Kontexts als viertes Konstruktorargument. Auch dieser Kontext erreicht somit denselben Konstruktor-Inkrementpfad. Der native Konstruktor erhält außerdem die Scriptressource im zweiten und gemeinsame Daten im dritten Argument.

Die vierte Argumentposition ist **nicht** der gemeinsame Datenblock: Kontext+88 erhält Argument3 und verwendet einen eigenen Zähler am Datenblockanfang. Dieser separate Datenzähler darf nicht mit Actor+1464 verwechselt werden.

## Drei sichtbare Releasepfade des Skriptkontexts

| Körper | Konkrete lokale Bedingung und Änderung |
|---|---|
| `3E1A00` | Wenn Kontext-DWORD+56 Bit `0x2` noch nicht gesetzt ist: bei nichtnull Kontext+96 dessen DWORD+1464 dekrementieren; anschließend Bit `0x2` setzen. |
| `3E1410` | Nach Script-, Kindkontext- und Ressourcenbereinigung dieselbe Prüfung, dass Bit `0x2` noch nicht gesetzt ist, dasselbe Dekrement und Setzen des Bits. |
| `3E1C80` | Nach Scriptausführung mit Rückgabe ungleich1 liest der Körper die Flags erneut. Nur bei weiterhin ungesetztem Bit `0x2` erfolgt das Dekrement über nichtnull Kontext+96, danach wird das Bit gesetzt. |

Die Maske 0x2 entspricht Bitindex1. Der gesamte Cleanup 3E1410 ist damit nicht als wiederholbar belegt: Seine Script- und Freigabearbeit läuft vor dem Counterguard.

Das lokale Bit verhindert auf diesen seriellen Pfaden ein weiteres Dekrement, solange es gesetzt bleibt. Das ist keine Atomizitäts- oder Konkurrenzgarantie und erfasst keine sämtlichen Writer dieses Bits. Die Routinen setzen den gespeicherten Zeiger+96 lokal nicht auf null; ein verbleibender Zeiger ist folglich nicht automatisch eine noch gezählte Referenz. Die Arithmetik ist ungesättigte DWORD-Arithmetik.

`3E1C80` behandelt außerdem Kindkontexte. Der hiesige Befund betrifft seinen klaren Releaseblock und dessen Verbindung zur Kontextkonstruktion; er behauptet keine vollständig geschlossene Semantik des gesamten Interpreters oder aller Kindkontextlebenszyklen.

## Befehlsabläufe

`3DB140` arbeitet mit dem eingehenden Objekt und dessen Ressourcen bei +2344. Es sucht zwei BAR-Einträge mit Typ24 beziehungsweise Typ25 und dem aus dem Literal `comd` gebildeten Tag. Die resultierenden Daten und das eingehende Objekt werden an `3B2A90` mit dem Controller aus `globalCurrentPlayer+3536` übergeben. Wenn die Ausführung nach den weiteren Aufrufen das Funktionsende erreicht, setzt der Körper im eingehenden Objekt DWORD+292 Bit `0x800` und erhöht dessen DWORD+1464 (`3DB267/3DB271`).

Wenn Bit `0x800` beim Eintritt schon gesetzt war, ruft `3DB140` zunächst Controller-Slot+40 auf, dekrementiert denselben Objektzähler und löscht das Bit. **Das belegt ein lokales vorheriges Dekrement und späteres Inkrement; es garantiert keine Nettoänderung null über sämtliche undurchsichtigen Callbacks.**

`3DB100` enthält den entsprechenden bedingten Release: Bei gesetztem Objekt+292-Bit `0x800` ruft es Controller-Slot+40 auf, dekrementiert Objekt+1464 und löscht Bit `0x800`. Bei ungesetztem Bit gibt es in diesem Körper kein Zählerdekrement.

Die erneut geprüften Caller `1C9D60` und `1C7E00` reichen jeweils den Inhalt ihres Kontextfelds+8 an diese Routinen weiter: `1C9D60` ruft `3DB140(context+8,4)` auf, `1C7E00` später lokal `3DB100(context+8)`. Ihre Verbindung mit Actor-Operationen ist in der vorhandenen Ownershipstudie dokumentiert. Hier wird die ursprüngliche Herkunft nur bis zu diesem konkreten Kontextfeld verfolgt, nicht für jeden möglichen Aufrufer neu konstruiert. Die tatsächliche zeitliche Folge beider Caller im Spiel ist kein Ergebnis dieser Studie.

## Grenzen der breiteren Suche

Die Root-Abfrage nach dem direkten Displacement `5B8h` enthält 56 Texttreffer. Darunter sind Stackvariablen, Vektorzugriffe und Felder anderer Objekttypen. Sie ist eine Kandidatenliste, keine Liste von 56 Actor-Counterzugriffen. Weitere sichtbare Treffer, etwa in `3E1790`, bleiben außerhalb dieses begrenzten Anschlusses. Es wird weder vollständige Writerabdeckung noch eine feste Zahl aller Referenzquellen behauptet.

Die bisherigen Kontaktbefunde bleiben als Teilmenge gültig: Ein Angriff kann zwei gezählte Verweise auf denselben Actor halten. Die zusätzliche Herkunft aus Kontexten und Befehlsabläufen zeigt jedoch, dass der Gesamtwert breiter ist. Counter0 reicht weiterhin nicht allein als Erlaubnis zur Actorfreigabe; der bereits untersuchte Zulassungspfad prüft weitere Bedingungen.

## Nachweis

- Sechs frisch erfasste vollständige Körper: **409 Instruktionen, 1487 Bytes**.
- Fünf ausdrücklich wiederverwendete vollständige Caller/Adapter: **306 Instruktionen, 1284 Bytes**.
- Insgesamt **elf Körper, 715 Instruktionen, 2771 Körperbytes**, keine getrennten Nichtinstruktionsbytes und 17 ausgewählte Anker.
- Jede ausgewählte Instruktionsgrenze und ihr Mnemonic wurden mit Capstone unabhängig gegen die Original-EXE und die vollständige IDA-Aufnahme verglichen. Die Körpergrößen stimmen mit dem bestehenden Inventar überein.
- Frische Aufnahme bedeutet keine erstmalige Entdeckung. Die zuvor vorhandenen 56 Suchtreffer wurden nicht als vollständige Funktionskörper gezählt.
- Root lieferte vollständige Captures; eine abgeschlossene globale Autoanalyse wird nicht behauptet. Kein Spiel-, Save-, GUI-, Injection- oder Twitch-Test. Keine Produktänderung in dieser Studie.

```powershell
py -3 -B docs/research/actor-reference-counter-20261013/verify.py --check
```

## Übernahme und unabhängige Prüfung

Die sieben Claims wurden unverändert in das gemeinsame Dokumentationsschema übernommen. Elf vollständige Körper dienen als Belege; vier davon haben hier keinen neuen eigenen Claim. Die globale Abdeckung dedupliziert konkrete Funktionsadressen gegen den bisherigen Bestand. Frische Aufnahmen oder vollständige Körper bedeuten weder erstmalige Erkenntnis noch vollständige Semantik.

`evidence.zip` enthält alle 22 Dateien der eingefrorenen Studie unter `study/` und die fünf Dateien der unabhängigen Prüfung unter `review/`, jeweils bytegenau einschließlich der Manifeste. `provenance.json` enthält jeden Dateihash und beide Manifestpins. `evidence.json` normalisiert ausschließlich die vorhandenen Instruktionslisten und die Darstellung der Originalbytes; die Seiten sind keine neuen IDA-Abfragen.

Die unabhängige Prüfung bestätigt sämtliche 715 Instruktionen/2771 Körperbytes, 42 konkrete Operandenanker und die fünf Originalbytes des bereits referenzierten `comd`-Literals. Alle sieben begrenzten Claims wurden akzeptiert. Der lokale Prüfer führt weder archivierte Skripte noch nativen Spielcode oder eine semantische VM aus.
