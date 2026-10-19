#!/usr/bin/env bash
set -euo pipefail

# Beweist, dass das mitgelieferte Beispiel (befehl-beispiel.sh.example) wirklich
# laeuft: gegen einen kleinen WebDAV-Server (python3) mit echtem curl.

# shellcheck source=scripts/tests/helfer.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/helfer.sh"

echo "test_webdav_beispiel.sh"

szenario "befehl-beispiel.sh.example gegen einen WebDAV-Server: Backup, Liste, Restore, Rotation"
if ! command -v python3 >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
  skip "python3 oder curl fehlt"
  test_ende
  exit 0
fi

testumgebung_anlegen
SERVER_PID=""
beenden() {
  [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null || true
  testumgebung_loeschen
}
trap beenden EXIT

rm -f "$BIN/curl" # echtes curl verwenden
mkdir -p "$T/dav-wurzel"
python3 "$FV_TESTS_DIR/webdav_server.py" "$T/dav-wurzel" "$T/dav-port" tester geheimpw &
SERVER_PID=$!
for _ in $(seq 1 50); do [[ -s "$T/dav-port" ]] && break; sleep 0.1; done
PORT="$(cat "$T/dav-port" 2>/dev/null || true)"
if [[ -z "$PORT" ]]; then
  _fv_schlecht "WebDAV-Testserver ist nicht gestartet"
  test_ende
  exit 1
fi

cp "$FV_SCRIPTS_DIR/backup/ziele/befehl-beispiel.sh.example" "$T/webdav.sh"
chmod 700 "$T/webdav.sh"
env_schreiben "BACKUP_TARGETS=befehl:$T/webdav.sh" "BACKUP_ERLAUBE_UNVERSCHLUESSELT_REMOTE=1" \
  "WEBDAV_URL=http://127.0.0.1:$PORT/dav/fieldvibe" "WEBDAV_USER=tester" "WEBDAV_PASSWORD=geheimpw"
DAV="$T/dav-wurzel/fieldvibe"

# Alte Saetze auf dem Server, damit die Rotation etwas zu tun hat
mkdir -p "$DAV"
for s in 20200101-000000 20200102-000000 20200103-000000; do satz_dummy "$DAV" "$s"; done

lauf "$REPO/scripts/backup.sh"
assert_rc 0 "backup.sh mit WebDAV-Beispiel"
S="$(neuester_stamp "$BD")"
assert_datei "$DAV/manifest-$S.json" "Manifest auf dem Server"
assert_datei "$DAV/db-$S.dump" "Dump auf dem Server"
assert_keine_datei "$DAV/secrets-$S.tar" "kein Klartext-Secrets-Buendel auf dem Server"
if cmp -s "$BD/db-$S.dump" "$DAV/db-$S.dump"; then _fv_ok; else _fv_schlecht "hochgeladener Dump weicht ab"; fi
assert_keine_datei "$DAV/manifest-20200101-000000.json" "Rotation hat den aeltesten Satz per DELETE entfernt"
assert_datei "$DAV/manifest-20200103-000000.json" "MIN_KEEP: die neuesten Saetze bleiben"

lauf "$REPO/scripts/restore.sh" liste
assert_rc 0 "restore liste"
assert_enthaelt "$OUT" "== befehl:$T/webdav.sh ==" "Ziel in der Liste"
assert_enthaelt "$OUT" "  $S" "Stamp ueber PROPFIND gefunden"

lauf "$REPO/scripts/restore.sh" db --von "befehl:$T/webdav.sh" --ja
assert_rc 0 "restore db ueber WebDAV"
assert_eq "$(sha256sum <"$BD/db-$S.dump")" "$(sha256sum <"$T/pgrestore-stdin.bin")" "wiederhergestellter Dump = gesicherter Dump"

lauf "$REPO/scripts/backup-pruefen.sh" --von "befehl:$T/webdav.sh"
assert_rc 1 "Pruefung: Remote-Satz ohne GPG hat kein Secrets-Buendel"
assert_enthaelt "$OUT" "kein Secrets-Buendel" "Meldung"
lauf "$REPO/scripts/backup-pruefen.sh" --von "befehl:$T/webdav.sh" --stamp "$S" --nur-pruefsummen
assert_rc 0 "Pruefsummen des Remote-Satzes ok"

# Falsches Passwort: das Ziel scheitert, der Lauf meldet es
env_schreiben "BACKUP_TARGETS=befehl:$T/webdav.sh" "BACKUP_ERLAUBE_UNVERSCHLUESSELT_REMOTE=1" \
  "WEBDAV_URL=http://127.0.0.1:$PORT/dav/fieldvibe" "WEBDAV_USER=tester" "WEBDAV_PASSWORD=falsch"
lauf "$REPO/scripts/backup.sh"
assert_rc 1 "falsches Passwort"
assert_regex "$BD/letzter-lauf.json" '"status": "fehler", "meldung": "Pruefung fehlgeschlagen"' "Status nennt die fehlgeschlagene Pruefung"

test_ende
