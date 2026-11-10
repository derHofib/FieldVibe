#!/usr/bin/env bash
set -euo pipefail

# Tests fuer scripts/minio-service-account.sh. docker und mc sind gestubbt: das
# prueft Ablauf, Idempotenz, Policy-Inhalt und .env-Pflege, NICHT das Verhalten
# eines echten MinIO (mc-Syntax/Policy-Durchsetzung bleiben ungetestet).

# shellcheck source=scripts/tests/helfer.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/helfer.sh"

echo "test_minio_service_account.sh"

umgebung() {
  testumgebung_anlegen
  cp "$FV_SCRIPTS_DIR/minio-service-account.sh" "$REPO/scripts/"
  : >"$REPO/docker-compose.yml"
  env_schreiben "MINIO_ROOT_USER=rootuser" "MINIO_ROOT_PASSWORD=rootpw" "S3_BUCKET_FOTOS=fieldvibe-fotos" "S3_ACCESS_KEY=" "S3_SECRET_KEY="
  # docker: "compose ... exec -T minio sh -s" -> Skript aus stdin mit Container-Umgebung und mc-Stub ausfuehren.
  cat >"$BIN/docker" <<'STUB'
#!/usr/bin/env bash
echo "docker $*" >>"$FV_STUB_LOG"
[[ "$*" == *" exec -T minio sh -s"* ]] || exit 0
[[ "${STUB_EXEC_FAIL:-0}" == "1" ]] && { echo "exec kaputt" >&2; exit 1; }
exec env MINIO_ROOT_USER=rootuser MINIO_ROOT_PASSWORD=rootpw sh -s
STUB
  cat >"$BIN/mc" <<'STUB'
#!/usr/bin/env bash
echo "mc $*" >>"$FV_STUB_LOG"
case "$1 $2 $3 $4" in
  "admin policy create "*) cp "${@: -1}" "$FV_T/policy.json" ;;
  "admin user svcacct info") [[ -f "$FV_T/svcacct" ]] || exit 1 ;;
  "admin user svcacct add") : >"$FV_T/svcacct" ;;
esac
if [[ "$1" == "mb" && "$*" == *"fvapp/"* && "${STUB_MB_APP_ERLAUBT:-0}" != "1" ]]; then exit 1; fi
exit 0
STUB
  chmod +x "$BIN/docker" "$BIN/mc"
}

szenario "Erstlauf: legt Bucket, Policy und Service-Account an und traegt neue Schluessel in .env ein"
umgebung
lauf "$REPO/scripts/minio-service-account.sh" --compose "docker compose"
assert_rc 0 "Erstlauf"
assert_enthaelt "$OUT" "GEAENDERT" "meldet geaenderte Zugangsdaten"
assert_regex "$REPO/.env" '^S3_ACCESS_KEY=fvapp[0-9a-f]{16}$' "Access-Key erzeugt (nicht der Root-User)"
assert_regex "$REPO/.env" '^S3_SECRET_KEY=[0-9a-f]{48}$' "Secret erzeugt"
assert_enthaelt "$REPO/.env" "MINIO_ROOT_USER=rootuser" "Root-Zugang unveraendert"
assert_enthaelt "$T/stub.log" "mc mb --ignore-existing fvroot/fieldvibe-fotos" "Bucket wird angelegt"
assert_enthaelt "$T/stub.log" "svcacct add" "Service-Account angelegt"
assert_enthaelt "$T/stub.log" "--name fieldvibe-app fvroot rootuser" "gebunden an den Root-Benutzer, mit Namen"
assert_enthaelt "$T/policy.json" '"arn:aws:s3:::fieldvibe-fotos/*"' "Objekt-Rechte nur auf den Bucket"
assert_enthaelt "$T/policy.json" '"s3:GetObject", "s3:GetObjectVersion", "s3:PutObject", "s3:DeleteObject", "s3:DeleteObjectVersion", "s3:PutObjectRetention", "s3:GetObjectRetention"' "nur Objekt-Rechte (inkl. Versionen/Retention), keine Bucket-Verwaltung"
assert_enthaelt_nicht "$T/policy.json" "s3:*" "keine Wildcard-Aktion"
assert_enthaelt_nicht "$T/policy.json" "admin:" "keine Admin-Rechte"
assert_enthaelt_nicht "$OUT" "$(grep '^S3_SECRET_KEY=' "$REPO/.env" | cut -d= -f2)" "Secret nicht in der Ausgabe"
grep '^docker ' "$T/stub.log" >"$T/docker-aufrufe.log"
assert_enthaelt_nicht "$T/docker-aufrufe.log" "$(grep '^S3_SECRET_KEY=' "$REPO/.env" | cut -d= -f2)" "Secret nicht in docker-Argumenten (Host-Prozessliste)"
testumgebung_loeschen

szenario "Idempotenz: zweiter Lauf behaelt Schluessel, aktualisiert statt neu anzulegen"
umgebung
lauf "$REPO/scripts/minio-service-account.sh" --compose "docker compose"
VORHER="$(grep '^S3_' "$REPO/.env")"
: >"$T/stub.log"
lauf "$REPO/scripts/minio-service-account.sh" --compose "docker compose"
assert_rc 0 "Zweitlauf"
assert_eq "$VORHER" "$(grep '^S3_' "$REPO/.env")" "Schluessel unveraendert"
assert_enthaelt_nicht "$OUT" "GEAENDERT" "keine Aenderung gemeldet"
assert_enthaelt "$T/stub.log" "svcacct edit" "vorhandener Account wird angeglichen"
assert_enthaelt_nicht "$T/stub.log" "svcacct add" "kein zweites Anlegen"
assert_eq "1" "$(grep -c '^S3_ACCESS_KEY=' "$REPO/.env")" "keine doppelten .env-Zeilen"
testumgebung_loeschen

szenario "Root-Zugang als S3_ACCESS_KEY in .env wird durch einen eigenen Schluessel ersetzt"
umgebung
env_schreiben "MINIO_ROOT_USER=rootuser" "MINIO_ROOT_PASSWORD=rootpw" "S3_ACCESS_KEY=rootuser" "S3_SECRET_KEY=rootpw"
lauf "$REPO/scripts/minio-service-account.sh" --compose "docker compose"
assert_rc 0 "Lauf"
assert_regex "$REPO/.env" '^S3_ACCESS_KEY=fvapp[0-9a-f]{16}$' "neuer Schluessel"
testumgebung_loeschen

szenario "Policy greift nicht (fremder Bucket anlegbar): Exit != 0, .env unveraendert"
umgebung
LAUF_ENV=(STUB_MB_APP_ERLAUBT=1)
lauf "$REPO/scripts/minio-service-account.sh" --compose "docker compose"
assert_rc_nicht0 "Kontrolle schlaegt an"
assert_enthaelt "$OUT" "Policy greift nicht" "klare Meldung"
assert_eq "S3_ACCESS_KEY=" "$(grep '^S3_ACCESS_KEY=' "$REPO/.env")" ".env unveraendert"
testumgebung_loeschen

szenario "Container nicht erreichbar: Exit != 0, .env unveraendert"
umgebung
LAUF_ENV=(STUB_EXEC_FAIL=1)
lauf "$REPO/scripts/minio-service-account.sh" --compose "docker compose"
assert_rc_nicht0 "exec scheitert"
assert_eq "S3_SECRET_KEY=" "$(grep '^S3_SECRET_KEY=' "$REPO/.env")" ".env unveraendert"
testumgebung_loeschen

szenario "--dry-run und ungueltiger Bucket-Name"
umgebung
lauf "$REPO/scripts/minio-service-account.sh" --dry-run --compose "docker compose"
assert_rc 0 "Trockenlauf"
assert_enthaelt_nicht "$T/stub.log" "svcacct" "Trockenlauf fasst MinIO nicht an"
assert_eq "S3_ACCESS_KEY=" "$(grep '^S3_ACCESS_KEY=' "$REPO/.env")" ".env unveraendert"
env_schreiben "S3_BUCKET_FOTOS=Foto Bucket\";x"
lauf "$REPO/scripts/minio-service-account.sh" --compose "docker compose"
assert_rc_nicht0 "Bucket-Name mit Sonderzeichen wird abgelehnt"
testumgebung_loeschen

test_ende
