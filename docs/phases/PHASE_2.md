# Phase 2 – Fachlicher Kern

## Was implementiert wurde

- **Datenmodell** (Migration `0002_fachlicher_kern`): `kunden`, `anlagen`,
  `vertraege`, `vorgaenge` (mit den zwei unabhängigen Dimensionen
  `abrechnungsart` × `leistungstyp`), `vorgang_events` (append-only
  Event-Stream/Chat) sowie `tags`/`tag_assignments`. Alle Tabellen mit
  Row Level Security nach demselben Muster wie Phase 1
  (`FORCE ROW LEVEL SECURITY` + Policy auf `mandant_id`).
- **`last_activity_at`-Trigger**: Ein DB-Trigger (`touch_vorgang_last_activity`)
  aktualisiert bei jedem INSERT auf `vorgang_events` automatisch
  `vorgaenge.last_activity_at` – das treibt später die Feed-Sortierung in
  Phase 3, ganz ohne Anwendungscode.
- **CRUD-APIs** für alle sechs Entitäten (`/api/kunden`, `/api/anlagen`,
  `/api/vertraege`, `/api/vorgaenge`, `/api/vorgaenge/{id}/events`,
  `/api/tags`), inkl. automatischer Nummernvergabe (`kundennummer`,
  `vorgangsnummer`), wenn der Client keine mitgibt.
- **Referenzielle Absicherung über Mandantengrenzen**: `anlage_id`,
  `kunde_id`, `vertrag_id`, `parent_vorgang_id` werden vor dem Schreiben per
  `session.get(...)` innerhalb der RLS-gescopten Session geprüft. Das ist
  nötig, weil FK-Constraint-Checks in Postgres mit den Rechten des
  Tabellenbesitzers laufen und damit RLS ignorieren – ein rein auf FKs
  gestütztes Modell könnte sonst über eine erratene ID einen Datensatz an
  einen fremden Mandanten "anhängen".
- **Status-Änderungen erzeugen automatisch Events**: Jeder `PATCH
  /api/vorgaenge/{id}`, der `status` ändert, schreibt einen
  `status_change`-Event in den Chat (`von`/`nach` im `payload`) und setzt
  `abgeschlossen_am`, sobald der Status `abgeschlossen` erreicht.
- **Idempotente Events**: `POST .../events` mit bereits bekannter
  `client_uuid` liefert den existierenden Event mit `200` statt einen neuen
  mit `409`/`201` zu erzeugen – Grundlage für die Offline-Outbox in Phase 4.
- **Tags**: Label-Normalisierung (`#Dringend` → `dringend`), System-Tags
  (`wiederkehrend`, `nachbestellen`, `ueberfaellig`, `gewaehrleistung`) sind
  nicht löschbar, polymorphe Zuordnung auf Kunde/Anlage/Vorgang.
- **Berechtigungen** (dokumentierte Annahmen, siehe unten): `super_admin`
  hat bewusst keinen direkten Zugriff auf fachliche Endpunkte – Zugriff läuft
  ausschließlich über "Login als Mandant" (Impersonation-Token trägt dann
  `role=mandant_admin`).
- **Tests**: 33 neue pytest-Tests (insgesamt 63), inkl. eines eigenen
  RLS-Isolationstests für die neuen Tabellen nach demselben Muster wie in
  Phase 1 (`test_phase2_rls_isolation.py`).
- **Seed-Skript erweitert**: Je Mandant 3 Kunden, 3–4 Anlagen, 1 Vertrag und
  7 Vorgänge – einer pro Status (`neu`, `geplant`, `in_arbeit`,
  `wartet_kunde`, `abgeschlossen`, `abgerechnet`, `storniert`), plus die vier
  System-Tags.

## Berechtigungsmodell dieser Phase (Entscheidung, nicht im Prompt spezifiziert)

| Ressource | mandant_admin | disponent | techniker |
|---|---|---|---|
| Kunden / Anlagen | lesen + schreiben | lesen + schreiben | nur lesen |
| Verträge (inkl. Konditionen) | lesen + schreiben | **kein Zugriff** | **kein Zugriff** |
| Vorgänge / Events | lesen + schreiben | lesen + schreiben | lesen + schreiben |
| Tags (Definition) | lesen + schreiben | lesen + schreiben | nur lesen |
| Tag-Zuweisung | lesen + schreiben | lesen + schreiben | lesen + schreiben |

Begründung: Abschnitt 8 der Vorgabe sagt explizit "disponent: kein Zugriff
auf Vertragskonditionen und Umsatzzahlen" und "techniker: keine Preise".
Da `konditionen` ein Feld des gesamten Vertrags ist (keine separate
Tabelle), wird der komplette `/api/vertraege`-Endpunkt statt einzelner Felder
eingeschränkt – granularere Feld-Level-Security wäre in dieser Phase
unverhältnismäßiger Aufwand. Die feingranulare "nur zugewiesene Vorgänge"-
Einschränkung für `techniker` (Abschnitt 8) ist noch nicht umsetzbar, weil
die Zuweisung eines Technikers zu einem Vorgang erst über Termine (Phase 5,
`termine.techniker_id`) entsteht – bis dahin sehen Techniker alle Vorgänge
des eigenen Mandanten.

## Wie es getestet wird

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest          # 63 Tests, inkl. RLS-Isolation
```

```bash
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend python -m app.seed
```

## Was offen bleibt

- **Feed mit Cursor-Pagination** (`GET /api/feed`), Vorgangs-Chat-UI, Suche/
  Typeahead, Profile, SSE, Benachrichtigungen – das ist laut Abschnitt 12
  Phase 3 ("Social-UX"). `GET /api/vorgaenge` in dieser Phase ist bewusst
  eine einfache Liste mit Offset/Limit und rollenabhängigem RLS-Filter,
  keine Cursor-Pagination.
- **Kein Frontend** in dieser Phase (nur Backend-CRUD-APIs, siehe Abschnitt
  12: "Phase 2 – Fachlicher Kern: ... CRUD-APIs" vs. "Phase 3 – Social-UX").
- Mängel, Angebote, Prüfzyklen, Termine, Zeiterfassung, Material – jeweils
  eigene Phasen (5/6/7).
- Volltextsuche/`pg_trgm`-Typeahead auf den neuen Tabellen ist noch nicht
  angebunden (Extension ist seit Phase 1 aktiviert, Nutzung folgt mit der
  Suche in Phase 3).
