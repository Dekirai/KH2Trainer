# Motionbindung: Ressourcen, Lebensdauer und ein begrenzter Scale-Pfad

## Ergebnis

Die Bindung ist jetzt bis zum nativen Ressourcen-Cache verfolgt. Der Controller liegt bei **Actor+344**. Seine aktuelle Motion steht bei **C+24 / Actor+368**, deren Payloadpointer bei **Motion+8**. Das Type-9-Objekt liegt im 144-Byte-Prefix des BAR-Eintrags; seine Payload beginnt bei `Motion+144`. Der Motionkonstruktor speichert keine Länge.

**Cache+80 kann als äußere Reservierungsgrenze dienen**, wenn der konkrete Reservierungszustand belegt und vor Änderungen widerrufen wird. Die exakte Dateilänge ist dafür nicht zwingend nötig. Der Cache verwendet diesen gerundeten Umfang für Platzvergabe und Kopieren. Die innere Motiongrenze muss zusätzlich aus dem tatsächlich gebundenen BAR-Eintrag+12 kommen. Ein beliebiger Cacheknoten mit lesbaren Feldern genügt allerdings nicht: Der Cache unterstützt verschachtelte Ressourcen, direkte Unterbereichszeiger, Relocation und Wiederverwendung derselben Deskriptoradresse.

Das ist ein konkreter nächster Implementierungsweg für Tiny/Giant. Diese Studie implementiert ihn noch nicht und bestätigt keine sichere dauerhafte Skalierung.

## Belegumfang und Grenzen

- 57 frisch aus der vorhandenen IDA-Session erfasste vollständige Funktionen, 61 ASM-Seiten, 3.709 Instruktionen, 15.587 Bytes der Funktionsbereiche. Davon sind 165 Bytes Padding bzw. Tabellen innerhalb der IDA-Bereiche separat ausgewiesen.
- Jeder Bereich stimmt mit der Original-EXE SHA256 `9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed` überein. Die disassemblierten Instruktionen sind zusätzlich mit Capstone dekodiert; ASM hat Vorrang vor dekompilierten Typen und Argumentlisten.
- 30 eng begrenzte Claims in `report.json`; weitere erfasste Körper dienen der Kette und erhalten keinen künstlichen Neuheitsclaim. Frühere Projection-/Payload-/Ownership-Ergebnisse sind Abhängigkeiten.
- Session `8a0c3990`, PID28784, vorhandene IDB `KH2_round_20261007_lifetime.i64`. `is_analyzing=false`, **`auto_analysis_ready=false`**, Hex-Rays verfügbar. Keine Analyse erzwungen, keine IDB geändert. Diese Readiness-Grenze bleibt ausdrücklich offen.
- Keine Spielausführung, Live-Speicherlesung, Injection, Hooks, Produktänderung oder Build. Die zwölf Modellfälle sind kleine Span-/Historien-Gegenbeispiele, keine Ausführung der Originalfunktionen. 19 Instruktionsanker prüfen konkrete behauptete Operationen.

Die erste zu große `get_bytes`-Antwort war transportseitig begrenzt. Ihr sichtbar abgeschnittener Eintrag wurde separat vollständig neu erfasst. Die vollständige Größenprüfung des Verifiers verwendet ausschließlich vollständige Bytes. Alle Rohantworten bleiben erhalten.

## 1. Normale und geliehene Motionbindung

`3B3200` initialisiert den Ressourcenhalter bei Actor+2320 über `3E63D0`. `3E6120` lädt über `39CC40` Ressourcenbasen; die optionale Motionressource aus `3E0BD0` steht bei Halter+32, also Actor+2352. `3DA940` übergibt diese Basis an `3C8460`, den Setter für C+0. Ein weiterer konkreter Caller ist `3EF750` mit `obj/%s.mset`.

| Feld relativ zu C=Actor+344 | Bedeutung in den geprüften Pfaden |
|---|---|
| +0 / +8 | Primäre und alternative BAR-Basis für die Auswahl |
| +16 | Actorbesitzer |
| +24 / +32 | Aktuelle Motion und Triggerdaten |
| +40 / +44 / +48 | Logische ID, aufgelöste ID und Variantenzustand |
| +64 / +68 / +72 / +76 | Dauer, Frame, Blend-/Zielfelder |
| +328 | Root-/Transformkontext; im Normalpfad Besitzer+128 |
| +344 / +352 | Zusätzlicher Quellkontext und alternative BAR-Basis |
| +432 | Optionaler Zeiger auf einen DWORD-Referenzzähler |

`3C8CD0` setzt zuerst den normalen Rootkontext und löscht C+344/+352. Es sucht C+8 vor C+0 und ruft `3C8A40`. Dieser findet den Type-9-Eintrag und publiziert dessen Pointer bei C+24. Die Entry-Länge wird dabei nicht mitgeführt. `40D7A0` liefert ebenfalls nur den dekodierten verschachtelten BAR-Pointer.

`3C65E0` bindet nach Tag/Variante fremde Motiondaten und setzt dabei einen anderen Root-/Quellkontext. Erst nach dem eigentlichen Bindungsaufruf wird ein optionaler Referenzzähler gespeichert und erhöht. In `3C6CC0` stammt er aus **Quell-Actor+1464**, in `3D93E0` aus **Quellobjekt+80**. Ein generischer Typ- oder Generationstest auf diesen Zeiger wäre falsch. `3C6740` kann während des nativen Updates eine Warteschlangenaktion samt Callback und anschließender Umbindung ausführen.

`3C7300` senkt diesen Zähler, stoppt Soundhandles, bereinigt Listen und ruft einen Callback. **Es löscht die aktuelle Motionadresse nicht direkt.** Eine identische Motionadresse nach Cleanup oder nach Release→Rebind belegt daher keine unveränderte Bindung. Der Referenzzähler kann ebenfalls wieder denselben Wert annehmen.

Die Override-Setter `3C7C10`, `3C7C40` und `3C8F10` ändern C+8 ohne Änderung von C+24. Für Auswahl/Clear sind mit `42F460` und `42F490` konkrete BDX-Caller erfasst. Für den direkten Setter `3C7C40` ist kein Codecaller belegt.

## 2. Cache und tatsächlicher Reservierungsumfang

Der Ressourcen-Cache ist eine Liste ab RVA `29F33C8`, mit gepacktem Next bei Knoten+112. `39CC40` sucht Name/Kategorie, erhöht WORD+2 und liefert Basis+88. `39DA10` sucht diese Basis wieder und senkt den Zähler. Das ist kein unmittelbares Freigeben von Payloadbytes.

Der 120-Byte-Deskriptor enthält Zustand+1, Referenzzähler+2, Flags+68, Kategorie+72, **Umfang+80**, neue Basis+88 und vorherige Basis+96. `39E000` rundet eine explizite Größe auf128; ohne explizite Größe wird ein Dateigrößenresultat zunächst auf2048 gerundet. Diese Arithmetik ist native Reservierungspolitik, kein Beleg für akzeptable Trainergrößen oder Overflowfreiheit.

`39D590` ordnet Reservierungen im Cachebereich neu an. Positive Kategorien wachsen aus dem Bereich ab RVA `BF33C0`, negative Kategorien von `off_140749740` abwärts. `39D460` vergleicht für nichtnegative Kategorien `Basis+Umfang` mit der resultierenden Grenze `29F33F0`, bevor es `39E690` aufruft. Letzteres bearbeitet Überlappungen, startet bei fehlender Quelle einen Read oder macht BAR-Fixups rückgängig, kopiert in 16-Byte-Schritten in geeigneter Richtung und fixiert das Ziel erneut. +96 wird bei geänderter Basis schließlich auf+88 gesetzt. Zustand3 wird über die Finalisierung geschrieben; fehlgeschlagene Ladecompletion setzt Zustand−1.

**Wichtige Ausnahme:** `39E900` kann Type-2-Container in neue Cacheknoten aufteilen. Dort wird Umfang+80 aus einer gerundeten BAR-Entry-Länge gebildet, während beide Basen direkt auf den Unterbereich zeigen. Der Elternknoten kann anschließend verschwinden. Deshalb ist „Knoten vorhanden, Zustand3, +88==+96“ allein kein Ownershipbeweis. `39E000` kann solche Knoten außerdem wiederverwenden und umkategorisieren.

Eine konservative erste Admission kann deshalb entweder eine beobachtete abgeschlossene Cache-Platzvergabe voraussetzen oder einen anderweitig belegten direkten Reservierungsursprung führen. Für die erste Variante: nur vollständig beobachtete, abgeschlossene Platzvergabe; nichtnegative gewöhnliche Kategorie; positiver begrenzter und ausgerichteter Umfang; stabiler Knoten/Ära; geprüftes Cachearenaende; keine überlappenden zugelassenen Reservationen; keine laufende Lade-/Relocation-/Containerexpansion. Das sind **Trainerbedingungen**, keine neu entdeckten nativen Ablehnungen. Bereits beim Installieren vorgefundene, ungeklärte Unterbereichsknoten bleiben zunächst unzulässig. Es genügt, diesen engen Reservationspfad zu schließen; die Analyse aller Dateiprovider ist dafür nicht erforderlich.

## 3. Begrenzte Payloadkopie

Ein umsetzbarer Hostpfad verwendet den vorhandenen Core-Motionparser und diese neue native Kopie:

1. Auf dem zulässigen Spielthread Actoridentität und beobachtete Cache-/Bindingära aufnehmen. Ursprünglich nur normaler Kontext C+328=Actor+128, C+344=0, C+352=0; geliehene und unbekannte Pfade abweisen.
2. Die primäre/gegebenenfalls explizit unterstützte Override-BAR-Basis einem zugelassenen Cachebereich zuordnen. Nur geprüfte Pointerdekodierung und begrenzte Lesefunktionen benutzen; keine nativen Find-/Acquire-Funktionen auf ungeprüften Daten aufrufen.
3. Jede BAR-Tabelle zuerst vollständig innerhalb ihrer äußeren Spanne prüfen. Anzahl, Multiplikation, Addition, Verschachtelungstiefe und Lesebudget begrenzen. Externe/unklare Entryverweise abweisen. Die ausgewählte ID und den Type-9-Eintrag reproduzieren und verlangen, dass dessen Pointer exakt C+24 ist.
4. Jede verschachtelte Entryspanne muss innerhalb ihrer Elternspanne liegen. Type9-Länge muss mindestens144 sein; `Motion+8 == Motion+144` und bekannte Vtable verlangen. Kopierbare Payload ist genau `[Motion+144, Motion+EntryLength)` innerhalb des bestätigten äußeren Cachebereichs. Aus Parser-Tabellenenden wird keine neue Länge geraten.
5. Generationen vor/nach der Kopie und vor Commit erneut prüfen. Der Host parst ausschließlich die zurückgegebene Kopie. Der Token bindet Actor-Generation, Cache-/Bindingära, Auswahlpfad, Payloadbasis/-länge und die für Projection tatsächlich nötigen Zustandswerte. Änderungen widerrufen; ein Hash allein ersetzt keine Ära.

So kann ein gerundeter äußerer Bereich eine sichere Lesebegrenzung liefern, während die Entry-Länge die tatsächlich zu dieser Motion gehörende innere Grenze festlegt. Lesbare virtuelle Seiten allein beweisen weiterhin keinen Ressourcenbesitz. Rootdatenvalidität beweist keine Skeleton-/IK- oder vollständige Collisiongültigkeit.

## 4. Kleine Invalidierungspunkte und ihre Reihenfolge

| Ereignis | Belegter Ansatzpunkt | Warum vor dem nativen Ereignis |
|---|---|---|
| Normale Kontext-/Motionauswahl | `3C8CD0` Entry bzw. vor Store `3C8D0D` | Rootcontext wird schon vor `3C8A40` ersetzt |
| Geliehener Kontext, Erfolg oder Fehler | `3C65E0` Entry | Erfolg schreibt Kontext vor Bindung; Fehler bereinigt vor Pointerclear |
| Direkte Bindung | `3C8A40` Entry | Dauer/BBox/Pose können im Bindungsaufruf selbst gelesen werden |
| Cleanup | `3C7300` Entry | Referenzfreigabe und Callback erfolgen vor Return, Motionadresse kann gleich bleiben |
| Primär-/Overridewechsel | `3C8460`, `3C7C10`, `3C7C40`, `3C8F10` Entry | Bankhistorie ändert sich auch ohne unmittelbaren Motionwechsel |
| Cache-Neuregistrierung/Wiederverwendung | `39E000` Entry | Zustand und Knoten können bei gleicher Adresse neu belegt werden |
| Reservierungsplan | `39D590` Entry | Neue Ziele werden vor tatsächlichem Kopieren publiziert |
| Byteumzug/Neuladen | `39E690` Entry | Unfixup/Kopie/Read verändert die wirksamen Bytes |
| Container-Aufteilung / BAR-Freigabe | `39E900`, `3A6A10` Entry | Unterbereichs-/Deskriptorersatz bzw. Ressourcencleanup kann vor Unlink erfolgen |

Das ist ein konkretes, konservatives **Kandidaten-Set für den geprüften Pfad**, keine behauptete fertig installierte Vollständigkeitsgarantie. Der Cache darf zunächst eine gemeinsame Ära erhalten; ein einfacher globaler Widerruf bei seltenen Cacheereignissen spart eine unnötig komplizierte pro-Ressource-Abhängigkeitsstruktur. Pro-Actor-Bindungsrevisionen müssen auch identische Neubindungen zählen. Reentrante Cleanupcallbacks dürfen nicht nach einem bereits beobachteten Write unter dem neuen Kontext blind restaurieren.

Ein Hook erst beim Return von `3C8A40` wäre unzureichend: virtuelle Duration an `3C8B09`, optionale Bounds an `3C8BD3` und Posevorbereitung `3C73C0` an `3C8CA6` liegen davor. Ebenso liegt ein Hook nur bei `3C8A40` nach den früheren Rootcontextstores seiner Caller. Das lokale Pre-Event-Revoke muss zum separaten Bodycache-/Scale-Writer-Vertrag passen; ein Post-Frame- oder `3CCB90`-Returncheck ersetzt diese Reihenfolge nicht.

## 5. Noch gezielt zu schließen, bevor Produktfreigabe möglich ist

- **Cacheadmission und Observerscope:** Eintritt/Return von `39D590`/`39D460` sowie `39E690` mit verschachtelten Aufrufen modellieren, inklusive Readcompletion `39DEE0`. Die Größe ist vorhanden; offen ist der neue Trainerbeweis einer stabilen, beobachteten Reservation für den konkreten geladenen Spieler. Primitive externe Loaderwrites oder unerkannte Mods dürfen nicht stillschweigend als beobachtet gelten.
- **Zusätzliche Bytewriter:** Falls BAR-Fixup/Re-Fixup außerhalb der zugelassenen Cache-Operationen unterstützt werden soll, die direkten Caller von `3A6840`, `3A6120`, `3A62B0` auf den gewählten MSETpfad begrenzen oder als zusätzliche globale Invalidierung erfassen. Keine pauschale ganze-Engine-Analyse nötig.
- **Vor-Write-Revoke:** Implementierung muss vor den obigen Kontextstores unter dem noch gültigen alten Kontext zurücknehmen oder die Mutation mit einem vorher geprüften zulässigen Folgezustand abdecken. Nur einen Revisionszähler zu erhöhen, während ein ungeprüfter Scale weiter angewendet bleibt, löst das Problem nicht.
- **Ausführungstests:** Echte Observer-ABI/Produktcallsite, gleiche Pointer mit neuer Ära, Cleanup mit Callback, normale/geliehene Auswahl, verzögerte Reads, Childaliases, Relocation mit Überlappung und Überläufe gezielt testen. Bestehende Actor-Identität und Core-Rootfixtures wiederverwenden. Diese Studie ist ausdrücklich kein Laufzeittest.

## Reproduktion

`py -B artifacts/motion-resource-binding-20261011/verify.py`

Prüft Original- und Arbeitskopiehash, alle vollständigen ASM-/Pseudocodeseiten, sämtliche Bereichsbytes, separate Nicht-Instruktionsspannen, originale Instruktionsanker, die zwölf begrenzten Modelle, Abhängigkeitspins, kanonische Claimreferenzen und die exakte rekursive Manifestdateimenge. Keine IDA-Verbindung und kein Spielzugriff nötig. `--write` erzeugt nur die abgeleiteten JSON-Ergebnisse im Studienordner neu.
