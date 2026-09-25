# Konzept: Arbeitszeiterfassung 2.0

Status: **Entwurf zur Abstimmung** (noch nicht umgesetzt)
Stand: 25.09.2026

## 1. Anlass und Ziel

Zeiteinträge an einem Vorgang müssen nachträglich bearbeitbar sein. Konkret:

- **Tätigkeit nachtragen**, wenn der Timer ohne Beschreibung gestartet/gestoppt wurde.
- **Zeiten korrigieren** (Timer vergessen zu stoppen, zu spät gestartet).
- **Fahrzeit mit gefahrenen Kilometern** erfassen.

Daraus ergibt sich die Frage, wie Zeiterfassung insgesamt aufgestellt sein soll:
wer darf was wann ändern, wie bleibt das nachvollziehbar, und wie fließt es in
Abrechnung und Auswertung (inkl. der neuen Ebene Projekt → Auftrag → Vorgang).

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

---

## 4. Zielbild

### Beteiligte und typische Fälle

- **Techniker (Feld-App)**
  - Stoppt den Timer und wird gleich gefragt, was er gemacht hat. Das Feld
    darf leer bleiben.
  - Tippt später auf einen Eintrag und ergänzt die Tätigkeit oder korrigiert
    Uhrzeiten.
  - Erfasst die Fahrt zum Kunden: Dauer, gefahrene km, Fahrzeug
    (vorbelegt mit seinem zugewiesenen Fahrzeug).
  - Trägt Zeit direkt am Vorgang nach („+ Zeit nachtragen“).
- **Büro/Dispo (Office)**
  - Sieht im Vorgang alle Zeiten inkl. km und Summen.
  - Korrigiert einen fremden Eintrag, gibt dabei einen Grund an, und die
    Änderung wird protokolliert.
  - Sieht offene Punkte: „Einträge ohne Tätigkeit“ und „Timer läuft seit über
    12 Std“.
- **Buchhaltung**
  - Übernimmt Arbeitszeit, Fahrzeit und Fahrtkosten als Rechnungsvorschläge.
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
| `abgerechnet_rechnung_id` | FK → `rechnungen.id`, nullable | vom Server gesetzt (siehe Abschnitt 8), sperrt den Eintrag |
| `geloescht_am` / `geloescht_von` | Soft-Delete (`SoftDeleteMixin`) | Löschen landet im Papierkorb statt hart |

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
| `aktion` | `angelegt`, `geaendert`, `geloescht`, `wiederhergestellt` |
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
| `zeit_korrekturfrist_tage` | `14` | So lange darf der Techniker eigene Einträge selbst ändern. Danach nur noch das Büro. `NULL` = unbegrenzt |

---

## 6. Regeln

### 6.1 Wer darf was?

| Aktion | Techniker (eigener Eintrag) | Büro (fremder Eintrag) |
|---|---|---|
| Nachtragen | ja | ja, **für** einen Techniker (neu, mit Grund) |
| Tätigkeit ändern | ja, auch bei laufendem Timer | ja, mit Grund |
| Zeiten/Kategorie/km ändern | ja, innerhalb der Korrekturfrist | ja, mit Grund |
| Löschen | ja, innerhalb der Frist (Papierkorb) | ja, mit Grund (Papierkorb) |
| Laufenden Timer beenden | ja | ja („Timer beenden“, mit Grund; Ende frei wählbar) |

„Büro“ heißt: Recht `mitarbeiterverwaltung.bearbeiten`. Dieses Recht steuert
schon heute die Einsicht in fremde Zeiten, deshalb wird kein neuer
Rechte-Bereich angelegt. `mandant_admin` darf es immer.

### 6.2 Sperren

Ein Eintrag ist für **alle** gesperrt, wenn:

1. `abgerechnet_rechnung_id` gesetzt ist und die Rechnung nicht mehr im
   Status `entwurf` ist, **oder**
2. sein Vorgang im Status `abgerechnet` oder `storniert` ist.

Vereinheitlichung (behebt L6): Nachtragen und Bearbeiten bleiben bei Status
`abgeschlossen` **erlaubt**, denn Nachtragen nach Abschluss ist genau der
Anwendungsfall. Nur der Timer bleibt dort wie bisher gesperrt.

Bei `abgerechnet`/`storniert` sind Timer, Nachtragen und Bearbeiten gesperrt.
Korrekturen laufen dann über eine Rechnungskorrektur und liegen außerhalb
dieses Konzepts.

### 6.3 Plausibilitätsprüfungen

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
  08:10–08:40  Fahrt · 21 km · WE-FV 123                    ›
  08:40–11:15  Sabine Müller · Zählerschrank getauscht       ›
  11:15–11:45  Fahrt · 21 km                                 ›
Gestern
  14:00–15:30  ⚠ Tätigkeit fehlt                             ›
```

- **Jede Zeile ist antippbar** und öffnet das Bearbeiten-Sheet (bestehende
  `Sheet`-Komponente).
- **Sheet „Zeiteintrag“**:
  - Art: Arbeit / Fahrt (Segmented Control)
  - Datum, Von, Bis
  - Tätigkeit: Textfeld plus Vorschlag-Chips (zuletzt benutzte Tätigkeiten
    und Standardtexte je Leistungstyp)
  - nur bei Arbeit: `abrechenbar`, Stundensatz (LV)
  - nur bei Fahrt: km, Fahrzeug (vorbelegt)
  - unten: „Löschen“ und bei Bedarf der Hinweis „Gesperrt – bereits
    abgerechnet“
- **Nach „Stoppen“** öffnet sich automatisch ein kleines Sheet: „Was hast du
  gemacht?“. Es enthält nur das Tätigkeitsfeld mit Chips sowie „Speichern“
  und „Später“. Das trifft L1 im Alltag am direktesten.
- Einträge ohne Tätigkeit bekommen einen dezenten Hinweis `⚠ Tätigkeit fehlt`
  (Statusfarbe plus Symbol plus Text, siehe `docs/DESIGN.md`).
- Gesperrte Einträge zeigen ein Schloss-Symbol und öffnen das Sheet nur zum
  Lesen.

### 7.2 Office: Vorgang → Tab Zeit (dichte Ansicht)

- Die bestehende Tabelle bekommt die Spalten **Art**, **km**,
  **abrechenbar** und **Status** (offen / gesperrt), dazu eine Summenzeile
  (Arbeit, Fahrt, km).
- Ein Klick auf eine Zeile öffnet das neue **SeitenPanel** (von rechts,
  ziehbar). Darin: dasselbe Formular wie im Sheet, zusätzlich der
  Reiter **„Verlauf“** mit dem Änderungsprotokoll.
- Buttons „+ Zeit nachtragen“ und „+ Fahrt erfassen“. Im Office gibt es dabei
  zusätzlich die Auswahl **„für Mitarbeiter“**.
- Bei fremden Einträgen ist das Feld **Grund** Pflicht.

### 7.3 Auftrag- und Projekt-Panel

Neuer Block „Zeit“ mit den Summen über alle zugehörigen Vorgänge: Arbeitszeit,
Fahrzeit, km, davon abrechenbar und davon bereits abgerechnet. Nur Anzeige,
bearbeitet wird am Vorgang.

### 7.4 Team-Zeiten / Statistik

- Einträge in der Tagesliste werden für das Büro bearbeitbar (gleiches
  SeitenPanel).
- Filter „Ohne Tätigkeit“ und „Timer läuft > 12 Std“.
- CSV-Export und Wochenzettel-PDF bekommen die Spalten **km** und **Fahrzeug**.

---

## 8. Abrechnung

Rechnungsvorschläge (`positionen_vorschlaege_fuer_vorgang`) werden
erweitert, gesteuert über `fahrzeit_abrechnung` (Abschnitt 5.3):

| Einstellung | Zusätzlicher Vorschlag |
|---|---|
| `zeit` | „Fahrzeit“, Summe der Stunden, Einzelpreis leer oder aus LV |
| `km` | „Fahrtkosten“, Summe km × `km_satz_netto` |
| `zeit_und_km` | beide |
| `keine` | nichts (wie heute) |

Wird ein Vorschlag in eine Rechnung übernommen, setzt der Server bei allen
beteiligten Einträgen `abgerechnet_rechnung_id`. Wird die Position wieder
entfernt, solange die Rechnung im Entwurf ist, wird das Feld zurückgesetzt.
Damit ist L5 geschlossen, und Zeit wird nicht doppelt abgerechnet.

Offene Zeit, die noch nicht abgerechnet ist, zeigt der Vorgang als Hinweis
an („2:15 Std noch nicht abgerechnet“).

---

## 9. Recht und Nachvollziehbarkeit

*(Technische Einschätzung, keine Rechtsberatung.)*

- **Arbeitszeiterfassung:** Seit EuGH 2019 und BAG 2022 besteht für
  Arbeitgeber eine Pflicht zur Erfassung der Arbeitszeit. Nachträgliche
  Änderungen sollten nachvollziehbar sein, dafür ist das Protokoll aus 5.2
  da, und Löschen geht nur noch in den Papierkorb.
- **Fahrzeit als Arbeitszeit:** Heute zählt Fahrzeit als Arbeitszeit
  (`fahrzeit` steht nicht in `ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT`).
  Das bleibt so, ist aber in Abschnitt 11 als Frage aufgenommen.
- **Fahrtenbuch:** Die km-Angabe ist **kein** steuerliches Fahrtenbuch. Das
  müsste lückenlos, zeitnah und unveränderbar sein und km-Stände, Ziel und
  Zweck enthalten. Die Oberfläche soll das nicht suggerieren. Die
  Beschriftung ist deshalb „gefahrene km“, nicht „Fahrtenbuch“.
- **GoBD:** Abgerechnete Einträge sind die Grundlage einer Rechnung und
  werden deshalb gesperrt (6.2).
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

### Stufe 2 – Fahrten mit km (löst L3, L9)
- Migration: `km`, `fahrzeug_id`, `quelle`
- „+ Fahrt erfassen“, Felder im Formular, Fahrzeug-Vorbelegung
- Summen im Zeit-Tab, km in CSV und Wochenzettel

### Stufe 3 – Protokoll und Korrektur durch das Büro (löst L4, L7)
- Migration: `zeiterfassung_aenderungen`, Soft-Delete, Korrekturfrist
- Office: fremde Einträge bearbeiten und nachtragen, Pflichtfeld Grund,
  „Timer beenden“ für fremde Timer, Reiter „Verlauf“
- Team-Zeiten: bearbeitbar, Filter

### Stufe 4 – Abrechnung und Auswertung (löst L5, L8)
- Mandanten-Einstellungen `km_satz_netto`, `fahrzeit_abrechnung`
- Vorschläge „Fahrzeit“ und „Fahrtkosten“, `abgerechnet_rechnung_id` setzen
  und zurücksetzen
- Zeit-Summen im Auftrag- und Projekt-Panel, Hinweis „noch nicht abgerechnet“

### Später / optional
- Fahrt-Timer („Fahrt starten“ → beim Stoppen km abfragen)
- Tätigkeits-Vorlagen je Mandant verwalten
- Erinnerung (Push) bei Timer läuft > X Std

---

## 11. Offene Fragen

1. **km je Fahrt oder je Tag?** Vorschlag: je Fahrt (Hin- und Rückweg sind
   zwei Einträge oder einer mit „Hin + Rück“). Was passt zu eurem Alltag?
2. **Wer darf fremde Zeiten korrigieren?** Vorschlag: Recht
   `mitarbeiterverwaltung.bearbeiten` plus Admin. Reicht das?
3. **Korrekturfrist für Techniker:** 14 Tage sinnvoll? Oder unbegrenzt bis
   zur Abrechnung?
4. **Fahrzeit abrechnen:** gar nicht, nach Zeit, nach km oder beides? Gibt es
   eine Anfahrtspauschale im Leistungsverzeichnis, die stattdessen greifen
   soll?
5. **Fahrzeit = Arbeitszeit?** Heute ja (zählt in Wochen- und Monatsstunden).
   So lassen?
6. **Tätigkeit Pflicht?** Vorschlag: nicht Pflicht, aber sichtbarer Hinweis
   und Filter. Oder beim Stoppen erzwingen?
7. **Fahrzeug erfassen:** nötig, oder reichen km?
8. **Reihenfolge:** Mit Stufe 1 starten (größter Alltagsnutzen, keine
   Migration) und Stufe 2 direkt danach?
