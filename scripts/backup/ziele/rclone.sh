#!/usr/bin/env bash
# Ziel-Adapter "rclone": jeder von rclone unterstuetzte Anbieter (S3, Backblaze B2,
# Hetzner Storage Box via SFTP/WebDAV, Nextcloud, GCS, Azure ...). Das Remote
# vorher einmalig mit "rclone config" auf diesem Server einrichten.
# Konfiguration: BACKUP_TARGETS="rclone:hetzner:fieldvibe-backups"
# Wird von ziel_aufruf() zusammen mit lib.sh gesourct -- nicht direkt ausfuehren.

# $1 = Ziel, $2 = Dateiname -> Remote-Pfad; "remote:" (Wurzel) braucht keinen Slash.
_rc_pfad() {
  local ziel="${1%/}"
  case "$ziel" in
    *:) printf '%s%s' "$ziel" "$2" ;;
    *)  printf '%s/%s' "$ziel" "$2" ;;
  esac
}

ziel_pruefen() {
  local ziel="$1" remote envname
  command -v rclone >/dev/null 2>&1 || { fehler "rclone ist nicht installiert (https://rclone.org/install/)."; return 1; }
  [[ -n "$ziel" ]] || { fehler "rclone: Ziel fehlt (rclone:<remote>:<pfad>)."; return 1; }
  if [[ "$ziel" =~ ^([A-Za-z0-9_.-]+): ]]; then
    remote="${BASH_REMATCH[1]}"
    if ! rclone listremotes 2>/dev/null | grep -qx -- "$remote:"; then
      envname="$(printf '%s' "$remote" | tr 'a-z.-' 'A-Z__')"
      if [[ -z "$(printenv "RCLONE_CONFIG_${envname}_TYPE" || true)" ]]; then
        fehler "rclone-Remote '$remote' ist nicht konfiguriert (einrichten mit 'rclone config', pruefen mit 'rclone listremotes')."
        return 1
      fi
    fi
  fi
}

ziel_hochladen() {
  local ziel="$1" quelle="$2" stamp="$3" f manifest=""
  shopt -s nullglob
  local -a dateien=("$quelle"/*-"$stamp".*)
  (( ${#dateien[@]} > 0 )) || { fehler "rclone: keine Dateien fuer Stamp $stamp in $quelle."; return 1; }
  rclone mkdir "$ziel" || { fehler "rclone: Zielverzeichnis $ziel nicht erreichbar/anlegbar."; return 1; }
  for f in "${dateien[@]}"; do
    if [[ "$(basename "$f")" == manifest-* ]]; then manifest="$f"; continue; fi
    rclone copyto "$f" "$(_rc_pfad "$ziel" "$(basename "$f")")" || { fehler "rclone: Upload von $(basename "$f") fehlgeschlagen."; return 1; }
  done
  [[ -n "$manifest" ]] || { fehler "rclone: Manifest fehlt im Sicherungssatz $stamp."; return 1; }
  rclone copyto "$manifest" "$(_rc_pfad "$ziel" "$(basename "$manifest")")" || { fehler "rclone: Upload des Manifests fehlgeschlagen."; return 1; }
}

ziel_auflisten() {
  local liste
  liste="$(rclone lsf --files-only "$1")" || { fehler "rclone: Auflisten von $1 fehlgeschlagen."; return 1; }
  satz_stamps_vollstaendig <<<"$liste"
}

# $4 (optional) = db|minio|secrets|alle: nur diese Art plus Manifest holen.
ziel_herunterladen() {
  local ziel="$1" stamp="$2" verz="$3" art="${4:-alle}" liste name
  liste="$(rclone lsf --files-only "$ziel")" || { fehler "rclone: Auflisten von $ziel fehlgeschlagen."; return 1; }
  grep -qx -- "manifest-$stamp.json" <<<"$liste" \
    || { fehler "rclone: Sicherungssatz $stamp in $ziel nicht vorhanden oder unvollstaendig (Manifest fehlt)."; return 1; }
  mkdir -p -- "$verz"
  while IFS= read -r name; do
    [[ "$name" == *-"$stamp".* ]] || continue
    art_passt "$art" "$name" || continue
    rclone copyto "$(_rc_pfad "$ziel" "$name")" "$verz/$name" || { fehler "rclone: Download von $name fehlgeschlagen."; return 1; }
  done <<<"$liste"
}

ziel_aufraeumen() {
  local ziel="$1" liste name
  local -a loeschen=()
  liste="$(rclone lsf --files-only "$ziel")" || { fehler "rclone: Auflisten von $ziel fehlgeschlagen."; return 1; }
  mapfile -t loeschen < <(rotation_plan "$2" "$3" <<<"$liste")
  for name in ${loeschen[@]+"${loeschen[@]}"}; do
    rclone deletefile "$(_rc_pfad "$ziel" "$name")" || { fehler "rclone: Loeschen von $name fehlgeschlagen."; return 1; }
    log "Rotation: $name auf $ziel geloescht."
  done
}
