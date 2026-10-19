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

`chmod 600 .env` nicht vergessen – die Datei enthält alle Secrets.

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

```bash
cd SocialCRM
git pull
export GIT_COMMIT="$(git rev-parse --short HEAD)"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm backend alembic upgrade head
```

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
auf GitHub, ohne selbst irgendetwas auszuführen. Ohne das `export` bleibt
die Anzeige auf „unknown" stehen, das Update selbst funktioniert trotzdem.

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
