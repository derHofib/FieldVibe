# Nacharbeiten – offene Punkte aus Phase 1–7

Kein eigener Abschnitt des Lastenhefts (der endet mit Phase 7/Abschnitt 15) –
diese Runde arbeitet gezielt die "Was offen bleibt"-Punkte ab, die in den
Phasen-Docs 1–7 als bewusst zurückgestellt dokumentiert waren. Zwei Punkte
aus der ursprünglichen Liste sind absichtlich **nicht** angegangen worden
(siehe "Was weiterhin offen bleibt").

## Was implementiert wurde

### Backend

- **`mandant_integrationen`-CRUD** (`GET/POST/PATCH/DELETE /api/integrationen`,
  nur `mandant_admin`): der seit Phase 1 vorbereitete generische Integrations-
  Slot hat jetzt tatsächlich Endpunkte. Secrets werden app-seitig mit Fernet
  verschlüsselt (`encrypt_secret`/`decrypt_secret`, Schlüssel aus
  `INTEGRATION_SECRET_KEY`, fällt auf `JWT_SECRET` zurück, wenn nicht
  separat gesetzt) statt im Klartext gespeichert zu werden – kein Ersatz für
  echtes Vault/KMS, aber ein klarer Fortschritt gegenüber Klartext. Aktuell
  einziger unterstützter `typ`: `"smtp"`.
- **SMTP-Mailversand + Kundenportal-Passwort-Reset**: `email_service.py`
  verschickt über die `smtp`-Integration eines Mandanten (blockierendes
  `smtplib` in einem Thread, damit ein lahmer SMTP-Server nicht den
  Event-Loop blockiert). Kundenportal bekommt
  `POST /api/kundenportal/auth/passwort-vergessen` (antwortet immer mit 202,
  unabhängig davon, ob die E-Mail existiert oder SMTP überhaupt konfiguriert
  ist – Enumeration-Schutz) und `POST .../passwort-zuruecksetzen` (kurzlebiges
  Single-Purpose-Token, eigener `TokenType.KUNDENPORTAL_PASSWORD_RESET`,
  niemals als Bearer-Token akzeptiert). Fallback ohne SMTP: ein Mitarbeiter
  kann das Passwort weiterhin direkt über
  `PATCH /api/kunden/{id}/portal-zugaenge/{zugang_id}` setzen.
- **Rechnungspositionen** (`rechnung_positionen`, mirror von
  `angebot_positionen`): Teil-/Sammelrechnungen mit eigenen Zeilen. Sind
  Positionen vorhanden, ist ihre Summe die Quelle der Wahrheit für
  `betrag_netto` (dieselbe Überlegung wie bei Angeboten); ohne Positionen
  bleibt der Phase-6-Weg (ein einzelner `betrag_netto`-Wert) unverändert
  nutzbar. `PATCH` verweigert das direkte Ändern von `betrag_netto`, sobald
  eigene Positionen existieren.
- **Mahnwesen** (`Rechnung.mahnstufe`/`letzte_mahnung_am`,
  `mahnwesen_service.py`): einfache automatische Eskalation überfälliger,
  noch unbezahlter Rechnungen nach konfigurierbaren Tagesschwellen
  (`MAHNSTUFE_1_TAGE`/`_2_/_3_`, Default 14/28/42 Tage). Eskaliert nur bei
  tatsächlichem Stufenwechsel (kein täglicher Benachrichtigungs-Spam),
  postet ein `VorgangEvent` am verknüpften Vorgang (falls vorhanden) und
  benachrichtigt Admin/Disponent.
- **Offline-Neuanlage eines Vorgangs**: `Vorgang.client_uuid` (unique,
  nullable) macht `POST /api/vorgaenge` idempotent, exakt dasselbe Muster
  wie `VorgangEvent.client_uuid` – ein Sync-Retry aus der Offline-Outbox
  gibt den bereits angelegten Vorgang zurück (200) statt einen zweiten zu
  erzeugen.
- **Scheduler pro Mandant konfigurierbar + Advisory Lock**:
  `Mandant.scheduler_stunde_utc` (NULL = globaler Default) plus
  `GET/PATCH /api/mandant/einstellungen` (`mandant_admin`-Self-Service).
  `run_pruefzyklen_scheduler`/`run_mahnwesen_eskalation` nehmen jetzt ein
  optionales `mandant_ids`-Filter. Der Worker läuft nicht mehr fix einmal
  täglich um 03:00 UTC, sondern stündlich: er ermittelt, welche Mandanten
  gerade ihre konfigurierte Stunde erreichen, und verarbeitet nur diese –
  geschützt durch einen Postgres-Session-Advisory-Lock
  (`pg_try_advisory_lock`, `worker_lock.py`), falls versehentlich mehr als
  ein Worker-Container gleichzeitig läuft.

### Frontend

- **Integrationen-Seite** (`/integrationen`, `mandant_admin`): SMTP
  einrichten/bearbeiten/deaktivieren/löschen, sowie eine Karte für die
  Scheduler-/Mahnwesen-Uhrzeit (Dropdown, "Standard (HH:00 UTC)" oder eine
  konkrete Stunde).
- **Kundenportal-Passwort-Reset-Seiten** (`/portal/passwort-vergessen`,
  `/portal/passwort-zuruecksetzen`): eigener, von der Staff-App komplett
  unabhängiger Flow, konsistent mit der in Phase 7 etablierten Trennung der
  beiden Auth-Räume. Ein "Passwort vergessen?"-Link wurde am Kundenportal-
  Login ergänzt.
- **Rechnungspositionen im Rechnung-Detail**: Positionen-Tabelle mit
  Hinzufügen-Formular (nur im Entwurf), spiegelt exakt die
  Angebot-Detail-UX aus Phase 6.
- **Offline-Hinweis** in "Neuer Vorgang": das Formular queued sich jetzt
  bei einem Netzwerkfehler automatisch in die bestehende Outbox
  (`queueVorgang`) und synchronisiert sich, sobald wieder eine Verbindung
  besteht – derselbe Mechanismus wie für Kommentare/Fotos seit Phase 4.

## Entscheidungen, die ich dokumentiere statt nachzufragen

- **Echte Buchhaltungs-API-Anbindung (lexoffice/sevdesk) bleibt bewusst
  aus**: ohne reale Zugangsdaten/API-Dokumentation wäre eine konkrete
  Integration geraten statt fundiert – das war schon in Phase 6 so
  dokumentiert und gilt unverändert. `mandant_integrationen` hat jetzt
  zumindest eine echte CRUD-Oberfläche und mit SMTP eine erste reale
  Nutzung; eine zweite Integration folgt, sobald eine mit echten Details
  ansteht.
- **Selbstregistrierung für Kunden bleibt aus**: das war in Phase 7 eine
  bewusste Design-Entscheidung (Zugänge werden von Mitarbeitern angelegt,
  passend für ein B2B-Handwerksgeschäft mit bestehenden
  Kundenbeziehungen), keine Lücke – daher hier nicht angefasst.
- **App-seitige Fernet-Verschlüsselung statt echtem Vault/KMS** für
  `secret_ref`: deutlich weniger Aufwand als eine externe Secret-Manager-
  Anbindung, aber ein echter Sicherheitsgewinn gegenüber Klartext. Wenn
  eine Integration mit höheren Anforderungen (Kredit-/Zahlungsdaten)
  ansteht, ist das der Punkt, eine echte KMS-Anbindung nachzuziehen.
- **Kein E-Mail-Enumeration-Leck beim Passwort-Reset**: `/passwort-vergessen`
  antwortet immer mit 202 – auch wenn die E-Mail unbekannt ist, der Zugang
  deaktiviert ist, oder der Mandant kein SMTP konfiguriert hat. Ein
  tatsächlicher SMTP-Zustellungsfehler wird serverseitig geloggt statt als
  500 durchgereicht, aus demselben Grund.
- **Positionssumme überschreibt `betrag_netto`, sobald Positionen
  existieren** (statt beide Werte parallel zu pflegen): exakt dieselbe
  "eine Quelle der Wahrheit"-Überlegung wie bei Angeboten in Phase 6.
- **`client_uuid` auf `Vorgang` statt eines komplizierteren
  Offline-Konflikt-Protokolls**: reicht aus, um den einzigen echten
  Fehlerfall (doppelter Sync-Versand nach Verbindungsabbruch) sicher
  abzudecken, ohne die Outbox-Architektur aus Phase 4 grundlegend zu
  verändern.
- **Scheduler-Stunde pro Mandant statt eines konfigurierbaren
  Cron-Ausdrucks**: eine einzelne Uhrzeit deckt den tatsächlichen
  Anwendungsfall (frühmorgens, aber ggf. in einer anderen Zeitzone als der
  Betrieb selbst) ab, ohne dass ein Mandant eine Cron-Syntax lernen muss.
- **Advisory Lock statt einer verteilten Lock-Bibliothek**: `pg_advisory_lock`
  ist bereits Teil der ohnehin vorhandenen Postgres-Instanz, kein
  zusätzlicher Dienst nötig – für "maximal ein Worker-Container pro
  Deployment" (die in Phase 5 dokumentierte Annahme) mehr als ausreichend.
- **Kein Docker-Compose-Live-Test**: in dieser Ausführungsumgebung ist
  weiterhin kein laufender Docker-Daemon erreichbar (`/var/run/docker.sock`
  existiert nicht) – derselbe, seit Phase 1 dokumentierte Umstand.

## Wie es getestet wird

```bash
cd backend && source .venv/bin/activate && python -m pytest   # 213 Tests
```

Neu in dieser Runde: `test_integrationen.py` (CRUD, Verschlüsselung
end-to-end über die DB verifiziert, unbekannter Typ abgelehnt, Rollen-/
Mandantenisolation), `test_email_service.py` (SMTP-Aufruf mit gemocktem
`smtplib.SMTP`, fehlende/unvollständige Konfiguration wirft
`EmailNichtKonfiguriert`, Login nur bei gesetztem Secret),
`test_kundenportal_reset.py` (voller Request-Mail-Reset-Login-Zyklus mit
aus der gemockten Mail extrahiertem Token, ungültiger/abgelaufener Token,
zu kurzes Passwort, Staff-Fallback-Passwort-Setzen), Erweiterungen in
`test_rechnungen.py` (Positionen überschreiben `betrag_netto`, Ergänzen nur
im Entwurf, `betrag_netto` nicht direkt änderbar bei vorhandenen
Positionen, PDF mit Positionen), `test_mahnwesen.py` (Eskalation auf Stufe
1/2, kein wiederholtes Eskalieren ohne Stufenwechsel, nicht-überfällige/
bezahlte/stornierte Rechnungen bleiben unberührt, Mandanten-Scoping),
Erweiterung in `test_vorgaenge.py` (`client_uuid`-Idempotenz: derselbe
Sync-Retry legt nie einen zweiten Vorgang an), Erweiterungen in
`test_scheduler.py` (`mandant_ids`-Scoping, `mandanten_faellig_um`
respektiert Override vs. globalen Default), `test_mandant_einstellungen.py`
(Default/Override/Zurücksetzen, Validierung 0–23, Rollen-/
Mandantenisolation), `test_worker_lock.py` (zweiter gleichzeitiger
Lock-Versuch scheitert, ist nach Freigabe wieder verfügbar).

End-to-End manuell mit Playwright gegen den echten Dev-Server + Backend +
lokalem PostgreSQL verifiziert: SMTP über die Integrationen-Seite
einrichten (Persistenz nach Reload geprüft) → Kundenportal
"Passwort vergessen" → Reset-Link-Token direkt generiert (kein echter
SMTP-Server in dieser Umgebung verfügbar) → neues Passwort setzen → Login
mit neuem Passwort. Rechnung mit zwei Positionen über die API angelegt,
Detail-Seite zeigt beide Zeilen und die korrekte Summe, PDF-Erzeugung
geprüft. Offline-Neuanlage eines Vorgangs: `POST /api/vorgaenge` gezielt
per Route-Interception abgebrochen (zuverlässiger als
Playwright-Context-Offline-Emulation, die anstehende Requests manchmal nur
verzögert statt sie sofort abzulehnen) → sofortige Navigation zum Feed,
Outbox-Badge zeigt "🕘 1", IndexedDB enthält den Eintrag → nach Freigabe
des Requests synchronisiert sich der Vorgang automatisch und erscheint im
Feed. Scheduler-Uhrzeit über die Integrationen-Seite gesetzt, nach Reload
persistiert geprüft. Impersonation-Start mehrfach durchlaufen, dabei
gezielt auf 403-Antworten und Konsolenfehler geachtet – keine beobachtet.

## Was weiterhin offen bleibt

- Echte Buchhaltungs-API-Anbindung (lexoffice/sevdesk o. ä.) – bewusst
  nicht ohne reale Zugangsdaten gebaut (siehe oben).
- Kundenportal-Selbstregistrierung – bewusste Design-Entscheidung aus
  Phase 7, keine Lücke.
- Echtes Vault/KMS für Integrations-Secrets (aktuell: app-seitige
  Fernet-Verschlüsselung, siehe oben).
- Docker-Compose-Stack wurde weiterhin nie gegen einen echten laufenden
  Docker-Daemon getestet (Umgebungseinschränkung, kein Code-Mangel).
- Highlights (Alben/Sortierung), Materialwirtschaft (Lieferanten/
  Bestellungen), Insights (Zeitraum-Filter/Export) – aus Phase 7 weiterhin
  offen, in dieser Runde nicht Teil des Auftrags.
