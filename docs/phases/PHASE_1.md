# Phase 1 – Fundament

## Was implementiert wurde

- **Projektgerüst**: `backend/` (FastAPI, SQLAlchemy 2.x async, Alembic, Pydantic v2)
  und `frontend/` (React 18 + TypeScript, Vite, TanStack Query, Tailwind CSS).
- **Docker Compose**: `postgres`, `backend`, `frontend` als eigene Container,
  `docker-compose.override.yml` für Hot-Reload in der lokalen Entwicklung.
- **Migrationen**: eine Alembic-Migration (`0001_initial_schema`) legt
  `mandanten`, `users`, `mandant_integrationen`, `audit_log` an, inklusive
  `updated_at`-Trigger und Extensions (`pgcrypto`, `pg_trgm`).
- **Mandantenfähigkeit**: Row Level Security auf allen vier Tabellen, mit
  `FORCE ROW LEVEL SECURITY` (notwendig, weil der App-DB-Nutzer Owner der
  Tabellen ist und Owner sonst RLS umgehen). Die Policy prüft
  `current_setting('app.current_mandant')` gegen `mandant_id` (bzw. `id` bei
  `mandanten` selbst), mit Ausnahme für `app.is_super_admin = true`.
- **Tenancy-Durchsetzung im Code**: `app/db/session.py` stellt zwei Session-
  Fabriken bereit:
  - `tenant_session(mandant_id, is_super_admin=False)` – für
    `mandant_admin`/`disponent`/`techniker`, setzt `SET LOCAL` (via
    `set_config(..., true)`) auf die Session-Variablen.
  - `system_session()` – bypass für `super_admin`-Requests, die
    Login-E-Mail-Suche (mandantenübergreifend nötig, da E-Mail global
    eindeutig ist) und Seed-/CLI-Skripte.
- **Auth**: JWT (Access/Refresh, `pyjwt`), Argon2id-Hashing (`argon2-cffi`),
  Login/Refresh/`me`-Endpunkte.
- **Impersonation ("Login als Mandant")**: `POST
  /api/admin/mandanten/{id}/impersonate` gibt ein zeitlich begrenztes,
  `mandant_admin`-skaliertes Token aus. `sub` bleibt der echte
  `super_admin`-User, sodass Aktionen während der Impersonation im
  Audit-Log korrekt dem echten Akteur zugeschrieben werden. Jede
  Impersonation erzeugt zwingend einen `login_als_mandant`-Eintrag in
  `audit_log`.
- **Super-Admin-Dashboard** (Frontend): Login, Mandanten-Verwaltung (Anlegen,
  Status ändern, Impersonation auslösen), Account-Verwaltung
  (mandantenübergreifend für `super_admin`, auf den eigenen Mandanten
  beschränkt für `mandant_admin`), Audit-Log-Ansicht. Impersonation zeigt ein
  dauerhaftes Warnband; die super_admin-only Ansichten (Mandanten,
  Audit-Log) werden während der Impersonation ausgeblendet, weil das
  Impersonation-Token dafür (korrekt) keine Berechtigung hat.
- **Isolationstest**: `backend/tests/test_rls_isolation.py` beweist über
  vier Wege, dass Mandant A niemals Daten von Mandant B lesen kann – u. a.
  durch direktes SQL mit absichtlich mandantenfremdem Filter innerhalb einer
  auf Mandant A gebundenen Session (RLS blockt auf DB-Ebene, unabhängig vom
  Anwendungscode).
- **Seed-Skript** (`app/seed.py`): zwei Mandanten ("Elektro Müller GmbH",
  "Blitz Elektrotechnik e.K.") mit je einem `mandant_admin`, einem
  `disponent` und zwei `techniker`, plus ein plattformweiter `super_admin`.
- **CLI** (`app/cli.py`): `create-super-admin` fragt das Passwort interaktiv
  ab (nicht als Argument, siehe Abschnitt 15.5).
- **Tests**: 30 pytest-Tests (Auth, Mandanten-CRUD, User-CRUD,
  Berechtigungsgrenzen, Impersonation/Audit-Log, RLS-Isolation) – alle grün
  gegen echtes PostgreSQL 16.

## Wie es startet

```bash
cp .env.example .env
# Secrets in .env ersetzen, z. B.:
#   openssl rand -base64 48   # für JWT_SECRET
#   openssl rand -base64 24   # für POSTGRES_PASSWORD

docker compose up -d --build
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend python -m app.seed   # Beispieldaten, optional
```

- Backend: http://localhost:8000 (Swagger UI unter `/docs`)
- Frontend: http://localhost:5173 (Vite Dev-Server via Override) bzw. Port
  4173 im Produktions-Build ohne Override
- Health-Check: `GET /healthz`

Anmeldedaten nach `python -m app.seed` (Passwörter über
`SEED_SUPER_ADMIN_PASSWORD` / `SEED_USER_PASSWORD` konfigurierbar, Default
siehe `app/seed.py`):

| Rolle | E-Mail |
|---|---|
| super_admin | `superadmin@socialcrm.example.de` |
| mandant_admin (Müller) | `admin@mueller.example.de` |
| disponent (Müller) | `dispo@mueller.example.de` |
| techniker (Müller) | `technik1@mueller.example.de`, `technik2@mueller.example.de` |
| mandant_admin (Blitz) | `admin@blitz.example.de` |
| … | analog für `blitz.example.de` |

Für den ersten produktiven Start: `docker compose run --rm backend python -m
app.cli create-super-admin --email admin@firma.de --name "Vorname Nachname"`
(Passwort wird interaktiv abgefragt).

### Backend-Tests lokal ausführen

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
# Erwartet eine erreichbare Postgres-Instanz (Standard: localhost:5432,
# Rolle "socialcrm", Passwort "socialcrm"); legt "socialcrm_test" bei Bedarf
# selbst an und migriert sie.
python -m pytest
```

### Frontend lokal

```bash
cd frontend
npm install
npm run dev      # Dev-Server auf :5173
npm run build    # Typecheck (tsc -b) + Produktions-Build
```

## Was offen bleibt

- **Fachliches Datenmodell** (Kunden, Anlagen, Verträge, Vorgänge,
  Event-Stream, Tags) folgt in Phase 2.
- **Social-UX** (Feed, Chat, Suche, Profile, SSE) folgt in Phase 3 – aktuell
  zeigt die Oberfläche für `mandant_admin`/`disponent`/`techniker` bewusst
  nur einen Platzhalter-Hinweis.
- **`mandant_integrationen`**: Tabelle existiert (inkl. RLS), aber es gibt
  noch keine CRUD-Endpunkte/UI dafür – das ist laut Abschnitt 7.4 Teil des
  Super-Admin-Dashboards, aber nicht Teil des in Abschnitt 12 definierten
  Phase-1-Umfangs ("Mandanten- und Account-Verwaltung"). Secret-Verschlüsselung
  (`secret_ref`) ist als Spalte vorbereitet, die Vault/KMS-Anbindung folgt mit
  den ersten echten Integrationen.
- **Abschnitt 15 (vServer-Deployment)**: Provisionierungs-Skripte, Caddy/
  nginx-Konfiguration, Backup-Automatisierung sind bewusst noch nicht Teil
  dieser Phase – `docker-compose.yml` deckt aktuell nur die lokale
  Entwicklung ab. Das wird sinnvollerweise angegangen, sobald mehr
  fachliche Phasen stehen und es tatsächlich etwas Vorzeigbares zu deployen
  gibt.
- Der Docker-Compose-Stack selbst konnte in dieser Umgebung nicht mit einem
  laufenden Docker-Daemon durchgetestet werden (kein Zugriff auf
  `/var/run/docker.sock` in der Ausführungsumgebung dieser Änderung); Backend
  und Frontend wurden stattdessen direkt (venv/npm) gegen eine echte
  PostgreSQL-16-Instanz getestet – inklusive eines Browser-End-to-End-Checks
  (Login, Mandant anlegen, Account anlegen, Impersonation samt Banner,
  Audit-Log). Vor dem ersten Produktivstart empfiehlt sich ein
  `docker compose up -d --build` zur Kontrolle der Container-Definitionen.
