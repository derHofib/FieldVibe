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
anlegen, Backup, Migrationen anwenden, Stack starten und prüfen (Health-Gate, bei
Fehlschlag automatischer Rollback), ersten Superadmin anlegen,
Backup-Cron einrichten. Idempotent – kann später erneut ausgeführt werden,
um zu aktualisieren (Ablauf: Abschnitt „6. Updates“). Optionen: `--ohne-backup`,
`--nicht-interaktiv`, `--health-timeout <Sekunden>`, `--help`.

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
direkt auf dem Server-Port veröffentlicht). Auch hier vorher die
App-Rolle in der Datenbank einrichten (Abschnitt 3,
`scripts/app_rolle_einrichten.sh`) – sonst verweigern Backend und Worker den
Start:

```bash
./scripts/app_rolle_einrichten.sh --nur-rolle --compose "docker compose -f docker-compose.yml -f docker-compose.ip.yml"
docker compose -f docker-compose.yml -f docker-compose.ip.yml up -d --build
```

Dabei in der `.env` setzen (Server-IP statt der Domains):
- `CORS_ORIGINS=["http://<server-ip>:4173"]`
- `VITE_API_BASE_URL=http://<server-ip>:8000`
- `S3_PUBLIC_URL_BASE=http://<server-ip>:9000`
- `FRONTEND_BASE_URL=http://<server-ip>:4173`

Im IP-Modus setzt `frontend/serve.json` nur Basis-Header (nosniff,
Referrer-Policy, X-Frame-Options, Permissions-Policy) – kein HSTS und keine
CSP. Außerdem wird `FORWARDED_ALLOW_IPS` dort bewusst nicht gesetzt: ohne
Proxy wäre `X-Forwarded-For` von jedem Client fälschbar, die Login-Limiter
zählen dann die Peer-IP des Docker-Netzes.

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
- `MINIO_KMS_SECRET_KEY` – ohne diesen Key lehnt MinIO **jeden** Upload
  (Fotos, Unterschriften, Rechnungs-PDFs, DSGVO-Belege) mit "KMS is not
  configured" ab, siehe Kommentar in `.env.example`. Format:
  `<name>:<32-Byte-Base64>`, erzeugen mit
  `printf "fieldvibe-minio:%s" "$(openssl rand -base64 32)"`.
  `scripts/deploy.sh` setzt das bei einem Neu-Deployment automatisch.
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

`chmod 600 .env` nicht vergessen – die Datei enthält alle Secrets. Ohne
`ENVIRONMENT=development` bricht der Start bei Platzhalter-Secrets ab, siehe
Abschnitt 6c.

**Impressum/Datenschutz:** Die Links auf Login-, Registrierungs- und
Portalseiten zeigen immer auf etwas. Reihenfolge: (1) `impressum_url`/
`datenschutz_url` in den Firmendaten des Betriebs (Integrationen →
Firmenprofil), (2) `VITE_IMPRESSUM_URL`/`VITE_DATENSCHUTZ_URL` in der `.env`
(Build-Zeit, danach Frontend neu bauen), (3) sonst die Platzhalter-Seiten
`/impressum` und `/datenschutz` der App, die nur die Firmenangaben anzeigen
und ausdrücklich als Platzhalter gekennzeichnet sind. Für den
Produktivbetrieb ersetzen rechtsgeprüfte Texte (1) oder (2) die Platzhalter
(§ 5 DDG, Art. 13 DSGVO). Die Platzhalter-Seiten erkennen den Betrieb bei
genau einem aktiven Mandanten automatisch, bei mehreren nur über den
Kundenportal-Link `/portal/l/<slug>`.

## 3. Starten

**Nicht** einfach `docker compose up` – das lädt automatisch
`docker-compose.override.yml` mit (reine Lokalentwicklung: Hot-Reload,
offene DB/MinIO-Ports). Stattdessen explizit die Basis- und die
Prod-Datei kombinieren:

Das offizielle Postgres-Image macht `POSTGRES_USER` zum **Bootstrap-
Superuser** – und ein Superuser umgeht Row-Level-Security immer, die
Mandantentrennung in der Datenbank wäre wirkungslos. Dem Bootstrap-User lässt
sich das nicht entziehen (`ALTER ROLE … NOSUPERUSER` scheitert mit „The
bootstrap user must have the SUPERUSER attribute"). Deshalb bleibt
`POSTGRES_USER` reiner Admin-Zugang, und Backend, Worker und Migrationen
verbinden sich als eigene Rolle `fieldvibe_app` (`LOGIN NOSUPERUSER
NOBYPASSRLS`). `scripts/deploy.sh` richtet sie automatisch ein; beim manuellen
Weg ist es Pflicht und idempotent:

```bash
./scripts/app_rolle_einrichten.sh --nur-rolle --compose "docker compose -f docker-compose.yml -f docker-compose.prod.yml"
```

Das Skript startet Postgres, legt die Rolle mit zufälligem Passwort an
(`APP_DB_USER`/`APP_DB_PASSWORD` in der `.env`), überträgt das Eigentum an
vorhandenen Tabellen (`scripts/sql/app_rolle_einrichten.sql`) und setzt
`DATABASE_URL`/`DATABASE_URL_SYNC` in der `.env` auf die neue Rolle. Backend
und Worker prüfen beim Start (`SELECT rolsuper, rolbypassrls …`) und brechen
mit einer klaren Fehlermeldung ab, solange die Verbindung Superuser oder
BYPASSRLS ist. Nur für Notfälle lässt sich das mit
`FIELDVIBE_ERLAUBE_RLS_BYPASS_ROLLE=1` in der `.env` übergehen (Start mit
WARNING im Log, Mandantentrennung per RLS dann ausser Kraft).

Danach den Stack starten:

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

### Datenschutz: Mapbox-Telemetrie

mapbox-gl 3.x sendet von sich aus Nutzungsdaten (Ereignisse `style.load`,
`appUserTurnstile`, `gljs.performance`, `map.load` samt anonymer
Nutzer-ID) an `events.mapbox.com` (USA). Das SDK bietet keine Option zum
Abschalten (geprüft an 3.28.1: `config.EVENTS_URL` ist ein Getter aus
`API_URL`, `"enabled.telemetry"` ist im Payload fest `false`). FieldVibe
verwirft diese Requests deshalb clientseitig in
`frontend/src/components/mapboxSetup.ts` (Fetch-Filter nur für den
Events-Host); Style-, Tile- und Session-Requests an `api.mapbox.com`
laufen unverändert. Das gilt auch im IP-Betrieb ohne Caddy. Die CSP im
`Caddyfile` führt den Host bewusst nicht in `connect-src` und meldet im
Report-Only-Modus einen Verstoß, falls doch ein Request an ihn geht.

Prüfen nach einem Update von mapbox-gl: im Browser unter Netzwerk nach
`events.mapbox` filtern (Kartenansicht öffnen) – es darf kein Eintrag
erscheinen. Automatisiert: `npx playwright test mapbox-telemetrie` in
`frontend/` (Dev-Stack mit Seed und Dummy-Token, siehe Kopfkommentar der
Spec).

Offen für den Betreiber: Die Mapbox-Lizenz schließt Änderungen an
Abrechnungs- und Datenerfassungscode aus (`node_modules/mapbox-gl/LICENSE.txt`);
ob der Fetch-Filter mit den Mapbox-Bedingungen vereinbar ist, ist
vertraglich zu klären. Unabhängig davon verarbeitet Mapbox Inc. (USA) für
Geocoding (Adressen, vom Backend) und Kartenkacheln (IP-Adresse und
Kartenausschnitt der Nutzer) personenbezogene Daten: Mapbox braucht einen
AV-Vertrag mit Standardvertragsklauseln und gehört in die Liste der
Unterauftragsverarbeiter.

## 5. Backups

> **Hinweis zur Verifikation:** Die Docker-Aufrufe in den Backup-Skripten
> (`docker compose exec … pg_dump/pg_restore`, `docker run … alpine tar`)
> sind in der Entwicklungsumgebung nicht gegen einen echten Docker-Daemon
> getestet (Shell-Tests mit Stubs und gegen einen lokalen Postgres laufen
> in CI). **Nach der Einrichtung auf dem Server einmal `scripts/backup.sh`
> und danach `scripts/backup-pruefen.sh` von Hand ausführen** und das
> Ergebnis ansehen, bevor man sich auf die Sicherung verlässt.

### Konzept: Sicherungssatz und Manifest

`scripts/backup.sh` läuft täglich per Host-Cron (richtet `deploy.sh` ein,
02:30 Uhr) und legt je Lauf einen **Sicherungssatz** mit gemeinsamem
Zeitstempel `<stamp>` (`YYYYMMDD-HHMMSS`) in `$BACKUP_DIR` ab:

| Datei | Inhalt |
|---|---|
| `db-<stamp>.dump` | Postgres im Custom-Format (`pg_dump -Fc`) |
| `minio-<stamp>.tar.gz` | MinIO-Datenverzeichnis (Fotos, serverseitig per SSE verschlüsselt) |
| `secrets-<stamp>.tar` | die `.env` (Rechte 0600) |
| `manifest-<stamp>.json` | Dateien mit Größe und SHA-256, Zeitstempel, Git-Commit, Postgres-Version, Format-Version `1` |

Mit `BACKUP_GPG_RECIPIENT` bekommen `db`, `minio` und `secrets` die Endung
`.gpg`; das Manifest enthält die Prüfsummen der **finalen** (verschlüsselten)
Dateien und bleibt unverschlüsselt (keine Nutzdaten).

**Warum die `.env` im Satz ist:** Ohne `MINIO_KMS_SECRET_KEY` sind die
SSE-verschlüsselten Fotos nach einem Totalverlust unlesbar, ohne
`INTEGRATION_SECRET_KEY` die in der DB verschlüsselten
Integrations-Zugangsdaten, und `JWT_SECRET`/DB-Passwörter müssten neu
vergeben werden. Das Bündel wird **nur verschlüsselt** an ein Ziel übertragen
(siehe Verschlüsselung).

Ein Satz gilt erst mit Manifest als **vollständig** (es wird zuletzt
geschrieben bzw. hochgeladen). Ablauf eines Laufs: Sperre (`flock`, kein
paralleler Lauf) → Ping „Start“ → Dump → MinIO-Archiv → Secrets-Bündel →
Verschlüsselung → Manifest → Upload und Rotation je Ziel → `letzter-lauf.json`
→ Ping/Benachrichtigung. Der Exit-Code ist ≠ 0, sobald irgendein Schritt oder
Ziel scheitert; ein ausfallendes Ziel bricht die anderen nicht ab.

Manuell einrichten (falls nicht `deploy.sh` benutzt wurde):

```bash
mkdir -p /opt/fieldvibe-backups
crontab -e
# Täglich 02:30 Backup, sonntags 04:30 Test-Restore:
30 2 * * * /pfad/zu/SocialCRM/scripts/backup.sh >> /var/log/fieldvibe-backup.log 2>&1
30 4 * * 0 /pfad/zu/SocialCRM/scripts/backup-pruefen.sh >> /var/log/fieldvibe-backup-pruefen.log 2>&1
```

### Ziele (austauschbare Anbieter)

`$BACKUP_DIR` ist immer die lokale Erstablage. Zusätzliche Ziele stehen in
`BACKUP_TARGETS` (Leerzeichen oder Komma getrennt, Eintrag = `<typ>:<ziel>`);
jedes Ziel wird einzeln geprüft, beliefert und rotiert:

| Typ | `<ziel>` | Wofür |
|---|---|---|
| `rclone` | `<remote>:<pfad>` | jeder von [rclone](https://rclone.org/) unterstützte Anbieter: S3-kompatibel, Backblaze B2, Hetzner Storage Box (SFTP/WebDAV), Nextcloud, GCS, Azure … |
| `local` | absoluter Pfad | zusätzliches lokales oder gemountetes Verzeichnis (NFS, SMB, USB-Platte) |
| `befehl` | absoluter Pfad eines Programms | beliebiger Anbieter über ein eigenes Programm, ohne am Repo etwas zu ändern (nächster Abschnitt) |

`BACKUP_RETENTION_DAYS` (Default 14) und `BACKUP_MIN_KEEP` (Default 3)
steuern die Rotation, **pro Ziel und lokal**: Sätze älter als die Aufbewahrung
werden gelöscht, aber unabhängig vom Alter bleiben immer mindestens
`BACKUP_MIN_KEEP` **vollständige** Sätze – ein langer Ausfall (Cron tot, Ziel
nicht erreichbar) räumt so nie alle Sicherungen weg. Unvollständige Sätze
(abgebrochene Läufe) werden entfernt. Alte Dateien im Format vor dieser
Umstellung (`db-*.sql.gz`) bleiben, bis mindestens `BACKUP_MIN_KEEP` neue
Sätze existieren, und werden danach nach Alter gelöscht. Dateien, die nicht zu
einem Sicherungssatz gehören, fasst die Rotation nie an. Ein Ziel, dessen
Upload scheitert, wird in diesem Lauf nicht rotiert.

Die alte Variable `BACKUP_OFFSITE_REMOTE` funktioniert weiter: ist
`BACKUP_TARGETS` leer, wird sie als `rclone:$BACKUP_OFFSITE_REMOTE`
behandelt (mit Hinweis im Log, dass sie veraltet ist).

#### Beispiel: Hetzner Storage Box über rclone/SFTP

Einmalig auf dem Server (`rclone config`, neues Remote `storagebox`, Typ
`sftp`; Host `uXXXXXX.your-storagebox.de`, Benutzer `uXXXXXX`, Port laut
Hetzner-Dokumentation `23`, SSH-Schlüssel oder Passwort), dann prüfen:

```bash
rclone lsd storagebox:            # muss ohne Fehler laufen
```
```bash
# .env
BACKUP_TARGETS=rclone:storagebox:fieldvibe-backups
BACKUP_GPG_RECIPIENT=backup@example.de
```

#### Beispiel: S3-kompatibler Speicher (Backblaze B2, Wasabi, MinIO, AWS …)

`rclone config` → Typ `s3` (Provider passend wählen, Endpoint/Region und
Zugangsschlüssel eintragen; für B2 alternativ Typ `b2`), dann:

```bash
BACKUP_TARGETS=rclone:s3backup:mein-bucket/fieldvibe
```

Für den Schutz gegen Löschen durch einen kompromittierten Server beim
Anbieter Versionierung bzw. Object Lock aktivieren (siehe „Ehrliche Grenzen“).

#### Beispiel: NAS/NFS-Mount

```bash
# /etc/fstab (Beispiel NFS)
nas.lan:/volume1/fieldvibe  /mnt/nas  nfs  defaults,_netdev  0 0
```
```bash
BACKUP_TARGETS=local:/mnt/nas/fieldvibe
```

Ist der Mount nicht eingehängt, würde in das leere Mountpoint-Verzeichnis auf
der lokalen Platte geschrieben – dann wäre es keine zweite Kopie. Abhilfe:
Mountpoint im ausgehängten Zustand unveränderlich machen (`umount /mnt/nas &&
chattr +i /mnt/nas && mount /mnt/nas`), dann scheitert der Lauf laut statt still.

Mehrere Ziele kombinieren:
`BACKUP_TARGETS="rclone:storagebox:fieldvibe-backups local:/mnt/nas/fieldvibe"`.

### Eigenen Anbieter einbinden (`befehl`)

Für jeden Anbieter, den rclone nicht abdeckt, schreibt man ein kleines
Programm in beliebiger Sprache und trägt es ein:

```bash
BACKUP_TARGETS=befehl:/opt/mein-adapter.sh
```

Das Programm (ausführbar, absoluter Pfad) wird mit einem Unterbefehl
aufgerufen. Das Ziel *ist* das Programm; es bekommt seinen Pfad deshalb nicht
noch einmal als Argument. Alle Variablen der `.env` stehen als
Umgebungsvariablen bereit (dort also auch eigene Zugangsdaten ablegen):

| Aufruf | Aufgabe | Ausgabe |
|---|---|---|
| `pruefen` | Konfiguration/Erreichbarkeit prüfen | Exit 0 = ok |
| `hochladen <verzeichnis> <stamp>` | alle Dateien `*-<stamp>.*` aus `<verzeichnis>` hochladen, **das Manifest zuletzt** | Exit 0 = alles angekommen |
| `auflisten` | vorhandene Stamps | **nur** Stamps (`YYYYMMDD-HHMMSS`), einer je Zeile, neueste zuletzt, nur Sätze **mit** Manifest; Meldungen auf stderr |
| `herunterladen <stamp> <zielverz> [art]` | Satz nach `<zielverz>` holen (Verzeichnis ggf. anlegen); `art` = `db`/`minio`/`secrets`/`alle` – das Programm darf es ignorieren und immer alles holen | Exit 0 |
| `aufraeumen <behalte_tage> <mindestens>` | Rotation: Sätze älter als `<behalte_tage>` löschen, aber die neuesten `<mindestens>` vollständigen Sätze immer behalten, unvollständige löschen | Exit 0 |

Jeder Exit-Code ≠ 0 gilt als Fehler dieses Ziels (die übrigen Ziele laufen
weiter). Wer die Rotationsregeln nicht nachbauen will, bindet die
Bibliothek ein: `source "$BACKUP_LIB_DATEI"` stellt
`rotation_plan <tage> <min>` (Dateinamen auf stdin, zu löschende auf stdout)
und `satz_stamps_vollstaendig` (Dateinamen auf stdin, Stamps auf stdout) bereit.

Ein vollständiges, lauffähiges Beispiel (WebDAV per `curl`: Nextcloud,
ownCloud, Storage Box per WebDAV) liegt in
`scripts/backup/ziele/befehl-beispiel.sh.example`:

```bash
cp scripts/backup/ziele/befehl-beispiel.sh.example /opt/fieldvibe-webdav.sh
chmod 700 /opt/fieldvibe-webdav.sh
# .env:
#   BACKUP_TARGETS=befehl:/opt/fieldvibe-webdav.sh
#   WEBDAV_URL=https://cloud.example.de/remote.php/dav/files/backup/fieldvibe
#   WEBDAV_USER=backup
#   WEBDAV_PASSWORD=...
set -a; source .env; set +a
/opt/fieldvibe-webdav.sh pruefen && /opt/fieldvibe-webdav.sh auflisten
```

Das Beispiel wird in den Shell-Tests gegen einen WebDAV-Testserver
ausgeführt. Ein fertiges eigenes Programm lässt sich mit
`scripts/restore.sh liste --von befehl:/opt/mein-adapter.sh` prüfen.

### Verschlüsselung (`BACKUP_GPG_RECIPIENT`)

Backups enthalten alle Kunden-/Rechnungsdaten (Art. 32 DSGVO: TOM).
Einrichtung (einmalig, auf einem **anderen** Rechner als dem Server – der
private Schlüssel darf nie auf den Server, sonst schützt die Verschlüsselung
nichts, wenn genau dieser Server kompromittiert wird):

```bash
gpg --full-generate-key                    # auf dem lokalen Rechner
gpg --export --armor deine@email.de > pub.asc
# pub.asc auf den Server kopieren, dort:
gpg --import pub.asc
```

Dann `BACKUP_GPG_RECIPIENT=deine@email.de` in `.env` setzen – ab dem nächsten
Lauf werden Dump, MinIO-Archiv und Secrets-Bündel zu `.gpg`-Dateien
verschlüsselt und die Klartext-Zwischendateien gelöscht. Den privaten
Schlüssel samt Passphrase an mindestens zwei getrennten Orten offline
aufbewahren: **ohne ihn sind alle verschlüsselten Sicherungen wertlos.**

Folgen, wenn `BACKUP_GPG_RECIPIENT` fehlt:

- Das Secrets-Bündel bleibt unverschlüsselt **nur lokal** in `$BACKUP_DIR`
  (0600) und wird **nie** an irgendein Ziel übertragen (Warnung im Log) – ein
  Remote-Satz enthält dann keine `.env`.
- Der Upload zu Remote-Zielen (`rclone`, `befehl`) wird **verweigert** (Ziel
  gilt als fehlgeschlagen, Exit ≠ 0). Wer den Anbieter bewusst Klartext
  sehen lassen will (eigenes, abgesichertes Netz), setzt ausdrücklich
  `BACKUP_ERLAUBE_UNVERSCHLUESSELT_REMOTE=1`; das Secrets-Bündel bleibt
  trotzdem ausgenommen.
- `local:`-Ziele brauchen keine Verschlüsselung.
- Ohne jedes Remote-Ziel bleibt es bei einer Warnung.

### Überwachung

Ein Backup, das stumm ausfällt, ist keins. Drei Hebel, alle in der `.env`:

- **Ping (`BACKUP_PING_URL`)**, kompatibel zu [healthchecks.io](https://healthchecks.io/):
  `GET <url>/start` zu Beginn, `GET <url>` bei Erfolg, `GET <url>/fail` bei
  Fehler (`curl -fsS -m 10 --retry 3`; ein nicht erreichbarer Ping lässt den
  Lauf nicht scheitern). Der Dienst schlägt auch Alarm, wenn der Ping **ganz
  ausbleibt** (Server/Cron tot) – deshalb Periode 1 Tag mit einigen Stunden
  Toleranz einstellen. Die wöchentliche Prüfung hat einen eigenen Ping,
  `BACKUP_PRUEF_PING_URL` (Periode 7 Tage).
- **Benachrichtigung (`BACKUP_BENACHRICHTIGUNG_BEFEHL`)**: wird bei jedem Lauf
  (Backup und Prüfung) mit `BACKUP_STATUS=ok|fehler`, `BACKUP_NACHRICHT` und
  `BACKUP_STAMP` aufgerufen. In **einfachen** Anführungszeichen setzen, sonst
  ersetzt die Shell die Variablen schon beim Einlesen der `.env`:
  ```bash
  BACKUP_BENACHRICHTIGUNG_BEFEHL='curl -fsS -d "$BACKUP_STATUS: $BACKUP_NACHRICHT" https://ntfy.sh/mein-thema'
  ```
- **`$BACKUP_DIR/letzter-lauf.json`**: Zeitstempel, Stamp, Gesamtstatus,
  Dauer, Status je Ziel – für Monitoring-Agenten (z. B. „Datei älter als 26 h“)
  oder eine spätere Oberfläche:
  ```json
  {
    "zeitpunkt": "2026-01-01T02:31:12+01:00", "stamp": "20260101-023001",
    "status": "fehler", "dauer_sekunden": 41, "meldung": "Sicherung … FEHLGESCHLAGEN: …",
    "lokal": {"status": "ok", "meldung": "Satz 20260101-023001 in /opt/fieldvibe-backups"},
    "ziele": [
      {"ziel": "rclone:storagebox:fieldvibe-backups", "status": "fehler", "meldung": "Upload fehlgeschlagen"},
      {"ziel": "local:/mnt/nas/fieldvibe", "status": "ok", "meldung": "Satz 20260101-023001 hochgeladen"}
    ]
  }
  ```

### Wiederherstellen (Einzelschritte)

```bash
scripts/restore.sh liste                                   # lokal + alle Ziele aus BACKUP_TARGETS
scripts/restore.sh liste --von rclone:storagebox:fieldvibe-backups

# Quelle: lokale Datei ODER ein Ziel (--von; ohne --stamp der neueste Satz)
scripts/restore.sh db      backups/db-20260101-020000.dump.gpg
scripts/restore.sh db      --von rclone:storagebox:fieldvibe-backups --stamp 20260101-020000
scripts/restore.sh minio   --von local:/mnt/nas/fieldvibe --stamp 20260101-020000
scripts/restore.sh secrets --von rclone:storagebox:fieldvibe-backups
```

- Vor jedem Einspielen wird die Prüfsumme gegen das Manifest geprüft; bei
  Abweichung bricht `restore.sh` ab, **bevor** etwas verändert wird. `.gpg`
  wird automatisch entschlüsselt (privater Schlüssel im Schlüsselbund des
  ausführenden Nutzers nötig).
- `db` stoppt Backend und Worker, spielt den Dump per
  `pg_restore --clean --if-exists --exit-on-error --single-transaction` in die
  bestehende Datenbank ein (scheitert etwas, bleibt die bisherige Datenbank
  unverändert) und startet Backend und Worker wieder. Die Rückfrage erscheint
  nur an einem Terminal; für Automatisierung `--ja` angeben (ohne Terminal und
  ohne `--ja` bricht das Skript ab). Objekte, die im Dump nicht vorkommen
  (z. B. Tabellen einer neueren Migration), bleiben bestehen – war der Code zur
  Sicherungszeit älter, danach `docker compose … run --rm backend alembic
  upgrade head`. Eigentümer werden mit zurückgespielt, damit die App-Rolle
  (`fieldvibe_app`) die Tabellen weiter besitzt; sie muss dafür existieren
  (`scripts/app_rolle_einrichten.sh`, macht auch `deploy.sh`). Ausnahme:
  `--ohne-eigentuemer`, danach `scripts/app_rolle_einrichten.sh` ausführen.
- Das Altformat `db-*.sql.gz` (Plain-SQL vor der Umstellung) wird weiter
  unterstützt: Schema `public` wird vorher neu angelegt und alles mit
  `psql -v ON_ERROR_STOP=1 --single-transaction` eingespielt.
- `minio` stoppt MinIO, leert das Datenverzeichnis (inkl. versteckter
  Metadaten) und spielt das Archiv ein. Die Objekte sind nur mit demselben
  `MINIO_KMS_SECRET_KEY` lesbar – also zuerst `secrets`.
- `secrets` schreibt `.env.wiederhergestellt` (0600) und überschreibt die
  vorhandene `.env` **nicht**; die Übernahme (`diff`, `cp`) nennt das Skript.

### Runbook: Totalverlust des Servers

Voraussetzungen, die **nicht** im Backup liegen: der private GPG-Schlüssel,
die Zugangsdaten zum Backup-Ziel (rclone-Konfiguration `~/.config/rclone/rclone.conf`
bzw. die Daten Ihres `befehl`-Programms) und der DNS-Zugang. Diese
getrennt aufbewahren.

1. **Neuen Server vorbereiten:** Docker, `git`, `gnupg` und je nach Ziel
   `rclone` installieren; Repo klonen (`git clone … && cd SocialCRM`). Wer
   exakt den alten Stand will: `git checkout <git_commit>` (steht in
   `manifest-<stamp>.json`); sonst nach dem Restore die Migrationen laufen
   lassen.
2. **Zugang herstellen:** privaten Schlüssel einspielen
   (`gpg --import private.asc`), Backup-Ziel einrichten (`rclone config`
   o. Ä.). Alternativ den Satz per `scp` auf den Server kopieren und
   `restore.sh` mit lokalen Dateien benutzen.
3. **Satz wählen:**
   `scripts/restore.sh liste --von rclone:storagebox:fieldvibe-backups` →
   gewünschten Stamp merken (neuester unten).
4. **Secrets zuerst, noch vor `deploy.sh`:**
   `scripts/restore.sh secrets --von rclone:storagebox:fieldvibe-backups --stamp <stamp>`,
   dann `cp .env.wiederhergestellt .env` und die Datei löschen. Damit
   starten Postgres und MinIO gleich mit den alten Passwörtern und
   Schlüsseln (`MINIO_KMS_SECRET_KEY`, `INTEGRATION_SECRET_KEY`,
   `JWT_SECRET` …). Hat sich die Domain geändert, `DOMAIN_*` anpassen.
   *(Läuft `deploy.sh` zuerst, erzeugt es neue Secrets, die zu Datenbank und
   Fotos nicht passen.)*
5. **Stack aufsetzen:** `sudo ./scripts/deploy.sh` – übernimmt die
   vorhandene `.env`, startet alles, legt die App-Rolle an und führt die
   Migrationen auf der leeren Datenbank aus (Frage nach einem neuen
   Plattform-Administrator mit „n“ beantworten).
6. **Datenbank:**
   `scripts/restore.sh db --von rclone:storagebox:fieldvibe-backups --stamp <stamp>`
7. **Fotos:**
   `scripts/restore.sh minio --von rclone:storagebox:fieldvibe-backups --stamp <stamp>`
8. **Migrationen**, falls der Code neuer ist als der Satz:
   `docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm backend alembic upgrade head`
9. **Funktionstest:** Login in Feld-App und Office, ein altes Foto öffnen
   (beweist den KMS-Schlüssel), Integrationen testen, `/healthz` prüfen;
   dann `scripts/backup.sh` und `scripts/backup-pruefen.sh` ausführen und
   `BACKUP_TARGETS`/Cron kontrollieren (`crontab -l`).

### Test-Restore (`scripts/backup-pruefen.sh`)

Ein Backup, das nie zurückgespielt wurde, ist nur eine Hoffnung.
`scripts/backup-pruefen.sh` (wöchentlich per Cron, sonntags 04:30) nimmt den
neuesten Satz (oder `--stamp`, lokal oder `--von <typ:ziel>`), prüft alle
Prüfsummen gegen das Manifest, entschlüsselt, spielt den Dump in eine
**Wegwerf-Datenbank** `restore_test_<stamp>` im Postgres-Container ein
(Plausibilität: Tabellen vorhanden, `alembic_version` gefüllt, Zeilenanzahl von
`mandanten` und `users` wird ausgegeben), prüft MinIO-Archiv (`tar tzf`) und
Secrets-Bündel auf Lesbarkeit und löscht die Wegwerf-Datenbank in jedem Fall.
Die Produktions-Datenbank wird nie angefasst. Exit ≠ 0 bei jedem Fehler;
das Ergebnis geht an `BACKUP_PRUEF_PING_URL` und
`BACKUP_BENACHRICHTIGUNG_BEFEHL`.

```bash
scripts/backup-pruefen.sh                      # neuester lokaler Satz, voller Test
scripts/backup-pruefen.sh --von rclone:storagebox:fieldvibe-backups
scripts/backup-pruefen.sh --nur-pruefsummen    # ohne Entschlüsselung und DB
```

Liegt der private GPG-Schlüssel – richtigerweise – nicht auf dem Server,
beschränkt sich der Cron-Lauf dort auf die **Prüfsummen** (klare Meldung im
Log, Exit 0). Den vollständigen Test-Restore deshalb zusätzlich regelmäßig
(z. B. monatlich) dort ausführen, wo Schlüssel und Docker-Stack vorhanden
sind. Ein Satz aus einem Remote-Ziel ohne Secrets-Bündel (kein GPG beim
Backup) gilt in der Prüfung als Fehler.

### Ehrliche Grenzen

- **Nur ein täglicher Dump, kein WAL-Archiv/Point-in-Time-Recovery:** Bei
  einem Totalverlust gehen die Änderungen seit dem letzten Lauf verloren
  (RPO bis 24 Stunden). Häufigere Läufe lassen sich über zusätzliche
  Cron-Zeilen einrichten; echtes PITR wäre ein eigenes Vorhaben.
- **Datenbank und MinIO werden nacheinander gesichert,** nicht atomar: das
  Tar eines laufenden MinIO-Verzeichnisses kann Objekte enthalten, die
  gerade geschrieben werden. Nachts gering, aber nicht ausgeschlossen.
- **Nicht im Backup:** der private GPG-Schlüssel, die rclone-Konfiguration bzw.
  Zugangsdaten eigener Ziele, Server-Konfiguration außerhalb der `.env`
  (Firewall, Cron, Docker). Das Runbook setzt sie voraus.
- **Löschschutz beim Anbieter:** Der Server hält die Zugangsdaten zum Ziel und
  löscht dort bei der Rotation selbst – ein kompromittierter Server könnte
  auch die Remote-Sicherungen löschen. Anbieterseitig Versionierung/Object
  Lock oder ein Zugang nur mit „anhängen“-Rechten einrichten, wenn das ein
  Risiko ist.
- **Der Test-Restore prüft Lesbarkeit und Plausibilität,** nicht die
  Fachlichkeit der Daten; er braucht kurzzeitig Platz im Postgres-Container
  und Plattenplatz für entschlüsselte Zwischendateien unter `$BACKUP_DIR`.
- **`pg_dump` läuft als `POSTGRES_USER`** (Bootstrap-Superuser, umgeht RLS) –
  nur so enthält der Dump alle Mandanten.

## 6. Updates

Der Standardweg ist `sudo ./scripts/deploy.sh` (auch für Updates, idempotent). Ablauf:

1. **Vorab-Check**: Docker-Daemon erreichbar, Compose-Dateien auflösbar, genug
   Plattenplatz (Standard ≥ 2 GB, `DEPLOY_MIN_FREI_MB`).
2. **Backup** (`scripts/backup.sh`) – schlägt es fehl, **bricht das Deployment ab**,
   bevor etwas verändert wurde. Opt-out nur bewusst: `--ohne-backup`. Erstinstallation
   (noch keine Datenbank): übersprungen.
3. **Images bauen** mit dem Commit als Tag (`fieldvibe-backend:<sha>`,
   `fieldvibe-frontend:<sha>`); der bisherige Stand bleibt unter seinem Tag liegen.
4. **Datenbank und Objektspeicher starten**, MinIO-Service-Account prüfen.
5. **Migration vor dem Rollout** (Worker ruht währenddessen). Scheitert sie, wird
   *nicht* ausgerollt – die laufende Version bleibt aktiv.
6. **Rollout** (`up -d --no-build`) und **Health-Gate**: wartet bis `--health-timeout`
   (Standard 300 s), dass Backend (`/health/ready`: Datenbank, Objektspeicher,
   Migrationsstand), Worker (Heartbeat) und Frontend antworten.
7. **Automatischer Rollback**, wenn das Gate scheitert: die Container laufen wieder
   mit den Image-Tags des Vorgängers (`.deploy-state`, Schlüssel `PREVIOUS_TAG`/
   `CURRENT_TAG`). Exit-Code ≠ 0, Log-Hinweis und `FEHLGESCHLAGEN_TAG` im State.

**Migrationen werden nicht zurückgerollt.** Das Schema bleibt auf dem neuen Stand,
auch wenn die alte Version zurückkehrt. Das geht nur gut, wenn Migrationen
abwärtskompatibel sind (Regel: Spalten/Tabellen *hinzufügen*, nie im selben Release
umbenennen oder löschen – „expand, then contract“). Bei einer inkompatiblen Migration
hilft nur das Backup vom Anfang des Laufs (`BACKUP_STAMP` in `.deploy-state`):
`scripts/restore.sh db --stamp <stamp>` – Schritt für Schritt in `docs/BETRIEB.md`.

Auf `/health/ready` ist eine Datenbank, die *neuer* ist als der Code (Rollback nach einer
Migration), ausdrücklich „bereit“ – sonst könnte ein Rollback nie gesund werden.

Der Rollback ist nur möglich, solange die Vorgänger-Images noch auf dem Host liegen
(`docker image prune -a` löscht sie). Eine Bestandsinstallation ohne `.deploy-state` bekommt
beim ersten Lauf den laufenden Stand automatisch als Tag `vorher-<zeit>` gesichert.

Per Hand (nur wenn `deploy.sh` nicht in Frage kommt – ohne Backup-Abbruch, Gate und Rollback):

```bash
cd SocialCRM
git pull
export GIT_COMMIT="$(git rev-parse --short HEAD)" IMAGE_TAG="$GIT_COMMIT"
C="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
scripts/backup.sh
$C build backend frontend worker
$C up -d postgres minio
$C stop worker
$C run --rm backend alembic upgrade head      # oder scripts/migrieren.sh --compose "$C"
$C up -d --no-build --remove-orphans
```

**Images aus der Registry (GHCR):** Die CI veröffentlicht bei Push auf `main` und bei Tags `v*`
`ghcr.io/<owner>/<repo>-backend` und `-frontend` (Tags: Commit, Version, `latest`) als Release-
Artefakte. `deploy.sh` baut weiterhin auf dem Server: das Frontend braucht die Domains des Servers
(`VITE_API_BASE_URL` & Co. werden zur Build-Zeit eingebacken), das Frontend-Image aus der CI trägt nur
die Standard-Argumente. Ein Betrieb ganz ohne Build auf dem Server wäre erst mit einer
Laufzeit-Konfiguration des Frontends möglich (siehe `docs/BACKLOG.md`).

**Einmalig nach dem Update auf die App-Rolle** (Installationen, die bisher
als `POSTGRES_USER` liefen oder mit `FIELDVIBE_ERLAUBE_RLS_BYPASS_ROLLE=1`
betrieben wurden), im Repo-Verzeichnis:

```bash
./scripts/app_rolle_einrichten.sh
```

Das Skript ruft vorab `scripts/backup.sh` auf (scheitert die Sicherung, z. B.
weil ein Remote-Ziel ohne `BACKUP_GPG_RECIPIENT` konfiguriert ist, bricht es ab,
bevor etwas verändert wird), kopiert die `.env`, richtet die
Rolle ein, stellt `.env` um, startet Backend/Worker neu und wendet die
Migrationen an. Schlägt ein Schritt nach der `.env`-Änderung fehl, spielt es
die alte `.env` zurück und startet Backend/Worker wieder damit; die
Eigentumsänderungen in der Datenbank bleiben bestehen (harmlos, der
Admin-User kann weiterhin alles), ein erneuter Lauf ist gefahrlos.
`--dry-run` zeigt vorab die Schritte. Ein weiterer Lauf ist jederzeit
idempotent. Benutzer- und Datenbankname kommen aus `POSTGRES_USER`/
`POSTGRES_DB` der `.env`.

`GIT_COMMIT` wird als Build-Arg ins Backend-Image gebacken und treibt die
rein informative Update-Anzeige im Super-Admin-Bereich (Menüpunkt
„Update") -- zeigt den aktuell laufenden Commit neben dem neuesten Commit
auf GitHub, ohne selbst irgendetwas auszuführen; zugleich ist es der Release-Tag des
Error-Trackings. `deploy.sh` setzt es selbst; ohne den Wert bleibt die Anzeige auf
„unknown" stehen, das Update selbst funktioniert trotzdem.

### Abhängigkeiten aktualisieren (Lockfiles)

Die Images installieren reproduzierbar: Backend aus den hashgepinnten
`backend/requirements.lock` (Produktion) und `backend/requirements-dev.lock`
(Tests/CI), Frontend per `npm ci` aus `frontend/package-lock.json`.
`requirements.txt`/`requirements-dev.txt` bleiben die menschenlesbaren Eingaben;
die `.lock`-Dateien nie von Hand editieren.

```bash
# Python 3.12 verwenden (wie das Dockerfile) -- die Aufloesung ist
# interpreter- und plattformabhaengig, Ziel ist linux/amd64.
python3.12 -m venv /tmp/piptools && /tmp/piptools/bin/pip install pip-tools
cd backend
/tmp/piptools/bin/pip-compile --generate-hashes --strip-extras --allow-unsafe -o requirements.lock requirements.txt
/tmp/piptools/bin/pip-compile --generate-hashes --strip-extras --allow-unsafe -o requirements-dev.lock requirements-dev.txt
# Einzelnes Paket anheben: Version in requirements.txt aendern und neu kompilieren,
# oder -P paketname==x.y.z an pip-compile haengen.

# Frontend: Aenderungen an package.json immer mit package-lock.json committen
cd ../frontend && npm install && npm audit
```

Beide Lockfiles gemeinsam committen. `pip install --require-hashes` bricht ab,
wenn ein Paket nicht gepinnt ist oder der Hash nicht passt.

## 6b. Fehlerberichte-Service-Token (optional)

Zugriff für Claude auf In-App-Fehlerberichte (Token, `.env`, Netzwerk):
siehe `docs/FEHLERBERICHTE.md`.

## 6c. Sicherheit (TOM, Art. 32 DSGVO)

Technische Maßnahmen dieser Installation und was dafür zu tun ist.

### Startabbruch bei unsicherer Konfiguration

`ENVIRONMENT` ist **fail-closed**: ohne Eintrag gilt `production`. Backend,
Worker, Alembic und CLI verweigern dann den Start mit einer Liste der
Probleme, wenn `JWT_SECRET` ein Platzhalter/Default oder kürzer als 32 Zeichen
ist, `S3_SECRET_KEY` oder ein gesetzter `INTEGRATION_SECRET_KEY` ein
Platzhalter ist (enthält `changeme`/`change-me`) oder die Datenbank-URLs ein
Default-Passwort (`fieldvibe`, `fieldvibe_app`, Platzhalter) tragen. Ein
fehlender `INTEGRATION_SECRET_KEY` bleibt erlaubt (Fallback auf `JWT_SECRET`;
ein neuer Schlüssel würde bereits verschlüsselte Integrations-Secrets
unlesbar machen). Dev/Test setzen `ENVIRONMENT=development` bzw. `test`
(`.env.example`, `docker-compose.override.yml`, `tests/conftest.py`).
`scripts/deploy.sh` setzt `production` auch bei Bestandsinstallationen.

### API-Dokumentation

`/docs`, `/redoc` und `/openapi.json` sind nur in Dev/Test erreichbar.
Gezielt umschalten: `FIELDVIBE_API_DOCS=1|0`.

### Zwei-Faktor-Anmeldung (TOTP) für Mitarbeiter

- Einrichtung im Profil („Zwei-Faktor-Anmeldung"): QR-Code (serverseitig als
  SVG erzeugt, keine externen Requests), Bestätigung mit einem Code, zehn
  Einmal-Wiederherstellungscodes (nur als HMAC gespeichert, einmalig sichtbar).
  Das Secret liegt Fernet-verschlüsselt in `users.mfa_secret_enc` (Schlüssel
  wie bei den Integrations-Secrets: `INTEGRATION_SECRET_KEY`, sonst
  `JWT_SECRET` – bei Rotation dieses Schlüssels müssen alle Nutzer MFA neu
  einrichten).
- Login zweistufig: `POST /api/auth/login` liefert bei aktiver MFA nur einen
  5 Minuten gültigen `mfa_token`; `POST /api/auth/mfa/verifizieren` tauscht ihn
  mit Code oder Wiederherstellungscode gegen die Tokens. Zeitfenster ±1 Schritt,
  ein Zeitschritt gilt nur einmal (Replay-Schutz). Fehlversuche zählen in
  denselben Login-Limitern wie das Passwort (5 je Konto / 20 je IP in 15 Min.).
- **Pflicht je Betrieb**: Integrationen → Sicherheit („Zwei-Faktor-Anmeldung
  vorschreiben", `firmendaten.mfa_pflicht`, Default aus). Betroffen sind alle
  Mandanten-Nutzer, nicht `super_admin`. Wer noch keine MFA hat, bekommt nur
  ein Einrichtungs-Token (alles außer `/me` und den MFA-Einrichtungsendpunkten
  antwortet 403); die App zeigt die Einrichtung vollbildig. Bereits
  ausgestellte Access-Tokens (30 Min.) laufen bis zum nächsten Refresh weiter.
  Bei Pflicht ist Deaktivieren gesperrt.
- **Verlorenes Gerät ohne Codes**: ein Admin setzt die MFA des Nutzers zurück
  (Accounts → „MFA zurücksetzen", `POST /api/users/{id}/mfa-zuruecksetzen`,
  Audit-Eintrag `mfa_zurueckgesetzt`, Nutzer wird überall abgemeldet). Hat der
  einzige Admin eines Betriebs beides verloren, kann ein `super_admin` ihn
  zurücksetzen. Weitere Audit-Einträge: `mfa_aktiviert`, `mfa_deaktiviert`,
  `mfa_wiederherstellungscode_verwendet`, `mfa_wiederherstellungscodes_erneuert`,
  `mfa_pflicht_geaendert`.
- Nicht enthalten: MFA für Kundenportal/Partnerportal, WebAuthn,
  Pflicht für `super_admin` (siehe `docs/BACKLOG.md`).

### Refresh-Token als HttpOnly-Cookie

Das Refresh-Token der Mitarbeiter liegt nicht mehr im Browser-Speicher,
sondern im Cookie `fv_refresh` (`HttpOnly; SameSite=Strict; Path=/api/auth`,
`Secure` außer Dev/Test und im IP-Betrieb). Der Access-Token (30 Min.) bleibt
wie bisher im `localStorage`, damit die Feld-App offline starten kann.

**Cookie-Variante (Entscheidung):** *host-only* am API-Host, kein
`Domain=`-Attribut. App (`app.<domain>`) und Office (`office.<domain>`) sprechen
beide mit **einem** API-Host (`api.<domain>`); das Cookie gehört diesem Host und
wird deshalb von beiden Oberflächen genutzt – sie teilen sich eine Sitzung (nach
dem Anmelden in einer Shell stellt die andere sie beim Start still wieder her),
Abmelden in einer meldet auch die andere ab. Fremde Subdomains erreichen das
Cookie nie. SameSite=Strict genügt, weil Frontend und API dieselbe registrierbare
Domain haben („same-site"). *Alternative:* `Domain=.<domain>` – nur nötig, wenn
die API je Oberfläche auf einem anderen Host liefe; sie öffnet das Cookie für
alle Subdomains (größere Angriffsfläche, z. B. Subdomain-Takeover) und wird
deshalb nicht verwendet.

**CSRF:** SameSite=Strict, dazu prüft `/api/auth/refresh` bei Cookie-Nutzung den
`Origin`-Header gegen `CORS_ORIGINS` (fehlt er oder ist er fremd: 403), und das
Frontend sendet den Header `X-Refresh-Cookie` (löst im Browser einen Preflight
aus). Das Cookie gilt nur für `/api/auth/*`.

**Übergangsfrist für alte Clients** (PWA-Bundle im Cache, Refresh-Token noch im
`localStorage`): bis einschließlich `FIELDVIBE_REFRESH_BODY_BIS` (Default
`2026-12-31`) wird das Refresh-Token noch im Antwort-Body geliefert und im
Request-Body akzeptiert (ohne Origin-Prüfung, es ist ein Bearer-Token). Neue
Clients bekommen es nie im Body. Nach dem Datum, oder bei leerem Wert, nur
noch Cookie; alte Clients landen dann einmalig auf der Login-Seite. Datum bei
Bedarf verlängern und nach Ablauf aus der Konfiguration entfernen.

Offen: Kundenportal und Partnerportal nutzen weiter Tokens im Browser-Speicher
(`docs/BACKLOG.md`).

### MinIO-Service-Account

Backend und Worker verbinden sich nicht mit dem MinIO-Root-Zugang, sondern mit
einem Service-Account, dessen Policy nur Objekte (Lesen/Schreiben/Löschen) und
das Auflisten des Buckets `S3_BUCKET_FOTOS` erlaubt. `scripts/deploy.sh` ruft
`scripts/minio-service-account.sh` auf (idempotent; legt Bucket, Policy
`fieldvibe-app` und den Account an, prüft mit dessen Zugang, dass ein fremder
Bucket nicht anlegbar ist, trägt `S3_ACCESS_KEY`/`S3_SECRET_KEY` in `.env` ein und
erzeugt Backend/Worker bei Änderung neu). Der Root-Zugang
(`MINIO_ROOT_USER`/`-PASSWORD`) bleibt für MinIO selbst und die Administration.
Manuell: `./scripts/minio-service-account.sh [--dry-run]`. Ist
`S3_ACCESS_KEY` leer, fällt die Compose-Datei auf den Root-Zugang zurück
(lokale Entwicklung). **Wurde bisher nicht gegen ein echtes MinIO getestet** (kein
Docker in der Entwicklungsumgebung): bei Problemen mit der `mc`-Syntax der
gepinnten MinIO-Version läuft der Stack mit dem Root-Zugang weiter, `deploy.sh`
warnt.

### Datenbank-Rolle: Besitz der Tabellen

Backend und Worker laufen als `NOSUPERUSER NOBYPASSRLS`-Rolle (Abschnitt 3).
Gehören dieser Rolle aber die Tabellen – der bisherige Standard, weil die
Migrationen über dieselbe Rolle laufen –, könnte sie RLS per `ALTER TABLE …
DISABLE ROW LEVEL SECURITY` selbst abschalten. Beim Start prüft
`app/db/rollen_pruefung.py` das und **warnt**. Härtung (opt-in):

```bash
./scripts/app_rolle_einrichten.sh --getrennter-owner --compose "docker compose -f docker-compose.yml -f docker-compose.prod.yml"
# oder bei deploy.sh: DB_GETRENNTER_OWNER=1 in die .env, Skript erneut ausführen
```

Danach gehören Tabellen/Funktionen/Typen einer eigenen Owner-Rolle
(`fieldvibe_owner`), die App-Rolle hat nur DML-Rechte (inkl. Default-Privilegien
für künftige Migrationen), die Owner-Zugangsdaten stehen in `.env.migration`
(nicht in `.env`, die als `env_file` in Backend/Worker geladen wird), Migrationen
laufen über `scripts/migrieren.sh`, und `FIELDVIBE_DB_BESITZ_VERBOTEN=1` lässt
den Start scheitern, falls die App-Rolle doch wieder Besitzerin wird. **Das SQL
und die Skriptverdrahtung wurden nicht gegen eine echte Datenbank mit
Rollenrechten getestet** – vor dem Einsatz auf einer Kopie der Produktionsdaten
probieren (`scripts/backup.sh` zuvor). `restore.sh`/Runbook-Schritte mit
`alembic` gehen weiter davon aus, dass die App-Rolle migriert; bei getrenntem
Owner stattdessen `scripts/migrieren.sh` verwenden.

## 6d. Betrieb: Monitoring, Logs, Healthchecks, Mail-Outbox

Alarmkette und Maßnahmen bei Störungen: **`docs/BETRIEB.md`**. Die Konfiguration im Überblick
(alles optional, Werte in der `.env`, Vorlage `.env.example`):

| Thema | Einstellung | Wirkung |
| --- | --- | --- |
| Logs | `LOG_FORMAT=json\|text`, `LOG_LEVEL` | JSON-Zeilen mit `request_id`, `mandant_id`, `user_id`, `job`; Standard `json` (Produktion) |
| Log-Rotation | Compose (`logging: json-file, max-size 10m, max-file 5`) | Alle Dienste, keine unbegrenzt wachsenden Container-Logs |
| Health | `HEALTH_TOKEN` | Details von `/health/ready` und `/health/heartbeats` für externes Monitoring |
| Worker-Ping | `HEARTBEAT_PING_URL` | healthchecks.io-kompatibler Ping des Workers (alle 60 s) |
| Error-Tracking | `SENTRY_DSN`, `VITE_SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_SAMPLE_RATE` | Sentry-kompatibel (GlitchTip); leer = aus |
| Mail-Outbox | `MAIL_OUTBOX_BACKOFF_MINUTEN`, `MAIL_OUTBOX_INTERVALL_SEKUNDEN` | Retry-Plan, Worker-Takt |
| Jobs | `SCHEDULER_TICK_SEKUNDEN`, `SCHEDULER_RETRY_MINUTEN`, `SCHEDULER_NACHHOLEN_MAX_TAGE` | Takt, Pause nach Fehlern, Alarmgrenze für Ausfälle |

**Healthchecks.** `GET /health` (Liveness, kein I/O), `GET /health/ready` (Datenbank, Objektspeicher,
Migrationsstand = Head; 200/503, ohne Ausweis nur `{"status": …}`), `GET /health/heartbeats`
(Worker-Tick, Mail-Sync, E-Mail-Rechnungseingang, Postfächer je Mandant, Mail-Outbox, Alter des Backups;
nur mit `HEALTH_TOKEN` oder als Plattform-Admin, sonst 404). Docker prüft Backend (`/health/ready`), Worker
(Heartbeat-Datei), Frontend (HTTP) und Caddy; abhängige Dienste starten mit `condition: service_healthy`.
Das Backup-Alter liest das Backend aus `letzter-lauf.json` (`BACKUP_DIR` wird schreibgeschützt nach
`/backups` eingehängt, `BACKUP_STATUS_DATEI`).

**Logs.** `docker compose logs -f backend worker`; jede Antwort trägt `X-Request-ID` (kommt aus dem
Proxy, wenn gültig, sonst neu erzeugt) – dieselbe ID steht in allen Log-Zeilen des Requests und im
Error-Tracking. Gelogt werden nie Tokens, Passwörter, Request-Bodies oder Query-Strings (Pfade als
Routenvorlage).

**Datenschutz Error-Tracking.** Standard aus. Wer es einschaltet, überträgt Fehlertexte und Stacktraces an
den gewählten Dienst: nur **EU-gehostet oder selbst betrieben** (z. B. GlitchTip auf eigenem Server),
Auftragsverarbeitungsvertrag (AVV) und Eintrag im Verzeichnis der Verarbeitungstätigkeiten nicht vergessen.
Übertragen werden keine Bodies, Cookies, Header-Werte, Query-Strings, SQL, Nutzer-/E-Mail-Daten (Backend:
`send_default_pii=False` plus eigener Filter; Frontend: schlanker Eigenbau ohne Session-Replay); Tokens,
Passwörter und IBANs in Texten werden geschwärzt. Mandant-ID und Request-ID gehen als Tags mit. Die
Content-Security-Policy öffnet `connect-src` nur für den Host aus `VITE_SENTRY_DSN` (`SENTRY_CSP_HOST`,
von `deploy.sh` gesetzt).

**Mail-Outbox.** Automatische Mails (Mahnwesen, Bestätigungs-/Widerrufsmails des Kundenportals) gehen
in die Tabelle `mail_outbox` und werden vom Worker *nach* dem Commit versendet; bei Fehlern wiederholt er
nach 1 min, 5 min, 30 min, 2 h, 12 h, danach gilt die Mail als fehlgeschlagen (Benachrichtigung an
Ersteller bzw. Disposition, Log-Event `mail_outbox_failed`). Der E-Mail-Verlauf zeigt „Wird gesendet“
bis zum Ergebnis. Fehlgeschlagene Mails: `GET /api/mail-outbox` (Administratoren), neu anstoßen mit
`POST /api/mail-outbox/{id}/wiederholen`. Synchron bleiben bewusst: vom Nutzer ausgelöste Sendungen
(Kunde, Vorgang, Angebot, Rechnung, Bestellung – der Nutzer braucht das Ergebnis sofort), Einladung und
Passwort-Reset (bei Fehlschlag liefert die Antwort den Link direkt zurück).

**Abhängigkeiten.** Dependabot (`.github/dependabot.yml`) schlägt wöchentlich gruppierte Updates vor
(pip, npm, docker, GitHub Actions); die CI führt `pip-audit` und `npm audit --omit=dev --audit-level=high`
nicht blockierend aus. Nach einem pip-PR die Lockfiles neu erzeugen (siehe „Abhängigkeiten aktualisieren“).

**Repository-Standardbranch.** Auf welchem Branch das Remote-HEAD steht, legt der Repository-Besitzer
auf GitHub fest (Settings → Branches); `deploy.sh` macht `git pull --ff-only` auf dem ausgecheckten
Branch, `GITHUB_BRANCH` steuert nur die Update-Anzeige.

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
die Daten noch gebraucht werden könnten (Wiederherstellen: Abschnitt 5).

## 8. Troubleshooting

- **Zertifikat wird nicht ausgestellt**: DNS-A-Records prüfen (müssen
  bereits vor dem ersten Start auf den Server zeigen), Port 80 muss von
  außen erreichbar sein (Let's Encrypt HTTP-01-Challenge). Logs:
  `docker compose logs caddy`.
- **`/health/ready` liefert 503**: Datenbank, Objektspeicher oder Migrationsstand
  stimmen nicht. Ohne Ausweis steht nur `nicht_bereit` im Body; die Ursache liefert
  `curl -H "Authorization: Bearer $HEALTH_TOKEN" https://<DOMAIN_API>/health/ready` bzw.
  `docs/BETRIEB.md`. Der ältere `/healthz` (DB + Objektspeicher + Zeitstempel des letzten
  Prüfzyklen-Laufs, `scheduler_letzter_lauf`) bleibt für die Super-Admin-Übersicht bestehen.
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
