#!/usr/bin/env bash
set -euo pipefail

# Tests fuer scripts/backup-pruefen.sh (Docker/psql/pg_restore sind gestubbt;
# der Test gegen einen echten Postgres steht in test_postgres_echt.sh).

# shellcheck source=scripts/tests/helfer.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/helfer.sh"

echo "test_pruefen.sh"

szenario "--nur-pruefsummen: intakter Satz ok, Manipulation/fehlende Datei/fehlendes Manifest -> Exit != 0"
testumgebung_anlegen
lauf "$REPO/scripts/backup.sh"
S="$(neuester_stamp "$BD")"
lauf "$REPO/scripts/backup-pruefen.sh" --nur-pruefsummen
assert_rc 0 "intakter Satz"
assert_enthaelt "$OUT" "Pruefsumme ok: db-$S.dump" "Pruefsumme je Datei geloggt"
assert_enthaelt_nicht "$T/stub.log" "pg_restore" "keine DB-Arbeit bei --nur-pruefsummen"
cp "$BD/db-$S.dump" "$T/db-orig"
printf 'X' | dd of="$BD/db-$S.dump" bs=1 seek=7 conv=notrunc 2>/dev/null
lauf "$REPO/scripts/backup-pruefen.sh" --nur-pruefsummen
assert_rc 1 "manipulierter Dump (gleiche Groesse)"
assert_enthaelt "$OUT" "Pruefsumme stimmt nicht" "SHA-256-Abweichung gemeldet"
cp "$T/db-orig" "$BD/db-$S.dump"
rm "$BD/minio-$S.tar.gz"
lauf "$REPO/scripts/backup-pruefen.sh" --nur-pruefsummen
assert_rc 1 "Satz mit fehlender Datei zaehlt nicht mehr als vollstaendig"
lauf "$REPO/scripts/backup-pruefen.sh" --nur-pruefsummen --stamp "$S"
assert_rc 1 "fehlende Datei bei explizitem Stamp"
assert_enthaelt "$OUT" "nicht gefunden" "fehlende Datei gemeldet"
rm "$BD/manifest-$S.json"
lauf "$REPO/scripts/backup-pruefen.sh" --nur-pruefsummen
assert_rc 1 "fehlendes Manifest (kein vollstaendiger Satz mehr)"
lauf "$REPO/scripts/backup-pruefen.sh" --nur-pruefsummen --stamp "$S"
assert_rc 1 "explizit angegebener Stamp ohne Manifest"
testumgebung_loeschen

szenario "leeres Backup-Verzeichnis: Exit != 0"
testumgebung_anlegen
lauf "$REPO/scripts/backup-pruefen.sh" --nur-pruefsummen
assert_rc 1 "kein Satz vorhanden"
assert_enthaelt "$OUT" "Kein vollstaendiger Sicherungssatz" "klare Meldung"
testumgebung_loeschen

szenario "vollstaendiger Test-Restore (Stubs): Wegwerf-DB wird angelegt, geprueft und geloescht"
testumgebung_anlegen
lauf "$REPO/scripts/backup.sh"
S="$(neuester_stamp "$BD")"
lauf "$REPO/scripts/backup-pruefen.sh"
assert_rc 0 "Test-Restore"
TESTDB="restore_test_${S//-/_}"
assert_enthaelt "$T/sql.log" "CREATE DATABASE \"$TESTDB\"" "Wegwerf-DB angelegt"
assert_enthaelt "$T/pgrestore-args" "-d $TESTDB --exit-on-error --no-owner --no-acl" "pg_restore --exit-on-error in die Wegwerf-DB"
assert_eq "DROP DATABASE IF EXISTS \"$TESTDB\"" "$(tail -n 1 "$T/sql.log" | sed 's/^SQL: //')" "letzte SQL-Anweisung loescht die Wegwerf-DB"
assert_enthaelt_nicht "$T/sql.log" "DATABASE IF EXISTS \"fieldvibe\"" "Produktions-DB nie angefasst"
assert_enthaelt_nicht "$T/sql.log" "DATABASE \"fieldvibe\"" "Produktions-DB nie angelegt/geloescht"
assert_eq "0" "$(grep -c -- "-d fieldvibe\b" "$T/pgrestore-args" || true)" "kein pg_restore in die Produktions-DB"
assert_enthaelt "$OUT" "Test-Restore ok" "Plausibilitaetsergebnis"
assert_enthaelt "$OUT" "mandanten=3" "Zeilenanzahl mandanten ausgegeben"
assert_enthaelt "$OUT" "users=3" "Zeilenanzahl users ausgegeben"
assert_enthaelt "$OUT" "alembic 0099_stub" "alembic-Version ausgegeben"
testumgebung_loeschen

szenario "Test-Restore scheitert: Exit != 0 und die Wegwerf-DB wird trotzdem geloescht"
testumgebung_anlegen
lauf "$REPO/scripts/backup.sh"
S="$(neuester_stamp "$BD")"
LAUF_ENV=(STUB_PGRESTORE_FAIL=1)
lauf "$REPO/scripts/backup-pruefen.sh"
assert_rc 1 "pg_restore scheitert"
TESTDB="restore_test_${S//-/_}"
assert_eq "DROP DATABASE IF EXISTS \"$TESTDB\"" "$(tail -n 1 "$T/sql.log" | sed 's/^SQL: //')" "Wegwerf-DB per Trap geloescht"
LAUF_ENV=(STUB_ALEMBIC_ZEILEN=0)
lauf "$REPO/scripts/backup-pruefen.sh"
assert_rc 1 "alembic_version leer"
assert_enthaelt "$OUT" "alembic_version" "Meldung nennt alembic_version"
LAUF_ENV=(STUB_TABELLEN=0)
lauf "$REPO/scripts/backup-pruefen.sh"
assert_rc 1 "keine Tabellen"
testumgebung_loeschen

szenario "kaputtes MinIO-Archiv (gzip ok, tar nicht lesbar) wird erkannt"
testumgebung_anlegen
LAUF_ENV=(STUB_MINIO_KAPUTT=1)
lauf "$REPO/scripts/backup.sh"
assert_rc 0 "Backup selbst merkt es nicht (gzip ist gueltig)"
LAUF_ENV=()
lauf "$REPO/scripts/backup-pruefen.sh"
assert_rc 1 "tar tzf schlaegt fehl"
assert_enthaelt "$OUT" "MinIO-Archiv ist nicht lesbar" "Meldung"
testumgebung_loeschen

szenario "Ping und Benachrichtigung (eigener Pruef-Ping)"
testumgebung_anlegen
env_schreiben "BACKUP_PING_URL=https://ping.example/backup" "BACKUP_PRUEF_PING_URL=https://ping.example/pruefung" \
  "BACKUP_BENACHRICHTIGUNG_BEFEHL='printf \"%s|%s\\n\" \"\$BACKUP_STATUS\" \"\$BACKUP_NACHRICHT\" >>\"\$FV_T/benachrichtigung.log\"'"
lauf "$REPO/scripts/backup.sh"
: >"$T/stub.log"
lauf "$REPO/scripts/backup-pruefen.sh"
assert_rc 0 "Pruefung ok"
assert_regex "$T/stub.log" "^curl .*https://ping.example/pruefung/start\$" "Start-Ping der Pruefung"
assert_regex "$T/stub.log" "^curl .*https://ping.example/pruefung\$" "Erfolgs-Ping der Pruefung"
assert_enthaelt_nicht "$T/stub.log" "ping.example/backup" "nicht der Ping des Backups"
assert_regex "$T/benachrichtigung.log" "^ok\|Backup-Pruefung" "Benachrichtigung ok"
: >"$T/stub.log"
LAUF_ENV=(STUB_PGRESTORE_FAIL=1)
lauf "$REPO/scripts/backup-pruefen.sh"
assert_rc 1 "Pruefung scheitert"
assert_regex "$T/stub.log" "^curl .*https://ping.example/pruefung/fail\$" "Fehler-Ping"
assert_regex "$T/benachrichtigung.log" "^fehler\|Backup-Pruefung .* FEHLGESCHLAGEN" "Benachrichtigung fehler"
testumgebung_loeschen

szenario "GPG: Entschluesselung + Test-Restore; ohne privaten Schluessel nur Pruefsummen"
if gpg_verfuegbar; then
  testumgebung_anlegen
  env_schreiben "BACKUP_GPG_RECIPIENT=$FV_GPG_EMPFAENGER" "BACKUP_TARGETS=rclone:fake:bucket/p"
  GNUPGHOME="$FV_GNUPGHOME"
  lauf "$REPO/scripts/backup.sh"
  assert_rc 0 "verschluesselter Lauf"
  S="$(neuester_stamp "$BD")"
  lauf "$REPO/scripts/backup-pruefen.sh"
  assert_rc 0 "Pruefung lokal mit privatem Schluessel"
  assert_enthaelt "$OUT" "Test-Restore ok" "Test-Restore lief"
  assert_eq "$(printf 'PGDMP\nfake-dump-inhalt\n' | sha256sum)" "$(sha256sum <"$T/pgrestore-stdin.bin")" "entschluesselter Dump wurde eingespielt"
  lauf "$REPO/scripts/backup-pruefen.sh" --von rclone:fake:bucket/p
  assert_rc 0 "Pruefung eines Remote-Satzes"
  assert_enthaelt "$OUT" "Secrets ok" "Secrets-Buendel lesbar"
  : >"$T/stub.log"
  GNUPGHOME="$FV_GNUPGHOME_NURPUB"
  lauf "$REPO/scripts/backup-pruefen.sh"
  assert_rc 0 "ohne privaten Schluessel: nur Pruefsummen"
  assert_enthaelt "$OUT" "nur Pruefsummen" "klare Meldung"
  assert_enthaelt_nicht "$T/stub.log" "pg_restore" "kein Test-Restore ohne Schluessel"
  printf 'X' | dd of="$BD/db-$S.dump.gpg" bs=1 seek=20 conv=notrunc 2>/dev/null
  lauf "$REPO/scripts/backup-pruefen.sh"
  assert_rc 1 "Pruefsumme schlaegt auch ohne Schluessel an"
  unset GNUPGHOME
  testumgebung_loeschen
else
  skip "gpg nicht verfuegbar"
fi

szenario "Remote-Satz ohne GPG enthaelt kein Secrets-Buendel -> Fehler"
testumgebung_anlegen
env_schreiben "BACKUP_TARGETS=local:$T/ziel"
lauf "$REPO/scripts/backup.sh"
lauf "$REPO/scripts/backup-pruefen.sh" --von "local:$T/ziel"
assert_rc 1 "Satz ohne Secrets"
assert_enthaelt "$OUT" "kein Secrets-Buendel" "Meldung"
lauf "$REPO/scripts/backup-pruefen.sh"
assert_rc 0 "lokaler Satz: Klartext-Secrets nur lokal ist ein Hinweis, kein Fehler"
testumgebung_loeschen

test_ende
