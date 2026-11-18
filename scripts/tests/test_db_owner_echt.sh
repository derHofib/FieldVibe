#!/usr/bin/env bash
set -euo pipefail

# Echter Test der getrennten Datenbank-Owner-Rolle gegen ein ECHTES Postgres 16
# (lokal bzw. CI-Service, Bootstrap-Superuser fieldvibe/fieldvibe auf localhost):
# die Skripte (app_rolle_einrichten.sh, migrieren.sh, restore.sh, backup-pruefen.sh)
# laufen unveraendert, nur "docker compose" ist ein Shim, der exec/run auf den lokalen
# Postgres bzw. das lokale alembic umlenkt. Das Backend-Verzeichnis ist das echte Repo-
# backend (nur gelesen; Ausnahme: die Test-Migration 9999, die per Trap IMMER wieder
# entfernt wird). NICHT getestet: ein echter Docker-Compose-Lauf von deploy.sh.
#
# Angefasst werden nur die Datenbank fieldvibe_t_owner und die clusterweiten Rollen
# fieldvibe_app, fieldvibe_system, fieldvibe_owner (im CI frisch; lokal werden nur Rollen
# wieder geloescht, die dieser Test selbst angelegt hat).
#
# Voraussetzungen: erreichbarer Postgres + psql/pg_dump/pg_restore und ein Python mit den
# Backend-Abhaengigkeiten (FV_PYTHON_BIN = Verzeichnis mit python und alembic, sonst aus
# dem PATH). Fehlt etwas: SKIP -- mit FV_ECHT_PFLICHT=1 (CI-Job db-owner-umstellung) ist
# das ein Fehler.

# shellcheck source=scripts/tests/helfer.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/helfer.sh"

echo "test_db_owner_echt.sh"

TESTDB="fieldvibe_t_owner"
BACKEND="$(cd "$FV_SCRIPTS_DIR/../backend" && pwd)"
MIGR_DATEI="$BACKEND/alembic/versions/9999_test_owner_default_privs.py"
export PGHOST=localhost PGPASSWORD=fieldvibe PGUSER=fieldvibe
ROLLEN=(fieldvibe_app fieldvibe_system fieldvibe_owner)
ROLLEN_VORHER=()

PYBIN="${FV_PYTHON_BIN:-}"
py() { if [[ -n "$PYBIN" ]]; then "$PYBIN/python" "$@"; else python3 "$@"; fi; }
alembic_pfad() { if [[ -n "$PYBIN" ]]; then echo "$PYBIN/alembic"; else command -v alembic || true; fi; }

pg_bereit() {
  command -v psql >/dev/null 2>&1 && command -v pg_dump >/dev/null 2>&1 && command -v pg_restore >/dev/null 2>&1 \
    && command -v createdb >/dev/null 2>&1 && psql -d postgres -Atc 'SELECT 1' >/dev/null 2>&1
}
python_bereit() {
  local a
  a="$(alembic_pfad)"
  [[ -n "$a" && -x "$a" ]] || return 1
  ( cd "$BACKEND" && ENVIRONMENT=test JWT_SECRET=x PYTHONDONTWRITEBYTECODE=1 \
      py -c 'import alembic, asyncpg, psycopg2, sqlalchemy; import app.db.rollen_pruefung' ) >/dev/null 2>&1
}

# Ohne Voraussetzungen: SKIP, mit FV_ECHT_PFLICHT=1 ein Fehler.
abbruch_ohne() {
  szenario "Echter Postgres: getrennte Owner-Rolle"
  if [[ "${FV_ECHT_PFLICHT:-0}" == "1" ]]; then
    _fv_schlecht "$1 -- mit FV_ECHT_PFLICHT=1 ist das kein SKIP"
  else
    skip "$1"
  fi
  test_ende || exit 1
  exit 0
}
if ! pg_bereit; then abbruch_ohne "kein lokaler Postgres erreichbar (localhost, Rolle/Passwort fieldvibe) oder psql/pg_dump fehlen"; fi
if ! python_bereit; then abbruch_ohne "Python mit Backend-Abhaengigkeiten (alembic, asyncpg, psycopg2, sqlalchemy) nicht verfuegbar (FV_PYTHON_BIN setzen)"; fi

sql() { psql -d "$TESTDB" -Atq -v ON_ERROR_STOP=1 -c "$1"; }

for r in "${ROLLEN[@]}"; do
  if [[ "$(psql -d postgres -Atc "SELECT count(*) FROM pg_roles WHERE rolname = '$r'")" != "0" ]]; then ROLLEN_VORHER+=("$r"); fi
done

aufraeumen() {
  rm -f "$MIGR_DATEI" "$BACKEND"/alembic/versions/__pycache__/9999_test_owner_default_privs*.pyc
  dropdb --if-exists "$TESTDB" >/dev/null 2>&1 || true
  local r vorher
  for r in "${ROLLEN[@]}"; do
    vorher=0
    for v in ${ROLLEN_VORHER[@]+"${ROLLEN_VORHER[@]}"}; do [[ "$v" == "$r" ]] && vorher=1; done
    (( vorher == 1 )) || psql -d postgres -q -c "DROP ROLE IF EXISTS $r" >/dev/null 2>&1 || true
  done
  testumgebung_loeschen
}
trap aufraeumen EXIT

# --- docker-Shim -----------------------------------------------------------------------
# "compose exec -T postgres <befehl>" laeuft lokal gegen den Postgres, "compose run --rm
# [-e VAR] backend alembic ..." als lokales alembic im Repo-backend (Host "postgres" wird
# zu localhost, die verwendete Rolle landet in $FV_T/alembic-rollen.log). Alles andere
# (up/stop/start/ps/run tar ...) beantwortet der Stub aus helfer.sh.
shim_anlegen() {
  mv "$BIN/docker" "$BIN/docker-basis"
  cat >"$BIN/docker" <<'SHIM'
#!/usr/bin/env bash
echo "docker $*" >>"$FV_STUB_LOG"
basis="$(dirname "$0")/docker-basis"
[[ "${1:-}" == "compose" ]] || exec "$basis" "$@"
orig=("$@")
shift
while [[ "${1:-}" == "-f" ]]; do shift 2; done
sub="${1:-}"
shift || true
case "$sub" in
  exec)
    [[ "${1:-}" == "-T" ]] && shift
    dienst="${1:-}"; shift
    [[ "$dienst" == "postgres" ]] || exec "$basis" "${orig[@]}"
    # Passwort des per -U genannten Users: Admin = fieldvibe, sonst Zugang aus .env.
    user=fieldvibe
    args=("$@")
    for ((i = 0; i < ${#args[@]}; i++)); do [[ "${args[$i]}" == "-U" ]] && user="${args[$((i + 1))]}"; done
    pw=fieldvibe
    if [[ "$user" != "fieldvibe" ]]; then
      pw="$(grep '^APP_DB_PASSWORD=' "$FV_T/repo/.env" | head -n1 | cut -d= -f2-)"
    fi
    export PGHOST=localhost PGPASSWORD="$pw"
    exec "$@"
    ;;
  run)
    extra=()
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --rm) shift ;;
        -e) extra+=("$2"); shift 2 ;;
        *) break ;;
      esac
    done
    [[ "${1:-}" == "backend" ]] || exec "$basis" "${orig[@]}"
    shift
    [[ "${1:-}" == "alembic" ]] || { echo "docker-shim: nur 'backend alembic' wird unterstuetzt" >&2; exit 2; }
    shift
    ersetzen() { printf '%s' "${1//@postgres:/@localhost:}"; }
    env_args=()
    sync=""
    for k in DATABASE_URL DATABASE_URL_SYNC DATABASE_URL_SYSTEM; do
      v="$(grep "^$k=" "$FV_T/repo/.env" | head -n1 | cut -d= -f2- || true)"
      [[ -z "$v" ]] || env_args+=("$k=$(ersetzen "$v")")
      [[ "$k" != "DATABASE_URL_SYNC" ]] || sync="$v"
    done
    for k in ${extra[@]+"${extra[@]}"}; do
      v="${!k:-}"
      env_args+=("$k=$(ersetzen "$v")")
      [[ "$k" != "DATABASE_URL_SYNC" ]] || sync="$v"
    done
    echo "alembic-rolle=$(sed -E 's#^[^:]+://([^:@/]+).*#\1#' <<<"$sync") args=$*" >>"$FV_T/alembic-rollen.log"
    alembic="$FV_PYTHON_BIN/alembic"
    [[ -n "${FV_PYTHON_BIN:-}" ]] || alembic="$(command -v alembic)"
    cd "$FV_BACKEND_DIR"
    exec env ENVIRONMENT=test JWT_SECRET=test-only-secret PYTHONDONTWRITEBYTECODE=1 FIELDVIBE_REFRESH_BODY_BIS=2999-12-31 \
      "${env_args[@]}" "$alembic" "$@"
    ;;
  *) exec "$basis" "${orig[@]}" ;;
esac
SHIM
  chmod +x "$BIN/docker"
  # shellcheck disable=SC2034  # von lauf() in helfer.sh gelesen
  LAUF_ENV=(FV_BACKEND_DIR="$BACKEND" FV_PYTHON_BIN="$PYBIN")
}

# Wert aus der .env der Testumgebung, Host "postgres" -> localhost.
env_wert() { grep "^$1=" "$REPO/.env" | head -n1 | cut -d= -f2- | sed 's/@postgres:/@localhost:/'; }
env_roh() { grep "^$1=" "$REPO/.env" | head -n1 | cut -d= -f2- || true; }

# psql als App-/System-Rolle (Passwort aus .env), Mandant per Session-Variable.
app_sql() { # mandant-id, sql
  PGPASSWORD="$(env_roh APP_DB_PASSWORD)" psql -U fieldvibe_app -d "$TESTDB" -Atq -v ON_ERROR_STOP=1 \
    -c "SET app.current_mandant = '$1'" -c "$2"
}
system_sql() {
  PGPASSWORD="$(env_roh APP_DB_SYSTEM_PASSWORD)" psql -U fieldvibe_system -d "$TESTDB" -Atq -v ON_ERROR_STOP=1 -c "$1"
}
# Erwartet: scheitert mit "must be owner"/"permission denied".
assert_app_verboten() { # beschreibung, mandant, sql
  local out rc=0
  out="$(app_sql "$2" "$3" 2>&1)" || rc=$?
  if [[ $rc -ne 0 && "$out" =~ (must\ be\ owner|permission\ denied) ]]; then _fv_ok; else _fv_schlecht "$1 (Exit $rc, erwartet Abbruch mit 'must be owner'/'permission denied')" "$out"; fi
}

# Anzahl Objekte in public (ohne Extension-Objekte), die einer der Rollen gehoeren.
objekte_von() { # rollen als SQL-Liste, z. B. "'fieldvibe_app','fieldvibe_system'"
  sql "SELECT
    (SELECT count(*) FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r','p','v','m','S','f')
       AND pg_get_userbyid(c.relowner) IN ($1)
       AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e'))
  + (SELECT count(*) FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace AND pg_get_userbyid(p.proowner) IN ($1)
       AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid AND d.deptype = 'e'))
  + (SELECT count(*) FROM pg_type t WHERE t.typnamespace = 'public'::regnamespace AND t.typtype IN ('e','d','r')
       AND pg_get_userbyid(t.typowner) IN ($1)
       AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_type'::regclass AND d.objid = t.oid AND d.deptype = 'e'))"
}
rls_tabellen_von() { # rolle
  sql "SELECT count(*) FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind IN ('r','p') AND relrowsecurity AND pg_get_userbyid(relowner) = '$1'"
}

# Ergebniszeile von besitz_pruefen.sql (Owner leer = App-Modus); Exit != 0 bei Verstoss.
besitz_pruefen() { # [owner]
  local args=(-v app_rolle=fieldvibe_app -v system_rolle=fieldvibe_system)
  [[ -z "${1:-}" ]] || args+=(-v "owner_rolle=$1")
  psql -d "$TESTDB" -Atq -v ON_ERROR_STOP=1 "${args[@]}" -f "$FV_SCRIPTS_DIR/sql/besitz_pruefen.sql" 2>&1
}

# Snapshot aller Eigentums-/Rechte-/Rollenangaben (ohne Passwort-Hash) plus Dateien.
snapshot() {
  sql "SELECT 'rel', c.relname, c.relkind, pg_get_userbyid(c.relowner), c.relacl::text FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace ORDER BY c.relname"
  sql "SELECT 'proc', p.oid::regprocedure::text, pg_get_userbyid(p.proowner), p.proacl::text FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace ORDER BY 2"
  sql "SELECT 'typ', t.typname, pg_get_userbyid(t.typowner) FROM pg_type t WHERE t.typnamespace = 'public'::regnamespace AND t.typtype IN ('e','d','r') ORDER BY 2"
  sql "SELECT 'defacl', pg_get_userbyid(defaclrole), defaclnamespace::regnamespace::text, defaclobjtype, defaclacl::text FROM pg_default_acl ORDER BY 2, 3, 4"
  sql "SELECT 'rolle', rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb, rolcanlogin, rolreplication, rolbypassrls, rolconnlimit FROM pg_roles WHERE rolname IN ('fieldvibe_app','fieldvibe_system','fieldvibe_owner') ORDER BY 2"
  cat "$REPO/.env" "$REPO/.env.migration" 2>/dev/null || true
}

# Startpruefung der App (pruefe_db_rolle) mit echten async Engines. Ausgabe:
# "ok warnungen=<n>" bzw. "fehler <Meldung>".
startpruefung() { # besitz_verboten (0|1)
  ( cd "$BACKEND" && \
    ENVIRONMENT=test JWT_SECRET=test-only-secret PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_URL="$(env_wert DATABASE_URL)" DATABASE_URL_SYNC="$(env_wert DATABASE_URL_SYNC)" \
    DATABASE_URL_SYSTEM="$(env_wert DATABASE_URL_SYSTEM)" FIELDVIBE_DB_BESITZ_VERBOTEN="$1" \
    py -I -c '
import asyncio, logging, os, sys
sys.path.insert(0, ".")
from sqlalchemy.ext.asyncio import create_async_engine
from app.db.rollen_pruefung import UnsichereDbRolleError, pruefe_db_rolle

class Sammler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records = []
    def emit(self, record):
        self.records.append(record)

async def main():
    sammler = Sammler()
    wurzel = logging.getLogger()
    wurzel.addHandler(sammler)
    wurzel.setLevel(logging.WARNING)
    app = create_async_engine(os.environ["DATABASE_URL"])
    system = create_async_engine(os.environ["DATABASE_URL_SYSTEM"])
    try:
        await pruefe_db_rolle(app, system)
        print("ok warnungen=%d" % len(sammler.records))
        for r in sammler.records:
            print("  warnung:", r.getMessage())
    except UnsichereDbRolleError as exc:
        print("fehler", exc)
    finally:
        await app.dispose()
        await system.dispose()

asyncio.run(main())
' )
}

# ------------------------------------------------------------------------------------------

dropdb --if-exists "$TESTDB" >/dev/null 2>&1 || true
createdb "$TESTDB"

testumgebung_anlegen
shim_anlegen
: >"$T/alembic-rollen.log"
env_schreiben "POSTGRES_DB=$TESTDB" "DEPLOY_MODE=ip" "APP_DB_USER=fieldvibe_app" "APP_DB_PASSWORD=changeme" "DB_GETRENNTER_OWNER=0"
# env_schreiben legt POSTGRES_DB schon mit dem Standardwert an und get_env der Skripte
# nimmt die ERSTE Zeile: ohne Ersetzen liefen die Skripte gegen eine fremde Datenbank.
sed -i "s/^POSTGRES_DB=.*/POSTGRES_DB=$TESTDB/" "$REPO/.env"
if [[ "$(grep -c '^POSTGRES_DB=' "$REPO/.env")" != "2" && "$(grep '^POSTGRES_DB=' "$REPO/.env" | sort -u)" != "POSTGRES_DB=$TESTDB" ]]; then
  echo "Abbruch: POSTGRES_DB in der Test-.env ist nicht $TESTDB" >&2; exit 1
fi

szenario "Ausgangslage Bestandsinstallation: App-Rolle besitzt alles, Migrationen laufen als App-Rolle, Testdaten in zwei Mandanten"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle
assert_rc 0 "app_rolle_einrichten.sh --nur-rolle (Owner abgeschaltet)"
assert_keine_datei "$REPO/.env.migration" "keine Owner-Datei im Altmodus"
lauf "$REPO/scripts/migrieren.sh"
assert_rc 0 "migrieren.sh (alle Migrationen als App-Rolle)"
assert_enthaelt "$T/alembic-rollen.log" "alembic-rolle=fieldvibe_app args=upgrade head" "Migration als App-Rolle"
assert_enthaelt "$OUT" "Migriere als App-Rolle fieldvibe_app" "Rolle im Log"
HEAD_REV="$(sql 'SELECT version_num FROM alembic_version')"
assert_regex <(printf '%s\n' "$HEAD_REV") '^[0-9a-z_]+$' "alembic_version gesetzt"

sql "INSERT INTO mandanten (name, slug) VALUES ('Mandant A', 'owner-test-a'), ('Mandant B', 'owner-test-b')"
MA="$(sql "SELECT id FROM mandanten WHERE slug = 'owner-test-a'")"
MB="$(sql "SELECT id FROM mandanten WHERE slug = 'owner-test-b'")"
sql "INSERT INTO kunden (mandant_id, kundennummer, name, portal_slug)
     SELECT m.id, 'K' || g, 'Kunde ' || g, m.slug || '-' || g FROM mandanten m, generate_series(1, 3) g
     WHERE m.slug IN ('owner-test-a', 'owner-test-b')"
assert_eq "6" "$(sql 'SELECT count(*) FROM kunden')" "Testdaten: 3 Kunden je Mandant"
if [[ "$(rls_tabellen_von fieldvibe_app)" -gt 0 ]]; then _fv_ok; else _fv_schlecht "Ausgangslage: die App-Rolle besitzt RLS-Tabellen"; fi
assert_eq "0" "$(objekte_von "'fieldvibe_owner'")" "Owner-Rolle besitzt noch nichts"
assert_eq "t" "$(sql "SELECT relforcerowsecurity FROM pg_class WHERE relname = 'kunden'")" "kunden: FORCE RLS"

ERG="$(startpruefung 1)"
assert_eq "1" "$([[ "$ERG" == fehler* ]] && echo 1 || echo 0)" "Startpruefung mit FIELDVIBE_DB_BESITZ_VERBOTEN=1 lehnt die besitzende App-Rolle ab"
ERG="$(startpruefung 0)"
assert_eq "1" "$([[ "$ERG" == ok\ warnungen=1* ]] && echo 1 || echo 0)" "ohne Strikt-Schalter nur eine Warnung ($ERG)"

szenario "Umstellung auf die getrennte Owner-Rolle (Standard): Besitz, Rechte, RLS-Isolation, Idempotenz"
sed -i '/^DB_GETRENNTER_OWNER=/d' "$REPO/.env"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle
assert_rc 0 "Umstellung per --nur-rolle (Standard = Owner-Modus)"
ANZ_UMSTELLUNG_OUT="$OUT"
assert_eq "600" "$(stat -c %a "$REPO/.env.migration")" ".env.migration hat 0600"
OWNER_PW="$(grep '^APP_DB_OWNER_PASSWORD=' "$REPO/.env.migration" | cut -d= -f2)"
APP_PW="$(env_roh APP_DB_PASSWORD)"; SYS_PW="$(env_roh APP_DB_SYSTEM_PASSWORD)"
assert_enthaelt_nicht "$REPO/.env" "$OWNER_PW" "Owner-Passwort nicht in .env"
assert_enthaelt_nicht "$REPO/.env" "fieldvibe_owner" "Owner-Name nicht in .env"
assert_enthaelt "$REPO/.env" "DB_GETRENNTER_OWNER=1" "Marker gesetzt"
assert_enthaelt "$REPO/.env" "FIELDVIBE_DB_BESITZ_VERBOTEN=1" "Strikt-Schalter gesetzt"
for pw in "$OWNER_PW" "$APP_PW" "$SYS_PW"; do assert_enthaelt_nicht "$ANZ_UMSTELLUNG_OUT" "$pw" "kein Passwort in der Skriptausgabe"; done

# a) Pruef-SQL und unabhaengige Assert-Query
ERG="$(besitz_pruefen fieldvibe_owner)" && RCB=0 || RCB=$?
assert_eq "0" "$RCB" "besitz_pruefen.sql Exit-Code"
assert_regex <(printf '%s\n' "$ERG") '^ok\|fieldvibe_owner\|[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+$' "besitz_pruefen.sql: Ergebniszeile"
assert_eq "0" "$(objekte_von "'fieldvibe_app','fieldvibe_system'")" "keine Objekte in public bei App-/System-Rolle"
if [[ "$(objekte_von "'fieldvibe_owner'")" -gt 100 ]]; then _fv_ok; else _fv_schlecht "Owner besitzt die Objekte in public (gezaehlt: $(objekte_von "'fieldvibe_owner'"))"; fi

# b) DML und Grenzen der App-Rolle
assert_eq "3" "$(app_sql "$MA" 'SELECT count(*) FROM kunden')" "App-Rolle: SELECT (Mandant A)"
app_sql "$MA" "INSERT INTO kunden (mandant_id, kundennummer, name, portal_slug) VALUES ('$MA', 'K99', 'Neu', 'owner-test-a-99')" >/dev/null && _fv_ok || _fv_schlecht "App-Rolle: INSERT"
app_sql "$MA" "UPDATE kunden SET name = 'Geaendert' WHERE kundennummer = 'K99'" >/dev/null && _fv_ok || _fv_schlecht "App-Rolle: UPDATE"
app_sql "$MA" "DELETE FROM kunden WHERE kundennummer = 'K99'" >/dev/null && _fv_ok || _fv_schlecht "App-Rolle: DELETE"
SEQ="$(sql "SELECT relname FROM pg_class WHERE relkind = 'S' AND relnamespace = 'public'::regnamespace ORDER BY relname LIMIT 1")"
assert_eq "1" "$([[ -n "$SEQ" ]] && echo 1 || echo 0)" "es gibt eine Sequenz in public"
app_sql "$MA" "SELECT nextval('$SEQ')" >/dev/null && _fv_ok || _fv_schlecht "App-Rolle: nextval auf $SEQ (USAGE)"
assert_eq "6" "$(system_sql 'SELECT count(*) FROM kunden')" "System-Rolle (BYPASSRLS) sieht alle Mandanten"
assert_app_verboten "ALTER TABLE ... DISABLE ROW LEVEL SECURITY" "$MA" "ALTER TABLE kunden DISABLE ROW LEVEL SECURITY"
assert_app_verboten "ALTER TABLE ... NO FORCE ROW LEVEL SECURITY" "$MA" "ALTER TABLE kunden NO FORCE ROW LEVEL SECURITY"
assert_app_verboten "DROP POLICY" "$MA" "DROP POLICY mandant_isolation ON kunden"
assert_app_verboten "CREATE TABLE in public" "$MA" "CREATE TABLE x (i int)"

# c) RLS-Isolation
assert_eq "3" "$(app_sql "$MA" "SELECT count(*) FROM kunden WHERE mandant_id = '$MA'")" "Mandant A sieht seine Zeilen"
assert_eq "0" "$(app_sql "$MA" "SELECT count(*) FROM kunden WHERE mandant_id = '$MB'")" "Mandant A sieht keine Zeilen von B"
assert_eq "0" "$(app_sql "$MA" "WITH u AS (UPDATE kunden SET name = 'x' WHERE mandant_id = '$MB' RETURNING 1) SELECT count(*) FROM u")" "UPDATE auf B-Zeilen trifft 0 Zeilen"
assert_eq "0" "$(app_sql "$MA" "WITH d AS (DELETE FROM kunden WHERE mandant_id = '$MB' RETURNING 1) SELECT count(*) FROM d")" "DELETE auf B-Zeilen trifft 0 Zeilen"
OUT_INS="$(app_sql "$MA" "INSERT INTO kunden (mandant_id, kundennummer, name, portal_slug) VALUES ('$MB', 'K98', 'Fremd', 'owner-test-b-98')" 2>&1)" && RCI=0 || RCI=$?
if [[ $RCI -ne 0 && "$OUT_INS" == *"row-level security"* ]]; then _fv_ok; else _fv_schlecht "INSERT mit mandant_id von B scheitert an WITH CHECK (Exit $RCI)" "$OUT_INS"; fi
assert_eq "6" "$(sql 'SELECT count(*) FROM kunden')" "Daten unveraendert (3 + 3)"

# d) zweiter Lauf ist No-op
SNAP_VORHER="$(snapshot)"
ENV_BACKUPS_VORHER="$(find "$REPO" -maxdepth 1 -name '.env.vor-app-rolle.*' | wc -l)"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle
assert_rc 0 "zweiter Lauf"
assert_eq "$SNAP_VORHER" "$(snapshot)" "No-op: Eigentum, ACLs, Default-Privilegien, Rollenattribute, .env, .env.migration unveraendert"
assert_eq "$ENV_BACKUPS_VORHER" "$(find "$REPO" -maxdepth 1 -name '.env.vor-app-rolle.*' | wc -l)" "keine neue .env.vor-app-rolle.*-Datei"

# e) Test-Migration: Default-Privilegien greifen fuer neue Objekte des Owners
HEAD_NEU="$( cd "$BACKEND" && ENVIRONMENT=test JWT_SECRET=x PYTHONDONTWRITEBYTECODE=1 \
  DATABASE_URL_SYNC="$(env_wert DATABASE_URL_SYNC)" "$(alembic_pfad)" heads 2>/dev/null | awk 'NR==1 {print $1}')"
assert_eq "$HEAD_REV" "$HEAD_NEU" "alembic heads = Stand der Datenbank"
cat >"$MIGR_DATEI" <<MIGRATION
"""Nur fuer scripts/tests/test_db_owner_echt.sh: Tabelle mit serial-Spalte als Owner."""
from alembic import op

revision = "9999"
down_revision = "$HEAD_NEU"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TABLE test_owner_dp (id serial PRIMARY KEY, wert text)")


def downgrade() -> None:
    op.execute("DROP TABLE test_owner_dp")
MIGRATION
: >"$T/alembic-rollen.log"
lauf "$REPO/scripts/migrieren.sh"
assert_rc 0 "migrieren.sh mit Test-Migration (als Owner)"
assert_enthaelt "$T/alembic-rollen.log" "alembic-rolle=fieldvibe_owner args=upgrade head" "Migration lief mit der Owner-URL aus .env.migration"
assert_enthaelt_nicht "$T/alembic-rollen.log" "alembic-rolle=fieldvibe_app" "nicht als App-Rolle"
assert_enthaelt "$OUT" "Migriere als Owner-Rolle fieldvibe_owner" "Rolle im Log"
assert_eq "fieldvibe_owner" "$(sql "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE relname = 'test_owner_dp'")" "neue Tabelle gehoert dem Owner"
for r in fieldvibe_app fieldvibe_system; do
  assert_eq "t" "$(sql "SELECT bool_and(has_table_privilege('$r', 'test_owner_dp', p)) FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE']) p")" "$r: DML auf der neuen Tabelle (Default-Privilegien)"
  assert_eq "t" "$(sql "SELECT has_sequence_privilege('$r', 'test_owner_dp_id_seq', 'USAGE')")" "$r: USAGE auf der neuen Sequenz"
done
assert_eq "fieldvibe_owner" "$(sql "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE relname = 'test_owner_dp_id_seq'")" "neue Sequenz gehoert dem Owner"
lauf "$REPO/scripts/migrieren.sh" downgrade -1
assert_rc 0 "migrieren.sh downgrade -1"
assert_eq "0" "$(sql "SELECT count(*) FROM pg_class WHERE relname = 'test_owner_dp'")" "Test-Tabelle nach dem Downgrade weg"
assert_eq "$HEAD_REV" "$(sql 'SELECT version_num FROM alembic_version')" "alembic_version zurueck"
rm -f "$MIGR_DATEI" "$BACKEND"/alembic/versions/__pycache__/9999_test_owner_default_privs*.pyc

# f) Startpruefung ohne Warnung
ERG="$(startpruefung 1)"
assert_eq "ok warnungen=0" "$ERG" "Startpruefung mit FIELDVIBE_DB_BESITZ_VERBOTEN=1 laeuft ohne Warnung durch"

szenario "Fehlende .env.migration: migrieren.sh und --nur-besitz scheitern klar, alembic wird nicht aufgerufen"
mv "$REPO/.env.migration" "$T/migration-weg"
: >"$T/stub.log"; : >"$T/alembic-rollen.log"
lauf "$REPO/scripts/migrieren.sh"
assert_rc_nicht0 "migrieren.sh ohne Owner-Zugang"
assert_enthaelt "$OUT" ".env.migration fehlt" "klare Meldung"
assert_eq "" "$(cat "$T/alembic-rollen.log")" "alembic wurde nicht aufgerufen"
assert_enthaelt_nicht "$T/stub.log" "alembic" "kein alembic-Aufruf im docker-Log"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-besitz
assert_rc_nicht0 "--nur-besitz ohne Owner-Zugang"
assert_enthaelt "$OUT" ".env.migration fehlt" "klare Meldung"
lauf "$REPO/scripts/restore.sh" db "$T/gibtesnicht.dump" --ja
assert_rc_nicht0 "restore.sh ohne Quelldatei"
mv "$T/migration-weg" "$REPO/.env.migration"

szenario "Restore: backup.sh -> Daten veraendern -> restore.sh db -> Besitz/Rechte/RLS wie vorher; backup-pruefen.sh prueft den Besitz mit"
VORHER_KUNDEN="$(sql "SELECT string_agg(kundennummer || mandant_id::text, ',' ORDER BY mandant_id, kundennummer) FROM kunden")"
lauf "$REPO/scripts/backup.sh"
assert_rc 0 "backup.sh (echtes pg_dump)"
S="$(neuester_stamp "$BD")"
sql "DELETE FROM kunden WHERE mandant_id = '$MA'"
sql "UPDATE alembic_version SET version_num = '0000_kaputt'"
lauf "$REPO/scripts/restore.sh" db "$BD/db-$S.dump" --ja
assert_rc 0 "restore.sh db"
assert_enthaelt "$OUT" "Besitzpruefung von $TESTDB: ok|fieldvibe_owner" "Besitzpruefung im Restore-Log"
ERG="$(besitz_pruefen fieldvibe_owner)" && RCB=0 || RCB=$?
assert_eq "0" "$RCB" "besitz_pruefen.sql nach dem Restore"
assert_regex <(printf '%s\n' "$ERG") '^ok\|fieldvibe_owner\|' "Ergebniszeile nach dem Restore"
assert_eq "0" "$(objekte_von "'fieldvibe_app','fieldvibe_system','fieldvibe'")" "nach dem Restore keine Objekte beim Admin/App/System"
assert_eq "$VORHER_KUNDEN" "$(sql "SELECT string_agg(kundennummer || mandant_id::text, ',' ORDER BY mandant_id, kundennummer) FROM kunden")" "Testdaten wie vorher"
assert_eq "$HEAD_REV" "$(sql 'SELECT version_num FROM alembic_version')" "alembic_version wie vorher"
assert_eq "3" "$(app_sql "$MA" 'SELECT count(*) FROM kunden')" "RLS nach Restore: Mandant A sieht 3"
assert_eq "0" "$(app_sql "$MA" "SELECT count(*) FROM kunden WHERE mandant_id = '$MB'")" "RLS nach Restore: keine B-Zeilen"
assert_app_verboten "nach Restore: DISABLE ROW LEVEL SECURITY verboten" "$MA" "ALTER TABLE kunden DISABLE ROW LEVEL SECURITY"
assert_eq "t" "$(sql "SELECT has_table_privilege('fieldvibe_app', 'kunden', 'DELETE') AND has_table_privilege('fieldvibe_system', 'kunden', 'INSERT')")" "DML-Rechte nach Restore"
lauf "$REPO/scripts/backup-pruefen.sh"
assert_rc 0 "backup-pruefen.sh"
assert_enthaelt "$OUT" "Besitz ok: Owner fieldvibe_owner" "Besitz-ok-Hinweis"
assert_eq "" "$(psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'restore\_test\_%'")" "Wegwerf-DB geloescht"

szenario "Abschalten (DB_GETRENNTER_OWNER=0): Eigentum zurueck an die App-Rolle, .env.migration archiviert, Warnung, migrieren.sh als App-Rolle"
OWNER_PW="$(grep '^APP_DB_OWNER_PASSWORD=' "$REPO/.env.migration" | cut -d= -f2)"
sed -i 's/^DB_GETRENNTER_OWNER=1$/DB_GETRENNTER_OWNER=0/' "$REPO/.env"
lauf "$REPO/scripts/app_rolle_einrichten.sh" --nur-rolle
assert_rc 0 "Abschalten"
assert_eq "0" "$(objekte_von "'fieldvibe_owner','fieldvibe_system'")" "Owner und System besitzen nichts mehr"
if [[ "$(rls_tabellen_von fieldvibe_app)" -gt 100 ]]; then _fv_ok; else _fv_schlecht "App-Rolle besitzt wieder die RLS-Tabellen"; fi
ERG="$(besitz_pruefen)" && RCB=0 || RCB=$?
assert_eq "0" "$RCB" "besitz_pruefen.sql im App-Modus"
assert_regex <(printf '%s\n' "$ERG") '^ok\|fieldvibe_app\|' "Ergebniszeile im App-Modus"
assert_keine_datei "$REPO/.env.migration" ".env.migration verschoben"
ARCH="$(find "$REPO" -maxdepth 1 -name '.env.migration.deaktiviert-*' | head -n1)"
assert_datei "$ARCH" "archivierte Owner-Datei"
assert_eq "600" "$(stat -c %a "$ARCH")" "Archiv mit 0600"
assert_enthaelt "$REPO/.env" "FIELDVIBE_DB_BESITZ_VERBOTEN=0" "Strikt-Schalter aus"
assert_enthaelt "$REPO/.env" "DB_GETRENNTER_OWNER=0" "Marker bleibt 0"
assert_enthaelt "$OUT" "ABGESCHALTET" "laute Warnung im Output"
assert_enthaelt_nicht "$OUT" "$OWNER_PW" "Owner-Passwort nicht in der Ausgabe"
: >"$T/alembic-rollen.log"
lauf "$REPO/scripts/migrieren.sh"
assert_rc 0 "migrieren.sh nach dem Abschalten"
assert_enthaelt "$T/alembic-rollen.log" "alembic-rolle=fieldvibe_app args=upgrade head" "Migration wieder als App-Rolle"
ERG="$(startpruefung 0)"
assert_eq "1" "$([[ "$ERG" == ok\ warnungen=1* ]] && echo 1 || echo 0)" "Startpruefung warnt wieder (App-Rolle besitzt RLS-Tabellen)"

test_ende
