# FieldVibe

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
| 4 – Feld-Tauglichkeit | ✅ siehe [`docs/phases/PHASE_4.md`](docs/phases/PHASE_4.md) |
| 5 – Steuerung | ✅ siehe [`docs/phases/PHASE_5.md`](docs/phases/PHASE_5.md) |
| 6 – Geschäftsprozesse | ✅ siehe [`docs/phases/PHASE_6.md`](docs/phases/PHASE_6.md) |
| 7 – Ausbau | ✅ siehe [`docs/phases/PHASE_7.md`](docs/phases/PHASE_7.md) |
| Nacharbeiten (kein Lastenheft-Abschnitt) | ✅ siehe [`docs/phases/PHASE_8.md`](docs/phases/PHASE_8.md) |

## Tech-Stack

- **DB**: PostgreSQL 16 (UUID-PKs, JSONB, Row Level Security, `pg_trgm`)
- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.x (async), Alembic, Pydantic v2
- **Frontend**: React 18 + TypeScript, Vite, TanStack Query, Tailwind CSS, PWA (Service Worker + IndexedDB-Offline-Outbox)
- **Auth**: JWT (Access + Refresh), Argon2id
- **Objektspeicher**: MinIO (S3-kompatibel) für Fotos
- **Deployment (lokal)**: Docker Compose, ein Container je Dienst

## Schnellstart

```bash
cp .env.example .env
# Secrets in .env ersetzen (siehe Kommentare in der Datei)

docker compose up -d --build
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend python -m app.seed   # Beispieldaten
```

Der `worker`-Container (Prüfzyklen-Scheduler + Mahnwesen, Phase 5/Nacharbeit)
startet automatisch mit `docker compose up`; er prüft stündlich, welche
Mandanten gerade ihre konfigurierte tägliche Uhrzeit erreichen (Default
03:00 UTC, pro Mandant einstellbar über `PATCH /api/mandant/einstellungen`).

- Frontend: http://localhost:5173
- Backend/Swagger: http://localhost:8000/docs

Details, Test-Anleitung und Anmeldedaten für die Beispieldaten stehen in
[`docs/phases/PHASE_1.md`](docs/phases/PHASE_1.md).

## Produktions-Deployment

Für einen eigenen vServer mit TLS (Caddy + Let's Encrypt) und
Backup-Automatisierung siehe [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).
Der obige Schnellstart mit `docker-compose.override.yml` ist **nur** für
lokale Entwicklung gedacht (offene DB/MinIO-Ports, kein TLS).

Für den schnellen Weg übernimmt `scripts/deploy.sh` die Schritte aus
`docs/DEPLOYMENT.md` automatisiert (Docker installieren, Secrets
generieren, Domains abfragen, Stack starten, Migrationen, ersten
Superadmin anlegen, Backup-Cron einrichten):

```bash
git clone https://github.com/derHofib/SocialCRM.git
cd SocialCRM
sudo ./scripts/deploy.sh
```

## Struktur

```
backend/    FastAPI-App, Alembic-Migrationen, pytest-Tests
frontend/   React-App: Super-Admin-Dashboard + Feld-App (Feed/Chat/Suche/...) + Kundenportal (/portal)
docs/phases/  Phasen-spezifische READMEs
docs/DEPLOYMENT.md             Produktions-Deployment (Abschnitt 15)
scripts/deploy.sh              Automatisiertes Produktions-Deployment (siehe docs/DEPLOYMENT.md)
scripts/uninstall.sh            Installation vollständig entfernen (siehe docs/DEPLOYMENT.md)
scripts/backup.sh, restore.sh  Backup-Automatisierung (siehe docs/DEPLOYMENT.md)
docker-compose.yml             Basis-Stack (Postgres, MinIO, Backend, Frontend, Worker)
docker-compose.override.yml    Lokale Entwicklung (Hot-Reload, offene Ports)
docker-compose.prod.yml        Produktions-Overlay (Caddy-Reverse-Proxy, TLS)
docker-compose.ip.yml          Produktions-Overlay ohne Domain (kein TLS, siehe docs/DEPLOYMENT.md)
Caddyfile                       Reverse-Proxy-Konfiguration für docker-compose.prod.yml
.env.example                    Dokumentierte Umgebungsvariablen
```
