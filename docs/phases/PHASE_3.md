# Phase 3 – Social-UX

## Was implementiert wurde

### Backend

- **`GET /api/feed`**: echte Cursor-Pagination über `(last_activity_at, id)`
  (opaker Base64-Cursor, kein Offset). Filter: `status`, `kunde_id`, `tag`,
  `leistungstyp`, `abrechnungsart`. Jede Karte enthält Kunde, Kurzadresse der
  Anlage, den Vorschautext des letzten Events, Tags und `timer_laeuft`
  (siehe "Was offen bleibt").
- **`GET /api/stories`**: `wartet_kunde` ist mit echten Daten befüllt
  (Vorgänge im Status `wartet_kunde`, die seit mehr als 3 Tagen keine neue
  Aktivität hatten). `heute`, `fristen`, `material` liefern bewusst leere,
  aber typisierte Arrays – die zugrunde liegenden Datenmodelle (Termine,
  Prüfzyklen/Prüfmittel, Artikel/Lagerbestand) kommen erst in Phase 4/5/7.
- **`GET /api/search`**: `pg_trgm` für Kunden/Anlagen/Vorgangsnummer/Tags,
  Volltextsuche über eine materialisierte, per Trigger gepflegte
  `tsvector`-Spalte auf `vorgaenge` (deckt Titel, Beschreibung **und** alle
  Kommentar-Event-Texte ab – ein zweiter Trigger auf `vorgang_events` hängt
  jeden neuen Kommentar an den `search_vector` des Vorgangs an, statt ihn neu
  zu berechnen). Ein führendes `#` durchsucht ausschließlich Tags.
- **Profile mit Mini-Feed**: `GET /api/kunden/{id}/profil` und
  `GET /api/anlagen/{id}/profil` liefern Stammdaten + zugehörige
  Anlagen/Vorgänge + Tags. Techniker-Profil zeigt in dieser Phase nur die
  eigenen Stammdaten (Termine/Zeiten/Prüfmittel kommen mit Phase 4/5).
  Prüfmittel-Profile sind komplett Phase 5.
- **SSE (`GET /api/stream`)**: In-Process-Pub/Sub (`EventBus`), ein
  Consumer-Queue pro Client, gekeyt auf `mandant_id`. Events:
  `vorgang_event` (neuer Chat-Eintrag), `feed_update` (Vorgang angelegt/
  geändert), `notification` (neue Benachrichtigung). Token kommt als
  Query-Parameter, weil `EventSource` im Browser keine Custom-Header
  unterstützt.
- **`notifications` + @Mentions**: Kommentare erkennen
  `@[Name](user-id)`-Markup (das Frontend fügt es über einen Mention-Picker
  ein), erzeugen eine `Notification` je erwähntem Kollegen (nur innerhalb
  desselben Mandanten, RLS-geprüft) und pushen sie per SSE.
  `GET/POST /api/notifications`.

### Frontend

- Der bisherige Platzhalter für `mandant_admin`/`disponent`/`techniker` ist
  durch die echte Feld-App ersetzt: Bottom-Nav mit **Feed, Suche, Neu,
  Benachrichtigungen, Profil** (Abschnitt 7.1).
- **Feed**: Story-Leiste oben (nur befüllte Gruppen werden angezeigt),
  darunter streng chronologische Vorgangskarten mit "Mehr laden"
  (Cursor-basiert, kein Endlos-Scroll-Autoload).
- **Vorgangs-Chat**: Kopfbereich mit Statuswechsler, chronologischer
  Event-Stream (System-Events zentriert/grau abgesetzt), Umschalter
  interne/Kundenansicht (filtert auf `kundensichtbar`), Kommentarfeld mit
  @Mention-Picker und "Für Kunde sichtbar"-Checkbox.
- **Suche**: Typeahead gegen `/api/search`, Tag-Wolke als Startpunkt.
- **Neu**: Vorgang-Erstellung (Kunde, Titel, Leistungstyp, Abrechnungsart).
  Foto/Zeiterfassung/QR-Scan sind als "kommt mit Phase 4" vermerkt statt als
  funktionslose Buttons gezeigt.
- **Benachrichtigungen**: Liste mit Ungelesen-Badge, Klick markiert gelesen
  und springt zum referenzierten Vorgang.
- **Profil**: eigene Stammdaten; Kunde-/Anlage-Profile sind über Klick aus
  Feed/Chat erreichbar (`/kunden/:id`, `/anlagen/:id`).
- **Live-Updates**: `useEventStream`-Hook öffnet `EventSource` und
  invalidiert die passenden TanStack-Query-Keys (`feed`, `stories`,
  `vorgang-events`, `notifications`).
- **Impersonation führt jetzt in die Feld-App**: Vorher (Phase 1, als es
  noch keine Feld-App gab) landete "Login als Mandant" nur auf einer
  eingeschränkten Accounts-Ansicht. Jetzt sieht der `super_admin` beim
  Impersonieren exakt das, was ein echter `mandant_admin` sähe – das ist der
  eigentliche Zweck von Impersonation als Support-Werkzeug. Die
  Plattform-Verwaltung (Mandanten/Accounts/Audit-Log) bleibt ausschließlich
  einem echten, nicht-impersonierenden `super_admin` vorbehalten.

## Entscheidungen, die ich dokumentiere statt nachzufragen

- **@Mention-Syntax**: `@[Name](user-id)` statt Freitext-Matching auf Namen
  oder E-Mail – eindeutig parsbar, verbreitetes Muster (Slack/GitHub-artig).
- **SSE-Skalierung**: In-Process-Pub/Sub passt zum aktuellen
  Docker-Compose-Stack (ein Backend-Container). Für mehrere Backend-Instanzen
  bräuchte es später Postgres `LISTEN/NOTIFY` oder Redis als gemeinsamen
  Broker – hier bewusst nicht vorgezogen.
- **`/api/users` GET jetzt auch für disponent/techniker**: ursprünglich
  (Phase 1) nur `super_admin`/`mandant_admin`. Der @Mention-Picker braucht
  die Kollegenliste; RLS scoped sie ohnehin auf den eigenen Mandanten, und
  Namen/E-Mails sind nicht so sensibel wie Account-Verwaltung (Anlegen/
  Ändern bleibt admin-only).
- **Techniker-/Kunde-/Anlage-Berechtigungen** unverändert zu Phase 2
  (siehe `PHASE_2.md`).

## Wie es getestet wird

```bash
cd backend && source .venv/bin/activate && python -m pytest   # 88 Tests
```

Die SSE-Auslieferung selbst wird nicht per pytest gegen den echten
`/api/stream`-Endpunkt getestet (ASGITransport + ein einzelner
Test-Event-Loop machen einen wirklich nebenläufigen Reader/Writer fragil
und flaky) – stattdessen: `test_stream.py` deckt die Auth-Guards
(401/403/422) ab, `test_event_bus.py` testet die Pub/Sub-Logik selbst
deterministisch, und die Live-Auslieferung wurde manuell per `curl -N`
gegen einen laufenden Server verifiziert (SSE-Event kam nach einem POST auf
`/api/vorgaenge/{id}/events` tatsächlich an).

Frontend wurde per Playwright-Browser-Test end-to-end durchgespielt: Login
als Techniker → Feed → Vorgang öffnen → kommentieren → Status ändern →
Kundenansicht umschalten → Suche → neuen Vorgang anlegen →
Benachrichtigungen → Profil; separat @Mention → Notification beim
erwähnten Kollegen → Klick navigiert zum Vorgang; separat Super-Admin →
Impersonation → Feed-App mit Banner → Beenden → zurück zum
Plattform-Dashboard.

## Was offen bleibt

- `timer_laeuft` in der Feed-Karte ist immer `false` (Zeiterfassung kommt
  mit Phase 4/5).
- `heute`/`fristen`/`material` in den Stories sind leer, bis Termine/
  Prüfzyklen/Material existieren.
- Foto-/Dokument-/Mangel-/Material-/Zeit-Anhänge im Chat-Aktionsmenü fehlen
  bewusst (Phase 4/6/7) – nur Kommentar und Statuswechsel sind aktuell
  funktional.
- Ein seltener, nicht-deterministischer Timing-Fall wurde beim manuellen
  Testen beobachtet: unmittelbar nach Start einer Impersonation können
  vereinzelt 1–2 erste Requests der neu gemounteten Feed-App noch mit dem
  alten super_admin-Token statt dem frisch gesetzten Impersonation-Token
  rausgehen (403, sofort gefolgt von einem erfolgreichen Retry durch den
  normalen React-Query-Refetch). Kein Datenverlust, keine falsch
  angezeigten Daten, nur ein kurzes Aufblitzen eines Ladezustands – wurde
  nicht weiter gejagt, da nicht reproduzierbar deterministisch und ohne
  funktionale Auswirkung.
- Insights/Dispo-Board/Kundenportal bleiben Phase 5/7 wie in Abschnitt 12
  vorgesehen.
