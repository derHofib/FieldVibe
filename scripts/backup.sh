#!/usr/bin/env bash
set -euo pipefail

# Taegliches Backup von Postgres (pg_dump) und MinIO (Objektdaten).
# Gedacht fuer host-seitiges Cron, nicht als eigener Compose-Service --
# ein Backup-Container haette keinen sinnvollen Dauerbetrieb-Lebenszyklus,
# ein einfacher Cron-Aufruf reicht (siehe docs/DEPLOYMENT.md).
#
# Beispiel-Crontab-Eintrag (taeglich 02:30):
#   30 2 * * * /pfad/zu/SocialCRM/scripts/backup.sh >> /var/log/fieldvibe-backup.log 2>&1

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

# Personenbezogene Daten (Kundendaten, Rechnungen, Fotos) liegen unverschluesselt
# in diesen Dumps -- ohne GPG-Verschluesselung ist ein gestohlenes Backup ein
# vollstaendiger Datenabfluss (Art. 32 DSGVO: TOM). BACKUP_GPG_RECIPIENT
# ist die Key-ID/E-Mail-Adresse eines OFFLINE aufbewahrten oeffentlichen
# GPG-Schluessels -- der private Schluessel gehoert NICHT auf diesen Server,
# sonst schuetzt die Verschluesselung nichts, wenn genau dieser Server
# kompromittiert wird. Erzeugen: gpg --full-generate-key (auf einem anderen
# Rechner), dann den public key mit "gpg --export --armor <ID>" hierher
# kopieren und mit "gpg --import" einspielen.
if [[ -n "${BACKUP_GPG_RECIPIENT:-}" ]]; then
  echo "[$(date -Iseconds)] Verschluessele Backups fuer $BACKUP_GPG_RECIPIENT..."
  for f in "$BACKUP_DIR/db-$STAMP.sql.gz" "$BACKUP_DIR/minio-$STAMP.tar.gz"; do
    gpg --batch --yes --trust-model always --encrypt \
      --recipient "$BACKUP_GPG_RECIPIENT" --output "$f.gpg" "$f"
    rm -f "$f"
  done
else
  echo "[$(date -Iseconds)] WARNUNG: BACKUP_GPG_RECIPIENT nicht gesetzt -- Backups liegen unverschluesselt auf der Platte." >&2
fi

echo "[$(date -Iseconds)] Alte Backups aufräumen (älter als $RETENTION_DAYS Tage)..."
find "$BACKUP_DIR" -name 'db-*.sql.gz*' -mtime "+$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -name 'minio-*.tar.gz*' -mtime "+$RETENTION_DAYS" -delete

# Ein Backup, das nur auf demselben Server liegt, ueberlebt einen
# Festplattendefekt oder eine kompromittierte Maschine nicht.
# BACKUP_OFFSITE_REMOTE ist ein rclone-Remote-Pfad (z.B. "hetzner-storagebox:fieldvibe-backups"),
# vorher einmalig mit "rclone config" auf diesem Server eingerichtet.
if [[ -n "${BACKUP_OFFSITE_REMOTE:-}" ]]; then
  echo "[$(date -Iseconds)] Kopiere Backups nach $BACKUP_OFFSITE_REMOTE..."
  rclone copy "$BACKUP_DIR" "$BACKUP_OFFSITE_REMOTE"
else
  echo "[$(date -Iseconds)] WARNUNG: BACKUP_OFFSITE_REMOTE nicht gesetzt -- Backups liegen nur auf diesem Server." >&2
fi

echo "[$(date -Iseconds)] Fertig: db-$STAMP.sql.gz*, minio-$STAMP.tar.gz* in $BACKUP_DIR"
