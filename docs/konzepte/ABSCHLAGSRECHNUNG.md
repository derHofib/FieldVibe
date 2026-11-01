# Konzept: Abschlags- und Schlussrechnung – Ausbau

Status: **Entwurf zur Abstimmung** (nichts umgesetzt) – Stand: 31.10.2026

## 1. Wichtigster Befund: Das Grundgerüst steht bereits

Die Analyse (`fieldvibe-vs-salesforce.md`, Punkt 7) und der Hinweis am Ende von
`docs/phases/PHASE_6.md` („Abschlags-/Schlussrechnung mit Anrechnung und Teilstorno weiterhin
offen“) sind **überholt**. Der Code (Migration 0108, `rechnungsart_service.py`, 58 Tests in
`tests/test_rechnungsarten.py`) enthält bereits:

| Funktion | Stand |
|---|---|
| Rechnungsarten `rechnung`, `abschlag`, `schluss`, `gutschrift` (`Rechnung.rechnungsart`) | fertig |
| Abschlag aus Angebot, in % oder Netto-Betrag, kumulative 100-%-Grenze, Sperre gegen Parallelanlage | fertig |
| Schlussrechnung mit **Netto-Anrechnung**: je Abschlag eine Abzugsposition mit den Steuerfeldern des Abschlags, Rest-USt ergibt sich über die Steuergruppen; Mischsteuersätze getrennt | fertig |
| Anrechnung auch ohne Angebot (über Vorgang/Kunde), gezielte Auswahl, Prüfung beim Versand | fertig |
| **Teilstorno** als Gutschrift mit Mengenobergrenze, mehreren Steuergruppen, Grund; Original bleibt gültig | fertig |
| Offene-Posten-Regel (Zahlungen + Gutschriften), Mahnwesen mahnt nur den Rest | fertig |
| Stornosperren (angerechneter Abschlag, Rechnung mit Gutschrift), Komplettstorno als Gegenbeleg | fertig |
| E-Rechnung: Typcode 386 (ZUGFeRD) bzw. 326 (XRechnung, BR-DE-17), 381 Gutschrift, BT-25-Bezug, Hinweis angerechneter Abschläge | fertig |
| GoBD: unveränderliches PDF/XML-Archiv mit SHA-256 beim Versand, Audit-Log | fertig |
| Frontend: `AngebotAbrechnung`, `AbschlagSheet`, `GutschriftSheet`, Filter nach Rechnungsart | fertig |

**Konsequenz für diesen Auftrag:** Es braucht kein neues Rechnungs-Fundament. Das Konzept
beschreibt, was zur praxistauglichen Bau-/Handwerksabrechnung **noch fehlt**, und lässt den
bewährten Steuerkern (`steuer_service`, Netto-Anrechnung) bewusst unangetastet.
Vorab zu tun: PHASE_6-Hinweis berichtigen (Phase 0 unten).

## 2. Verbleibende Lücken (aus dem Code abgeleitet)

| # | Lücke | Beleg |
|---|---|---|
| L1 | **Kein Zahlungsplan.** Jeder Abschlag wird von Hand angelegt; es gibt keine Planung („30 % bei Auftrag, 40 % bei Rohinstallation, Rest bei Abnahme“), keine Fälligkeitserinnerung | `rechnung_aus_angebot` nimmt nur Prozent oder Betrag |
| L2 | **Kein Leistungsstand.** Ein Abschlag ist eine Pauschalposition (`ABSCHLAG_EINHEIT = "psch"`). Keine Aufstellung „bisher / diese Rechnung / Rest“ je Angebotsposition, wie sie für prüfbare Abschläge (§ 632a BGB, VOB/B § 16) üblich ist | `rechnungsart_service.rechnung_aus_angebot`, Zweig `art == "abschlag"` |
| L3 | **Kein Sicherheitseinbehalt** (z. B. 5 % bis Abnahme/Gewährleistung, VOB/B § 17) | kein Feld, kein Konzept in Schluss-/OP-Regel |
| L4 | **Abschlag ist nur komplett stornierbar.** Eine Teilkorrektur („Betrag war zu hoch“) geht nur über Storno und Neuanlage; `erstelle_gutschrift` lehnt Abschläge ausdrücklich ab | Test `test_gutschrift_auf_abschlag_ist_nicht_moeglich` |
| L5 | **Verhalten bei Überzahlung** der Abschläge (Summe der Abschläge > Schlussbetrag, etwa weil Positionen am Schluss gekürzt wurden) ist nicht geklärt; ein negativer Schlussrechnungs-Saldo ist weder getestet noch dokumentiert | im Code nicht abgedeckt, **zuerst prüfen** (Phase 1) |
| L6 | **DATEV:** Abschläge werden wie Rechnungen gebucht (Buchungstext „Rechnung“), ohne Anzahlungskonten; Zahlungsbuchungen (OP-Ausgleich) fehlen insgesamt | `auswertung_service.py` (Buchungstext), `docs/konzepte/DATEV.md`, `BACKLOG.md` |
| L7 | **Steuerliche Einordnung** der Abschläge (Anzahlung vs. Teilleistung, Entstehung der USt bei Ist-/Soll-Versteuerung) ist nicht abgebildet | `steuer_service` kennt nur Kategorien, keine Versteuerungsart |
| L8 | Kundenportal und Mahnwesen kennen die Rechnungsart, aber nicht den **Abrechnungsstand** des Auftrags („Sie haben 70 % abgerechnet, 40 % bezahlt“) | `AngebotAbrechnung` zeigt `abgerechnet_netto`/Rest nur intern |

## 3. Zielbild

Ein Angebot (oder Auftrag) kann einen **Zahlungsplan** tragen. Aus dem Plan entstehen
Abschlagsrechnungen auf Knopfdruck oder zeitgesteuert als Entwurf. Optional beziffert ein
**Leistungsstand** je Angebotsposition, was abgerechnet wird. Die Schlussrechnung rechnet alles
an, zieht einen **Einbehalt** ab und weist ihn separat als offen aus. Das Ganze nutzt die
vorhandene Rechnungsart-Mechanik: **keine neue Rechnungsart**, sondern zusätzliche Quellen für
`abschlag`-Entwürfe.

## 4. Datenmodell (Migrationen ab `0116`, sequenziell; RLS-Policy + Trigger nach Vorlage)

### 4.1 Zahlungsplan (L1)
**`angebot_zahlungsplan_positionen`**: `id`, `mandant_id`, `angebot_id`, `position`,
`bezeichnung` („Rohinstallation abgeschlossen“), `prozent` **oder** `betrag_netto` (genau eines,
CHECK), `faellig_art` (`datum|manuell|vorgang_status`), `faellig_am` (Date),
`ausloeser_vorgang_id` + `ausloeser_status` (z. B. `abgeschlossen`), `status`
(`geplant|faellig|abgerechnet|entfallen`), `rechnung_id` (FK, gesetzt sobald der Entwurf entstand).
Summe der Prozent/Beträge je Angebot darf 100 % des Angebotsnetto nicht überschreiten
(Service-Prüfung wie bestehend, Sperre `FOR UPDATE` auf dem Angebot).

Der Plan ist **Planung, keine Buchung**: erst der erzeugte Abschlagsentwurf ist ein Beleg. Ein
Planpunkt zeigt per `rechnung_id` auf die Rechnung; wird diese storniert, wird er wieder
`geplant`.

### 4.2 Leistungsstand (L2), optional und abschaltbar
**`rechnung_leistungsstand`**: `id`, `mandant_id`, `rechnung_id` (Abschlag), `angebot_position_id`,
`fertig_prozent_bisher`, `fertig_prozent_neu`. Abschlagspositionen entstehen dann nicht als
Pauschale, sondern je Angebotsposition: `Betrag = Positionssumme × (neu − bisher) / 100`, Einheit
`psch`, Beschreibung mit Positionsbezug. „Bisher“ wird aus den nicht stornierten Abschlägen des
Angebots errechnet, nie frei eingegeben. Die Netto-Anrechnung in der Schlussrechnung bleibt
unverändert (Summe der Abschläge), die Aufstellung dient als Anlage im PDF.

### 4.3 Sicherheitseinbehalt (L3)
Spalte `angebote.einbehalt_prozent` (Numeric, NULL = keiner) bzw. am Vertrag/Auftrag übernommen.
Wirkung:
- Abschlag/Schluss: Zeile „Einbehalt X % (Sicherheit)“ mit **negativem Betrag, gleiche
  Steuerfelder** wie die Basis (Netto-Abzug, analog Abzugspositionen), damit die
  Gruppenrechnung stimmt. Die USt auf den Einbehalt wird erst mit dessen Freigabe fällig, daher
  ist die steuerliche Behandlung **vor Umsetzung mit der Steuerberatung zu klären** (F2).
- Freigabe des Einbehalts = **eigene Rechnung** (`rechnungsart='rechnung'` mit Bezug auf die
  Schlussrechnung) oder Auszahlungs-Planpunkt; keine Änderung der versendeten Schlussrechnung
  (GoBD).

### 4.4 Teilkorrektur Abschlag (L4)
Statt Gutschrift auf Abschlag (steuerlich unklar) bleibt der Weg **Storno + Neuanlage**, aber
mit Komfort: Aktion „Abschlag korrigieren“ erzeugt den Storno-Beleg und legt in einem Schritt
einen neuen Entwurf mit vorbelegten Werten an (`korrigiert_rechnung_id` als Verweis, nur
Anzeige). Keine neue Rechnungsart.

## 5. Verhalten und Regeln

- **Neuer Service** `abrechnungsplan_service.py` (Plan, Fälligkeit, Entwurfserzeugung); delegiert
  die Belegerstellung an `rechnungsart_service.rechnung_aus_angebot` (keine zweite Rechenlogik).
  `rechnungsart_service` wächst nicht weiter.
- **Entwurf nie automatisch versenden.** Auch zeitgesteuerte Planpunkte erzeugen höchstens einen
  Entwurf (Mandanteneinstellung `abschlag_entwurf_automatisch`, Standard aus: nur Erinnerung).
- **Fälligkeit** `vorgang_status`: Der Statuswechsel am Auslöser-Vorgang
  (`api/routes/vorgaenge.py`, Statuspfad) setzt den Planpunkt `faellig` und benachrichtigt;
  `datum`: Worker-Job (siehe 6).
- **Schlussrechnung aus Plan**: nutzt die vorhandene Anrechnung; offene Planpunkte (nicht
  abgerechnet) werden beim Erzeugen der Schlussrechnung angezeigt und ausdrücklich auf `entfallen`
  gesetzt oder bleiben Pflicht-Hinweis. Keine stillschweigende Verrechnung.
- **Überzahlung (L5)**: Ist Summe Abschläge > Schlussbetrag, muss die Schlussrechnung
  einen **negativen Restbetrag** tragen dürfen oder die Erstellung mit klarer Meldung sperren und
  auf eine Gutschrift zum Abschlag-Überhang verweisen. Entscheidung nach dem Prüfergebnis aus Phase 1.
- **Rundung**: ausschließlich `steuer_service.runde_cent`; Prozentabschläge rechnen vom
  Angebotsnetto, nicht vom Restbetrag (Reihenfolge der Abschläge darf das Ergebnis nicht ändern).
- **Mandant mit `Kleinunternehmer`**: Planpunkte funktionieren, Steuerfelder bleiben `E` wie im
  bestehenden `_steuer_aus_angebot`.

## 6. Worker

Täglicher Job `abschlag_faelligkeit` in `job_runner.TAEGLICHE_JOBS` (zustandsbasiert wie die
übrigen: ein nachgeholter Lauf erledigt alles Aufgelaufene):

1. Planpunkte `geplant` mit `faellig_am <= heute` auf `faellig` setzen.
2. Je neu fälliger Punkt `Notification` (neuer Typ `abschlag` in `NOTIFICATION_TYPEN`, CHECK in
   Migration erweitern) an Ersteller des Angebots bzw. Disponenten, SSE über `event_bus`.
3. Optional (Mandantenschalter) Entwurf erzeugen, Planpunkt-`rechnung_id` setzen.

Idempotenz: Statuswechsel `geplant → faellig` ist der Marker; ein zweiter Lauf findet nichts.

## 7. API (Auszug)

- `GET/PUT /api/angebote/{id}/zahlungsplan` (komplette Liste ersetzen, nur solange keine
  abgerechneten Punkte betroffen sind), Recht: `abrechnung_erstellen`.
- `POST /api/angebote/{id}/zahlungsplan/{pos}/abrechnen` → erzeugt den Abschlagsentwurf.
- `POST /api/rechnungen/{id}/korrigieren` (nur Abschlag; Storno + Neuentwurf in einer Transaktion).
- `GET /api/angebote/{id}` liefert zusätzlich `abgerechnet_netto`, `bezahlt_netto`, `einbehalt`,
  Planstand (heute teils vorhanden: `abgerechnet_netto`).
- Portal: `GET /api/portal/angebote/{id}/abrechnung` nur lesend (Phase 5).

## 8. Frontend

- `AngebotAbrechnung` (vorhanden): Zahlungsplan als Liste mit Statuschips (geplant/fällig/
  abgerechnet), Button „Abschlag erstellen“ pro Planpunkt statt freier Prozenteingabe;
  `AbschlagSheet` bleibt als Ad-hoc-Weg erhalten.
- Leistungsstand-Eingabe als Tabelle (Position, bisher %, neu %) im Sheet; Feld-App einfach,
  Office mit Raster. Nach `docs/DESIGN.md`, Dark Mode.
- Rechnungsdetail: Schlussrechnung zeigt „Angerechnete Abschläge“ mit Links (heute nur Positionen).

## 9. E-Rechnung, GoBD, DATEV

- **XRechnung/ZUGFeRD**: keine Änderung am Typcode (386/326/380/381/384 bleiben). Einbehalt als
  negative Zeile mit denselben Steuerkategorien; Prüfung gegen die vorhandenen Regeln (BR-CO-10,
  BR-S-08) per Test, **XML-Schematron-Lauf wie in `E_RECHNUNG_PRUEFUNG.md`** für die neuen Fälle
  (Abschlag je Position, Schluss mit Einbehalt) ergänzen. Leistungsstand-Aufstellung nur im PDF,
  nicht in der XML.
- **GoBD**: Planpunkte sind veränderbare Planungsdaten; belegrelevant ist erst die versendete
  Rechnung mit archiviertem PDF/XML (unverändert). Änderungen am Plan laufen durch den
  Audit-Pfad (`audit_service`) mit alt/neu. Kein Löschen abgerechneter Planpunkte.
  Verfahrensdoku `docs/konzepte/GOBD.md` um einen Absatz „Abschlagsplanung“ ergänzen.
- **DATEV** (L6): Buchungstext je Rechnungsart („Abschlag“, „Schlussrechnung“, „Gutschrift“)
  statt immer „Rechnung“. Optional Anzahlungskonten (SKR03/04) über Stammdaten-Mapping.
  Die Anrechnung braucht keine Sonderbuchung, weil die Schlussrechnung netto nur den Rest bucht
  (Abschlag und Rest ergeben zusammen den Erlös). Zahlungsbuchungen bleiben das bereits geführte
  Backlog-Thema und werden hier nicht mitgebaut. Abnahme durch Steuerberater/DATEV-Import-Test steht
  weiterhin aus (`DATEV.md`).

## 10. Umsetzungsphasen

0. **Doku berichtigen**: Hinweis in PHASE_6, `BACKLOG.md`/Analyse (trivial).
1. **Prüfung L5** (Überzahlung/negativer Saldo): Testfälle schreiben, Verhalten festlegen; kleine
   Korrektur im `rechnungsart_service`, falls nötig. Kann sofort starten.
2. **DATEV-Buchungstext je Rechnungsart** (klein, unabhängig).
3. **Zahlungsplan** (Migration, Service, API, Planansicht, Worker, Notification-Typ).
4. **Abschlag korrigieren** (Storno + Neuentwurf) und Aufstellung „angerechnete Abschläge“.
5. **Leistungsstand** je Position (optional, nach Rückmeldung zu Bedarf).
6. **Sicherheitseinbehalt** inkl. Freigabe-Rechnung (erst nach steuerlicher Klärung).
7. **Portal-Anzeige** des Abrechnungsstands.

Die Phasen 1–4 liefern den größten Alltagsnutzen bei geringem Risiko; 5–6 sind Baubranche-spezifisch
und hängen an eurem Kundenstamm.

## 11. Tests (Auswahl)

- Plan: Summe > 100 % abgelehnt; parallele Anlage; Prozent vs. Betrag (CHECK); Reihenfolge-
  unabhängige Rundung; Storno des Entwurfs setzt Planpunkt zurück.
- Worker: Fälligkeit einmalig, Nachholen nach Ausfall, kein Entwurf ohne Mandantenschalter.
- Leistungsstand: „bisher“ aus nicht stornierten Abschlägen; Storno eines Abschlags korrigiert den
  Stand; Summe neu ≤ 100 %.
- Einbehalt: Gruppenrechnung mit Mischsteuersätzen, XML-Konformität, Freigabe-Rechnung.
- Schluss mit Plan: offene Planpunkte erzwingen Entscheidung; keine doppelte Anrechnung.
- **Mandantentrennung/RLS** für alle neuen Tabellen; Recht `abrechnung_erstellen` an jedem
  neuen Endpunkt (Muster `test_neue_endpunkte_brauchen_das_recht_abrechnung_erstellen`).
- Migration up/down/up (Muster `test_migration_0108_up_down_up`).

## 12. Offene Fragen

- **F1** Wie rechnet ihr heute ab: überwiegend Pauschal-Abschläge (Phase 3 reicht) oder nach
  Leistungsstand (Phase 5 nötig)? Entscheidet, ob 5 überhaupt gebaut wird.
- **F2** Arbeitet ihr mit Sicherheitseinbehalt/VOB-Verträgen, und wie behandelt eure Steuerberatung
  Abschlag (Anzahlung vs. Teilleistung) und Einbehalt umsatzsteuerlich? Ohne Antwort bleibt L7 offen;
  das ist keine Rechtsberatung, die Klärung gehört vor Phase 6.
- **F3** Sollen Planpunkte automatisch Entwürfe erzeugen oder nur erinnern (Vorschlag: nur erinnern)?
- **F4** Soll der Kunde im Portal den Zahlungsplan sehen?
