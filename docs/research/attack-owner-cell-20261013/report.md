# ATTACK_OBJ: Herkunft der äußeren Zelle

Die äußere Zelle, deren Adresse `40F1C0` im Angriffsobjekt speichert
([vorheriger Nachweis](../attack-object-ownership-20261011/report.md)), stammt
aus einer Tabelle mit acht Einträgen. Auf dem geprüften Adapterpfad liegt sie
bei `secondArg + 3104 + 16 * index`. Sie ist kein separat angelegtes Objekt.

`3D25D0` sucht einen passenden bestehenden Angriff oder merkt sich die letzte
freie Zelle. Bei einem passenden Angriff werden zusätzlich zwei Parameter
verglichen. Nur bei Gleichheit wird er wiederverwendet; sonst ruft die Routine
die Markierungsfunktion für den alten Angriff auf und trägt einen neu
konstruierten ein.

Die Markierung durch `3D0EB0` ist keine unmittelbare Zerstörung: Sie sucht den
Zeiger in der globalen Kontaktliste und setzt Bit `0x800`. Das ist auch für
`3D24B0` relevant. Dieser Manager-Cleanup ruft für seine belegten Zellen die
Markierungsfunktion auf und setzt die Zellen sofort auf null. Daraus folgt noch nicht, dass alle Angriffe
und ihre gespeicherten Zeiger auf diese Zellen bereits verschwunden sind.

Der untersuchte Cleanup-Wrapper `3D2720` ruft danach weitere Bereinigungen und
`152570` für das umgebende Objekt auf. In diesem Wrapper selbst wird der
Actor-Zähler bei `+1464` nicht geprüft. Ob die Aufrufer nur bereits freigebbare
Objekte zulassen und wann markierte Angriffe tatsächlich zerstört werden,
bleibt der nächste Anschluss. Diese Analyse beweist keinen Fehler im normalen
Spielablauf und gibt keine neue Schreibfunktion frei.

Zwei lokale Voraussetzungen sind nun ausdrücklich dokumentiert: Der Manager
braucht einen passenden oder freien Eintrag; eine vollständig belegte Tabelle
ohne Treffer hat in diesem Körper keinen gültigen Ausweichpfad. Auch ein
fehlgeschlagenes Allocationsergebnis wird vor dem späteren Feldzugriff nicht
abgefangen. Die Erreichbarkeit dieser Fälle im normalen Spiel ist nicht belegt.

## Nachweis

Fünf vollständige IDA-Körper wurden mit der Original-EXE und unabhängiger
Capstone-Dekodierung verglichen: **186 Instruktionen, 666 Bytes**. Die
Funktionsgrößen stimmen mit dem bisherigen Inventar überein. Fünf zusätzlich
abgerufene Bytes hinter `3D0EB0` sind ausdrücklich nicht mitgezählt.

IDA meldete `auto_analysis_ready=false`. Die vollständigen Einzelabfragen und
der Originalvergleich belegen die ausgewählten Körper, keine vollständige
globale Autoanalyse. Weitere gespeicherte Decompiles bleiben Erkundungsmaterial.

Reproduktion: `py -3 -B docs/research/attack-owner-cell-20261013/verify.py`.
Es werden nur lokale Dateien gelesen und der Prüfbericht neu geschrieben.
Es gab keine Spiel-, Speicherstand- oder Twitch-Aktion.
