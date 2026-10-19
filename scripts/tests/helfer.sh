#!/usr/bin/env bash
# Assert-Hilfen und Testumgebung fuer die Backup-Tests (reines Bash, kein bats).
# Wird von den test_*.sh gesourct. Docker, curl und rclone werden durch Stub-
# Skripte im PATH ersetzt; es wird nie ein echter Docker-Daemon angesprochen.

FV_TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FV_SCRIPTS_DIR="$(dirname "$FV_TESTS_DIR")"

FV_ASSERTS=0
FV_FEHLER=0
FV_SKIPS=0
FV_SZENARIEN=0
FV_AKTUELL=""
T=""

# --- Assert-Hilfen -----------------------------------------------------------------

_fv_ok() { FV_ASSERTS=$((FV_ASSERTS + 1)); }
_fv_schlecht() {
  FV_ASSERTS=$((FV_ASSERTS + 1))
  FV_FEHLER=$((FV_FEHLER + 1))
  printf '    FEHLER [%s]: %s\n' "$FV_AKTUELL" "$1" >&2
  if [[ -n "${2:-}" ]]; then printf '%s\n' "$2" | sed 's/^/      | /' >&2; fi
}

szenario() {
  FV_AKTUELL="$1"
  FV_SZENARIEN=$((FV_SZENARIEN + 1))
  printf '  - %s\n' "$1"
}

skip() {
  FV_SKIPS=$((FV_SKIPS + 1))
  printf '  SKIP: %s\n' "$1"
}

assert_eq() { # erwartet, tatsaechlich, beschreibung
  if [[ "$1" == "$2" ]]; then _fv_ok; else _fv_schlecht "$3 (erwartet '$1', war '$2')"; fi
}
assert_rc() { # erwarteter exit code, beschreibung (liest RC)
  if [[ "$RC" == "$1" ]]; then _fv_ok; else _fv_schlecht "$2 (Exit-Code erwartet $1, war $RC)" "$(tail -n 15 "${OUT:-/dev/null}" 2>/dev/null)"; fi
}
assert_rc_nicht0() {
  if [[ "$RC" != "0" ]]; then _fv_ok; else _fv_schlecht "$1 (Exit-Code war 0, erwartet != 0)" "$(tail -n 15 "${OUT:-/dev/null}" 2>/dev/null)"; fi
}
assert_datei() { if [[ -f "$1" ]]; then _fv_ok; else _fv_schlecht "${2:-Datei fehlt}: $1"; fi; }
assert_keine_datei() { if [[ ! -e "$1" ]]; then _fv_ok; else _fv_schlecht "${2:-Datei sollte nicht existieren}: $1"; fi; }
assert_enthaelt() { # datei, fester Text, beschreibung
  if grep -qF -- "$2" "$1" 2>/dev/null; then _fv_ok; else _fv_schlecht "${3:-Text fehlt} ('$2' in $1)" "$(tail -n 12 "$1" 2>/dev/null)"; fi
}
assert_enthaelt_nicht() {
  if ! grep -qF -- "$2" "$1" 2>/dev/null; then _fv_ok; else _fv_schlecht "${3:-Text unerwartet vorhanden} ('$2' in $1)" "$(grep -F -- "$2" "$1" | head -n 5)"; fi
}
assert_regex() { # datei, ERE, beschreibung
  if grep -qE -- "$2" "$1" 2>/dev/null; then _fv_ok; else _fv_schlecht "${3:-Muster fehlt} ('$2' in $1)" "$(tail -n 12 "$1" 2>/dev/null)"; fi
}

test_ende() {
  printf '  => %s Szenario(en), %s Pruefung(en), %s Fehler, %s SKIP\n' "$FV_SZENARIEN" "$FV_ASSERTS" "$FV_FEHLER" "$FV_SKIPS"
  if [[ -n "${FV_ERGEBNIS:-}" ]]; then
    printf '%s %s %s %s\n' "$FV_SZENARIEN" "$FV_ASSERTS" "$FV_FEHLER" "$FV_SKIPS" >>"$FV_ERGEBNIS"
  fi
  [[ "$FV_FEHLER" -eq 0 ]]
}

# --- Testumgebung --------------------------------------------------------------------------

# Legt ein eigenes "Repo" mit Kopie der Skripte, .env-Platzhalter, Stub-PATH und
# BACKUP_DIR in einem Temp-Verzeichnis an. Setzt T, REPO, BIN, BD.
testumgebung_anlegen() {
  T="$(mktemp -d "${TMPDIR:-/tmp}/fvtest.XXXXXX")"
  REPO="$T/repo"
  BIN="$T/bin"
  BD="$T/backups"
  mkdir -p "$REPO/scripts" "$BIN" "$BD" "$T/home" "$T/tmp" "$T/minio-daten"
  cp -r "$FV_SCRIPTS_DIR/backup" "$REPO/scripts/backup"
  cp "$FV_SCRIPTS_DIR/backup.sh" "$FV_SCRIPTS_DIR/restore.sh" "$FV_SCRIPTS_DIR/backup-pruefen.sh" "$REPO/scripts/"
  printf 'foto-1\n' >"$T/minio-daten/foto1.jpg"
  mkdir -p "$T/minio-daten/.minio.sys"
  printf 'meta\n' >"$T/minio-daten/.minio.sys/config.json"
  : >"$T/stub.log"
  LAUF_ENV=()
  stubs_anlegen
  env_schreiben
}

testumgebung_loeschen() {
  if [[ -n "$T" && -d "$T" && -z "${FV_BEHALTE:-}" ]]; then rm -rf "$T"; fi
}

# Schreibt .env; zusaetzliche Zeilen als Argumente (Werte mit Leerzeichen selbst quoten).
# shellcheck disable=SC2120  # Argumente kommen nur aus den Testdateien
env_schreiben() {
  {
    printf 'POSTGRES_USER=fieldvibe\nPOSTGRES_PASSWORD=geheim\nPOSTGRES_DB=fieldvibe\n'
    printf 'MINIO_KMS_SECRET_KEY=fieldvibe-minio:TESTSCHLUESSEL\nINTEGRATION_SECRET_KEY=test-integration\nJWT_SECRET=test-jwt\n'
    printf 'BACKUP_DIR=%s\nBACKUP_RETENTION_DAYS=14\n' "$BD"
    local zeile
    for zeile in "$@"; do printf '%s\n' "$zeile"; done
  } >"$REPO/.env"
}

# Fuehrt ein Kommando mit sauberer Umgebung aus (env -i), setzt RC und OUT (Logdatei).
# Zusaetzliche Variablen ueber das Array LAUF_ENV (z.B. LAUF_ENV=(STUB_DUMP_FAIL=1)).
lauf() {
  RC=0
  LAUFNR=$(( ${LAUFNR:-0} + 1 ))
  OUT="$T/out.$LAUFNR.log"
  local -a gpg_env=()
  if [[ -n "${GNUPGHOME:-}" ]]; then gpg_env=(GNUPGHOME="$GNUPGHOME"); fi
  ( cd "$T" && env -i PATH="$BIN:$PATH" HOME="$T/home" LANG=C.UTF-8 TZ=UTC TMPDIR="$T/tmp" \
      ${gpg_env[@]+"${gpg_env[@]}"} FV_T="$T" FV_STUB_LOG="$T/stub.log" \
      ${LAUF_ENV[@]+"${LAUF_ENV[@]}"} "$@" ) >"$OUT" 2>&1 </dev/null || RC=$?
}

# Wie lauf(), aber im Hintergrund (fuer den Sperr-Test); PID in LAUF_PID.
lauf_hintergrund() {
  OUT="$T/out.bg.log"
  ( cd "$T" && exec env -i PATH="$BIN:$PATH" HOME="$T/home" LANG=C.UTF-8 TZ=UTC TMPDIR="$T/tmp" \
      FV_T="$T" FV_STUB_LOG="$T/stub.log" ${LAUF_ENV[@]+"${LAUF_ENV[@]}"} "$@" ) >"$OUT" 2>&1 </dev/null &
  # shellcheck disable=SC2034  # wird vom Test (wait) gelesen
  LAUF_PID=$!
}

# Neuester Stamp aus den Manifest-Dateien in $1.
neuester_stamp() {
  local m
  m="$(find "$1" -maxdepth 1 -name 'manifest-*.json' -printf '%f\n' | sort | tail -n 1)"
  m="${m#manifest-}"
  printf '%s\n' "${m%.json}"
}

# Erzeugt einen (un)vollstaendigen Dummy-Satz mit Stamp $2 in $1: nur zum Testen
# der Rotation, Inhalte sind egal.
satz_dummy() { # verz, stamp, [unvollstaendig|alt]
  local v="$1" s="$2" art="${3:-voll}"
  case "$art" in
    voll)
      printf 'x' >"$v/db-$s.dump"; printf 'x' >"$v/minio-$s.tar.gz"; printf '{}' >"$v/manifest-$s.json" ;;
    unvollstaendig)
      printf 'x' >"$v/db-$s.dump"; printf 'x' >"$v/minio-$s.tar.gz" ;;
    alt)
      printf 'x' >"$v/db-$s.sql.gz"; printf 'x' >"$v/minio-$s.tar.gz" ;;
    *) return 1 ;;
  esac
}

# --- GPG ----------------------------------------------------------------------------------------

# Erzeugt (einmal pro Testlauf, siehe run.sh) einen Wegwerf-Schluessel. Setzt
# FV_GNUPGHOME (mit privatem Schluessel) und FV_GNUPGHOME_NURPUB (nur oeffentlicher
# Schluessel -- simuliert den Server ohne privaten Schluessel).
FV_GPG_EMPFAENGER="backup-test@fieldvibe.invalid"
gpg_verfuegbar() { command -v gpg >/dev/null 2>&1 && [[ -n "${FV_GNUPGHOME:-}" && -d "$FV_GNUPGHOME" ]]; }

# Wird von run.sh einmal aufgerufen.
gpg_testschluessel_erzeugen() {
  command -v gpg >/dev/null 2>&1 || return 1
  local basis="$1"
  FV_GNUPGHOME="$basis/gpg-voll"
  FV_GNUPGHOME_NURPUB="$basis/gpg-pub"
  mkdir -p "$FV_GNUPGHOME" "$FV_GNUPGHOME_NURPUB"
  chmod 700 "$FV_GNUPGHOME" "$FV_GNUPGHOME_NURPUB"
  GNUPGHOME="$FV_GNUPGHOME" gpg --batch --quiet --passphrase '' --quick-generate-key "$FV_GPG_EMPFAENGER" default default never >/dev/null 2>&1 || return 1
  GNUPGHOME="$FV_GNUPGHOME" gpg --batch --quiet --export "$FV_GPG_EMPFAENGER" >"$basis/pub.gpg" || return 1
  GNUPGHOME="$FV_GNUPGHOME_NURPUB" gpg --batch --quiet --import "$basis/pub.gpg" >/dev/null 2>&1 || return 1
  export FV_GNUPGHOME FV_GNUPGHOME_NURPUB
}

# --- Stubs ------------------------------------------------------------------------------------------

stubs_anlegen() {
  cat >"$BIN/docker" <<'STUB'
#!/usr/bin/env bash
# Test-Stub fuer docker: protokolliert und liefert feste Ausgaben.
echo "docker $*" >>"$FV_STUB_LOG"
if [[ "$1" == "compose" ]]; then
  shift
  case "$1" in
    exec)
      shift
      [[ "$1" == "-T" ]] && shift
      shift # Dienstname (postgres)
      cmd="$1"; shift
      case "$cmd" in
        pg_dump)
          if [[ -n "${STUB_DUMP_SLEEP:-}" ]]; then : >"$FV_T/dump-gestartet"; sleep "$STUB_DUMP_SLEEP"; fi
          if [[ "${STUB_DUMP_FAIL:-0}" == "1" ]]; then echo "pg_dump: stub-fehler" >&2; exit 1; fi
          printf 'PGDMP\n%s\n' "${STUB_DUMP_INHALT:-fake-dump-inhalt}"
          ;;
        pg_restore)
          echo "pg_restore $*" >>"$FV_T/pgrestore-args"
          cat >"$FV_T/pgrestore-stdin.bin"
          [[ "${STUB_PGRESTORE_FAIL:-0}" == "1" ]] && { echo "pg_restore: stub-fehler" >&2; exit 1; }
          exit 0
          ;;
        psql)
          sql=""
          psql_argumente="$*"
          while [[ $# -gt 0 ]]; do if [[ "$1" == "-c" ]]; then sql="$2"; shift; fi; shift; done
          if [[ -z "$sql" ]]; then
            echo "psql $psql_argumente" >>"$FV_T/psql-args"
            cat >"$FV_T/psql-stdin.bin"
            exit 0
          fi
          echo "SQL: $sql" >>"$FV_T/sql.log"
          case "$sql" in
            *server_version*) echo "16.4" ;;
            *version_num*) echo "0099_stub" ;;
            *alembic_version*) echo "${STUB_ALEMBIC_ZEILEN:-1}" ;;
            *information_schema*) echo "${STUB_TABELLEN:-12}" ;;
            *"count(*)"*) echo "3" ;;
          esac
          ;;
      esac
      ;;
    ps) echo "stubcontainer123" ;;
    stop | start) ;;
  esac
elif [[ "$1" == "run" ]]; then
  all="$*"
  if [[ "$all" == *"tar czf -"* ]]; then
    if [[ "${STUB_MINIO_KAPUTT:-0}" == "1" ]]; then head -c 2048 /dev/zero | tr '\0' 'x' | gzip; exit 0; fi
    tar czf - -C "$FV_T/minio-daten" .
  elif [[ "$all" == *":/backup.tar.gz:ro"* ]]; then
    for a in "$@"; do
      if [[ "$a" == *":/backup.tar.gz:ro" ]]; then
        quelle="${a%:/backup.tar.gz:ro}"
        tar tzf "$quelle" >/dev/null || exit 1
        cp "$quelle" "$FV_T/minio-restore-quelle.tar.gz"
      fi
    done
  fi
fi
exit 0
STUB
  cat >"$BIN/curl" <<'STUB'
#!/usr/bin/env bash
echo "curl $*" >>"$FV_STUB_LOG"
[[ "${STUB_CURL_FAIL:-0}" == "1" ]] && exit 22
exit 0
STUB
  cat >"$BIN/rclone" <<'STUB'
#!/usr/bin/env bash
# Test-Stub fuer rclone: Remote "fake:<pfad>" liegt unter $FV_T/rclone-root/<pfad>.
echo "rclone $*" >>"$FV_STUB_LOG"
cmd="$1"; shift
args=()
for a in "$@"; do [[ "$a" == --* ]] || args+=("$a"); done
if [[ "$cmd" == "listremotes" ]]; then printf 'fake:\nhetzner:\n'; exit 0; fi
[[ "${STUB_RCLONE_FAIL:-0}" == "1" ]] && { echo "rclone: stub-fehler" >&2; exit 1; }
abbild() { if [[ "$1" == *:* && "$1" != /* ]]; then printf '%s/rclone-root/%s' "$FV_T" "${1#*:}"; else printf '%s' "$1"; fi; }
case "$cmd" in
  mkdir) mkdir -p "$(abbild "${args[0]}")" ;;
  copyto) mkdir -p "$(dirname "$(abbild "${args[1]}")")"; cp "$(abbild "${args[0]}")" "$(abbild "${args[1]}")" ;;
  lsf) d="$(abbild "${args[0]}")"; [[ -d "$d" ]] || exit 3; find "$d" -maxdepth 1 -type f -printf '%f\n' ;;
  deletefile) rm -f "$(abbild "${args[0]}")" ;;
  *) echo "rclone-stub: unbekannter Befehl $cmd" >&2; exit 2 ;;
esac
STUB
  chmod +x "$BIN/docker" "$BIN/curl" "$BIN/rclone"
}
