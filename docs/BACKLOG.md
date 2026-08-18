# Offene Punkte & Ideen

Sammelstelle für alles, was besprochen, aber noch nicht entschieden oder
gebaut ist — damit es nicht verloren geht, wenn eine Session-Historie mal
komprimiert wird. Ergänzt laufend, keine feste Reihenfolge innerhalb der
Abschnitte außer der angegebenen Priorität.

## Unfertige Arbeiten

- **Partnerportal hat keine Oberfläche.** Backend ist vollständig da
  (`app/api/routes/partner.py`, `partner_auth.py`, `partner_portal.py`,
  Models `partner`/`partner_nachweis`/`partner_zugang`, Migration 0062) —
  Nachunternehmer-Verwaltung inkl. Freistellungsbescheinigung, eigener
  Login. Aber: kein Mitarbeiter kann im Frontend einen Partner anlegen,
  und der Partner selbst hat keine App/Seite, um sich einzuloggen.
- **Partner-Einladung fehlt im Frontend.** Analog zu Mitarbeiter-/
  Kunden-Einladung (`/registrieren`, `/portal/registrieren`) fehlt
  `/partnerportal/registrieren` als Seite — hängt am Punkt oben, da ohne
  Partnerportal-Oberfläche auch keine Registrierungsseite sinnvoll ist.
- **SMTP Port 465 (implizites SSL/TLS) wird nicht unterstützt** —
  `email_service.py` verbindet immer per klassischem SMTP + `starttls()`
  (passt zu Port 587). Ein Anbieter, der zwingend Port 465 verlangt,
  scheitert damit. Betrifft aktuell nicht den globalen FieldVibe-Versand
  (auf 587 korrigiert), könnte aber bei einzelnen Mandanten-eigenen
  SMTP-Konfigurationen auftreten.

## Offene Entscheidungen

- **Navigations-Neusortierung** (siehe Ausarbeitung vom 17.08., Artifact
  „FieldVibe Navigation"): Vorschlag A (Techniker-Zuweisungen und
  Partner-Verwaltung nach „Arbeit", Postfach nach „Kommunikation", Profil
  raus aus der Kategorie-Logik) ist der risikoarme Vorschlag. Vorschlag B
  geht weiter und teilt „Verwaltung" sichtbar in „Zugriff & Team" und
  „Firma einrichten" auf. Offene Frage dabei: wohin mit „Team-Zeiten"
  (Zugriff & Team vs. Finanzen)?
- **„Meine Ansicht" — personalisierte Menü-Profile.** Ein Nutzer soll in
  seinem Profil zwischen vordefinierten Ansichten (Techniker, Dispo,
  Büro/Buchhaltung, „Alles") wechseln können, die filtern/kuratieren, was
  in Bottom-Nav bzw. Office-Sidebar prominent angezeigt wird — nie mehr,
  als die echten Rechte erlauben. Der mandant_admin soll diese Profile
  selbst pflegen können (Vorschläge, die er umbenennen/umbauen/löschen
  kann, kein starres System). Zusätzlich: eigene Startseite je Nutzer
  statt immer Feed/Vorgänge. Skizzierter Umfang: neue Tabelle
  `ansichts_profile` (mandantengebunden, RLS), neue Felder auf `User`
  (`ansicht_profil_id`, `startseite`), CRUD-Routen, neue Verwaltungsseite,
  neuer Abschnitt auf der Profil-Seite, Sidebar-Filterung mit
  „Alle Bereiche anzeigen"-Fluchtweg. Noch nicht begonnen.
- **Portal-Branding — eigenes Logo im Kundenportal.** Ein Mandant lädt
  sein Firmenlogo hoch; es ersetzt die FieldVibe-Wortmarke auf der
  Kundenportal-Login-Seite und im Portal-Header seiner Kunden, mit einem
  dezenten „by FieldVibe"-Hinweis unten links. Mockup als Artifact gezeigt
  (17.08.). Naheliegender Ansatzpunkt: das bereits vorhandene, bisher
  ungenutzte `Mandant.branding`-JSON-Feld — keine neue Migration nötig.
  Zu unterscheiden von der bereits gebauten Kunden-Logo-Funktion (ein
  einzelner Kunde zeigt sein eigenes Logo auf seinem persönlichen
  Portal-Link) — hier geht es um das Logo des Betriebs selbst, für alle
  seine Kunden gleich. Noch nicht begonnen.

## Kleinere Klarheits-Punkte (kein Bug, aber verwirrend)

- Nav-Label „Zeiterfassung" führt technisch zur Route `/statistik`
  (historisch gewachsener Name).
- Seitenname „Geschäft" ist als Bezeichnung vage — bündelt Kunden/
  Material/Abrechnung, aber der Name verrät das nicht.

## Erledigt, zur Einordnung

`v1.0.0` (17.08.2026) markiert den Ausgangsstand nach Zusammenführung
von Office-Desktop-Oberfläche, Postfach (IMAP/SMTP-Mailclient),
Einladungssystem (Mitarbeiter/Kunde) samt Registrierungsseiten,
Account-Typen mit Rechte-Matrix und globalem SMTP-Fallback. Details siehe
`docs/phases/PHASE_10.md` und die Tag-Nachricht von `v1.0.0`.
