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
Internet ──443──▶ Caddy ──▶ DOMAIN_APP    → frontend:4173  (React-App, mobil)
                        ──▶ DOMAIN_OFFICE → frontend:4173  (React-App, Desktop)
                        ──▶ DOMAIN_API    → backend:8000   (FastAPI)
                        ──▶ DOMAIN_S3     → minio:9000     (Fotos, presigned URLs)
```

Postgres, MinIO, Backend und Frontend haben **keine** direkt aus dem
Internet erreichbaren Ports – nur Caddy auf 80/443. Vier Subdomains statt
einer mit Pfad-Präfixen, weil S3-Presigned-URLs Host *und* Pfad signieren;
ein nachträglich von Caddy gestripptes Pfad-Präfix würde die Signatur
brechen (siehe Kommentar in `app/services/storage_service.py`).

`DOMAIN_APP` und `DOMAIN_OFFICE` zeigen bewusst auf **denselben**
Container: es gibt genau einen Vite-Build. Welche Oberfläche erscheint,
entscheidet der Browser am Hostnamen (`frontend/src/office/hostname.ts`) –
`app.` liefert die mobile PWA, `office.` die Desktop-Ansicht mit
Seitenleiste. Ein zweiter Container wäre derselbe Quellcode ein zweites
Mal gebaut.

Zwei Folgen daraus, die im Betrieb auffallen:
- **`CORS_ORIGINS` braucht beide Hosts**, sonst schlägt jeder API-Aufruf
  von `office.` fehl.
- **Der Login gilt pro Subdomain.** Das Token liegt im `localStorage`, der
  an den Origin gebunden ist – wer zwischen `app.` und `office.` wechselt,
  meldet sich zweimal an. Ein gemeinsames Cookie auf `.<domain>` ist
  bewusst als späterer Schritt zurückgestellt.

---

## ⬛ Nachtrag: Office-Subdomain zu bestehender Installation hinzufügen

> Nur relevant, wenn `app.<domain>` bereits produktiv läuft und jetzt die
> Desktop-Ansicht unter `office.<domain>` dazukommen soll. Bei einer
> **Neuinstallation** ist das schon Teil der normalen Schritte 1–4 weiter
> unten – dieser Abschnitt kann dann übersprungen werden.

1. **DNS-A-Record anlegen**, bevor am Server etwas passiert:
   ```
   office.example.de   A   <server-ip>
   ```
   Ohne diesen Eintrag bekommt Caddy in Schritt 4 kein
   Let's-Encrypt-Zertifikat für die neue Domain.

2. **Code aktualisieren:**
   ```bash
   cd SocialCRM
   git pull
   ```

3. **`.env` ergänzen.** Am einfachsten `scripts/deploy.sh` erneut
   ausführen – das Skript erkennt, dass `DOMAIN_OFFICE` fehlt, fragt
   gezielt nur danach und schreibt `CORS_ORIGINS` automatisch auf beide
   Domains um, ohne den Rest der Konfiguration anzufassen:
   ```bash
   sudo ./scripts/deploy.sh
   ```
   Manuell geht es genauso, direkt in der `.env`:
   ```
   DOMAIN_OFFICE=office.example.de
   CORS_ORIGINS=["https://app.example.de","https://office.example.de"]
   ```
   `chmod 600 .env` gilt weiterhin.

4. **Stack neu bauen und starten** – der `frontend`-Container muss neu
   gebaut werden (er enthält jetzt den Office-Code mit), Caddy und Backend
   brauchen den neuen `.env`-Wert:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```
   Caddy braucht dabei erneut ein bis zwei Minuten für das Zertifikat der
   neuen Domain (`docker compose logs -f caddy`). **Keine Migration nötig**
   – die Office-Ansicht ist reines Frontend, es gibt keine neuen Tabellen.

5. **Prüfen:** `https://office.example.de` im Browser öffnen. Ab ca. 900 px
   Fensterbreite erscheint die Seitenleiste automatisch; auf einem
   Smartphone leitet die Geräte-Weiche selbst zurück auf `app.`. Der Login
   gilt separat vom Handy-Account (siehe "Architektur" oben) – auf
   `office.` muss man sich einmalig neu anmelden.

**Downtime:** nur der kurze Neustart von `frontend`, `backend` und `caddy`
während `up -d --build` – Postgres und MinIO sind nicht betroffen, laufende
Techniker-Sessions auf `app.` bleiben unberührt.

---

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
   `office.203.0.113.5.sslip.io`, `api.203.0.113.5.sslip.io`,
   `s3.203.0.113.5.sslip.io` als ganz normale
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

Im IP-Modus gibt es keine Subdomains und damit auch **keine
Desktop-Ansicht** – `http://<server-ip>:4173` liefert immer die mobile
Oberfläche. Das ist Absicht: die Umschaltung hängt am Hostnamen, und eine
nackte IP hat keinen. Wer die Desktop-Ansicht braucht, nimmt Weg 1 oder 2.

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
- Vier DNS-A-Records, die auf die Server-IP zeigen, z. B.:
  ```
  app.example.de      A   <server-ip>
  office.example.de   A   <server-ip>
  api.example.de      A   <server-ip>
  s3.example.de       A   <server-ip>
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
- `DOMAIN_APP`, `DOMAIN_OFFICE`, `DOMAIN_API`, `DOMAIN_S3` – die vier
  Subdomains von oben. Für jede muss ein A-Record auf die Server-IP
  zeigen, **bevor** der Stack startet – sonst bekommt Caddy für die
  fehlende Domain kein Zertifikat.
- `CADDY_EMAIL` – für Let's-Encrypt-Benachrichtigungen.
- `CORS_ORIGINS=["https://<DOMAIN_APP>","https://<DOMAIN_OFFICE>"]` – beide
  Einträge, sonst bleibt die Desktop-Ansicht ohne Daten.
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

## 4b. Kartenansicht (optional, Modul "karten")

Voraussetzung: ein Mapbox-Account mit einem Access-Token (der Standard
"public token", pk...) genügt für Geocoding und Kartenrendering.

1. `MAPBOX_ACCESS_TOKEN` und `VITE_MAPBOX_TOKEN` in der `.env` setzen
   (derselbe Token-Wert in beiden Variablen).
2. Neu bauen/starten, damit das Backend den Token einliest (siehe
   Abschnitt 6, "Updates").
3. Im Super-Admin-Bereich unter dem jeweiligen Mandanten das Modul
   "Kartenansicht (Mapbox)" aktivieren – ist standardmäßig **aus**, damit
   keine Mandanten ungewollt Mapbox-Kosten verursachen.
4. Optional: bestehende Standorte/Anlagen mit Adresse aber ohne
   Koordinaten einmalig nachgeocodieren:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml \
     run --rm backend python -m app.backfill_geocode
   ```

   Ohne gesetzten Token bricht das Skript sofort ab, ohne etwas zu tun.
   Neue Standorte/Anlagen werden ab aktiviertem Modul automatisch beim
   Anlegen/Ändern der Adresse geocodiert.

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

**Verschlüsselung (`BACKUP_GPG_RECIPIENT`, dringend empfohlen):** Backups
enthalten alle Kunden-/Rechnungsdaten unverschlüsselt, sofern kein
GPG-Empfänger konfiguriert ist. Einrichtung (einmalig, auf einem **anderen**
Rechner als dem Server – der private Schlüssel darf nie auf den Server, sonst
schützt die Verschlüsselung nichts, wenn genau dieser Server kompromittiert
wird):
```bash
gpg --full-generate-key                    # auf dem lokalen Rechner
gpg --export --armor deine@email.de > pub.asc
# pub.asc auf den Server kopieren, dort:
gpg --import pub.asc
```
Dann `BACKUP_GPG_RECIPIENT=deine@email.de` in `.env` setzen – ab dem nächsten
Lauf werden `db-*.sql.gz` und `minio-*.tar.gz` zu `.gpg`-Dateien verschlüsselt
und die unverschlüsselten Zwischendateien gelöscht.

**Offsite-Kopie (`BACKUP_OFFSITE_REMOTE`, dringend empfohlen):** Ein Backup,
das nur auf demselben Server liegt, überlebt einen Festplattendefekt oder
eine kompromittierte Maschine nicht. Mit [rclone](https://rclone.org/)
einmalig ein Remote einrichten (`rclone config`, z. B. gegen einen Hetzner
Storage Box, Backblaze B2, S3-Bucket o. ä.), dann
`BACKUP_OFFSITE_REMOTE=<remote>:<pfad>` in `.env` setzen – jeder Backup-Lauf
kopiert den gesamten `$BACKUP_DIR` automatisch dorthin.

Wiederherstellen:
```bash
scripts/restore.sh db backups/db-20260101-020000.sql.gz
scripts/restore.sh minio backups/minio-20260101-020000.tar.gz
# Bei verschluesselten Backups (.gpg): einfach den Dateinamen mit .gpg angeben,
# restore.sh entschluesselt automatisch (braucht den privaten Schluessel im
# Schluesselbund des ausfuehrenden Nutzers):
scripts/restore.sh db backups/db-20260101-020000.sql.gz.gpg
```
Beide fragen vor dem Überschreiben explizit nach Bestätigung.

## 6. Updates

```bash
cd SocialCRM
git pull
export GIT_COMMIT="$(git rev-parse --short HEAD)"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm backend alembic upgrade head
```

`GIT_COMMIT` wird als Build-Arg ins Backend-Image gebacken und treibt die
rein informative Update-Anzeige im Super-Admin-Bereich (Menüpunkt
„Update") -- zeigt den aktuell laufenden Commit neben dem neuesten Commit
auf GitHub, ohne selbst irgendetwas auszuführen. Ohne das `export` bleibt
die Anzeige auf „unknown" stehen, das Update selbst funktioniert trotzdem.

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
