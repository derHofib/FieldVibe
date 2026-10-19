#!/usr/bin/env bash
set -euo pipefail

# Richtet die Pruefwerkzeuge fuer ausgehende E-Rechnungen (EN 16931, CII) in einem
# gitignorierten Cache-Verzeichnis ein: Saxon-HE + xmlresolver (Maven Central) und die
# kompilierten CEN-Geschaeftsregeln (ConnectingEurope/eInvoicing-EN16931, per git auf
# gepinnten Commit). Jede Datei wird gegen die in pins.sh gepinnte SHA-256 geprueft;
# bei Abweichung bricht das Skript ab und hinterlaesst nichts im Cache.
#
# Usage: scripts/e-rechnung/installieren.sh
# Cache: EN16931_CACHE_DIR (Standard: .cache/e-rechnung im Repo)
# Benoetigt: java (>= 11), curl, git, sha256sum bzw. shasum

SKRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SKRIPT_DIR/../.." && pwd)"
# shellcheck source=scripts/e-rechnung/pins.sh
source "$SKRIPT_DIR/pins.sh"

CACHE_DIR="${EN16931_CACHE_DIR:-$REPO_DIR/.cache/e-rechnung}"
MAVEN="${MAVEN_CENTRAL_URL:-https://repo1.maven.org/maven2}"

fehler() { echo "FEHLER: $*" >&2; }

sha256_von() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  else
    shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

pruefsumme_ok() { # <datei> <erwartet>
  [[ -f "$1" && "$(sha256_von "$1")" == "$2" ]]
}

for werkzeug in java curl git; do
  command -v "$werkzeug" >/dev/null 2>&1 || { fehler "$werkzeug nicht gefunden"; exit 1; }
done

mkdir -p "$CACHE_DIR"
ARBEIT="$(mktemp -d "$CACHE_DIR/.arbeit.XXXXXX")"
trap 'rm -rf "$ARBEIT"' EXIT

# Maven Central drosselt gelegentlich mit 429; curl wiederholt das mit --retry.
herunterladen() { # <url> <ziel> <sha256>
  local url="$1" ziel="$2" soll="$3"
  if pruefsumme_ok "$ziel" "$soll"; then
    echo "vorhanden: $(basename "$ziel")"
    return
  fi
  echo "lade: $url"
  curl -fsSL --retry 5 --retry-delay 3 -o "$ARBEIT/download" "$url"
  if ! pruefsumme_ok "$ARBEIT/download" "$soll"; then
    fehler "Pruefsumme von $(basename "$ziel") weicht ab (erwartet $soll, erhalten $(sha256_von "$ARBEIT/download")) -- abgebrochen"
    exit 1
  fi
  mv "$ARBEIT/download" "$ziel"
}

herunterladen "$MAVEN/net/sf/saxon/Saxon-HE/$SAXON_VERSION/Saxon-HE-$SAXON_VERSION.jar" \
  "$CACHE_DIR/Saxon-HE-$SAXON_VERSION.jar" "$SAXON_SHA256"
herunterladen "$MAVEN/org/xmlresolver/xmlresolver/$XMLRESOLVER_VERSION/xmlresolver-$XMLRESOLVER_VERSION.jar" \
  "$CACHE_DIR/xmlresolver-$XMLRESOLVER_VERSION.jar" "$XMLRESOLVER_SHA256"
herunterladen "$MAVEN/org/xmlresolver/xmlresolver/$XMLRESOLVER_VERSION/xmlresolver-$XMLRESOLVER_VERSION-data.jar" \
  "$CACHE_DIR/xmlresolver-$XMLRESOLVER_VERSION-data.jar" "$XMLRESOLVER_DATA_SHA256"

XSLT_ZIEL="$CACHE_DIR/EN16931-CII-validation.xslt"
if pruefsumme_ok "$XSLT_ZIEL" "$EN16931_XSLT_SHA256"; then
  echo "vorhanden: $(basename "$XSLT_ZIEL")"
else
  # Gezielt den gepinnten Commit holen statt eines Branches: gleiche Regeln auf
  # jedem Rechner, unabhaengig davon, was upstream inzwischen passiert ist.
  echo "lade: $EN16931_REPO @ $EN16931_COMMIT"
  git init -q "$ARBEIT/quelle"
  git -C "$ARBEIT/quelle" fetch -q --depth 1 "$EN16931_REPO" "$EN16931_COMMIT"
  if [[ "$(git -C "$ARBEIT/quelle" rev-parse FETCH_HEAD)" != "$EN16931_COMMIT" ]]; then
    fehler "geholter Commit entspricht nicht dem gepinnten $EN16931_COMMIT -- abgebrochen"
    exit 1
  fi
  git -C "$ARBEIT/quelle" show "FETCH_HEAD:$EN16931_XSLT_PFAD" >"$ARBEIT/regeln.xslt"
  if ! pruefsumme_ok "$ARBEIT/regeln.xslt" "$EN16931_XSLT_SHA256"; then
    fehler "Pruefsumme der EN16931-Regeln weicht ab (erhalten $(sha256_von "$ARBEIT/regeln.xslt")) -- abgebrochen"
    exit 1
  fi
  mv "$ARBEIT/regeln.xslt" "$XSLT_ZIEL"
fi

# Marker, an dem pruefen.sh und die pytest-Konformitaetstests die Installation erkennen.
printf 'saxon-he %s\nxmlresolver %s\nen16931-cii-validation @ %s\n' \
  "$SAXON_VERSION" "$XMLRESOLVER_VERSION" "$EN16931_COMMIT" >"$CACHE_DIR/installiert.txt"
echo "Pruefwerkzeug bereit in $CACHE_DIR"
