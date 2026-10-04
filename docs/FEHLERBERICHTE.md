# In-App-Fehlerberichte (Betreiber-Überblick)

## Funktionsweise

Nutzer melden Fehler direkt in der App (Beschreibung, Schweregrad, optional
Screenshot). Das Frontend hängt technischen Kontext an (Route, App-Version,
Commit, Klickpfad, Konsolenfehler, fehlgeschlagene Requests). Berichte liegen
mandantengetrennt (RLS) in der Datenbank, Screenshots im S3/MinIO-Speicher.
Gleichartige Fehler erhalten denselben Fingerprint und werden als mögliche
Duplikate markiert. Super-Admin und Mandanten-Admin sehen die Berichte in der
App; Claude greift über die Service-API (`/api/service/fehlerberichte`) zu,
siehe `docs/BUGFIX_WORKFLOW.md`.

## Recht „Fehlerberichte"

Rechte-Bereich `fehlerberichte` (sehen, erstellen, bearbeiten, löschen) in der
Rechte-Matrix der Account-Typen. „erstellen" bedeutet melden. Wer Berichte
melden oder einsehen soll, braucht das jeweilige Recht.

## Datenschutz

- Schwärzung doppelt: im Frontend vor dem Senden und serverseitig als zweite
  Verteidigungslinie (Tokens, Authorization-/Cookie-Header, Passwort-/PIN-
  artige Schlüssel, JWTs).
- Aufbewahrung: `FIELDVIBE_FEHLERBERICHT_AUFBEWAHRUNG_TAGE` (Standard 90).
  Danach löscht der Worker Berichte samt Screenshots.
- Der Service-Zugriff ist lesend über alle Mandanten und schreibend nur für
  Status, Lösungsnotiz, Fix-Commit und PR-URL; jeder Zugriff wird im Audit-Log
  protokolliert (`fehlerbericht.service_zugriff`).
- Berichte können Kundendaten enthalten. Der Workflow verbietet, sie in
  Commits/PRs zu übernehmen. Prüfen, ob die Weitergabe an Claude zu eurer
  Auftragsverarbeitung/Datenschutzerklärung passt.

## Service-Token einrichten

1. Token erzeugen: `docker compose run --rm backend python -m app.cli fehlerbericht-token`.
   Die Ausgabe enthält Klartext-Token (nur einmal sichtbar) und Hash.
2. Hash in die `.env` des Servers: `FIELDVIBE_FEHLERBERICHT_TOKEN_HASH=<hash>`.
3. Backend neu starten (`docker compose up -d backend`). Ohne Hash antwortet
   die Service-API mit 404.
4. Klartext-Token als Umgebungsvariable `FIELDVIBE_BUGREPORT_TOKEN` (zusammen
   mit `FIELDVIBE_API_URL`, z. B. `https://api.fieldvibe.de`) in der
   Claude-Code-Cloud-Umgebung hinterlegen (Secrets der Umgebung), nie im Repo.
5. API-Domain in die Netzwerk-Allowlist der Claude-Code-Umgebung eintragen.
   Für Screenshots im MCP-Server zusätzlich die Domain des S3-Speichers
   (presigned URLs), sonst kommen nur URLs statt Bilder.
6. Test: `scripts/fehlerberichte.sh liste`.

Rate-Limit: 10 Anfragen je IP und 15 Minuten (429).

## Geplante Claude-Code-Routine

Beispiel-Prompt:

> Arbeite offene Fehlerberichte gemäß docs/BUGFIX_WORKFLOW.md ab, max. 3 pro
> Lauf. Starte mit `scripts/fehlerberichte.sh liste neu`. Nichts mergen.

## Token-Rotation

Neues Token erzeugen (Schritt 1), neuen Hash in `.env` ersetzen, Backend
neu starten (das alte Token ist sofort ungültig), neues Token in der
Claude-Umgebung eintragen. Bei Verdacht auf Leck sofort rotieren; der Hash
allein ist nicht verwendbar.
