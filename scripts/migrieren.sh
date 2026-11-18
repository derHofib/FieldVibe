#!/usr/bin/env bash
set -euo pipefail

# Fuehrt `alembic upgrade head` (bzw. die uebergebenen alembic-Argumente) im Backend-
# Container aus -- der einzige vorgesehene Weg, Migrationen auf dem Server anzuwenden.
# Mit eingerichteter getrennter Owner-Rolle (Standard, siehe scripts/app_rolle_einrichten.sh)
# laufen die Migrationen mit dem Datenbank-Zugang aus .env.migration statt mit dem der
# App-Rolle: nur so duerfen sie Tabellen anlegen/aendern, waehrend die App-Rolle keine
# RLS-Einstellungen aendern kann. Der Owner-Zugang geht per -e aus der Umgebung des
# Aufrufs an den Einmal-Container (nicht in .env, nicht als Argument).
#
# Steht DB_GETRENNTER_OWNER=1 in .env, fehlt aber .env.migration, bricht das Skript ab
# (kein stiller Rueckfall auf die App-Rolle, der an fehlendem Eigentum scheitern wuerde).
#
# Usage: ./scripts/migrieren.sh [--compose "docker compose -f ... -f ..."] [alembic-Argumente]

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

log()  { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mWarnung:\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31mFehler:\033[0m %s\n' "$*" >&2; exit 1; }

COMPOSE=(docker compose)
if [[ "${1:-}" == "--compose" ]]; then
  [[ $# -ge 2 ]] || err "--compose braucht ein Argument."
  read -ra COMPOSE <<< "$2"
  shift 2
fi
ALEMBIC_ARGS=("$@")
[[ ${#ALEMBIC_ARGS[@]} -gt 0 ]] || ALEMBIC_ARGS=(upgrade head)

get_env() { grep "^${1}=" .env 2>/dev/null | head -n1 | cut -d= -f2- || true; }
# Nur der Benutzername aus einer Connection-URL, nie das Passwort.
url_rolle() { sed -E 's#^[^:]+://([^:@/]+).*#\1#' <<<"$1"; }

marker="$(get_env DB_GETRENNTER_OWNER)"
if [[ ! -f .env.migration && "$marker" == "1" ]]; then
  err "DB_GETRENNTER_OWNER=1 steht in .env, aber .env.migration fehlt -- ohne den Owner-Zugang laesst sich nicht migrieren (die App-Rolle besitzt keine Tabellen). Neu anlegen (neues Passwort): ./scripts/app_rolle_einrichten.sh --nur-rolle (legt ihn neu an, deploy.sh ebenso)."
fi

if [[ -f .env.migration ]]; then
  if [[ "$(stat -c %a .env.migration)" != "600" ]]; then
    chmod 600 .env.migration
    warn ".env.migration hatte zu weite Zugriffsrechte -- auf 600 gesetzt."
  fi
  [[ "$marker" != "0" ]] || warn "DB_GETRENNTER_OWNER=0 steht in .env, .env.migration existiert aber noch -- Abschalten abschliessen mit ./scripts/app_rolle_einrichten.sh --nur-rolle."
  url="$(grep '^DATABASE_URL_SYNC=' .env.migration | head -n1 | cut -d= -f2- || true)"
  [[ -n "$url" ]] || err "DATABASE_URL_SYNC fehlt in .env.migration."
  log "Migriere als Owner-Rolle $(url_rolle "$url") (Zugang aus .env.migration): alembic ${ALEMBIC_ARGS[*]}"
  DATABASE_URL_SYNC="$url" "${COMPOSE[@]}" run --rm -e DATABASE_URL_SYNC backend alembic "${ALEMBIC_ARGS[@]}"
else
  app_url="$(get_env DATABASE_URL_SYNC)"
  app_rolle="aus der .env des Containers"
  [[ -z "$app_url" ]] || app_rolle="$(url_rolle "$app_url")"
  log "Migriere als App-Rolle ${app_rolle} -- keine getrennte Owner-Rolle eingerichtet: alembic ${ALEMBIC_ARGS[*]}"
  "${COMPOSE[@]}" run --rm backend alembic "${ALEMBIC_ARGS[@]}"
fi
