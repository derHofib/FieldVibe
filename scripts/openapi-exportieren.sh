#!/usr/bin/env bash
set -euo pipefail

# Erzeugt das OpenAPI-Schema aus der FastAPI-App und legt es unter
# docs/api/openapi.json ab. Der Import der App braucht weder Datenbank noch
# Netz; ENVIRONMENT=development ist nur noetig, damit der fail-closed
# Konfigurationscheck (siehe docs/DEPLOYMENT.md, 6c) nicht auf fehlende
# Produktionsgeheimnisse anspricht.
#
# Usage: ./scripts/openapi-exportieren.sh [--pruefen]
#   ohne Argument  schreibt docs/api/openapi.json neu
#   --pruefen      schreibt nichts, beendet sich mit Fehler, wenn die
#                  eingecheckte Datei nicht zum Code passt (CI)
#
# PYTHON=/pfad/zu/python waehlt den Interpreter (Standard: python3). Die
# Ausgabe haengt von den installierten Paketversionen ab -- gleiche Versionen
# wie in backend/requirements.lock verwenden (pip install --require-hashes -r
# requirements.lock), sonst gibt es Scheindifferenzen.

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZIEL="$REPO_DIR/docs/api/openapi.json"
PYTHON="${PYTHON:-python3}"
PRUEFEN=0
case "${1:-}" in
  "") ;;
  --pruefen) PRUEFEN=1 ;;
  *) echo "Unbekanntes Argument: $1" >&2; exit 2 ;;
esac

erzeugen() {
  (
    cd "$REPO_DIR/backend"
    ENVIRONMENT=development "$PYTHON" -c '
import json, sys
from app.main import app

# Feste Schluesselreihenfolge und Einrueckung, damit Diffs im Repo lesbar bleiben.
json.dump(app.openapi(), sys.stdout, indent=2, ensure_ascii=False, sort_keys=True)
sys.stdout.write("\n")
'
  )
}

mkdir -p "$(dirname "$ZIEL")"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
erzeugen > "$TMP"

if [[ $PRUEFEN -eq 1 ]]; then
  if ! diff -q "$TMP" "$ZIEL" > /dev/null 2>&1; then
    echo "docs/api/openapi.json ist veraltet. Neu erzeugen mit:" >&2
    echo "  ./scripts/openapi-exportieren.sh" >&2
    echo "und die Datei mit committen. Abweichung (gekuerzt):" >&2
    diff "$ZIEL" "$TMP" 2>&1 | head -n 40 >&2 || true
    exit 1
  fi
  echo "docs/api/openapi.json ist aktuell."
else
  # install statt cp: mktemp legt die Datei mit 0600 an, im Repo soll sie 0644 sein.
  install -m 644 "$TMP" "$ZIEL"
  echo "Geschrieben: $ZIEL"
fi
