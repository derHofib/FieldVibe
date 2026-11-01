#!/usr/bin/env bash
set -euo pipefail

# Richtet fuer Backend und Worker einen MinIO-Service-Account mit Policy
# ein, die nur den Foto-Bucket erlaubt (Lesen/Schreiben/Loeschen von Objekten,
# Auflisten des einen Buckets), und traegt dessen Zugangsdaten als
# S3_ACCESS_KEY/S3_SECRET_KEY in .env ein. Der Root-Zugang (MINIO_ROOT_USER/
# MINIO_ROOT_PASSWORD) bleibt nur fuer MinIO selbst und Admin-Aufgaben: ein
# kompromittiertes Backend kann damit keine MinIO-Benutzer/Policies anlegen
# und keine anderen Buckets lesen.
#
# Usage (im Repo-Verzeichnis, MinIO-Container muss laufen):
#   ./scripts/minio-service-account.sh [--dry-run] [--compose "docker compose -f ... -f ..."]
#
# Idempotent: ein zweiter Lauf erkennt Service-Account und Policy und gleicht
# Secret und Policy an. Backend/Worker muessen nach einer .env-Aenderung neu
# erzeugt werden (deploy.sh macht das). Exit-Code 0 = fertig; die Ausgabe
# "GEAENDERT" verraet, dass sich die Zugangsdaten in .env geaendert haben.

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

log()  { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31mFehler:\033[0m %s\n' "$*" >&2; exit 1; }

DRY_RUN=0
COMPOSE_ARG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --compose) shift; [[ $# -gt 0 ]] || err "--compose braucht ein Argument."; COMPOSE_ARG="$1" ;;
    -h|--help) sed -n '3,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)         err "Unbekannte Option: $1 (siehe --help)" ;;
  esac
  shift
done

[[ -f docker-compose.yml ]] || err "Muss aus dem geklonten Repo heraus ausgefuehrt werden."
[[ -f .env ]] || err ".env nicht gefunden -- zuerst scripts/deploy.sh ausfuehren oder .env aus .env.example anlegen."

get_env() { grep "^${1}=" .env 2>/dev/null | head -n1 | cut -d= -f2- || true; }

# Wie in app_rolle_einrichten.sh: awk/ENVIRON statt sed, damit Sonderzeichen im
# Wert nicht als Ersetzungs-Syntax wirken.
set_env() {
  local tmp
  tmp="$(mktemp .env.XXXXXX)"
  KEY="$1" VAL="$2" awk '
    BEGIN { k = ENVIRON["KEY"]; v = ENVIRON["VAL"]; done = 0 }
    index($0, k "=") == 1 { if (!done) { print k "=" v; done = 1 } ; next }
    { print }
    END { if (!done) print k "=" v }
  ' .env > "$tmp"
  cat "$tmp" > .env
  rm -f "$tmp"
}

if [[ -n "$COMPOSE_ARG" ]]; then
  read -ra COMPOSE <<< "$COMPOSE_ARG"
else
  case "$(get_env DEPLOY_MODE)" in
    domain) COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml) ;;
    ip)     COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.ip.yml) ;;
    *)      COMPOSE=(docker compose) ;;
  esac
fi

BUCKET="$(get_env S3_BUCKET_FOTOS)"; BUCKET="${BUCKET:-fieldvibe-fotos}"
ROOT_USER="$(get_env MINIO_ROOT_USER)"; ROOT_USER="${ROOT_USER:-fieldvibe}"
ACCESS_KEY="$(get_env S3_ACCESS_KEY)"
SECRET_KEY="$(get_env S3_SECRET_KEY)"

# Bucket-Name und Schluessel landen in einer JSON-Policy und in Shell-Variablen:
# nur harmlose Zeichen zulassen.
[[ "$BUCKET" =~ ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ ]] || err "S3_BUCKET_FOTOS='$BUCKET' ist kein gueltiger Bucket-Name."

NEU=0
if [[ -z "$ACCESS_KEY" || "$ACCESS_KEY" == "$ROOT_USER" || -z "$SECRET_KEY" || "$SECRET_KEY" == *changeme* ]]; then
  # Nur Hex: kein Quoting noetig, nirgends. Neuer Schluessel auch dann, wenn
  # bisher der Root-Zugang eingetragen war.
  ACCESS_KEY="fvapp$(openssl rand -hex 8)"
  SECRET_KEY="$(openssl rand -hex 24)"
  NEU=1
fi
[[ "$ACCESS_KEY" =~ ^[A-Za-z0-9]{3,64}$ ]] || err "S3_ACCESS_KEY in .env enthaelt unerwartete Zeichen -- Zeile loeschen, dann erzeugt das Skript einen neuen."
[[ "$SECRET_KEY" =~ ^[A-Za-z0-9]{8,128}$ ]] || err "S3_SECRET_KEY in .env enthaelt unerwartete Zeichen -- Zeile loeschen, dann erzeugt das Skript einen neuen."

if [[ $DRY_RUN -eq 1 ]]; then
  log "Trockenlauf -- es wird nichts veraendert."
  cat <<PLAN
  Compose:        ${COMPOSE[*]}
  Bucket:         ${BUCKET}
  Service-Account: ${ACCESS_KEY} ($([[ $NEU -eq 1 ]] && echo "wird neu erzeugt" || echo "aus .env"))
  Schritte: Bucket anlegen (falls fehlt), Policy fieldvibe-app setzen, Service-Account
            anlegen/angleichen, Zugriff pruefen (Bucket ok, fremder Bucket verweigert),
            S3_ACCESS_KEY/S3_SECRET_KEY in .env eintragen.
PLAN
  exit 0
fi

command -v openssl &>/dev/null || err "openssl nicht gefunden."

log "Richte MinIO-Service-Account ${ACCESS_KEY} fuer Bucket ${BUCKET} ein..."
# Zugangsdaten reisen ueber stdin in den Container (nicht als Argument: die
# waeren in der Prozessliste sichtbar). Das Skript selbst steht im Heredoc.
{
  printf "FV_AK='%s'\nFV_SK='%s'\nFV_BUCKET='%s'\n" "$ACCESS_KEY" "$SECRET_KEY" "$BUCKET"
  cat <<'IM_CONTAINER'
set -eu
mc alias set fvroot http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc mb --ignore-existing "fvroot/$FV_BUCKET" >/dev/null

cat > /tmp/fv-policy.json <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": ["s3:ListBucket", "s3:ListBucketVersions", "s3:GetBucketLocation"], "Resource": ["arn:aws:s3:::$FV_BUCKET"]},
    {"Effect": "Allow", "Action": ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject", "s3:DeleteObject", "s3:DeleteObjectVersion", "s3:PutObjectRetention", "s3:GetObjectRetention"], "Resource": ["arn:aws:s3:::$FV_BUCKET/*"]}
  ]
}
POLICY

# "policy create" ersetzt eine vorhandene Policy; aeltere mc-Staende kennen nur "add".
mc admin policy create fvroot fieldvibe-app /tmp/fv-policy.json >/dev/null 2>&1 \
  || mc admin policy add fvroot fieldvibe-app /tmp/fv-policy.json >/dev/null

if mc admin user svcacct info fvroot "$FV_AK" >/dev/null 2>&1; then
  mc admin user svcacct edit --secret-key "$FV_SK" --policy /tmp/fv-policy.json fvroot "$FV_AK" >/dev/null
  echo "Service-Account $FV_AK aktualisiert."
else
  mc admin user svcacct add --access-key "$FV_AK" --secret-key "$FV_SK" \
    --policy /tmp/fv-policy.json --name fieldvibe-app fvroot "$MINIO_ROOT_USER" >/dev/null
  echo "Service-Account $FV_AK angelegt."
fi
rm -f /tmp/fv-policy.json

# Kontrolle mit den Zugangsdaten des Service-Accounts selbst: der eigene Bucket
# muss gehen, ein anderer Bucket darf nicht anlegbar sein.
mc alias set fvapp http://localhost:9000 "$FV_AK" "$FV_SK" >/dev/null
mc ls "fvapp/$FV_BUCKET" >/dev/null
if mc mb "fvapp/fv-negativtest-$FV_BUCKET" >/dev/null 2>&1; then
  mc rb "fvroot/fv-negativtest-$FV_BUCKET" >/dev/null 2>&1 || true
  echo "FEHLER: Service-Account darf fremde Buckets anlegen -- Policy greift nicht." >&2
  exit 1
fi
mc alias remove fvapp >/dev/null 2>&1 || true
mc alias remove fvroot >/dev/null 2>&1 || true
echo "Zugriff geprueft."
IM_CONTAINER
} | "${COMPOSE[@]}" exec -T minio sh -s \
  || err "Einrichtung im MinIO-Container fehlgeschlagen (laeuft der Container? ${COMPOSE[*]} ps minio). .env unveraendert."

if [[ "$(get_env S3_ACCESS_KEY)" != "$ACCESS_KEY" || "$(get_env S3_SECRET_KEY)" != "$SECRET_KEY" ]]; then
  set_env S3_ACCESS_KEY "$ACCESS_KEY"
  set_env S3_SECRET_KEY "$SECRET_KEY"
  chmod 600 .env
  log "S3_ACCESS_KEY/S3_SECRET_KEY in .env eingetragen -- Backend und Worker neu erzeugen."
  echo "GEAENDERT"
else
  log "Zugangsdaten in .env waren bereits aktuell."
fi
