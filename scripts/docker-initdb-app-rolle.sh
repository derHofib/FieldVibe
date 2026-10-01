#!/bin/sh
# Postgres-Init-Skript fuer die lokale Entwicklung (Mount in
# docker-compose.override.yml nach /docker-entrypoint-initdb.d/). Laeuft nur
# bei frischem Datenvolume, als POSTGRES_USER auf der noch leeren Datenbank --
# legt die App-Rolle an, mit der sich Backend/Worker verbinden, damit die
# RLS-Startpruefung auch lokal besteht (Produktion: scripts/app_rolle_einrichten.sh).
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_rolle="${APP_DB_USER:-fieldvibe_app}" \
  -v app_passwort="${APP_DB_PASSWORD:-fieldvibe_app}" \
  -v db_name="$POSTGRES_DB" \
  -f /opt/fieldvibe/app_rolle_einrichten.sql
