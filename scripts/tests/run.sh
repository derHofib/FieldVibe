#!/usr/bin/env bash
set -euo pipefail

# Fuehrt alle Shell-Tests der Backup-Skripte aus (test_*.sh in diesem
# Verzeichnis). Braucht weder Docker noch bats. Usage:
#   bash scripts/tests/run.sh [test_name.sh ...]
# FV_BEHALTE=1 behaelt die Temp-Verzeichnisse der Szenarien zur Fehlersuche.

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/tests/helfer.sh
source "$TESTS_DIR/helfer.sh"

BASIS="$(mktemp -d "${TMPDIR:-/tmp}/fvtests.XXXXXX")"
FV_ERGEBNIS="$BASIS/ergebnis"
export FV_ERGEBNIS
: >"$FV_ERGEBNIS"

beenden() {
  if [[ -n "${FV_GNUPGHOME:-}" ]]; then
    GNUPGHOME="$FV_GNUPGHOME" gpgconf --kill all >/dev/null 2>&1 || true
    GNUPGHOME="${FV_GNUPGHOME_NURPUB:-}" gpgconf --kill all >/dev/null 2>&1 || true
  fi
  rm -rf "$BASIS"
}
trap beenden EXIT

if gpg_testschluessel_erzeugen "$BASIS"; then
  echo "GPG-Testschluessel erzeugt."
else
  echo "Hinweis: gpg nicht verfuegbar oder Schluessel nicht erzeugbar -- GPG-Szenarien werden uebersprungen."
fi

if [[ $# -gt 0 ]]; then
  tests=("$@")
else
  mapfile -t tests < <(cd "$TESTS_DIR" && ls test_*.sh)
fi

rc=0
for t in "${tests[@]}"; do
  echo "== $t"
  bash "$TESTS_DIR/$t" || rc=1
done

szenarien=0; pruefungen=0; fehler=0; skips=0
while read -r a b c d; do
  szenarien=$((szenarien + a)); pruefungen=$((pruefungen + b)); fehler=$((fehler + c)); skips=$((skips + d))
done <"$FV_ERGEBNIS"

echo
echo "Gesamt: $szenarien Szenario(en), $pruefungen Pruefung(en), $fehler Fehler, $skips SKIP"
if [[ "$rc" -ne 0 || "$fehler" -ne 0 ]]; then
  echo "FEHLGESCHLAGEN"
  exit 1
fi
echo "OK"
