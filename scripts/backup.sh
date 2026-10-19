#!/usr/bin/env bash
set -euo pipefail

# Taegliche Sicherung von Postgres (pg_dump -Fc), MinIO-Objektdaten und .env
# als ein Sicherungssatz (gleicher Stamp, Manifest mit SHA-256), optional per GPG
# verschluesselt, danach Upload zu allen Zielen aus BACKUP_TARGETS und Rotation.
# Konfiguration und Zieltypen: .env.example (Block "Backups") und
# docs/DEPLOYMENT.md, Abschnitt "5. Backups".
#
# Gedacht fuer host-seitiges Cron (scripts/deploy.sh richtet es ein), nicht als
# eigener Compose-Service -- ein Backup-Container haette keinen sinnvollen
# Dauerbetrieb-Lebenszyklus.
#
# Exit-Code != 0, sobald irgendein Schritt oder Ziel scheitert; ein
# fehlschlagendes Ziel bricht die uebrigen Ziele aber nicht ab.
#
# Beispiel-Crontab-Eintrag (taeglich 02:30):
#   30 2 * * * /pfad/zu/SocialCRM/scripts/backup.sh >> /var/log/fieldvibe-backup.log 2>&1

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
# shellcheck source=scripts/backup/lib.sh
source "$REPO_DIR/scripts/backup/lib.sh"

backup_env_laden || exit 1
backup_konfig_auswerten || exit 1

# Sicherungsdateien enthalten alle Mandantendaten: nur fuer den ausfuehrenden
# Nutzer lesbar.
umask 077
mkdir -p "$BACKUP_DIR"

command -v flock >/dev/null 2>&1 || { fehler "flock (util-linux) fehlt."; exit 1; }
exec 9>"$BACKUP_DIR/.backup.lock"
if ! flock -n 9; then
  fehler "Es laeuft bereits eine Sicherung (Sperre $BACKUP_DIR/.backup.lock) -- dieser Lauf wird abgebrochen."
  exit 75
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
# Zwei Laeufe in derselben Sekunde (z.B. von Hand direkt nacheinander) wuerden
# sich sonst Dateien teilen -- und ein Fehlschlag raeumte den fremden Satz weg.
while compgen -G "$BACKUP_DIR/*-$STAMP.*" >/dev/null; do
  sleep 1
  STAMP="$(date +%Y%m%d-%H%M%S)"
done
UPLOAD_DIR="$BACKUP_DIR/.upload-$STAMP"
STATUS_DATEI="$BACKUP_DIR/letzter-lauf.json"
START_SEKUNDEN=$SECONDS

GESAMT="ok"
MELDUNGEN=()
LOKAL_STATUS="fehler"
LOKAL_MELDUNG="nicht ausgefuehrt"
ZIEL_NAMEN=()
ZIEL_STATI=()
ZIEL_MELDUNGEN=()
ABGESCHLOSSEN=0

problem() {
  GESAMT="fehler"
  MELDUNGEN+=("$1")
  fehler "$1"
}

# Laeuft auch bei unerwartetem Abbruch (set -e), damit Ping und Status nie
# ausbleiben: ein stilles Scheitern waere der schlimmste Fall.
abschliessen() {
  local rc=$?
  trap - EXIT
  rm -rf -- "$UPLOAD_DIR"
  if (( ABGESCHLOSSEN == 0 )); then
    GESAMT="fehler"
    MELDUNGEN+=("Unerwarteter Abbruch (Exit-Code $rc)")
    fehler "Unerwarteter Abbruch (Exit-Code $rc)."
  fi
  local meldung m verbunden="" dauer=$(( SECONDS - START_SEKUNDEN ))
  if [[ "$GESAMT" == "ok" ]]; then
    meldung="Sicherung $STAMP ok (${#ZIEL_NAMEN[@]} Ziel(e), ${dauer}s)"
  else
    for m in ${MELDUNGEN[@]+"${MELDUNGEN[@]}"}; do verbunden+="${verbunden:+; }$m"; done
    meldung="Sicherung $STAMP FEHLGESCHLAGEN: $verbunden"
  fi
  status_schreiben "$STATUS_DATEI" "$GESAMT" "$STAMP" "$dauer" "$meldung" \
    || warn "letzter-lauf.json konnte nicht geschrieben werden."
  if [[ "$GESAMT" == "ok" ]]; then
    log "Fertig: $meldung"
    ping_senden "${BACKUP_PING_URL:-}" ""
    benachrichtigen ok "$meldung" "$STAMP"
    exit 0
  fi
  fehler "$meldung"
  ping_senden "${BACKUP_PING_URL:-}" "/fail"
  benachrichtigen fehler "$meldung" "$STAMP"
  exit 1
}
trap abschliessen EXIT

# $1 = Eintrag "<typ>:<ziel>". Haengt Name/Status/Meldung an die ZIEL_*-Arrays.
ziel_verarbeiten() {
  local eintrag="$1" typ pfad meldung=""
  ziel_zerlegen "$eintrag"
  typ="$ZIEL_TYP"
  pfad="$ZIEL_PFAD"
  ZIEL_NAMEN+=("$eintrag")

  if ! ziel_typ_bekannt "$typ"; then
    meldung="Unbekannter Zieltyp '$typ' (mitgeliefert: local, rclone, befehl)"
    ZIEL_STATI+=("fehler"); ZIEL_MELDUNGEN+=("$meldung")
    problem "Ziel $eintrag: $meldung"
    return 0
  fi
  if ziel_ist_remote "$typ" && [[ -z "${BACKUP_GPG_RECIPIENT:-}" && "${BACKUP_ERLAUBE_UNVERSCHLUESSELT_REMOTE:-}" != "1" ]]; then
    meldung="Upload verweigert: unverschluesselte Daten duerfen nicht zu einem Remote-Ziel. BACKUP_GPG_RECIPIENT setzen (siehe docs/DEPLOYMENT.md) oder bewusst BACKUP_ERLAUBE_UNVERSCHLUESSELT_REMOTE=1."
    ZIEL_STATI+=("fehler"); ZIEL_MELDUNGEN+=("$meldung")
    problem "Ziel $eintrag: $meldung"
    return 0
  fi
  if ziel_ist_remote "$typ" && [[ -z "${BACKUP_GPG_RECIPIENT:-}" ]]; then
    warn "Ziel $eintrag: Upload UNVERSCHLUESSELT (BACKUP_ERLAUBE_UNVERSCHLUESSELT_REMOTE=1) -- Kunden- und Rechnungsdaten liegen beim Anbieter im Klartext."
  fi
  if [[ "$typ" == "local" ]]; then
    local real_ziel real_staging
    real_ziel="$(readlink -m -- "$pfad")"
    real_staging="$(readlink -m -- "$BACKUP_DIR")"
    if [[ "$real_ziel" == "$real_staging" ]]; then
      meldung="local-Ziel ist identisch mit BACKUP_DIR (bringt keine zweite Kopie) -- anderes Verzeichnis/Mount angeben."
      ZIEL_STATI+=("fehler"); ZIEL_MELDUNGEN+=("$meldung")
      problem "Ziel $eintrag: $meldung"
      return 0
    fi
  fi

  log "Ziel $eintrag: pruefe..."
  if ! ziel_aufruf "$typ" pruefen "$pfad"; then
    meldung="Pruefung fehlgeschlagen"
    ZIEL_STATI+=("fehler"); ZIEL_MELDUNGEN+=("$meldung")
    problem "Ziel $eintrag: $meldung"
    return 0
  fi
  log "Ziel $eintrag: lade Satz $STAMP hoch..."
  if ! ziel_aufruf "$typ" hochladen "$pfad" "$UPLOAD_DIR" "$STAMP"; then
    meldung="Upload fehlgeschlagen"
    ZIEL_STATI+=("fehler"); ZIEL_MELDUNGEN+=("$meldung")
    problem "Ziel $eintrag: $meldung"
    return 0
  fi
  # Rotation nur nach erfolgreichem Upload: ein Ziel, das gerade nichts
  # annimmt, soll nicht zusaetzlich Altbestand verlieren.
  log "Ziel $eintrag: Rotation (>$BACKUP_RETENTION_DAYS Tage, mindestens $BACKUP_MIN_KEEP Saetze bleiben)..."
  if ! ziel_aufruf "$typ" aufraeumen "$pfad" "$BACKUP_RETENTION_DAYS" "$BACKUP_MIN_KEEP"; then
    meldung="Upload ok, Rotation fehlgeschlagen"
    ZIEL_STATI+=("fehler"); ZIEL_MELDUNGEN+=("$meldung")
    problem "Ziel $eintrag: $meldung"
    return 0
  fi
  ZIEL_STATI+=("ok"); ZIEL_MELDUNGEN+=("Satz $STAMP hochgeladen")
}

ping_senden "${BACKUP_PING_URL:-}" "/start"
log "Sicherung $STAMP startet (Verzeichnis $BACKUP_DIR, ${#BACKUP_ZIELE[@]} Ziel(e))."

HAT_REMOTE=0
for eintrag in ${BACKUP_ZIELE[@]+"${BACKUP_ZIELE[@]}"}; do
  ziel_zerlegen "$eintrag"
  ziel_ist_remote "$ZIEL_TYP" && HAT_REMOTE=1
done
if (( HAT_REMOTE == 0 )); then
  warn "Kein Remote-Ziel konfiguriert (BACKUP_TARGETS) -- die Sicherungen liegen nur auf diesem Server und ueberleben einen Plattendefekt oder Totalverlust nicht."
  if [[ -z "${BACKUP_GPG_RECIPIENT:-}" ]]; then
    warn "BACKUP_GPG_RECIPIENT nicht gesetzt -- die Sicherungen liegen unverschluesselt auf der Platte."
  fi
fi

if satz_erstellen "$STAMP"; then
  LOKAL_STATUS="ok"
  LOKAL_MELDUNG="Satz $STAMP in $BACKUP_DIR"
  upload_verzeichnis_erstellen "$UPLOAD_DIR" || problem "Upload-Verzeichnis konnte nicht angelegt werden"
  # Absicherung, falls satz_erstellen() je geaendert wird: Klartext-Secrets
  # duerfen auf keinen Fall in den Upload-Satz geraten.
  if compgen -G "$UPLOAD_DIR/secrets-*.tar" >/dev/null; then
    problem "Interner Fehler: unverschluesseltes Secrets-Buendel im Upload-Satz -- Uploads abgebrochen"
  else
    for eintrag in ${BACKUP_ZIELE[@]+"${BACKUP_ZIELE[@]}"}; do
      ziel_verarbeiten "$eintrag"
    done
  fi
  log "Lokale Rotation (>$BACKUP_RETENTION_DAYS Tage, mindestens $BACKUP_MIN_KEEP Saetze bleiben)..."
  lokal_aufraeumen "$BACKUP_DIR" "$BACKUP_RETENTION_DAYS" "$BACKUP_MIN_KEEP" \
    || problem "Lokale Rotation fehlgeschlagen"
else
  LOKAL_MELDUNG="Sicherungssatz konnte nicht erstellt werden"
  problem "$LOKAL_MELDUNG (Details siehe oben) -- Uploads und Rotation uebersprungen"
fi

ABGESCHLOSSEN=1
