#!/usr/bin/env bash
set -euo pipefail

# Stellt eine Datenbank- oder MinIO-Sicherung wieder her.
# ACHTUNG: ueberschreibt den aktuellen Stand vollstaendig.
#
# Usage:
#   scripts/restore.sh db backups/db-20260101-020000.sql.gz
#   scripts/restore.sh minio backups/minio-20260101-020000.tar.gz

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

set -a
source .env
set +a

MODE="${1:?Usage: $0 <db|minio> <backup-datei>}"
FILE="${2:?Usage: $0 <db|minio> <backup-datei>}"

if [[ ! -f "$FILE" ]]; then
  echo "Backup-Datei nicht gefunden: $FILE" >&2
  exit 1
fi

case "$MODE" in
  db)
    echo "Stellt Datenbank '$POSTGRES_DB' aus $FILE wieder her -- überschreibt den aktuellen Inhalt."
    read -rp "Fortfahren? [y/N] " confirm
    [[ "$confirm" == "y" || "$confirm" == "Y" ]] || { echo "Abgebrochen."; exit 1; }
    gunzip -c "$FILE" | docker compose exec -T postgres psql -U "$POSTGRES_USER" "$POSTGRES_DB"
    echo "Datenbank wiederhergestellt."
    ;;
  minio)
    echo "Stellt MinIO-Objektdaten aus $FILE wieder her -- überschreibt vorhandene Objekte."
    read -rp "Fortfahren? [y/N] " confirm
    [[ "$confirm" == "y" || "$confirm" == "Y" ]] || { echo "Abgebrochen."; exit 1; }
    docker compose stop minio
    CONTAINER_ID="$(docker compose ps -a -q minio)"
    ABS_FILE="$(cd "$(dirname "$FILE")" && pwd)/$(basename "$FILE")"
    docker run --rm --volumes-from "$CONTAINER_ID" -v "$ABS_FILE":/backup.tar.gz:ro alpine \
      sh -c "rm -rf /data/* && tar xzf /backup.tar.gz -C /data"
    docker compose start minio
    echo "MinIO-Objektdaten wiederhergestellt."
    ;;
  *)
    echo "Unbekannter Modus: $MODE (erwartet: db|minio)" >&2
    exit 1
    ;;
esac
