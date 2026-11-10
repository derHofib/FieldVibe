#!/usr/bin/env bash
set -euo pipefail

# Tests fuer scripts/restore.sh (Docker/pg_restore/psql sind gestubbt).

# shellcheck source=scripts/tests/helfer.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/helfer.sh"

zeile_von() { grep -n -- "$1" "$T/stub.log" | head -n 1 | cut -d: -f1; }

echo "test_restore.sh"

# --- db: lokale Datei -------------------------------------------------------------------------------
szenario "db: Custom-Format wird mit --clean/--if-exists/--exit-on-error/--single-transaction eingespielt"
testumgebung_anlegen
lauf "$REPO/scripts/backup.sh"
S="$(neuester_stamp "$BD")"
lauf "$REPO/scripts/restore.sh" db "$BD/db-$S.dump" --ja
assert_rc 0 "restore db"
assert_enthaelt "$T/pgrestore-args" "--clean --if-exists --exit-on-error --single-transaction" "pg_restore-Optionen"
assert_enthaelt_nicht "$T/pgrestore-args" "--no-owner" "Eigentuemer (App-Rolle) bleiben erhalten"
assert_enthaelt "$T/pgrestore-args" "-d fieldvibe" "Ziel-Datenbank"
assert_eq "$(sha256sum <"$BD/db-$S.dump")" "$(sha256sum <"$T/pgrestore-stdin.bin")" "pg_restore bekam genau den gesicherten Dump"
z_stop="$(zeile_von "compose stop backend worker")"; z_rest="$(zeile_von "pg_restore")"; z_start="$(zeile_von "compose start backend worker")"
if [[ -n "$z_stop" && -n "$z_rest" && -n "$z_start" ]] && (( z_stop < z_rest && z_rest < z_start )); then _fv_ok; else _fv_schlecht "Reihenfolge stop -> pg_restore -> start ($z_stop/$z_rest/$z_start)"; fi
rm -f "$T/pgrestore-args"
lauf "$REPO/scripts/restore.sh" db "$BD/db-$S.dump" --ja --ohne-eigentuemer
assert_enthaelt "$T/pgrestore-args" "--no-owner" "--ohne-eigentuemer reicht --no-owner durch"
testumgebung_loeschen

szenario "db: ohne Terminal und ohne --ja wird nichts veraendert"
testumgebung_anlegen
lauf "$REPO/scripts/backup.sh"
S="$(neuester_stamp "$BD")"
lauf "$REPO/scripts/restore.sh" db "$BD/db-$S.dump"
assert_rc 1 "restore ohne --ja und ohne Terminal"
assert_enthaelt "$OUT" "--ja" "Hinweis auf --ja"
assert_keine_datei "$T/pgrestore-args" "pg_restore nicht aufgerufen"
testumgebung_loeschen

szenario "db: scheitert pg_restore, werden Backend/Worker wieder gestartet"
testumgebung_anlegen
lauf "$REPO/scripts/backup.sh"
S="$(neuester_stamp "$BD")"
LAUF_ENV=(STUB_PGRESTORE_FAIL=1)
lauf "$REPO/scripts/restore.sh" db "$BD/db-$S.dump" --ja
assert_rc 1 "pg_restore scheitert"
assert_enthaelt "$OUT" "unveraendert" "Meldung: Datenbank unveraendert (single-transaction)"
assert_enthaelt "$T/stub.log" "compose start backend worker" "Dienste wieder gestartet"
testumgebung_loeschen

szenario "db: Altformat db-*.sql.gz wird korrekt (Schema neu, ON_ERROR_STOP, eine Transaktion) eingespielt"
testumgebung_anlegen
printf 'CREATE TABLE t (id int);\nINSERT INTO t VALUES (1);\n' | gzip >"$BD/db-20200101-000000.sql.gz"
lauf "$REPO/scripts/restore.sh" db "$BD/db-20200101-000000.sql.gz" --ja
assert_rc 0 "Altformat"
assert_enthaelt "$T/psql-args" "ON_ERROR_STOP=1" "ON_ERROR_STOP"
assert_enthaelt "$T/psql-args" "--single-transaction" "eine Transaktion"
assert_eq "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" "$(head -n 1 "$T/psql-stdin.bin")" "Schema wird vorher neu angelegt"
assert_enthaelt "$T/psql-stdin.bin" "INSERT INTO t VALUES (1);" "Inhalt des Altformats"
assert_enthaelt "$OUT" "Kein Manifest" "Hinweis: keine Pruefsumme beim Altformat"
testumgebung_loeschen

# --- Pruefsumme ------------------------------------------------------------------------------------------
szenario "(i) manipulierte Datei: restore bricht vor jeder Aenderung ab"
testumgebung_anlegen
lauf "$REPO/scripts/backup.sh"
S="$(neuester_stamp "$BD")"
printf 'manipuliert' >>"$BD/db-$S.dump"
lauf "$REPO/scripts/restore.sh" db "$BD/db-$S.dump" --ja
assert_rc 1 "restore mit manipuliertem Dump"
assert_enthaelt "$OUT" "Groesse stimmt nicht" "Abweichung erkannt"
assert_keine_datei "$T/pgrestore-args" "pg_restore nicht aufgerufen"
assert_enthaelt_nicht "$T/stub.log" "compose stop backend" "Dienste nicht gestoppt"
# gleiche Groesse, anderer Inhalt -> SHA-256
cp "$BD/minio-$S.tar.gz" "$T/minio-orig"
printf 'X' | dd of="$BD/minio-$S.tar.gz" bs=1 seek=10 conv=notrunc 2>/dev/null
lauf "$REPO/scripts/restore.sh" minio "$BD/minio-$S.tar.gz" --ja
assert_rc 1 "restore mit veraendertem MinIO-Archiv"
assert_enthaelt "$OUT" "Pruefsumme stimmt nicht" "SHA-256-Abweichung erkannt"
assert_enthaelt_nicht "$T/stub.log" "compose stop minio" "MinIO nicht gestoppt"
testumgebung_loeschen

# --- minio -------------------------------------------------------------------------------------------------
szenario "minio: Archiv wird eingespielt (inkl. versteckter Eintraege leeren)"
testumgebung_anlegen
lauf "$REPO/scripts/backup.sh"
S="$(neuester_stamp "$BD")"
lauf "$REPO/scripts/restore.sh" minio "$BD/minio-$S.tar.gz" --ja
assert_rc 0 "restore minio"
assert_enthaelt "$T/stub.log" "compose stop minio" "MinIO gestoppt"
assert_enthaelt "$T/stub.log" "find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} +" "auch .minio.sys wird geleert"
assert_enthaelt "$T/stub.log" "compose start minio" "MinIO wieder gestartet"
if cmp -s "$BD/minio-$S.tar.gz" "$T/minio-restore-quelle.tar.gz"; then _fv_ok; else _fv_schlecht "falsches Archiv eingespielt"; fi
assert_enthaelt "$OUT" "MINIO_KMS_SECRET_KEY" "Hinweis auf den KMS-Schluessel"
testumgebung_loeschen

# --- secrets -----------------------------------------------------------------------------------------------
szenario "secrets: schreibt .env.wiederhergestellt und laesst die vorhandene .env unberuehrt"
testumgebung_anlegen
lauf "$REPO/scripts/backup.sh"
S="$(neuester_stamp "$BD")"
cp "$REPO/.env" "$T/env-orig"
echo "NEU=1" >>"$REPO/.env"
lauf "$REPO/scripts/restore.sh" secrets "$BD/secrets-$S.tar"
assert_rc 0 "restore secrets"
assert_eq "$(cat "$T/env-orig")" "$(cat "$REPO/.env.wiederhergestellt")" "wiederhergestellte .env = gesicherte .env"
assert_enthaelt "$REPO/.env" "NEU=1" "vorhandene .env unveraendert"
assert_eq "600" "$(stat -c %a "$REPO/.env.wiederhergestellt")" "Rechte 0600"
assert_enthaelt "$OUT" "cp .env.wiederhergestellt .env" "Anleitung zur Uebernahme"
rm -f "$REPO/.env"
lauf "$REPO/scripts/restore.sh" secrets "$BD/secrets-$S.tar"
assert_rc 0 "restore secrets auf einem Server ohne .env"
testumgebung_loeschen

szenario "secrets: ein Satz ohne GPG enthaelt kein Secrets-Buendel auf dem Ziel"
testumgebung_anlegen
env_schreiben "BACKUP_TARGETS=local:$T/ziel"
lauf "$REPO/scripts/backup.sh"
S="$(neuester_stamp "$BD")"
lauf "$REPO/scripts/restore.sh" secrets --von "local:$T/ziel" --stamp "$S"
assert_rc 1 "secrets von einem Ziel ohne Buendel"
assert_enthaelt "$OUT" "Secrets-Buendel" "Meldung nennt das Secrets-Buendel"
assert_keine_datei "$REPO/.env.wiederhergestellt" "keine Datei geschrieben"
testumgebung_loeschen

# --- mit GPG ---------------------------------------------------------------------------------------------------
szenario "GPG: verschluesselter Satz von einem Ziel (rclone) wiederherstellen"
if gpg_verfuegbar; then
  testumgebung_anlegen
  GNUPGHOME="$FV_GNUPGHOME"
  env_schreiben "BACKUP_GPG_RECIPIENT=$FV_GPG_EMPFAENGER" "BACKUP_TARGETS=rclone:fake:bucket/g"
  lauf "$REPO/scripts/backup.sh"
  assert_rc 0 "verschluesselter Lauf"
  S="$(neuester_stamp "$BD")"
  lauf "$REPO/scripts/restore.sh" liste
  assert_regex "$OUT" "^== lokal" "liste: lokal"
  assert_regex "$OUT" "^== rclone:fake:bucket/g" "liste: Ziel"
  assert_enthaelt "$OUT" "  $S" "liste: Stamp"
  lauf "$REPO/scripts/restore.sh" db --von rclone:fake:bucket/g --ja
  assert_rc 0 "db --von rclone (neuester Satz)"
  assert_eq "$(printf 'PGDMP\nfake-dump-inhalt\n' | sha256sum)" "$(sha256sum <"$T/pgrestore-stdin.bin")" "entschluesselter Dump wurde eingespielt"
  lauf "$REPO/scripts/restore.sh" minio --von rclone:fake:bucket/g --stamp "$S" --ja
  assert_rc 0 "minio --von rclone"
  rm -f "$REPO/.env.wiederhergestellt"
  lauf "$REPO/scripts/restore.sh" secrets --von rclone:fake:bucket/g --stamp "$S"
  assert_rc 0 "secrets --von rclone"
  assert_eq "$(cat "$REPO/.env")" "$(cat "$REPO/.env.wiederhergestellt")" "Secrets aus dem Remote-Satz"
  # manipuliert auf dem Ziel
  printf 'X' | dd of="$T/rclone-root/bucket/g/db-$S.dump.gpg" bs=1 seek=20 conv=notrunc 2>/dev/null
  rm -f "$T/pgrestore-args"
  lauf "$REPO/scripts/restore.sh" db --von rclone:fake:bucket/g --stamp "$S" --ja
  assert_rc 1 "manipulierter Satz auf dem Ziel"
  assert_keine_datei "$T/pgrestore-args" "pg_restore nicht aufgerufen"
  # ohne privaten Schluessel
  lauf "$REPO/scripts/backup.sh"
  S2="$(neuester_stamp "$BD")"
  GNUPGHOME="$FV_GNUPGHOME_NURPUB"
  : >"$T/stub.log"
  lauf "$REPO/scripts/restore.sh" db "$BD/db-$S2.dump.gpg" --ja
  assert_rc 1 "ohne privaten Schluessel"
  assert_enthaelt "$OUT" "privaten GPG-Schluessel" "klare Meldung zum Schluessel"
  assert_enthaelt_nicht "$T/stub.log" "compose stop backend" "Dienste nicht angefasst"
  unset GNUPGHOME
  testumgebung_loeschen
else
  skip "gpg nicht verfuegbar"
fi

# --- liste -----------------------------------------------------------------------------------------------------
szenario "liste: zeigt lokale Saetze und je Ziel; ein kaputtes Ziel macht Exit 1"
testumgebung_anlegen
env_schreiben "BACKUP_TARGETS=\"local:$T/ziel rclone:fake:bucket/y\"" "BACKUP_ERLAUBE_UNVERSCHLUESSELT_REMOTE=1"
lauf "$REPO/scripts/backup.sh"
S="$(neuester_stamp "$BD")"
lauf "$REPO/scripts/restore.sh" liste
assert_rc 0 "liste"
assert_enthaelt "$OUT" "== local:$T/ziel ==" "Ziel local"
assert_enthaelt "$OUT" "== rclone:fake:bucket/y ==" "Ziel rclone"
assert_eq "3" "$(grep -c "  $S" "$OUT")" "Stamp lokal und in beiden Zielen"
LAUF_ENV=(STUB_RCLONE_FAIL=1)
lauf "$REPO/scripts/restore.sh" liste
assert_rc 1 "liste mit kaputtem Ziel"
assert_enthaelt "$OUT" "Auflisten fehlgeschlagen" "Fehler wird angezeigt"
LAUF_ENV=()
lauf "$REPO/scripts/restore.sh" db --von "local:$T/ziel" --stamp 20000101-000000 --ja
assert_rc 1 "unbekannter Stamp"
lauf "$REPO/scripts/restore.sh" bogus
assert_rc 1 "unbekannter Modus"
testumgebung_loeschen

szenario "neuester Satz bei mehreren Staenden, --stamp waehlt gezielt"
testumgebung_anlegen
env_schreiben "BACKUP_TARGETS=local:$T/ziel"
LAUF_ENV=(STUB_DUMP_INHALT=alt)
lauf "$REPO/scripts/backup.sh"
S1="$(neuester_stamp "$BD")"
LAUF_ENV=(STUB_DUMP_INHALT=neu)
lauf "$REPO/scripts/backup.sh"
LAUF_ENV=()
lauf "$REPO/scripts/restore.sh" db --von "local:$T/ziel" --ja
assert_enthaelt "$T/pgrestore-stdin.bin" "neu" "ohne --stamp der neueste Satz"
lauf "$REPO/scripts/restore.sh" db --von "local:$T/ziel" --stamp "$S1" --ja
assert_enthaelt "$T/pgrestore-stdin.bin" "alt" "--stamp waehlt den aelteren Satz"
testumgebung_loeschen

test_ende
