#!/usr/bin/env bash
set -euo pipefail

# Prueft CII-E-Rechnungen gegen die CEN-Geschaeftsregeln der EN 16931 (Schematron,
# kompiliert als XSLT); Dokumente mit der XRechnung-CustomizationID zusaetzlich gegen die
# XRechnung-Regeln (BR-DE-*, siehe pins.sh). Je Datei eine Zeile OK bzw. FEHLER, darunter
# die verletzten Regeln mit Regel-ID, Meldung und Fundstelle (XPath im Dokument).
# Warnungen (Flag "warning") werden angezeigt, zaehlen aber nicht als Fehler.
#
# Usage: scripts/e-rechnung/pruefen.sh [--svrl <verzeichnis>] <datei.xml> [...]
#   --svrl <dir>  legt den rohen SVRL-Bericht je Datei dort ab
# Exit-Code: 0 alle Dateien ohne Fehler, 1 mindestens eine Datei mit Regelverstoss,
#            2 Aufruf-/Installationsproblem (Werkzeug fehlt: installieren.sh ausfuehren)
# Nicht geprueft wird Peppol (siehe docs/konzepte/E_RECHNUNG_PRUEFUNG.md); die XRechnung-Regeln
# sind das Schematron der KoSIT, aber ohne den KoSIT-Validator drumherum (kein XSD-/Berichtslauf).

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
XR_REGELN="$CACHE_DIR/XRechnung-CII-validation.xslt"
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
  regelsaetze=("$REGELN")
  # Die XRechnung-Regeln gelten nur fuer Dokumente, die sich als XRechnung ausgeben.
  if grep -q 'urn:xoev-de:kosit:standard:xrechnung' "$datei"; then
    if [[ ! -f "$XR_REGELN" ]]; then
      fehler "XRechnung-Regeln nicht installiert ($XR_REGELN fehlt) -- zuerst scripts/e-rechnung/installieren.sh ausfuehren"
      exit 2
    fi
    regelsaetze+=("$XR_REGELN")
  fi
  : >"$ARBEIT/auswertung.txt"
  verarbeitbar=1
  for regeln in "${regelsaetze[@]}"; do
    svrl="$ARBEIT/bericht.svrl"
    if ! saxon -s:"$datei" -xsl:"$regeln" -o:"$svrl" 2>"$ARBEIT/saxon.err"; then
      echo "FEHLER  $name  (XML nicht verarbeitbar)"
      grep -v '^Picked up JAVA_TOOL_OPTIONS' "$ARBEIT/saxon.err" | sed 's/^/  /' || true
      GESAMT_FEHLER=1
      verarbeitbar=0
      break
    fi
    if [[ -n "$SVRL_DIR" ]]; then
      cp "$svrl" "$SVRL_DIR/${name%.xml}$([[ "$regeln" == "$XR_REGELN" ]] && echo -xrechnung || true).svrl"
    fi
    saxon -s:"$svrl" -xsl:"$SKRIPT_DIR/svrl-auswertung.xsl" -o:"$ARBEIT/teil.txt" 2>/dev/null
    cat "$ARBEIT/teil.txt" >>"$ARBEIT/auswertung.txt"
  done
  [[ "$verarbeitbar" -eq 1 ]] || continue

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
