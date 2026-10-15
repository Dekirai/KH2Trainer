# Begrenzte Kopie einer bereits gebundenen nativen Motion

## Ergebnis und Autorität

Ein Kopierer kann die aktuelle Motion über zwei residente BAR-Tabellen bestimmen und ausschließlich ihre Payload in privaten Speicher kopieren. Diese Funktion darf nur innerhalb eines vom Aufrufer belegten synchronen Ressourcen-Lesebereichs laufen. Lesbare Seiten, gleiche Pointer und frei übergebene Token belegen diesen Bereich nicht.

Die unten genannten nativen Regeln sind aus bestehenden, vollständigen Original-ASM-Belegen wiederverwendet. Fünf frische IDA-Captures dienen als Gegenprüfung; sie erhalten keinen Neuheitsclaim. Die strengeren Admission-Regeln sind Produktentscheidungen. Sie geben weder Tiny/Giant noch einen installierten Runtime-Consumer frei. v0.12.19 bleibt unverändert.

## 1. Residente BAR-Felder

| Struktur/Feld | Native Verwendung |
|---|---|
| BAR+0..+3 | Drei BAR-Magicbytes und Versions-/Flagbyte. Die hier geprüfte Find-Funktion validiert diese Bytes nicht. Fixup prüft die Spezialklasse `BYTE+3 & 0xC0`; Bits4..5 werden mit Metadaten bei +12 verbunden. |
| BAR+4 | **Signed Int32** Anzahl; Find liefert für `count <= 0` null. |
| BAR+8 | **UInt32 gepackter Selfpointer** nach Fixup; vor Fixup null. Kein Dateioffset nach abgeschlossener Fixierung. |
| BAR+12 | DWORD mit gemischten Flags/Metadaten. `BYTE+12 & 1` wählt die Variantengruppe, `&2` kann den Blendparameter löschen. **Keine Länge**. |
| BAR+16 | Beginn der Tabelle; jeder Eintrag belegt genau16 Bytes. |
| Entry+0 | UInt16 Typ. |
| Entry+2 | UInt16 Rohfeld. Die geprüften Fixup-/Relocationpfade prüfen nur `BYTE+2 &1` und überspringen dann die typbezogene Rekursion/Konstruktion. Keine belegte generische Linkauflösung. |
| Entry+4 | UInt32 Tag. FindByType und der normale Motionpfad ignorieren ihn. |
| Entry+8 | UInt32 gepackter Datenpointer nach Fixup; beim initialen Fixup war dies ein **unsigned** Offset relativ zum Container. |
| Entry+12 | UInt32 deklarierte Eintragslänge; null wird im Fixup gesondert behandelt. Diese Länge ist keine äußere Allokationsgarantie. |

`3A6840` speichert packedSelf bei +8 und ersetzt für Einträge mit nichtnull Länge den bisherigen unsigned Offset durch Encode(self+offset). `3A6120` verschiebt bereits gepackte Eintragsziele um `neuerSelf-alterSelf`; `3A62B0` setzt den Selfpointer und führt ausgewählte Typnachbehandlungen aus. Fixierung, Relocation und Ressourcenwechsel müssen durch den äußeren Vertrag ausgeschlossen sein.

## 2. Packed Pointer

Native Nullhülle `4AD270`: Eingabe ECX==0 liefert RAX==0; sonst Sprung zu `4AD3F0`. Dort:

```
index = (encoded & 0x7fffffff) >> 25;   // immer 0..63
offset = encoded & 0x01ffffff;
pointer = regionTable[index] | offset;
regionTable = imageBase + 0x2B0D720;   // 64 QWORDs
```

Der native Decoder ignoriert Markerbit31 und ruft einen Lazy-Initialisierer auf. Der Kopierer soll **keine** native Decode-/Encode-/Fixupfunktion aufrufen. Der Encoder legt 32-MiB-ausgerichtete Regionsbasen ab und setzt Markerbit31; ein all-ones Tabelleneintrag ist der native freie Zustand.

Konservative eigene Decode-Regeln: encoded!=0; Markerbit31 gesetzt; ausgewählter Tabelleneintrag weder0 noch UINT64_MAX; seine unteren25 Bits null; `base | offset` und alle Folgespannen innerhalb des zugelassenen Adressbereichs. Die benötigten Regionseinträge sind Teil des vor/nach verglichenen Witness. Das ist zusätzliche Trainerpolicy, keine native Markerprüfung. Der Witness ersetzt keinen Schutz vor konkurrierender Freigabe oder unverändertem Release→Reuse.

## 3. Exakte Auswahl, ID und Variante

- `3C8CD0(C, resolvedId, blend, start)` erhält C in RCX, ID als signed EDX, float in XMM2/XMM3 und liefert Erfolg in AL. Er schreibt zuerst `C+328=C+16+128`, löscht C+344/+352 und sucht nur bei nichtnegativer ID und nichtnull C+0.
- Er sucht C+8 zuerst, fällt bei fehlendem Ergebnis auf C+0 zurück. **C+8==0 ist daher eine engere Kopiererpolicy.**
- `40D7A0(BAR,id)` ruft `3A6420(BAR,-1,id)`. Bei Typ==-1 wird jede Tabellenzeile gezählt: **id ist der nullbasierte physische Tabellenindex über alle Typen**, kein Name, Tag oder Index nur der Type17-Einträge.
- `3A6420(BAR,type,occurrence)` erhält RCX/EDX/R8D, liefert Entry* in RAX. Nur bei passendem Typ (oder -1) wird occurrence dekrementiert. Negative occurrence wird nicht als Sondermodus behandelt. Die Routine kennt keinen äußeren Bereich und prüft weder Linkfeld noch Pointer noch Länge.
- `3C8A40(C,selectedBAR,blend,start)` nimmt anschließend **den ersten Type9-Eintrag** (`Find(type=9,occurrence=0)`), dekodiert dessen +8 und speichert ihn in C+24. Es darf bei ungültigem erstem Type9 nicht ein späterer gewählt werden. Trigger Type16 ist ein getrennter Lookup und gehört nicht zur Payloadkopie.
- Nach erfolgreichem Normalbind schreibt `3C8CD0` C+44=resolvedId und C+48 entweder `resolvedId%4` (wenn primäres HeaderBYTE+12 mask1) oder -1. Für die zugelassene nichtnegative ID entspricht Modulo den unteren zwei Bits.
- C+40 ist die logische ID. `3C88C0` lässt sie über `3C7C50` auflösen und speichert sie erst nach erfolgreicher Auswahl. Der Mapper kann `4*logical+variant` verwenden, priorisiert vier Varianten abhängig vom damaligen Actorzustand und prüft jeweils Override vor Primärbank. Ein Kopierer darf diese historische Wahl **nicht anhand des heutigen Actorzustands neu treffen**. Er folgt der beobachteten, bereits gebundenen C+44 und prüft C+24 sowie C+48. C+40 wird nur als Witness übernommen; auch -1 kann nach direktem Normalbind vorkommen.

## 4. Type9 und innere Spanne

`1C5F20` setzt RDX=Motion+144 und liest dort den DWORD-Kind. Kind0 springt zum Prototype0-Konstruktor, Kind1 zum RAW-Konstruktor, andere Werte liefern null. Der gemeinsame Konstruktor `1C3840` schreibt Motion+8=Payload, vier QWORD-Arbeitsfelder+16..+40 auf0 und die Basistabelle. Die konkreten Konstruktoren schreiben anschließend:

| Payloadkind | Erwartete Vtable-RVA |
|---|---|
| 0 (Prototype0) | 0x5B4958 |
| 1 (RAW) | 0x5B4A38 |

Die Konstruktoren speichern keine Länge. Deshalb muss der ausgewählte Type9-Eintrag mindestens148 Bytes umfassen, der Datenpointer exakt C+24 sein und `Motion+8 == Motion+144` gelten. Kopiert werden genau `EntryLength-144` Bytes ab Motion+144. Für einen Parser kann eine größere formatabhängige Mindestlänge gelten; die vier Kindbytes allein beweisen keine gültige Motion.

## 5. Minimaler konservativer Produktpfad

1. Auf zulässigem Spielthread einen aktuellen Actor-/Binding-Witness unter bereits wirksamem synchronem Admission-/Lifetime-Schutz aufnehmen. Besitzer C+16 stimmt mit dem erlaubten Actor überein. C+328=Actor+128; C+8, C+344, C+352 und C+432 sind0. Der äußere Provider liefert die tatsächlich belegte Reservation; Cache+80 ist nur unter diesem Vertrag eine verwendbare Obergrenze.
2. Primär-BAR C+0 liegt vollständig in dieser Reservation. Profilpolicy: Bytes0..2=`BAR`, low nibble von BYTE3==1; zunächst Spezialklassen `BYTE3 &0xC0 !=0` ablehnen. Bits4..5 sind Metadaten, kein Versionsfehler. Header+8 dekodiert exakt zur jeweiligen Containerbasis. Diese Policy ist bewusst enger als die native Find-Routine.
3. Beide Tabellen vor Eintragszugriff vollständig prüfen: positive signed Anzahl, konfigurierter Zeilenhöchstwert, checked `16+count*16`, genügend Elternbytes. Multiplikation und Adressaddition dürfen nicht umbrechen. Bevorzugt prüfen: `offset<=length && requested<=length-offset`.
4. C+44 muss nichtnegativ und kleiner als die äußere Anzahl sein. Exakt diesen Eintrag wählen. Zunächst ausschließlich Type17 mit Linkwort0 zulassen; andere native Container-/Override-/Linkpfade liefern Unsupported. Sein nichtnull Datenpointer und seine positive Entrylänge liegen komplett **hinter** der äußeren Tabelle und innerhalb der äußeren Reservation. Das ist die Elternspanne der zweiten BAR.
5. Die innere BAR nach denselben Header-/Tabellenregeln prüfen. Exakt den ersten Type9 wählen. Linkwort!=0, Größe<148, null/außerhalb/überlappende Tabellenpointer, falsche Vtable, falscher Kind oder `Motion+8 != Motion+144` ablehnen. Kein Reparieren und keine Suche nach einer späteren Alternative.
6. Die Payload liegt komplett hinter der inneren Tabelle und innerhalb der **aus dem äußeren Entry gewonnenen inneren BAR-Spanne**. Damit reichen Lesbarkeit oder die größere gesamte Cachearena allein nicht aus. Begrenzte Payload- und Metadatenbudgets vor Allokation/Iteration prüfen. Genau zwei BAR-Ebenen werden betreten; keine allgemeine Rekursion.
7. In eine eigene temporäre Bytefolge kopieren. Danach alle benötigten Controller-/Header-/Entry-/Vtable-/Pointertabellen-Witnessfelder und die vom äußeren Provider geschützte Ära erneut prüfen. Bei Änderung Ergebnis verwerfen. Erst dann ein unveränderliches Ergebnis veröffentlichen; keine nativen Pointer zum späteren Nachlesen herausgeben.

Externalziele, ungeklärte Parent-/Childcachealiase, direkte geliehene BARs, unbekannte Regionen, Links und freie Pointertoken bleiben unzulässig. Ein synthetischer Testprovider darf diesen Vertrag modellieren, ist aber kein installierter Produktionsprovider. Sibling-Aliase werden nicht als neue Allokationsgrenze interpretiert; die Funktion bescheinigt keine Gültigkeit der unbetretenen BAR-Einträge.

## 6. Fehler und gezielte Tests

Fehler vor der Kopie: UnsupportedContext/Profile/Link, InvalidHeader/Count/Index, InvalidPackedPointer, OutOfSpan, WrongCurrentMotion, WrongKindVtable und BudgetExceeded. Änderung während/nach Lesen: Changed. Echte Provider-/Lesefehler dürfen nicht als gültige leere Payload erscheinen. Keine native Enginecallouts.

Erforderliche Tests: äußere Ordinalwahl bei gemischten Typen und irreführenden Tags; erster ungültiger Type9 vor späterem gültigem; fehlender erster Type9; negative/zu große Anzahl oder ID; exakte Tabellen-/Payloadgrenze und ein Byte darüber; Linkwort und Typ17-Policy; markerloses Wort trotz nativ gleicher Dekodierung; freie/falsch ausgerichtete Region; falscher Selfpointer; Parentgrenze kleiner als Cachearena; 147/148-Byte-Type9; C+24/Kind/Vtable/+8 mismatch; vor/nach geänderte Ära/Region/Entry; Allokations- und Lesefehler ohne Teilresultat. Die bestehenden Core-Parserprüfungen bleiben getrennt.

Eine erfolgreiche Kopie beweist ausschließlich den begrenzt gelesenen Zustand während des zugelassenen Scopes. Sie beweist keine historischen Writerabdeckung, spätere Runtime-Lebensdauer, vollständige Motion-/Skelettgültigkeit oder sichere Scale-Anwendung.
