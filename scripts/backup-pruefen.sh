#!/usr/bin/env bash
set -euo pipefail

# Test-Restore: prueft, ob ein Sicherungssatz im Ernstfall wirklich taugt --
# ein Backup, das nie zurueckgespielt wurde, ist nur eine Hoffnung.
#
# Ablauf: neuesten (oder --stamp) Satz aus dem lokalen BACKUP_DIR oder von einem
# Ziel (--von) nehmen, alle Pruefsummen gegen das Manifest pruefen, entschluesseln,
# das DB-Dump in eine WEGWERF-Datenbank restore_test_<stamp> im Postgres-Container
# einspielen und auf Plausibilitaet pruefen, MinIO-Archiv und Secrets-Buendel auf
# Lesbarkeit pruefen. Die Produktions-Datenbank wird nie angefasst; die Wegwerf-
# Datenbank wird in jedem Fall wieder geloescht.
#
# Usage: scripts/backup-pruefen.sh [--stamp <stamp>] [--von <typ:ziel>] [--nur-pruefsummen]
#
# Ohne privaten GPG-Schluessel auf diesem Rechner (Normalfall auf dem Server!)
# bleibt es bei der Pruefsummen-Pruefung; den vollstaendigen Test-Restore dann auf
# einem Rechner mit Schluessel und Stack ausfuehren (siehe docs/DEPLOYMENT.md).
# Ergebnis wird per BACKUP_PRUEF_PING_URL und BACKUP_BENACHRICHTIGUNG_BEFEHL gemeldet.
#
# Cron (sonntags 04:30, richtet scripts/deploy.sh ein):
#   30 4 * * 0 /pfad/zu/SocialCRM/scripts/backup-pruefen.sh >> /var/log/fieldvibe-backup-pruefen.log 2>&1

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
# shellcheck source=scripts/backup/lib.sh
source "$REPO_DIR/scripts/backup/lib.sh"

STAMP=""
VON=""
NUR_PRUEFSUMMEN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --stamp) STAMP="${2:?--stamp braucht einen Wert}"; shift ;;
    --von)   VON="${2:?--von braucht ein Ziel (<typ:ziel> oder lokal)}"; shift ;;
    --nur-pruefsummen) NUR_PRUEFSUMMEN=1 ;;
    -h | --help) sed -n '4,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) fehler "Unbekannte Option: $1"; exit 1 ;;
  esac
  shift
done

if (( NUR_PRUEFSUMMEN == 1 )); then backup_env_laden optional; else backup_env_laden || exit 1; fi
backup_konfig_auswerten || exit 1
umask 077
mkdir -p "$BACKUP_DIR"

PRUEF_PING_URL="${BACKUP_PRUEF_PING_URL:-}"
GESAMT="ok"
MELDUNGEN=()
HINWEISE=()
ABGESCHLOSSEN=0
ARBEITSDIR="$(mktemp -d "$BACKUP_DIR/.pruefen.XXXXXX")"

problem() {
  GESAMT="fehler"
  MELDUNGEN+=("$1")
  fehler "$1"
}

# Auch bei unerwartetem Abbruch: Wegwerf-DB loeschen und das Ergebnis melden.
abschliessen() {
  local rc=$?
  trap - EXIT
  db_testrestore_aufraeumen
  rm -rf -- "$ARBEITSDIR"
  if (( ABGESCHLOSSEN == 0 )); then
    GESAMT="fehler"
    MELDUNGEN+=("Unerwarteter Abbruch (Exit-Code $rc)")
    fehler "Unerwarteter Abbruch (Exit-Code $rc)."
  fi
  local meldung m verbunden=""
  if [[ "$GESAMT" == "ok" ]]; then
    for m in ${HINWEISE[@]+"${HINWEISE[@]}"}; do verbunden+="${verbunden:+; }$m"; done
    meldung="Backup-Pruefung ${STAMP:-?} ok${verbunden:+ ($verbunden)}"
    log "Fertig: $meldung"
    ping_senden "$PRUEF_PING_URL" ""
    benachrichtigen ok "$meldung" "${STAMP:-}"
    exit 0
  fi
  for m in ${MELDUNGEN[@]+"${MELDUNGEN[@]}"}; do verbunden+="${verbunden:+; }$m"; done
  meldung="Backup-Pruefung ${STAMP:-?} FEHLGESCHLAGEN: $verbunden"
  fehler "$meldung"
  ping_senden "$PRUEF_PING_URL" "/fail"
  benachrichtigen fehler "$meldung" "${STAMP:-}"
  exit 1
}
trap abschliessen EXIT

# Spaetere Schritte hoeren nach dem ersten Fehler nicht auf (jeder Befund ist
# eine eigene Information), bauen aber nur auf Vorherigem auf, wenn das ging.
pruefen_hauptteil() {
  local verz ziel_typ ziel_pfad dateiname secrets_name
  ping_senden "$PRUEF_PING_URL" "/start"

  # --- Quelle bestimmen -------------------------------------------------------
  if [[ -n "$VON" ]]; then
    if [[ "$VON" == "lokal" ]]; then ziel_typ="local"; ziel_pfad="$BACKUP_DIR"; else ziel_zerlegen "$VON"; ziel_typ="$ZIEL_TYP"; ziel_pfad="$ZIEL_PFAD"; fi
  else
    ziel_typ="local"; ziel_pfad="$BACKUP_DIR"
  fi
  if [[ -z "$STAMP" ]]; then
    STAMP="$(ziel_aufruf "$ziel_typ" auflisten "$ziel_pfad" | tail -n 1)" || { problem "Auflisten von ${VON:-lokal} fehlgeschlagen"; return 0; }
    [[ -n "$STAMP" ]] || { problem "Kein vollstaendiger Sicherungssatz in ${VON:-lokal} gefunden"; return 0; }
  fi
  log "Pruefe Satz $STAMP aus ${VON:-lokal ($BACKUP_DIR)}..."
  if [[ "$ziel_typ" == "local" ]]; then
    verz="$ziel_pfad"
  else
    verz="$ARBEITSDIR/satz"
    ziel_aufruf "$ziel_typ" herunterladen "$ziel_pfad" "$STAMP" "$verz" alle \
      || { problem "Download des Satzes $STAMP von $VON fehlgeschlagen"; return 0; }
  fi

  # --- Pruefsummen ----------------------------------------------------------------
  if ! manifest_pruefen "$verz" "$STAMP" "*"; then
    problem "Pruefsummen-Pruefung fehlgeschlagen (Satz beschaedigt, unvollstaendig oder manipuliert)"
    return 0
  fi
  HINWEISE+=("Pruefsummen ok")
  if (( NUR_PRUEFSUMMEN == 1 )); then return 0; fi

  # --- Secrets-Buendel vorhanden? ------------------------------------------------------
  # Ohne .env im Satz sind nach einem Totalverlust MinIO-Objekte und Integrations-
  # Zugangsdaten verloren. Ohne GPG liegt das Buendel nur lokal (nicht im Manifest,
  # nie auf Remote-Zielen): lokal ein Hinweis, aus einem Remote-Satz ein Fehler.
  secrets_name=""
  if secrets_name="$(satz_dateiname "$verz" "$STAMP" secrets)"; then
    if ! grep -q "\"secrets-$STAMP" "$verz/manifest-$STAMP.json"; then
      HINWEISE+=("Secrets-Buendel nur lokal und unverschluesselt")
    fi
  else
    problem "Der Satz enthaelt kein Secrets-Buendel (BACKUP_GPG_RECIPIENT beim Backup nicht gesetzt?) -- die .env waere nach einem Totalverlust nicht aus dem Backup zu holen"
  fi

  # --- Entschluesselung moeglich? ---------------------------------------------------------
  local ist_verschluesselt=0
  compgen -G "$verz/*-$STAMP.*.gpg" >/dev/null && ist_verschluesselt=1
  if (( ist_verschluesselt == 1 )) && ! gpg_privater_schluessel_vorhanden; then
    warn "Kein privater GPG-Schluessel auf diesem Rechner -- Entschluesselung und Test-Restore uebersprungen (nur Pruefsummen geprueft). Vollstaendigen Test auf einem Rechner mit Schluessel ausfuehren."
    HINWEISE+=("nur Pruefsummen: kein privater GPG-Schluessel hier")
    return 0
  fi

  # --- Secrets ------------------------------------------------------------------------------------
  if [[ -n "$secrets_name" ]]; then
    local sec="$verz/$secrets_name"
    if [[ "$secrets_name" == *.gpg ]]; then
      if datei_entschluesseln "$sec" "$ARBEITSDIR/secrets.tar"; then sec="$ARBEITSDIR/secrets.tar"; else problem "Secrets-Buendel nicht entschluesselbar"; sec=""; fi
    fi
    if [[ -n "$sec" ]]; then
      if tar -tf "$sec" 2>/dev/null | grep -qx '\.env\|\./\.env'; then HINWEISE+=("Secrets ok"); else problem "Secrets-Buendel ist nicht lesbar oder enthaelt keine .env"; fi
    fi
  fi

  # --- MinIO ---------------------------------------------------------------------------------------
  if dateiname="$(satz_dateiname "$verz" "$STAMP" minio)"; then
    local mi="$verz/$dateiname"
    if [[ "$dateiname" == *.gpg ]]; then
      if datei_entschluesseln "$mi" "$ARBEITSDIR/minio.tar.gz"; then mi="$ARBEITSDIR/minio.tar.gz"; else problem "MinIO-Archiv nicht entschluesselbar"; mi=""; fi
    fi
    if [[ -n "$mi" ]]; then
      if tar -tzf "$mi" >/dev/null 2>&1; then HINWEISE+=("MinIO-Archiv lesbar"); else problem "MinIO-Archiv ist nicht lesbar (tar tzf)"; fi
    fi
  else
    problem "Der Satz enthaelt kein MinIO-Archiv"
  fi

  # --- Datenbank (Test-Restore in Wegwerf-DB) -------------------------------------------------------------
  if dateiname="$(satz_dateiname "$verz" "$STAMP" db)"; then
    local dump="$verz/$dateiname" ok=1
    if [[ "$dateiname" == *.gpg ]]; then
      if datei_entschluesseln "$dump" "$ARBEITSDIR/db.dump"; then dump="$ARBEITSDIR/db.dump"; else problem "Datenbank-Dump nicht entschluesselbar"; ok=0; fi
    fi
    if (( ok == 1 )) && [[ "$dump" == *.dump ]]; then
      : "${POSTGRES_USER:?POSTGRES_USER fehlt in .env}"
      : "${POSTGRES_DB:?POSTGRES_DB fehlt in .env}"
      if db_testrestore "$dump" "$STAMP"; then HINWEISE+=("Test-Restore: ${TESTRESTORE_ERGEBNIS:-ok}"); else problem "Test-Restore der Datenbank fehlgeschlagen"; fi
    elif (( ok == 1 )); then
      problem "Datenbank-Dump im Altformat ($dateiname) -- kein Test-Restore moeglich (neues Backup anlegen)"
    fi
  else
    problem "Der Satz enthaelt keinen Datenbank-Dump"
  fi
  return 0
}

pruefen_hauptteil
ABGESCHLOSSEN=1
