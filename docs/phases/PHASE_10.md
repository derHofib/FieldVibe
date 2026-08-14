# Phase 10 – Postfach: persönlicher E-Mail-Client (IMAP/SMTP)

Auf ausdrücklichen Wunsch: FieldVibe soll für den einzelnen Nutzer Outlook &
Co. ersetzen können, statt nur System-/Transaktions-Mails zu verschicken
(das leistet `email_service.py` seit Phase 8 bereits, bleibt unverändert).
Abgestimmter Zuschnitt für V1: **persönliches** Postfach je Nutzer (nicht
eine gemeinsame Team-Inbox), **generisches IMAP/SMTP** (jeder Provider,
kein OAuth-Flow) und **voller Funktionsumfang** in der Office-Oberfläche
(Ordner, Suche, Signatur) — die Feld-App bekommt bewusst eine schlankere
Ansicht.

## Architekturentscheidung: fünf unabhängig lauffähige Stufen

Jede Stufe wurde als eigener Commit umgesetzt, mit vollem Test-/Build-Lauf
davor — kein Punkt, an dem der bestehende Code für längere Zeit kaputt war.

## Stufe 1 — Kontoverwaltung (Backend)

- **`mail_accounts`** (Migration `0060`): IMAP+SMTP-Zugangsdaten je Nutzer,
  ein gemeinsames Passwort für beide Protokolle (verschlüsselt über das
  bestehende `encrypt_secret`/`decrypt_secret` aus Phase 8 — kein neuer
  Schlüssel nötig). RLS nur auf den Mandanten wie bei `MandantIntegration`;
  die zusätzliche Einschränkung auf den eigenen Nutzer passiert app-seitig,
  gleiches Muster wie `GespeicherterFilter` — ein Kollege im selben
  Mandanten darf das Postfach nicht sehen oder ändern.
- **Neues Mandanten-Modul `"postfach"`**, per Super-Admin abschaltbar wie
  die übrigen optionalen Module.
- **`POST /api/mail-accounts/test-verbindung`**: echter IMAP+SMTP-Login-
  Versuch, bevor überhaupt etwas gespeichert wird — Fehler (falscher Host,
  falsches Passwort) zeigen sich sofort im Formular statt erst nach dem
  Anlegen.

## Stufe 2 — IMAP-Sync-Engine (Backend)

- **`mail_folders`/`mail_messages`/`mail_attachments`** (Migration `0061`).
  Sync läuft je Ordner inkrementell über IMAP-UIDs — gleiches Grundprinzip
  wie der bestehende Rechnungseingang-Import (`email_ingest_service.py`),
  hier aber mit echter **UIDVALIDITY-Behandlung**: ändert sie sich
  serverseitig, wird der Ordner komplett neu aufgebaut statt (wie beim
  Rechnungseingang) bewusst ignoriert zu werden — bei einem täglich
  genutzten persönlichen Postfach fällt "Nachrichten verschwinden oder
  verdoppeln sich" deutlich stärker auf.
- **Eigener 2-Minuten-Takt im Worker**, nicht der stündliche Scheduler-Tick:
  eine Stunde Verzögerung wäre für einen Outlook-Ersatz spürbar schlecht.
  Echtes IMAP IDLE (Server-Push) ist für V1 bewusst zurückgestellt.
  `worker_lock()` bekam dafür einen zweiten, unabhängigen Advisory-Lock-
  Schlüssel (`mail_sync_lock()`), damit sich Mail-Sync und stündlicher Tick
  nicht gegenseitig blockieren.
- Volltextsuche via `search_vector`/`tsvector`, gleiches Muster wie
  `vorgaenge.search_vector` aus Phase 3. Anhänge landen wie Fotos/Belege in
  S3/MinIO.

## Stufe 3 — Lesen, Senden, Antworten, Weiterleiten (Backend)

- Ordnerliste, Cursor-paginierte Nachrichtenliste (gleiches Cursor-Prinzip
  wie `feed.py`), Nachricht lesen/als gelesen markieren, Anhang-Download
  über presigned URL.
- Eigener SMTP-Sendedienst **je Nutzerkonto** (`mail_send_service.py`,
  getrennt von `email_service.py`). `Bcc` wird bewusst nicht als Kopfzeile
  gesetzt, sondern nur ins SMTP-Envelope aufgenommen — sonst sähen andere
  Empfänger, wer verdeckt mitgelesen hat.
- Antworten setzt `In-Reply-To`/`References` für korrektes Threading im
  Client. Empfänger ("nur Absender" vs. "Allen antworten") bestimmt bewusst
  der **Client**, nicht der Server — dieselbe Route bedient beide Fälle.
- **Keine lokale Kopie gesendeter Mails**: taucht über den nächsten
  Mail-Sync-Tick im Gesendet-Ordner auf, sofern der Provider dort eine
  Kopie ablegt (die meisten tun das bei authentifiziertem SMTP-Versand über
  denselben Account automatisch).

## Stufe 4 — Office-Oberfläche (Drei-Spalten-Mailclient)

- Neuer Sidebar-Eintrag "Postfach", aus derselben `navSeiten.ts`-Quelle wie
  jede andere Seite. Neuer Icon-Ton `"teal"` — die bisherigen acht Töne
  reichten für einen eigenen, unverwechselbaren Funktionsbereich nicht mehr
  (`docs/DESIGN.md` entsprechend ergänzt).
- Ohne verbundenes Postfach zeigt die Seite direkt das Einrichtungsformular
  statt eines Leerzustands mit Verweis auf eine andere Stelle.
- Mit Konto: Ordnerliste, Nachrichtenliste (Suche inklusive) und Leseansicht
  nebeneinander. Das Compose-Panel für Neu/Antworten/Weiterleiten **ersetzt**
  dabei bewusst die Leseansicht statt als Modal zu überlagern — passt zur
  vorhandenen Drei-Spalten-Fläche, ohne ein weiteres UI-Muster einzuführen.
- HTML-Nachrichten laufen in einem `sandbox`-iframe ohne Skriptrechte;
  externe Bilder (Tracking-Pixel) laden trotzdem — dasselbe Risiko wie in
  jedem Mailclient, kein FieldVibe-spezifisches Problem.

## Stufe 5 — Feld-App: schlanke Mobil-Ansicht

- Liste + Lesen + Antworten, bewusst **ohne** Ordner-Verwaltung — zeigt
  immer den Posteingang des ersten Kontos. Gesendet/Papierkorb/mehrere
  Postfächer gleichzeitig bleiben der Office-Ansicht vorbehalten.
- Kontoeinrichtung nutzt **dieselbe** `MailKontoFormular`-Komponente wie die
  Office-Ansicht (dafür responsiv gemacht: `grid-cols-1 sm:grid-cols-2`
  statt fest zweispaltig — auf 390 px wären IMAP/SMTP-Felder sonst zu
  schmal). Kein zweites Formular für dieselben zehn Felder.
- Antworten blendet das Compose-Panel erst nach Tap ein, statt es
  dauerhaft unter jeder Nachricht offen zu halten — sonst hätte der
  "Abbrechen"-Button keine sinnvolle Wirkung gehabt.
- Route `/postfach` wird von beiden Shells gemeinsam genutzt (Feld-Gate in
  `App.tsx` + `OfficeApp.tsx`), keine zwei verschiedenen Pfade zur selben
  Seite.

## Verifikation

`pytest`: 647 Tests grün (35 neue: Kontoverwaltung, Sync-Engine inkl.
UIDVALIDITY-Wechsel, Lese-/Sende-Routes, `mail_send_service` mit gemocktem
`smtplib`). Migrationszyklus (`upgrade head` → `downgrade -1` → `upgrade
head`) für beide neuen Migrationen sauber. `npm run lint`/`build` clean.

Live gegen den echten Dev-Server: Formular → "Verbindung testen" → Backend
versucht einen echten IMAP/SMTP-Connect gegen eine ungültige Domain → die
Fehlermeldung (`[Errno -2] Name or service not known`) kommt bis in die UI
durch — belegt, dass die gesamte Kette (Frontend → Route → `mail_service`
→ Fehlerpropagation → UI) funktioniert, auch ohne echten Mailserver in
dieser Umgebung. Mobile Regression (Feed, Bottom-Nav, Service Worker)
weiterhin unauffällig. Dark Mode auf beiden Shells geprüft.

**Nicht möglich in dieser Umgebung:** ein vollständiger Rundlauf gegen
einen echten IMAP-Server (Nachricht ankommt → Sync holt sie ab → wird
angezeigt → Antwort geht raus → taucht im Gesendet-Ordner auf). Die
IMAP-Sync-Engine ist stattdessen durch gezielte Unit-Tests abgedeckt, die
`_sync_account_blockierend` mocken (gleiches Muster wie die bestehenden
Tests für `email_ingest_service.py`) — reale Server-Eigenheiten (Non-
Standard-LIST-Antworten, IMAP-UTF-7-Ordnernamen, exotische Flag-Formate)
zeigen sich erst im echten Betrieb.

## Was offen bleibt

- **Kein IMAP IDLE.** Sync-Takt ist 2 Minuten Polling, kein Server-Push.
  Für V1 bewusst so entschieden (siehe Stufe 2) — spürbar, aber kein
  Blocker.
- **Nicht-ASCII-Ordnernamen** (z. B. "Gesendete Elemente" bei manchen
  Providern) werden nicht aus IMAP-UTF-7 dekodiert, sondern roh angezeigt.
  Eine vollständige UTF-7-Implementierung war für V1 nicht im Verhältnis
  zum Nutzen.
- **Weiterleiten hängt Original-Anhänge nicht erneut an** — nur der
  zitierte Text. Ein erneuter Datei-Upload/-Anhang beim Weiterleiten ist
  ein separater Ausbau.
- **Keine lokale Kopie gesendeter Mails** vor dem nächsten Sync-Tick (siehe
  Stufe 3) — bei Providern ohne automatische Gesendet-Kopie fehlt die
  gesendete Mail bis zu 2 Minuten in der Liste, dauerhaft, wenn der
  Provider gar keine Kopie ablegt. Eine echte IMAP-`APPEND` nach dem Senden
  wäre der nächste Schritt, falls das in der Praxis stört.
- **Stufe 6 aus dem ursprünglichen Phasenplan bewusst nicht gebaut**:
  Ordner-Verwaltung (anlegen/umbenennen/löschen), Regeln/Filter, weitere
  Provider-Komfortfunktionen. Erst bauen, wenn sich im echten Gebrauch
  zeigt, was wirklich fehlt.
- **Keine Verknüpfung mit Kunden/Vorgängen.** Bewusste Entscheidung aus der
  Scoping-Rückfrage zu Beginn ("Persönliches Postfach je Nutzer" statt
  "Beides, gestuft") — eine Team-Inbox mit automatischer Kunden-Verknüpfung
  wäre ein eigener, späterer Umbau.
- **OAuth (Gmail/Microsoft 365) nicht unterstützt** — ebenfalls bewusste
  Entscheidung aus der Scoping-Rückfrage. Nutzer mit aktivierter
  Zwei-Faktor-Anmeldung brauchen ein App-Passwort; das Formular weist bei
  erkanntem `gmail`-Hostnamen darauf hin.
- **Docker/Migrationszyklus auf dem echten Server ungetestet** (kein
  Docker-Daemon in dieser Umgebung, Umgebungseinschränkung, kein
  Code-Mangel) — wie bei jeder vorherigen Phase.
