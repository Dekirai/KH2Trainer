# Unabhängiger Review der Körpergrenzen-Studie

**Im angegebenen Umfang akzeptiert; keine offenen Blocker.**

Geprüfter Autorenstand: `actor-body-bounds-20261011`, Manifest
`bc97953b4c545eae7983987ccc2f965c2e407206af9ce2a60b96d737090c5c1d`.

Der Review prüft Original-PE und alle 13 vollständigen Bodies unabhängig,
einschließlich ASM-Seiten, Cursor, 4.966 Bytes und 1.057 Instruktionen. Alle 13
Claims wurden in ihrem begrenzten Umfang gelesen; die 27 Referenzen funktionieren
mit dem unveränderten Coverageparser. Der zusätzliche gepinnte Vorarbeitsbeleg
für `1A94C0` bestätigt die Matrixkopie hinter den beschriebenen Publikationsstellen.

Ein eigener Interpreter führt die drei Rechenfunktionen ohne Callstubs oder
externe Datenzugriffe auf 15 künstlichen endlichen Eingaben aus. Er stimmt mit
allen zwölf gespeicherten nativen Ergebnissen und drei zusätzlichen Fällen
überein. Die zwölf nativen Fälle wurden ergänzend erneut im privaten
Review-Python-Prozess ausgeführt. Dafür wurde die zuvor gelesene `run_native`-
Routine des Autors verwendet; sie gibt ihr Ergebnis zurück und schreibt selbst
keine Datei. Ihr Ergebnis liegt ausschließlich hier in `native-replay.json`.
Diese ergänzende Wiederholung ersetzt die unabhängige Prüfung nicht.

Die ursprünglichen Autorenfiles blieben byteidentisch. Es gab keine Änderung an
Spiel, IDB, Produkt, Docs oder Paketen. Die Aussage betrifft die konkrete
MINSS-Rechnung und ihre beschriebenen lokalen Aufrufer. Sie belegt weder einen
allgemeinen Szenenfehler noch die Sicherheit eines globalen Patches oder einer
vollständigen Tiny/Giant-Funktion.

Reproduktion des gespeicherten Reviews ohne erneute native Ausführung:

```
py -3 -B artifacts/review-actor-body-bounds-20261011/review.py
```

Die erstmalige private native Wiederholung wurde mit `--native --write`
ausgeführt. Im eingefrorenen Zustand liest der Standardaufruf nur Dateien und
interpretiert Instruktionen; er überschreibt keine Belege. Der Receipt enthält
die exakten Grenzen und Quellenpins. Prüfzahlen sind keine semantische
Abdeckungsquote.
