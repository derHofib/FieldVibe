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
PG_USER="$(get_env POSTGRES_USER)"
PG_PW="$(get_env POSTGRES_PASSWORD)"
PG_DB="$(get_env POSTGRES_DB)"
set_env DATABASE_URL "postgresql+asyncpg://${PG_USER}:${PG_PW}@postgres:5432/${PG_DB}"
set_env DATABASE_URL_SYNC "postgresql+psycopg2://${PG_USER}:${PG_PW}@postgres:5432/${PG_DB}"

is_placeholder JWT_SECRET && set_env JWT_SECRET "$(gen_secret)"
is_placeholder INTEGRATION_SECRET_KEY && set_env INTEGRATION_SECRET_KEY "$(gen_secret)"
is_placeholder MINIO_ROOT_PASSWORD && set_env MINIO_ROOT_PASSWORD "$(gen_secret)"

# --- 6. Domains bzw. Server-IP ----------------------------------------------
if [[ "$DEPLOY_MODE" == "domain" ]]; then
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

# --- 7. Vorhandenes Repo aktualisieren (falls kein Erststart) --------------
if [[ -d .git ]] && git rev-parse --git-dir &>/dev/null; then
  if [[ -z "$(git status --porcelain)" ]]; then
    log "Hole neuesten Code-Stand (git pull)..."
    git pull --ff-only || warn "git pull fehlgeschlagen, fahre mit dem aktuellen Stand fort."
  else
    warn "Lokale Änderungen im Repo gefunden, überspringe 'git pull' -- committe oder verwirf sie zuerst, falls du aktualisieren willst."
  fi
fi

# --- 8. Stack starten -------------------------------------------------------
log "Baue und starte den Stack (Postgres, MinIO, Backend, Frontend, Worker$([[ "$DEPLOY_MODE" == "domain" ]] && echo ", Caddy"))..."
"${COMPOSE[@]}" up -d --build

if [[ "$DEPLOY_MODE" == "domain" ]]; then
  log "Caddy holt beim allerersten Start ein bis zwei Minuten lang die TLS-Zertifikate. Fortschritt: ${COMPOSE[*]} logs -f caddy"
fi

# --- 9. Migrationen ----------------------------------------------------------
log "Wende Datenbank-Migrationen an..."
"${COMPOSE[@]}" run --rm backend alembic upgrade head

# --- 10. Ersten Plattform-Administrator anlegen -----------------------------
read -rp $'\nJetzt einen Plattform-Administrator anlegen? [Y/n] ' create_admin
if [[ ! "$create_admin" =~ ^[Nn]$ ]]; then
  read -rp "E-Mail: " ADMIN_EMAIL
  read -rp "Name: " ADMIN_NAME
  "${COMPOSE[@]}" run --rm backend python -m app.cli create-super-admin --email "$ADMIN_EMAIL" --name "$ADMIN_NAME"
fi

# --- 11. Backup-Cron ----------------------------------------------------------
BACKUP_DIR_VAL="$(get_env BACKUP_DIR)"
mkdir -p "${BACKUP_DIR_VAL:-/opt/socialcrm-backups}"

if ! command -v crontab &>/dev/null; then
  if [[ $IS_ROOT -eq 1 ]] && command -v apt-get &>/dev/null; then
    log "crontab nicht gefunden, installiere cron..."
    apt-get update -qq && apt-get install -y -qq cron
    systemctl enable --now cron &>/dev/null || true
  else
    warn "crontab nicht gefunden und kann hier nicht automatisch installiert werden -- Backup-Cron wird übersprungen."
  fi
fi

CRON_LINE="30 2 * * * ${REPO_DIR}/scripts/backup.sh >> /var/log/socialcrm-backup.log 2>&1"
if command -v crontab &>/dev/null; then
  if ! crontab -l 2>/dev/null | grep -qF "${REPO_DIR}/scripts/backup.sh"; then
    log "Richte tägliches Backup per Cron ein (02:30 Uhr)..."
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab - \
      || warn "Cron-Eintrag konnte nicht angelegt werden, bitte manuell eintragen: $CRON_LINE"
  else
    log "Backup-Cron bereits eingerichtet, überspringe."
  fi
fi

# --- 12. Zusammenfassung ------------------------------------------------------
log "Fertig!"
if [[ "$DEPLOY_MODE" == "domain" ]]; then
  cat <<SUMMARY

  App:       https://$(get_env DOMAIN_APP)
  API-Docs:  https://$(get_env DOMAIN_API)/docs
  Backups:   ${BACKUP_DIR_VAL:-/opt/socialcrm-backups} (täglich 02:30 Uhr)

  Falls das Zertifikat noch nicht bereit ist:
    ${COMPOSE[*]} logs -f caddy

  Später aktualisieren: dieses Skript einfach erneut ausführen.
SUMMARY
else
  cat <<SUMMARY

  App:       http://$(get_env DEPLOY_IP):4173
  API-Docs:  http://$(get_env DEPLOY_IP):8000/docs
  Backups:   ${BACKUP_DIR_VAL:-/opt/socialcrm-backups} (täglich 02:30 Uhr)

  ⚠ Unverschlüsselt (kein HTTPS) -- nur für Tests/internes Netz gedacht.
    Für echten Betrieb später auf eine Domain umsteigen: die Zeile
    "DEPLOY_MODE=" aus der .env löschen und dieses Skript erneut ausführen.

  Später aktualisieren: dieses Skript einfach erneut ausführen.
SUMMARY
fi
