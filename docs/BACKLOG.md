# Offene Punkte & Ideen

Sammelstelle für alles, was besprochen, aber noch nicht entschieden oder
gebaut ist — damit es nicht verloren geht, wenn eine Session-Historie mal
komprimiert wird. Durchnummeriert, damit man beim Abarbeiten einfach per
Nummer referenzieren kann ("mach jetzt 3"). Reihenfolge der Nummern ist
keine Priorität, nur Referenz — neue Punkte hängen am Ende an, bestehende
Nummern werden nicht neu vergeben, damit alte Verweise gültig bleiben.

## 1. Partnerportal fertigstellen

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

## Erledigt, zur Einordnung

`v1.0.0` (17.08.2026) markiert den Ausgangsstand nach Zusammenführung
von Office-Desktop-Oberfläche, Postfach (IMAP/SMTP-Mailclient),
Einladungssystem (Mitarbeiter/Kunde) samt Registrierungsseiten,
Account-Typen mit Rechte-Matrix und globalem SMTP-Fallback. Details siehe
`docs/phases/PHASE_10.md` und die Tag-Nachricht von `v1.0.0`.
