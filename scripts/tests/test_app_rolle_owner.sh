#!/usr/bin/env bash
set -euo pipefail

# Tests fuer die getrennte Owner-Rolle (Standard) in scripts/app_rolle_einrichten.sh
# und scripts/migrieren.sh. docker/psql sind gestubbt (Stub aus helfer.sh): geprueft
# werden Argument-/Dateilogik und dass der Owner-Zugang nie in .env landet. Das SQL
# selbst laeuft erst in test_db_owner_echt.sh gegen ein echtes Postgres.

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

szenario "Standard (ohne Option, ohne Marker): Owner-Zugang nur in .env.migration (0600), SQL bekommt owner_rolle, Marker und Strikt-Schalter an"
umgebung
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --compose "docker compose"
assert_rc 0 "Lauf mit Owner"
assert_datei "$REPO/.env.migration" "Owner-Datei angelegt"
assert_eq "600" "$(stat -c %a "$REPO/.env.migration")" "Dateirechte 0600"
assert_regex "$REPO/.env.migration" '^APP_DB_OWNER_USER=fieldvibe_owner$' "Standard-Owner-Name"
assert_regex "$REPO/.env.migration" '^DATABASE_URL_SYNC=postgresql\+psycopg2://fieldvibe_owner:[0-9a-f]{48}@postgres:5432/fieldvibe$' "Owner-URL"
OWNER_PW="$(grep '^APP_DB_OWNER_PASSWORD=' "$REPO/.env.migration" | cut -d= -f2)"
assert_enthaelt_nicht "$REPO/.env" "$OWNER_PW" "Owner-Passwort steht nicht in .env (env_file von Backend/Worker)"
assert_enthaelt_nicht "$REPO/.env" "fieldvibe_owner" "Owner-Name steht nicht in .env"
assert_enthaelt "$REPO/.env" "FIELDVIBE_DB_BESITZ_VERBOTEN=1" "Start verweigert kuenftig App-Rolle mit Tabellenbesitz"
assert_enthaelt "$REPO/.env" "DB_GETRENNTER_OWNER=1" "Marker gesetzt"
assert_enthaelt "$T/psql-stdin.bin" "\\set owner_rolle fieldvibe_owner" "SQL erhaelt die Owner-Rolle"
assert_enthaelt_nicht "$OUT" "$OWNER_PW" "Owner-Passwort nicht in der Ausgabe"
assert_enthaelt_nicht "$OUT" "Owner-Zugang fehlte" "erste Umstellung ist keine Selbstheilung"
VORHER="$(cat "$REPO/.env.migration")"
ENV_VORHER="$(cat "$REPO/.env")"
ANZ_VORHER="$(find "$REPO" -maxdepth 1 -name '.env.vor-app-rolle.*' | wc -l)"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --compose "docker compose"
assert_rc 0 "zweiter Lauf"
assert_eq "$VORHER" "$(cat "$REPO/.env.migration")" "zweiter Lauf behaelt das Owner-Passwort"
assert_eq "$ENV_VORHER" "$(cat "$REPO/.env")" "zweiter Lauf laesst .env unveraendert"
assert_eq "$ANZ_VORHER" "$(find "$REPO" -maxdepth 1 -name '.env.vor-app-rolle.*' | wc -l)" "zweiter Lauf legt keine weitere .env-Sicherung an"
testumgebung_loeschen

szenario "--getrennter-owner erzwingt den Owner-Modus auch bei DB_GETRENNTER_OWNER=0; beide Optionen zusammen sind ein Fehler"
umgebung
env_schreiben "APP_DB_USER=fieldvibe_app" "APP_DB_PASSWORD=changeme" "DB_GETRENNTER_OWNER=0"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --getrennter-owner --compose "docker compose"
assert_rc 0 "erzwungener Owner"
assert_datei "$REPO/.env.migration" "Owner-Datei"
assert_enthaelt "$REPO/.env" "DB_GETRENNTER_OWNER=1" "Marker auf 1"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --getrennter-owner --ohne-getrennten-owner --compose "docker compose"
assert_rc_nicht0 "widerspruechliche Optionen"
testumgebung_loeschen

szenario "DB_GETRENNTER_OWNER=0: kein Owner, keine .env.migration, kein owner_rolle im SQL, Warnung"
umgebung
env_schreiben "APP_DB_USER=fieldvibe_app" "APP_DB_PASSWORD=changeme" "DB_GETRENNTER_OWNER=0"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --compose "docker compose"
assert_rc 0 "Lauf ohne Owner"
assert_keine_datei "$REPO/.env.migration" "keine Owner-Datei"
assert_enthaelt_nicht "$T/psql-stdin.bin" "\\set owner_rolle fieldvibe" "SQL ohne gesetzte Owner-Variable"
assert_enthaelt_nicht "$REPO/.env" "FIELDVIBE_DB_BESITZ_VERBOTEN" "Strikt-Schalter bleibt aus"
assert_enthaelt "$REPO/.env" "DB_GETRENNTER_OWNER=0" "Marker bleibt 0"
assert_enthaelt "$OUT" "abgeschaltet" "Warnung im Output"
testumgebung_loeschen

szenario "Abschalten auf umgestellter Installation (DB_GETRENNTER_OWNER=0 bzw. --ohne-getrennten-owner): Datei verschoben, Strikt-Schalter 0, laute Warnung"
umgebung
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --compose "docker compose"
OWNER_PW="$(grep '^APP_DB_OWNER_PASSWORD=' "$REPO/.env.migration" | cut -d= -f2)"
sed -i 's/^DB_GETRENNTER_OWNER=1$/DB_GETRENNTER_OWNER=0/' "$REPO/.env"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --compose "docker compose"
assert_rc 0 "Abschalten per Marker"
assert_keine_datei "$REPO/.env.migration" "Owner-Datei verschoben"
ARCH="$(find "$REPO" -maxdepth 1 -name '.env.migration.deaktiviert-*' | head -n1)"
assert_datei "$ARCH" "archivierte Owner-Datei"
assert_eq "600" "$(stat -c %a "$ARCH")" "Archiv mit 0600"
assert_enthaelt "$ARCH" "$OWNER_PW" "Archiv enthaelt den alten Zugang"
assert_enthaelt "$REPO/.env" "FIELDVIBE_DB_BESITZ_VERBOTEN=0" "Strikt-Schalter aus"
assert_enthaelt "$REPO/.env" "DB_GETRENNTER_OWNER=0" "Marker bleibt 0"
assert_enthaelt_nicht "$T/psql-stdin.bin" "\\set owner_rolle fieldvibe" "SQL ohne Owner (Eigentum zurueck an die App-Rolle)"
assert_enthaelt "$OUT" "ABGESCHALTET" "laute Warnung"
assert_enthaelt "$OUT" "Row-Level-Security" "Warnung nennt das Risiko"
assert_enthaelt_nicht "$OUT" "$OWNER_PW" "Owner-Passwort nicht in der Ausgabe"
# migrieren.sh laeuft danach wieder als App-Rolle
lauf "$REPO/scripts/migrieren.sh" --compose "docker compose"
assert_rc 0 "migrieren nach Abschalten"
assert_enthaelt "$OUT" "Migriere als App-Rolle fieldvibe_app" "Rolle geloggt"
# Wieder einschalten: Marker-Zeile entfernen = Standard
sed -i '/^DB_GETRENNTER_OWNER=/d' "$REPO/.env"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --compose "docker compose"
assert_rc 0 "Wieder einschalten"
assert_datei "$REPO/.env.migration" "neue Owner-Datei"
assert_enthaelt "$REPO/.env" "FIELDVIBE_DB_BESITZ_VERBOTEN=1" "Strikt-Schalter wieder an"
testumgebung_loeschen

umgebung
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --compose "docker compose"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --ohne-getrennten-owner --compose "docker compose"
assert_rc 0 "Abschalten per Option"
assert_keine_datei "$REPO/.env.migration" "Owner-Datei verschoben"
assert_enthaelt "$REPO/.env" "DB_GETRENNTER_OWNER=0" "Marker persistent auf 0"
assert_enthaelt "$REPO/.env" "FIELDVIBE_DB_BESITZ_VERBOTEN=0" "Strikt-Schalter aus"
testumgebung_loeschen

szenario "Marker ohne .env.migration: --nur-rolle legt den Zugang neu an (Warnung), migrieren.sh/--nur-besitz brechen klar ab"
umgebung
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --compose "docker compose"
mv "$REPO/.env.migration" "$T/migration-weg"
: >"$T/stub.log"
lauf "$REPO/scripts/migrieren.sh" --compose "docker compose"
assert_rc_nicht0 "migrieren.sh ohne Owner-Zugang"
assert_enthaelt "$OUT" ".env.migration fehlt" "klare Meldung"
assert_enthaelt "$OUT" "app_rolle_einrichten.sh --nur-rolle" "Hinweis auf Neuanlage"
assert_enthaelt_nicht "$T/stub.log" "alembic" "alembic wurde nicht aufgerufen"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-besitz --compose "docker compose"
assert_rc_nicht0 "--nur-besitz ohne Owner-Zugang"
assert_enthaelt "$OUT" ".env.migration fehlt" "klare Meldung"
mv "$T/migration-weg" "$REPO/.env.migration"
mv "$REPO/.env.migration" "$T/migration-weg"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --compose "docker compose"
assert_rc 0 "Selbstheilung"
assert_datei "$REPO/.env.migration" "Owner-Zugang neu angelegt"
assert_eq "600" "$(stat -c %a "$REPO/.env.migration")" "mit 0600"
assert_enthaelt "$OUT" "Owner-Zugang fehlte" "deutliche Warnung"
assert_eq "1" "$([[ "$(grep '^APP_DB_OWNER_PASSWORD=' "$REPO/.env.migration" | cut -d= -f2)" != "$(grep '^APP_DB_OWNER_PASSWORD=' "$T/migration-weg" | cut -d= -f2)" ]] && echo 1 || echo 0)" "neues Passwort"
testumgebung_loeschen

szenario "--nur-besitz: keine Passwoerter, keine .env-Aenderung, kein Backup, kein Neustart; Datenbank waehlbar"
umgebung
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --compose "docker compose"
ENV_VORHER="$(cat "$REPO/.env")"
MIGR_VORHER="$(cat "$REPO/.env.migration")"
: >"$T/stub.log"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-besitz --datenbank restore_test_x --compose "docker compose"
assert_rc 0 "nur-besitz"
assert_enthaelt "$T/psql-stdin.bin" "\\set nur_besitz 1" "Modus nur_besitz"
assert_enthaelt "$T/psql-stdin.bin" "\\set db_name restore_test_x" "gewaehlte Datenbank"
assert_enthaelt "$T/psql-args" "-d restore_test_x" "psql gegen die gewaehlte Datenbank"
assert_enthaelt "$T/psql-stdin.bin" "\\set owner_rolle fieldvibe_owner" "Owner-Rolle uebergeben"
if grep -qE '^\\set (app|owner|system)_passwort [^ ]' "$T/psql-stdin.bin"; then _fv_schlecht "Passwoerter im Besitz-SQL"; else _fv_ok; fi
assert_eq "$ENV_VORHER" "$(cat "$REPO/.env")" ".env unveraendert"
assert_eq "$MIGR_VORHER" "$(cat "$REPO/.env.migration")" ".env.migration unveraendert"
assert_enthaelt_nicht "$T/stub.log" "compose up" "kein Neustart"
assert_enthaelt_nicht "$T/stub.log" "compose stop" "kein Stopp"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-besitz --datenbank "bad;name" --compose "docker compose"
assert_rc_nicht0 "ungueltiger Datenbankname"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-besitz --nur-rolle --compose "docker compose"
assert_rc_nicht0 "nur-besitz mit nur-rolle"
testumgebung_loeschen

szenario "SQL-Schritt wird bis zu dreimal versucht (Deadlock bei der ersten Umstellung)"
umgebung
LAUF_ENV=(STUB_SQL_FAIL_ANZAHL=2 APP_ROLLE_SQL_PAUSE=0)
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --compose "docker compose"
assert_rc 0 "dritter Versuch klappt"
assert_eq "3" "$(cat "$T/sql-versuche")" "drei Versuche"
assert_enthaelt "$OUT" "Versuch 1/3" "Wiederholung angekuendigt"
testumgebung_loeschen
umgebung
LAUF_ENV=(STUB_SQL_FAIL_ANZAHL=3 APP_ROLLE_SQL_PAUSE=0)
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --compose "docker compose"
assert_rc_nicht0 "auch der dritte Versuch scheitert"
assert_eq "3" "$(cat "$T/sql-versuche")" "genau drei Versuche"
assert_enthaelt_nicht "$REPO/.env" "DATABASE_URL_SYSTEM" ".env bleibt bei Fehlschlag unveraendert"
LAUF_ENV=()
testumgebung_loeschen

szenario "System-Rolle: Passwort erzeugt, DATABASE_URL_SYSTEM (asyncpg) in .env, SQL bekommt system_rolle, Passwort maskiert"
umgebung
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --compose "docker compose"
assert_rc 0 "Lauf mit System-Rolle"
assert_regex "$REPO/.env" '^APP_DB_SYSTEM_USER=fieldvibe_system$' "Standard-Name der System-Rolle"
assert_regex "$REPO/.env" '^APP_DB_SYSTEM_PASSWORD=[0-9a-f]{48}$' "System-Passwort erzeugt"
assert_regex "$REPO/.env" '^DATABASE_URL_SYSTEM=postgresql\+asyncpg://fieldvibe_system:[0-9a-f]{48}@postgres:5432/fieldvibe$' "System-URL"
SYS_PW="$(grep '^APP_DB_SYSTEM_PASSWORD=' "$REPO/.env" | cut -d= -f2)"
APP_PW="$(grep '^APP_DB_PASSWORD=' "$REPO/.env" | cut -d= -f2)"
assert_eq "1" "$([[ "$SYS_PW" != "$APP_PW" ]] && echo 1 || echo 0)" "System- und App-Passwort verschieden"
assert_enthaelt "$T/psql-stdin.bin" "\\set system_rolle fieldvibe_system" "SQL erhaelt die System-Rolle"
assert_enthaelt_nicht "$OUT" "$SYS_PW" "System-Passwort nicht in der Ausgabe"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --compose "docker compose"
assert_enthaelt "$REPO/.env" "APP_DB_SYSTEM_PASSWORD=$SYS_PW" "zweiter Lauf behaelt das System-Passwort"
testumgebung_loeschen

szenario "System-Rolle gleich App-Rolle wird abgelehnt; --dry-run nennt die System-Rolle"
umgebung
env_schreiben "APP_DB_USER=fieldvibe_app" "APP_DB_PASSWORD=changeme" "APP_DB_SYSTEM_USER=fieldvibe_app"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --compose "docker compose"
assert_rc_nicht0 "gleicher Name"
env_schreiben "APP_DB_USER=fieldvibe_app" "APP_DB_PASSWORD=changeme"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --dry-run --compose "docker compose"
assert_rc 0 "Trockenlauf"
assert_enthaelt "$OUT" "System-Rolle:     fieldvibe_system" "Trockenlauf nennt die System-Rolle"
assert_enthaelt "$OUT" "BYPASSRLS" "Trockenlauf beschreibt die Rolle"
assert_enthaelt_nicht "$REPO/.env" "DATABASE_URL_SYSTEM" "Trockenlauf aendert .env nicht"
testumgebung_loeschen

szenario "Owner-Name gleich App-Rolle wird abgelehnt"
umgebung
printf 'APP_DB_OWNER_USER=fieldvibe_app\n' >"$REPO/.env.migration"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle --getrennter-owner --compose "docker compose"
assert_rc_nicht0 "gleicher Name"
testumgebung_loeschen

szenario "migrieren.sh: ohne .env.migration (und ohne Marker) App-Zugang, mit Datei Owner-URL per -e; Rolle wird geloggt, Rechte 600 erzwungen"
umgebung
lauf "$REPO/scripts/migrieren.sh" --compose "docker compose"
assert_rc 0 "ohne Owner"
assert_enthaelt "$T/stub.log" "docker compose run --rm backend alembic upgrade head" "App-Zugang"
: >"$T/stub.log"
printf 'DATABASE_URL_SYNC=postgresql+psycopg2://o:geheim123@postgres:5432/x\n' >"$REPO/.env.migration"
chmod 644 "$REPO/.env.migration"
lauf "$REPO/scripts/migrieren.sh" --compose "docker compose"
assert_rc 0 "mit Owner"
assert_enthaelt "$T/stub.log" "docker compose run --rm -e DATABASE_URL_SYNC backend alembic upgrade head" "Owner-Zugang per -e ohne Wert"
assert_enthaelt_nicht "$T/stub.log" "geheim123" "Passwort nicht in den Argumenten"
assert_enthaelt "$OUT" "Migriere als Owner-Rolle o " "Rollenname geloggt"
assert_enthaelt_nicht "$OUT" "geheim123" "Passwort nicht in der Ausgabe"
assert_eq "600" "$(stat -c %a "$REPO/.env.migration")" "Rechte auf 600 gesetzt"
assert_enthaelt "$OUT" "600" "Warnung zu den Rechten"
testumgebung_loeschen

test_ende
