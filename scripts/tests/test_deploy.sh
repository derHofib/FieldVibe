#!/usr/bin/env bash
set -euo pipefail

# Tests fuer den Release-Ablauf in scripts/deploy-lib.sh (deploy_release & Co.).
# docker, backup.sh und migrieren.sh sind gestubbt: geprueft wird die REIHENFOLGE und
# die Entscheidungslogik (Backup-Abbruch, Migration vor Rollout, Health-Gate, Rollback
# auf den Vorgaenger-Tag), NICHT das Verhalten echter Container.

# shellcheck source=scripts/tests/helfer.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/helfer.sh"

echo "test_deploy.sh"

umgebung() {
  testumgebung_anlegen
  cp "$FV_SCRIPTS_DIR/deploy-lib.sh" "$REPO/scripts/"
  mkdir -p "$T/images"
  : >"$REPO/docker-compose.yml"
  # Treiber: ruft die Bibliotheksfunktionen wie scripts/deploy.sh auf.
  cat >"$REPO/treiber.sh" <<'TREIBER'
#!/usr/bin/env bash
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE=(docker compose -f docker-compose.yml)
# shellcheck source=/dev/null
source "$REPO_DIR/scripts/deploy-lib.sh"
"$@"
TREIBER
  cat >"$REPO/scripts/backup.sh" <<'STUB'
#!/usr/bin/env bash
echo "backup" >>"$FV_STUB_LOG"
[[ "${STUB_BACKUP_FAIL:-0}" == "1" ]] && { echo "Backup kaputt" >&2; exit 1; }
BD="$(grep '^BACKUP_DIR=' "$(dirname "$0")/../.env" | cut -d= -f2-)"
printf '{\n  "stamp": "20260101-020000",\n  "status": "ok"\n}\n' >"$BD/letzter-lauf.json"
STUB
  cat >"$REPO/scripts/migrieren.sh" <<'STUB'
#!/usr/bin/env bash
echo "migrieren tag=${IMAGE_TAG:-} args=$*" >>"$FV_STUB_LOG"
[[ "${STUB_MIGRATION_FAIL:-0}" == "1" ]] && { echo "Migration kaputt" >&2; exit 1; }
exit 0
STUB
  # docker: Subbefehl hinter "compose [-f datei]..." auswerten.
  cat >"$BIN/docker" <<'STUB'
#!/usr/bin/env bash
if [[ "$1" == "compose" ]]; then
  shift
  while [[ "${1:-}" == "-f" ]]; do shift 2; done
  sub="$1"; shift
  echo "compose $sub tag=${IMAGE_TAG:-} $*" >>"$FV_STUB_LOG"
  case "$sub" in
    config) [[ "${STUB_CONFIG_FAIL:-0}" == "1" ]] && exit 1; exit 0 ;;
    ps)
      [[ "$*" == *"-q postgres"* && -f "$FV_T/postgres-laeuft" ]] && echo pgcid
      [[ "$*" == *"-q backend" && -f "$FV_T/stack-laeuft" ]] && echo becid
      [[ "$*" == *"-q frontend" && -f "$FV_T/stack-laeuft" ]] && echo fecid
      exit 0 ;;
    build)
      [[ "${STUB_BUILD_FAIL:-0}" == "1" ]] && exit 1
      : >"$FV_T/images/fieldvibe-backend:$IMAGE_TAG"; : >"$FV_T/images/fieldvibe-frontend:$IMAGE_TAG"; exit 0 ;;
    up)
      [[ "${STUB_UP_FAIL:-0}" == "1" && "$*" == *"--no-build"* && "$IMAGE_TAG" == "${STUB_UP_FAIL_TAG:-neu}" ]] && exit 1
      [[ "$*" == *"--no-build"* && "$*" == *"--remove-orphans"* ]] && echo "$IMAGE_TAG" >"$FV_T/aktiv"
      exit 0 ;;
    exec)
      aktiv="$(cat "$FV_T/aktiv" 2>/dev/null || true)"
      for t in ${STUB_GATE_FAIL_TAGS:-}; do [[ "$aktiv" == "$t" ]] && exit 1; done
      exit 0 ;;
    *) exit 0 ;;
  esac
fi
echo "docker $*" >>"$FV_STUB_LOG"
case "$1" in
  info) [[ "${STUB_INFO_FAIL:-0}" == "1" ]] && exit 1; exit 0 ;;
  inspect) echo "sha256:abc123"; exit 0 ;;
  tag) : >"$FV_T/images/${3}"; exit 0 ;;
  image) [[ -f "$FV_T/images/${3}" ]] && exit 0; exit 1 ;;
esac
exit 0
STUB
  chmod +x "$BIN/docker" "$REPO/scripts/backup.sh" "$REPO/scripts/migrieren.sh" "$REPO/treiber.sh"
  env_schreiben
}

# Vorgaenger "alt" ist ausgerollt und laeuft.
vorgaenger_alt() {
  : >"$T/images/fieldvibe-backend:alt"; : >"$T/images/fieldvibe-frontend:alt"
  printf 'CURRENT_TAG=alt\n' >"$REPO/.deploy-state"
  : >"$T/postgres-laeuft"; : >"$T/stack-laeuft"
  echo alt >"$T/aktiv"
}

# Zeilennummer der ersten Log-Zeile, die das Muster enthaelt (0 = nicht vorhanden).
zeile() { grep -nF -- "$1" "$T/stub.log" | head -n1 | cut -d: -f1 || true; }
zeile_nr() { local z; z="$(zeile "$1")"; echo "${z:-0}"; }

treiber() { lauf bash "$REPO/treiber.sh" "$@"; }

# --------------------------------------------------------------------------------------

szenario "Erfolg: Reihenfolge Backup, Build, Migration VOR Rollout, Gate; State wird fortgeschrieben"
umgebung; vorgaenger_alt
treiber deploy_release neu
assert_rc 0 "Release"
b="$(zeile_nr "backup")"; bau="$(zeile_nr "compose build tag=neu")"; mig="$(zeile_nr "migrieren tag=neu")"
roll="$(zeile_nr "compose up tag=neu -d --no-build --remove-orphans")"; gate="$(zeile_nr "compose exec tag= -T backend")"
[[ "$b" -gt 0 && "$b" -lt "$bau" && "$bau" -lt "$mig" && "$mig" -lt "$roll" && "$roll" -lt "$gate" ]] \
  && _fv_ok || _fv_schlecht "Reihenfolge Backup($b) < Build($bau) < Migration($mig) < Rollout($roll) < Gate($gate)" "$(cat "$T/stub.log")"
assert_enthaelt "$T/stub.log" "compose stop tag= worker" "Worker wird vor der Migration ruhend gestellt"
assert_enthaelt "$REPO/.deploy-state" "CURRENT_TAG=neu" "aktueller Tag"
assert_enthaelt "$REPO/.deploy-state" "PREVIOUS_TAG=alt" "Vorgaenger-Tag gemerkt"
assert_enthaelt "$REPO/.deploy-state" "BACKUP_STAMP=20260101-020000" "Backup-Stamp im State"
testumgebung_loeschen

szenario "Backup fehlgeschlagen: Abbruch ohne Build, Migration oder Rollout (Exit 10)"
umgebung; vorgaenger_alt
LAUF_ENV=(STUB_BACKUP_FAIL=1)
treiber deploy_release neu
assert_rc 10 "Exit-Code Backup"
assert_enthaelt_nicht "$T/stub.log" "compose build" "kein Build"
assert_enthaelt_nicht "$T/stub.log" "migrieren" "keine Migration"
assert_enthaelt_nicht "$T/stub.log" "--no-build" "kein Rollout"
assert_enthaelt "$OUT" "Backup fehlgeschlagen" "Meldung"
assert_enthaelt "$REPO/.deploy-state" "CURRENT_TAG=alt" "State unveraendert"
LAUF_ENV=()
testumgebung_loeschen

szenario "Opt-out: --ohne-backup ueberspringt das Backup (mit Warnung), Release laeuft durch"
umgebung; vorgaenger_alt
LAUF_ENV=(STUB_BACKUP_FAIL=1 DEPLOY_OHNE_BACKUP=1)
treiber deploy_release neu
assert_rc 0 "Release trotz kaputtem Backup-Skript"
assert_enthaelt_nicht "$T/stub.log" "backup" "Backup nicht aufgerufen"
assert_enthaelt "$OUT" "Backup uebersprungen" "Warnung"
LAUF_ENV=()
testumgebung_loeschen

szenario "Backup bereits von deploy.sh erledigt: kein zweiter Lauf"
umgebung; vorgaenger_alt
LAUF_ENV=(DEPLOY_BACKUP_ERLEDIGT=1)
treiber deploy_release neu
assert_rc 0 "Release"
assert_enthaelt_nicht "$T/stub.log" "backup" "Backup nicht doppelt"
LAUF_ENV=()
testumgebung_loeschen

szenario "Migration fehlgeschlagen: kein Rollout, laufende Version bleibt, Worker wird mit altem Tag neu gestartet (Exit 11)"
umgebung; vorgaenger_alt
LAUF_ENV=(STUB_MIGRATION_FAIL=1)
treiber deploy_release neu
assert_rc 11 "Exit-Code Migration"
assert_enthaelt_nicht "$T/stub.log" "compose up tag=neu -d --no-build --remove-orphans" "kein Rollout"
assert_enthaelt "$T/stub.log" "compose up tag=alt -d --no-build worker" "Worker laeuft wieder mit dem alten Stand"
assert_enthaelt "$OUT" "NICHT ausgerollt" "Meldung"
assert_enthaelt "$REPO/.deploy-state" "CURRENT_TAG=alt" "State unveraendert"
LAUF_ENV=()
testumgebung_loeschen

szenario "Build fehlgeschlagen: nichts migriert, nichts ausgerollt (Exit 14)"
umgebung; vorgaenger_alt
LAUF_ENV=(STUB_BUILD_FAIL=1)
treiber deploy_release neu
assert_rc 14 "Exit-Code Build"
assert_enthaelt_nicht "$T/stub.log" "migrieren" "keine Migration"
LAUF_ENV=()
testumgebung_loeschen

szenario "Gate-Timeout: automatischer Rollback auf den Vorgaenger-Tag, Hinweis zu Migrationen (Exit 12)"
umgebung; vorgaenger_alt
LAUF_ENV=(STUB_GATE_FAIL_TAGS=neu DEPLOY_HEALTH_TIMEOUT=2 DEPLOY_HEALTH_INTERVALL=1)
treiber deploy_release neu
assert_rc 12 "Exit-Code Rollback erfolgreich"
roll_neu="$(zeile_nr "compose up tag=neu -d --no-build --remove-orphans")"
roll_alt="$(zeile_nr "compose up tag=alt -d --no-build --remove-orphans")"
[[ "$roll_neu" -gt 0 && "$roll_alt" -gt "$roll_neu" ]] && _fv_ok || _fv_schlecht "Rollback (alt) nach Rollout (neu)" "$(cat "$T/stub.log")"
assert_enthaelt "$OUT" "Health-Gate" "Gate-Fehlschlag gemeldet"
assert_enthaelt "$OUT" "NICHT zurueckgerollt" "Hinweis: Migrationen nicht rueckrollbar"
assert_enthaelt "$OUT" "restore.sh db --stamp 20260101-020000" "Restore-Hinweis mit Backup-Stamp"
assert_enthaelt "$REPO/.deploy-state" "CURRENT_TAG=alt" "aktueller Stand bleibt der Vorgaenger"
assert_enthaelt "$REPO/.deploy-state" "FEHLGESCHLAGEN_TAG=neu" "fehlgeschlagener Tag vermerkt"
assert_enthaelt_nicht "$REPO/.deploy-state" "CURRENT_TAG=neu" "neuer Tag nicht als aktuell gemerkt"
LAUF_ENV=()
testumgebung_loeschen

szenario "Rollout selbst scheitert: ebenfalls Rollback"
umgebung; vorgaenger_alt
LAUF_ENV=(STUB_UP_FAIL=1 STUB_UP_FAIL_TAG=neu DEPLOY_HEALTH_TIMEOUT=2 DEPLOY_HEALTH_INTERVALL=1)
treiber deploy_release neu
assert_rc 12 "Exit-Code"
assert_enthaelt "$T/stub.log" "compose up tag=alt -d --no-build --remove-orphans" "Rollback ausgefuehrt"
LAUF_ENV=()
testumgebung_loeschen

szenario "Erstinstallation ohne Vorgaenger: Gate scheitert, kein Rollback moeglich (Exit 13), Backup uebersprungen"
umgebung
LAUF_ENV=(STUB_GATE_FAIL_TAGS=neu DEPLOY_HEALTH_TIMEOUT=2 DEPLOY_HEALTH_INTERVALL=1)
treiber deploy_release neu
assert_rc 13 "Exit-Code kein Rollback"
assert_enthaelt_nicht "$T/stub.log" "backup" "kein Backup ohne laufende Datenbank"
assert_enthaelt "$OUT" "kein automatischer Rollback" "Hinweis"
LAUF_ENV=()
testumgebung_loeschen

szenario "Erstinstallation erfolgreich: State ohne Vorgaenger"
umgebung
treiber deploy_release neu
assert_rc 0 "Release"
assert_enthaelt "$REPO/.deploy-state" "CURRENT_TAG=neu" "Tag gemerkt"
assert_enthaelt_nicht "$REPO/.deploy-state" "PREVIOUS_TAG" "kein Vorgaenger"
testumgebung_loeschen

szenario "Vorgaenger-Images fehlen (docker image prune): kein Rollback, Exit 13"
umgebung; vorgaenger_alt
rm -f "$T/images/fieldvibe-backend:alt" "$T/images/fieldvibe-frontend:alt"
LAUF_ENV=(STUB_GATE_FAIL_TAGS=neu DEPLOY_HEALTH_TIMEOUT=2 DEPLOY_HEALTH_INTERVALL=1)
treiber deploy_release neu
assert_rc 13 "Exit-Code"
assert_enthaelt_nicht "$T/stub.log" "compose up tag=alt -d --no-build --remove-orphans" "kein Rollback-Versuch"
assert_enthaelt "$OUT" "nicht mehr vorhanden" "Hinweis"
LAUF_ENV=()
testumgebung_loeschen

szenario "Rollback scheitert ebenfalls am Gate (Exit 13)"
umgebung; vorgaenger_alt
LAUF_ENV=(STUB_GATE_FAIL_TAGS="neu alt" DEPLOY_HEALTH_TIMEOUT=2 DEPLOY_HEALTH_INTERVALL=1)
treiber deploy_release neu
assert_rc 13 "Exit-Code"
assert_enthaelt "$OUT" "Rollback nicht moeglich oder ebenfalls fehlgeschlagen" "Meldung"
LAUF_ENV=()
testumgebung_loeschen

szenario "Bestandsinstallation ohne .deploy-state: laufender Stand wird als Rollback-Ziel getaggt und ist zurueckrollbar"
umgebung
: >"$T/postgres-laeuft"; : >"$T/stack-laeuft"; echo unbekannt >"$T/aktiv"
LAUF_ENV=(STUB_GATE_FAIL_TAGS=neu DEPLOY_HEALTH_TIMEOUT=2 DEPLOY_HEALTH_INTERVALL=1)
treiber deploy_release neu
assert_rc 12 "Rollback auf den gesicherten Altstand"
assert_regex "$T/stub.log" "^docker tag sha256:abc123 fieldvibe-backend:vorher-[0-9]{14}$" "Backend-Image getaggt"
assert_regex "$T/stub.log" "^docker tag sha256:abc123 fieldvibe-frontend:vorher-[0-9]{14}$" "Frontend-Image getaggt"
assert_regex "$REPO/.deploy-state" "^CURRENT_TAG=vorher-[0-9]{14}$" "Altstand ist aktueller Tag"
LAUF_ENV=()
testumgebung_loeschen

szenario "Vorab-Check: Docker-Daemon, Compose-Konfiguration und Plattenplatz"
umgebung
LAUF_ENV=(STUB_INFO_FAIL=1); treiber deploy_vorabcheck
assert_rc 1 "Daemon nicht erreichbar"; assert_enthaelt "$OUT" "Docker-Daemon" "Meldung"
LAUF_ENV=(STUB_CONFIG_FAIL=1); treiber deploy_vorabcheck
assert_rc 1 "Compose-Konfiguration ungueltig"
LAUF_ENV=(DEPLOY_MIN_FREI_MB=999999999 DEPLOY_DISK_PFAD="$T"); treiber deploy_vorabcheck
assert_rc 1 "zu wenig Plattenplatz"; assert_enthaelt "$OUT" "Plattenplatz" "Meldung"
LAUF_ENV=(DEPLOY_MIN_FREI_MB=1 DEPLOY_DISK_PFAD="$T"); treiber deploy_vorabcheck
assert_rc 0 "alles in Ordnung"
LAUF_ENV=()
testumgebung_loeschen

szenario "State-Datei: lesen, setzen, ersetzen ohne Duplikate"
umgebung
treiber deploy_state_setzen CURRENT_TAG a
treiber deploy_state_setzen CURRENT_TAG b
treiber deploy_state_setzen PREVIOUS_TAG a
assert_eq "2" "$(wc -l <"$REPO/.deploy-state" | tr -d ' ')" "genau zwei Zeilen"
assert_enthaelt "$REPO/.deploy-state" "CURRENT_TAG=b" "ersetzt"
treiber deploy_state_lesen PREVIOUS_TAG
assert_eq "a" "$(cat "$OUT")" "gelesen"
testumgebung_loeschen

test_ende
