#!/usr/bin/env bash
set -euo pipefail

# Kommandozeilen-Zugriff auf die Service-API der Fehlerberichte (bash + curl).
# Env: FIELDVIBE_API_URL (z. B. https://api.fieldvibe.de), FIELDVIBE_BUGREPORT_TOKEN
# Siehe docs/FEHLERBERICHTE.md und docs/BUGFIX_WORKFLOW.md.

STATI="neu gesichtet in_arbeit behoben abgelehnt duplikat"
SCHWEREGRADE="niedrig mittel hoch blockierend"
ARTEN="fehler idee"

fehler() { echo "Fehler: $*" >&2; exit 1; }

hilfe() {
  cat >&2 <<'HILFE'
Aufruf: fehlerberichte.sh <befehl> [argumente]

  liste [status] [schweregrad] [art]   Berichte auflisten (ohne Filter: alle; "-" = kein Filter)
                                 art: fehler | idee; alternativ --art <art> an beliebiger Stelle
                                 (Ideen: Status "gesichtet" = vom Betreiber freigegeben)
  zeige <id>                     Detail als JSON
  bundle <id>                    AI-Bundle (Markdown)
  aehnliche <id>                 Berichte mit gleichem Fingerprint
  notiz <id> "<text>"            nur Loesungsnotiz setzen, Status unveraendert
  status <id> <status> [--notiz "..."] [--commit sha] [--pr url]

Env: FIELDVIBE_API_URL, FIELDVIBE_BUGREPORT_TOKEN
HILFE
  exit 2
}

[[ $# -ge 1 ]] || hilfe
befehl="$1"
shift

[[ -n "${FIELDVIBE_API_URL:-}" ]] || fehler "FIELDVIBE_API_URL ist nicht gesetzt"
[[ -n "${FIELDVIBE_BUGREPORT_TOKEN:-}" ]] || fehler "FIELDVIBE_BUGREPORT_TOKEN ist nicht gesetzt"
command -v curl >/dev/null || fehler "curl fehlt"

BASIS="${FIELDVIBE_API_URL%/}/api/service/fehlerberichte"

enthalten() { [[ " $2 " == *" $1 "* ]]; }

pruefe_id() {
  [[ "${1:-}" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]] \
    || fehler "ungueltige Bericht-ID: ${1:-<leer>}"
}

# Gibt den Body auf stdout aus, bei HTTP >= 400 eine verstaendliche Meldung auf
# stderr und Exit 1. Das Token geht per stdin-Config an curl, damit es weder in
# der Prozessliste noch in der Ausgabe auftaucht.
anfrage() {
  local methode="$1" url="$2" body="${3:-}"
  local tmp code
  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' RETURN
  local args=(-sS -o "$tmp" -w '%{http_code}' --max-time 30 -X "$methode" -K -)
  if [[ -n "$body" ]]; then
    args+=(-H 'Content-Type: application/json' --data-binary "$body")
  fi
  code="$(printf 'header = "Authorization: Bearer %s"\n' "$FIELDVIBE_BUGREPORT_TOKEN" | curl "${args[@]}" "$url")" \
    || fehler "Verbindung zu ${FIELDVIBE_API_URL} fehlgeschlagen"
  if [[ "$code" -ge 400 ]]; then
    case "$code" in
      401) echo "Fehler 401: Token ungueltig (FIELDVIBE_BUGREPORT_TOKEN pruefen)." >&2 ;;
      404) echo "Fehler 404: nicht gefunden (Bericht-ID falsch oder Service-API serverseitig nicht aktiviert)." >&2 ;;
      422) echo "Fehler 422: Eingabe abgelehnt: $(head -c 500 "$tmp")" >&2 ;;
      429) echo "Fehler 429: Rate-Limit erreicht, spaeter erneut versuchen." >&2 ;;
      *) echo "Fehler HTTP $code: $(head -c 300 "$tmp")" >&2 ;;
    esac
    return 1
  fi
  cat "$tmp"
}

json_string() { python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"; }

case "$befehl" in
  liste)
    pos=(); ar="-"
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --art) [[ $# -ge 2 ]] || fehler "Option --art braucht einen Wert"; ar="$2"; shift 2 ;;
        *) pos+=("$1"); shift ;;
      esac
    done
    st="${pos[0]:--}"; sg="${pos[1]:--}"
    [[ "${pos[2]:-}" ]] && ar="${pos[2]}"
    query=""
    if [[ "$st" != "-" ]]; then
      enthalten "$st" "$STATI" || fehler "ungueltiger Status '$st' (erlaubt: $STATI)"
      query="status=$st"
    fi
    if [[ "$sg" != "-" ]]; then
      enthalten "$sg" "$SCHWEREGRADE" || fehler "ungueltiger Schweregrad '$sg' (erlaubt: $SCHWEREGRADE)"
      query="${query:+$query&}schweregrad=$sg"
    fi
    if [[ "$ar" != "-" ]]; then
      enthalten "$ar" "$ARTEN" || fehler "ungueltige Art '$ar' (erlaubt: $ARTEN)"
      query="${query:+$query&}art=$ar"
    fi
    antwort="$(anfrage GET "$BASIS?${query:+$query&}limit=200")"
    if command -v jq >/dev/null; then
      # Prioritaet: blockierend > hoch > mittel > niedrig, innerhalb aelteste zuerst.
      echo "$antwort" | jq -r '
        {"blockierend":0,"hoch":1,"mittel":2,"niedrig":3} as $p
        | sort_by([$p[.schweregrad], .created_at])
        | .[] | [.id, (.art // "fehler"), .schweregrad, .status, (.created_at[:10]), .titel] | @tsv'
    else
      echo "$antwort"
    fi
    ;;
  zeige)
    pruefe_id "${1:-}"
    antwort="$(anfrage GET "$BASIS/$1")"
    if command -v jq >/dev/null; then echo "$antwort" | jq .; else echo "$antwort"; fi
    ;;
  bundle)
    pruefe_id "${1:-}"
    anfrage GET "$BASIS/$1/ai-bundle"
    ;;
  aehnliche)
    pruefe_id "${1:-}"
    antwort="$(anfrage GET "$BASIS/$1/aehnliche")"
    if command -v jq >/dev/null; then
      echo "$antwort" | jq -r '.[] | [.id, .schweregrad, .status, (.created_at[:10]), .titel] | @tsv'
    else
      echo "$antwort"
    fi
    ;;
  notiz)
    pruefe_id "${1:-}"
    [[ -n "${2:-}" ]] || hilfe
    anfrage PATCH "$BASIS/$1" "{\"loesungsnotiz\": $(json_string "$2")}" >/dev/null
    echo "Bericht $1: Notiz gesetzt"
    ;;
  status)
    pruefe_id "${1:-}"
    id="$1"
    neuer="${2:-}"
    [[ -n "$neuer" ]] || hilfe
    enthalten "$neuer" "$STATI" || fehler "ungueltiger Status '$neuer' (erlaubt: $STATI)"
    shift 2
    felder="\"status\": $(json_string "$neuer")"
    while [[ $# -gt 0 ]]; do
      [[ $# -ge 2 ]] || fehler "Option $1 braucht einen Wert"
      case "$1" in
        --notiz) felder+=", \"loesungsnotiz\": $(json_string "$2")" ;;
        --commit) felder+=", \"fix_commit\": $(json_string "$2")" ;;
        --pr) felder+=", \"fix_pr_url\": $(json_string "$2")" ;;
        *) fehler "unbekannte Option $1" ;;
      esac
      shift 2
    done
    anfrage PATCH "$BASIS/$id" "{$felder}" >/dev/null
    echo "Bericht $id: Status -> $neuer"
    ;;
  *) hilfe ;;
esac
