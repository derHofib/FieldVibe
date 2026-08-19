# SocialCRM ("FieldVibe")

Multi-Tenant-CRM für Handwerksbetriebe mit Social-Feed-UX. Vier Frontends auf
einer Codebase: Super-Admin-Dashboard, Feld-App (Techniker, mobil/PWA),
Office-Ansicht (Büro/Dispo, Desktop), Kundenportal.

## Tech-Stack
- Backend: FastAPI, SQLAlchemy (async), Alembic, PostgreSQL mit Row-Level-
  Security (RLS) für Mandanten-Isolation
- Frontend: React + TypeScript + Vite + Tailwind, React Query, IndexedDB-
  Offline-Outbox
- Infra: Docker Compose (Postgres, MinIO/S3, Backend, Frontend, Worker,
  optional Caddy für TLS)

## Architektur/Verzeichnisse
- `backend/app/api/routes/` — Routen-Module, `backend/app/models/` — ORM-
  Modelle, `backend/alembic/versions/` — Migrationen, sequenziell
  nummeriert (`00NN_beschreibung.py`)
- `frontend/src/pages/` — Super-Admin-Seiten; `frontend/src/pages/feld/` —
  Feld-App; `frontend/src/office/` — Office-Ansicht (office.<domain>,
  dieselbe Codebase, Shell wird zur Laufzeit am Hostnamen gewählt);
  `frontend/src/portal/` — Kundenportal
- Entwicklungshistorie je Baustufe inkl. bewusster Design-Entscheidungen:
  `docs/phases/PHASE_1.md` … `PHASE_10.md` (jede endet mit "Was offen
  bleibt" — dort nachsehen, ob etwas als Lücke bekannt und bewusst
  zurückgestellt ist, bevor es als neuer Bug gemeldet wird)

## Domänen-Vokabular
Mandant=Tenant, Vorgang=Auftrag/Ticket, Anlage=Betriebsmittel beim Kunden,
Standort=Site, Pruefzyklus/Pruefmittel=Wartungsintervalle/Messgeräte,
Dauerauftrag=wiederkehrender Auftrag, Mangel=Defekt→Angebot→Rechnung-Workflow

## Konventionen
- Kommentare nur auf Deutsch, nur für nicht-offensichtliches WARUM (kein
  Was-Kommentar) — siehe bestehender Code als Maßstab für die Dichte
- RLS: jede neue Tabelle mit Mandanten-Bezug braucht Policy + Trigger,
  bestehende Migrationen als Vorlage nehmen
- Felder, die nicht direkt per PATCH erreichbar sein dürfen (z. B. Status
  "abgerechnet"), bekommen ein eigenes eingeschränktes Literal-Schema
  (`VorgangStatusSetzbar` vs. `VorgangStatus` in `schemas/vorgang.py`)

## Design/UI
Siehe `docs/DESIGN.md` für geltende UI-Konventionen (Icon-Badges +
Farbpalette, Dark-Mode-Pflicht, Bottom-Nav, Formulare). Vor neuen UI-
Elementen dort prüfen, ob ein bestehendes Pattern passt, statt ein neues
zu erfinden.

## Tests & Dev-Server
- Backend: `pytest` (`backend/tests/`, `pytest.ini` mit
  `asyncio_mode = auto`); `requirements-dev.txt` für Testabhängigkeiten
  (u. a. moto als S3-Mock)
- Frontend: `npm run dev` / `npm run build` (tsc -b) / `npm run test`
  (vitest) / `npm run lint` (tsc --noEmit)
- Kein CI vorhanden — Tests laufen nur manuell

## Docker/Deployment
- `backend/Dockerfile`: Multi-Stage (`base` → `deps` für Tests/CI,
  `runtime` als Produktions-Default). Produktions-Image enthält kein
  `tests/`, kein `moto`/`pytest`/`httpx`.
- Compose-Overlays: `docker-compose.override.yml` (lokal), `.prod.yml`
  (Caddy+TLS), `.ip.yml` (ohne Domain) — `.prod.yml` und `.ip.yml` nie
  gemeinsam verwenden.
- Bekannte Umgebungs-Eigenheit: In dieser Sandbox läuft kein Docker-Daemon
  (keine Root-Rechte) — `docker build`/`compose up` können hier nicht
  getestet werden, nur Syntax/Referenzen prüfen. Nicht erneut versuchen,
  `dockerd` zu starten.

## Git-Workflow
- Kleine, thematisch abgeschlossene Commits, sofort pushen — nicht auf ein
  großes Bündel warten. Grund: die Sandbox hat den Working Tree in dieser
  Session mehrfach unangekündigt zurückgesetzt; häufige Zwischenstände auf
  dem Remote begrenzen den Schaden, wenn das wieder passiert.

## Zusammenarbeit / Kommunikationsstil
- Antworten direkt und knapp, auf Deutsch, ohne unnötige Floskeln oder
  übertriebene Gliederung bei einfachen Fragen.
- Bei riskanten/größeren Änderungen (Infra, Docker, Migrationen) zuerst
  Ursache/Diagnose erklären, dann einen konkreten Vorschlag machen und auf
  explizite Zustimmung warten ("Ja bitte", "ja mach das" u. ä. reichen als
  Freigabe — danach den Task eigenständig bis zum Ende durchziehen, nicht
  nach jedem Teilschritt erneut nachfragen).
- Bei Doku-/Konfig-Änderungen (wie dieser Datei) erst einen Entwurf zeigen,
  auf kurzes Feedback reagieren und iterieren, bevor tatsächlich
  geschrieben/committet wird.
- Ehrlich über Grenzen der Umgebung sein statt Erfolg zu behaupten (z. B.
  ungetesteter Docker-Build klar als solcher benennen).
- Kurze, oft unvollständig formulierte Nachfragen sind normal — im
  Zweifel knapp rückfragen statt spekulativ draufzulegen.
