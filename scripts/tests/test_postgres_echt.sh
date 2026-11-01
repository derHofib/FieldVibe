#!/usr/bin/env bash
set -euo pipefail

# Test gegen einen ECHTEN lokalen Postgres: pg_dump -Fc -> pg_restore (Wegwerf-DB
# und Wiederherstellen in die Test-DB). Ein docker-Shim leitet
# "docker compose exec -T postgres <befehl>" auf den lokalen Server um (Rolle und
# Passwort fieldvibe, localhost). Angefasst werden NUR die Datenbanken
# fieldvibe_t_backup und restore_test_*. Ohne erreichbaren Postgres: SKIP.

# shellcheck source=scripts/tests/helfer.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/helfer.sh"

echo "test_postgres_echt.sh"

TESTDB="fieldvibe_t_backup"
export PGHOST=localhost PGPASSWORD=fieldvibe PGUSER=fieldvibe

pg_bereit() {
  command -v psql >/dev/null 2>&1 && command -v pg_dump >/dev/null 2>&1 && command -v pg_restore >/dev/null 2>&1 \
    && command -v createdb >/dev/null 2>&1 && psql -d postgres -Atc 'SELECT 1' >/dev/null 2>&1
}

sql() { psql -d "$TESTDB" -Atq -v ON_ERROR_STOP=1 -c "$1"; }

testdb_neu() {
  dropdb --if-exists "$TESTDB" 2>/dev/null
  createdb "$TESTDB"
  psql -d "$TESTDB" -q -v ON_ERROR_STOP=1 <<'SQL'
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY);
INSERT INTO alembic_version VALUES ('0099_test');
CREATE TABLE mandanten (id serial PRIMARY KEY, name text NOT NULL);
CREATE TABLE users (id serial PRIMARY KEY, mandant_id int REFERENCES mandanten(id), email text,
                    geheim bytea DEFAULT pgp_sym_encrypt('x', 'k'));
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY users_alle ON users USING (true);
INSERT INTO mandanten (name) VALUES ('a'), ('b'), ('c');
INSERT INTO users (mandant_id, email) SELECT 1 + (g % 3), 'u' || g || '@example.de' FROM generate_series(1, 5) g;
SQL
}

stand() { printf '%s/%s/%s' "$(sql 'SELECT count(*) FROM mandanten')" "$(sql 'SELECT count(*) FROM users')" "$(sql 'SELECT version_num FROM alembic_version')"; }
restore_test_dbs() { psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'restore\_test\_%'"; }

aufraeumen() {
  dropdb --if-exists "$TESTDB" >/dev/null 2>&1 || true
  testumgebung_loeschen
}

shim_anlegen() {
  mv "$BIN/docker" "$BIN/docker-basis"
  cat >"$BIN/docker" <<'SHIM'
#!/usr/bin/env bash
# docker-Shim: "compose exec -T postgres <befehl>" laeuft gegen den lokalen Postgres.
echo "docker $*" >>"$FV_STUB_LOG"
if [[ "$1" == "compose" && "$2" == "exec" ]]; then
  shift 2
  [[ "$1" == "-T" ]] && shift
  shift # Dienstname
  export PGHOST=localhost PGPASSWORD=fieldvibe
  exec "$@"
fi
exec "$(dirname "$0")/docker-basis" "$@"
SHIM
  chmod +x "$BIN/docker"
}

if ! pg_bereit; then
  szenario "Echter Postgres: pg_dump -Fc -> pg_restore"
  skip "kein lokaler Postgres erreichbar (localhost, Rolle/Passwort fieldvibe) oder psql/pg_dump fehlen"
  test_ende
  exit 0
fi

trap aufraeumen EXIT

szenario "echter Postgres: Backup -> Test-Restore (Wegwerf-DB) -> Wiederherstellen"
testumgebung_anlegen
shim_anlegen
testdb_neu
env_schreiben "POSTGRES_DB=$TESTDB"
VORHER="$(stand)"
assert_eq "3/5/0099_test" "$VORHER" "Ausgangsbestand der Test-DB"

lauf "$REPO/scripts/backup.sh"
assert_rc 0 "backup.sh mit echtem pg_dump"
S="$(neuester_stamp "$BD")"
if pg_restore -l "$BD/db-$S.dump" >/dev/null 2>&1; then _fv_ok; else _fv_schlecht "Dump ist kein gueltiges Custom-Format-Archiv"; fi
assert_regex "$BD/manifest-$S.json" '"postgres_version": "16\.' "echte Postgres-Version im Manifest"

lauf "$REPO/scripts/backup-pruefen.sh"
assert_rc 0 "backup-pruefen.sh (Test-Restore in Wegwerf-DB)"
assert_enthaelt "$OUT" "mandanten=3 Zeilen, users=5 Zeilen" "Zeilenanzahl aus der Wegwerf-DB"
assert_enthaelt "$OUT" "alembic_version=0099_test" "alembic-Version aus der Wegwerf-DB"
assert_eq "" "$(restore_test_dbs)" "Wegwerf-DB wurde geloescht"
assert_eq "$VORHER" "$(stand)" "Test-DB durch den Test-Restore unveraendert"

# Datenbank veraendern, dann wiederherstellen
sql "DELETE FROM users"
sql "INSERT INTO mandanten (name) VALUES ('zusaetzlich')"
sql "UPDATE alembic_version SET version_num = '0100_neu'"
assert_eq "4/0/0100_neu" "$(stand)" "Test-DB wurde veraendert"
lauf "$REPO/scripts/restore.sh" db "$BD/db-$S.dump" --ja --ohne-eigentuemer
assert_rc 0 "restore.sh db mit echtem pg_restore --clean"
assert_eq "$VORHER" "$(stand)" "Zeilenanzahl und alembic_version nach der Wiederherstellung wie vor dem Backup"
assert_eq "t" "$(sql "SELECT relrowsecurity FROM pg_class WHERE relname = 'users'")" "RLS (ENABLE) nach Restore erhalten"
assert_eq "1" "$(sql "SELECT count(*) FROM pg_policies WHERE tablename = 'users'")" "RLS-Policy nach Restore vorhanden"
# Zweite Wiederherstellung hintereinander (idempotent)
lauf "$REPO/scripts/restore.sh" db "$BD/db-$S.dump" --ja --ohne-eigentuemer
assert_rc 0 "zweites Wiederherstellen"
assert_eq "$VORHER" "$(stand)" "Bestand nach zweitem Restore"

# manipulierter Dump -> Pruefsumme schlaegt an, DB bleibt unberuehrt
sql "DELETE FROM users"
printf 'X' | dd of="$BD/db-$S.dump" bs=1 seek=100 conv=notrunc 2>/dev/null
lauf "$REPO/scripts/restore.sh" db "$BD/db-$S.dump" --ja
assert_rc 1 "restore mit manipuliertem Dump"
assert_eq "3/0/0099_test" "$(stand)" "DB bei Pruefsummenfehler unveraendert (kein halbes Restore)"
lauf "$REPO/scripts/backup-pruefen.sh" --nur-pruefsummen
assert_rc 1 "backup-pruefen --nur-pruefsummen bei Manipulation"
aufraeumen

szenario "echter Postgres: Altformat (Plain-SQL, db-*.sql.gz) wird korrekt zurueckgespielt"
testumgebung_anlegen
shim_anlegen
testdb_neu
env_schreiben "POSTGRES_DB=$TESTDB"
VORHER="$(stand)"
pg_dump "$TESTDB" | gzip >"$BD/db-20200101-000000.sql.gz"
sql "DELETE FROM users"
sql "INSERT INTO mandanten (name) VALUES ('zusaetzlich')"
lauf "$REPO/scripts/restore.sh" db "$BD/db-20200101-000000.sql.gz" --ja
assert_rc 0 "restore Altformat"
assert_eq "$VORHER" "$(stand)" "Bestand nach Altformat-Restore (Schema vorher neu angelegt)"
# kaputtes Altformat: Transaktion rollt zurueck, alter Stand bleibt
sql "DELETE FROM users"
printf 'CREATE TABLE gut (id int);\nINSERT INTO gibtesnicht VALUES (1);\n' | gzip >"$BD/db-20200102-000000.sql.gz"
lauf "$REPO/scripts/restore.sh" db "$BD/db-20200102-000000.sql.gz" --ja
assert_rc 1 "fehlerhaftes SQL bricht ab (ON_ERROR_STOP)"
assert_eq "3/0/0099_test" "$(stand)" "bei Fehler bleibt die Datenbank unveraendert (single-transaction)"
aufraeumen

szenario "echter Postgres: verschluesselter Satz (GPG) -> Test-Restore"
if gpg_verfuegbar; then
  testumgebung_anlegen
  shim_anlegen
  testdb_neu
  env_schreiben "POSTGRES_DB=$TESTDB" "BACKUP_GPG_RECIPIENT=$FV_GPG_EMPFAENGER"
  GNUPGHOME="$FV_GNUPGHOME"
  lauf "$REPO/scripts/backup.sh"
  assert_rc 0 "verschluesseltes Backup"
  lauf "$REPO/scripts/backup-pruefen.sh"
  assert_rc 0 "Test-Restore des verschluesselten Satzes"
  assert_enthaelt "$OUT" "mandanten=3 Zeilen, users=5 Zeilen" "Zeilenanzahl"
  assert_eq "" "$(restore_test_dbs)" "Wegwerf-DB geloescht"
  unset GNUPGHOME
  aufraeumen
else
  skip "gpg nicht verfuegbar"
fi

test_ende
