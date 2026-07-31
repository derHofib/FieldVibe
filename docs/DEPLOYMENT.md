# Deployment (Abschnitt 15)

Produktions-Deployment auf einem selbst verwalteten vServer. Getrennt von
der phasenweisen Feature-Entwicklung (Abschnitt 12) – dieses Dokument
beschreibt, wie der aktuelle Stand (Phase 1–5) auf einem eigenen Server
läuft, mit TLS und ohne offene Rohdaten-Ports.

## Architektur

Ein Caddy-Container ist der einzige nach außen erreichbare Dienst. Er
terminiert TLS (automatisch, Let's-Encrypt-Zertifikate) und reicht
Anfragen anhand der Subdomain weiter:

```
Internet ──443──▶ Caddy ──▶ DOMAIN_APP  → frontend:4173  (React-App)
                        ──▶ DOMAIN_API  → backend:8000   (FastAPI)
                        ──▶ DOMAIN_S3   → minio:9000     (Fotos, presigned URLs)
```

Postgres, MinIO, Backend und Frontend haben **keine** direkt aus dem
Internet erreichbaren Ports – nur Caddy auf 80/443. Drei Subdomains statt
einer mit Pfad-Präfixen, weil S3-Presigned-URLs Host *und* Pfad signieren;
ein nachträglich von Caddy gestripptes Pfad-Präfix würde die Signatur
brechen (siehe Kommentar in `app/services/storage_service.py`).

## Automatisiert: `scripts/deploy.sh`

Führt die Schritte 1–5 unten (bis auf DNS/Firewall-Freigabe auf
Provider-Seite) automatisiert aus: Docker installieren, `.env` mit
generierten Secrets und abgefragten Domains (oder Server-IP, siehe unten)
anlegen, Stack starten, Migrationen anwenden, ersten Superadmin anlegen,
Backup-Cron einrichten. Idempotent – kann später erneut ausgeführt werden,
um zu aktualisieren.

```bash
git clone https://github.com/derHofib/SocialCRM.git
cd SocialCRM
sudo ./scripts/deploy.sh
```

Setzt eine interaktive Shell voraus (fragt Domains/IP und die
Admin-Zugangsdaten ab) – **nicht** per `curl | bash` ausführen, sondern
das Repo erst klonen. Die restlichen Abschnitte dieses Dokuments erklären
dieselben Schritte manuell, falls du mehr Kontrolle brauchst oder etwas
schiefgeht.

## Ohne eigene Domain

Drei Wege, wenn (noch) keine Domain vorhanden ist:

1. **Kostenlose IP-Domain** (z. B. [sslip.io](https://sslip.io)): bei
   Server-IP `203.0.113.5` funktionieren `app.203.0.113.5.sslip.io`,
   `api.203.0.113.5.sslip.io`, `s3.203.0.113.5.sslip.io` als ganz normale
   DNS-Namen, ohne dass DNS-Einträge angelegt werden müssen – Let's
   Encrypt stellt dafür ein echtes Zertifikat aus. In `scripts/deploy.sh`
   (oder manuell unten) einfach diese Namen als Domains eintragen.
   Nachteil: bindet die Adresse an diese eine Server-IP.
2. **Echte Domain kaufen** (z. B. bei INWX, Namecheap, Cloudflare) – für
   dauerhaften Betrieb die sauberste Lösung, wenige Euro pro Jahr.
3. **Nur über die Server-IP, ohne TLS** – schnellster Weg, aber
   **unverschlüsselt**: Passwörter und Kundendaten laufen im Klartext
   übers Netz. Nur für einen kurzen Test oder ein abgeschottetes internes
   Netz vertretbar, nicht für echten Betrieb mit Kundendaten über das
   offene Internet.

Für Weg 3 gibt es `docker-compose.ip.yml` als Ersatz für
`docker-compose.prod.yml` (kein Caddy, Backend/Frontend/MinIO werden
direkt auf dem Server-Port veröffentlicht):

```bash
docker compose -f docker-compose.yml -f docker-compose.ip.yml up -d --build
```

Dabei in der `.env` setzen (Server-IP statt der Domains):
- `CORS_ORIGINS=["http://<server-ip>:4173"]`
- `VITE_API_BASE_URL=http://<server-ip>:8000`
- `S3_PUBLIC_URL_BASE=http://<server-ip>:9000`
- `FRONTEND_BASE_URL=http://<server-ip>:4173`

Firewall dann auf 22, 4173, 8000 und 9000 statt 22/80/443 begrenzen –
idealerweise zusätzlich auf bestimmte Quell-IPs, statt für das ganze
Internet zu öffnen:

```bash
ufw allow from <deine-ip> to any port 4173,8000,9000 proto tcp
```

`scripts/deploy.sh` fragt das beim ersten Lauf ab (Betriebsart "nur
Server-IP") und übernimmt genau diese Schritte automatisch.

## 1. Voraussetzungen

- Ein vServer mit Docker + Compose-Plugin:
  ```bash
  curl -fsSL https://get.docker.com | sh
  apt-get install -y docker-compose-plugin
  ```
- Drei DNS-A-Records, die auf die Server-IP zeigen, z. B.:
  ```
  app.example.de   A   <server-ip>
  api.example.de   A   <server-ip>
  s3.example.de    A   <server-ip>
  ```
- Firewall: nur SSH (22), HTTP (80, für die Let's-Encrypt-Challenge) und
  HTTPS (443) von außen erreichbar. Alles andere (5432, 8000, 9000, 9001)
  bleibt intern im Docker-Netzwerk – ohne das Prod-Overlay ist das
  ohnehin schon der Fall (`docker-compose.yml` published dafür keine
  Ports), das Overlay fügt nur Caddy hinzu.
  ```bash
  ufw allow 22/tcp
  ufw allow 80/tcp
  ufw allow 443/tcp
  ufw enable
  ```

## 2. Code holen und konfigurieren

```bash
git clone https://github.com/derHofib/SocialCRM.git
cd SocialCRM
cp .env.example .env
```

In `.env` mindestens setzen:
- `POSTGRES_PASSWORD`, `JWT_SECRET`, `MINIO_ROOT_PASSWORD` – je mit
  `openssl rand -base64 48` erzeugen, nicht die Beispielwerte übernehmen.
- `DOMAIN_APP`, `DOMAIN_API`, `DOMAIN_S3` – die drei Subdomains von oben.
- `CADDY_EMAIL` – für Let's-Encrypt-Benachrichtigungen.
- `CORS_ORIGINS=["https://<DOMAIN_APP>"]`
- `VITE_API_BASE_URL=https://<DOMAIN_API>`
- `S3_PUBLIC_URL_BASE=https://<DOMAIN_S3>`
- `DATABASE_URL`/`DATABASE_URL_SYNC` – Passwort aus `POSTGRES_PASSWORD`
  übernehmen (siehe Kommentare in der Datei).

`chmod 600 .env` nicht vergessen – die Datei enthält alle Secrets.

## 3. Starten

**Nicht** einfach `docker compose up` – das lädt automatisch
`docker-compose.override.yml` mit (reine Lokalentwicklung: Hot-Reload,
offene DB/MinIO-Ports). Stattdessen explizit die Basis- und die
Prod-Datei kombinieren:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Caddy braucht beim allerersten Start ein bis zwei Minuten, um die
Zertifikate zu holen (`docker compose logs -f caddy` zum Verfolgen).

## 4. Migrationen + Superadmin

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm backend alembic upgrade head

docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm backend python -m app.cli create-super-admin
```

`app.seed` (Demo-Daten mit bekannten Passwörtern) hier **nicht**
ausführen – das ist nur für lokale Entwicklung gedacht.

Danach: `https://<DOMAIN_APP>` aufrufen, mit dem Superadmin-Account
einloggen und den ersten echten Mandanten anlegen.

## 5. Backups

`scripts/backup.sh` sichert täglich per Host-Cron einen `pg_dump` der
Datenbank und ein Tar-Archiv der MinIO-Objektdaten nach `$BACKUP_DIR`
(Default aus `.env`: `/opt/fieldvibe-backups`), mit Rotation nach
`BACKUP_RETENTION_DAYS` (Default 14).

```bash
mkdir -p /opt/fieldvibe-backups
crontab -e
# Taeglich 02:30:
30 2 * * * /pfad/zu/SocialCRM/scripts/backup.sh >> /var/log/fieldvibe-backup.log 2>&1
```

Wiederherstellen:
```bash
scripts/restore.sh db backups/db-20260101-020000.sql.gz
scripts/restore.sh minio backups/minio-20260101-020000.tar.gz
```
Beide fragen vor dem Überschreiben explizit nach Bestätigung. Die
Backup-Dateien selbst sollten zusätzlich außerhalb des Servers gesichert
werden (z. B. per `rsync`/`rclone` auf einen zweiten Host) – ein Backup,
das nur auf demselben Server liegt, überlebt einen Festplattendefekt
oder eine kompromittierte Maschine nicht.

## 6. Updates

```bash
cd SocialCRM
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm backend alembic upgrade head
```

## 7. Deinstallieren

`scripts/uninstall.sh` entfernt eine Installation vollständig: alle
Container, die Docker-Volumes (**Postgres-Datenbank und alle
MinIO-Fotos!**), die gebauten Images und den Backup-Cron-Eintrag. Fragt
vor der Ausführung eine wörtliche Bestätigung ab und rührt vorhandene
Backups in `BACKUP_DIR` standardmäßig nicht an.

```bash
./scripts/uninstall.sh                  # Container + Volumes + Images + Cron
./scripts/uninstall.sh --keep-images    # Docker-Images behalten
./scripts/uninstall.sh --purge-backups  # zusätzlich auch alle Backups löschen
./scripts/uninstall.sh --remove-repo    # zusätzlich das ganze Repo-Verzeichnis löschen
```

Macht selbst keine Sicherung – vorher `scripts/backup.sh` ausführen, falls
die Daten noch gebraucht werden könnten.

## 8. Troubleshooting

- **Zertifikat wird nicht ausgestellt**: DNS-A-Records prüfen (müssen
  bereits vor dem ersten Start auf den Server zeigen), Port 80 muss von
  außen erreichbar sein (Let's Encrypt HTTP-01-Challenge). Logs:
  `docker compose logs caddy`.
- **`/healthz` liefert Fehler**: prüft DB-Verbindung und
  Objektspeicher-Erreichbarkeit sowie den Zeitstempel des letzten
  Prüfzyklen-Scheduler-Laufs (`scheduler_letzter_lauf`, `null` bedeutet,
  der `worker`-Container hat noch keinen erfolgreichen Lauf gehabt – bei
  einem frischen Deployment normal, sollte spätestens einen Tag nach der
  konfigurierten Scheduler-Stunde des ersten Mandanten (Default 03:00 UTC,
  siehe `PATCH /api/mandant/einstellungen`) einen Wert haben).
- **Fotos laden nicht (403/404 auf presigned URLs)**: `S3_PUBLIC_URL_BASE`
  muss exakt `https://<DOMAIN_S3>` sein (Schema + Host, kein Pfad-Suffix,
  kein Port) – sonst weicht die Signatur vom tatsächlich aufgerufenen URL
  ab.

## Was hier bewusst nicht enthalten ist

- Kein automatisches Server-Provisioning (Terraform/Ansible) – die paar
  Schritte oben von Hand auszuführen ist für einen einzelnen vServer
  einfacher nachvollziehbar als ein zusätzliches Tooling einzuführen.
- Kein Multi-Server-/Cluster-Betrieb (siehe "Was offen bleibt" in
  `docs/phases/PHASE_5.md` zum in-process Scheduler/EventBus) – für einen
  Handwerksbetrieb auf einem vServer ausreichend dimensioniert.
