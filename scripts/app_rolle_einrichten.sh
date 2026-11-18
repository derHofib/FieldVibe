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
# Zusaetzlich entsteht die System-Rolle (Standard fieldvibe_system, LOGIN
# NOSUPERUSER BYPASSRLS, besitzt keine Tabellen): sie traegt system_session()
# (DATABASE_URL_SYSTEM). Der RLS-Bypass haengt so an einer DB-Rolle statt an
# einer Session-Variable, die jede App-Verbindung setzen koennte.
#
# Standard ist eine getrennte Owner-Rolle (APP_DB_OWNER_USER, Standard
# fieldvibe_owner): ihr gehoeren Tabellen, Funktionen und Typen, Migrationen laufen
# als sie; die App-Rolle behaelt nur DML-Rechte und kann RLS nicht per ALTER TABLE
# abschalten. Zugangsdaten landen in .env.migration (NICHT in .env, die als env_file
# in Backend/Worker geladen wird, immer chmod 600); in .env stehen nur die Marker
# DB_GETRENNTER_OWNER=1 und FIELDVIBE_DB_BESITZ_VERBOTEN=1. Migrationen laufen
# danach ausschliesslich ueber scripts/migrieren.sh bzw. deploy.sh.
#
# Idempotent: ein zweiter Lauf erkennt Rollen und Passwoerter und laeuft durch.
#
# Optionen:
#   --dry-run       nur anzeigen, was passieren wuerde, nichts aendern
#   --ohne-backup   Datenbank-Sicherung (scripts/backup.sh) ueberspringen
#   --nur-rolle     nur Rollen + .env (kein Backup, kein Neustart, keine
#                   Migrationen) -- fuer scripts/deploy.sh, das den Stack
#                   danach selbst startet
#   --compose "..." Compose-Aufruf statt Erkennung ueber DEPLOY_MODE in .env
#   --ohne-getrennten-owner
#                   Owner-Rolle abschalten (wie DB_GETRENNTER_OWNER=0 in .env): das
#                   Eigentum geht zurueck an die App-Rolle, .env.migration wird nach
#                   .env.migration.deaktiviert-<Zeitstempel> verschoben. Die App-Rolle
#                   koennte RLS dann selbst abschalten -- nur bewusst verwenden.
#   --getrennter-owner
#                   erzwingt den Owner-Modus (Standard), auch bei DB_GETRENNTER_OWNER=0
#   --nur-besitz [--datenbank <db>]
#                   nur Eigentum/Rechte in einer (wiederhergestellten) Datenbank
#                   herstellen -- fuer restore.sh und backup-pruefen.sh. Keine
#                   Passwoerter, keine .env-Aenderung, kein Backup, kein Neustart; die
#                   Rollen muessen bereits existieren.

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

log()  { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mWarnung:\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31mFehler:\033[0m %s\n' "$*" >&2; exit 1; }

DRY_RUN=0
OHNE_BACKUP=0
NUR_ROLLE=0
NUR_BESITZ=0
BESITZ_DB=""
FLAG_OWNER_AN=0
FLAG_OWNER_AUS=0
COMPOSE_ARG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)     DRY_RUN=1 ;;
    --ohne-backup) OHNE_BACKUP=1 ;;
    --nur-rolle)   NUR_ROLLE=1 ;;
    --getrennter-owner) FLAG_OWNER_AN=1 ;;
    --ohne-getrennten-owner) FLAG_OWNER_AUS=1 ;;
    --nur-besitz)  NUR_BESITZ=1 ;;
    --datenbank)   shift; [[ $# -gt 0 ]] || err "--datenbank braucht ein Argument."; BESITZ_DB="$1" ;;
    --compose)     shift; [[ $# -gt 0 ]] || err "--compose braucht ein Argument."; COMPOSE_ARG="$1" ;;
    -h|--help)     sed -n '3,51p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)             err "Unbekannte Option: $1 (siehe --help)" ;;
  esac
  shift
done

[[ $FLAG_OWNER_AN -eq 0 || $FLAG_OWNER_AUS -eq 0 ]] \
  || err "--getrennter-owner und --ohne-getrennten-owner schliessen sich aus."
[[ -z "$BESITZ_DB" || $NUR_BESITZ -eq 1 ]] || err "--datenbank gilt nur zusammen mit --nur-besitz."
[[ $NUR_BESITZ -eq 0 || ( $NUR_ROLLE -eq 0 && $DRY_RUN -eq 0 ) ]] || err "--nur-besitz laesst sich nicht mit --nur-rolle oder --dry-run kombinieren."

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
SYS_USER="$(get_env APP_DB_SYSTEM_USER)"; SYS_USER="${SYS_USER:-fieldvibe_system}"
SYS_PW="$(get_env APP_DB_SYSTEM_PASSWORD)"

# Der Name landet in SQL-Bezeichnern und der Connection-URL -- nur harmlose
# Zeichen zulassen.
[[ "$APP_USER" =~ ^[a-z_][a-z0-9_]{0,62}$ ]] \
  || err "APP_DB_USER='$APP_USER' ist ungueltig (erlaubt: Kleinbuchstaben, Ziffern, Unterstrich)."
[[ "$APP_USER" != "$PG_USER" ]] \
  || err "APP_DB_USER darf nicht mit POSTGRES_USER ($PG_USER) identisch sein."
[[ "$SYS_USER" =~ ^[a-z_][a-z0-9_]{0,62}$ ]] \
  || err "APP_DB_SYSTEM_USER='$SYS_USER' ist ungueltig (erlaubt: Kleinbuchstaben, Ziffern, Unterstrich)."
[[ "$SYS_USER" != "$PG_USER" && "$SYS_USER" != "$APP_USER" ]] \
  || err "APP_DB_SYSTEM_USER muss sich von APP_DB_USER und POSTGRES_USER unterscheiden."
[[ "$PG_DB" =~ ^[A-Za-z0-9_]+$ ]] || err "POSTGRES_DB='$PG_DB' enthaelt unerwartete Zeichen."

# --- Modus: getrennte Owner-Rolle (Standard) ---------------------------------
# Eine Quelle: DB_GETRENNTER_OWNER in .env (1 = eingerichtet, 0 = bewusst aus, leer =
# noch nicht umgestellt) und die Optionen. Standard ist AN.
MIGR_DATEI=".env.migration"
get_migr() { grep "^${1}=" "$MIGR_DATEI" 2>/dev/null | head -n1 | cut -d= -f2- || true; }
MARKER="$(get_env DB_GETRENNTER_OWNER)"
if [[ $FLAG_OWNER_AUS -eq 1 ]]; then OWNER_AN=0
elif [[ $FLAG_OWNER_AN -eq 1 ]]; then OWNER_AN=1
elif [[ "$MARKER" == "0" ]]; then OWNER_AN=0
else OWNER_AN=1
fi

OWNER_USER=""; OWNER_PW=""; OWNER_NEU=0; ABSCHALTEN=0
if [[ $OWNER_AN -eq 1 ]]; then
  OWNER_USER="$(get_migr APP_DB_OWNER_USER)"; OWNER_USER="${OWNER_USER:-fieldvibe_owner}"
  [[ "$OWNER_USER" =~ ^[a-z_][a-z0-9_]{0,62}$ ]] || err "APP_DB_OWNER_USER='$OWNER_USER' ist ungueltig."
  [[ "$OWNER_USER" != "$APP_USER" && "$OWNER_USER" != "$PG_USER" ]] \
    || err "APP_DB_OWNER_USER muss sich von APP_DB_USER und POSTGRES_USER unterscheiden."
  [[ "$OWNER_USER" != "$SYS_USER" ]] || err "APP_DB_OWNER_USER muss sich von APP_DB_SYSTEM_USER unterscheiden."
  if [[ $NUR_BESITZ -eq 0 ]]; then
    OWNER_PW="$(get_migr APP_DB_OWNER_PASSWORD)"
    if [[ ! -f "$MIGR_DATEI" || -z "$OWNER_PW" ]]; then
      OWNER_PW="$(openssl rand -hex 24)"
      OWNER_NEU=1
    fi
    [[ "$OWNER_PW" =~ ^[A-Za-z0-9._~-]+$ ]] || err "APP_DB_OWNER_PASSWORD in ${MIGR_DATEI} enthaelt unerwartete Zeichen -- Zeile loeschen."
  elif [[ "$MARKER" == "1" && ! -f "$MIGR_DATEI" ]]; then
    err "DB_GETRENNTER_OWNER=1 steht in .env, aber ${MIGR_DATEI} fehlt -- der Owner-Zugang ist nicht mehr vorhanden. Neu anlegen (neues Passwort): ./scripts/app_rolle_einrichten.sh --nur-rolle (oder scripts/deploy.sh)."
  fi
else
  # Abschalten auf einer umgestellten Installation: Eigentum zurueck an die App-Rolle.
  if [[ -f "$MIGR_DATEI" || "$MARKER" == "1" || "$(get_env FIELDVIBE_DB_BESITZ_VERBOTEN)" == "1" ]]; then ABSCHALTEN=1; fi
fi

if [[ $NUR_BESITZ -eq 1 ]]; then
  BESITZ_DB="${BESITZ_DB:-$PG_DB}"
  [[ "$BESITZ_DB" =~ ^[A-Za-z0-9_]+$ ]] || err "Datenbankname '$BESITZ_DB' enthaelt unerwartete Zeichen."
  command -v docker &>/dev/null || err "docker nicht gefunden."
  log "Stelle Eigentum und Rechte in der Datenbank ${BESITZ_DB} her (Eigentuemer: ${OWNER_USER:-$APP_USER})..."
  if ! {
    printf '\\set app_rolle %s\n\\set db_name %s\n\\set system_rolle %s\n\\set nur_besitz 1\n' "$APP_USER" "$BESITZ_DB" "$SYS_USER"
    [[ -z "$OWNER_USER" ]] || printf '\\set owner_rolle %s\n' "$OWNER_USER"
    cat scripts/sql/app_rolle_einrichten.sql
  } | "${COMPOSE[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$BESITZ_DB" -f - 2>&1 \
    | cat >&2; then
    err "Eigentum/Rechte in ${BESITZ_DB} konnten nicht hergestellt werden, siehe Ausgabe oben."
  fi
  exit 0
fi

PW_NEU=0
if [[ -z "$APP_PW" || "$APP_PW" == *changeme* ]]; then
  # Nur Hex: kein URL-Encoding noetig, wenn das Passwort in DATABASE_URL steht.
  APP_PW="$(openssl rand -hex 24)"
  PW_NEU=1
fi
[[ "$APP_PW" =~ ^[A-Za-z0-9._~-]+$ ]] \
  || err "APP_DB_PASSWORD in .env enthaelt Zeichen, die in der DATABASE_URL kodiert werden muessten -- Zeile loeschen, dann erzeugt das Skript ein neues."

SYS_PW_NEU=0
if [[ -z "$SYS_PW" || "$SYS_PW" == *changeme* ]]; then
  SYS_PW="$(openssl rand -hex 24)"
  SYS_PW_NEU=1
fi
[[ "$SYS_PW" =~ ^[A-Za-z0-9._~-]+$ ]] \
  || err "APP_DB_SYSTEM_PASSWORD in .env enthaelt Zeichen, die in der DATABASE_URL kodiert werden muessten -- Zeile loeschen, dann erzeugt das Skript ein neues."

STAMP="$(date +%Y%m%d-%H%M%S)"
ENV_BACKUP=".env.vor-app-rolle.${STAMP}"
MIGR_ARCHIV=".env.migration.deaktiviert-${STAMP}"
URL_ASYNC="postgresql+asyncpg://${APP_USER}:${APP_PW}@postgres:5432/${PG_DB}"
URL_SYNC="postgresql+psycopg2://${APP_USER}:${APP_PW}@postgres:5432/${PG_DB}"
URL_SYSTEM="postgresql+asyncpg://${SYS_USER}:${SYS_PW}@postgres:5432/${PG_DB}"
MARKER_SOLL=$OWNER_AN

if [[ $DRY_RUN -eq 1 ]]; then
  log "Trockenlauf -- es wird nichts veraendert."
  cat <<PLAN
  Compose:          ${COMPOSE[*]}
  Admin-User/DB:    ${PG_USER} / ${PG_DB}
  App-Rolle:        ${APP_USER} ($([[ $PW_NEU -eq 1 ]] && echo "Passwort wird neu erzeugt" || echo "Passwort aus .env"))
  System-Rolle:     ${SYS_USER} ($([[ $SYS_PW_NEU -eq 1 ]] && echo "Passwort wird neu erzeugt" || echo "Passwort aus .env"))
PLAN
  if [[ -n "$OWNER_USER" ]]; then
    echo "  Owner-Rolle:      ${OWNER_USER} ($([[ $OWNER_NEU -eq 1 ]] && echo "Zugang wird neu erzeugt" || echo "Zugang aus ${MIGR_DATEI}"))"
  else
    echo "  Owner-Rolle:      aus (App-Rolle besitzt die Tabellen)"
  fi
  echo
  echo "  Geplante Schritte:"
  [[ $NUR_ROLLE -eq 0 && $OHNE_BACKUP -eq 0 ]] && echo "   1. Sicherung: scripts/backup.sh"
  echo "   2. .env kopieren nach ${ENV_BACKUP}"
  echo "   3. Postgres starten/abwarten: ${COMPOSE[*]} up -d postgres"
  echo "   4. scripts/sql/app_rolle_einrichten.sql als ${PG_USER} in ${PG_DB} ausfuehren (App-Rolle und System-Rolle ${SYS_USER} anlegen, Eigentum uebertragen)"
  echo "      System-Rolle ${SYS_USER}: LOGIN NOSUPERUSER BYPASSRLS NOCREATEDB NOCREATEROLE, besitzt keine Tabellen, nur DML-Rechte"
  [[ -n "$OWNER_USER" ]] && echo "      mit getrennter Owner-Rolle ${OWNER_USER}: Tabellen gehoeren ihr, ${APP_USER} bekommt nur DML-Rechte; Zugang in ${MIGR_DATEI}"
  [[ $ABSCHALTEN -eq 1 ]] && echo "      Abschalten: Eigentum geht zurueck an ${APP_USER}, ${MIGR_DATEI} wird nach ${MIGR_ARCHIV} verschoben, FIELDVIBE_DB_BESITZ_VERBOTEN=0"
  echo "   5. .env: APP_DB_USER/APP_DB_PASSWORD, DATABASE_URL, DATABASE_URL_SYNC setzen; APP_DB_SYSTEM_USER/APP_DB_SYSTEM_PASSWORD, DATABASE_URL_SYSTEM setzen; FIELDVIBE_ERLAUBE_RLS_BYPASS_ROLLE entfernen"
  if [[ $NUR_ROLLE -eq 0 ]]; then
    echo "   6. backend und worker neu erzeugen, bis zu 90 s auf 'healthy' warten"
    echo "   7. scripts/migrieren.sh (Migrationen als ${OWNER_USER:-$APP_USER})"
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
BESITZ_AKTUELL="$(get_env FIELDVIBE_DB_BESITZ_VERBOTEN)"
if [[ $NUR_ROLLE -eq 0 || "$(get_env DATABASE_URL)" != "$URL_ASYNC" \
      || "$(get_env DATABASE_URL_SYNC)" != "$URL_SYNC" \
      || "$(get_env DATABASE_URL_SYSTEM)" != "$URL_SYSTEM" \
      || -n "$(get_env FIELDVIBE_ERLAUBE_RLS_BYPASS_ROLLE)" \
      || "$MARKER" != "$MARKER_SOLL" \
      || ( $OWNER_AN -eq 1 && "$BESITZ_AKTUELL" != "1" ) \
      || ( $OWNER_AN -eq 0 && -n "$BESITZ_AKTUELL" && "$BESITZ_AKTUELL" != "0" ) ]]; then
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
if [[ $OWNER_NEU -eq 1 && "$MARKER" == "1" ]]; then
  warn "Owner-Zugang fehlte (${MIGR_DATEI} nicht vorhanden), neu angelegt: neues Passwort fuer ${OWNER_USER}, Zugang in ${MIGR_DATEI}."
fi
sql_ausfuehren() {
  {
    printf '\\set app_rolle %s\n\\set app_passwort %s\n\\set db_name %s\n' "$APP_USER" "$APP_PW" "$PG_DB"
    printf '\\set system_rolle %s\n\\set system_passwort %s\n' "$SYS_USER" "$SYS_PW"
    if [[ -n "$OWNER_USER" ]]; then
      printf '\\set owner_rolle %s\n\\set owner_passwort %s\n' "$OWNER_USER" "$OWNER_PW"
    fi
    cat scripts/sql/app_rolle_einrichten.sql
  } | "${COMPOSE[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DB" -f - 2>&1 \
    | sed "s/${APP_PW}/***/g; s/${OWNER_PW:-__kein_owner__}/***/g; s/${SYS_PW}/***/g"
}
log "Richte Rollen ${APP_USER}${OWNER_USER:+, ${OWNER_USER}} und ${SYS_USER} ein und uebertrage das Eigentum an den Tabellen..."
# Die erste Umstellung nimmt ACCESS-EXCLUSIVE-Locks auf alle Tabellen, waehrend das alte
# Backend noch laeuft; ein Deadlock bricht die Transaktion sauber ab -- dann hilft ein Wiederholen.
sql_ok=0
for versuch in 1 2 3; do
  if sql_ausfuehren; then sql_ok=1; break; fi
  [[ $versuch -lt 3 ]] || break
  warn "SQL-Schritt fehlgeschlagen (Versuch ${versuch}/3) -- neuer Versuch in ${APP_ROLLE_SQL_PAUSE:-5} s."
  sleep "${APP_ROLLE_SQL_PAUSE:-5}"
done
[[ $sql_ok -eq 1 ]] || err ".env unveraendert (Sicherung: ${ENV_BACKUP}). SQL-Schritt auch im dritten Versuch fehlgeschlagen, siehe Ausgabe oben."

# --- (d) .env umstellen ------------------------------------------------------
log "Stelle .env auf die App-Rolle um..."
set_env APP_DB_USER "$APP_USER"
set_env APP_DB_PASSWORD "$APP_PW"
set_env DATABASE_URL "$URL_ASYNC"
set_env DATABASE_URL_SYNC "$URL_SYNC"
set_env APP_DB_SYSTEM_USER "$SYS_USER"
set_env APP_DB_SYSTEM_PASSWORD "$SYS_PW"
set_env DATABASE_URL_SYSTEM "$URL_SYSTEM"
del_env FIELDVIBE_ERLAUBE_RLS_BYPASS_ROLLE
if [[ -n "$OWNER_USER" ]]; then
  # Owner-Zugang in eigene Datei: .env wird als env_file in Backend und Worker
  # geladen, der Owner-Zugang soll dort nie ankommen. Nur scripts/migrieren.sh liest ihn.
  if [[ $OWNER_NEU -eq 1 ]]; then
    ( umask 077
      printf 'APP_DB_OWNER_USER=%s\nAPP_DB_OWNER_PASSWORD=%s\nDATABASE_URL_SYNC=postgresql+psycopg2://%s:%s@postgres:5432/%s\n' \
        "$OWNER_USER" "$OWNER_PW" "$OWNER_USER" "$OWNER_PW" "$PG_DB" >"$MIGR_DATEI" )
  fi
  chmod 600 "$MIGR_DATEI"
  set_env DB_GETRENNTER_OWNER 1
  set_env FIELDVIBE_DB_BESITZ_VERBOTEN 1
  log "Owner-Rolle ${OWNER_USER} eingerichtet, Zugang in ${MIGR_DATEI}; Migrationen laufen kuenftig ueber scripts/migrieren.sh."
else
  [[ "$MARKER" == "0" ]] || set_env DB_GETRENNTER_OWNER 0
  [[ -z "$BESITZ_AKTUELL" ]] || set_env FIELDVIBE_DB_BESITZ_VERBOTEN 0
  if [[ $ABSCHALTEN -eq 1 ]]; then
    if [[ -f "$MIGR_DATEI" ]]; then
      mv -- "$MIGR_DATEI" "$MIGR_ARCHIV"
      chmod 600 "$MIGR_ARCHIV"
    fi
    warn "Getrennte Owner-Rolle ABGESCHALTET: ${APP_USER} besitzt die Tabellen wieder und koennte Row-Level-Security per ALTER TABLE selbst abschalten (ein SQL-Injection-Treffer reichte). Owner-Zugang archiviert in ${MIGR_ARCHIV}. Wieder einschalten: DB_GETRENNTER_OWNER-Zeile aus .env entfernen und scripts/app_rolle_einrichten.sh --nur-rolle (oder scripts/deploy.sh)."
  else
    warn "Getrennte Owner-Rolle ist abgeschaltet (DB_GETRENNTER_OWNER=0): ${APP_USER} besitzt die Tabellen und koennte Row-Level-Security selbst abschalten."
  fi
fi
chmod 600 .env

if [[ $NUR_ROLLE -eq 1 ]]; then
  log "App-Rolle ${APP_USER} und System-Rolle ${SYS_USER} eingerichtet, .env umgestellt (Stack-Start folgt durch den Aufrufer)."
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

log "Wende Migrationen als ${OWNER_USER:-$APP_USER} an (scripts/migrieren.sh)..."
./scripts/migrieren.sh --compose "${COMPOSE[*]}" || rollback

log "Fertig. Backend und Worker laufen als ${APP_USER} (System-Zugriffe als ${SYS_USER}); Row-Level-Security ist wirksam."
echo "  Sicherungen: ${ENV_BACKUP} (die Datei enthaelt das alte Passwort -- nach Kontrolle loeschen)."
