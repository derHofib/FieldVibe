#!/usr/bin/env bash
# Richtet den Claude-Zugang zur Fehlerbericht-API auf dem Server ein:
# Token erzeugen, Hash in .env eintragen (vorhandener wird ersetzt = Rotation),
# Backend neu starten, Verbindung pruefen und die Werte fuer die
# Claude-Code-Umgebung ausgeben. Aufruf im Repo-Verzeichnis auf dem Server:
#   ./scripts/fehlerbericht_token_einrichten.sh
set -euo pipefail

cd "$(dirname "$0")/.."

fehler() { echo "Fehler: $*" >&2; exit 1; }

[[ -f .env ]] || fehler ".env nicht gefunden – im FieldVibe-Verzeichnis ausfuehren."
command -v openssl >/dev/null || fehler "openssl fehlt"
command -v sha256sum >/dev/null || fehler "sha256sum fehlt"

env_wert() { grep -E "^$1=" .env | tail -n1 | cut -d= -f2- | tr -d '"' || true; }

# Overlay wie beim Deployment: mit Domain laeuft Caddy (.prod.yml), sonst .ip.yml.
# .prod.yml und .ip.yml duerfen nie gemeinsam verwendet werden.
# Ausgabe erst einsammeln: grep -q beendet die Pipe frueh, mit pipefail
# wuerde das als Fehler gewertet und faelschlich .ip.yml gewaehlt.
CONTAINER="$(docker ps --format '{{.Names}}')"
if grep -q caddy <<<"$CONTAINER"; then
  COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
else
  COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.ip.yml)
fi

if grep -qE '^FIELDVIBE_FEHLERBERICHT_TOKEN_HASH=.+' .env; then
  echo "Es ist bereits ein Token eingerichtet. Ein neues macht das alte sofort ungueltig"
  echo "(danach muss es auch in der Claude-Umgebung ersetzt werden)."
  read -rp "Neues Token erzeugen? [j/N] " antwort
  [[ "$antwort" =~ ^[jJ]$ ]] || { echo "Abgebrochen, nichts geaendert."; exit 0; }
fi

# URL-sicheres Token ohne Zeilenumbruch; gehasht wird exakt dieser String
# (so vergleicht auch das Backend).
TOKEN="$(openssl rand -base64 48 | tr '+/' '-_' | tr -d '=\n')"
HASH="$(printf '%s' "$TOKEN" | sha256sum | cut -d' ' -f1)"

cp .env ".env.bak-$(date +%Y%m%d-%H%M%S)"
if grep -qE '^FIELDVIBE_FEHLERBERICHT_TOKEN_HASH=' .env; then
  sed -i "s|^FIELDVIBE_FEHLERBERICHT_TOKEN_HASH=.*|FIELDVIBE_FEHLERBERICHT_TOKEN_HASH=${HASH}|" .env
else
  printf '\n# Claude-Zugang Fehlerberichte (scripts/fehlerbericht_token_einrichten.sh)\nFIELDVIBE_FEHLERBERICHT_TOKEN_HASH=%s\n' "$HASH" >> .env
fi
echo "Hash in .env eingetragen (Sicherung: .env.bak-*)."

echo "Starte Backend neu..."
"${COMPOSE[@]}" up -d --force-recreate backend >/dev/null

API_URL="$(env_wert VITE_API_BASE_URL)"
DOMAIN_API="$(env_wert DOMAIN_API)"
DOMAIN_S3="$(env_wert DOMAIN_S3)"
[[ -n "$API_URL" ]] || API_URL="https://${DOMAIN_API}"

echo -n "Pruefe Verbindung"
code=""
for _ in $(seq 1 30); do
  code="$(printf 'header = "Authorization: Bearer %s"\n' "$TOKEN" \
    | curl -s -o /dev/null -w '%{http_code}' -K - "${API_URL}/api/service/fehlerberichte?limit=1" || true)"
  [[ "$code" == "200" ]] && break
  echo -n "."
  sleep 2
done
echo
if [[ "$code" == "200" ]]; then
  echo "Verbindung ok (HTTP 200)."
else
  echo "Achtung: Testabruf ergab HTTP ${code:-keine Antwort}. Backend-Log pruefen:"
  echo "  ${COMPOSE[*]} logs --tail=50 backend"
fi

cat <<EOF

================================================================================
 In Claude Code eintragen (Session-Titelleiste -> Umgebungsmenue -> Edit)
================================================================================

 Umgebungsvariablen:

   FIELDVIBE_API_URL=${API_URL}
   FIELDVIBE_BUGREPORT_TOKEN=${TOKEN}

 Network access -> Custom -> Allowed domains (Paketmanager-Liste behalten):

   ${DOMAIN_API:-<API-Domain>}
   ${DOMAIN_S3:-<S3-Domain>}

 Das Token wird nur jetzt angezeigt: in den Passwort-Manager kopieren und
 dieses Terminal danach mit 'clear' leeren. Nicht in Chats oder Mails einfuegen.
================================================================================
EOF
