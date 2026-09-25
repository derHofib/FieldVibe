# Konzept: Arbeitszeiterfassung 2.0

Status: **Entwurf zur Abstimmung** (noch nicht umgesetzt) – Überarbeitung 1: Buchungsablauf
Stand: 25.09.2026

## 1. Anlass und Ziel

Zeiteinträge an einem Vorgang müssen nachträglich bearbeitbar sein. Konkret:

- **Tätigkeit nachtragen**, wenn der Timer ohne Beschreibung gestartet/gestoppt wurde.
- **Zeiten korrigieren** (Timer vergessen zu stoppen, zu spät gestartet).
- **Fahrzeit mit gefahrenen Kilometern** erfassen.

Daraus ergibt sich die Frage, wie Zeiterfassung insgesamt aufgestellt sein soll:
wer darf was wann ändern, wie bleibt das nachvollziehbar, und wie fließt es in
Abrechnung und Auswertung (inkl. der neuen Ebene Projekt → Auftrag → Vorgang).

**Grundprinzip (abgestimmt):** Erfasste Zeit ist zunächst nur am Vorgang
**vermerkt**. Abrechenbar wird sie erst, wenn sie **aktiv gebucht** wurde.
Der Techniker merkt seine Einträge zur Buchung vor, das Büro prüft und bucht.
Als Arbeitszeit des Mitarbeiters zählt sie trotzdem sofort ab dem Erfassen.
Die Buchung betrifft nur die Abrechnung beim Kunden.

---

## 2. Ist-Stand

### Datenmodell (`backend/app/models/zeiterfassung.py`)

| Feld | Bedeutung |
|---|---|
| `vorgang_id` | optional (seit Migration 0050), Pflicht nur bei Kategorie `auftrag` |
| `techniker_id` | wessen Zeit |
| `start_at` / `ende_at` | `ende_at = NULL` heißt: Timer läuft |
| `kategorie` | `auftrag`, `verwaltung`, `fahrzeit`, `schulung`, `pause`, `urlaub`, `krankheit`, `sonstiges` |
| `taetigkeit` | Freitext, optional |
| `abrechenbar` | fließt in Rechnungsvorschläge |
| `lv_position_id` | optionaler Stundenverrechnungssatz aus dem Leistungsverzeichnis |

Es gibt **kein** Feld für Kilometer, Fahrzeug, Herkunft (Timer oder manuell)
oder Abrechnungsstatus.

### API (`backend/app/api/routes/zeiterfassung.py`)

| Endpunkt | Was geht |
|---|---|
| `POST /start`, `POST /{id}/stop` | Timer, nur Kategorie `auftrag`, gesperrt bei geschlossenem Vorgang |
| `POST /manuell` | Nachtragen mit beliebiger Kategorie |
| `PATCH /{id}` | Bearbeiten, **nur eigene** Einträge, nicht bei laufendem Timer |
| `DELETE /{id}` | **hartes** Löschen, nur eigene Einträge |
| `GET` | Liste, Statistik, CSV-Export, Wochenzettel-PDF |

### Frontend

- Vorgang → Tab **Zeit**: Timer starten/stoppen und eine reine Leseliste
  (Desktop: Tabelle). **Kein Bearbeiten, kein Nachtragen am Vorgang.**
- `ZeiterfassungManuellForm.tsx`: Nachtragen über die Zeiterfassungs-/
  Statistikseite, nicht aus dem Vorgang heraus.
- `zeiterfassungApi.aktualisieren` und `.loeschen` existieren in
  `frontend/src/api/endpoints.ts`, werden aber **nirgends in der Oberfläche
  benutzt**. Das Backend kann also schon bearbeiten, die UI bietet es nur nicht an.

### Abrechnung (`backend/app/services/rechnung_service.py`)

Rechnungsvorschläge summieren abrechenbare `auftrag`-Zeit je Vorgang (mit
oder ohne Stundensatz). Fahrzeit fließt **nicht** ein. Ein Eintrag weiß nicht,
ob er schon auf einer Rechnung steht.

### Rechte (heute)

- Jeder erfasst nur die **eigene** Zeit (bewusste Entscheidung aus Phase 4).
- **Fremde** Zeiten **einsehen**: `mitarbeiterverwaltung.bearbeiten`
  (`darf_fremde_mitarbeiterdaten_einsehen`).
- **Fremde** Zeiten **bearbeiten**: niemand, auch nicht der Admin.

---

## 3. Lücken

| # | Lücke | Folge |
|---|---|---|
| L1 | Keine Bearbeiten-UI | Tätigkeit/Zeiten lassen sich praktisch nicht korrigieren |
| L2 | Kein Nachtragen direkt am Vorgang | Umweg über die Statistikseite, Vorgang muss dort gesucht werden |
| L3 | Keine km bei Fahrzeit | Fahrtkosten lassen sich nicht abrechnen oder auswerten |
| L4 | Kein Änderungsprotokoll, hartes Löschen | Nicht nachvollziehbar, wer wann welche Zeit geändert hat (Arbeitszeitrecht, Streitfälle mit Kunden) |
| L5 | Keine Sperre nach Abrechnung | Zeit, die schon auf einer Rechnung steht, kann noch geändert oder gelöscht werden |
| L6 | Uneinheitliche Sperrregel | Timer auf geschlossenem Vorgang gesperrt, Nachtragen/Bearbeiten aber nicht, auch nicht bei `abgerechnet` |
| L7 | Büro kann nicht korrigieren | Vergisst ein Techniker das Stoppen, kann nur er selbst den Eintrag reparieren |
| L8 | Keine Summen je Auftrag/Projekt | Neue Ebene Auftrag hat noch keine Zeitauswertung |
| L9 | Timer-Einträge und nachgetragene Einträge nicht unterscheidbar | Vertrauen in die Daten, Auswertung |
| L10 | Keine Freigabe vor der Abrechnung | Jede abrechenbare Zeit landet sofort in den Rechnungsvorschlägen, ungeprüft und auch mit leerer Tätigkeit |

---

## 4. Zielbild

### Beteiligte und typische Fälle

- **Techniker (Feld-App)**
  - Stoppt den Timer und wird gleich gefragt, was er gemacht hat. Das Feld
    darf beim Erfassen leer bleiben.
  - Tippt später auf einen Eintrag und ergänzt die Tätigkeit oder korrigiert
    Uhrzeiten.
  - Erfasst die Fahrt zum Kunden: Dauer, gefahrene km, Fahrzeug
    (vorbelegt mit seinem zugewiesenen Fahrzeug).
  - Trägt Zeit direkt am Vorgang nach („+ Zeit nachtragen“).
  - Markiert seine fertigen Einträge und klickt **„Zur Buchung vormerken“**.
- **Büro/Dispo (Office)**
  - Sieht im Vorgang alle Zeiten inkl. km, Summen und Buchungsstatus.
  - Prüft die vorgemerkten Einträge, markiert sie und klickt **„Buchen“**.
  - Nimmt eine Buchung bei Bedarf zurück („Buchung stornieren“, mit Grund).
  - Korrigiert einen fremden Eintrag, gibt dabei einen Grund an, und die
    Änderung wird protokolliert.
  - Sieht offene Punkte: „Zur Buchung vorgemerkt“, „Einträge ohne Tätigkeit“
    und „Timer läuft seit über 12 Std“.
- **Buchhaltung**
  - Sieht in den Rechnungsvorschlägen **nur gebuchte** Zeit.
  - Abgerechnete Einträge sind danach gesperrt.
- **Admin**
  - Stellt ein: km-Satz, ob und wie Fahrzeit abgerechnet wird, Korrekturfrist.

---

## 5. Datenmodell

### 5.1 Erweiterung `zeiterfassung`

| Neues Feld | Typ | Regel |
|---|---|---|
| `km` | `NUMERIC(7,1)`, nullable | nur bei `kategorie = 'fahrzeit'`, `>= 0` (CHECK) |
| `fahrzeug_id` | FK → `anlagen.id`, nullable | nur Anlagen mit `objekttyp = 'fahrzeug'`; nur bei Fahrzeit sinnvoll; Vorbelegung aus `FahrzeugZuweisung` |
| `quelle` | `TEXT`, `'timer' \| 'manuell'` | vom Server gesetzt, nie per API änderbar; Altbestand wird `'timer'` bei vorhandenem Vorgang-Event `zeit_start`, sonst `'manuell'` |
| `buchungsstatus` | `TEXT`, Default `'vermerkt'` | `'vermerkt' \| 'vorgemerkt' \| 'gebucht' \| 'abgerechnet'` (CHECK); ändert sich nur über die Buchungs-Endpunkte (6.1), nie per PATCH |
| `vorgemerkt_von` / `vorgemerkt_am` | FK → `users.id` / Zeitstempel, nullable | wer hat zur Buchung vorgemerkt |
| `gebucht_von` / `gebucht_am` | FK → `users.id` / Zeitstempel, nullable | wer hat gebucht |
| `abgerechnet_rechnung_id` | FK → `rechnungen.id`, nullable | vom Server gesetzt (siehe Abschnitt 8) |
| `geloescht_am` / `geloescht_von` | Soft-Delete (`SoftDeleteMixin`) | Löschen landet im Papierkorb statt hart |

`buchungsstatus` gibt es nur für Einträge **mit Vorgang**. Urlaub,
Krankheit, Pause, Schulung usw. ohne Vorgang werden nicht beim Kunden
abgerechnet und bleiben dauerhaft `vermerkt`. Buchen ist für sie nicht
möglich.

`abrechenbar` bleibt zusätzlich bestehen und bedeutet „soll dem Kunden
berechnet werden“. Ein gebuchter Eintrag mit `abrechenbar = false` (z. B.
Gewährleistung, Kulanz) ist geprüft und freigegeben, erscheint aber nicht in
den Rechnungsvorschlägen.

**Altbestand:** Bestehende Einträge an Vorgängen mit Status `abgerechnet`
werden zu `abgerechnet`. Alle übrigen Einträge mit Vorgang werden zu
`gebucht`, damit laufende Abrechnungen am Tag der Umstellung nicht plötzlich
ohne Zeitvorschläge dastehen. Nur neu erfasste Zeit startet als `vermerkt`.

Fahrzeit darf (wie heute schon technisch möglich) einen `vorgang_id` haben.
Dann wird die Fahrt dem Vorgang zugeordnet und erscheint dort.

Bewusst **kein** Fahrtenbuch mit Start-/End-km-Stand, Start/Ziel und Zweck.
Das wäre ein eigenes, steuerlich strenges Thema (siehe Abschnitt 9). `km`
ist hier nur eine Mengenangabe für Abrechnung und Auswertung.

### 5.2 Neue Tabelle `zeiterfassung_aenderungen` (Protokoll)

Nach dem Vorbild von `form_submission_audit`:

| Feld | Inhalt |
|---|---|
| `id`, `mandant_id` | Standard + RLS-Policy nach Muster aus Migration 0082/0083 |
| `zeiterfassung_id` | FK, `ON DELETE CASCADE` |
| `aktion` | `angelegt`, `geaendert`, `geloescht`, `wiederhergestellt`, `vorgemerkt`, `vormerkung_zurueckgezogen`, `gebucht`, `buchung_storniert`, `abgerechnet` |
| `feld`, `alter_wert`, `neuer_wert` | je geändertem Feld eine Zeile (JSONB-Werte) |
| `grund` | Pflicht, wenn jemand einen **fremden** Eintrag ändert |
| `geaendert_von`, `geaendert_am` | wer und wann |

Das Protokoll ist nur lesbar, über die API lässt sich nichts darin ändern
oder löschen.

### 5.3 Mandanten-Einstellungen (Erweiterung `mandanten`)

| Einstellung | Default | Zweck |
|---|---|---|
| `km_satz_netto` | `NULL` (aus) | €/km für Fahrtkosten-Vorschläge |
| `fahrzeit_abrechnung` | `'keine'` | `'keine' \| 'zeit' \| 'km' \| 'zeit_und_km'` |
| `zeit_korrekturfrist_tage` | `NULL` (keine) | Optional: so lange darf der Techniker eigene, noch **vermerkte** Einträge ändern. Möglicherweise überflüssig, weil Vormerken/Buchen die Grenze bildet (siehe offene Frage 3) |

---

## 6. Regeln

### 6.1 Buchungsablauf

```
vermerkt ──(Techniker: vormerken)──▶ vorgemerkt ──(Büro: buchen)──▶ gebucht ──(Rechnung)──▶ abgerechnet

Rückwege:
  vorgemerkt ──(zurückziehen)──────────▶ vermerkt
  gebucht    ──(Büro: stornieren)──────▶ vermerkt
  abgerechnet ─(Position entfernt, Rechnung noch Entwurf)─▶ gebucht
```

| Übergang | Wer | Voraussetzung |
|---|---|---|
| vermerkt → vorgemerkt | Techniker (eigene), Büro (alle) | Timer beendet, **Tätigkeit ausgefüllt**, Vorgang nicht `abgerechnet`/`storniert` |
| vorgemerkt → vermerkt („zurückziehen“) | Techniker (eigene), Büro | noch nicht gebucht |
| vorgemerkt → gebucht | Büro | |
| vermerkt → gebucht (direkt) | Büro | wie beim Vormerken (Timer beendet, Tätigkeit ausgefüllt); Techniker muss nicht vorgemerkt haben |
| gebucht → vermerkt („Buchung stornieren“) | Büro | noch nicht abgerechnet; **Grund Pflicht** |
| gebucht → abgerechnet | Server | beim Übernehmen in eine Rechnung (Abschnitt 8) |
| abgerechnet → gebucht | Server | Position wieder entfernt, solange die Rechnung `entwurf` ist |

Alle Übergänge gehen gesammelt über eigene Endpunkte, z. B.
`POST /api/zeiterfassung/vormerken`, `/buchen`, `/buchung-stornieren` mit
einer Liste von IDs. Es gilt alles oder nichts: Scheitert die Prüfung bei
einem Eintrag, bucht der Endpunkt keinen und nennt die betroffenen Einträge.
Jeder Übergang landet im Protokoll (5.2).

Die Tätigkeit ist **beim Erfassen freiwillig**, **beim Vormerken Pflicht**.
Das erzwingt keine Unterbrechung im Feld, sorgt aber dafür, dass keine Zeit
ohne Beschreibung beim Kunden abgerechnet wird.

### 6.2 Wer darf was?

„Büro“ heißt: Recht `mitarbeiterverwaltung.bearbeiten`. Dieses Recht steuert
schon heute die Einsicht in fremde Zeiten, deshalb wird kein neuer
Rechte-Bereich angelegt. `mandant_admin` darf es immer.

| Aktion | vermerkt | vorgemerkt | gebucht | abgerechnet |
|---|---|---|---|---|
| Techniker: eigene bearbeiten/löschen | ja (innerhalb Korrekturfrist) | nein, erst zurückziehen | nein | nein |
| Techniker: Tätigkeit ergänzen | ja, auch bei laufendem Timer | nein, erst zurückziehen | nein | nein |
| Büro: bearbeiten/löschen (mit Grund bei fremden) | ja | ja | nein, erst Buchung stornieren | nein |
| Büro: für einen Techniker nachtragen | ja (neuer Eintrag startet als `vermerkt`) | – | – | – |
| Büro: fremden laufenden Timer beenden | ja (mit Grund, Ende frei wählbar) | – | – | – |

### 6.3 Sperren durch den Vorgang

Unabhängig vom Buchungsstatus gilt:

- Vorgang `abgeschlossen`: Timer gesperrt (wie heute). Nachtragen,
  Bearbeiten, Vormerken und Buchen bleiben **erlaubt**, denn Nachtragen nach
  Abschluss ist genau der Anwendungsfall (behebt L6).
- Vorgang `abgerechnet` oder `storniert`: alles gesperrt. Korrekturen laufen
  dann über eine Rechnungskorrektur und liegen außerhalb dieses Konzepts.

### 6.4 Plausibilitätsprüfungen

| Prüfung | Art |
|---|---|
| Ende nach Start | Fehler (gibt es schon) |
| Start oder Ende in der Zukunft | Fehler |
| Dauer > 12 Std | Warnung, speichern trotzdem möglich |
| Überschneidung mit eigenem Eintrag | Warnung, speichern trotzdem möglich |
| `km` ohne Kategorie Fahrzeit | Fehler |
| `km > 1.500` | Warnung |
| Fahrzeug nicht vom Typ `fahrzeug` | Fehler |

Warnungen kommen wie bei den Terminen (`TerminWarnung`) als Liste in der
Antwort zurück und blockieren nicht.

---

## 7. Oberfläche

### 7.1 Feld-App: Vorgang → Zeit

```
ARBEITSZEIT                              Bisher 3:45 Std · 42 km
[ Tätigkeit (optional)            ] [ Zeit starten ]
[ + Zeit nachtragen ]  [ + Fahrt erfassen ]

Heute
☐ 08:10–08:40  Fahrt · 21 km · WE-FV 123        Vermerkt     ›
☐ 08:40–11:15  Zählerschrank getauscht          Vermerkt     ›
☐ 11:15–11:45  Fahrt · 21 km                    Vermerkt     ›
Gestern
  14:00–15:30  ⚠ Tätigkeit fehlt                Vermerkt     ›
  09:00–12:00  Leitung verlegt                  Gebucht 🔒   ›

[ 3 ausgewählt · Zur Buchung vormerken ]
```

- **Status je Eintrag** als Tag: Vermerkt (grau), Vorgemerkt (blau),
  Gebucht (grün, Schloss), Abgerechnet (Schloss). Farbe steht nie allein,
  immer mit Text (siehe `docs/DESIGN.md`).
- **Auswahl-Kästchen** nur bei eigenen, vermerkten, fertigen Einträgen.
  Ohne Tätigkeit ist das Kästchen deaktiviert mit Hinweis „Tätigkeit
  fehlt“. Die Aktionsleiste „Zur Buchung vormerken“ erscheint, sobald
  etwas ausgewählt ist.
- Vorgemerkte eigene Einträge bieten „Zurückziehen“ an.
- **Jede Zeile ist antippbar** und öffnet das Bearbeiten-Sheet (bestehende
  `Sheet`-Komponente).
- **Sheet „Zeiteintrag“**:
  - Art: Arbeit / Fahrt (Segmented Control)
  - Datum, Von, Bis
  - Tätigkeit: Textfeld plus Vorschlag-Chips (zuletzt benutzte Tätigkeiten
    und Standardtexte je Leistungstyp)
  - nur bei Arbeit: `abrechenbar`, Stundensatz (LV)
  - nur bei Fahrt: km, Fahrzeug (vorbelegt)
  - unten: „Löschen“, oder bei gesperrten Einträgen der Hinweis „Gebucht
    am … von …“ bzw. „Abgerechnet in Rechnung …“
- **Nach „Stoppen“** öffnet sich automatisch ein kleines Sheet: „Was hast du
  gemacht?“. Es enthält nur das Tätigkeitsfeld mit Chips sowie „Speichern“
  und „Später“. Das trifft L1 im Alltag am direktesten.
- Einträge ohne Tätigkeit bekommen einen dezenten Hinweis `⚠ Tätigkeit fehlt`
  (Statusfarbe plus Symbol plus Text, siehe `docs/DESIGN.md`).
- Gebuchte und abgerechnete Einträge zeigen ein Schloss-Symbol und öffnen
  das Sheet nur zum Lesen.

### 7.2 Office: Vorgang → Tab Zeit (dichte Ansicht)

```
☐ | Datum | Von–Bis | Mitarbeiter | Art | Tätigkeit | km | abr. | Status
───────────────────────────────────────────────────────────────────────────
Summe: Arbeit 6:45 · Fahrt 1:00 · 42 km   │ vermerkt 2:30 · vorgemerkt 3:15 · gebucht 2:00

[ Buchen (4) ]  [ Alle vorgemerkten buchen ]  [ Buchung stornieren ]
```

- Die bestehende Tabelle bekommt die Spalten **Mitarbeiter**, **Art**,
  **km**, **abrechenbar** und **Status**, dazu Auswahl-Kästchen und eine
  Summenzeile nach Art **und** nach Buchungsstatus.
- **Aktionsleiste fürs Büro:**
  - „Buchen“ (Auswahl)
  - „Alle vorgemerkten buchen“ (Abkürzung)
  - „Buchung stornieren“ (Auswahl gebuchter Einträge, fragt nach dem Grund)
- Vor dem Buchen zeigt ein kurzer Bestätigungsdialog Anzahl, Summe Stunden
  und km sowie Warnungen (z. B. Überschneidung, > 12 Std).
- Ein Klick auf eine Zeile öffnet das **SeitenPanel** (von rechts, ziehbar).
  Darin steht dasselbe Formular wie im Sheet und zusätzlich der Reiter
  **„Verlauf“** mit dem Änderungsprotokoll inkl. Buchungsschritten.
- Buttons „+ Zeit nachtragen“ und „+ Fahrt erfassen“. Im Office gibt es dabei
  zusätzlich die Auswahl **„für Mitarbeiter“**.
- Bei fremden Einträgen ist das Feld **Grund** Pflicht.

### 7.3 Neue Office-Seite „Zeiten buchen“

Arbeitsvorrat fürs Büro über **alle** Vorgänge, damit niemand jeden Vorgang
einzeln öffnen muss:

- Standardfilter: Status „vorgemerkt“
- Gruppiert nach Vorgang (Vorgangsnummer, Kunde, Auftrag/Projekt), darin die
  Einträge
- Weitere Filter: Mitarbeiter, Zeitraum, Kunde, Auftrag, Projekt, „vermerkt
  älter als X Tage“
- Dieselbe Aktionsleiste wie im Vorgang (Auswahl → Buchen / Stornieren),
  Zeilenklick öffnet das SeitenPanel
- Zähler in der Seitenleiste (Badge) mit der Anzahl vorgemerkter Einträge

### 7.4 Auftrag- und Projekt-Panel

Neuer Block „Zeit“ mit den Summen über alle zugehörigen Vorgänge:
Arbeitszeit, Fahrzeit und km, jeweils aufgeteilt nach vermerkt, vorgemerkt,
gebucht und abgerechnet. Das ist nur eine Anzeige, bearbeitet und gebucht
wird am Vorgang oder auf „Zeiten buchen“.

### 7.5 Team-Zeiten / Statistik

- Wochen- und Monatsstunden zählen **alle** erfassten Arbeitszeiten,
  unabhängig vom Buchungsstatus (abgestimmt, siehe Abschnitt 1).
- Die Tagesliste zeigt zusätzlich den Status-Tag je Eintrag. Einträge sind
  für das Büro bearbeitbar (gleiches SeitenPanel).
- Filter „Ohne Tätigkeit“, „Timer läuft > 12 Std“ und „Noch nicht vorgemerkt“.
- CSV-Export und Wochenzettel-PDF bekommen die Spalten **km**, **Fahrzeug**
  und **Status**.

---

## 8. Abrechnung

**Grundregel:** Rechnungsvorschläge (`positionen_vorschlaege_fuer_vorgang`)
berücksichtigen nur noch Einträge mit `buchungsstatus = 'gebucht'` und
`abrechenbar = true`. Vermerkte und vorgemerkte Zeit erscheint dort nicht.
Die Box zeigt stattdessen einen Hinweis wie „2:15 Std noch nicht gebucht →
Zeiten buchen“, damit nichts vergessen wird.

Zusätzlich werden die Vorschläge erweitert, gesteuert über
`fahrzeit_abrechnung` (Abschnitt 5.3):

| Einstellung | Zusätzlicher Vorschlag |
|---|---|
| `zeit` | „Fahrzeit“, Summe der Stunden, Einzelpreis leer oder aus LV |
| `km` | „Fahrtkosten“, Summe km × `km_satz_netto` |
| `zeit_und_km` | beide |
| `keine` | nichts (wie heute) |

Wird ein Vorschlag in eine Rechnung übernommen, setzt der Server bei allen
beteiligten Einträgen `abgerechnet_rechnung_id` und `buchungsstatus =
'abgerechnet'`. Wird die Position wieder entfernt, solange die Rechnung im
Entwurf ist, gehen die Einträge zurück auf `gebucht`. Damit ist L5
geschlossen, und Zeit wird nicht doppelt abgerechnet.

Der Vorgang zeigt als Hinweis „gebucht, aber noch nicht abgerechnet“ an
(z. B. „3:00 Std gebucht, noch nicht abgerechnet“).

---

## 9. Recht und Nachvollziehbarkeit

*(Technische Einschätzung, keine Rechtsberatung.)*

- **Arbeitszeiterfassung:** Seit EuGH 2019 und BAG 2022 besteht für
  Arbeitgeber eine Pflicht zur Erfassung der Arbeitszeit. Nachträgliche
  Änderungen sollten nachvollziehbar sein, dafür ist das Protokoll aus 5.2
  da, und Löschen geht nur noch in den Papierkorb. Der Buchungsstatus
  berührt das nicht: Arbeitszeit zählt ab dem Erfassen. Eine
  Buchungsstornierung ändert nur den Status, nie die Zeit selbst.
- **Fahrzeit als Arbeitszeit:** Heute zählt Fahrzeit als Arbeitszeit
  (`fahrzeit` steht nicht in `ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT`).
  Das bleibt so, ist aber in Abschnitt 11 als Frage aufgenommen.
- **Fahrtenbuch:** Die km-Angabe ist **kein** steuerliches Fahrtenbuch. Das
  müsste lückenlos, zeitnah und unveränderbar sein und km-Stände, Ziel und
  Zweck enthalten. Die Oberfläche soll das nicht suggerieren. Die
  Beschriftung ist deshalb „gefahrene km“, nicht „Fahrtenbuch“.
- **GoBD:** Gebuchte und abgerechnete Einträge sind die Grundlage einer
  Rechnung und werden deshalb gesperrt (6.2).
- **DSGVO:** Arbeitszeiten sind personenbezogen. Die bestehende
  Zugriffsregel (nur eigene Zeit oder Recht `mitarbeiterverwaltung.bearbeiten`)
  gilt unverändert auch für das Protokoll.

---

## 10. Umsetzung in Stufen

Jede Stufe ist für sich nutzbar und wird einzeln committet und getestet.

### Stufe 1 – Bearbeiten und Nachtragen am Vorgang (löst L1, L2, L6)
- **Frontend:**
  - Zeit-Tab (kompakt und dicht): Zeilen klickbar, Sheet bzw. SeitenPanel
    mit Formular
  - „+ Zeit nachtragen“, vorbelegt mit dem Vorgang
  - Tätigkeits-Sheet nach „Stoppen“
  - Hinweis „Tätigkeit fehlt“
  - Nutzt die vorhandenen `zeiterfassungApi.aktualisieren`/`.loeschen`
- **Backend:**
  - Tätigkeit auch bei laufendem Timer per PATCH änderbar
  - Sperre bei Vorgang `abgerechnet`/`storniert` für manuell, PATCH und
    DELETE
  - Prüfung „nicht in der Zukunft“
- **Tests:** Backend-Tests für die Sperrregeln; Playwright-Durchlauf
  Timer → Tätigkeit → Bearbeiten.

### Stufe 2 – Buchen: vormerken, prüfen, buchen (löst L10, L4, L7)
- **Migration:**
  - `buchungsstatus`, `vorgemerkt_von/_am`, `gebucht_von/_am`
    (Altbestand wie in 5.1)
  - `zeiterfassung_aenderungen` (Protokoll)
  - Soft-Delete
- **Backend:**
  - Endpunkte vormerken, zurückziehen, buchen und stornieren (gesammelt,
    alles oder nichts)
  - Sperrregeln je Status (6.2), Büro darf fremde Einträge bearbeiten und
    nachtragen (Grund Pflicht)
  - Rechnungsvorschläge nur noch aus **gebuchter** Zeit
- **Frontend:**
  - Status-Tags, Auswahl und Aktionsleiste im Zeit-Tab (Feld und Office)
  - Bestätigungsdialog beim Buchen, Reiter „Verlauf“ im SeitenPanel
  - Neue Office-Seite **„Zeiten buchen“** mit Zähler in der Seitenleiste
  - „Timer beenden“ für fremde Timer
- **Tests:**
  - Backend: alle Übergänge inkl. verbotener Übergänge,
    alles-oder-nichts, Protokolleinträge, Rechnungsvorschläge nur aus
    gebuchter Zeit
  - Playwright: Techniker merkt vor → Büro bucht → Techniker kann nicht
    mehr ändern

### Stufe 3 – Fahrten mit km (löst L3, L9)
- Migration: `km`, `fahrzeug_id`, `quelle`
- „+ Fahrt erfassen“, Felder im Formular, Fahrzeug-Vorbelegung
- Summen im Zeit-Tab, km in CSV und Wochenzettel

### Stufe 4 – Abrechnung und Auswertung (löst L5, L8)
- Mandanten-Einstellungen `km_satz_netto`, `fahrzeit_abrechnung`
- Vorschläge „Fahrzeit“ und „Fahrtkosten“
- `abgerechnet_rechnung_id` und Status `abgerechnet` beim Übernehmen setzen
  bzw. beim Entfernen der Position zurücksetzen
- Zeit-Summen je Status im Auftrag- und Projekt-Panel

### Später / optional
- Fahrt-Timer („Fahrt starten“ → beim Stoppen km abfragen)
- Tätigkeits-Vorlagen je Mandant verwalten
- Erinnerung (Push) bei Timer läuft > X Std

---

## 11. Offene Fragen

### Bereits abgestimmt

- Zeit ist erst **vermerkt** und wird erst nach aktiver **Buchung**
  abrechenbar.
- Der **Techniker merkt vor**, das **Büro bucht**.
- Gebucht wird per **Auswahl im Vorgang** (plus Sammelseite „Zeiten buchen“,
  siehe 7.3).
- Nach dem Buchen ist der Eintrag **gesperrt**. Das **Büro kann die Buchung
  zurücknehmen** (mit Grund, protokolliert).
- Vermerkte Zeit **zählt sofort als Arbeitszeit**.
- Das **Büro kann auch direkt buchen**, ohne dass der Techniker vorgemerkt
  hat (Übergang vermerkt → gebucht in 6.1).

### Noch offen

1. **„Büro“ = Recht `mitarbeiterverwaltung.bearbeiten`?** Oder soll Buchen
   ein eigenes Recht bekommen, z. B. Bereich `abrechnung`, Aktion
   `bearbeiten`? Dann könnte die Buchhaltung buchen, ohne die
   Mitarbeiterverwaltung zu dürfen.
2. **Tätigkeit Pflicht beim Vormerken und Buchen** (nicht beim Erfassen) –
   passt das?
3. **Korrekturfrist** für eigene, noch nicht vorgemerkte Einträge: Braucht
   es die neben dem Buchen überhaupt noch? Vorschlag: weglassen, das
   Vormerken ist die natürliche Grenze.
4. **Altbestand** bei der Umstellung als `gebucht` übernehmen (5.1), damit
   laufende Abrechnungen nicht stocken – einverstanden?
5. **km je Fahrt oder je Tag?** Vorschlag: je Fahrt (Hin- und Rückweg zwei
   Einträge oder einer mit „Hin + Rück“).
6. **Fahrzeit abrechnen:** gar nicht, nach Zeit, nach km oder beides? Gibt es
   eine Anfahrtspauschale im Leistungsverzeichnis, die stattdessen greifen
   soll?
7. **Fahrzeit = Arbeitszeit?** Heute ja (zählt in Wochen- und
   Monatsstunden). So lassen?
8. **Fahrzeug erfassen:** nötig, oder reichen km?
9. **Reihenfolge:** Stufe 1 (Bearbeiten, ohne Migration) zuerst und direkt
   danach Stufe 2 (Buchen)? Oder Buchen zuerst?
