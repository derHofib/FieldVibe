#!/usr/bin/env bash
set -euo pipefail

# Fuehrt `alembic upgrade head` im Backend-Container aus. Existiert .env.migration
# (getrennte Owner-Rolle, siehe scripts/app_rolle_einrichten.sh --getrennter-owner),
# laufen die Migrationen mit deren Datenbank-Zugang statt mit dem der App-Rolle:
# nur so duerfen sie Tabellen anlegen/aendern, waehrend die App-Rolle keine RLS-
# Einstellungen aendern kann. Der Owner-Zugang geht per -e aus der Umgebung des
# Aufrufs an den Einmal-Container (nicht in .env, nicht als Argument).
#
# Usage: ./scripts/migrieren.sh [--compose "docker compose -f ... -f ..."] [alembic-Argumente]

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

COMPOSE=(docker compose)
if [[ "${1:-}" == "--compose" ]]; then
  [[ $# -ge 2 ]] || { echo "--compose braucht ein Argument." >&2; exit 1; }
  read -ra COMPOSE <<< "$2"
  shift 2
fi
ALEMBIC_ARGS=("$@")
[[ ${#ALEMBIC_ARGS[@]} -gt 0 ]] || ALEMBIC_ARGS=(upgrade head)

if [[ -f .env.migration ]]; then
  url="$(grep '^DATABASE_URL_SYNC=' .env.migration | head -n1 | cut -d= -f2- || true)"
  [[ -n "$url" ]] || { echo "DATABASE_URL_SYNC fehlt in .env.migration." >&2; exit 1; }
  DATABASE_URL_SYNC="$url" "${COMPOSE[@]}" run --rm -e DATABASE_URL_SYNC backend alembic "${ALEMBIC_ARGS[@]}"
else
  "${COMPOSE[@]}" run --rm backend alembic "${ALEMBIC_ARGS[@]}"
fi
