# Gemeinsame Angriffsmanager-Adapter

Die vorhandene IDA-Datenbank liefert **42 direkte Codeaufrufer** von `3D25D0`.
Alle sind vollständige Adapter mit jeweils 46 Bytes und 12 Instruktionen.
Nach Normalisierung der relativen CALL-Distanz sind ihre Bytes identisch.
Der zusätzliche Datenverweis liegt in `.pdata`; er zählt nicht als weiterer Aufrufer.

## Aufrufkonvention

Die Argumentnummern beziehen sich auf den Windows-x64-Eintritt in den Adapter.

| Eingang | Übergabe an `3D25D0` |
| --- | --- |
| Argument 1 / RCX | Im Adapter verworfen |
| Argument 2 / RDX | Adresse plus 3088 als Manager in RCX |
| Argument 3 / R8 | Untere 32 Bit nach EDX |
| Argument 4 / R9 | Untere 32 Bit nach R8D |
| Argument 5 / Stack | Vollständige 64 Bit nach R9 |
| Argument 6 / Stack | Untere 32 Bit als fünftes Argument auf den Stack |
| Rückgabe von `3D25D0` | RAX bleibt beim Rücksprung erhalten |

Jeder Adapter reserviert 56 Stackbytes und gibt sie vor dem Rücksprung frei.
Er fügt keine eigene Null-, Typ- oder Lebensdauerprüfung hinzu. Zusammen mit
dem [Manager-Nachweis](../attack-owner-cell-20261013/report.md) liegen die acht
möglichen äußeren Zellen auf diesen Wegen bei `Argument2 + 3104 + 16 * Index`.
Der gemeinsame Manager wählt den Index; der Adapter selbst greift nicht auf die Zellen zu.

## Bedeutung für weitere Mods

Diese Aufrufer verwenden denselben Managervertrag. Eine spätere Diagnose oder
Attack-Steuerung braucht daher keine 42 unterschiedlichen Implementierungen
für diese Adapter. Sie muss den konkreten Actor und dessen Manager trotzdem
validieren. Der Nachweis erlaubt keine beliebigen Aufrufe mit rohen Zeigern.

Die vollständigen Körper, Stackzugriffe und direkten CALL-Ziele wurden mit der
Original-EXE und unabhängig mit Capstone verglichen: **504 Instruktionen,
1932 Bytes**. Das belegt diese kleinen Adapter, keine vollständige Kenntnis der
aufgerufenen Routinen oder aller indirekten Aufrufwege. Keine Spielaktion,
native Ausführung oder Änderung am Trainer.

Reproduktion: `py -3 -B docs/research/attack-manager-adapters-20261013/verify.py --check`.
Die Rohabfragen liegen unverändert in `raw.zip`; `verification.json` enthält
Originalbytes, Hashes und disassemblierte Instruktionen.

## Erfasste Adapter

| Funktionsanfang | CALL nach `3D25D0` |
| --- | --- |
| 0x1401b01f0 | 0x1401b0214 |
| 0x1402e29d0 | 0x1402e29f4 |
| 0x14038ff30 | 0x14038ff54 |
| 0x140393cf0 | 0x140393d14 |
| 0x140394ad0 | 0x140394af4 |
| 0x1403970d0 | 0x1403970f4 |
| 0x1403a72b0 | 0x1403a72d4 |
| 0x1403c29f0 | 0x1403c2a14 |
| 0x1403d29b0 | 0x1403d29d4 |
| 0x1403d5150 | 0x1403d5174 |
| 0x1403db600 | 0x1403db624 |
| 0x1403dda40 | 0x1403dda64 |
| 0x1403f8be0 | 0x1403f8c04 |
| 0x140403280 | 0x1404032a4 |
| 0x140404200 | 0x140404224 |
| 0x140404cd0 | 0x140404cf4 |
| 0x140405cd0 | 0x140405cf4 |
| 0x1404067e0 | 0x140406804 |
| 0x140410640 | 0x140410664 |
| 0x140411580 | 0x1404115a4 |
| 0x140415300 | 0x140415324 |
| 0x1404194e0 | 0x140419504 |
| 0x140419890 | 0x1404198b4 |
| 0x140419c90 | 0x140419cb4 |
| 0x14041a0b0 | 0x14041a0d4 |
| 0x14041a6a0 | 0x14041a6c4 |
| 0x14041a9f0 | 0x14041aa14 |
| 0x140549df0 | 0x140549e14 |
| 0x14054b870 | 0x14054b894 |
| 0x14054d9b0 | 0x14054d9d4 |
| 0x140551a70 | 0x140551a94 |
| 0x140559400 | 0x140559424 |
| 0x1405597b0 | 0x1405597d4 |
| 0x14055c7e0 | 0x14055c804 |
| 0x14055e6c0 | 0x14055e6e4 |
| 0x14055ea90 | 0x14055eab4 |
| 0x14055fd30 | 0x14055fd54 |
| 0x140560430 | 0x140560454 |
| 0x1405607b0 | 0x1405607d4 |
| 0x140560bc0 | 0x140560be4 |
| 0x140561a70 | 0x140561a94 |
| 0x140561e70 | 0x140561e94 |
