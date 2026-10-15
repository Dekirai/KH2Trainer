# Wiederverwendung einer Attack-Ownerzelle

## Ergebnis

**Ein alter Angriff kann seinen gespeicherten Zeiger auf dieselbe Zelle behalten, in die der Manager gerade einen neuen Angriff einträgt.** Wird danach sein ursprünglicher Destruktor aufgerufen, schreibt dieser durch den gespeicherten Zeiger bedingungslos null. Er vergleicht den aktuellen Zelleninhalt nicht mit dem alten Objekt.

Das ist eine konkret belegte lokale Reihenfolge mit ausdrücklich benannten Voraussetzungen. Sie beweist noch keinen im normalen Spiel erreichbaren Fehler: Die äußere Aufruffolge, veränderte Parameter und das Ausbleiben zusätzlicher Eingriffe durch Helfer oder andere Writer wurden nicht in einer laufenden Spielszene nachgewiesen. Insbesondere folgt daraus kein Use-after-free. Der unmittelbar belegte Effekt ist die Leerung einer Registrierung in einer weiterhin gültig vorausgesetzten Zelle.

## Genaue Folge im Originalcode

Der geprüfte Adapter `3D29B0` verwendet den eingebetteten Manager bei `secondArg+3088`. Die Pointerzelle eines Eintrags liegt bei `manager+16+16*i`, also `actor+3104+16*i`. Die vollständige Originaltabelle `5C6250` wurde bereits in der Vorstudie erfasst; die Zelle bei `5C62E8` wird hier erneut direkt geprüft und zeigt auf diesen Adapter.

1. `3D25D0` findet einen belegten Eintrag, dessen Angriff-DWORD+200 zum angefragten Schlüssel passt und dessen dekodiertes Feld+20 dem übergebenen Actor entspricht. Es prüft dann Angriff-DWORD+24 gegen den Parameter und den Eintrags-DWORD gegen den Tag. Sind beide gleich, erfolgt keine neue Allocation.
2. Weicht einer dieser beiden Werte ab, ruft `3D2694` den Helper `3D0EB0(old)` auf. Dieser setzt bei aktivem Kontaktlisten-Byte und gefundenem Listeneintrag lediglich `old->flags |= 0x800`; er zerstört das Objekt nicht und schreibt nicht nach `old+720`.
3. Der Manager allokiert 728 Bytes und übergibt bei `3D26E0/3D26E5` die Adresse **derselben Zelle** als fünftes Argument an `40F1C0(new, ...)`. Der vollständige abgeleitete Konstruktor speichert sie bei `40F468` in `new+720`.
4. Bei `3D26ED` schreibt der Manager `new` in diese Zelle. Der Managerkörper schreibt den gespeicherten Zeiger `old+720` nicht um. Unter der ausdrücklich nötigen Annahme, dass die aufgerufenen Helfer und keine andere Ausführung diesen Zeiger ändern, besitzen nun beide Objekte dieselbe äußere Zellenadresse.
5. Für einen späteren Aufruf von `40F4C0(old,1)` liest `40F4D9` den Zeiger aus `old+720`. **`40F4E0` schreibt sofort null durch ihn**, ohne den Inhalt der Zelle zu vergleichen. Erst danach beginnt der gemeinsame Cleanup. Die lokale Nullschreibung trifft deshalb auch einen dort inzwischen gespeicherten neuen Angriff.

Die Markierung ist für die sofortige Ersetzung im Manager keine Erfolgsvoraussetzung. Sowohl bei deaktiviertem Kontaktlisten-Byte als auch bei fehlendem Listeneintrag kehrt `3D0EB0` ohne Markierung zurück; der Manager setzt seinen Ersatzpfad trotzdem fort. Diese Fälle sind lokale Zweige, keine Behauptung über ihre Erreichbarkeit bei gültigen Spielobjekten.

## Verbraucher und die zwei neuen Körper

Der bereits vollständig geprüfte Kontaktverbraucher `3CFF40` ist hier eine ausdrücklich wiederverwendete Abhängigkeit. Er speichert den nächsten Listeneintrag und ruft bei `flags & 0x800` den virtuellen Destruktor mit Löschflag 1 auf. Die erneut gelesene Vtable `5CE6C0` enthält `40F4C0` in Slot0 und `40F610` in Slot+24. Nicht markierte Einträge erreichen im Kontaktverbraucher Slot+24. Der Zweig für ein Objekt ist damit bereits gewählt, bevor dessen Update läuft; eine dort neu gesetzte Markierung führt in dieser einen Iteration nicht rückwirkend in den Destruktorzweig.

`40F610` kann selbst `3D0EB0(this)` aufrufen: nach bestimmten Rückgaben seiner Actor-/Parameterhelfer oder nach einer freigegebenen Aktualisierung, die keinen passenden Eintrag zählt. Der vollständige Körper enthält keine ausdrückliche lokale Umleitung oder Invalidierung des gespeicherten Ownerzellenzeigers bei +720. Seine lokalen Zähler-, Positions- und Flagaktualisierungen lösen die oben beschriebene Aliaslage daher nicht ausdrücklich auf. Das schließt transitive Eingriffe seiner zahlreichen externen Helfer nicht aus; diese wurden für diesen Anschluss nicht erneut vollständig verfolgt.

`4323B0` ist ein sechs Instruktionen langer Adapter: Er dekodiert den DWORD an seiner Eingabeadresse und springt zu `3D0EB0`. Er leert weder seine Eingabezelle noch liest oder verändert er ausdrücklich das gespeicherte Feld+720 des Zielobjekts. Die Herkunft seiner Eingabe und die genaue zeitliche Aufruffolge bleiben offen.

Die vollständigen IDA-Xref-Abfragen enthalten 42 Codeverweise auf `3D25D0` sowie einen Datenverweis, elf Codeverweise auf `3D0EB0` sowie einen Datenverweis und einen Codeverweis auf `40F1C0` sowie einen Datenverweis. Ein vorhandener Codeverweis beweist keine tatsächliche Folge mit geänderten Parametern vor dem nächsten Kontaktverbraucher. Diese Studie verwendet nur den ausgewählten Adapter. Die [separate Adapterstudie](../attack-manager-adapters-20261013/report.md) belegt inzwischen die gleiche lokale Argumentübergabe aller 42 erfassten Adapter.

## Synthetische Prüfung der Originalinstruktionen

Fünf Fälle interpretieren die vollständigen lokalen Körper von Manager, Markierungsfunktion, abgeleitetem Konstruktor und gegebenenfalls löschendem Wrapper:

| Fall | Ersatz | Altes Objekt markiert | Explizit nachgeschalteter alter Destruktor |
|---|---:|---:|---|
| Parameter verändert | ja | ja | Leert die inzwischen neu belegte Zelle |
| Tag verändert | ja | ja | Leert die inzwischen neu belegte Zelle |
| Beide Werte gleich | nein | nein | Nicht aufgerufen |
| Kontaktliste deaktiviert | ja | nein | Nicht aufgerufen |
| Alter Eintrag fehlt in Kontaktliste | ja | nein | Nicht aufgerufen |

Die zwei Destruktoraufrufe werden **vom Fixture ausdrücklich nach dem Manageraufruf vorgegeben**. Der Kontakt-Scheduler wird dabei nicht ausgeführt. Der gemeinsame Basiskonstruktor und gemeinsame Cleanup sind offene Helfergrenzen; deren Fixtures beweisen keine native Listenregistrierung, Zählerführung oder vollständigen Seiteneffekte. Auch Allocation, Ptr32-Zuordnung und Speicherbereiche sind vorgegeben. Die entscheidenden Stores im Manager, im abgeleiteten Konstruktor und vor dem gemeinsamen Cleanup stammen hingegen aus den Originalinstruktionen.

Die fünf Fälle benötigen **886 interpretierte Schritte und 223 verschiedene ausgeführte Instruktionen**. Der bereits gepinnte Interpreter wird unverändert verwendet. Speicher außerhalb der Fixturebereiche wird zurückgewiesen; das ist eine Eigenschaft des Fixtures, kein behaupteter Schutz des Spiels. Kein nativer Code wurde ausgeführt.

## Konsequenz für mögliche Trainerfunktionen

Eine Diagnose kann später eine Zelle mit dem zugehörigen Objekt+720 vergleichen und den Status „zur Beendigung markiert“ getrennt darstellen. Diese Studie implementiert weder eine solche Laufzeitvalidierung noch eine Reparatur.

Eine Funktion zum spontanen Ersetzen oder Abbrechen von Angriffen darf aus der Pointerzelle allein keine exklusive Zuständigkeit ableiten. Ein Eingriff müsste zusätzlich die konkrete Objektgeneration und die spätere Destruktorfolge berücksichtigen. Einfach einen zweiten Angriff in dieselbe Zelle zu schreiben wäre durch die hier geprüften Körper nicht abgesichert. Eine pauschale Änderung des Originaldestruktors wird daraus nicht abgeleitet.

## Nachweisgrenzen und Reproduktion

- **Zwei frische vollständige Körper:** 171 Instruktionen, 740 Bytes. „Frisch“ bedeutet neu erfasst, nicht erstmals entdeckt.
- **Sechs ausdrücklich wiederverwendete Körper:** 379 Instruktionen, 1741 Bytes.
- **Gesamt:** acht Körper, 550 Instruktionen, 2481 Körperbytes und zusätzlich 40 originale Vtabledatenbytes. Alle ausgewählten Körperbytes sind durch Instruktionen abgedeckt.
- Alle Originalbytes, Instruktionsgrenzen und Mnemonics werden erneut unabhängig mit Capstone gegen die Original-EXE geprüft. Die Größen stimmen mit dem bestehenden Inventar überein.
- Vollständige Root-Captures liegen vor. Der Reviewer hatte keinen eigenen Zugriff auf die Root-Sitzung; eine abgeschlossene globale Autoanalyse wird nicht behauptet.
- Keine allumfassende Writer-, Reentranz-, Thread-, Lifetime-, Leak- oder Spielbuggarantie. Kein Live-Spiel, keine GUI-, Injection-, Save- oder Twitch-Aktion.

```powershell
py -3 -B artifacts/attack-slot-reuse-20261013/verify.py --check
```

Das eingefrorene Original mit Rohaufnahmen, Interpreter-Probe und Manifest liegt unverändert in `original-study.zip`. Diese Dokumentation normalisiert nur die Evidenz für den globalen Nachweisindex und ergänzt den Querverweis zur späteren Adapterstudie.
