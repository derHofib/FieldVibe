#!/usr/bin/env bash
set -euo pipefail

# Prueft CII-E-Rechnungen (Profil EN 16931) gegen die CEN-Geschaeftsregeln
# (Schematron, kompiliert als XSLT). Je Datei eine Zeile OK bzw. FEHLER, darunter
# die verletzten Regeln mit Regel-ID, Meldung und Fundstelle (XPath im Dokument).
# Warnungen (Flag "warning") werden angezeigt, zaehlen aber nicht als Fehler.
#
# Usage: scripts/e-rechnung/pruefen.sh [--svrl <verzeichnis>] <datei.xml> [...]
#   --svrl <dir>  legt den rohen SVRL-Bericht je Datei dort ab
# Exit-Code: 0 alle Dateien ohne Fehler, 1 mindestens eine Datei mit Regelverstoss,
#            2 Aufruf-/Installationsproblem (Werkzeug fehlt: installieren.sh ausfuehren)
# Geprueft wird NUR EN 16931 -- weder das XRechnung-Profil noch Peppol (siehe
# docs/konzepte/E_RECHNUNG_PRUEFUNG.md).

SKRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SKRIPT_DIR/../.." && pwd)"
# shellcheck source=scripts/e-rechnung/pins.sh
source "$SKRIPT_DIR/pins.sh"

CACHE_DIR="${EN16931_CACHE_DIR:-$REPO_DIR/.cache/e-rechnung}"

fehler() { echo "FEHLER: $*" >&2; }

SVRL_DIR=""
DATEIEN=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --svrl) SVRL_DIR="${2:?--svrl braucht ein Verzeichnis}"; shift ;;
    -h | --help) sed -n '4,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) fehler "Unbekannte Option: $1"; exit 2 ;;
    *) DATEIEN+=("$1") ;;
  esac
  shift
done
if [[ ${#DATEIEN[@]} -eq 0 ]]; then
  fehler "Keine Datei angegeben (Usage: pruefen.sh [--svrl <dir>] <datei.xml> [...])"
  exit 2
fi

SAXON="$CACHE_DIR/Saxon-HE-$SAXON_VERSION.jar"
RESOLVER="$CACHE_DIR/xmlresolver-$XMLRESOLVER_VERSION.jar"
RESOLVER_DATA="$CACHE_DIR/xmlresolver-$XMLRESOLVER_VERSION-data.jar"
REGELN="$CACHE_DIR/EN16931-CII-validation.xslt"
for f in "$SAXON" "$RESOLVER" "$RESOLVER_DATA" "$REGELN"; do
  if [[ ! -f "$f" ]]; then
    fehler "Pruefwerkzeug nicht installiert ($f fehlt) -- zuerst scripts/e-rechnung/installieren.sh ausfuehren"
    exit 2
  fi
done
command -v java >/dev/null 2>&1 || { fehler "java nicht gefunden"; exit 2; }

if [[ -n "$SVRL_DIR" ]]; then
  mkdir -p "$SVRL_DIR"
fi
ARBEIT="$(mktemp -d)"
trap 'rm -rf "$ARBEIT"' EXIT
CLASSPATH_SAXON="$SAXON:$RESOLVER:$RESOLVER_DATA"

# Saxon schreibt Warnungen/Hinweise auf stderr; nur echte Abbrueche (Exit != 0) zaehlen.
saxon() { java -cp "$CLASSPATH_SAXON" net.sf.saxon.Transform "$@"; }

GESAMT_FEHLER=0
for datei in "${DATEIEN[@]}"; do
  name="$(basename "$datei")"
  if [[ ! -f "$datei" ]]; then
    echo "FEHLER  $name  (Datei nicht gefunden)"
    GESAMT_FEHLER=1
    continue
  fi
  svrl="$ARBEIT/bericht.svrl"
  if ! saxon -s:"$datei" -xsl:"$REGELN" -o:"$svrl" 2>"$ARBEIT/saxon.err"; then
    echo "FEHLER  $name  (XML nicht verarbeitbar)"
    grep -v '^Picked up JAVA_TOOL_OPTIONS' "$ARBEIT/saxon.err" | sed 's/^/  /' || true
    GESAMT_FEHLER=1
    continue
  fi
  if [[ -n "$SVRL_DIR" ]]; then
    cp "$svrl" "$SVRL_DIR/${name%.xml}.svrl"
  fi
  saxon -s:"$svrl" -xsl:"$SKRIPT_DIR/svrl-auswertung.xsl" -o:"$ARBEIT/auswertung.txt" 2>/dev/null

  fehler_zeilen="$(grep -c '^FEHLER'$'\t' "$ARBEIT/auswertung.txt" || true)"
  if [[ "$fehler_zeilen" -eq 0 ]]; then
    echo "OK      $name"
  else
    echo "FEHLER  $name  ($fehler_zeilen Regelverstoesse)"
    GESAMT_FEHLER=1
  fi
  while IFS=$'\t' read -r art regel_id meldung fundstelle; do
    [[ -n "$art" ]] || continue
    if [[ "$art" == "FEHLER" ]]; then
      echo "  [$regel_id] $meldung"
    else
      echo "  Warnung [$regel_id] $meldung"
    fi
    echo "      Fundstelle: $fundstelle"
  done <"$ARBEIT/auswertung.txt"
done

exit "$GESAMT_FEHLER"
