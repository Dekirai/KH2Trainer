# Actor-Update, direkte Bereinigung und Destruktorgrenze

## Ergebnis

Der normale Actor-Update und eine separate Bereinigungsroutine erreichen die
Entfernungsmarkierung auf unterschiedlichen Wegen. **Die Prüfung des Zählers
bei Actor+1464 ist keine allgemeine Voraussetzung jedes Markierungsaufrufs.**
Die vollständige Routine `3BF8F0` kann Descriptor-Slot+72 direkt aufrufen, ohne
vorher dessen Zulassungs-Slot+64 aufzurufen. Vor der Actor-Schleife leert sie
allerdings bereits die Kontaktliste und ruft weitere Bereinigungshelfer auf.
Aus dem fehlenden lokalen Countertest folgt deshalb kein nachgewiesener Spielfehler.

Außerdem ist jetzt der Aufruf des eigentlichen Actor-Updates durch den separaten
Actor-Taskmanager verbunden. Vor dem späteren Destruktor gibt es einen weiteren
klassenabhängigen Callback. Diese Befunde schließen konkrete Lücken der vorherigen
Kontaktstudie; sie beweisen keine allgemeine Sperre gegen sämtliche Freigaben.

## Normaler Updatepfad

Die bereits belegte Registrierung `3BF810` legt `3BF550` im Feld-Taskmanager an
und `3BF5E0` im separaten Actor-Taskmanager. Der neue vollständige Körper
`3BF550` ruft nach `3F6540` den Forwarder `14FC20` mit dem Manager aus
`2A17180` auf. `14FC20` reicht Maske 0 und Vergleichswert 0 an `14FD60` weiter.
Damit erfüllt jeder tatsächlich verkettete Task dessen Flagvergleich.

Bei null Task+112 ruft `14FD60` den gespeicherten Callback direkt auf. Der
untersuchte Taskkonstruktor `14F770` initialisiert dieses Feld mit null. Unter
der Voraussetzung, dass Task, Verkettung und Manager seitdem entsprechend
erhalten sind, führt der normale Aufruf daher synchron zu `3BF5E0`.

`3BF5E0` läuft über die aktive Liste `2A171C8` und den Packed-Link Actor+2704.
Es schreibt den gerade bearbeiteten Actor nach `2A17248` und ruft `3BFD30`
direkt oder in weiteren, von Bindungen abhängigen Durchläufen auf. Anschließend
bearbeitet es aktualisierte Actors, löscht ausgewählte Updateflags und setzt
`2A17248` wieder auf null. Die Schleifen und undurchsichtigen Helfer erlauben
hier keine allgemeine Terminierungs- oder Zeitgarantie.

In `3BFD30` bleibt der bereits belegte Ablauf bestehen: Requestflag
`0x10000000` führt zu Slot+64; nur Erfolg führt zu Slot+72. Für die originale
Descriptorzelle `74C380 → 5C6250` sind dies `3D28B0 → 3DAC30` und
`3D28C0 → 3B45C0`. Die erste Kette berücksichtigt den Referenzzähler und weitere
Bedingungen. Die zweite bereinigt und setzt das Flag `0x80000`.

## Direkter Pfad mit Schwellwert

`3BF8F0(threshold)` ruft vor der Actor-Schleife elf Helfer auf; einer davon ist
`3CFED0`, das alle Kontakte über deren virtuellen Destruktor entfernt und die
Kontaktliste deaktiviert. Die übrigen Helfer sind keine hier geschlossenen
Beweise für sämtliche Skript- oder Ressourcenreferenzen.

Für jeden Actor ohne Flag `0x80000` ruft `3BF8F0` Descriptor-Slot+112 auf und
vergleicht dessen 32-Bit-Ergebnis **vorzeichenbehaftet** mit `threshold`:

- Ergebnis mindestens Schwellwert: direkter Aufruf von Slot+72.
- Ergebnis kleiner: anderer Zweig über den Tag `event`, `3DA520` und gegebenenfalls
  `3B6050`; dieser Zweig wird nicht als gleichwertige Entfernung behauptet.

Die neu gelesene Originaltabelle bindet Slot+112 an `3D2920 → 3B44A0`.
`3B44A0` dekodiert Actor-DWORD+8 und reicht ihn über `3E0B50(...,0)` an
`39DB20` weiter. Die genaue Bedeutung sämtlicher möglicher Rückgabewerte bleibt
offen. Die frisch geprüften Caller `3AC2F0` und der bedingte Pfad in `3AD0E0`
verwenden den Schwellwert **2000**. Der weitere Caller `3AC750` wurde nur
explorativ dekompiliert und zählt nicht zu den vollständigen Körperbelegen.

## Callback vor dem Destruktor

Der bereits belegte Dead-List-Verbraucher `3BF300` ruft vor Descriptor-Slot0
zunächst `3B4E80(actor)` auf. Wenn Actor-DWORD+2488 die Maske `0x40` nicht
enthält, ruft `3B4E80` Slot+48 auf und setzt die Maske **erst nach dessen Rückkehr**.
Die Routine liefert damit keinen allgemeinen Schutz vor Wiedereintritt oder
parallel ausgeführten Callbacks.

Für `5C6250` ist Slot+48 `3D2840 → 3DABE0`. Diese Routine arbeitet an den
eingebetteten Bereichen Actor+344 und +128 und ruft anschließend `3B43C0` auf.
`3B43C0` ruft zunächst `3E61E0(actor+2320)` auf. Falls Actor+2696 nicht null ist,
folgt dessen virtueller Slot+72 mit der Rückgabe von `152590` und Actor+1968;
danach wird Actor+2696 auf null gesetzt. Das ist konkretes zusätzliches Cleanup,
kein reiner Statusgetter.

Erst danach erreicht der Dead-List-Verbraucher den ausgewählten Destruktor
`3D2720`: eingebettete Teile bereinigen, `3B3D60(actor)` aufrufen, anschließend
`152570(actor)`. Der vollständige gemeinsame Cleanup `3B3D60` ruft Helfer für
mehrere Actorfelder auf, darunter +1472, +2560, +1600 und +1584 sowie eingebettete
Bereiche. In diesen beiden vollständigen Körpern steht kein lokaler Test auf
Actor+1464. Transitive Prüfungen oder weitere Freigaben durch ihre Helfer werden
nicht pauschal ausgeschlossen. Die konkrete Allocationfreigabe hinter `152570`
hängt weiterhin vom aktuellen Allocator und dessen virtuellem Slot ab.

## Bedeutung für den Trainer

Die vorhandenen Anzeigen für Referenzzahl und Entfernungsflags sind getrennte
Beobachtungen. Ein aktuell gelesener Zähler von null oder eine frühere
Actoridentität berechtigt nicht dazu, später einen gespeicherten Pointer zu
verwenden. Ein Produktionspfad für Motion-Daten benötigt weiterhin einen
konkreten Gültigkeitsbereich für Actor, Ressourcen und konkurrierende Änderungen.

Der ergänzend erfasste `14EB70` ruft den Haupt-Taskmanager aus `9BA888` auf.
Das ist eine eigene Managerquelle gegenüber `2A17180`; Gleichheit dieser
Manager wird nicht behauptet. Die getrennte Motion-Untersuchung verbindet die
Request-Registrierung mit dem Hauptmanager.

## Nachweis

- 15 frisch erfasste vollständige Körper: 460 Instruktionen, 1830 Bytes.
- 14 ausdrücklich wiederverwendete Körper: 739 Instruktionen, 2929 Bytes.
- Gesamt: 29 Körper, 1199 Instruktionen, 4759 Körperbytes; zusätzlich 136 Datenbytes.
- Original-PE-Hash, Funktionsgrößen, alle Instruktionsgrenzen und Mnemonics mit
  Capstone geprüft; 22 ausgewählte Instruktionsanker und konkrete Descriptorzellen.
- Frische Aufnahme bedeutet keine erstmalige Entdeckung. Keine Funktion wird
  als vollständig semantisch verstanden eingestuft.
- Keine nativen Spielaufrufe, Spiel-, Save-, GUI-, Injection- oder Twitch-Aktionen.
  Keine Änderung an Produkt oder ausgelieferter EXE.

```powershell
py -3 -B artifacts/actor-destruction-boundary-20261013/verify.py --check
```


## Documentation import and independent review

The frozen source study and review are preserved byte-for-byte in `evidence.zip`, including their manifests. `provenance.json` pins every archive member and maps every normalized body to its archived original record. Stored IDA lines are wrapped as one complete page and original bytes are spaced for the existing coverage parser. No new capture, runtime behavior or complete-semantics claim is added.

This document contributes 15 bounded per-function claim records and 0 separate range findings, backed by 29 complete bodies. Global coverage deduplicates function addresses against prior work; these record counts are not counts of newly understood functions. Run this folder's `verify.py --check` for read-only archive, original-byte, normalization and reference checks. The archived author scripts retain their original paths.
