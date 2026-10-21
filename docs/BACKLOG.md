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

## Erledigt, zur Einordnung

`v1.0.0` (17.08.2026) markiert den Ausgangsstand nach Zusammenführung
von Office-Desktop-Oberfläche, Postfach (IMAP/SMTP-Mailclient),
Einladungssystem (Mitarbeiter/Kunde) samt Registrierungsseiten,
Account-Typen mit Rechte-Matrix und globalem SMTP-Fallback. Details siehe
`docs/phases/PHASE_10.md` und die Tag-Nachricht von `v1.0.0`.
