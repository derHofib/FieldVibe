#!/usr/bin/env bash
set -euo pipefail

# Entfernt eine FieldVibe-Installation vollstaendig: alle Container, die
# Docker-Volumes (Postgres-Datenbank UND MinIO-Fotos!), die gebauten
# Docker-Images und den taeglichen Backup-Cron-Eintrag aus scripts/deploy.sh.
# Macht KEINE Sicherung vorher -- dafuer ist scripts/backup.sh da, nicht
# dieses Skript. Vorhandene Backups in BACKUP_DIR bleiben standardmaessig
# unangetastet.
#
# Usage:
#   ./scripts/uninstall.sh                  Container + Volumes + Images + Cron entfernen
#   ./scripts/uninstall.sh --keep-images     Docker-Images NICHT loeschen
#   ./scripts/uninstall.sh --purge-backups   zusaetzlich auch BACKUP_DIR leeren
#   ./scripts/uninstall.sh --remove-repo     zusaetzlich das ganze Repo-Verzeichnis loeschen
#
# Fragt vor jeder unwiderruflichen Aktion eine woertliche Bestaetigung ab.

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

log()  { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mWarnung:\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31mFehler:\033[0m %s\n' "$*" >&2; exit 1; }

[[ -f "docker-compose.yml" ]] || err "Muss aus dem geklonten SocialCRM-Repo heraus ausgefuehrt werden."

KEEP_IMAGES=0
PURGE_BACKUPS=0
REMOVE_REPO=0
for arg in "$@"; do
  case "$arg" in
    --keep-images) KEEP_IMAGES=1 ;;
    --purge-backups) PURGE_BACKUPS=1 ;;
    --remove-repo) REMOVE_REPO=1 ;;
    -h|--help)
      sed -n '4,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) err "Unbekannte Option: $arg (erlaubt: --keep-images, --purge-backups, --remove-repo, --help)" ;;
  esac
done

# Alle drei Compose-Dateien zusammen: "down" braucht nur die Service-
# Definitionen (z.B. den nur in docker-compose.prod.yml vorhandenen
# "caddy"-Dienst), nicht die Ports/Build-Args, die bei "up" kollidieren
# koennten -- so werden Container aus jeder frueher genutzten Betriebsart
# (Domain/TLS oder Nur-IP) zuverlaessig gefunden, egal welche gerade lief.
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.ip.yml)

BACKUP_DIR_VAL="/opt/fieldvibe-backups"
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
  BACKUP_DIR_VAL="${BACKUP_DIR:-$BACKUP_DIR_VAL}"
fi

echo
echo "Das wird jetzt UNWIDERRUFLICH gelöscht:"
echo "  - Alle laufenden FieldVibe-Container"
echo "  - Die Postgres-Datenbank (alle Mandanten, Kunden, Vorgänge, Rechnungen, ...)"
echo "  - Alle in MinIO gespeicherten Fotos"
[[ $KEEP_IMAGES -eq 0 ]] && echo "  - Die gebauten Docker-Images (Backend/Frontend)"
echo "  - Der tägliche Backup-Cron-Eintrag"
[[ $PURGE_BACKUPS -eq 1 ]] && echo "  - ZUSÄTZLICH: alle vorhandenen Backups in $BACKUP_DIR_VAL"
[[ $REMOVE_REPO -eq 1 ]] && echo "  - ZUSÄTZLICH: das komplette Repo-Verzeichnis $REPO_DIR (inkl. .env mit allen Secrets)"
echo
if [[ $PURGE_BACKUPS -eq 0 ]]; then
  echo "Backups in $BACKUP_DIR_VAL bleiben erhalten (mit --purge-backups auch die löschen)."
fi
echo

read -rp "Zum Bestätigen \"LOESCHEN\" eingeben: " confirm
if [[ "$confirm" != "LOESCHEN" && "$confirm" != "LÖSCHEN" ]]; then
  echo "Abgebrochen, nichts wurde verändert."
  exit 1
fi

log "Stoppe und entferne Container + Volumes..."
DOWN_ARGS=(down --volumes --remove-orphans)
[[ $KEEP_IMAGES -eq 0 ]] && DOWN_ARGS+=(--rmi local)
"${COMPOSE[@]}" "${DOWN_ARGS[@]}" \
  || warn "docker compose down meldete einen Fehler -- prüfe manuell mit 'docker ps -a' und 'docker volume ls'."

log "Entferne Backup-Cron-Eintrag..."
if crontab -l 2>/dev/null | grep -qF "${REPO_DIR}/scripts/backup.sh"; then
  crontab -l 2>/dev/null | grep -vF "${REPO_DIR}/scripts/backup.sh" | crontab -
  echo "Cron-Eintrag entfernt."
else
  echo "Kein passender Cron-Eintrag gefunden, nichts zu tun."
fi

if [[ $PURGE_BACKUPS -eq 1 && -d "$BACKUP_DIR_VAL" ]]; then
  log "Lösche Backups in $BACKUP_DIR_VAL..."
  rm -rf "${BACKUP_DIR_VAL:?}"/*
fi

log "Fertig. Container, Volumes$([[ $KEEP_IMAGES -eq 0 ]] && echo ", Images") und der Backup-Cron sind entfernt."
[[ $PURGE_BACKUPS -eq 0 ]] && echo "Backups liegen weiterhin in $BACKUP_DIR_VAL."

if [[ $REMOVE_REPO -eq 1 ]]; then
  echo
  read -rp "Auch das komplette Verzeichnis $REPO_DIR löschen? Zum Bestätigen erneut \"LOESCHEN\" eingeben: " confirm2
  if [[ "$confirm2" == "LOESCHEN" || "$confirm2" == "LÖSCHEN" ]]; then
    cd /
    rm -rf "${REPO_DIR:?}"
    echo "Verzeichnis $REPO_DIR gelöscht."
  else
    echo "Verzeichnis wurde NICHT gelöscht."
  fi
fi
