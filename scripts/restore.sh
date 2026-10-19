#!/usr/bin/env bash
set -euo pipefail

# Stellt Datenbank, MinIO-Objektdaten oder .env aus einem Sicherungssatz wieder
# her. Quelle ist eine lokale Datei ODER ein Backup-Ziel (--von).
#
# Usage:
#   scripts/restore.sh liste [--von <typ:ziel>]
#   scripts/restore.sh db      <datei> | --von <typ:ziel> [--stamp <stamp>]  [--ja] [--ohne-eigentuemer]
#   scripts/restore.sh minio   <datei> | --von <typ:ziel> [--stamp <stamp>]  [--ja]
#   scripts/restore.sh secrets <datei> | --von <typ:ziel> [--stamp <stamp>]
#
# Beispiele:
#   scripts/restore.sh liste
#   scripts/restore.sh db backups/db-20260101-020000.dump.gpg
#   scripts/restore.sh db --von rclone:hetzner:fieldvibe-backups --stamp 20260101-020000
#   scripts/restore.sh secrets --von local:/mnt/nas/fieldvibe          # neuester Satz
#
# Ohne --stamp wird der neueste vollstaendige Satz genommen. "lokal" steht fuer
# das lokale BACKUP_DIR. Vor dem Einspielen wird die Pruefsumme gegen das
# Manifest geprueft; .gpg-Dateien werden entschluesselt (privater Schluessel im
# Schluesselbund noetig). Die Rueckfrage erscheint nur an einem Terminal; ohne
# Terminal (Automatisierung) ist --ja Pflicht.

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
# shellcheck source=scripts/backup/lib.sh
source "$REPO_DIR/scripts/backup/lib.sh"

usage() { sed -n '4,23p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

MODUS="${1:-}"
[[ -n "$MODUS" ]] || { usage >&2; exit 1; }
shift
case "$MODUS" in
  -h | --help) usage; exit 0 ;;
  db | minio | secrets | liste) ;;
  *) fehler "Unbekannter Modus: $MODUS (erwartet: db|minio|secrets|liste)"; usage >&2; exit 1 ;;
esac

DATEI=""
VON=""
STAMP=""
JA=0
OHNE_EIGENTUEMER=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --von)   VON="${2:?--von braucht ein Ziel (<typ:ziel>)}"; shift ;;
    --stamp) STAMP="${2:?--stamp braucht einen Wert}"; shift ;;
    --ja)    JA=1 ;;
    --ohne-eigentuemer) OHNE_EIGENTUEMER=1 ;;
    -h | --help) usage; exit 0 ;;
    -*) fehler "Unbekannte Option: $1"; exit 1 ;;
    *) [[ -z "$DATEI" ]] || { fehler "Mehrere Dateien angegeben."; exit 1; }; DATEI="$1" ;;
  esac
  shift
done

# secrets/liste muessen auch auf einem frischen Server ohne .env laufen -- dort
# soll die .env ja erst wiederhergestellt werden.
if [[ "$MODUS" == "secrets" || "$MODUS" == "liste" ]]; then
  backup_env_laden optional
else
  backup_env_laden || exit 1
fi
backup_konfig_auswerten || exit 1

if [[ "$MODUS" != "liste" ]]; then
  [[ -n "$DATEI" || -n "$VON" ]] || { fehler "Datei oder --von <typ:ziel> angeben."; usage >&2; exit 1; }
  [[ -z "$DATEI" || -z "$VON" ]] || { fehler "Entweder eine Datei ODER --von angeben, nicht beides."; exit 1; }
fi

von_aufloesen() {
  if [[ "$1" == "lokal" ]]; then
    ZIEL_TYP="local"; ZIEL_PFAD="$BACKUP_DIR"
  elif [[ "$1" =~ ^[a-z0-9_-]+:.+$ ]]; then
    ziel_zerlegen "$1"
  else
    fehler "Ungueltiges Ziel '$1' (erwartet: <typ>:<ziel> oder 'lokal')."
    return 1
  fi
}

# --- liste --------------------------------------------------------------------
if [[ "$MODUS" == "liste" ]]; then
  rc=0
  listen() {
    local label="$1" stamps
    printf '== %s ==\n' "$label"
    if stamps="$(ziel_aufruf "$ZIEL_TYP" auflisten "$ZIEL_PFAD")"; then
      if [[ -n "$stamps" ]]; then sed 's/^/  /' <<<"$stamps"; else echo "  (keine vollstaendigen Saetze)"; fi
    else
      echo "  (Auflisten fehlgeschlagen)"
      rc=1
    fi
  }
  if [[ -n "$VON" ]]; then
    von_aufloesen "$VON" || exit 1
    listen "$VON"
  else
    ZIEL_TYP="local"; ZIEL_PFAD="$BACKUP_DIR"
    listen "lokal ($BACKUP_DIR)"
    for eintrag in ${BACKUP_ZIELE[@]+"${BACKUP_ZIELE[@]}"}; do
      ziel_zerlegen "$eintrag"
      listen "$eintrag"
    done
  fi
  exit "$rc"
fi

# --- db / minio / secrets: Datei beschaffen, pruefen, entschluesseln ----------
ART="$MODUS"
mkdir -p "$BACKUP_DIR"
# Arbeitsverzeichnis im Backup-Verzeichnis statt /tmp: Dumps und MinIO-Archive
# sind gross, /tmp ist oft klein oder RAM-basiert.
ARBEITSDIR="$(mktemp -d "$BACKUP_DIR/.restore.XXXXXX")"
DIENSTE_GESTOPPT=0
aufraeumen() {
  local rc=$?
  trap - EXIT
  rm -rf -- "$ARBEITSDIR"
  if (( DIENSTE_GESTOPPT == 1 )); then
    log "Starte Backend und Worker wieder..."
    app_dienste_starten || warn "Backend/Worker konnten nicht gestartet werden -- bitte 'docker compose start backend worker' ausfuehren."
  fi
  exit "$rc"
}
trap aufraeumen EXIT

if [[ -n "$VON" ]]; then
  von_aufloesen "$VON" || exit 1
  if [[ -z "$STAMP" ]]; then
    STAMP="$(ziel_aufruf "$ZIEL_TYP" auflisten "$ZIEL_PFAD" | tail -n 1)" || { fehler "Auflisten von $VON fehlgeschlagen."; exit 1; }
    [[ -n "$STAMP" ]] || { fehler "Kein vollstaendiger Sicherungssatz in $VON gefunden."; exit 1; }
    log "Kein --stamp angegeben -- verwende den neuesten Satz: $STAMP"
  fi
  SATZDIR="$ARBEITSDIR/satz"
  log "Lade Satz $STAMP (${ART}) von $VON herunter..."
  ziel_aufruf "$ZIEL_TYP" herunterladen "$ZIEL_PFAD" "$STAMP" "$SATZDIR" "$ART" \
    || { fehler "Download von $VON fehlgeschlagen."; exit 1; }
  manifest_pruefen "$SATZDIR" "$STAMP" "$ART-*" || {
    fehler "Der Satz $STAMP enthaelt keine intakte $ART-Datei (Pruefsumme/Manifest) -- Abbruch, es wurde nichts veraendert. Enthaelt der Satz ein Secrets-Buendel? Das gibt es nur bei gesetztem BACKUP_GPG_RECIPIENT."
    exit 1
  }
  NAME="$(satz_dateiname "$SATZDIR" "$STAMP" "$ART")" || { fehler "Der Satz $STAMP enthaelt keine $ART-Datei."; exit 1; }
  QUELLE="$SATZDIR/$NAME"
else
  [[ -f "$DATEI" ]] || { fehler "Backup-Datei nicht gefunden: $DATEI"; exit 1; }
  QUELLE="$DATEI"
  NAME="$(basename "$DATEI")"
  if STAMP="$(stamp_aus_dateiname "$DATEI")" && [[ -f "$(dirname "$DATEI")/manifest-$STAMP.json" ]]; then
    rc=0
    manifest_pruefen "$(dirname "$DATEI")" "$STAMP" "$NAME" || rc=$?
    if (( rc == 1 )); then
      fehler "Pruefsumme stimmt nicht -- Abbruch, es wurde nichts veraendert."
      exit 1
    elif (( rc == 2 )); then
      warn "$NAME steht nicht im Manifest (z.B. lokal abgelegtes Secrets-Buendel) -- Pruefsumme nicht pruefbar."
    fi
  else
    warn "Kein Manifest neben $NAME gefunden -- Pruefsumme kann nicht geprueft werden."
  fi
fi

if [[ "$NAME" == *.gpg ]]; then
  log "Entschluesselle $NAME -- braucht den privaten GPG-Schluessel im Schluesselbund dieses Nutzers."
  datei_entschluesseln "$QUELLE" "$ARBEITSDIR/klartext" || exit 1
  QUELLE="$ARBEITSDIR/klartext"
  NAME="${NAME%.gpg}"
fi

bestaetigen() {
  (( JA == 1 )) && return 0
  if [[ ! -t 0 ]]; then
    fehler "Kein Terminal fuer die Rueckfrage -- fuer Automatisierung --ja angeben. Es wurde nichts veraendert."
    return 1
  fi
  local antwort
  read -rp "$1 Fortfahren? [j/N] " antwort
  [[ "$antwort" == "j" || "$antwort" == "J" || "$antwort" == "y" || "$antwort" == "Y" ]] || { echo "Abgebrochen."; return 1; }
}

case "$MODUS" in
  db)
    : "${POSTGRES_DB:?POSTGRES_DB fehlt in .env}"
    : "${POSTGRES_USER:?POSTGRES_USER fehlt in .env}"
    bestaetigen "Ersetzt den Inhalt der Datenbank '$POSTGRES_DB' vollstaendig durch $NAME (Stand $STAMP). Backend und Worker werden dafuer gestoppt." || exit 1
    log "Stoppe Backend und Worker..."
    app_dienste_stoppen || { fehler "Backend/Worker konnten nicht gestoppt werden."; exit 1; }
    DIENSTE_GESTOPPT=1
    # --single-transaction: scheitert etwas, bleibt die bisherige Datenbank
    # unveraendert statt halb ueberschrieben zurueckzubleiben.
    case "$NAME" in
      *.dump)
        pg_optionen=(--clean --if-exists --exit-on-error --single-transaction)
        (( OHNE_EIGENTUEMER == 1 )) && pg_optionen+=(--no-owner)
        log "Spiele $NAME ein (pg_restore ${pg_optionen[*]})..."
        if ! db_restore_stream "$POSTGRES_DB" "${pg_optionen[@]}" <"$QUELLE"; then
          fehler "pg_restore ist fehlgeschlagen -- die bisherige Datenbank ist unveraendert. Meldung 'role ... does not exist': zuerst die App-Rolle anlegen (scripts/app_rolle_einrichten.sh, macht auch deploy.sh) oder mit --ohne-eigentuemer erneut versuchen und danach scripts/app_rolle_einrichten.sh ausfuehren."
          exit 1
        fi
        ;;
      *.sql.gz)
        # Altformat (Plain-SQL): ohne vorheriges Leeren des Schemas wuerde es auf
        # bestehende Tabellen treffen. Alles in einer Transaktion.
        log "Spiele Altformat $NAME ein (Schema public wird vorher neu angelegt)..."
        if ! { echo 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'; gunzip -c "$QUELLE"; } | db_restore_sql_stream "$POSTGRES_DB"; then
          fehler "Einspielen des Altformats ist fehlgeschlagen -- die bisherige Datenbank ist unveraendert."
          exit 1
        fi
        ;;
      *) fehler "Unbekanntes Datenbank-Format: $NAME (erwartet .dump oder .sql.gz)"; exit 1 ;;
    esac
    log "Datenbank wiederhergestellt."
    echo "Hinweis: War der Code zum Zeitpunkt der Sicherung aelter als der jetzige, danach die Migrationen ausfuehren:"
    echo "  docker compose run --rm backend alembic upgrade head   (mit denselben -f-Dateien wie beim Start)"
    ;;
  minio)
    [[ "$NAME" == *.tar.gz ]] || { fehler "Unbekanntes MinIO-Format: $NAME (erwartet .tar.gz)"; exit 1; }
    bestaetigen "Ersetzt ALLE MinIO-Objektdaten durch $NAME (Stand $STAMP)." || exit 1
    minio_wiederherstellen "$QUELLE" || { fehler "MinIO-Wiederherstellung fehlgeschlagen."; exit 1; }
    log "MinIO-Objektdaten wiederhergestellt."
    echo "Hinweis: Die Objekte sind SSE-verschluesselt -- MINIO_KMS_SECRET_KEY in der .env muss derselbe sein wie bei der Sicherung (restore.sh secrets)."
    ;;
  secrets)
    [[ "$NAME" == *.tar ]] || { fehler "Unbekanntes Secrets-Format: $NAME (erwartet .tar)"; exit 1; }
    tar -tf "$QUELLE" | grep -qx '\.env\|\./\.env' || { fehler "Das Secrets-Buendel enthaelt keine .env."; exit 1; }
    ZIEL_ENV="$REPO_DIR/.env.wiederhergestellt"
    ( umask 077; tar -xOf "$QUELLE" .env >"$ZIEL_ENV" ) || { fehler "Entpacken der .env fehlgeschlagen."; exit 1; }
    chmod 600 "$ZIEL_ENV"
    log "Geschrieben: $ZIEL_ENV (Stand $STAMP) -- die vorhandene .env wurde NICHT angefasst."
    echo "Naechste Schritte:"
    echo "  diff .env .env.wiederhergestellt       # falls schon eine .env existiert: Unterschiede ansehen"
    echo "  cp .env.wiederhergestellt .env         # uebernehmen (auf einem neuen Server VOR scripts/deploy.sh)"
    echo "  rm .env.wiederhergestellt              # danach aufraeumen, die Datei enthaelt alle Secrets"
    ;;
esac
