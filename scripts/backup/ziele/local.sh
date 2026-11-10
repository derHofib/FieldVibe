#!/usr/bin/env bash
# Ziel-Adapter "local": zusaetzliches lokales oder gemountetes Verzeichnis
# (NFS, USB-Platte, SMB-Mount). Konfiguration: BACKUP_TARGETS="local:/mnt/nas/fieldvibe".
# Wird von ziel_aufruf() zusammen mit lib.sh gesourct -- nicht direkt ausfuehren.

ziel_pruefen() {
  local verz="$1"
  if [[ -z "$verz" || "$verz" != /* ]]; then
    fehler "local: braucht einen absoluten Verzeichnispfad (local:/pfad), ist: '$verz'"
    return 1
  fi
  mkdir -p -- "$verz" 2>/dev/null || { fehler "local: Verzeichnis $verz laesst sich nicht anlegen (gemountet?)."; return 1; }
  [[ -w "$verz" ]] || { fehler "local: Verzeichnis $verz ist nicht beschreibbar."; return 1; }
}

# Kopie unter Hilfsnamen, dann umbenennen: ein abgebrochener Lauf hinterlaesst
# nie eine halbe Datei unter dem endgueltigen Namen.
_local_kopieren() {
  local quelle="$1" verz="$2" name
  name="$(basename "$quelle")"
  if ! cp -- "$quelle" "$verz/.$name.part" || ! mv -f -- "$verz/.$name.part" "$verz/$name"; then
    rm -f -- "$verz/.$name.part"
    fehler "local: Kopieren von $name nach $verz fehlgeschlagen."
    return 1
  fi
}

ziel_hochladen() {
  local verz="$1" quelle="$2" stamp="$3" f manifest=""
  shopt -s nullglob
  local -a dateien=("$quelle"/*-"$stamp".*)
  (( ${#dateien[@]} > 0 )) || { fehler "local: keine Dateien fuer Stamp $stamp in $quelle."; return 1; }
  for f in "${dateien[@]}"; do
    if [[ "$(basename "$f")" == manifest-* ]]; then manifest="$f"; continue; fi
    _local_kopieren "$f" "$verz" || return 1
  done
  [[ -n "$manifest" ]] || { fehler "local: Manifest fehlt im Sicherungssatz $stamp."; return 1; }
  _local_kopieren "$manifest" "$verz"
}

ziel_auflisten() {
  [[ -d "$1" ]] || { fehler "local: Verzeichnis $1 existiert nicht."; return 1; }
  find "$1" -maxdepth 1 -type f -printf '%f\n' | satz_stamps_vollstaendig
}

# $4 (optional) = db|minio|secrets|alle: nur diese Art plus Manifest holen.
ziel_herunterladen() {
  local verz="$1" stamp="$2" ziel="$3" art="${4:-alle}" f name
  [[ -f "$verz/manifest-$stamp.json" ]] || { fehler "local: Sicherungssatz $stamp in $verz nicht vorhanden oder unvollstaendig (Manifest fehlt)."; return 1; }
  mkdir -p -- "$ziel"
  shopt -s nullglob
  for f in "$verz"/*-"$stamp".*; do
    name="$(basename "$f")"
    art_passt "$art" "$name" || continue
    cp -- "$f" "$ziel/$name" || return 1
  done
}

ziel_aufraeumen() {
  [[ -d "$1" ]] || { fehler "local: Verzeichnis $1 existiert nicht."; return 1; }
  lokal_aufraeumen "$1" "$2" "$3"
}
