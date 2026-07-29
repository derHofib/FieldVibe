# SocialCRM

Mandantenfähiges Auftragsmanagement- und CRM-System für einen
Elektro-Handwerksbetrieb: ein streng strukturiertes fachliches Datenmodell
(Mandant → Kunde → Anlage → Vertrag → Vorgang), bedient über eine
Social-Media-artige Oberfläche (Feed, Chat, Profile, Hashtags) für Monteure
im Feld.

Das Projekt wird phasenweise aufgebaut (siehe Projektvorgabe). Der aktuelle
Stand:

| Phase | Status |
|---|---|
| 1 – Fundament | ✅ siehe [`docs/phases/PHASE_1.md`](docs/phases/PHASE_1.md) |
| 2 – Fachlicher Kern | ✅ siehe [`docs/phases/PHASE_2.md`](docs/phases/PHASE_2.md) |
| 3 – Social-UX | ✅ siehe [`docs/phases/PHASE_3.md`](docs/phases/PHASE_3.md) |
| 4 – Feld-Tauglichkeit | offen |
| 5 – Steuerung | offen |
| 6 – Geschäftsprozesse | offen |
| 7 – Ausbau | offen |

## Tech-Stack

- **DB**: PostgreSQL 16 (UUID-PKs, JSONB, Row Level Security, `pg_trgm`)
- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.x (async), Alembic, Pydantic v2
- **Frontend**: React 18 + TypeScript, Vite, TanStack Query, Tailwind CSS
- **Auth**: JWT (Access + Refresh), Argon2id
- **Deployment (lokal)**: Docker Compose, ein Container je Dienst

## Schnellstart

```bash
cp .env.example .env
# Secrets in .env ersetzen (siehe Kommentare in der Datei)

docker compose up -d --build
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend python -m app.seed   # Beispieldaten
```

- Frontend: http://localhost:5173
- Backend/Swagger: http://localhost:8000/docs

Details, Test-Anleitung und Anmeldedaten für die Beispieldaten stehen in
[`docs/phases/PHASE_1.md`](docs/phases/PHASE_1.md).

## Struktur

```
backend/    FastAPI-App, Alembic-Migrationen, pytest-Tests
frontend/   React-App: Super-Admin-Dashboard + Feld-App (Feed/Chat/Suche/...)
docs/phases/  Phasen-spezifische READMEs
docker-compose.yml            Basis-Stack (Postgres, Backend, Frontend)
docker-compose.override.yml   Lokale Entwicklung (Hot-Reload, offene Ports)
.env.example                  Dokumentierte Umgebungsvariablen
```
