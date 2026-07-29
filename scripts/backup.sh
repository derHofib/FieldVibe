#!/usr/bin/env bash
set -euo pipefail

# Taegliches Backup von Postgres (pg_dump) und MinIO (Objektdaten).
# Gedacht fuer host-seitiges Cron, nicht als eigener Compose-Service --
# ein Backup-Container haette keinen sinnvollen Dauerbetrieb-Lebenszyklus,
# ein einfacher Cron-Aufruf reicht (siehe docs/DEPLOYMENT.md).
#
# Beispiel-Crontab-Eintrag (taeglich 02:30):
#   30 2 * * * /pfad/zu/SocialCRM/scripts/backup.sh >> /var/log/socialcrm-backup.log 2>&1

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

set -a
source .env
set +a

BACKUP_DIR="${BACKUP_DIR:-$REPO_DIR/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BACKUP_DIR"

echo "[$(date -Iseconds)] Postgres-Dump..."
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip > "$BACKUP_DIR/db-$STAMP.sql.gz"

echo "[$(date -Iseconds)] MinIO-Objektdaten..."
# --volumes-from statt "exec minio tar ...": das MinIO-Image bringt kein
# garantiertes tar/sh mit, ein separater Alpine-Container mit geteiltem
# Volume-Mount ist unabhaengig vom Inhalt des MinIO-Images.
docker run --rm --volumes-from "$(docker compose ps -q minio)" alpine \
  tar czf - -C /data . > "$BACKUP_DIR/minio-$STAMP.tar.gz"

echo "[$(date -Iseconds)] Alte Backups aufräumen (älter als $RETENTION_DAYS Tage)..."
find "$BACKUP_DIR" -name 'db-*.sql.gz' -mtime "+$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -name 'minio-*.tar.gz' -mtime "+$RETENTION_DAYS" -delete

echo "[$(date -Iseconds)] Fertig: db-$STAMP.sql.gz, minio-$STAMP.tar.gz in $BACKUP_DIR"
