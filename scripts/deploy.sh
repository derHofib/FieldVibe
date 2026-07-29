#!/usr/bin/env bash
set -euo pipefail

# Automatisiertes Produktions-Deployment (Abschnitt 15, siehe
# docs/DEPLOYMENT.md fuer den manuellen Weg mit Erklaerungen). Fuehrt aus:
# Docker installieren, Firewall, .env mit generierten Secrets + Domains
# anlegen, Stack mit TLS starten, Migrationen, ersten Superadmin anlegen,
# taeglichen Backup-Cron einrichten.
#
# Usage (auf dem Zielserver, als root oder mit sudo):
#   git clone https://github.com/derHofib/SocialCRM.git
#   cd SocialCRM
#   sudo ./scripts/deploy.sh
#
# Idempotent: bereits gesetzte Secrets/Domains in einer vorhandenen .env
# werden nicht ueberschrieben, ein vorhandener Backup-Cron-Eintrag nicht
# dupliziert -- das Skript kann daher auch spaeter fuer Updates erneut
# ausgefuehrt werden (git pull + Stack neu bauen + Migrationen).

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

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

# --- 2. Firewall -----------------------------------------------------------
if [[ $IS_ROOT -eq 1 ]] && command -v ufw &>/dev/null; then
  log "Öffne Ports 22 (SSH), 80 und 443 (Let's Encrypt/HTTPS) in der Firewall..."
  ufw allow 22/tcp >/dev/null
  ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp >/dev/null
  if ! ufw status | grep -q "Status: active"; then
    warn "ufw ist noch nicht aktiv. Port 22 wurde freigegeben, prüfe aber vor dem Aktivieren selbst, dass du nicht ausgesperrt wirst:"
    echo "    ufw enable"
  fi
else
  warn "ufw nicht gefunden oder nicht root -- Firewall-Konfiguration übersprungen, bitte manuell prüfen (nur 22/80/443 sollten von außen erreichbar sein)."
fi

# --- 3. .env anlegen und Platzhalter-Secrets ersetzen ----------------------
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
get_env() { grep "^${1}=" .env | head -n1 | cut -d= -f2-; }
is_placeholder() { [[ "$(get_env "$1")" == *changeme* ]]; }

log "Prüfe/generiere Secrets in .env (bereits gesetzte Werte bleiben unverändert)..."

if is_placeholder POSTGRES_PASSWORD; then
  set_env POSTGRES_PASSWORD "$(gen_secret)"
fi
PG_USER="$(get_env POSTGRES_USER)"
PG_PW="$(get_env POSTGRES_PASSWORD)"
PG_DB="$(get_env POSTGRES_DB)"
set_env DATABASE_URL "postgresql+asyncpg://${PG_USER}:${PG_PW}@postgres:5432/${PG_DB}"
set_env DATABASE_URL_SYNC "postgresql+psycopg2://${PG_USER}:${PG_PW}@postgres:5432/${PG_DB}"

is_placeholder JWT_SECRET && set_env JWT_SECRET "$(gen_secret)"
is_placeholder INTEGRATION_SECRET_KEY && set_env INTEGRATION_SECRET_KEY "$(gen_secret)"
is_placeholder MINIO_ROOT_PASSWORD && set_env MINIO_ROOT_PASSWORD "$(gen_secret)"

# --- 4. Domains ------------------------------------------------------------
CURRENT_DOMAIN_APP="$(get_env DOMAIN_APP)"
if [[ "$CURRENT_DOMAIN_APP" == "app.example.de" || -z "$CURRENT_DOMAIN_APP" ]]; then
  log "Domains konfigurieren. Die drei DNS-A-Records müssen schon jetzt auf diesen Server zeigen."
  read -rp "App-Domain (z.B. app.deinefirma.de): " DOMAIN_APP
  read -rp "API-Domain (z.B. api.deinefirma.de): " DOMAIN_API
  read -rp "Fotos/S3-Domain (z.B. s3.deinefirma.de): " DOMAIN_S3
  read -rp "E-Mail für Let's-Encrypt-Benachrichtigungen: " CADDY_EMAIL

  set_env DOMAIN_APP "$DOMAIN_APP"
  set_env DOMAIN_API "$DOMAIN_API"
  set_env DOMAIN_S3 "$DOMAIN_S3"
  set_env CADDY_EMAIL "$CADDY_EMAIL"
  set_env CORS_ORIGINS "[\"https://${DOMAIN_APP}\"]"
  set_env VITE_API_BASE_URL "https://${DOMAIN_API}"
  set_env S3_PUBLIC_URL_BASE "https://${DOMAIN_S3}"
  set_env FRONTEND_BASE_URL "https://${DOMAIN_APP}"
  set_env ENVIRONMENT "production"
else
  log "Domains bereits konfiguriert (${CURRENT_DOMAIN_APP}), überspringe Abfrage."
fi

# --- 5. Vorhandenes Repo aktualisieren (falls kein Erststart) --------------
if [[ -d .git ]] && git rev-parse --git-dir &>/dev/null; then
  if [[ -z "$(git status --porcelain)" ]]; then
    log "Hole neuesten Code-Stand (git pull)..."
    git pull --ff-only || warn "git pull fehlgeschlagen, fahre mit dem aktuellen Stand fort."
  else
    warn "Lokale Änderungen im Repo gefunden, überspringe 'git pull' -- committe oder verwirf sie zuerst, falls du aktualisieren willst."
  fi
fi

# --- 6. Stack starten -------------------------------------------------------
log "Baue und starte den Stack (Postgres, MinIO, Backend, Frontend, Worker, Caddy)..."
"${COMPOSE[@]}" up -d --build

log "Caddy holt beim allerersten Start ein bis zwei Minuten lang die TLS-Zertifikate. Fortschritt: ${COMPOSE[*]} logs -f caddy"

# --- 7. Migrationen ----------------------------------------------------------
log "Wende Datenbank-Migrationen an..."
"${COMPOSE[@]}" run --rm backend alembic upgrade head

# --- 8. Ersten Plattform-Administrator anlegen -----------------------------
read -rp $'\nJetzt einen Plattform-Administrator anlegen? [Y/n] ' create_admin
if [[ ! "$create_admin" =~ ^[Nn]$ ]]; then
  read -rp "E-Mail: " ADMIN_EMAIL
  read -rp "Name: " ADMIN_NAME
  "${COMPOSE[@]}" run --rm backend python -m app.cli create-super-admin --email "$ADMIN_EMAIL" --name "$ADMIN_NAME"
fi

# --- 9. Backup-Cron ----------------------------------------------------------
BACKUP_DIR_VAL="$(get_env BACKUP_DIR)"
mkdir -p "${BACKUP_DIR_VAL:-/opt/socialcrm-backups}"
CRON_LINE="30 2 * * * ${REPO_DIR}/scripts/backup.sh >> /var/log/socialcrm-backup.log 2>&1"
if ! crontab -l 2>/dev/null | grep -qF "${REPO_DIR}/scripts/backup.sh"; then
  log "Richte tägliches Backup per Cron ein (02:30 Uhr)..."
  (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
else
  log "Backup-Cron bereits eingerichtet, überspringe."
fi

# --- 10. Zusammenfassung ------------------------------------------------------
log "Fertig!"
cat <<SUMMARY

  App:       https://$(get_env DOMAIN_APP)
  API-Docs:  https://$(get_env DOMAIN_API)/docs
  Backups:   ${BACKUP_DIR_VAL:-/opt/socialcrm-backups} (täglich 02:30 Uhr)

  Falls das Zertifikat noch nicht bereit ist:
    ${COMPOSE[*]} logs -f caddy

  Später aktualisieren: dieses Skript einfach erneut ausführen.
SUMMARY
