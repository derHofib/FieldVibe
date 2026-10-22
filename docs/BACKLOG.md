# Offene Punkte & Ideen

Sammelstelle für alles, was besprochen, aber noch nicht entschieden oder
gebaut ist — damit es nicht verloren geht, wenn eine Session-Historie mal
komprimiert wird. Durchnummeriert, damit man beim Abarbeiten einfach per
Nummer referenzieren kann ("mach jetzt 3"). Reihenfolge der Nummern ist
keine Priorität, nur Referenz — neue Punkte hängen am Ende an, bestehende
Nummern werden nicht neu vergeben, damit alte Verweise gültig bleiben.

## 1. Partnerportal fertigstellen

> **Stand 19.10.2026:** Teilweise überholt -- ein Partnerportal-Frontend
> existiert unter `frontend/src/partner/` (Login, Registrierung, Passwort,
> Aufträge, Zeitplan, Profil). Offen bleibt zu prüfen, ob 1.1 (Verwaltung der
> Partner im Office) vollständig ist.

Backend ist vollständig da (`app/api/routes/partner.py`, `partner_auth.py`,
`partner_portal.py`, Models `partner`/`partner_nachweis`/`partner_zugang`,
Migration 0062) — Nachunternehmer-Verwaltung inkl. Freistellungsbescheinigung,
eigener Login. Im Frontend fehlt aber der komplette Zugang dazu.

- **1.1 Oberfläche zum Anlegen/Verwalten von Partnern** im Office bzw. der
  Feld-App — bisher kann kein Mitarbeiter überhaupt einen Partner anlegen.
- **1.2 Eigene Login-/App-Oberfläche für den Partner selbst** — analog zum
  Kundenportal, existiert bisher gar nicht.
- **1.3 Partner-Einladung im Frontend** (`/partnerportal/registrieren`) —
  analog zu Mitarbeiter-/Kunden-Einladung (`/registrieren`,
  `/portal/registrieren`). Hängt an 1.2, ohne Oberfläche keine sinnvolle
  Registrierungsseite.

## 2. SMTP Port 465 (implizites SSL/TLS) wird nicht unterstützt

`email_service.py` verbindet immer per klassischem SMTP + `starttls()`
(passt zu Port 587). Ein Anbieter, der zwingend Port 465 verlangt, scheitert
damit. Betrifft aktuell nicht den globalen FieldVibe-Versand (auf 587
korrigiert), könnte aber bei einzelnen Mandanten-eigenen SMTP-Konfigurationen
auftreten.

## 3. Navigations-Neusortierung

Siehe Ausarbeitung vom 17.08., Artifact „FieldVibe Navigation".

- **3.1 Vorschlag A (risikoarm):** Techniker-Zuweisungen und
  Partner-Verwaltung nach „Arbeit", Postfach nach „Kommunikation", Profil
  raus aus der Kategorie-Logik.
- **3.2 Vorschlag B (weitergehend):** zusätzlich „Verwaltung" sichtbar in
  „Zugriff & Team" und „Firma einrichten" aufteilen. Offene Frage dabei:
  wohin mit „Team-Zeiten" (Zugriff & Team vs. Finanzen)?

## 4. „Meine Ansicht" — personalisierte Menü-Profile

Ein Nutzer soll in seinem Profil zwischen vordefinierten Ansichten
(Techniker, Dispo, Büro/Buchhaltung, „Alles") wechseln können, die
filtern/kuratieren, was in Bottom-Nav bzw. Office-Sidebar prominent
angezeigt wird — nie mehr, als die echten Rechte erlauben.

- **[Erledigt, 18.08.] Eigene Auswahl in der Office-Seitenleiste** —
  schlanke Zwischenlösung, kein vollständiger Ersatz für 4.1: jeder Nutzer
  wählt unter „Seitenleiste anpassen" selbst per Checkbox, welche Bereiche
  in seiner Office-Sidebar erscheinen (gruppiert nach den bestehenden
  Kategorien Arbeit/Finanzen/Kommunikation/Verwaltung — 3. bleibt davon
  unberührt, es sind weiterhin die alten Kategorien). Rein self-service,
  kein Admin-Eingriff, keine benannten/wiederverwendbaren Profile, keine
  eigene Startseite. `PATCH /api/users/me/office-nav`,
  `office_nav_items` auf `User` (Migration 0065), analog zu
  `bottom_nav_items`.
- **4.1 Vordefinierte, vom mandant_admin pflegbare Ansichts-Profile** —
  Vorschläge, die er umbenennen/umbauen/löschen kann, kein starres System.
  Skizzierter Umfang: neue Tabelle `ansichts_profile` (mandantengebunden,
  RLS), CRUD-Routen, neue Verwaltungsseite, Sidebar-Filterung mit
  „Alle Bereiche anzeigen"-Fluchtweg. Noch nicht begonnen — bleibt größer
  als die jetzt gebaute Einzelauswahl (mehrere Nutzer teilen ein Profil,
  statt jeder seine eigene Checkliste zu pflegen).
- **4.2 Eigene Startseite je Nutzer** statt immer Feed/Vorgänge. Neues Feld
  `startseite` auf `User`, neuer Abschnitt auf der Profil-Seite. Noch nicht
  begonnen.

## 5. Portal-Branding — eigenes Logo im Kundenportal

Ein Mandant lädt sein Firmenlogo hoch; es ersetzt die FieldVibe-Wortmarke
auf der Kundenportal-Login-Seite und im Portal-Header seiner Kunden, mit
einem dezenten „by FieldVibe"-Hinweis unten links. Mockup als Artifact
gezeigt (17.08.). Naheliegender Ansatzpunkt: das bereits vorhandene, bisher
ungenutzte `Mandant.branding`-JSON-Feld — keine neue Migration nötig. Zu
unterscheiden von der bereits gebauten Kunden-Logo-Funktion (ein einzelner
Kunde zeigt sein eigenes Logo auf seinem persönlichen Portal-Link) — hier
geht es um das Logo des Betriebs selbst, für alle seine Kunden gleich.
Noch nicht begonnen.

## 6. Nav-Label „Zeiterfassung" führt zu `/statistik`

Kein Bug, nur verwirrend — historisch gewachsener Name.

## 7. Seitenname „Geschäft" ist vage

Bündelt Kunden/Material/Abrechnung, aber der Name verrät das nicht.

## 8. Mandanten-eigene Rechtstexte im Kundenportal — Teilweise erledigt

Die Links zu Impressum und Datenschutz im Kundenportal zeigen bisher auf die
plattformweiten Texte (`VITE_IMPRESSUM_URL`/`VITE_DATENSCHUTZ_URL`, Build-Zeit).
Gegenüber seinen Kunden ist aber der Handwerksbetrieb selbst
Diensteanbieter und Verantwortlicher, braucht also ein eigenes Impressum und
eine eigene Datenschutzerklärung. Offen: pro Mandant hinterlegbare URLs (z. B.
im `Mandant.branding`-JSON, siehe Punkt 5) und Vorrang vor dem Plattform-Link
im Portal.

Stand: Pro Mandant hinterlegbar sind `impressum_url`/`datenschutz_url` in
`Mandant.firmendaten` (Formular „Firmenprofil“, nur http/https). Reihenfolge je
Link: Firmendaten-URL, dann Build-Env, dann interne Platzhalter-Seite
`/impressum` bzw. `/datenschutz`, die nur die Firmenangaben anzeigt
(`GET /api/public/rechtliches`, Mandant über `portal_slug` bzw. bei genau einem
aktiven Mandanten). Die Links sind dadurch nie tot. Offen: die rechtsgeprüften
Texte selbst (Platzhalter-Hinweis bleibt, bis URLs hinterlegt sind), Mandanten-
Kontext im Partnerportal und auf den Kundenportal-Seiten ohne Slug (Registrieren,
Passwort zurücksetzen) bei mehreren aktiven Mandanten.

## 9. Angebot: Gliederung, Alternativ-/Bedarfspositionen, Varianten, Textbausteine (Roadmap 3.1)

Angebote sind bisher eine flache Positionsliste mit festem Einleitungs- und Schlusstext im PDF. Offen sind Gliederung (Titel/Zwischensummen), Alternativ- und Bedarfspositionen, Varianten sowie frei wählbare Textbausteine für Einleitung und Schluss.

## 10. DATEV-Export: Abnahme und Lücken (Roadmap 1.7)

Stand und Annahmen: `docs/konzepte/DATEV.md`.

- **Abnahme per Testimport beim Steuerberater offen.** Header (Formatversion 13),
  Spaltenköpfe und Feldregeln sind aus dem Gedächtnis rekonstruiert, nicht gegen die
  DATEV-Spezifikation geprüft; ebenso die SKR04-Standardkonten.
- **Zahlungsbuchungen (OP-Ausgleich)** fehlen: der Stapel enthält nur Rechnungen, keine
  Zahlungseingänge/-ausgänge, Skonto oder Mahngebühren.
- **Eingangsrechnung mit gemischten MwSt-Sätzen**: eine Eingangsrechnung hat genau einen
  Satz und ergibt eine Buchungszeile; Aufwandskonto je Kategorie ist nicht konfigurierbar.
- Wirtschaftsjahr-übergreifende Zeiträume werden nicht geprüft; keine Umnummerierung der
  Personenkonten bei geänderter Sachkontenlänge; kein Bearbeiten des Kreditorenkontos in der
  Oberfläche (nur API).

## 11. Sicherheit: Rest nach Roadmap 1.2

- **MFA für Kundenportal und Partnerportal** — TOTP gibt es nur für
  Mitarbeiter (`app/services/mfa_service.py`, `users.mfa_*`). Portal-Zugänge
  hätten dieselbe Mechanik (Spalten an `kundenportal_zugaenge`/`partner_zugaenge`).
- **Refresh-Cookie für Kundenportal und Partnerportal** — dort liegt das
  Refresh-Token weiter im `localStorage` (`kundenAuthStore`, `partnerAuthStore`);
  `app/core/refresh_cookie.py` ist wiederverwendbar, die Portale brauchen
  eigene Cookie-Namen und Pfade.
- **WebAuthn/Passkeys** als zweiter Faktor oder Ersatz für TOTP.
- **MFA-Pflicht für `super_admin`** — bewusst Teil der späteren „Console"
  (Super-Admin-Frontend); technisch ist MFA für `super_admin` schon möglich,
  nur die Pflicht (`mfa_service.einrichtung_erforderlich`) nimmt die Rolle aus.
- **Getrennte DB-Owner-Rolle als Standard** — heute opt-in
  (`--getrennter-owner`), nicht gegen echtes Postgres mit Rollenrechten
  getestet; `restore.sh`/Backup-Prüfung kennen die Owner-Rolle noch nicht.
- **MinIO-Service-Account gegen echtes MinIO verifizieren** und
  Schlüsselrotation (heute: Zeilen in `.env` löschen, Skript erneut ausführen).
- **Access-Token nicht im `localStorage`** — bleibt dort, damit die Feld-App
  offline startet; Alternative: In-Memory plus Offline-Sitzungsmodus.
- **Refresh-Token-Rotation mit Wiederverwendungserkennung** — Refresh-Tokens
  sind weiterhin zustandslose JWTs; ein gestohlenes Cookie gilt bis zum Ablauf
  (14 Tage) oder Widerruf.

## 12. Datenimport: Lücken (Roadmap 1.10)

Stand und Regeln: `docs/konzepte/DATENIMPORT.md`. Umgesetzt: Kunden, Standorte & Anlagen
(mit Prüfzyklus), Material; Probelauf, Dubletten, Fehlerbericht, Rückgängig.

- **Offene Posten nicht umgesetzt** (Entscheidungsvorlage: `docs/konzepte/DATENIMPORT_OFFENE_POSTEN.md`).
- Baujahr der Anlage landet in der Notiz (kein Feld im Modell); Anlagen-Zusatzfelder
  (`stammdaten`) lassen sich nicht importieren.
- Keine Importe für Verträge, Vorgänge, Lieferanten, Partner; keine mehrfachen Ansprechpartner
  je Kunde; kein Einkaufspreis (Materialmodell kennt nur den Einzelpreis).
- Rückgängig setzt aktualisierte Datensätze nicht zurück (nur angelegte, unveränderte).
- Body-Limit vor dem Upload-Endpunkt (Reverse-Proxy) nicht konfiguriert; die App prüft erst
  nach dem Empfang. Bestehende CSV-Exporte (`csv_response`) haben keinen Formelschutz, nur der
  Import-Fehlerbericht (`csv_service.formel_sicher`).
- Kein eigener Rechte-Bereich „Import“ (nur mandant_admin/loesch_operativ).

## 13. GoBD-Paket: Lücken (Roadmap 1.9)

Stand und Entscheidungen: `docs/konzepte/GOBD.md`; Dokumente: `docs/gobd/`.

- **Z3-`index.xml` nicht gegen IDEA/DTD validiert** (Struktur aus dem Beschreibungsstandard rekonstruiert, DTD nicht beigelegt).
  Abnahme per IDEA-Einlesen beim Steuerberater offen. Z1/Z2 nur organisatorisch (kein Prüferzugang).
- **Object Lock ungetestet gegen echtes MinIO** (nur moto); Docker/Compose nicht ausprobiert. Compose-Durchreichung von
  `S3_OBJECT_LOCK`/`S3_RECHNUNGEN_RETENTION` nur syntaktisch geprüft. Verlängerung bestehender Retention nicht umgesetzt.
- **Kein Trigger auf `rechnung_zahlungen`** (additiv nur per Konvention); kein Hash für Eingangsbeleg-PDFs.
- **Ablaufhemmung der Aufbewahrung** (§ 147 Abs. 3 S. 5 AO) und manuelle „Legal Hold“-Markierung nicht abgebildet; kein Job, der
  Löschvorschläge vormerkt; keine Oberfläche für Löschvorschläge/S3-Retry-Liste (nur API).
- **Protokollumfang:** keine Stammdatenänderungen (Kunde, Material), keine Lesezugriffe; Portal- und Partner-Anmeldungen nicht protokolliert;
  Plattform-Aktionen des Super-Admin ohne Mandantenbezug (`mandant_erstellt`, `mandant_geaendert`) stehen nur im Plattformprotokoll.
- **Hash-Kette:** Kettenende nur mit extern festgehaltenem Kopf prüfbar; sehr große Protokolle werden bei der Prüfung vollständig gelesen.
- **Vollexport:** ohne Postfach, Partner-Nachweise, Formular-Dateien (Form-Submissions), Mail-Anhänge; ZIP wird im API-Prozess erzeugt
  (bei sehr großen Betrieben Worker-Container bevorzugen).
- **Nummernlücken** durch gelöschte Rechnungsentwürfe (Nummer bei Anlage); Vergabe erst beim Versand wäre ein Umbau des Nummernkreises.
- Altobjekte im Objektspeicher behalten ihre Schlüssel ohne Mandantenpräfix; keine Migration.
## 14. Betrieb: Rest nach Roadmap 1.3

Stand und Handbuch: `docs/BETRIEB.md`, `docs/DEPLOYMENT.md` (6, 6d). Umgesetzt: Error-Tracking
(optional), JSON-Logs mit Request-ID, Healthchecks/Heartbeats, zustandsgeführte Jobs, Mail-Outbox,
Deploy mit Backup/Gate/Rollback, GHCR-Images, Dependabot, Audits.

- **Nie gegen echtes Docker/GHCR/Caddy ausgeführt** (Entwicklungsumgebung ohne Docker-Daemon):
  `deploy.sh`-Gesamtlauf, Compose-Healthchecks (`depends_on: service_healthy`, Caddy-Admin-API auf
  `127.0.0.1:2019`, `wget` im Frontend-Image), `{$SENTRY_CSP_HOST:}` im Caddyfile, die CI-Jobs
  `images`/`pip-audit`/`npm-audit`. Getestet sind nur die Ablauflogik (Shell-Tests mit Stub-`docker`)
  und die Python-/TypeScript-Seite.
- **Frontend-Laufzeitkonfiguration**: `VITE_*` werden zur Build-Zeit eingebacken, daher baut `deploy.sh`
  das Frontend auf dem Server und die GHCR-Frontend-Images sind nur Archiv. Mit einer `config.js`
  zur Laufzeit ließe sich ein Betrieb ganz aus der Registry (Pull statt Build) und ein schnelleres
  Rollback ohne lokale Images umsetzen.
- **Interaktive Mails nicht in der Outbox**: Kunde/Vorgang/Angebot/Rechnung/Bestellung senden synchron
  (Nutzer sieht das Ergebnis sofort), mit der Ghost-Send-Lücke, dass bei einem Commit-Fehler nach dem SMTP-Erfolg
  der Verlaufseintrag fehlt. Option: „im Hintergrund senden“ mit Statusanzeige. Einladung und Passwort-Reset
  bleiben synchron, weil die Antwort den Link zurückgibt, wenn der Versand scheitert.
- **Outbox-Verwaltung ohne Oberfläche**: nur API (`/api/mail-outbox`); eine Liste „Fehlgeschlagene Mails“
  gehört in die Integrationen-Seite des Mandanten. Verwaiste Anhänge (`mail-outbox/…`) nach abgebrochenen
  Requests werden nicht automatisch aufgeräumt.
- **Jobs**: `run_*`-Funktionen rechnen mit `date.today()` in Serverzeit (UTC) statt in der Betriebs-Zeitzone;
  die „Obergrenze N Tage“ beim Nachholen ist nur Alarmgrenze (alle Jobs sind zustandsbasiert, ein Lauf holt
  alles nach) – Entscheidung nötig, falls ein Job je verpasstem Tag etwas erzeugen soll. Mahnstufen springen
  nach langem Ausfall direkt auf die Zielstufe (bestehendes Verhalten). Kein UNIQUE-Index gegen doppelte
  Daueraufträge/Prüfvorgänge (Schutz: `offener_vorgang_id`, Advisory-Lock, `SKIP LOCKED`).
- **Health**: Heartbeats sind je Typ, nicht je Worker-Instanz; Host-Metriken (Platte/RAM) fehlen.
  Der `mail_konten`-Alarm kennt nur das Alter des letzten erfolgreichen Syncs, keine Fehlerursache je Konto.
- **Error-Tracking Frontend**: schlanker Eigenbau – kein Stacktrace-Parsing, keine Sourcemaps, kein
  Release-Upload, keine Breadcrumbs. Bei Bedarf auf `@sentry/browser` umstellen (CSP und Schwärzung bleiben).
- **Abhängigkeiten**: Stand 22.10.2026 sind `certifi` 2026.10.19, `pillow` 13.0.0 und `pypdf` 6.21.2 eingespielt
  (`pip-audit` auf `requirements-dev.lock` meldet nichts mehr). Auto-Merge für Dependabot ist nicht eingerichtet.
  Die Basisimages (`python:3.12-slim`, `node:24-alpine`, `postgres:16-alpine`, `caddy:2.11-alpine`) sind nur auf
  Tag, nicht auf Digest gepinnt – Rebuilds ziehen Sicherheitsupdates automatisch, sind aber nicht bitgleich.
- **Migrationen**: Rollback der Anwendung ohne Schema-Rollback setzt abwärtskompatible Migrationen voraus;
  das ist Konvention, kein Test. Die Migrations-Reihenfolge (Migration vor Rollout) lässt die alte Version kurz
  gegen das neue Schema laufen.
- **Repository-Standardbranch/Remote-HEAD**: Sache des Repository-Besitzers (GitHub → Settings →
  Branches); `GITHUB_BRANCH` steuert nur die Update-Anzeige.

## 15. Frontend-Aufräumen: Rest nach der ersten Projektdurchsicht

Erledigt (Stand 22.10.2026): „Heute“ überall in Lokalzeit (`heuteIso`/`datumZuIso`,
Leitplanke im Test `utils/heute.test.ts`), Navigation an die Backend-Berechtigungen
angeglichen (Konsistenztest `config/navSeiten.test.ts`, Datenexport als Seitenleisten-Eintrag),
`window.confirm` durch `bestaetigen()` ersetzt, Office/Admin/Portal/Randseiten nachgeladen
(Startseite 1554 kB -> 509 kB JS), `VorgangDetailPage` in `pages/feld/vorgangDetail/` zerlegt.

Offen:

- **„Heute“ nutzt die Browser-Zeitzone**, nicht die Betriebs-Zeitzone des Mandanten. Das Frontend
  kennt keine Mandanten-Zeitzone (siehe Punkt „Jobs“ unter 14); sobald das Backend sie liefert,
  gehört sie in `utils/format.ts` (`heuteIso`) — alle Aufrufer ziehen automatisch nach.
- **Native `<select>` bleiben** (Design: kurze Listen nativ, lange `SearchableSelect`), sind aber nur
  zentral gestaltet. Eine Durchsicht, welche der ~130 Selects eigentlich lange Listen haben
  (Kunden, Anlagen, Material), steht aus.
- **Feld-Kernseiten bleiben statisch im Hauptbündel** (Offline-Start): `VorgangDetailPage` samt
  Unterkomponenten, Kunden-/Partner-/Anlagenprofil, Material. Weiteres Splitten ginge nur mit
  Offline-Test auf einem echten Gerät; der Service-Worker precacht auch alle nachgeladenen Chunks
  (160 Einträge, ~4,8 MiB).
- **`mapboxSetup`-Chunk 1,8 MB** (lazy, nur Karten) und `jspdf`/`html2canvas` (lazy) bleiben groß.
- **Playwright-E2E nicht gelaufen** (`frontend/e2e`, braucht laufendes Backend); Seitenleiste und
  Dialoge nur per Vitest und Mock-Screenshots geprüft.
- **Backend-Hinweis aus der Navigations-Prüfung:** `GET /api/users` verlangt `mitarbeiterverwaltung.sehen`,
  die Einladungsliste dagegen `mandant_admin` — ein `custom`-Nutzer mit dem Recht sieht die Seite
  „Nutzer verwalten“, aber ohne Einladungen. `/einstellungen` (Verwaltungsübersicht) ist im Office
  nur noch über Rücksprung-Links erreichbar, nicht über die Seitenleiste.
## 17. API-Typen für das Frontend aus OpenAPI

Vorbereitung ist da, das Frontend nutzt sie noch nicht: `scripts/openapi-exportieren.sh` schreibt das
Schema der FastAPI-App nach `docs/api/openapi.json` (ohne Datenbank/Netz, `ENVIRONMENT=development`);
der CI-Schritt „OpenAPI-Schema aktuell?“ im Job `backend-tests` bricht ab, wenn die eingecheckte Datei
nicht zum Code passt (`--pruefen`). Nach jeder Änderung an Routen/Schemas die Datei neu erzeugen und
mit committen (am besten mit den Paketversionen aus `backend/requirements.lock`, sonst Scheindifferenzen).

Später im Frontend einführen (nicht Teil dieses Punkts):

- `npm i -D openapi-typescript` (Version pinnen, `package-lock.json` mitcommitten).
- Script in `frontend/package.json`, z. B.
  `"api:typen": "openapi-typescript ../docs/api/openapi.json -o src/api/schema.d.ts"`.
- Erzeugte Datei einchecken und in CI aktuell halten (Typen neu erzeugen, dann auf Diff prüfen);
  handgeschriebene Typen in `src/api/` schrittweise durch `components["schemas"][...]` ersetzen.
- Listen-Endpunkte liefern die Gesamtzahl im Header `X-Total-Count` (nicht im Schema der Antwort) –
  das braucht im Fetch-Wrapper einen eigenen Zugriff auf `response.headers`.

## 16. Paginierung: Stand und Rest

Listen-Endpunkte (Kunden, Anlagen, Standorte, Angebote, Eingangsrechnungen, Material, Termine,
Benachrichtigungen, Bestellungen, Lieferanten, Zeiterfassung, Mängel, Aufträge, Projekte) nehmen optional
`limit` (Standard und Maximum 1000) und `offset`, sortieren stabil (Tiebreaker `id`) und melden die
Gesamtzahl im Header `X-Total-Count` (`app/api/paginierung.py`). Vorgänge (Standard 50, Maximum 200) und
Rechnungen (Summen im Body) hatten schon ein Limit. **Grenze:** ein Mandant mit mehr als 1000 Zeilen in
einer dieser Listen sieht ohne Blättern nur die ersten 1000 – das Frontend muss dann über `X-Total-Count`
nachladen (bisher nicht umgesetzt).

Noch unbegrenzt (bewusst nicht angefasst, wachsen kaum oder sind an einen Datensatz gebunden):
E-Mail-Verläufe je Beleg, Vorgangs-Events, Verträge, Abwesenheiten, Prüfzyklen/Prüfmittel, Daueraufträge,
Leistungsverzeichnis-Positionen, Papierkorb, Kundenportal-Listen, Partnerportal-Listen, Tag-Zuordnungen.

## Erledigt, zur Einordnung

`v1.0.0` (17.08.2026) markiert den Ausgangsstand nach Zusammenführung
von Office-Desktop-Oberfläche, Postfach (IMAP/SMTP-Mailclient),
Einladungssystem (Mitarbeiter/Kunde) samt Registrierungsseiten,
Account-Typen mit Rechte-Matrix und globalem SMTP-Fallback. Details siehe
`docs/phases/PHASE_10.md` und die Tag-Nachricht von `v1.0.0`.
