# Konzept: SLA- und Reaktionszeit-Management

Status: **Entwurf zur Abstimmung** (nichts umgesetzt) – Stand: 31.10.2026

## 1. Anlass und Ziel

Wartungsverträge und Störungsdienste versprechen dem Kunden Zeiten: „Reaktion binnen 2 Stunden,
Behebung binnen 24 Stunden, Mo–Fr 7–17 Uhr“. FieldVibe kennt dafür bisher nur lose Bausteine
(siehe 2). Ziel:

1. Je Vorgang gibt es **zwei Fristen**: Reaktionsfrist (bis zur ersten Mitarbeiter-Reaktion) und
   Lösungsfrist (bis zum Abschluss).
2. Die Fristen folgen aus einer **SLA-Richtlinie**, die am Vertrag hängt (Fallback: Mandanten-Standard)
   und nach Priorität und Geschäftszeiten rechnet.
3. Der Worker **eskaliert in Stufen** (Warnung, Verletzung, Eskalation an Vorgesetzte), ohne dass
   jemand Listen durchsuchen muss.
4. Die **Erfüllungsquote** ist auswertbar (Vertrag, Kunde, Techniker, Zeitraum).

Nicht Ziel in V1: vertragliche Vertragsstrafen/Gutschriften automatisch berechnen, Kunden per SMS
informieren, freie Regel-Engine (siehe Punkt 1 der Analyse, „Workflow-Engine“; SLA wird bewusst
fest verdrahtet, damit es nicht auf die Engine warten muss).

## 2. Ist-Stand (im Code geprüft)

| Baustein | Fundort | Eignung für SLA |
|---|---|---|
| `Vorgang.faelligkeit_am`, `prioritaet` (1–5, 5 = höchste), `wiedervorlage_am` | `models/vorgang.py` | Fälligkeit ist ein freies Wunschdatum, keine berechnete Frist; Priorität ist die richtige Eingangsgröße |
| `Vertrag.konditionen` (JSONB, nur Stundensatz/Anfahrt), `laufzeit_von/bis`, `aktiv` | `models/vertrag.py` | Ort für die Zuordnung; Freitext-JSONB ist für SLA zu lose → eigene Spalte |
| Vorgangsstatus `neu → … → abgeschlossen`, `wartet_kunde` | `models/vorgang.py` | `wartet_kunde` ist der natürliche **Uhr-Stopp** |
| `VorgangEvent` (Kommentar, Status, Termin …) mit Autor | `models/vorgang_event.py` | Quelle für „erste Reaktion“ |
| `VorgangAnfrage` (Kundenportal) | `models/vorgang_anfrage.py` | Fristbeginn kann der Anfrageeingang sein |
| Feiertage je Bundesland, Soll-Arbeitszeiten | `services/arbeitszeit_service.py` (`feiertage_fuer`), `models/arbeitszeit.py`, `Mandant.bundesland` | Wiederverwendbar für Geschäftszeit-Rechnung |
| Worker-Takt: jede Minute, Systemjobs `stuendlich`/`taeglich`, Zustand in `job_laeufe` | `services/job_runner.py`, `worker.py` | SLA braucht einen **feineren Takt** (siehe 6) |
| `Notification` (Typ `frist`), SSE über `event_bus`, Mail über `mail_outbox_service.enqueue_email` | `models/notification.py`, `services/` | Eskalationskanäle sind vorhanden |
| Vorgesetztenkette | Organigramm (`models/organigramm.py`, `services/organigramm_service.py`) | Empfänger „Vorgesetzter“ |
| `services/eskalation_service.py` | – | **Achtung Namensfalle:** das ist der Rechte-Eskalationsschutz, nichts mit SLA. Neuer Service heißt `sla_service.py` |

Lücke: Es gibt weder eine Frist-Definition noch eine Messung, ob sie eingehalten wurde.

## 3. Fachliche Regeln

### 3.1 Richtlinie
Eine Richtlinie hat einen Namen, einen **Kalender** und eine **Zieltabelle je Priorität**:

```
Priorität 5 (dringend):  Reaktion  30 min,  Lösung   4 h
Priorität 4:             Reaktion  60 min,  Lösung   8 h
Priorität 3 (normal):    Reaktion   4 h,    Lösung   2 Arbeitstage
Priorität 2/1:           Reaktion   1 Arbeitstag, Lösung 5 Arbeitstage
```

Einheit der Ziele ist **Minuten Geschäftszeit** (Arbeitstage werden beim Anlegen in Minuten
umgerechnet: Tageslänge der Geschäftszeit). Ein Ziel darf leer sein (= keine Frist dieser Art).

Kalender: `rund_um_die_uhr` oder `geschaeftszeiten` mit Zeitfenstern je Wochentag (z. B. Mo–Fr
07:00–17:00, Zeitzone des Mandanten) plus Schalter `feiertage_ausnehmen` (nutzt
`feiertage_fuer(mandant.bundesland, jahr)`). Rund-um-die-Uhr ist die Variante für
Bereitschaftsverträge, Geschäftszeiten für normale Wartung.

### 3.2 Zuordnung (Vorrang von oben nach unten)
1. `Vorgang.sla_richtlinie_id` explizit gesetzt (Ausnahme durch Dispo).
2. Richtlinie des **Vertrags** (`Vorgang.vertrag_id` → `Vertrag.sla_richtlinie_id`).
3. **Mandanten-Standard** (Richtlinie mit `ist_standard`), falls aktiviert.
4. Sonst: keine SLA, alle SLA-Felder am Vorgang bleiben NULL und nichts eskaliert.

Vertrag nicht aktiv oder außerhalb `laufzeit_von/bis` am Meldezeitpunkt → Stufe 2 greift nicht.

### 3.3 Uhr
- **Start**: Eingang. Bei Vorgang aus Portal-Anfrage `vorgang_anfragen.created_at`, sonst
  `vorgaenge.created_at`. Nicht der Zeitpunkt der Annahme, sonst verbrennt die Anfrage-Bearbeitung
  Zeit, die der Kunde nicht sieht.
- **Reaktion erfolgt** (`sla_reagiert_am`), sobald das erste dieser Ereignisse von einem
  **Mitarbeiter** (nicht Kunde, Portal, System) vorliegt: Übernehmen/Zuweisen mit Termin, Kommentar,
  Termin angelegt, Statuswechsel weg von `neu`. Reine Zuweisung ohne Aussage zählt nicht
  (Entscheidung E1).
- **Pause**: Status `wartet_kunde` hält beide Uhren an (der Ball liegt beim Kunden). Beim Verlassen
  läuft die Uhr mit der **Restzeit** weiter; die Fälligkeit wird neu berechnet, nicht um
  Kalenderzeit verschoben (sonst falsch bei Geschäftszeiten).
- **Ende Lösung** (`sla_geloest_am`): Status `abgeschlossen`, `abgerechnet` oder `storniert`.
  Wiederöffnung setzt die Lösung zurück, die Uhr läuft mit Restzeit weiter. `storniert` zählt nicht
  in die Quote.
- **Prioritätswechsel**: Fristen werden mit den neuen Zielen **ab Eingang** neu gerechnet, abzüglich
  bereits verbrauchter Zeit. Eine Höherstufung kann dadurch sofort überfällig sein – gewollt und im
  Verlauf sichtbar (Event `system`).

### 3.4 Eskalationsstufen
Je Richtlinie und Fristart beliebig viele Stufen, jede mit **Fortschritt in %** der Frist und
Aktion. Standard-Vorlage:

| Stufe | Schwelle | Aktion |
|---|---|---|
| Warnung | 75 % | Notification an Zugewiesenen (sonst Dispo/Admin) |
| Verletzung | 100 % | Notification an Zugewiesenen + Dispo, Mail an Dispo, Vorgang in Feed/Filter rot |
| Eskalation | 150 % bzw. +X min | Notification und Mail an Vorgesetzten laut Organigramm (Fallback Admin) |

Jede Stufe feuert **genau einmal je Vorgang** (Idempotenz über `sla_eskalationen`, siehe 4); ein
Neuberechnen der Frist nach Prioritäts- oder Pausenwechsel setzt nur noch nicht gefeuerte Stufen
zurück. Kunden-Mails bei Verletzung sind in V1 **nicht** vorgesehen (E2).

## 4. Datenmodell (Migration `0116_sla`, RLS-Policy + Trigger nach Vorlage der Migrationen)

**`sla_richtlinien`**: `id`, `mandant_id`, `name`, `beschreibung`, `aktiv`, `ist_standard`
(höchstens eine je Mandant, partieller Unique-Index), `kalender` (`rund_um_die_uhr|geschaeftszeiten`),
`geschaeftszeiten` JSONB (Wochentag → Liste von `[von, bis]`), `feiertage_ausnehmen`, `ziele` JSONB
(`{"5": {"reaktion_min": 30, "loesung_min": 240}, …}`, per Pydantic validiert, Prioritäten 1–5),
Zeitstempel/Soft-Delete wie andere Stammdaten.

**`sla_eskalationsstufen`**: `id`, `mandant_id`, `richtlinie_id`, `frist_art` (`reaktion|loesung`),
`schwelle_prozent`, `aktion` (`benachrichtigen|mail`), `empfaenger` (`zugewiesener|dispo|vorgesetzter|admin`),
`position`.

**`vertraege`**: neue Spalte `sla_richtlinie_id` (FK, nullable).

**`vorgaenge`** (Snapshot, damit eine spätere Richtlinienänderung laufende und abgeschlossene
Vorgänge nicht rückwirkend verändert): `sla_richtlinie_id`, `sla_start_am`,
`sla_reaktion_faellig_am`, `sla_loesung_faellig_am`, `sla_reagiert_am`, `sla_geloest_am`,
`sla_pausiert_seit`, `sla_reaktion_rest_min`, `sla_loesung_rest_min` (Restminuten für Pause),
`sla_ergebnis` (`erfuellt|verletzt|NULL`). Partieller Index auf die beiden Fälligkeiten
`WHERE sla_geloest_am IS NULL AND sla_pausiert_seit IS NULL`, damit der Worker nicht scannt.

**`sla_eskalationen`** (additiv, nie geändert): `id`, `mandant_id`, `vorgang_id`, `stufe_id`,
`ausgeloest_am`; Unique `(vorgang_id, stufe_id)` ist die Idempotenz. Dient zugleich als
Revisionsspur für „wann wurde wen gewarnt“.

`NOTIFICATION_TYPEN` bekommt `sla` (CHECK-Constraint in derselben Migration erweitern, Downgrade
entfernt nur Neues). `VorgangEvent`-Typ `system` für „SLA verletzt“ im Verlauf, kein neuer Typ.

## 5. Berechnung (`services/sla_service.py`, `services/sla_kalender.py`)

- `sla_kalender.add_geschaeftsminuten(start, minuten, richtlinie, bundesland) -> datetime` und
  `geschaeftsminuten_zwischen(a, b, …) -> int`. Reine Funktionen ohne DB, gut testbar: Wochenende,
  Feiertag, Start außerhalb der Geschäftszeit (Uhr beginnt am nächsten Fenster), Sommerzeitwechsel
  (Berechnung in lokaler Zeit des Mandanten, Speicherung UTC).
- `sla_service.initialisieren(session, vorgang)`: Richtlinie auflösen, Snapshot und Fälligkeiten
  setzen. Aufgerufen bei `create_vorgang`, Anlage aus Portal-Anfrage, `folge_auftrag_erstellen`,
  Daueraufträge (Worker) und bei Vertragszuordnung per PATCH.
- `sla_service.bei_ereignis(session, vorgang, ereignis)`: Reaktion erkennen, Pause/Fortsetzen,
  Abschluss/Wiederöffnung, Prioritätswechsel. Hängt an **einer** Stelle im bestehenden
  Statuswechsel-Code in `api/routes/vorgaenge.py` (`update_vorgang`) und in
  `vorgang_event_service`, nicht verstreut.
- Jede Änderung der SLA-Felder läuft über diese Funktionen; kein anderer Code schreibt `sla_*`.

## 6. Worker

Neuer Job `sla_eskalation` mit neuer Taktung **`viertelstuendlich`** in `job_runner.SYSTEM_JOBS`
(bisher nur `stuendlich`/`taeglich`; der Tick läuft ohnehin minütlich, ergänzt wird nur der Slot in
`ist_faellig`). Ablauf je Lauf, mandantenübergreifend über `system_session`:

1. Kandidaten per Index: offene, nicht pausierte Vorgänge, deren Fortschritt irgendeine noch nicht
   gefeuerte Stufenschwelle erreicht hat (Fortschritt = verbrauchte / gesamte Geschäftsminuten,
   aus Fälligkeit zurückgerechnet).
2. Pro Stufe `INSERT … ON CONFLICT DO NOTHING` in `sla_eskalationen`; nur bei tatsächlichem Insert
   Notification/Mail/SSE auslösen (Mehrfach-Worker-sicher, zusätzlich `FOR UPDATE SKIP LOCKED` wie in
   `scheduler_service.run_wiedervorlage_scheduler`).
3. Bei Verletzung `sla_ergebnis` nicht endgültig setzen, erst bei Abschluss (eine Reaktion
   „zu spät“ ist trotzdem eine verletzte Reaktionsfrist, wird aber getrennt je Fristart gewertet).
4. Mail über `mail_outbox_service.enqueue_email` (Retry und Versand nach Commit sind dort gelöst).

Fehler eines Mandanten dürfen die anderen nicht blockieren (Muster der bestehenden Mandantenjobs).

## 7. API

Unter `api/routes/sla.py` (Modul-Flag `sla` pro Mandant, wie `postfach`):

- `GET/POST/PATCH/DELETE /api/sla/richtlinien` inkl. Stufen; Löschen nur, wenn keine offenen
  Vorgänge darauf verweisen (sonst `aktiv=false`).
- `PATCH /api/vertraege/{id}` und `POST/PATCH /api/vorgaenge` nehmen `sla_richtlinie_id` an.
- `VorgangRead` bekommt ein berechnetes Objekt `sla`: `{status: ok|gefaehrdet|verletzt|pausiert|keine,
  reaktion_faellig_am, loesung_faellig_am, reaktion_erfuellt, …}`. Der Status wird bei der
  Ausgabe aus den Snapshot-Feldern abgeleitet, nicht gespeichert.
- Listenfilter `?sla=gefaehrdet|verletzt` und Sortierung nach nächster Fälligkeit an
  `GET /api/vorgaenge` (Index siehe 4; Pagination und `X-Total-Count` wie überall).
- `GET /api/sla/auswertung?von=&bis=&vertrag_id=&kunde_id=&techniker_id=`: Erfüllungsquote
  Reaktion/Lösung, Anzahl, Median/90-Perzentil der Reaktionszeit, aus `sla_ergebnis` und den
  Snapshot-Feldern (kein Abgleich mit der Live-Richtlinie).

Rechte: neuer Bereich `sla` mit `ansehen` und `verwalten` in `core/rechte_registry.py`; Richtlinien
anlegen nur mit `verwalten`. Ausnahme zuweisen (`sla_richtlinie_id` am Vorgang) braucht
`verwalten`, damit ein Techniker seine Frist nicht wegkonfigurieren kann. Technikern bleibt
„sichtbar, nicht änderbar“.

## 8. Frontend

- **Feld-App** (`pages/feld/`): am Vorgangskopf und in der Liste ein Badge mit Restzeit
  („noch 1 h 20 min“, rot bei Verletzung, grau bei Pause) nach `docs/DESIGN.md` (Icon-Badge,
  Farbpalette, Dark Mode). Liste: Filter „SLA gefährdet/verletzt“.
- **Office** (`office/vorgaenge/`): Spalte „SLA“ im Raster, sortierbar; Dispo-Board markiert gefährdete
  Vorgänge; neue Seite **SLA-Richtlinien** (Einstellungen, Stufen-Editor, Vorschau „Priorität 4,
  Meldung Fr 16:30 → Reaktion fällig Mo 07:30“) und **SLA-Auswertung** (Quote je Vertrag/Monat).
- **Vertrag** (Formular): Auswahl der Richtlinie.
- **Kundenportal**: V1 nur lesend die zugesagte Reaktionszeit am Vorgang anzeigen (ohne interne
  Eskalationsstufen). Optional, deshalb eigene Phase.

## 9. Umsetzungsphasen (je eigener Commit, je mit Tests)

1. **Kalender-Kern**: `sla_kalender` mit Tests (reine Funktionen, keine Migration).
2. **Datenmodell und Richtlinien-CRUD**: Migration 0116, Modelle, Schemas, API, Rechte, RLS-Test.
3. **Vorgangsintegration**: `initialisieren`/`bei_ereignis`, Snapshot, `sla` im `VorgangRead`, Filter.
4. **Worker und Eskalation**: Takt `viertelstuendlich`, Job, Stufen, Benachrichtigungen/Mails.
5. **Frontend** Feld/Office + Richtlinien-Editor.
6. **Auswertung** und optional Portal-Anzeige.

Eine Stufe ist einzeln auslieferbar; ohne Phase 4 zeigen Badges und Filter bereits Nutzen.

## 10. Tests (Auswahl)

- Kalender: Mo–Fr 7–17, Meldung Fr 16:30 + 60 min → Mo 07:30; Feiertag in der Mitte; Start am
  Sonntag; Zeitumstellung; Rund-um-die-Uhr.
- Uhr: Pause `wartet_kunde` verlängert korrekt; Wiederöffnung; Prioritätswechsel in beide Richtungen;
  Reaktion zählt nur von Mitarbeitern (nicht Portalnutzer, nicht System-Event).
- Zuordnung: Vorrang Vorgang > Vertrag > Standard; inaktiver/abgelaufener Vertrag.
- Worker: Stufe feuert genau einmal (zwei parallele Läufe), nachgeholter Lauf nach Ausfall feuert
  verpasste Stufen einmalig, pausierte und abgeschlossene Vorgänge bleiben ruhig.
- **Mandantentrennung**: Richtlinie/Stufen/Eskalationen eines Mandanten für anderen unsichtbar
  (RLS), Worker eskaliert nie an Nutzer eines fremden Mandanten.
- Migration up/down/up wie `test_migration_0108_up_down_up`.

## 11. Entscheidungen und offene Fragen

- **E1** Reaktion = erste inhaltliche Mitarbeiter-Aktion (Kommentar, Termin, Statuswechsel), nicht
  bloße Zuweisung. Alternative „schon Zuweisung zählt“ ist trivial umstellbar (eine Bedingung).
- **E2** Keine automatischen Kundenmails bei Verletzung in V1.
- **E3** Snapshot am Vorgang statt Live-Berechnung: Richtlinienänderungen wirken nur auf neue
  Vorgänge; ein „Fristen neu berechnen“-Knopf je Richtlinie ist Phase-2-Option.
- **F1** (Frage an Dennis) Welche Zeiten gelten für Bereitschaftsverträge: reicht
  „rund um die Uhr“ je Richtlinie, oder braucht ihr Bereitschaftskalender je Techniker? Letzteres
  wäre ein eigenes Thema (Dienstplan).
- **F2** (Frage an Dennis) Soll die Priorität automatisch aus dem Leistungstyp `stoerung` hoch
  gesetzt werden, damit SLA-Vorgänge nicht an vergessener Prioritätspflege scheitern? Heute ist die
  Voreinstellung 3.
- **F3** Gelten SLA auch für Daueraufträge (Wartungstermine)? Vorschlag: nein, dort steuert die
  Toleranz in `prioritaet_service`; SLA nur für Störungen/Anfragen (Richtlinien-Flag `leistungstypen`).
