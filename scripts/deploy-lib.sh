#!/usr/bin/env bash
# Funktionen des Release-Ablaufs von scripts/deploy.sh -- eigene Datei, damit der
# Ablauf mit gestubbtem docker getestet werden kann (scripts/tests/test_deploy.sh).
# Wird gesourct, nicht ausgefuehrt. Erwartet vom Aufrufer:
#   REPO_DIR   Repo-Wurzel
#   COMPOSE    Array mit dem compose-Aufruf (docker compose -f ... -f ...)
#
# Ablauf (deploy_release):
#   Backup (Abbruch bei Fehlschlag) -> Images bauen -> Datenbank + Objektspeicher
#   starten -> Migration -> Rollout -> Health-Gate (/health/ready) -> bei Fehlschlag
#   automatischer Rollback auf den vorherigen Image-Tag (.deploy-state).
# Die Migration laeuft VOR dem Rollout: scheitert sie, laeuft die alte Version
# unveraendert weiter (alembic migriert transaktional).

DEPLOY_STATE_DATEI="${DEPLOY_STATE_DATEI:-${REPO_DIR:-.}/.deploy-state}"
DEPLOY_OHNE_BACKUP="${DEPLOY_OHNE_BACKUP:-0}"
DEPLOY_HEALTH_TIMEOUT="${DEPLOY_HEALTH_TIMEOUT:-300}"
DEPLOY_HEALTH_INTERVALL="${DEPLOY_HEALTH_INTERVALL:-5}"

# Rueckgabecodes von deploy_release
DEPLOY_RC_BACKUP=10
DEPLOY_RC_MIGRATION=11
DEPLOY_RC_ROLLBACK_OK=12
DEPLOY_RC_ROLLBACK_FEHLT=13
DEPLOY_RC_BAUEN=14

_dl() { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
_dw() { printf '\033[1;33mWarnung:\033[0m %s\n' "$*" >&2; }
_de() { printf '\033[1;31mFehler:\033[0m %s\n' "$*" >&2; }

# --- Zustand (.deploy-state: KEY=VALUE, keine Geheimnisse) ------------------------------

deploy_state_lesen() { # key
  [[ -f "$DEPLOY_STATE_DATEI" ]] || return 0
  grep -E "^${1}=" "$DEPLOY_STATE_DATEI" | head -n1 | cut -d= -f2- || true
}

deploy_state_setzen() { # key value
  local tmp="$DEPLOY_STATE_DATEI.tmp"
  {
    if [[ -f "$DEPLOY_STATE_DATEI" ]]; then grep -vE "^${1}=" "$DEPLOY_STATE_DATEI" || true; fi
    printf '%s=%s\n' "$1" "$2"
  } >"$tmp"
  mv -f -- "$tmp" "$DEPLOY_STATE_DATEI"
}

deploy_image_name() { # dienst
  printf '%sfieldvibe-%s' "${IMAGE_REGISTRY:-}" "$1"
}

deploy_image_vorhanden() { # tag
  docker image inspect "$(deploy_image_name backend):$1" >/dev/null 2>&1 \
    && docker image inspect "$(deploy_image_name frontend):$1" >/dev/null 2>&1
}

# --- Bausteine ---------------------------------------------------------------------------

# Prueft vor jeder Aenderung, ob ein Deployment ueberhaupt gelingen kann.
deploy_vorabcheck() {
  local frei_mb mindest="${DEPLOY_MIN_FREI_MB:-2048}"
  if ! docker info >/dev/null 2>&1; then
    _de "Der Docker-Daemon ist nicht erreichbar."
    return 1
  fi
  if ! "${COMPOSE[@]}" config -q >/dev/null 2>&1; then
    _de "Die Compose-Konfiguration ist ungueltig (fehlende .env-Werte oder Syntaxfehler): ${COMPOSE[*]} config"
    return 1
  fi
  frei_mb="$(df -Pm "${DEPLOY_DISK_PFAD:-/var/lib/docker}" 2>/dev/null | awk 'NR==2 {print $4}')"
  [[ -n "$frei_mb" ]] || frei_mb="$(df -Pm "$REPO_DIR" | awk 'NR==2 {print $4}')"
  if [[ -n "$frei_mb" && "$frei_mb" -lt "$mindest" ]]; then
    _de "Zu wenig freier Plattenplatz: ${frei_mb} MB, benoetigt mindestens ${mindest} MB (Images bauen, Backup)."
    return 1
  fi
}

# Bestandsinstallation ohne .deploy-state: die gerade laufenden Images unter einem Tag
# festhalten, damit schon das ERSTE Update mit dem neuen Skript zurueckrollbar ist.
deploy_vorgaenger_sichern() {
  [[ -z "$(deploy_state_lesen CURRENT_TAG)" ]] || return 0
  local be fe tag
  be="$("${COMPOSE[@]}" ps -q backend 2>/dev/null | head -n1 || true)"
  fe="$("${COMPOSE[@]}" ps -q frontend 2>/dev/null | head -n1 || true)"
  [[ -n "$be" && -n "$fe" ]] || return 0
  tag="vorher-$(date +%Y%m%d%H%M%S)"
  if docker tag "$(docker inspect -f '{{.Image}}' "$be")" "$(deploy_image_name backend):$tag" \
    && docker tag "$(docker inspect -f '{{.Image}}' "$fe")" "$(deploy_image_name frontend):$tag"; then
    deploy_state_setzen CURRENT_TAG "$tag"
    _dl "Laufender Stand als Rollback-Ziel gesichert (Tag $tag)."
  else
    _dw "Der laufende Stand liess sich nicht als Rollback-Ziel sichern -- das erste Update ist nicht automatisch zurueckrollbar."
  fi
}

deploy_backup() {
  if [[ "$DEPLOY_OHNE_BACKUP" == "1" ]]; then
    _dw "Backup uebersprungen (--ohne-backup): bei einer fehlgeschlagenen Migration gibt es keinen frischen Wiederherstellungspunkt."
    return 0
  fi
  if [[ -z "$("${COMPOSE[@]}" ps -q postgres 2>/dev/null || true)" ]]; then
    _dl "Noch keine laufende Datenbank (Erstinstallation) -- kein Backup noetig."
    return 0
  fi
  _dl "Sichere Datenbank, Objektspeicher und Secrets vor dem Update (scripts/backup.sh)..."
  if ! "$REPO_DIR/scripts/backup.sh"; then
    _de "Backup fehlgeschlagen -- Deployment abgebrochen, es wurde nichts veraendert."
    _de "Ursache beheben (Log oben) und erneut starten; nur wenn bewusst gewollt: --ohne-backup."
    return 1
  fi
}

deploy_letzter_backup_stamp() {
  local dir datei
  dir="$(grep -E '^BACKUP_DIR=' "$REPO_DIR/.env" 2>/dev/null | head -n1 | cut -d= -f2- || true)"
  datei="${dir:-/opt/fieldvibe-backups}/letzter-lauf.json"
  [[ -f "$datei" ]] || return 0
  sed -n 's/.*"stamp": *"\([^"]*\)".*/\1/p' "$datei" | head -n1
}

deploy_bauen() { # tag
  IMAGE_TAG="$1" "${COMPOSE[@]}" build backend frontend worker
}

deploy_infrastruktur() { # tag
  IMAGE_TAG="$1" "${COMPOSE[@]}" up -d postgres minio
}

deploy_migrieren() { # tag
  # Worker ruhend stellen: keine Jobs gegen ein halb migriertes Schema.
  "${COMPOSE[@]}" stop worker >/dev/null 2>&1 || true
  IMAGE_TAG="$1" "$REPO_DIR/scripts/migrieren.sh" --compose "${COMPOSE[*]}"
}

deploy_ausrollen() { # tag
  IMAGE_TAG="$1" "${COMPOSE[@]}" up -d --no-build --remove-orphans
}

# Wartet, bis Backend (/health/ready: DB, Objektspeicher, Migrationsstand), Worker
# (Heartbeat) und Frontend antworten. 0 = gesund, 1 = Zeitueberschreitung.
deploy_gate() {
  local ende=$((SECONDS + DEPLOY_HEALTH_TIMEOUT)) fehlt
  while :; do
    fehlt=""
    "${COMPOSE[@]}" exec -T backend python -m app.healthcheck backend >/dev/null 2>&1 || fehlt+=" backend"
    "${COMPOSE[@]}" exec -T worker python -m app.healthcheck worker >/dev/null 2>&1 || fehlt+=" worker"
    "${COMPOSE[@]}" exec -T frontend wget -q --spider http://127.0.0.1:4173/ >/dev/null 2>&1 || fehlt+=" frontend"
    [[ -z "$fehlt" ]] && return 0
    if (( SECONDS >= ende )); then
      _de "Health-Gate nach ${DEPLOY_HEALTH_TIMEOUT}s nicht bestanden. Nicht bereit:${fehlt}"
      "${COMPOSE[@]}" logs --tail 40 backend worker 2>&1 | sed 's/^/    | /' >&2 || true
      return 1
    fi
    sleep "$DEPLOY_HEALTH_INTERVALL"
  done
}

deploy_rollback() { # vorheriger tag
  local vorher="$1"
  if [[ -z "$vorher" ]]; then
    _dw "Kein vorheriger Stand bekannt (Erstinstallation) -- kein automatischer Rollback moeglich."
    return 2
  fi
  if ! deploy_image_vorhanden "$vorher"; then
    _dw "Die Images des vorherigen Stands ($vorher) sind nicht mehr vorhanden (docker image prune?) -- kein automatischer Rollback moeglich."
    return 2
  fi
  _dl "Rollback auf den vorherigen Stand ($vorher)..."
  deploy_ausrollen "$vorher" || return 1
  deploy_gate
}

deploy_hinweis_migration() { # backup-stamp
  _dw "Die Datenbank-Migrationen dieses Releases wurden bereits angewendet und NICHT zurueckgerollt."
  _dw "Waren sie abwaertskompatibel (nur hinzufuegen -- die Regel), laeuft die alte Version damit weiter."
  _dw "Sonst: Datenbank aus dem Backup vor dem Update wiederherstellen${1:+ (Stamp $1)}:"
  _dw "  scripts/restore.sh db --stamp ${1:-<stamp>}     (Ablauf: docs/BETRIEB.md, \"Migration scheitert\")"
}

# Gesamtablauf. $1 = neuer Image-Tag (Git-SHA). Rueckgabe siehe DEPLOY_RC_*.
deploy_release() {
  local neu="$1" vorher stamp
  deploy_vorgaenger_sichern
  vorher="$(deploy_state_lesen CURRENT_TAG)"

  # deploy.sh sichert schon vor der Rollen-Umstellung (DEPLOY_BACKUP_ERLEDIGT=1).
  if [[ "${DEPLOY_BACKUP_ERLEDIGT:-0}" != "1" ]]; then deploy_backup || return "$DEPLOY_RC_BACKUP"; fi
  stamp="$(deploy_letzter_backup_stamp)"

  _dl "Baue Images (Tag $neu)..."
  deploy_bauen "$neu" || { _de "Build fehlgeschlagen -- die laufende Version ist unveraendert."; return "$DEPLOY_RC_BAUEN"; }
  deploy_infrastruktur "$neu" || { _de "Datenbank/Objektspeicher liessen sich nicht starten."; return "$DEPLOY_RC_BAUEN"; }

  _dl "Wende Datenbank-Migrationen an (vor dem Rollout)..."
  if ! deploy_migrieren "$neu"; then
    _de "Migration fehlgeschlagen -- es wurde NICHT ausgerollt, die laufende Version bleibt aktiv."
    if [[ -n "$vorher" ]] && deploy_image_vorhanden "$vorher"; then
      IMAGE_TAG="$vorher" "${COMPOSE[@]}" up -d --no-build worker >/dev/null 2>&1 || true
    fi
    _dw "Alembic migriert transaktional; nach einem Fehler steht die Datenbank meist unveraendert da."
    _dw "Pruefen: scripts/migrieren.sh current; bei Zweifel Backup${stamp:+ (Stamp $stamp)} einspielen (docs/BETRIEB.md)."
    return "$DEPLOY_RC_MIGRATION"
  fi

  _dl "Rolle aus (Tag $neu)..."
  local gate_ok=0
  if deploy_ausrollen "$neu"; then
    _dl "Warte auf das Health-Gate (/health/ready, bis ${DEPLOY_HEALTH_TIMEOUT}s)..."
    deploy_gate && gate_ok=1
  else
    _de "Rollout fehlgeschlagen."
  fi

  if [[ "$gate_ok" == "1" ]]; then
    [[ -n "$vorher" && "$vorher" != "$neu" ]] && deploy_state_setzen PREVIOUS_TAG "$vorher"
    deploy_state_setzen CURRENT_TAG "$neu"
    deploy_state_setzen DEPLOYED_AT "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    deploy_state_setzen BACKUP_STAMP "${stamp:-}"
    _dl "Release $neu ist gesund."
    return 0
  fi

  deploy_hinweis_migration "$stamp"
  if deploy_rollback "$vorher"; then
    deploy_state_setzen FEHLGESCHLAGEN_TAG "$neu"
    _dw "Automatischer Rollback auf $vorher erfolgreich -- Release $neu ist NICHT live."
    return "$DEPLOY_RC_ROLLBACK_OK"
  fi
  _de "Rollback nicht moeglich oder ebenfalls fehlgeschlagen -- manuell eingreifen (docs/BETRIEB.md)."
  return "$DEPLOY_RC_ROLLBACK_FEHLT"
}
