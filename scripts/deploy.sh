#!/usr/bin/env bash
set -euo pipefail

# Automatisiertes Produktions-Deployment (Abschnitt 15, siehe
# docs/DEPLOYMENT.md fuer den manuellen Weg mit Erklaerungen). Fuehrt aus:
# Docker installieren, Firewall, .env mit generierten Secrets + Domains
# (oder Server-IP, siehe unten) anlegen, Stack starten, Migrationen,
# ersten Superadmin anlegen, taeglichen Backup-Cron einrichten.
#
# Usage (auf dem Zielserver, als root oder mit sudo):
#   git clone https://github.com/derHofib/SocialCRM.git
#   cd SocialCRM
#   sudo ./scripts/deploy.sh
#
# Zwei Betriebsarten, beim ersten Lauf abgefragt:
#   - "domain": drei DNS-Subdomains (eigene oder kostenlose wie sslip.io) +
#     automatisches TLS-Zertifikat via Caddy/Let's Encrypt. Fuer echten Betrieb.
#   - "ip": kein DNS noetig, Zugriff nur ueber http://<server-ip>:<port> ohne
#     TLS. NUR fuer Tests oder ein abgeschottetes internes Netz -- Anfragen
#     (inkl. Passwoerter, Kundendaten) laufen unverschluesselt.
#
# Idempotent: bereits gesetzte Secrets/Domains/Modus in einer vorhandenen
# .env werden nicht ueberschrieben, ein vorhandener Backup-Cron-Eintrag
# nicht dupliziert -- das Skript kann daher auch spaeter fuer Updates
# erneut ausgefuehrt werden (git pull + Stack neu bauen + Migrationen).

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

log()  { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mWarnung:\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31mFehler:\033[0m %s\n' "$*" >&2; exit 1; }

[[ -f "docker-compose.yml" && -f "Caddyfile" ]] || err "Muss aus dem geklonten SocialCRM-Repo heraus ausgefuehrt werden (docker-compose.yml/Caddyfile nicht gefunden)."

IS_ROOT=0
[[ $EUID -eq 0 ]] && IS_ROOT=1

# --- 1. Docker + Compose-Plugin ------------------------------------------
if ! command -v docker &>/dev/null; then
  if [[ $IS_ROOT -eq 1 ]]; then
    log "Docker nicht gefunden, installiere..."
    curl -fsSL https://get.docker.com | sh
  else
    err "Docker ist nicht installiert und dieses Skript läuft nicht als root, um es zu installieren. Mit 'sudo ./scripts/deploy.sh' erneut ausführen, oder Docker vorher manuell installieren."
  fi
else
  log "Docker bereits installiert ($(docker --version))."
fi

if ! docker compose version &>/dev/null; then
  if [[ $IS_ROOT -eq 1 ]] && command -v apt-get &>/dev/null; then
    log "Docker-Compose-Plugin nicht gefunden, installiere..."
    apt-get update -qq && apt-get install -y -qq docker-compose-plugin
  else
    err "Docker-Compose-Plugin fehlt und kann hier nicht automatisch installiert werden (kein apt-get oder nicht root). Siehe https://docs.docker.com/compose/install/"
  fi
fi

# --- 2. .env anlegen -------------------------------------------------------
if [[ ! -f .env ]]; then
  log ".env nicht gefunden, lege sie aus .env.example an..."
  cp .env.example .env
fi
chmod 600 .env

gen_secret() { openssl rand -base64 48 | tr -d '\n=/+' ; }
set_env() {
  local key="$1" value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    echo "${key}=${value}" >> .env
  fi
}
get_env() { grep "^${1}=" .env 2>/dev/null | head -n1 | cut -d= -f2- || true; }
is_placeholder() { [[ "$(get_env "$1")" == *changeme* ]]; }

# --- 3. Betriebsart: Domain (mit TLS) oder nur Server-IP (ohne TLS) --------
DEPLOY_MODE="$(get_env DEPLOY_MODE)"
if [[ -z "$DEPLOY_MODE" ]]; then
  echo
  echo "Wie soll der Server erreichbar sein?"
  echo "  1) Über eine Domain, mit automatischem HTTPS-Zertifikat (empfohlen für echten Betrieb;"
  echo "     auch eine kostenlose IP-Domain wie sslip.io funktioniert hier)"
  echo "  2) Nur über die Server-IP, ohne HTTPS (nur für Tests oder ein internes Netz -- Daten"
  echo "     inkl. Passwörter/Kundendaten laufen dabei unverschlüsselt über das Netz)"
  read -rp "Auswahl [1/2]: " mode_choice
  if [[ "$mode_choice" == "2" ]]; then
    DEPLOY_MODE="ip"
  else
    DEPLOY_MODE="domain"
  fi
  set_env DEPLOY_MODE "$DEPLOY_MODE"
else
  log "Betriebsart bereits konfiguriert: ${DEPLOY_MODE}."
fi

if [[ "$DEPLOY_MODE" == "domain" ]]; then
  COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
else
  COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.ip.yml)
fi

# --- 4. Firewall -----------------------------------------------------------
if [[ $IS_ROOT -eq 1 ]] && command -v ufw &>/dev/null; then
  if [[ "$DEPLOY_MODE" == "domain" ]]; then
    log "Öffne Ports 22 (SSH), 80 und 443 (Let's Encrypt/HTTPS) in der Firewall..."
    ufw allow 22/tcp >/dev/null
    ufw allow 80/tcp >/dev/null
    ufw allow 443/tcp >/dev/null
  else
    log "Öffne Ports 22 (SSH), 4173 (App), 8000 (API) und 9000 (Fotos) in der Firewall..."
    ufw allow 22/tcp >/dev/null
    ufw allow 4173/tcp >/dev/null
    ufw allow 8000/tcp >/dev/null
    ufw allow 9000/tcp >/dev/null
    warn "Diese Ports sind damit für JEDEN im Internet erreichbar, unverschlüsselt. Für mehr als einen kurzen Test: Zugriff auf bestimmte Quell-IPs einschränken, z. B.:"
    echo "    ufw allow from <deine-ip> to any port 4173,8000,9000 proto tcp"
    echo "    ufw delete allow 4173/tcp; ufw delete allow 8000/tcp; ufw delete allow 9000/tcp"
  fi
  if ! ufw status | grep -q "Status: active"; then
    warn "ufw ist noch nicht aktiv. Port 22 wurde freigegeben, prüfe aber vor dem Aktivieren selbst, dass du nicht ausgesperrt wirst:"
    echo "    ufw enable"
  fi
else
  warn "ufw nicht gefunden oder nicht root -- Firewall-Konfiguration übersprungen, bitte manuell prüfen."
fi

# --- 5. Secrets -------------------------------------------------------------
log "Prüfe/generiere Secrets in .env (bereits gesetzte Werte bleiben unverändert)..."

is_placeholder POSTGRES_PASSWORD && set_env POSTGRES_PASSWORD "$(gen_secret)"
# DATABASE_URL/DATABASE_URL_SYNC setzt scripts/app_rolle_einrichten.sh in
# Abschnitt 8 -- die Anwendung verbindet sich als eigene App-Rolle, nicht als
# POSTGRES_USER (Bootstrap-Superuser, siehe dort).

is_placeholder JWT_SECRET && set_env JWT_SECRET "$(gen_secret)"
is_placeholder INTEGRATION_SECRET_KEY && set_env INTEGRATION_SECRET_KEY "$(gen_secret)"
is_placeholder MINIO_ROOT_PASSWORD && set_env MINIO_ROOT_PASSWORD "$(gen_secret)"
# Auch Bestandsinstallationen: eine aus .env.example kopierte .env traegt
# ENVIRONMENT=development -- das haette die Startpruefung auf Platzhalter-
# Secrets (app/core/config.py) und die API-Doku-Sperre ausgehebelt.
set_env ENVIRONMENT "production"
# Eigener Key statt gen_secret(): MinIO braucht echtes, unverstuemmeltes
# Base64 eines 32-Byte-Schluessels (gen_secret() entfernt bewusst
# =/+ fuer Passwoerter, die z.B. in einer DATABASE_URL landen).
is_placeholder MINIO_KMS_SECRET_KEY && set_env MINIO_KMS_SECRET_KEY "fieldvibe-minio:$(openssl rand -base64 32)"

# --- 6. Domains bzw. Server-IP ----------------------------------------------
# Fester Standard fuer dieses Deployment -- Enter druecken uebernimmt ihn,
# eigene Eingabe ueberschreibt ihn bei Bedarf trotzdem noch.
DEFAULT_DOMAIN_BASE="fieldvibe.de"

if [[ "$DEPLOY_MODE" == "domain" ]]; then
  CURRENT_DOMAIN_APP="$(get_env DOMAIN_APP)"
  if [[ "$CURRENT_DOMAIN_APP" == "app.example.de" || -z "$CURRENT_DOMAIN_APP" ]]; then
    log "Domains konfigurieren. Die vier DNS-A-Records müssen schon jetzt auf diesen Server zeigen."
    read -rp "App-Domain (Handy) [app.${DEFAULT_DOMAIN_BASE}]: " DOMAIN_APP
    DOMAIN_APP="${DOMAIN_APP:-app.${DEFAULT_DOMAIN_BASE}}"
    read -rp "Office-Domain (Desktop) [office.${DEFAULT_DOMAIN_BASE}]: " DOMAIN_OFFICE
    DOMAIN_OFFICE="${DOMAIN_OFFICE:-office.${DEFAULT_DOMAIN_BASE}}"
    read -rp "API-Domain [api.${DEFAULT_DOMAIN_BASE}]: " DOMAIN_API
    DOMAIN_API="${DOMAIN_API:-api.${DEFAULT_DOMAIN_BASE}}"
    read -rp "Fotos/S3-Domain [s3.${DEFAULT_DOMAIN_BASE}]: " DOMAIN_S3
    DOMAIN_S3="${DOMAIN_S3:-s3.${DEFAULT_DOMAIN_BASE}}"
    read -rp "E-Mail für Let's-Encrypt-Benachrichtigungen [admin@${DEFAULT_DOMAIN_BASE}]: " CADDY_EMAIL
    CADDY_EMAIL="${CADDY_EMAIL:-admin@${DEFAULT_DOMAIN_BASE}}"

    set_env DOMAIN_APP "$DOMAIN_APP"
    set_env DOMAIN_OFFICE "$DOMAIN_OFFICE"
    set_env DOMAIN_API "$DOMAIN_API"
    set_env DOMAIN_S3 "$DOMAIN_S3"
    set_env CADDY_EMAIL "$CADDY_EMAIL"
    set_env CORS_ORIGINS "[\"https://${DOMAIN_APP}\",\"https://${DOMAIN_OFFICE}\"]"
    set_env VITE_API_BASE_URL "https://${DOMAIN_API}"
    set_env S3_PUBLIC_URL_BASE "https://${DOMAIN_S3}"
    set_env FRONTEND_BASE_URL "https://${DOMAIN_APP}"
    set_env ENVIRONMENT "production"
  elif [[ -z "$(get_env DOMAIN_OFFICE)" || "$(get_env DOMAIN_OFFICE)" == "office.example.de" ]]; then
    # Nachtrag fuer Bestandsinstallationen: die Domains von oben sind laengst
    # gesetzt, die Office-Domain kam erst spaeter dazu. Ohne diesen Zweig
    # wuerde sie auf einem Update-Lauf nie gefuellt -- Caddy bekaeme ein leeres
    # {$DOMAIN_OFFICE} und CORS_ORIGINS bliebe einwertig.
    log "Office-Domain (Desktop-Oberfläche) ist noch nicht konfiguriert."
    warn "Der DNS-A-Record dafür muss bereits auf diesen Server zeigen, sonst bekommt Caddy kein Zertifikat."
    read -rp "Office-Domain [office.${DEFAULT_DOMAIN_BASE}]: " DOMAIN_OFFICE
    DOMAIN_OFFICE="${DOMAIN_OFFICE:-office.${DEFAULT_DOMAIN_BASE}}"
    set_env DOMAIN_OFFICE "$DOMAIN_OFFICE"
    set_env CORS_ORIGINS "[\"https://${CURRENT_DOMAIN_APP}\",\"https://${DOMAIN_OFFICE}\"]"
    log "Office-Domain gesetzt (${DOMAIN_OFFICE}), CORS_ORIGINS auf beide Frontends erweitert."
  else
    log "Domains bereits konfiguriert (${CURRENT_DOMAIN_APP}, $(get_env DOMAIN_OFFICE)), überspringe Abfrage."
  fi
else
  CURRENT_IP="$(get_env DEPLOY_IP)"
  if [[ -z "$CURRENT_IP" ]]; then
    log "Ermittle die öffentliche Server-IP..."
    DETECTED_IP="$(curl -fsSL -4 --max-time 5 https://api.ipify.org 2>/dev/null || true)"
    [[ -z "$DETECTED_IP" ]] && DETECTED_IP="$(curl -fsSL -4 --max-time 5 https://ifconfig.me 2>/dev/null || true)"
    [[ -z "$DETECTED_IP" ]] && DETECTED_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"

    if [[ -n "$DETECTED_IP" ]]; then
      read -rp "Server-IP [$DETECTED_IP]: " SERVER_IP
      SERVER_IP="${SERVER_IP:-$DETECTED_IP}"
    else
      read -rp "Konnte die IP nicht automatisch ermitteln. Server-IP eingeben: " SERVER_IP
    fi

    set_env DEPLOY_IP "$SERVER_IP"
    set_env CORS_ORIGINS "[\"http://${SERVER_IP}:4173\"]"
    set_env VITE_API_BASE_URL "http://${SERVER_IP}:8000"
    set_env S3_PUBLIC_URL_BASE "http://${SERVER_IP}:9000"
    set_env FRONTEND_BASE_URL "http://${SERVER_IP}:4173"
    set_env ENVIRONMENT "production"
  else
    log "Server-IP bereits konfiguriert (${CURRENT_IP}), überspringe Abfrage."
  fi
fi

# --- 6b. Rechtstexte (Impressum/Datenschutz) ---------------------------------
# Nur Hinweis, kein Abbruch: die Links werden zur Build-Zeit ins Frontend
# gebacken; ohne Wert zeigt das Frontend die Platzhalter-Seiten der App.
for legal_var in VITE_IMPRESSUM_URL VITE_DATENSCHUTZ_URL; do
  if [[ -z "$(get_env "$legal_var")" ]]; then
    log "Hinweis: ${legal_var} ist in der .env nicht gesetzt -- die App nutzt Platzhalter-Seiten (/impressum, /datenschutz); echte URLs in den Firmendaten oder in der .env hinterlegen (Pflicht für den Produktivbetrieb, §5 DDG / Art. 13 DSGVO). Nach einer .env-Änderung dieses Skript erneut ausführen, damit das Frontend neu gebaut wird."
  fi
done

# --- 7. Vorhandenes Repo aktualisieren (falls kein Erststart) --------------
if [[ -d .git ]] && git rev-parse --git-dir &>/dev/null; then
  if [[ -z "$(git status --porcelain)" ]]; then
    log "Hole neuesten Code-Stand (git pull)..."
    git pull --ff-only || warn "git pull fehlgeschlagen, fahre mit dem aktuellen Stand fort."
  else
    warn "Lokale Änderungen im Repo gefunden, überspringe 'git pull' -- committe oder verwirf sie zuerst, falls du aktualisieren willst."
  fi
fi

# --- 8. Datenbank-Rolle absichern ------------------------------------------
# Das offizielle postgres-Image macht POSTGRES_USER zum Bootstrap-Superuser,
# dem sich SUPERUSER/BYPASSRLS nicht entziehen lassen -- und ein Superuser
# umgeht Row-Level-Security immer. Backend und Worker verweigern daher den
# Start mit so einer Rolle (app/db/rollen_pruefung.py). Stattdessen laeuft
# die Anwendung als eigene Rolle (APP_DB_USER, Standard fieldvibe_app); das
# Skript legt sie an, uebertraegt das Eigentum an bestehenden Tabellen und
# stellt DATABASE_URL in .env um. Muss VOR dem Start von Backend/Worker und
# den Migrationen laufen; bei einer Neuinstallation ist das Schema noch
# leer. Idempotent, bei jedem Lauf sicher wiederholbar.
log "Richte die Datenbank-Rolle für die Anwendung ein (Voraussetzung für wirksame Mandantentrennung per Row-Level-Security)..."
# Optional (DB_GETRENNTER_OWNER=1 in der .env oder schon vorhandene .env.migration):
# getrennte Owner-Rolle, damit die App-Rolle RLS nicht per ALTER TABLE abschalten kann.
OWNER_ARG=()
if [[ "$(get_env DB_GETRENNTER_OWNER)" == "1" || -f .env.migration ]]; then OWNER_ARG=(--getrennter-owner); fi
./scripts/app_rolle_einrichten.sh --nur-rolle ${OWNER_ARG[@]+"${OWNER_ARG[@]}"} --compose "${COMPOSE[*]}" \
  || err "Einrichtung der App-Rolle fehlgeschlagen -- Row-Level-Security wäre sonst wirkungslos, Deployment abgebrochen."

# --- 8a. MinIO-Image bereitstellen -------------------------------------------
# Das in docker-compose.yml gepinnte MinIO-Tag gibt es auf Docker Hub nicht
# (MinIO liefert keine Community-Images mehr) -- es wird lokal aus dem
# bisherigen :latest erzeugt, damit `up` nicht am Pull scheitert.
MINIO_IMAGE="$(grep -oE 'minio/minio:RELEASE[^[:space:]]+' docker-compose.yml | head -n1)"
if [[ -n "$MINIO_IMAGE" ]] && ! docker image inspect "$MINIO_IMAGE" &>/dev/null; then
  if docker image inspect minio/minio:latest &>/dev/null || docker pull minio/minio:latest; then
    log "Setze lokales MinIO-Tag $MINIO_IMAGE (aus minio/minio:latest)..."
    docker tag minio/minio:latest "$MINIO_IMAGE"
  else
    err "MinIO-Image $MINIO_IMAGE nicht verfügbar und minio/minio:latest nicht ladbar."
  fi
fi

# --- 8b. Stack starten ------------------------------------------------------
# GIT_COMMIT wird als Build-Arg ins Backend-Image gebacken -- rein fuer die
# informative Update-Anzeige im Super-Admin-Bereich (aktueller vs. neuester
# Commit auf GitHub), siehe app/services/version_service.py. Kein git-
# Repo (z.B. per curl heruntergeladenes Tarball) -> bleibt "unknown".
GIT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
export GIT_COMMIT
log "Baue und starte den Stack (Postgres, MinIO, Backend, Frontend, Worker$([[ "$DEPLOY_MODE" == "domain" ]] && echo ", Caddy"))..."
"${COMPOSE[@]}" up -d --build

if [[ "$DEPLOY_MODE" == "domain" ]]; then
  log "Caddy holt beim allerersten Start ein bis zwei Minuten lang die TLS-Zertifikate. Fortschritt: ${COMPOSE[*]} logs -f caddy"
fi

# --- 8c. MinIO-Service-Account ----------------------------------------------
# Backend und Worker sollen nicht mit dem MinIO-Root-Zugang laufen, sondern mit
# einem Service-Account, dessen Policy nur den Foto-Bucket erlaubt. Idempotent;
# nur bei geaenderten Zugangsdaten werden Backend/Worker neu erzeugt. Scheitert
# der Schritt (z. B. mc-Syntax anderer MinIO-Version), laeuft der Stack mit dem
# Root-Zugang weiter -- das ist ein Sicherheitshinweis, kein Deployment-Abbruch.
log "Richte den MinIO-Service-Account für die Anwendung ein (Bucket-beschränkter Zugang statt Root)..."
S3_KEY_VORHER="$(get_env S3_ACCESS_KEY):$(get_env S3_SECRET_KEY)"
if ./scripts/minio-service-account.sh --compose "${COMPOSE[*]}"; then
  if [[ "$S3_KEY_VORHER" != "$(get_env S3_ACCESS_KEY):$(get_env S3_SECRET_KEY)" ]]; then
    "${COMPOSE[@]}" up -d --force-recreate --no-deps backend worker
  fi
else
  warn "MinIO-Service-Account konnte nicht eingerichtet werden -- Backend/Worker nutzen weiter den Root-Zugang. Nachholen: ./scripts/minio-service-account.sh (siehe docs/DEPLOYMENT.md, Abschnitt Sicherheit)."
fi

# --- 9. Migrationen ----------------------------------------------------------
log "Wende Datenbank-Migrationen an..."
./scripts/migrieren.sh --compose "${COMPOSE[*]}"

# --- 10. Ersten Plattform-Administrator anlegen -----------------------------
read -rp $'\nJetzt einen Plattform-Administrator anlegen? [Y/n] ' create_admin
if [[ ! "$create_admin" =~ ^[Nn]$ ]]; then
  read -rp "E-Mail: " ADMIN_EMAIL
  read -rp "Name: " ADMIN_NAME
  "${COMPOSE[@]}" run --rm backend python -m app.cli create-super-admin --email "$ADMIN_EMAIL" --name "$ADMIN_NAME"
fi

# --- 11. Backup-Cron ----------------------------------------------------------
BACKUP_DIR_VAL="$(get_env BACKUP_DIR)"
mkdir -p "${BACKUP_DIR_VAL:-/opt/fieldvibe-backups}"

if ! command -v crontab &>/dev/null; then
  if [[ $IS_ROOT -eq 1 ]] && command -v apt-get &>/dev/null; then
    log "crontab nicht gefunden, installiere cron..."
    apt-get update -qq && apt-get install -y -qq cron
    systemctl enable --now cron &>/dev/null || true
  else
    warn "crontab nicht gefunden und kann hier nicht automatisch installiert werden -- Backup-Cron wird übersprungen."
  fi
fi

CRON_LINE="30 2 * * * ${REPO_DIR}/scripts/backup.sh >> /var/log/fieldvibe-backup.log 2>&1"
PRUEF_CRON_LINE="30 4 * * 0 ${REPO_DIR}/scripts/backup-pruefen.sh >> /var/log/fieldvibe-backup-pruefen.log 2>&1"
if command -v crontab &>/dev/null; then
  if ! crontab -l 2>/dev/null | grep -qF "${REPO_DIR}/scripts/backup.sh"; then
    log "Richte tägliches Backup per Cron ein (02:30 Uhr)..."
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab - \
      || warn "Cron-Eintrag konnte nicht angelegt werden, bitte manuell eintragen: $CRON_LINE"
  else
    log "Backup-Cron bereits eingerichtet, überspringe."
  fi
  if ! crontab -l 2>/dev/null | grep -qF "${REPO_DIR}/scripts/backup-pruefen.sh"; then
    log "Richte wöchentliche Backup-Prüfung (Test-Restore) per Cron ein (sonntags 04:30 Uhr)..."
    (crontab -l 2>/dev/null; echo "$PRUEF_CRON_LINE") | crontab - \
      || warn "Cron-Eintrag konnte nicht angelegt werden, bitte manuell eintragen: $PRUEF_CRON_LINE"
  else
    log "Cron für die Backup-Prüfung bereits eingerichtet, überspringe."
  fi
fi

# Nur Hinweise, nichts Interaktives: die Werte gehören in die .env (siehe
# .env.example, Block "Backups").
if [[ -z "$(get_env BACKUP_TARGETS)" && -z "$(get_env BACKUP_OFFSITE_REMOTE)" ]]; then
  warn "Weder BACKUP_TARGETS noch BACKUP_OFFSITE_REMOTE in der .env gesetzt -- die Backups liegen nur auf diesem Server und überleben einen Plattendefekt oder Totalverlust nicht. Ziele einrichten: docs/DEPLOYMENT.md, Abschnitt 5."
fi
if [[ -z "$(get_env BACKUP_GPG_RECIPIENT)" ]]; then
  warn "BACKUP_GPG_RECIPIENT in der .env nicht gesetzt -- Backups sind unverschlüsselt, das Secrets-Bündel (.env) wird dann nur lokal abgelegt, und Uploads zu Remote-Zielen werden verweigert. Einrichtung: docs/DEPLOYMENT.md, Abschnitt 5."
fi

# --- 12. Zusammenfassung ------------------------------------------------------
log "Fertig!"
if [[ "$DEPLOY_MODE" == "domain" ]]; then
  cat <<SUMMARY

  App (Handy):     https://$(get_env DOMAIN_APP)
  Office (Desktop): https://$(get_env DOMAIN_OFFICE)
  Backups:         ${BACKUP_DIR_VAL:-/opt/fieldvibe-backups} (täglich 02:30 Uhr, Prüfung sonntags 04:30 Uhr)

  Falls das Zertifikat noch nicht bereit ist:
    ${COMPOSE[*]} logs -f caddy

  Später aktualisieren: dieses Skript einfach erneut ausführen.
SUMMARY
else
  cat <<SUMMARY

  App:       http://$(get_env DEPLOY_IP):4173
  Backups:   ${BACKUP_DIR_VAL:-/opt/fieldvibe-backups} (täglich 02:30 Uhr, Prüfung sonntags 04:30 Uhr)

  ⚠ Unverschlüsselt (kein HTTPS) -- nur für Tests/internes Netz gedacht.
    Für echten Betrieb später auf eine Domain umsteigen: die Zeile
    "DEPLOY_MODE=" aus der .env löschen und dieses Skript erneut ausführen.

  Hinweis: Die Desktop-Oberfläche braucht eine eigene Subdomain und ist im
    IP-Modus deshalb nicht erreichbar. Auf einem breiten Bildschirm lässt sie
    sich unter obiger Adresse mit ?office=1 trotzdem ansehen.

  Später aktualisieren: dieses Skript einfach erneut ausführen.
SUMMARY
fi
