#!/usr/bin/env bash
# Gemeinsame Funktionen fuer scripts/backup.sh, restore.sh und backup-pruefen.sh.
# Wird nur gesourct und tut beim Laden nichts. Alle Funktionen, die Docker,
# Postgres oder MinIO anfassen (db_*, minio_*, app_dienste_*), sind einzeln
# benannt, damit ein Test sie nach dem Sourcen ueberschreiben kann.
#
# Meldungen gehen auf stderr; stdout gehoert den Daten (z.B. ziel_auflisten).

BACKUP_LIB_DATEI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
BACKUP_LIB_DIR="$(dirname "$BACKUP_LIB_DATEI")"
# Exportiert, damit ein "befehl:"-Adapterprogramm die Hilfsfunktionen (z.B.
# rotation_plan) per "source" mitbenutzen kann.
export BACKUP_LIB_DATEI

# --- Logging ------------------------------------------------------------------
log()    { printf '[%s] %s\n' "$(date -Iseconds)" "$*" >&2; }
warn()   { printf '[%s] WARNUNG: %s\n' "$(date -Iseconds)" "$*" >&2; }
fehler() { printf '[%s] FEHLER: %s\n' "$(date -Iseconds)" "$*" >&2; }

json_str() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '%s' "$s"
}

# --- Konfiguration ------------------------------------------------------------

# $1 = "optional": fehlende .env nur warnen (z.B. restore.sh secrets auf einem
# frischen Server, wo die .env ja erst wiederhergestellt werden soll).
backup_env_laden() {
  local datei="${BACKUP_ENV_DATEI:-$REPO_DIR/.env}"
  if [[ -f "$datei" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$datei"
    set +a
  elif [[ "${1:-}" == "optional" ]]; then
    warn ".env nicht gefunden ($datei) -- es gelten nur Umgebungsvariablen und Standardwerte."
  else
    fehler ".env nicht gefunden: $datei"
    return 1
  fi
}

# Setzt BACKUP_DIR, BACKUP_RETENTION_DAYS, BACKUP_MIN_KEEP und das Array
# BACKUP_ZIELE (Eintraege "<typ>:<ziel>").
backup_konfig_auswerten() {
  BACKUP_DIR="${BACKUP_DIR:-$REPO_DIR/backups}"
  BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
  BACKUP_MIN_KEEP="${BACKUP_MIN_KEEP:-3}"
  export BACKUP_DIR BACKUP_RETENTION_DAYS BACKUP_MIN_KEEP

  if ! [[ "$BACKUP_RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
    fehler "BACKUP_RETENTION_DAYS muss eine ganze Zahl sein (ist: '$BACKUP_RETENTION_DAYS')."
    return 1
  fi
  if ! [[ "$BACKUP_MIN_KEEP" =~ ^[0-9]+$ ]] || (( BACKUP_MIN_KEEP < 1 )); then
    fehler "BACKUP_MIN_KEEP muss eine ganze Zahl >= 1 sein (ist: '$BACKUP_MIN_KEEP')."
    return 1
  fi

  BACKUP_ZIELE=()
  local roh="${BACKUP_TARGETS:-}"
  if [[ -z "${roh//[[:space:],]/}" && -n "${BACKUP_OFFSITE_REMOTE:-}" ]]; then
    warn "BACKUP_OFFSITE_REMOTE ist veraltet -- verwende stattdessen BACKUP_TARGETS=\"rclone:${BACKUP_OFFSITE_REMOTE}\". Bis dahin wird es automatisch so behandelt."
    roh="rclone:${BACKUP_OFFSITE_REMOTE}"
  fi
  roh="${roh//,/ }"
  local -a eintraege=()
  read -r -a eintraege <<<"$roh"
  local eintrag
  for eintrag in ${eintraege[@]+"${eintraege[@]}"}; do
    if ! [[ "$eintrag" =~ ^[a-z0-9_-]+:.+$ ]]; then
      fehler "Ungueltiges Backup-Ziel '$eintrag' in BACKUP_TARGETS (erwartet: <typ>:<ziel>, z.B. rclone:hetzner:fieldvibe-backups)."
      return 1
    fi
    BACKUP_ZIELE+=("$eintrag")
  done
}

# shellcheck disable=SC2034  # ZIEL_TYP/ZIEL_PFAD werden von den aufrufenden Skripten gelesen
ziel_zerlegen() {
  ZIEL_TYP="${1%%:*}"
  ZIEL_PFAD="${1#*:}"
}

ziel_ist_remote() { [[ "$1" != "local" ]]; }

ziel_typ_bekannt() {
  [[ "$1" =~ ^[a-z0-9_-]+$ && -f "${BACKUP_ZIELE_DIR:-$BACKUP_LIB_DIR/ziele}/$1.sh" ]]
}

# Jeder Adapter definiert dieselben Funktionsnamen -- deshalb laeuft jeder Aufruf
# in einem eigenen bash-Prozess mit frischem "set -e" (auch wenn der Aufrufer
# in einem if/|| steht, wo set -e sonst abgeschaltet waere). fd 9 (Sperre aus
# backup.sh) wird geschlossen, damit ein vom Adapter gestarteter Dienst sie
# nicht ueber das Skriptende hinaus festhaelt.
ziel_aufruf() {
  local typ="$1" funktion="$2"
  shift 2
  local adapter="${BACKUP_ZIELE_DIR:-$BACKUP_LIB_DIR/ziele}/$typ.sh"
  if ! ziel_typ_bekannt "$typ"; then
    fehler "Unbekannter Zieltyp '$typ' (erwartet wird eine Datei $adapter)."
    return 2
  fi
  "$BASH" -c 'set -euo pipefail; source "$1"; source "$2"; shift 2; "$@"' \
    _ "$BACKUP_LIB_DATEI" "$adapter" "ziel_$funktion" "$@" 9>&-
}

# --- Datenbank/MinIO (Docker, hier einzeln ueberschreibbar) ----------------------

db_dump() {
  docker compose exec -T postgres pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB" </dev/null
}

db_version() {
  docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atq \
    -c 'SHOW server_version' </dev/null 2>/dev/null || true
}

# $1 = Datenbank, $2 = SQL
db_sql() {
  docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$1" -Atq -v ON_ERROR_STOP=1 \
    -c "$2" </dev/null
}

# stdin = Custom-Format-Dump, $1 = Ziel-Datenbank, Rest = pg_restore-Optionen
db_restore_stream() {
  local db="$1"
  shift
  docker compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$db" "$@"
}

# stdin = Plain-SQL (Altformat), $1 = Ziel-Datenbank
db_restore_sql_stream() {
  docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$1" -q \
    -v ON_ERROR_STOP=1 --single-transaction
}

# stdout = MinIO-Datenverzeichnis als tar.gz. --volumes-from statt "exec minio
# tar": das MinIO-Image bringt kein garantiertes tar/sh mit, ein separater
# Alpine-Container mit geteiltem Volume ist unabhaengig vom Image-Inhalt.
minio_archiv() {
  local cid
  cid="$(docker compose ps -q minio)"
  if [[ -z "$cid" ]]; then
    fehler "MinIO-Container nicht gefunden (laeuft der Stack? 'docker compose ps minio')."
    return 1
  fi
  docker run --rm --volumes-from "$cid" alpine tar czf - -C /data .
}

# $1 = tar.gz-Datei. Leert /data inkl. versteckter Eintraege (.minio.sys!) --
# "rm -rf /data/*" liesse die alten Metadaten stehen.
minio_wiederherstellen() {
  local abs cid
  abs="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
  docker compose stop minio || return 1
  cid="$(docker compose ps -a -q minio)"
  if [[ -z "$cid" ]]; then
    fehler "MinIO-Container nicht gefunden."
    return 1
  fi
  docker run --rm --volumes-from "$cid" -v "$abs":/backup.tar.gz:ro alpine \
    sh -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} + && tar xzf /backup.tar.gz -C /data' || return 1
  docker compose start minio
}

app_dienste_stoppen()  { docker compose stop backend worker; }
app_dienste_starten()  { docker compose start backend worker; }

# --- Dateien: Pruefsummen, Verschluesselung -------------------------------------

datei_sha256() { sha256sum -- "$1" | cut -d' ' -f1; }
datei_groesse() { wc -c <"$1" | tr -d ' '; }

# $1 = Klartextdatei -> $1.gpg, Klartext wird geloescht. Ob verschluesselt
# werden soll, entscheidet der Aufrufer.
datei_verschluesseln() {
  if ! gpg --batch --yes --trust-model always --encrypt \
      --recipient "$BACKUP_GPG_RECIPIENT" --output "$1.gpg" "$1" 9>&-; then
    rm -f -- "$1.gpg"
    fehler "GPG-Verschluesselung von $(basename "$1") fehlgeschlagen (Schluessel für '$BACKUP_GPG_RECIPIENT' importiert?)."
    return 1
  fi
  rm -f -- "$1"
}

# $1 = .gpg-Datei, $2 = Ausgabedatei
datei_entschluesseln() {
  if ! gpg --batch --yes --decrypt --output "$2" "$1" 9>&-; then
    rm -f -- "$2"
    fehler "Entschluesselung von $(basename "$1") fehlgeschlagen -- der private GPG-Schluessel muss im Schluesselbund dieses Nutzers liegen."
    return 1
  fi
}

gpg_privater_schluessel_vorhanden() {
  gpg --batch --list-secret-keys --with-colons 2>/dev/null | grep -q '^sec:'
}

# --- Sicherungssatz ---------------------------------------------------------------

# Dateiname je Art ("db", "minio", "secrets") fuer einen Stamp in $1 suchen;
# Reihenfolge: verschluesselt vor unverschluesselt, neues Format vor Altformat.
satz_dateiname() {
  local verz="$1" stamp="$2" art="$3" kandidat
  local -a kandidaten
  case "$art" in
    db)      kandidaten=("db-$stamp.dump.gpg" "db-$stamp.dump" "db-$stamp.sql.gz.gpg" "db-$stamp.sql.gz") ;;
    minio)   kandidaten=("minio-$stamp.tar.gz.gpg" "minio-$stamp.tar.gz") ;;
    secrets) kandidaten=("secrets-$stamp.tar.gpg" "secrets-$stamp.tar") ;;
    *) return 2 ;;
  esac
  for kandidat in "${kandidaten[@]}"; do
    if [[ -f "$verz/$kandidat" ]]; then
      printf '%s\n' "$kandidat"
      return 0
    fi
  done
  return 1
}

stamp_aus_dateiname() {
  local n
  n="$(basename "$1")"
  if [[ "$n" =~ ^(db|minio|secrets|manifest)-([0-9]{8}-[0-9]{6})\. ]]; then
    printf '%s\n' "${BASH_REMATCH[2]}"
  else
    return 1
  fi
}

# Welche Dateien eines Satzes ein Adapter beim Herunterladen holt: das Manifest
# immer, sonst nur die gewuenschte Art ("alle" = alles).
art_passt() {
  local art="${1:-alle}" name="$2"
  [[ "$art" == "alle" || "$name" == manifest-* || "$name" == "$art"-* ]]
}

# $1 = Verzeichnis, $2 = Stamp, $3.. = Dateinamen (relativ zu $1). Nur die
# Dateien, die an Remote-Ziele gehen duerfen -- das Klartext-Secrets-Buendel
# gehoert nie dazu und taucht deshalb im Manifest nicht auf.
manifest_schreiben() {
  local verz="$1" stamp="$2"
  shift 2
  local ziel="$verz/manifest-$stamp.json" name i=0 n=$# commit pgv verschl="false"
  commit="$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || true)"
  pgv="$(db_version)"
  [[ -n "${BACKUP_GPG_RECIPIENT:-}" ]] && verschl="true"
  {
    printf '{\n'
    printf '  "format_version": 1,\n'
    printf '  "stamp": "%s",\n' "$stamp"
    printf '  "erstellt": "%s",\n' "$(date -Iseconds)"
    if [[ -n "$commit" ]]; then printf '  "git_commit": "%s",\n' "$(json_str "$commit")"; else printf '  "git_commit": null,\n'; fi
    if [[ -n "$pgv" ]]; then printf '  "postgres_version": "%s",\n' "$(json_str "$pgv")"; else printf '  "postgres_version": null,\n'; fi
    printf '  "verschluesselt": %s,\n' "$verschl"
    printf '  "dateien": [\n'
    for name in "$@"; do
      i=$((i + 1))
      printf '    {"name": "%s", "groesse": %s, "sha256": "%s"}' \
        "$(json_str "$name")" "$(datei_groesse "$verz/$name")" "$(datei_sha256 "$verz/$name")"
      if (( i < n )); then printf ',\n'; else printf '\n'; fi
    done
    printf '  ]\n}\n'
  } >"$ziel.tmp" || { rm -f -- "$ziel.tmp"; return 1; }
  mv -f -- "$ziel.tmp" "$ziel"
}

# stdout: "<sha256><TAB><groesse><TAB><name>" je Datei des Manifests.
manifest_eintraege() {
  sed -n 's/.*"name": *"\([^"]*\)", *"groesse": *\([0-9]*\), *"sha256": *"\([0-9a-f]*\)".*/\3\t\2\t\1/p' "$1"
}

# Prueft die Dateien aus manifest-<stamp>.json in $1 gegen Groesse und SHA-256.
# $3 = Glob ueber Dateinamen (Default *); nur passende Eintraege werden
# geprueft, sie muessen dann aber vorhanden sein.
# Rueckgabe: 0 ok, 1 Abweichung/Fehler, 2 kein passender Eintrag im Manifest.
manifest_pruefen() {
  local verz="$1" stamp="$2" muster="${3:-*}"
  local manifest="$verz/manifest-$stamp.json" sha groesse name geprueft=0 schlecht=0
  if [[ ! -f "$manifest" ]]; then
    fehler "Manifest fehlt: manifest-$stamp.json"
    return 1
  fi
  if ! grep -q '"format_version": *1,' "$manifest"; then
    fehler "Unbekannte Backup-Format-Version in manifest-$stamp.json (erwartet: 1)."
    return 1
  fi
  while IFS=$'\t' read -r sha groesse name; do
    # shellcheck disable=SC2053
    [[ "$name" == $muster ]] || continue
    geprueft=$((geprueft + 1))
    if [[ ! -f "$verz/$name" ]]; then
      fehler "Datei laut Manifest vorhanden, aber nicht gefunden: $name"
      schlecht=1
    elif [[ "$(datei_groesse "$verz/$name")" != "$groesse" ]]; then
      fehler "Groesse stimmt nicht mit dem Manifest ueberein: $name"
      schlecht=1
    elif [[ "$(datei_sha256 "$verz/$name")" != "$sha" ]]; then
      fehler "Pruefsumme stimmt nicht mit dem Manifest ueberein: $name (Datei beschaedigt oder veraendert)"
      schlecht=1
    else
      log "Pruefsumme ok: $name"
    fi
  done < <(manifest_eintraege "$manifest")
  (( schlecht == 0 )) || return 1
  if (( geprueft == 0 )); then
    fehler "Das Manifest enthaelt keinen Eintrag, der zu '$muster' passt."
    return 2
  fi
}

# Legt den Sicherungssatz $1 (Stamp) in $BACKUP_DIR an. Setzt SATZ_UPLOAD_DATEIEN
# (Namen, die an Ziele gehen duerfen, Manifest zuletzt). Scheitert ein Schritt,
# werden alle Teile dieses Satzes wieder entfernt -- ohne Manifest zaehlt ein Satz
# ohnehin nicht als vollstaendig.
satz_erstellen() {
  local stamp="$1" verz="$BACKUP_DIR"
  local db="db-$stamp.dump" minio="minio-$stamp.tar.gz" secrets="secrets-$stamp.tar"
  SATZ_UPLOAD_DATEIEN=()

  log "Postgres-Dump (Custom-Format)..."
  if ! db_dump >"$verz/$db.tmp"; then
    fehler "Postgres-Dump fehlgeschlagen."
    rm -f -- "$verz"/*-"$stamp".*
    return 1
  fi
  # Faengt leere/fehlerhafte Ausgaben ab, die ohne Exit-Code endeten.
  if [[ "$(head -c 5 "$verz/$db.tmp")" != "PGDMP" ]]; then
    fehler "Postgres-Dump ist kein gueltiges Custom-Format (Kopfzeile PGDMP fehlt)."
    rm -f -- "$verz"/*-"$stamp".*
    return 1
  fi
  mv -f -- "$verz/$db.tmp" "$verz/$db"

  log "MinIO-Objektdaten..."
  if ! minio_archiv >"$verz/$minio.tmp"; then
    fehler "MinIO-Archiv fehlgeschlagen."
    rm -f -- "$verz"/*-"$stamp".*
    return 1
  fi
  if ! gzip -t "$verz/$minio.tmp" 2>/dev/null; then
    fehler "MinIO-Archiv ist kein lesbares gzip (leer oder abgebrochen)."
    rm -f -- "$verz"/*-"$stamp".*
    return 1
  fi
  mv -f -- "$verz/$minio.tmp" "$verz/$minio"

  # Ohne .env sind nach einem Totalverlust die SSE-verschluesselten MinIO-Objekte
  # (MINIO_KMS_SECRET_KEY) und die Integrations-Zugangsdaten in der DB
  # (INTEGRATION_SECRET_KEY) nicht mehr lesbar.
  log "Secrets-Buendel (.env)..."
  if [[ ! -f "$REPO_DIR/.env" ]] || ! tar -cf "$verz/$secrets.tmp" -C "$REPO_DIR" .env; then
    fehler "Secrets-Buendel konnte nicht erstellt werden (.env fehlt?)."
    rm -f -- "$verz"/*-"$stamp".*
    return 1
  fi
  chmod 600 "$verz/$secrets.tmp"
  mv -f -- "$verz/$secrets.tmp" "$verz/$secrets"

  local name
  local -a teile=("$db" "$minio" "$secrets")
  if [[ -n "${BACKUP_GPG_RECIPIENT:-}" ]]; then
    log "Verschluessele den Sicherungssatz fuer $BACKUP_GPG_RECIPIENT..."
    local -a verschluesselt=()
    for name in "${teile[@]}"; do
      if ! datei_verschluesseln "$verz/$name"; then
        rm -f -- "$verz"/*-"$stamp".*
        return 1
      fi
      verschluesselt+=("$name.gpg")
    done
    teile=("${verschluesselt[@]}")
  else
    # Nur das Secrets-Buendel ist zwingend zu verschluesseln: unverschluesselt
    # bleibt es lokal (0600) und wird nie uebertragen.
    teile=("$db" "$minio")
    warn "BACKUP_GPG_RECIPIENT nicht gesetzt: Das Secrets-Buendel ($secrets) bleibt unverschluesselt NUR in $verz (Rechte 0600) und wird nicht uebertragen -- ohne GPG gibt es nach einem Totalverlust keine .env aus dem Backup."
  fi

  log "Manifest mit Pruefsummen..."
  if ! manifest_schreiben "$verz" "$stamp" "${teile[@]}"; then
    fehler "Manifest konnte nicht geschrieben werden."
    rm -f -- "$verz"/*-"$stamp".*
    return 1
  fi
  SATZ_UPLOAD_DATEIEN=("${teile[@]}" "manifest-$stamp.json")
}

# Hardlinks (Fallback: Kopie) der uploadfaehigen Dateien in ein eigenes
# Verzeichnis: so sieht ein Adapter mit dem Muster *-<stamp>.* garantiert nie
# das Klartext-Secrets-Buendel.
upload_verzeichnis_erstellen() {
  local up="$1" name
  rm -rf -- "$up"
  mkdir -p -- "$up"
  for name in "${SATZ_UPLOAD_DATEIEN[@]}"; do
    ln -- "$BACKUP_DIR/$name" "$up/$name" 2>/dev/null || cp -p -- "$BACKUP_DIR/$name" "$up/$name" || return 1
  done
}

# --- Saetze erkennen und rotieren ---------------------------------------------------

# stdin: Dateinamen. stdout: "<status><TAB><stamp><TAB><name>" je erkannter Datei.
# status: vollstaendig (Manifest + DB + MinIO), alt (Altformat db-*.sql.gz ohne
# Manifest) oder unvollstaendig. Fremde Dateinamen werden ignoriert -- damit
# fasst die Rotation nie etwas an, was nicht zu einem Sicherungssatz gehoert.
satz_analyse() {
  local name stamp art rest status
  local -A dateien=() hat_manifest=() hat_db=() hat_minio=() hat_alt=()
  local -a stamps=()
  while IFS= read -r name; do
    [[ "$name" =~ ^(db|minio|secrets|manifest)-([0-9]{8}-[0-9]{6})\.(.+)$ ]] || continue
    art="${BASH_REMATCH[1]}"
    stamp="${BASH_REMATCH[2]}"
    rest="${BASH_REMATCH[3]}"
    if [[ -z "${dateien[$stamp]+x}" ]]; then
      stamps+=("$stamp")
      dateien[$stamp]=""
    fi
    dateien[$stamp]+="$name"$'\n'
    case "$art:$rest" in
      manifest:json) hat_manifest[$stamp]=1 ;;
      db:dump | db:dump.gpg) hat_db[$stamp]=1 ;;
      db:sql.gz | db:sql.gz.gpg) hat_alt[$stamp]=1 ;;
      minio:tar.gz | minio:tar.gz.gpg) hat_minio[$stamp]=1 ;;
      *) ;;
    esac
  done
  for stamp in ${stamps[@]+"${stamps[@]}"}; do
    if [[ -n "${hat_manifest[$stamp]+x}" && -n "${hat_db[$stamp]+x}" && -n "${hat_minio[$stamp]+x}" ]]; then
      status="vollstaendig"
    elif [[ -n "${hat_alt[$stamp]+x}" && -z "${hat_manifest[$stamp]+x}" ]]; then
      status="alt"
    else
      status="unvollstaendig"
    fi
    while IFS= read -r name; do
      [[ -n "$name" ]] && printf '%s\t%s\t%s\n' "$status" "$stamp" "$name"
    done <<<"${dateien[$stamp]}"
  done
  return 0
}

# stdin: Dateinamen. stdout: vollstaendige Stamps, aelteste zuerst. Ein Satz
# zaehlt nur mit Manifest (das als Letztes hochgeladen wird).
satz_stamps_vollstaendig() {
  satz_analyse | awk -F'\t' '$1 == "vollstaendig" { print $2 }' | sort -u
}

stamp_epoch() {
  date -d "${1:0:4}-${1:4:2}-${1:6:2} ${1:9:2}:${1:11:2}:${1:13:2}" +%s 2>/dev/null || date +%s
}

# $1 = behalte_tage, $2 = mindestens_behalten, stdin = Dateinamen im Ziel.
# stdout: Dateinamen, die zu loeschen sind.
#  - vollstaendige Saetze: aelter als $1 Tage, aber die neuesten $2 bleiben immer
#    (schuetzt bei langem Ausfall vor einer Rotation, die alles wegraeumt)
#  - unvollstaendige Saetze: immer (abgebrochene Laeufe)
#  - Altformat-Saetze (ohne Manifest): nach Alter, aber erst wenn mindestens $2
#    neue vollstaendige Saetze existieren -- sie waeren sonst die einzige Sicherung
rotation_plan() {
  local tage="$1" min="$2" grenze status stamp name n i
  grenze=$(( $(date +%s) - tage * 86400 ))
  local analyse
  analyse="$(satz_analyse | sort -t$'\t' -k2,2 -k3,3)"
  local -a voll=()
  mapfile -t voll < <(awk -F'\t' '$1 == "vollstaendig" { print $2 }' <<<"$analyse" | sort -u)
  n=${#voll[@]}
  local -A behalten=()
  for (( i = n - min; i < n; i++ )); do
    if (( i >= 0 )); then behalten[${voll[$i]}]=1; fi
  done
  while IFS=$'\t' read -r status stamp name; do
    [[ -n "$name" ]] || continue
    case "$status" in
      vollstaendig)
        if [[ -z "${behalten[$stamp]+x}" ]] && (( $(stamp_epoch "$stamp") < grenze )); then
          printf '%s\n' "$name"
        fi
        ;;
      unvollstaendig)
        printf '%s\n' "$name"
        ;;
      alt)
        if (( n >= min )) && (( $(stamp_epoch "$stamp") < grenze )); then
          printf '%s\n' "$name"
        fi
        ;;
      *) ;;
    esac
  done <<<"$analyse"
  return 0
}

# $1 = Verzeichnis, $2 = behalte_tage, $3 = mindestens_behalten
lokal_aufraeumen() {
  local verz="$1" name geloescht=0
  while IFS= read -r name; do
    rm -f -- "$verz/$name"
    log "Rotation: $verz/$name geloescht."
    geloescht=$((geloescht + 1))
  done < <(find "$verz" -maxdepth 1 -type f -printf '%f\n' | rotation_plan "$2" "$3")
  log "Rotation in $verz: $geloescht Datei(en) entfernt (>$2 Tage, mindestens $3 vollstaendige Saetze bleiben)."
}

# --- Ping und Benachrichtigung ---------------------------------------------------------

# $1 = URL (leer = nichts tun), $2 = Suffix ("", "/start", "/fail"). Ein
# Fehler beim Ping darf den Lauf nie scheitern lassen.
ping_senden() {
  [[ -n "${1:-}" ]] || return 0
  curl -fsS -m 10 --retry 3 -o /dev/null "${1%/}${2:-}" \
    || warn "Ping${2:+ ($2)} konnte nicht gesendet werden -- wird ignoriert."
  return 0
}

# $1 = ok|fehler, $2 = Nachricht, $3 = Stamp
benachrichtigen() {
  [[ -n "${BACKUP_BENACHRICHTIGUNG_BEFEHL:-}" ]] || return 0
  BACKUP_STATUS="$1" BACKUP_NACHRICHT="$2" BACKUP_STAMP="$3" \
    "$BASH" -c "$BACKUP_BENACHRICHTIGUNG_BEFEHL" 9>&- \
    || warn "Benachrichtigungsbefehl ist fehlgeschlagen -- wird ignoriert."
  return 0
}

# --- Status ---------------------------------------------------------------------------------

# $1 = Datei, $2 = Gesamtstatus, $3 = Stamp, $4 = Dauer in Sekunden, $5 = Meldung.
# Liest die Arrays ZIEL_NAMEN/ZIEL_STATI/ZIEL_MELDUNGEN sowie LOKAL_STATUS/
# LOKAL_MELDUNG. Atomar geschrieben, damit Monitoring nie eine halbe Datei liest.
status_schreiben() {
  local datei="$1" i n=${#ZIEL_NAMEN[@]}
  {
    printf '{\n'
    printf '  "zeitpunkt": "%s",\n' "$(date -Iseconds)"
    printf '  "stamp": "%s",\n' "$(json_str "$3")"
    printf '  "status": "%s",\n' "$2"
    printf '  "dauer_sekunden": %s,\n' "$4"
    printf '  "meldung": "%s",\n' "$(json_str "$5")"
    printf '  "lokal": {"status": "%s", "meldung": "%s"},\n' "${LOKAL_STATUS:-fehler}" "$(json_str "${LOKAL_MELDUNG:-}")"
    printf '  "ziele": ['
    for (( i = 0; i < n; i++ )); do
      (( i == 0 )) || printf ','
      printf '\n    {"ziel": "%s", "status": "%s", "meldung": "%s"}' \
        "$(json_str "${ZIEL_NAMEN[$i]}")" "${ZIEL_STATI[$i]}" "$(json_str "${ZIEL_MELDUNGEN[$i]}")"
    done
    (( n == 0 )) || printf '\n  '
    printf ']\n}\n'
  } >"$datei.tmp" && chmod 644 "$datei.tmp" && mv -f -- "$datei.tmp" "$datei"
}

# --- Test-Restore -----------------------------------------------------------------------------

# $1 = Custom-Format-Dump (entschluesselt), $2 = Stamp. Spielt ihn in eine
# Wegwerf-Datenbank restore_test_<stamp> ein und prueft sie auf Plausibilitaet.
# Die Produktions-DB wird nie angefasst; der Aufrufer loescht die Wegwerf-DB
# ueber db_testrestore_aufraeumen (Trap), auch wenn hier etwas scheitert.
db_testrestore() {
  local dump="$1" stamp="$2" tabellen anzahl_alembic version mandanten users
  TESTDB="restore_test_${stamp//-/_}"
  if ! [[ "$TESTDB" =~ ^restore_test_[0-9]{8}_[0-9]{6}$ ]] || [[ "$TESTDB" == "$POSTGRES_DB" ]]; then
    fehler "Ungueltiger Name fuer die Wegwerf-Datenbank: $TESTDB"
    TESTDB=""
    return 1
  fi
  db_sql postgres "DROP DATABASE IF EXISTS \"$TESTDB\"" >/dev/null || { TESTDB=""; return 1; }
  db_sql postgres "CREATE DATABASE \"$TESTDB\"" >/dev/null || { TESTDB=""; return 1; }
  TESTDB_ANGELEGT="$TESTDB"
  log "Spiele den Dump in die Wegwerf-Datenbank $TESTDB ein..."
  if ! db_restore_stream "$TESTDB" --exit-on-error --no-owner --no-acl <"$dump"; then
    fehler "pg_restore in die Wegwerf-Datenbank ist fehlgeschlagen."
    return 1
  fi
  tabellen="$(db_sql "$TESTDB" "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")" || return 1
  if [[ ! "$tabellen" =~ ^[0-9]+$ ]] || (( tabellen == 0 )); then
    fehler "Plausibilitaetspruefung: keine Tabellen im wiederhergestellten Schema public."
    return 1
  fi
  anzahl_alembic="$(db_sql "$TESTDB" "SELECT count(*) FROM alembic_version" 2>/dev/null)" || anzahl_alembic=""
  if [[ ! "$anzahl_alembic" =~ ^[0-9]+$ ]] || (( anzahl_alembic == 0 )); then
    fehler "Plausibilitaetspruefung: Tabelle alembic_version fehlt oder ist leer."
    return 1
  fi
  version="$(db_sql "$TESTDB" "SELECT version_num FROM alembic_version LIMIT 1")" || version="?"
  mandanten="$(db_sql "$TESTDB" "SELECT count(*) FROM mandanten" 2>/dev/null)" || mandanten=""
  users="$(db_sql "$TESTDB" "SELECT count(*) FROM users" 2>/dev/null)" || users=""
  if [[ -z "$mandanten" || -z "$users" ]]; then
    fehler "Plausibilitaetspruefung: Tabelle mandanten oder users fehlt im wiederhergestellten Dump."
    return 1
  fi
  log "Test-Restore ok: $tabellen Tabellen, alembic_version=$version, mandanten=$mandanten Zeilen, users=$users Zeilen."
  # shellcheck disable=SC2034  # von backup-pruefen.sh gelesen
  TESTRESTORE_ERGEBNIS="$tabellen Tabellen, alembic $version, mandanten=$mandanten, users=$users"
}

db_testrestore_aufraeumen() {
  if [[ -n "${TESTDB_ANGELEGT:-}" && "$TESTDB_ANGELEGT" =~ ^restore_test_[0-9]{8}_[0-9]{6}$ ]]; then
    db_sql postgres "DROP DATABASE IF EXISTS \"$TESTDB_ANGELEGT\"" >/dev/null 2>&1 \
      || warn "Wegwerf-Datenbank $TESTDB_ANGELEGT konnte nicht geloescht werden -- bitte von Hand entfernen."
    TESTDB_ANGELEGT=""
  fi
  return 0
}
