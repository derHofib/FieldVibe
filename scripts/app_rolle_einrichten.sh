#!/usr/bin/env bash
set -euo pipefail

# Richtet die Datenbank-Rolle ein, mit der Backend, Worker und Alembic sich
# verbinden (Standard: fieldvibe_app), und stellt .env darauf um.
#
# Warum: POSTGRES_USER ist im offiziellen postgres-Image der Bootstrap-
# Superuser; dem lassen sich SUPERUSER/BYPASSRLS nicht entziehen ("The
# bootstrap user must have the SUPERUSER attribute"), und ein Superuser
# umgeht jede RLS-Policy. Der Bootstrap-User bleibt deshalb reiner Admin, die
# Anwendung laeuft als eigene Rolle ohne Sonderrechte. Die eigentliche
# DB-Arbeit steckt in scripts/sql/app_rolle_einrichten.sql.
#
# Usage (im Repo-Verzeichnis auf dem Server):
#   ./scripts/app_rolle_einrichten.sh [--dry-run] [--ohne-backup]
#                                     [--compose "docker compose -f ... -f ..."]
#
# Idempotent: ein zweiter Lauf erkennt Rolle und Passwort und laeuft durch.
#
# Optionen:
#   --dry-run       nur anzeigen, was passieren wuerde, nichts aendern
#   --ohne-backup   Datenbank-Sicherung (scripts/backup.sh) ueberspringen
#   --nur-rolle     nur Rolle + .env (kein Backup, kein Neustart, keine
#                   Migrationen) -- fuer scripts/deploy.sh, das den Stack
#                   danach selbst startet
#   --compose "..." Compose-Aufruf statt Erkennung ueber DEPLOY_MODE in .env

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

log()  { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mWarnung:\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31mFehler:\033[0m %s\n' "$*" >&2; exit 1; }

DRY_RUN=0
OHNE_BACKUP=0
NUR_ROLLE=0
COMPOSE_ARG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)     DRY_RUN=1 ;;
    --ohne-backup) OHNE_BACKUP=1 ;;
    --nur-rolle)   NUR_ROLLE=1 ;;
    --compose)     shift; [[ $# -gt 0 ]] || err "--compose braucht ein Argument."; COMPOSE_ARG="$1" ;;
    -h|--help)     sed -n '3,28p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)             err "Unbekannte Option: $1 (siehe --help)" ;;
  esac
  shift
done

[[ -f docker-compose.yml && -f scripts/sql/app_rolle_einrichten.sql ]] \
  || err "Muss aus dem geklonten SocialCRM-Repo heraus ausgefuehrt werden."
[[ -f .env ]] || err ".env nicht gefunden -- zuerst scripts/deploy.sh ausfuehren oder .env aus .env.example anlegen."

get_env() { grep "^${1}=" .env 2>/dev/null | head -n1 | cut -d= -f2- || true; }

# Ersetzt den Wert in-place (erste Zeile, weitere Duplikate fallen weg) oder
# haengt an. Per awk/ENVIRON statt sed, damit Sonderzeichen im Wert (&, |, \)
# nicht als Ersetzungs-Syntax wirken.
set_env() {
  local tmp
  tmp="$(mktemp .env.XXXXXX)"
  KEY="$1" VAL="$2" awk '
    BEGIN { k = ENVIRON["KEY"]; v = ENVIRON["VAL"]; done = 0 }
    index($0, k "=") == 1 { if (!done) { print k "=" v; done = 1 } ; next }
    { print }
    END { if (!done) print k "=" v }
  ' .env > "$tmp"
  cat "$tmp" > .env
  rm -f "$tmp"
}
del_env() {
  local tmp
  tmp="$(mktemp .env.XXXXXX)"
  KEY="$1" awk 'index($0, ENVIRON["KEY"] "=") != 1' .env > "$tmp" || true
  cat "$tmp" > .env
  rm -f "$tmp"
}

# --- Compose-Aufruf ---------------------------------------------------------
if [[ -n "$COMPOSE_ARG" ]]; then
  read -ra COMPOSE <<< "$COMPOSE_ARG"
else
  case "$(get_env DEPLOY_MODE)" in
    domain) COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml) ;;
    ip)     COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.ip.yml) ;;
    *)      err "DEPLOY_MODE in .env nicht gesetzt -- Compose-Aufruf mit --compose \"docker compose -f docker-compose.yml -f docker-compose.prod.yml\" angeben." ;;
  esac
fi

PG_USER="$(get_env POSTGRES_USER)"; PG_USER="${PG_USER:-fieldvibe}"
PG_DB="$(get_env POSTGRES_DB)";     PG_DB="${PG_DB:-fieldvibe}"
APP_USER="$(get_env APP_DB_USER)";  APP_USER="${APP_USER:-fieldvibe_app}"
APP_PW="$(get_env APP_DB_PASSWORD)"

# Der Name landet in SQL-Bezeichnern und der Connection-URL -- nur harmlose
# Zeichen zulassen.
[[ "$APP_USER" =~ ^[a-z_][a-z0-9_]{0,62}$ ]] \
  || err "APP_DB_USER='$APP_USER' ist ungueltig (erlaubt: Kleinbuchstaben, Ziffern, Unterstrich)."
[[ "$APP_USER" != "$PG_USER" ]] \
  || err "APP_DB_USER darf nicht mit POSTGRES_USER ($PG_USER) identisch sein."
[[ "$PG_DB" =~ ^[A-Za-z0-9_]+$ ]] || err "POSTGRES_DB='$PG_DB' enthaelt unerwartete Zeichen."

PW_NEU=0
if [[ -z "$APP_PW" || "$APP_PW" == *changeme* ]]; then
  # Nur Hex: kein URL-Encoding noetig, wenn das Passwort in DATABASE_URL steht.
  APP_PW="$(openssl rand -hex 24)"
  PW_NEU=1
fi
[[ "$APP_PW" =~ ^[A-Za-z0-9._~-]+$ ]] \
  || err "APP_DB_PASSWORD in .env enthaelt Zeichen, die in der DATABASE_URL kodiert werden muessten -- Zeile loeschen, dann erzeugt das Skript ein neues."

STAMP="$(date +%Y%m%d-%H%M%S)"
ENV_BACKUP=".env.vor-app-rolle.${STAMP}"
URL_ASYNC="postgresql+asyncpg://${APP_USER}:${APP_PW}@postgres:5432/${PG_DB}"
URL_SYNC="postgresql+psycopg2://${APP_USER}:${APP_PW}@postgres:5432/${PG_DB}"

if [[ $DRY_RUN -eq 1 ]]; then
  log "Trockenlauf -- es wird nichts veraendert."
  cat <<PLAN
  Compose:          ${COMPOSE[*]}
  Admin-User/DB:    ${PG_USER} / ${PG_DB}
  App-Rolle:        ${APP_USER} ($([[ $PW_NEU -eq 1 ]] && echo "Passwort wird neu erzeugt" || echo "Passwort aus .env"))

  Geplante Schritte:
PLAN
  [[ $NUR_ROLLE -eq 0 && $OHNE_BACKUP -eq 0 ]] && echo "   1. Sicherung: scripts/backup.sh"
  echo "   2. .env kopieren nach ${ENV_BACKUP}"
  echo "   3. Postgres starten/abwarten: ${COMPOSE[*]} up -d postgres"
  echo "   4. scripts/sql/app_rolle_einrichten.sql als ${PG_USER} in ${PG_DB} ausfuehren (Rolle anlegen, Eigentum uebertragen)"
  echo "   5. .env: APP_DB_USER/APP_DB_PASSWORD, DATABASE_URL, DATABASE_URL_SYNC setzen; FIELDVIBE_ERLAUBE_RLS_BYPASS_ROLLE entfernen"
  if [[ $NUR_ROLLE -eq 0 ]]; then
    echo "   6. backend und worker neu erzeugen, bis zu 90 s auf 'healthy' warten"
    echo "   7. alembic upgrade head"
    echo "   Bei Fehlschlag in 6/7: .env aus ${ENV_BACKUP} zurueckspielen, backend/worker neu erzeugen, Exit 1"
  fi
  exit 0
fi

command -v docker &>/dev/null || err "docker nicht gefunden."
command -v openssl &>/dev/null || err "openssl nicht gefunden."

# --- (a) Sicherungen ---------------------------------------------------------
if [[ $NUR_ROLLE -eq 0 && $OHNE_BACKUP -eq 0 ]]; then
  log "Sichere die Datenbank (scripts/backup.sh)..."
  ./scripts/backup.sh || err "Backup fehlgeschlagen -- abgebrochen, es wurde nichts veraendert. Mit --ohne-backup auf eigene Verantwortung ueberspringen."
elif [[ $NUR_ROLLE -eq 0 ]]; then
  warn "Datenbank-Backup uebersprungen (--ohne-backup)."
fi
# Bei jedem deploy.sh-Lauf (--nur-rolle) eine Kopie anzulegen wuerde das
# Verzeichnis zumuellen -- nur sichern, wenn sich an .env wirklich etwas aendert.
if [[ $NUR_ROLLE -eq 0 || "$(get_env DATABASE_URL)" != "$URL_ASYNC" \
      || "$(get_env DATABASE_URL_SYNC)" != "$URL_SYNC" \
      || -n "$(get_env FIELDVIBE_ERLAUBE_RLS_BYPASS_ROLLE)" ]]; then
  cp -p .env "$ENV_BACKUP"
  chmod 600 "$ENV_BACKUP"
  log ".env gesichert: ${ENV_BACKUP}"
fi

# --- Postgres bereit ---------------------------------------------------------
log "Starte Postgres (falls noetig)..."
"${COMPOSE[@]}" up -d postgres
bereit=0
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T postgres pg_isready -U "$PG_USER" -d "$PG_DB" >/dev/null 2>&1; then bereit=1; break; fi
  sleep 1
done
[[ $bereit -eq 1 ]] || err "Postgres wurde nicht rechtzeitig bereit. Log: ${COMPOSE[*]} logs postgres"

# --- (c) SQL ausfuehren ------------------------------------------------------
# Die Variablen laufen per \set ueber stdin statt per -v: Kommandozeilen-
# Argumente waeren in der Prozessliste sichtbar, das Passwort nicht. Die
# Ausgabe wird zusaetzlich maskiert, falls eine Fehlermeldung es zitiert.
log "Richte Rolle ${APP_USER} ein und uebertrage das Eigentum an den Tabellen..."
if ! {
  printf '\\set app_rolle %s\n\\set app_passwort %s\n\\set db_name %s\n' "$APP_USER" "$APP_PW" "$PG_DB"
  cat scripts/sql/app_rolle_einrichten.sql
} | "${COMPOSE[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DB" -f - 2>&1 \
  | sed "s/${APP_PW}/***/g"; then
  err ".env unveraendert (Sicherung: ${ENV_BACKUP}). SQL-Schritt fehlgeschlagen, siehe Ausgabe oben."
fi

# --- (d) .env umstellen ------------------------------------------------------
log "Stelle .env auf die App-Rolle um..."
set_env APP_DB_USER "$APP_USER"
set_env APP_DB_PASSWORD "$APP_PW"
set_env DATABASE_URL "$URL_ASYNC"
set_env DATABASE_URL_SYNC "$URL_SYNC"
del_env FIELDVIBE_ERLAUBE_RLS_BYPASS_ROLLE
chmod 600 .env

if [[ $NUR_ROLLE -eq 1 ]]; then
  log "App-Rolle ${APP_USER} eingerichtet, .env umgestellt (Stack-Start folgt durch den Aufrufer)."
  exit 0
fi

# --- (e) Backend/Worker neu starten, Migrationen -----------------------------
rollback() {
  warn "Umstellung fehlgeschlagen -- spiele .env aus ${ENV_BACKUP} zurueck."
  cp -p "$ENV_BACKUP" .env
  "${COMPOSE[@]}" up -d --force-recreate --no-deps backend worker || warn "Neustart mit alter .env ebenfalls fehlgeschlagen."
  cat >&2 <<MSG

Die alte .env ist wiederhergestellt und backend/worker laufen wieder mit der alten Verbindung.
Die Eigentumsaenderungen in der Datenbank bleiben bestehen -- harmlos, ${PG_USER} ist
Superuser und kann weiterhin alles. Ein erneuter Lauf dieses Skripts ist gefahrlos.
Ursache finden: ${COMPOSE[*]} logs --tail=100 backend worker
MSG
  exit 1
}

log "Starte backend und worker mit der App-Rolle neu..."
"${COMPOSE[@]}" up -d --force-recreate --no-deps backend worker || rollback

log "Warte bis zu 90 s auf ein gesundes Backend..."
gesund=0
for _ in $(seq 1 45); do
  cid="$("${COMPOSE[@]}" ps -q backend 2>/dev/null || true)"
  status=""
  [[ -n "$cid" ]] && status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || true)"
  if [[ "$status" == "healthy" ]]; then gesund=1; break; fi
  sleep 2
done
[[ $gesund -eq 1 ]] || rollback

log "Wende Migrationen als ${APP_USER} an..."
"${COMPOSE[@]}" run --rm backend alembic upgrade head || rollback

log "Fertig. Backend und Worker laufen als ${APP_USER}; Row-Level-Security ist wirksam."
echo "  Sicherungen: ${ENV_BACKUP} (die Datei enthaelt das alte Passwort -- nach Kontrolle loeschen)."
