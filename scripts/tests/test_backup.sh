#!/usr/bin/env bash
set -euo pipefail

# Tests fuer scripts/backup.sh, die Ziel-Adapter und die Rotation (ohne Docker).

# shellcheck source=scripts/tests/helfer.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/helfer.sh"

json_gueltig() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$1" 2>/dev/null
  else
    return 0
  fi
}

# Ruft ziel_aufruf() einer Adapter-Funktion mit der Lib aus dem Test-Repo auf.
adapter() {
  lauf "$BASH" -c 'REPO_DIR=$1; shift; source "$REPO_DIR/scripts/backup/lib.sh"; ziel_aufruf "$@"' _ "$REPO" "$@"
}

echo "test_backup.sh"

# --- (a) -------------------------------------------------------------------------------------------
szenario "(a) lokaler Lauf erzeugt vollstaendigen Satz mit korrekten SHA-256"
testumgebung_anlegen
git -C "$REPO" init -q
git -C "$REPO" -c user.name=t -c user.email=t@t commit -q --allow-empty -m x
lauf "$REPO/scripts/backup.sh"
assert_rc 0 "backup.sh ohne Ziele"
S="$(neuester_stamp "$BD")"
assert_datei "$BD/db-$S.dump" "DB-Dump"
assert_datei "$BD/minio-$S.tar.gz" "MinIO-Archiv"
assert_datei "$BD/secrets-$S.tar" "Secrets-Buendel"
assert_datei "$BD/manifest-$S.json" "Manifest"
assert_eq "PGDMP" "$(head -c 5 "$BD/db-$S.dump")" "Custom-Format-Kopf"
assert_enthaelt "$BD/manifest-$S.json" "$(sha256sum "$BD/db-$S.dump" | cut -d' ' -f1)" "SHA-256 des Dumps im Manifest"
assert_enthaelt "$BD/manifest-$S.json" "$(sha256sum "$BD/minio-$S.tar.gz" | cut -d' ' -f1)" "SHA-256 des MinIO-Archivs im Manifest"
assert_enthaelt "$BD/manifest-$S.json" "\"groesse\": $(wc -c <"$BD/db-$S.dump" | tr -d ' ')," "Groesse im Manifest"
assert_enthaelt_nicht "$BD/manifest-$S.json" "secrets-" "Klartext-Secrets nicht im Manifest"
assert_enthaelt "$BD/manifest-$S.json" '"format_version": 1' "Format-Version"
assert_enthaelt "$BD/manifest-$S.json" '"postgres_version": "16.4"' "Postgres-Version"
assert_enthaelt "$BD/manifest-$S.json" "\"git_commit\": \"$(git -C "$REPO" rev-parse --short HEAD)\"" "Git-Commit"
assert_eq "600" "$(stat -c %a "$BD/secrets-$S.tar")" "Rechte des Secrets-Buendels"
assert_eq "$(cat "$REPO/.env")" "$(tar -xOf "$BD/secrets-$S.tar" .env)" "Secrets-Buendel enthaelt die .env"
assert_datei "$BD/letzter-lauf.json" "letzter-lauf.json"
assert_enthaelt "$BD/letzter-lauf.json" '"status": "ok"' "Gesamtstatus ok"
if json_gueltig "$BD/letzter-lauf.json" && json_gueltig "$BD/manifest-$S.json"; then _fv_ok; else _fv_schlecht "JSON von Status/Manifest ungueltig"; fi
assert_enthaelt "$T/stub.log" "pg_dump -Fc -U fieldvibe fieldvibe" "pg_dump im Custom-Format aufgerufen"
assert_enthaelt "$OUT" "BACKUP_GPG_RECIPIENT nicht gesetzt" "Warnung ohne GPG"
assert_keine_datei "$BD/.upload-$S" "Upload-Staging aufgeraeumt"
testumgebung_loeschen

# --- (b) ---------------------------------------------------------------------------------------------
szenario "(b) local-Ziel: Roundtrip hochladen/auflisten/herunterladen"
testumgebung_anlegen
env_schreiben "BACKUP_TARGETS=local:$T/ziel1" "BACKUP_ERLAUBE_UNVERSCHLUESSELT_REMOTE=0"
lauf "$REPO/scripts/backup.sh"
assert_rc 0 "Lauf mit local-Ziel"
S="$(neuester_stamp "$BD")"
assert_datei "$T/ziel1/manifest-$S.json" "Manifest im Ziel"
assert_datei "$T/ziel1/db-$S.dump" "Dump im Ziel"
assert_keine_datei "$T/ziel1/secrets-$S.tar" "Klartext-Secrets nicht im local-Ziel"
adapter local auflisten "$T/ziel1"
assert_eq "$S" "$(cat "$OUT")" "auflisten liefert den Stamp"
adapter local herunterladen "$T/ziel1" "$S" "$T/dl"
assert_rc 0 "herunterladen"
if cmp -s "$BD/db-$S.dump" "$T/dl/db-$S.dump" && cmp -s "$BD/manifest-$S.json" "$T/dl/manifest-$S.json"; then _fv_ok; else _fv_schlecht "heruntergeladene Dateien weichen ab"; fi
adapter local herunterladen "$T/ziel1" "$S" "$T/dl-db" db
assert_datei "$T/dl-db/db-$S.dump" "Art-Filter: DB geholt"
assert_keine_datei "$T/dl-db/minio-$S.tar.gz" "Art-Filter: MinIO nicht geholt"
assert_datei "$T/dl-db/manifest-$S.json" "Art-Filter: Manifest immer"
adapter local herunterladen "$T/ziel1" "20000101-000000" "$T/dl-x"
assert_rc_nicht0 "herunterladen eines unbekannten Stamps"
# Ein Satz ohne Manifest zaehlt nicht
rm "$T/ziel1/manifest-$S.json"
adapter local auflisten "$T/ziel1"
assert_eq "" "$(cat "$OUT")" "Satz ohne Manifest wird nicht aufgelistet"
testumgebung_loeschen

# --- (c) ---------------------------------------------------------------------------------------------
szenario "(c) befehl-Ziel mit Fake-Adapter (fremder Anbieter ohne Repo-Aenderung)"
testumgebung_anlegen
cat >"$T/fake-adapter.sh" <<'ADAPTER'
#!/usr/bin/env bash
# Fake-Anbieter: legt alles unter $FV_T/anbieter ab.
set -euo pipefail
D="$FV_T/anbieter"; mkdir -p "$D"
echo "$*" >>"$FV_T/adapter-aufrufe.log"
case "$1" in
  pruefen) ;;
  hochladen)
    for f in "$2"/*-"$3".*; do [[ "$f" == */manifest-* ]] || cp "$f" "$D/"; done
    cp "$2/manifest-$3.json" "$D/" ;;
  auflisten) find "$D" -name 'manifest-*.json' -printf '%f\n' | sed 's/^manifest-\(.*\)\.json$/\1/' | sort ;;
  herunterladen) mkdir -p "$3"; cp "$D"/*-"$2".* "$3/" ;;
  aufraeumen) echo "Rotation $2 $3" >>"$FV_T/adapter-aufrufe.log" ;;
  *) exit 2 ;;
esac
ADAPTER
chmod +x "$T/fake-adapter.sh"
env_schreiben "BACKUP_TARGETS=befehl:$T/fake-adapter.sh" "BACKUP_ERLAUBE_UNVERSCHLUESSELT_REMOTE=1"
lauf "$REPO/scripts/backup.sh"
assert_rc 0 "Lauf mit befehl-Ziel"
S="$(neuester_stamp "$BD")"
assert_datei "$T/anbieter/db-$S.dump" "Anbieter hat den Dump"
assert_datei "$T/anbieter/manifest-$S.json" "Anbieter hat das Manifest"
assert_regex "$T/adapter-aufrufe.log" "^hochladen .*/\.upload-$S $S\$" "hochladen <verzeichnis> <stamp>"
assert_regex "$T/adapter-aufrufe.log" "^Rotation 14 3\$" "aufraeumen <tage> <min>"
assert_regex "$T/adapter-aufrufe.log" "^pruefen\$" "pruefen aufgerufen"
lauf "$REPO/scripts/restore.sh" liste --von "befehl:$T/fake-adapter.sh"
assert_rc 0 "restore liste --von befehl"
assert_enthaelt "$OUT" "$S" "liste zeigt den Stamp des Fremd-Anbieters"
lauf "$REPO/scripts/restore.sh" db --von "befehl:$T/fake-adapter.sh" --stamp "$S" --ja
assert_rc 0 "restore db --von befehl"
assert_eq "$(sha256sum <"$BD/db-$S.dump")" "$(sha256sum <"$T/pgrestore-stdin.bin")" "pg_restore bekam genau den gesicherten Dump"
lauf "$REPO/scripts/restore.sh" db --von "befehl:/nicht/vorhanden.sh" --ja
assert_rc_nicht0 "unbekanntes Adapterprogramm"
testumgebung_loeschen

# --- (d) ---------------------------------------------------------------------------------------------
szenario "(d) fehlschlagendes Ziel: Exit != 0, andere Ziele bedient, letzter-lauf.json zeigt beides"
testumgebung_anlegen
cat >"$T/kaputt.sh" <<'ADAPTER'
#!/usr/bin/env bash
case "$1" in hochladen) echo "Anbieter nicht erreichbar" >&2; exit 1 ;; *) exit 0 ;; esac
ADAPTER
chmod +x "$T/kaputt.sh"
env_schreiben "BACKUP_TARGETS=\"befehl:$T/kaputt.sh local:$T/ziel2\"" "BACKUP_ERLAUBE_UNVERSCHLUESSELT_REMOTE=1" "BACKUP_PING_URL=https://ping.example/abc"
lauf "$REPO/scripts/backup.sh"
assert_rc 1 "ein Ziel scheitert"
S="$(neuester_stamp "$BD")"
assert_datei "$T/ziel2/manifest-$S.json" "zweites Ziel wurde trotzdem bedient"
assert_enthaelt "$BD/letzter-lauf.json" '"status": "fehler"' "Gesamtstatus fehler"
assert_regex "$BD/letzter-lauf.json" "\"ziel\": \"befehl:$T/kaputt.sh\", \"status\": \"fehler\"" "fehlerhaftes Ziel im Status"
assert_regex "$BD/letzter-lauf.json" "\"ziel\": \"local:$T/ziel2\", \"status\": \"ok\"" "gutes Ziel im Status"
assert_regex "$T/stub.log" "^curl .*https://ping.example/abc/fail\$" "Fehlerping gesendet"
json_gueltig "$BD/letzter-lauf.json" && _fv_ok || _fv_schlecht "letzter-lauf.json ist kein gueltiges JSON"
testumgebung_loeschen

# --- (e) ---------------------------------------------------------------------------------------------
szenario "(e) Abwaertskompatibilitaet: BACKUP_OFFSITE_REMOTE -> rclone-Adapter"
testumgebung_anlegen
env_schreiben "BACKUP_OFFSITE_REMOTE=fake:bucket/fieldvibe" "BACKUP_ERLAUBE_UNVERSCHLUESSELT_REMOTE=1"
lauf "$REPO/scripts/backup.sh"
assert_rc 0 "Lauf mit altem BACKUP_OFFSITE_REMOTE"
S="$(neuester_stamp "$BD")"
assert_enthaelt "$OUT" "BACKUP_OFFSITE_REMOTE ist veraltet" "Hinweis auf veraltete Variable"
assert_enthaelt "$T/stub.log" "rclone copyto $BD/.upload-$S/db-$S.dump fake:bucket/fieldvibe/db-$S.dump" "rclone copyto fuer den Dump"
assert_datei "$T/rclone-root/bucket/fieldvibe/manifest-$S.json" "Manifest beim Anbieter"
zeile_db="$(grep -n "copyto .*db-$S.dump" "$T/stub.log" | head -n 1 | cut -d: -f1)"
zeile_manifest="$(grep -n "copyto .*manifest-$S.json" "$T/stub.log" | head -n 1 | cut -d: -f1)"
if (( zeile_manifest > zeile_db )); then _fv_ok; else _fv_schlecht "Manifest muss zuletzt hochgeladen werden"; fi
assert_enthaelt "$T/stub.log" "rclone listremotes" "Remote-Konfiguration geprueft"
adapter rclone auflisten fake:bucket/fieldvibe
assert_eq "$S" "$(cat "$OUT")" "rclone auflisten"
adapter rclone herunterladen fake:bucket/fieldvibe "$S" "$T/dl-rc" secrets
assert_rc 0 "rclone herunterladen"
assert_datei "$T/dl-rc/manifest-$S.json" "rclone: Manifest geholt"
assert_keine_datei "$T/dl-rc/db-$S.dump" "rclone: Art-Filter"
# BACKUP_TARGETS hat Vorrang vor der alten Variable
env_schreiben "BACKUP_OFFSITE_REMOTE=fake:bucket/alt" "BACKUP_TARGETS=local:$T/ziel-neu"
lauf "$REPO/scripts/backup.sh"
assert_rc 0 "BACKUP_TARGETS gewinnt"
assert_keine_datei "$T/rclone-root/bucket/alt" "alte Variable ignoriert, wenn BACKUP_TARGETS gesetzt"
testumgebung_loeschen

# --- (f) ---------------------------------------------------------------------------------------------
szenario "(f) Remote-Ziel ohne GPG wird verweigert, mit ausdruecklichem Opt-in erlaubt"
testumgebung_anlegen
env_schreiben "BACKUP_TARGETS=rclone:fake:bucket/x"
lauf "$REPO/scripts/backup.sh"
assert_rc 1 "unverschluesselter Remote-Upload"
assert_enthaelt "$OUT" "Upload verweigert" "klare Meldung"
assert_enthaelt_nicht "$T/stub.log" "copyto" "nichts wurde hochgeladen"
S="$(neuester_stamp "$BD")"
assert_datei "$BD/manifest-$S.json" "lokaler Satz trotzdem vollstaendig"
assert_enthaelt "$BD/letzter-lauf.json" '"status": "fehler"' "Status fehler"
env_schreiben "BACKUP_TARGETS=rclone:fake:bucket/x" "BACKUP_ERLAUBE_UNVERSCHLUESSELT_REMOTE=1"
lauf "$REPO/scripts/backup.sh"
assert_rc 0 "mit BACKUP_ERLAUBE_UNVERSCHLUESSELT_REMOTE=1"
assert_enthaelt "$OUT" "UNVERSCHLUESSELT" "Warnung beim erlaubten Klartext-Upload"
assert_enthaelt "$T/stub.log" "copyto" "jetzt wird hochgeladen"
env_schreiben "BACKUP_TARGETS=local:$T/ziel-lokal"
lauf "$REPO/scripts/backup.sh"
assert_rc 0 "local-Ziel braucht keine Verschluesselung"
testumgebung_loeschen

# --- (g) ---------------------------------------------------------------------------------------------
szenario "(g) Secrets-Buendel geht ohne GPG nie an ein Ziel"
testumgebung_anlegen
env_schreiben "BACKUP_TARGETS=\"rclone:fake:bucket/s local:$T/ziel-s\"" "BACKUP_ERLAUBE_UNVERSCHLUESSELT_REMOTE=1"
lauf "$REPO/scripts/backup.sh"
assert_rc 0 "Lauf ohne GPG mit erlaubtem Klartext-Upload"
S="$(neuester_stamp "$BD")"
assert_datei "$BD/secrets-$S.tar" "Secrets lokal vorhanden"
assert_eq "0" "$(find "$T/rclone-root" "$T/ziel-s" -name 'secrets-*' | wc -l | tr -d ' ')" "keine Secrets bei Remote-/local-Ziel"
assert_eq "0" "$(grep -rl "test-integration" "$T/rclone-root" "$T/ziel-s" 2>/dev/null | wc -l | tr -d ' ')" "kein Secret-Inhalt in den Zielen"
assert_enthaelt "$OUT" "wird nicht uebertragen" "Warnung zum Secrets-Buendel"
testumgebung_loeschen

# --- (g2) GPG ----------------------------------------------------------------------------------------
szenario "(g2) mit GPG: alles verschluesselt, Manifest-Summen der finalen Dateien, Secrets im Ziel"
if gpg_verfuegbar; then
  testumgebung_anlegen
  GNUPGHOME="$FV_GNUPGHOME"
  env_schreiben "BACKUP_GPG_RECIPIENT=$FV_GPG_EMPFAENGER" "BACKUP_TARGETS=rclone:fake:bucket/g"
  lauf "$REPO/scripts/backup.sh"
  assert_rc 0 "verschluesselter Lauf mit Remote-Ziel ohne Opt-in"
  S="$(neuester_stamp "$BD")"
  assert_datei "$BD/db-$S.dump.gpg" "DB verschluesselt"
  assert_datei "$BD/minio-$S.tar.gz.gpg" "MinIO verschluesselt"
  assert_datei "$BD/secrets-$S.tar.gpg" "Secrets verschluesselt"
  assert_keine_datei "$BD/db-$S.dump" "Klartext-Dump entfernt"
  assert_keine_datei "$BD/secrets-$S.tar" "Klartext-Secrets entfernt"
  assert_enthaelt "$BD/manifest-$S.json" "$(sha256sum "$BD/db-$S.dump.gpg" | cut -d' ' -f1)" "Manifest enthaelt SHA-256 der verschluesselten Datei"
  assert_enthaelt "$BD/manifest-$S.json" '"verschluesselt": true' "Manifest-Flag"
  assert_datei "$T/rclone-root/bucket/g/secrets-$S.tar.gpg" "verschluesseltes Secrets-Buendel im Ziel"
  assert_eq "0" "$(grep -c "fake-dump-inhalt" "$BD/db-$S.dump.gpg" || true)" "Dump-Inhalt nicht im Klartext"
  GNUPGHOME="$FV_GNUPGHOME" gpg --batch --quiet --decrypt "$BD/secrets-$S.tar.gpg" 2>/dev/null >"$T/secrets.tar"
  assert_eq "$(cat "$REPO/.env")" "$(tar -xOf "$T/secrets.tar" .env)" "entschluesseltes Secrets-Buendel = .env"
  unset GNUPGHOME
  testumgebung_loeschen
else
  skip "gpg nicht verfuegbar"
fi

# --- (h) ---------------------------------------------------------------------------------------------
szenario "(h) Rotation: BACKUP_MIN_KEEP schuetzt, unvollstaendige/alte Saetze werden geloescht"
testumgebung_anlegen
V="$T/rot"; mkdir -p "$V"
for s in 20200101-000000 20200102-000000 20200103-000000 20200104-000000 20200105-000000; do satz_dummy "$V" "$s"; done
satz_dummy "$V" 20200106-000000 unvollstaendig
satz_dummy "$V" 20190101-000000 alt
HEUTE="$(date +%Y%m%d-%H%M%S)"
satz_dummy "$V" "$HEUTE"
printf 'x' >"$V/notizen.txt"; printf '{}' >"$V/letzter-lauf.json"
adapter local aufraeumen "$V" 14 3
assert_rc 0 "Rotation"
assert_keine_datei "$V/manifest-20200101-000000.json" "aeltester Satz geloescht"
assert_keine_datei "$V/db-20200102-000000.dump" "zweitaeltester geloescht"
assert_keine_datei "$V/minio-20200103-000000.tar.gz" "drittaeltester geloescht"
assert_datei "$V/manifest-20200104-000000.json" "die 3 neuesten vollstaendigen Saetze bleiben (2)"
assert_datei "$V/manifest-20200105-000000.json" "die 3 neuesten vollstaendigen Saetze bleiben (3)"
assert_datei "$V/manifest-$HEUTE.json" "aktueller Satz bleibt"
assert_keine_datei "$V/db-20200106-000000.dump" "unvollstaendiger Satz geloescht"
assert_keine_datei "$V/db-20190101-000000.sql.gz" "Altformat geloescht (genug neue Saetze)"
assert_datei "$V/notizen.txt" "fremde Datei unberuehrt"
assert_datei "$V/letzter-lauf.json" "Statusdatei unberuehrt"
# Langer Ausfall: alles alt, aber MIN_KEEP bleibt
V2="$T/rot2"; mkdir -p "$V2"
for s in 20200101-000000 20200102-000000 20200103-000000; do satz_dummy "$V2" "$s"; done
adapter local aufraeumen "$V2" 14 3
assert_eq "3" "$(find "$V2" -name 'manifest-*' | wc -l | tr -d ' ')" "Bei langem Ausfall bleiben MIN_KEEP Saetze trotz Alter"
# Weniger als MIN_KEEP + Altformat: Altformat bleibt als einzige weitere Sicherung
V3="$T/rot3"; mkdir -p "$V3"
satz_dummy "$V3" 20200101-000000
satz_dummy "$V3" 20190101-000000 alt
satz_dummy "$V3" 20200102-000000 unvollstaendig
adapter local aufraeumen "$V3" 14 3
assert_datei "$V3/db-20190101-000000.sql.gz" "Altformat bleibt, solange weniger als MIN_KEEP neue Saetze existieren"
assert_datei "$V3/manifest-20200101-000000.json" "einziger vollstaendiger Satz bleibt"
assert_keine_datei "$V3/db-20200102-000000.dump" "unvollstaendiger Satz auch hier geloescht"
# MIN_KEEP=1, RETENTION=0
V4="$T/rot4"; mkdir -p "$V4"
for s in 20200101-000000 20200102-000000; do satz_dummy "$V4" "$s"; done
adapter local aufraeumen "$V4" 0 1
assert_datei "$V4/manifest-20200102-000000.json" "MIN_KEEP=1 behaelt den neuesten"
assert_keine_datei "$V4/manifest-20200101-000000.json" "MIN_KEEP=1 loescht den aelteren"
# gleiche Regeln beim rclone-Adapter
mkdir -p "$T/rclone-root/b/rot"
for s in 20200101-000000 20200102-000000 20200103-000000 20200104-000000; do
  satz_dummy "$T/rclone-root/b/rot" "$s"
done
adapter rclone aufraeumen fake:b/rot 14 3
assert_rc 0 "rclone-Rotation"
assert_keine_datei "$T/rclone-root/b/rot/manifest-20200101-000000.json" "rclone: aeltester Satz geloescht"
assert_datei "$T/rclone-root/b/rot/manifest-20200102-000000.json" "rclone: MIN_KEEP bleibt"
assert_enthaelt "$T/stub.log" "rclone deletefile fake:b/rot/db-20200101-000000.dump" "rclone deletefile verwendet"
# Integration: backup.sh rotiert BACKUP_DIR und ein local-Ziel
mkdir -p "$T/ziel-r"
for s in 20200101-000000 20200102-000000 20200103-000000; do satz_dummy "$BD" "$s"; satz_dummy "$T/ziel-r" "$s"; done
env_schreiben "BACKUP_TARGETS=local:$T/ziel-r" "BACKUP_MIN_KEEP=2"
lauf "$REPO/scripts/backup.sh"
assert_rc 0 "backup.sh mit Rotation"
S="$(neuester_stamp "$BD")"
assert_keine_datei "$BD/manifest-20200101-000000.json" "lokal: alter Satz rotiert"
assert_keine_datei "$BD/manifest-20200102-000000.json" "lokal: MIN_KEEP=2 (neuer + 1 alter): zweiter alter rotiert"
assert_datei "$BD/manifest-20200103-000000.json" "lokal: ein alter Satz bleibt"
assert_keine_datei "$T/ziel-r/manifest-20200101-000000.json" "Ziel: alter Satz rotiert"
assert_datei "$T/ziel-r/manifest-$S.json" "Ziel: neuer Satz vorhanden"
testumgebung_loeschen

# --- (j) ---------------------------------------------------------------------------------------------
szenario "(j) zweiter paralleler Lauf wird durch die Sperre abgewiesen"
testumgebung_anlegen
LAUF_ENV=(STUB_DUMP_SLEEP=3)
lauf_hintergrund "$REPO/scripts/backup.sh"
for _ in $(seq 1 50); do [[ -f "$T/dump-gestartet" ]] && break; sleep 0.1; done
assert_datei "$T/dump-gestartet" "erster Lauf laeuft"
LAUF_ENV=()
lauf "$REPO/scripts/backup.sh"
assert_rc 75 "zweiter Lauf"
assert_enthaelt "$OUT" "laeuft bereits eine Sicherung" "klare Meldung"
RC=0
wait "$LAUF_PID" || RC=$?
OUT="$T/out.bg.log"
assert_rc 0 "erster Lauf endet erfolgreich"
assert_eq "1" "$(find "$BD" -name 'manifest-*' | wc -l | tr -d ' ')" "genau ein Satz"
lauf "$REPO/scripts/backup.sh"
assert_rc 0 "nach Ende des ersten Laufs ist die Sperre wieder frei"
testumgebung_loeschen

# --- (k) ---------------------------------------------------------------------------------------------
szenario "(k) Ping-URL und Benachrichtigungsbefehl"
testumgebung_anlegen
env_schreiben "BACKUP_PING_URL=https://ping.example/uuid-1" \
  "BACKUP_BENACHRICHTIGUNG_BEFEHL='printf \"%s|%s|%s\\n\" \"\$BACKUP_STATUS\" \"\$BACKUP_NACHRICHT\" \"\$BACKUP_STAMP\" >>\"\$FV_T/benachrichtigung.log\"'"
lauf "$REPO/scripts/backup.sh"
assert_rc 0 "erfolgreicher Lauf"
S="$(neuester_stamp "$BD")"
assert_regex "$T/stub.log" "^curl -fsS -m 10 --retry 3 .*https://ping.example/uuid-1/start\$" "Start-Ping mit curl-Optionen"
assert_regex "$T/stub.log" "^curl .*https://ping.example/uuid-1\$" "Erfolgs-Ping"
assert_enthaelt_nicht "$T/stub.log" "/fail" "kein Fehler-Ping"
assert_regex "$T/benachrichtigung.log" "^ok\|Sicherung $S ok.*\|$S\$" "Benachrichtigung mit BACKUP_STATUS=ok"
: >"$T/stub.log"
LAUF_ENV=(STUB_DUMP_FAIL=1)
lauf "$REPO/scripts/backup.sh"
assert_rc 1 "fehlgeschlagener Lauf"
assert_regex "$T/stub.log" "^curl .*https://ping.example/uuid-1/start\$" "Start-Ping auch beim Fehlerlauf"
assert_regex "$T/stub.log" "^curl .*https://ping.example/uuid-1/fail\$" "Fehler-Ping"
assert_eq "0" "$(grep -cE 'uuid-1$' "$T/stub.log" || true)" "kein Erfolgs-Ping beim Fehler"
assert_regex "$T/benachrichtigung.log" "^fehler\|Sicherung .* FEHLGESCHLAGEN" "Benachrichtigung mit BACKUP_STATUS=fehler"
assert_eq "0" "$(find "$BD" -name 'db-*' -o -name 'minio-*' -o -name 'manifest-*' | grep -v "$S" | wc -l | tr -d ' ')" "keine halben Dateien des fehlgeschlagenen Laufs"
assert_enthaelt "$BD/letzter-lauf.json" '"status": "fehler"' "Status fehler"
LAUF_ENV=(STUB_CURL_FAIL=1)
lauf "$REPO/scripts/backup.sh"
assert_rc 0 "kaputter Ping laesst den Lauf nicht scheitern"
assert_enthaelt "$OUT" "Ping" "Warnung zum Ping"
testumgebung_loeschen

# --- (l) Konfigurationsfehler ------------------------------------------------------------------------
szenario "(l) ungueltige Konfiguration bricht ab"
testumgebung_anlegen
env_schreiben "BACKUP_MIN_KEEP=0"
lauf "$REPO/scripts/backup.sh"
assert_rc 1 "BACKUP_MIN_KEEP=0"
env_schreiben "BACKUP_TARGETS=ohnedoppelpunkt"
lauf "$REPO/scripts/backup.sh"
assert_rc 1 "ungueltiges Ziel"
env_schreiben "BACKUP_TARGETS=gibtesnicht:/x"
lauf "$REPO/scripts/backup.sh"
assert_rc 1 "unbekannter Zieltyp"
assert_enthaelt "$OUT" "Unbekannter Zieltyp" "Meldung zum Zieltyp"
env_schreiben "BACKUP_TARGETS=local:$BD"
lauf "$REPO/scripts/backup.sh"
assert_rc 1 "local-Ziel identisch mit BACKUP_DIR"
testumgebung_loeschen

test_ende
