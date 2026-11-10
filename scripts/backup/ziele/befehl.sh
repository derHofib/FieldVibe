#!/usr/bin/env bash
# Ziel-Adapter "befehl": bindet einen beliebigen Anbieter ueber ein eigenes
# Programm (jede Sprache) ein, ohne das Repo zu aendern.
# Konfiguration: BACKUP_TARGETS="befehl:/opt/mein-adapter.sh"
#
# Das Programm wird mit einem Unterbefehl aufgerufen (die Konfiguration aus .env
# steht als Umgebungsvariablen zur Verfuegung):
#   pruefen                                   Konfiguration/Erreichbarkeit pruefen
#   hochladen <verzeichnis> <stamp>           alle Dateien *-<stamp>.* hochladen, Manifest zuletzt
#   auflisten                                 vollstaendige Stamps ausgeben, einer je Zeile, neueste zuletzt
#   herunterladen <stamp> <zielverz> [art]    Satz holen (art: db|minio|secrets|alle)
#   aufraeumen <behalte_tage> <mindestens>    Rotation (siehe docs/DEPLOYMENT.md)
# Exit-Code != 0 = Fehler (Meldungen auf stderr, auflisten schreibt NUR Stamps auf stdout).
# Wird von ziel_aufruf() zusammen mit lib.sh gesourct -- nicht direkt ausfuehren.
#
# Das Ziel selbst ist das Programm; es bekommt deshalb nicht noch einmal seinen
# eigenen Pfad als Argument.

_befehl_programm_pruefen() {
  if [[ "$1" != /* || ! -f "$1" || ! -x "$1" ]]; then
    fehler "befehl: '$1' ist keine ausfuehrbare Datei mit absolutem Pfad (chmod +x?)."
    return 1
  fi
}

ziel_pruefen() {
  _befehl_programm_pruefen "$1" || return 1
  "$1" pruefen
}

ziel_hochladen() {
  _befehl_programm_pruefen "$1" || return 1
  "$1" hochladen "$2" "$3"
}

# Nur Zeilen im Stamp-Format durchlassen: schuetzt vor Begleitausgaben des Programms.
ziel_auflisten() {
  local ausgabe
  _befehl_programm_pruefen "$1" || return 1
  ausgabe="$("$1" auflisten)" || return 1
  { grep -E '^[0-9]{8}-[0-9]{6}$' <<<"$ausgabe" || true; } | sort -u
}

ziel_herunterladen() {
  _befehl_programm_pruefen "$1" || return 1
  "$1" herunterladen "$2" "$3" "${4:-alle}"
}

ziel_aufraeumen() {
  _befehl_programm_pruefen "$1" || return 1
  "$1" aufraeumen "$2" "$3"
}
