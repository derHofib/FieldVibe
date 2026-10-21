# Betriebs-Runbook

Für den Betreiber eines FieldVibe-Servers: woran man merkt, dass etwas nicht stimmt, und was dann zu
tun ist. Installation und Konfiguration stehen in `docs/DEPLOYMENT.md`; dieses Dokument ist die
Alarmkette und die Checkliste für den Ernstfall.

Alle Befehle im Repo-Verzeichnis auf dem Server. Kurzform für Compose (Domain-Betrieb; im IP-Betrieb
`docker-compose.ip.yml` statt `.prod.yml`):

```bash
C="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
```

## 1. Alarmkette

Wer merkt was, und wer wird wie benachrichtigt? Ohne Einrichtung steht alles nur im Log – deshalb
mindestens die ersten drei Zeilen aktivieren.

| Was fällt aus | Wie es auffällt | Empfohlene Einrichtung |
| --- | --- | --- |
| Server/Backend nicht erreichbar | Externer Uptime-Check auf `https://<DOMAIN_API>/health/ready` (200 = ok, 503 = nicht bereit) | Beliebiger Uptime-Dienst (EU-Anbieter oder selbst gehostet), Intervall 1–5 min |
| **Worker steht** (Jobs, Mails, Postfächer) | Ping `HEARTBEAT_PING_URL` bleibt aus; `/health/heartbeats` → `worker_tick`; Docker-Status `unhealthy` | healthchecks.io-kompatibler Dienst: Periode 1 min, Toleranz 5 min |
| **Backup alt/fehlgeschlagen** | `BACKUP_PING_URL` bleibt aus bzw. `/fail`; `/health/heartbeats` → `backup` | Siehe `DEPLOYMENT.md`, „Überwachung“; Ping-Periode 1 Tag + einige Stunden |
| Mails hängen | `/health/heartbeats` → `mail_outbox` (`pending_ueberfaellig`, `failed`); Benachrichtigung „E-Mail nicht zugestellt“ in der App | Externer Check auf `/health/heartbeats` mit `HEALTH_TOKEN` (liefert 503 bei Fehlern) |
| Anwendungsfehler (500er) | Error-Tracking (wenn eingerichtet); sonst Log-Zeilen `level=ERROR` | `SENTRY_DSN` (GlitchTip/EU-Sentry), siehe `DEPLOYMENT.md`, „Datenschutz Error-Tracking“ |
| Plattenplatz | `df -h`, Docker-Log-Rotation begrenzt Container-Logs | Host-Monitoring (nicht Teil von FieldVibe) |

**Ein externer Uptime-Check mit Token** deckt fast alles ab:

```bash
curl -fsS -H "Authorization: Bearer $HEALTH_TOKEN" https://<DOMAIN_API>/health/heartbeats
```

Antwort `200` = alles in Ordnung, `503` = mindestens ein Heartbeat im Zustand `fehler`; der Body nennt
den Verursacher. Ohne `HEALTH_TOKEN` (Variable in der `.env` setzen: `openssl rand -base64 32`) sind die
Details nur mit einem Plattform-Admin-Login abrufbar, anonym antwortet der Pfad mit 404.

### Heartbeats lesen

| `name` | Bedeutung | Grenze (einstellbar) |
| --- | --- | --- |
| `worker_tick` | Der Worker lebt (Lebenszeichen alle 30 s) | 180 s |
| `mail_sync` | Persönliche Postfächer wurden synchronisiert (nur wenn aktive Postfächer existieren) | 900 s |
| `mail_konten` | Aktive Postfächer ohne erfolgreichen Sync seit > 60 min, mit betroffenen Mandanten | 60 min (`warnung`) |
| `email_ingest` | Stündlicher Import von E-Mail-Rechnungen (nur mit aktiver IMAP-Integration) | gut 3 h |
| `mail_outbox` | Wartende, hängende und endgültig fehlgeschlagene Mails | `fehler`, sobald `failed` > 0 oder `pending` länger als 10 min überfällig |
| `backup` | Alter und Status aus `letzter-lauf.json` | 36 h |

Der Backend-Watchdog wertet das alle 5 Minuten aus und schreibt bei **Zustandswechseln** eine Zeile
`Heartbeat-Alarm …` (WARNING/ERROR) ins Log – auch wenn der Worker tot ist.

## 2. Logs

```bash
$C logs -f --tail 200 backend worker
$C logs backend | jq -c 'select(.level=="ERROR")'                       # nur Fehler (JSON-Format)
$C logs backend worker | jq -c 'select(.request_id=="<id aus X-Request-ID>")'   # ein Request
$C logs worker | jq -c 'select(.job=="mahnwesen")'                       # ein Job
```

Jede API-Antwort trägt den Header `X-Request-ID`; wer einen Fehler meldet, kann die ID aus den
Browser-Entwicklertools (Netzwerk) mitliefern. Die Zugriffszeilen (`event: http_request`) enthalten
Methode, Routenvorlage, Status, Dauer, `mandant_id`/`user_id` – nie Tokens, Query-Strings oder Bodies.
`/health*` wird nicht protokolliert. Container-Logs rotieren bei 5 × 10 MB je Dienst.

## 3. Was tun bei …

### … Worker steht

Erkennbar an: Ping bleibt aus, `worker_tick` auf `fehler`, `$C ps` zeigt den Worker `unhealthy`/`restarting`.

```bash
$C ps worker
$C logs --tail 100 worker           # Absturz? Datenbank/Objektspeicher nicht erreichbar? Rollenprüfung?
curl -fsS https://<DOMAIN_API>/health/ready                      # Abhängigkeiten gesund?
$C restart worker
```

Nach dem Neustart holt der Worker **Versäumtes selbst nach**: Jobs sind zustandsgeführt (Tabelle
`job_laeufe`) und laufen, sobald der letzte erfolgreiche Lauf vor dem jüngsten Slot liegt – ein Ausfall
über Nacht kostet keinen Tageslauf mehr. Ein Ausfall von mehr als `SCHEDULER_NACHHOLEN_MAX_TAGE` (3) Tagen
wird zusätzlich als `ERROR job_nachholen_ueberschritten` gemeldet; der Lauf wird trotzdem **einmal**
nachgeholt (die Jobs sind zustandsbasiert, ein Lauf erledigt alles Aufgelaufene, nichts wird je verpasstem Tag
wiederholt). Ausstehende Mails gehen anschließend automatisch raus.

Stand der Jobs ansehen:

```bash
$C exec postgres psql -U "$POSTGRES_USER" "$POSTGRES_DB" -c \
  "select job, mandant_id, letzter_lauf_am, letzter_versuch_am, fehler_in_folge, left(letzter_fehler,80) from job_laeufe order by job, mandant_id"
```

`fehler_in_folge > 0` heißt: der Job scheitert; nach `SCHEDULER_RETRY_MINUTEN` (30) wird er erneut
versucht. Scheitert die Sammel-Ausführung, wiederholt der Worker die Mandanten einzeln – ein defekter
Mandant blockiert die anderen nicht. Den Fehler mit `letzter_fehler` und dem Log (`job=<name>`) eingrenzen.

Mehrere Worker-Container gleichzeitig sind unkritisch (Advisory-Lock je Tick, `FOR UPDATE SKIP
LOCKED` bei Mails und beim Anlegen von Vorgängen), aber nicht nötig.

### … Mails hängen

```bash
curl -fsS -H "Authorization: Bearer $HEALTH_TOKEN" https://<DOMAIN_API>/health/heartbeats | jq '.heartbeats[] | select(.name=="mail_outbox")'
$C exec postgres psql -U "$POSTGRES_USER" "$POSTGRES_DB" -c \
  "select status, count(*), min(naechster_versuch_am) from mail_outbox group by status"
```

- `pending` mit überfälligem `naechster_versuch_am` → der Worker arbeitet nicht (siehe oben).
- `pending` mit `versuche > 0` → Retry läuft (1 min, 5 min, 30 min, 2 h, 12 h); Grund in
  `letzter_fehler` (meist SMTP-Zugang/Server). Im E-Mail-Verlauf des Vorgangs steht „Wird gesendet“ samt Grund.
- `failed` → endgültig. Ursache beheben (SMTP unter *Integrationen*, Empfängeradresse), dann
  `POST /api/mail-outbox/<id>/wiederholen` (Administrator) oder die Mail neu schreiben.
- `sending` länger als 15 min → der Worker ist beim Versand abgestürzt. Die Mail wird **nicht**
  automatisch wiederholt (sie könnte schon rausgegangen sein), sondern als `failed` mit „Zustellung
  unbekannt“ markiert und gemeldet. Prüfen (Gesendet-Ordner/Empfänger), dann gezielt wiederholen oder verwerfen.
- Offene Mails des Mandanten: `GET /api/mail-outbox?status=failed` (Mandanten-Admin sieht nur die eigenen).

Anhänge liegen bis zum Versand unter `mail-outbox/…` im Objektspeicher. Bricht eine Anfrage nach dem Hochladen
ab, bleibt ein verwaistes Objekt zurück (harmlos, gering); bei Bedarf Objekte unter diesem Präfix, die zu keiner
`mail_outbox`-Zeile gehören, von Hand löschen.

### … Backup ist alt oder fehlgeschlagen

```bash
cat "$(grep '^BACKUP_DIR=' .env | cut -d= -f2)/letzter-lauf.json"      # status, meldung, Ziele
tail -n 50 /var/log/fieldvibe-backup.log
crontab -l | grep backup                                             # Cron noch eingetragen?
scripts/backup.sh                                                    # von Hand, zeigt den Fehler
```

Häufige Ursachen: Remote-Ziel nicht erreichbar, `BACKUP_GPG_RECIPIENT` fehlt (Upload zu Remote-Zielen wird
dann verweigert), Platte voll, Sperre durch einen noch laufenden Lauf (Exit 75). Details und
Wiederherstellung: `DEPLOYMENT.md`, Abschnitt 5. **Solange das Backup alt ist, bricht `deploy.sh` ab** – gewollt;
erst reparieren, nicht mit `--ohne-backup` umgehen.

### … Migration scheitert

Beim Deployment: `deploy.sh` migriert **vor** dem Rollout. Scheitert die Migration, wird nichts ausgerollt, die
laufende Version bleibt aktiv (Exit 11, Worker wird wieder gestartet). Alembic migriert transaktional, die
Datenbank steht danach meist unverändert da.

```bash
scripts/migrieren.sh current               # welcher Stand ist aktiv?
scripts/migrieren.sh heads                 # welcher Stand wird erwartet?
scripts/migrieren.sh history -r current:head
$C logs --tail 80 backend                  # (Fehlermeldung der Migration steht in der Ausgabe von deploy.sh)
```

Typische Ursachen: Daten, die eine neue Constraint verletzen (die Meldung nennt Tabelle und Constraint),
fehlende Rechte der Owner-Rolle (`.env.migration`), zwei Heads (Branches mit gleicher Revisionsnummer; nach
einem Merge `alembic merge`). Den Fehler beheben (Daten bereinigen oder Migration korrigieren) und
`scripts/deploy.sh` erneut ausführen.

**Wenn die Datenbank beschädigt oder halb migriert ist** (selten; nur bei Datenbank-Operationen außerhalb einer
Transaktion): Backup vom Beginn des Laufs einspielen. Der Stamp steht in `.deploy-state` (`BACKUP_STAMP`)
und in `letzter-lauf.json`:

```bash
scripts/restore.sh liste
$C stop backend worker
scripts/restore.sh db --stamp <stamp>          # fragt nach; --ja für Automatisierung
IMAGE_TAG=$(grep '^CURRENT_TAG=' .deploy-state | cut -d= -f2) $C up -d --no-build --remove-orphans
```

### … Deploy fehlgeschlagen (Health-Gate/Rollback)

`deploy.sh` meldet, was passiert ist (Exit-Code und Text):

- **Backup fehlgeschlagen** (Exit 10): nichts verändert; Backup reparieren (oben).
- **Build fehlgeschlagen** (14): nichts verändert; Log des Builds lesen.
- **Migration fehlgeschlagen** (11): siehe oben.
- **Health-Gate nicht bestanden, Rollback erfolgreich** (12): Die alte Version läuft wieder
  (`CURRENT_TAG` in `.deploy-state`), `FEHLGESCHLAGEN_TAG` nennt den verworfenen Stand. Ursache:
  `$C logs --tail 200 backend worker`. **Die Migrationen des verworfenen Releases sind angewendet geblieben**;
  die alte Version läuft damit nur, wenn sie abwärtskompatibel waren (`/health/ready` bleibt für „DB neuer
  als Code“ bewusst grün). Bei Fehlern der alten Version auf neuem Schema: Backup einspielen (oben).
- **Rollback nicht möglich oder gescheitert** (13): kein Vorgänger-Tag bekannt, Vorgänger-Images fehlen
  (`docker image prune`?) oder auch der alte Stand wird nicht gesund. Manuell:

  ```bash
  docker images | grep fieldvibe                      # welche Tags gibt es?
  IMAGE_TAG=<älterer tag> $C up -d --no-build --remove-orphans
  $C ps; curl -fsS https://<DOMAIN_API>/health/ready
  ```

  Gibt es keinen lauffähigen älteren Tag: den letzten funktionierenden Commit auschecken und
  `scripts/deploy.sh --ohne-backup` (das Backup lief schon) ausführen.

Das Health-Gate wartet standardmäßig 300 s; auf langsamen Servern `--health-timeout 600`.

### … Datenbank oder Objektspeicher nicht erreichbar

`/health/ready` liefert 503; mit Token zeigt `pruefungen` welcher Teil. Backend und Worker laufen weiter, aber
Anfragen schlagen fehl.

```bash
$C ps postgres minio
$C logs --tail 80 postgres        # Platte voll? Absturz?
$C logs --tail 80 minio
df -h
$C restart postgres               # erst wenn die Ursache klar ist
```

### … ein Mandant meldet „Fehler“ (Support)

Ablauf: Uhrzeit und Seite erfragen → `request_id` aus der Antwort (Header `X-Request-ID`, im Fehlerbericht
enthalten) → `$C logs backend | jq -c 'select(.request_id=="…")'` → Stacktrace im Feld `exc`. Im
Error-Tracking (falls an) trägt das Event dasselbe `request_id`-Tag.

## 4. Abhängigkeiten und Sicherheitsmeldungen

Dependabot öffnet wöchentlich gruppierte PRs; die CI-Jobs `pip-audit` und `npm-audit` melden bekannte
Schwachstellen (nicht blockierend, Befunde im Job-Log/Zusammenfassung). Vorgehen:

1. Befund prüfen (betrifft die Funktion, die wir nutzen?). Meist genügt ein Update-PR von Dependabot;
   bei pip danach die Lockfiles neu erzeugen (`DEPLOYMENT.md`, „Abhängigkeiten aktualisieren“).
2. Lässt sich nicht aktualisieren, die Ausnahme **begründet** festhalten: Eintrag in der Tabelle unten und
   `--ignore-vuln <ID>` im Schritt „Produktions-Abhängigkeiten prüfen“ des Jobs `pip-audit` (bzw.
   `npm audit` mit Begründung hier). Ausnahmen haben ein Ablaufdatum.

| ID | Paket | Grund der Ausnahme | Prüfen bis |
| --- | --- | --- | --- |
| – | – | derzeit keine Ausnahmen | – |

Stand der ersten Prüfung (21.10.2026, `pip-audit` gegen `backend/requirements.lock`): `certifi 2026.7.22`
(PYSEC-2026-4320, fix 2026.10.19) und `pillow 12.3.0` (mehrere CVE-2026-112xxx, fix 13.0.0) – Updates
stehen aus; `npm audit --omit=dev --audit-level=high`: keine Befunde.

## 5. Eingebaute Grenzen

- Healthchecks und Heartbeats sehen den Docker-Host nicht (Plattenplatz, RAM, Kernel): dafür ein
  Host-Monitoring einsetzen.
- Es gibt keinen Multi-Server-Betrieb; Worker-Neustarts und Deploys unterbrechen Jobs für Sekunden bis
  Minuten, nie für einen Tageslauf.
- Rollback betrifft Images, nicht das Schema (siehe oben). Migrationen daher immer „erst hinzufügen,
  später entfernen“.
- Der Worker pingt nur bei laufendem Event-Loop: ein hängender Loop wird erkannt, ein hängender *Job*
  (z. B. dauerhaft blockierender Mailserver) hält den Loop nicht an – er zeigt sich über die Job-Zeit
  im Log und das ausbleibende Mail-Heartbeat-Alter.
