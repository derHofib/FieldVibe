#!/usr/bin/env bash
set -euo pipefail

# Tests fuer die optionale getrennte Owner-Rolle in scripts/app_rolle_einrichten.sh
# und scripts/migrieren.sh. docker/psql sind gestubbt (Stub aus helfer.sh): geprueft
# werden Argument-/Dateilogik und dass der Owner-Zugang nie in .env landet. Das SQL
# selbst laeuft hier NICHT (siehe docs/DEPLOYMENT.md: ungetestet gegen echtes Postgres).

# shellcheck source=scripts/tests/helfer.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/helfer.sh"

echo "test_app_rolle_owner.sh"

umgebung() {
  testumgebung_anlegen
  mkdir -p "$REPO/scripts/sql"
  cp "$FV_SCRIPTS_DIR/app_rolle_einrichten.sh" "$FV_SCRIPTS_DIR/migrieren.sh" "$REPO/scripts/"
  cp "$FV_SCRIPTS_DIR/sql/app_rolle_einrichten.sql" "$REPO/scripts/sql/"
  : >"$REPO/docker-compose.yml"
  env_schreiben "APP_DB_USER=fieldvibe_app" "APP_DB_PASSWORD=changeme"
}

szenario "ohne --getrennter-owner: kein Owner, keine .env.migration, kein owner_rolle im SQL"
umgebung
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --compose "docker compose"
assert_rc 0 "Lauf ohne Owner"
assert_keine_datei "$REPO/.env.migration" "keine Owner-Datei"
assert_enthaelt_nicht "$T/psql-stdin.bin" "\\set owner_rolle fieldvibe" "SQL ohne gesetzte Owner-Variable"
assert_enthaelt_nicht "$REPO/.env" "FIELDVIBE_DB_BESITZ_VERBOTEN" "Strikt-Schalter bleibt aus"
testumgebung_loeschen

szenario "--getrennter-owner: Owner-Zugang nur in .env.migration (0600), SQL bekommt owner_rolle, Strikt-Schalter an"
umgebung
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --getrennter-owner --compose "docker compose"
assert_rc 0 "Lauf mit Owner"
assert_datei "$REPO/.env.migration" "Owner-Datei angelegt"
assert_eq "600" "$(stat -c %a "$REPO/.env.migration")" "Dateirechte 0600"
assert_regex "$REPO/.env.migration" '^APP_DB_OWNER_USER=fieldvibe_owner$' "Standard-Owner-Name"
assert_regex "$REPO/.env.migration" '^DATABASE_URL_SYNC=postgresql\+psycopg2://fieldvibe_owner:[0-9a-f]{48}@postgres:5432/fieldvibe$' "Owner-URL"
OWNER_PW="$(grep '^APP_DB_OWNER_PASSWORD=' "$REPO/.env.migration" | cut -d= -f2)"
assert_enthaelt_nicht "$REPO/.env" "$OWNER_PW" "Owner-Passwort steht nicht in .env (env_file von Backend/Worker)"
assert_enthaelt_nicht "$REPO/.env" "fieldvibe_owner" "Owner-Name steht nicht in .env"
assert_enthaelt "$REPO/.env" "FIELDVIBE_DB_BESITZ_VERBOTEN=1" "Start verweigert kuenftig App-Rolle mit Tabellenbesitz"
assert_enthaelt "$T/psql-stdin.bin" "\\set owner_rolle fieldvibe_owner" "SQL erhaelt die Owner-Rolle"
assert_enthaelt_nicht "$OUT" "$OWNER_PW" "Owner-Passwort nicht in der Ausgabe"
VORHER="$(cat "$REPO/.env.migration")"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --getrennter-owner --compose "docker compose"
assert_eq "$VORHER" "$(cat "$REPO/.env.migration")" "zweiter Lauf behaelt das Owner-Passwort"
testumgebung_loeschen

szenario "Owner-Name gleich App-Rolle wird abgelehnt"
umgebung
printf 'APP_DB_OWNER_USER=fieldvibe_app\n' >"$REPO/.env.migration"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --getrennter-owner --compose "docker compose"
assert_rc_nicht0 "gleicher Name"
testumgebung_loeschen

szenario "migrieren.sh: ohne .env.migration normaler Aufruf, mit Datei Owner-URL per -e aus der Umgebung"
umgebung
lauf "$REPO/scripts/migrieren.sh" --compose "docker compose"
assert_rc 0 "ohne Owner"
assert_enthaelt "$T/stub.log" "docker compose run --rm backend alembic upgrade head" "App-Zugang"
: >"$T/stub.log"
printf 'DATABASE_URL_SYNC=postgresql+psycopg2://o:geheim123@postgres:5432/x\n' >"$REPO/.env.migration"
lauf "$REPO/scripts/migrieren.sh" --compose "docker compose"
assert_rc 0 "mit Owner"
assert_enthaelt "$T/stub.log" "docker compose run --rm -e DATABASE_URL_SYNC backend alembic upgrade head" "Owner-Zugang per -e ohne Wert"
assert_enthaelt_nicht "$T/stub.log" "geheim123" "Passwort nicht in den Argumenten"
testumgebung_loeschen

test_ende
