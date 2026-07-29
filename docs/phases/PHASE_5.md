# Phase 5 – Steuerung

## Was implementiert wurde

### Backend

- **Termine / Dispo**: neue Tabelle `termine` (Abschnitt 4.5), an einen
  Vorgang und einen Techniker gebunden, mit `CHECK (ende_at > start_at)`
  und Index `idx_termine_techniker (techniker_id, start_at)` für die
  Konfliktprüfung. `POST/PATCH /api/termine` sind `mandant_admin`/
  `disponent`-only, `GET` ist für alle drei Tenant-Rollen offen (RLS
  scoped trotzdem korrekt).
- **Terminkonflikt-Prüfung** (`app/services/dispo_service.py`):
  Überschneidung (echte Zeitraum-Überlappung desselben Technikers) und
  eine Fahrzeit-Heuristik per Haversine-Luftlinie zwischen den
  `geo_lat`/`geo_lng` der beteiligten Anlagen, geteilt durch eine
  angenommene Durchschnittsgeschwindigkeit (`DISPO_GESCHWINDIGKEIT_KMH`,
  Default 40 km/h) plus Pufferzeit (`DISPO_PUFFER_MINUTEN`, Default 30
  Min.). Beides sind **Warnungen, kein Hard-Block** (Abschnitt 12) – `POST`
  und `PATCH` legen den Termin trotzdem an und liefern die Warnungen im
  Response mit, damit der Disponent informiert entscheiden kann.
- **Prüfzyklen** (`pruefzyklen`, Abschnitt 4.5): pro Anlage wiederkehrende
  Prüfungen (z. B. E-Check/DGUV V3) mit Intervall in Monaten.
  `naechste_pruefung_am` wird beim Anlegen und bei jeder Aktualisierung von
  `letzte_pruefung_am` automatisch neu berechnet (`app/services/
  date_utils.py::add_months`, kalendergenau inkl. Tages-Clamping am
  Monatsende).
- **Prüfmittel** (`pruefmittel`, Abschnitt 4.7): Kalibrierungs-Tracking für
  Messgeräte, optional einem Techniker zugewiesen, mit Status
  `aktiv`/`defekt`/`ausser_betrieb`.
- **Prüfzyklen-Scheduler** (`app/services/scheduler_service.py`,
  `app/worker.py`): täglicher Lauf (03:00 UTC) in einem eigenen
  Compose-Service `worker` – getrennt vom Backend-Container, damit ein
  API-Deploy den Takt nicht stört. Für jeden fälligen (oder innerhalb von
  `PRUEFZYKLUS_VORLAUF_TAGE`, Default 30 Tage, fällig werdenden) aktiven
  Prüfzyklus wird **einmalig** ein Vorgang (`leistungstyp=pruefung`)
  angelegt und Admin/Disponent per Notification (`typ=frist`) informiert.
  `Pruefzyklus.offener_vorgang_id` verhindert doppelte Vorgänge bei
  wiederholten Läufen; wird der verknüpfte Vorgang auf `abgeschlossen`
  gesetzt (`app/api/routes/vorgaenge.py`), gilt die Prüfung als
  durchgeführt – `letzte_pruefung_am`/`naechste_pruefung_am` werden
  fortgeschrieben und `offener_vorgang_id` wird geleert. Fällige
  Prüfmittel erzeugen keinen Vorgang (Kalibrierung ist kein
  Kundenauftrag), nur eine Erinnerung – dedupliziert gegen bereits
  ungelesene Notifications, damit der Scheduler nicht täglich spammt.
- **`/healthz`** meldet jetzt zusätzlich `scheduler_letzter_lauf` (Zeitpunkt
  des letzten erfolgreichen Scheduler-Laufs, aus dem `audit_log`
  ausgelesen) – die in Phase 4 offene Stelle "Scheduler-Zeitstempel folgt
  mit Phase 5".
- **Stories** (`GET /api/stories`) liefern jetzt echte Daten statt leerer
  Arrays: `heute` = die eigenen Termine des Aufrufers am aktuellen Tag
  (bewusst personenbezogen, nicht das ganze Team – die Story-Leiste ist
  eine persönliche Kurzübersicht, kein Dispo-Ersatz); `fristen` = fällige/
  bald fällige Prüfzyklen (verlinkt auf die Anlage) und
  Prüfmittel-Kalibrierungen, mit Ampel (rot = überfällig, gelb = binnen 7
  Tagen, grün = später innerhalb des Vorlaufs).

### Frontend

- **Dispo-Board** (`/dispo`, `DispoBoardPage.tsx`): eigene Desktop-Ansicht
  für `mandant_admin`/`disponent` (bewusst kein Feed-Ersatz – Disposition
  ist keine Kommunikation), erreichbar über einen zusätzlichen
  Bottom-Nav-Eintrag, der für `techniker` gar nicht angezeigt wird; ein
  direkter Aufruf der URL durch einen Techniker leitet zu `/feed` um.
  Wochenraster (Techniker × Wochentag), Termine sind per natives HTML5
  Drag-and-Drop zwischen Tagen/Technikern verschiebbar (verifiziert per
  Playwright mit echten Maus-Events, nicht nur simulierten DOM-Events) –
  verschiebt Datum und Techniker, behält Uhrzeit/Dauer bei. Formular zum
  Anlegen neuer Termine (Vorgang/Techniker/Titel/Zeitraum), zeigt
  Konflikt-/Fahrzeit-Warnungen aus dem Backend an.
- **Prüfmittelverwaltung** (`/pruefmittel`, `PruefmittelPage.tsx`): Liste
  mit Fälligkeitsfarbe, Anlegen, Zuweisung an einen Nutzer, "Kalibrierung
  erfolgt (heute)"-Button.
- **Prüfzyklen auf dem Anlagen-Profil**: neue Sektion in
  `AnlageProfilePage.tsx` – Liste, Anlegen (nur Admin/Disponent),
  "Prüfung erfolgt (heute)"-Button.
- **Termin-Planung im Vorgangs-Chat**: neue Sektion in
  `VorgangDetailPage.tsx` – zeigt vorhandene Termine des Vorgangs (für
  alle Rollen sichtbar) und ein Anlage-Formular (nur Admin/Disponent),
  inkl. Anzeige der vom Backend gelieferten Warnungen nach dem Anlegen.

## Entscheidungen, die ich dokumentiere statt nachzufragen

- **Fahrzeit-Heuristik statt Routendienst**: Luftlinie (Haversine) durch
  eine angenommene Durchschnittsgeschwindigkeit ist für die
  Handwerker-Praxis ("zwei Termine an entgegengesetzten Stadtenden in 15
  Minuten") ausreichend, ohne einen externen Routing-Dienst/API-Key
  einzuführen. Fehlen Geo-Koordinaten an einer beteiligten Anlage, wird
  die Fahrzeit-Prüfung für diesen Vergleich übersprungen (kein erfundener
  Wert).
- **Konflikte als Warnung, nie Hard-Block**: sowohl Überschneidung als
  auch Fahrzeit – deckt sich mit Abschnitt 12 und lässt dem Disponenten
  die Entscheidungshoheit (z. B. bewusst zwei Techniker kurz parallel
  einplanen).
- **Prüfzyklen-Scheduler erzeugt Vorgänge, Prüfmittel nur Erinnerungen**:
  eine fällige Anlagenprüfung ist ein Kundenauftrag (braucht einen
  Vorgang im Feed, den ein Techniker abarbeitet), eine fällige
  Werkzeug-Kalibrierung ist ein interner Vorgang ohne Kundenbezug – dafür
  reicht eine Erinnerung an Admin/Disponent/zugewiesenen Nutzer.
- **`offener_vorgang_id` statt Zeitfenster-Deduplizierung**: verhindert
  doppelte Vorgänge bei täglichen Scheduler-Läufen zuverlässiger als ein
  "wurde in den letzten X Tagen schon einer angelegt"-Check, weil es exakt
  an den tatsächlichen Erledigungsstatus koppelt statt an eine geschätzte
  Zeitspanne.
- **Dispo-Board/Prüfmittelverwaltung nur für Admin/Disponent**: beide
  Seiten leiten einen `techniker`, der die URL direkt aufruft, zu `/feed`
  um – konsistent mit den Backend-Berechtigungen für `POST`/`PATCH` auf
  diesen Ressourcen.
- **"heute" in der Story-Leiste ist personenbezogen**: zeigt die eigenen
  Termine des Aufrufers, nicht die des ganzen Teams – das Dispo-Board
  deckt die Team-Sicht bereits eigenständig ab.

## Wie es getestet wird

```bash
cd backend && source .venv/bin/activate && python -m pytest   # 125 Tests
```

Neu in Phase 5: `test_termine.py` (CRUD, Berechtigungen, RLS-Isolation,
Überschneidungs- und Fahrzeit-Warnungen inkl. eines echten Berlin/München-
Abstands, Statuswechsel), `test_pruefzyklen.py`, `test_pruefmittel.py`,
`test_scheduler.py` (Vorgang+Notification-Erzeugung, keine Duplikate bei
wiederholten Läufen, Fortschreibung nach Vorgangs-Abschluss,
Prüfmittel-Erinnerung ohne Notification-Spam), sowie neue Fälle in
`test_stories.py` für `heute`/`fristen`.

End-to-End manuell mit Playwright gegen den echten Dev-Server + Backend +
lokalem PostgreSQL + `moto`-S3-Server verifiziert: Login als Disponent →
Dispo-Board öffnen → Termin anlegen → per Drag-and-Drop auf einen anderen
Tag verschieben (Uhrzeit bleibt erhalten) → Prüfmittel anlegen und als
kalibriert markieren → Anlagen-Profil öffnen, Prüfzyklus anlegen → im
Vorgangs-Chat einen Termin direkt planen. Zusätzlich verifiziert, dass ein
`techniker`-Login weder den Dispo-Nav-Eintrag sieht noch `/dispo` bzw.
`/pruefmittel` per direkter URL erreichen kann (Redirect zu `/feed`).

## Was offen bleibt

- Mängel, Angebote, PDF-Protokolle, Rechnungs-API: Phase 6.
- Kundenportal, Highlights, Materialwirtschaft, Insights: Phase 7.
- Der Scheduler läuft als fester täglicher Takt (03:00 UTC) ohne
  konfigurierbare Uhrzeit pro Mandant – für einen Betrieb pro
  Compose-Stack ausreichend, würde aber bei echtem Multi-Server-Deploy
  ggf. eine verteilte Lock-Strategie brauchen (aktuell: ein Worker-
  Container pro Deployment, kein Cluster-Betrieb vorgesehen).
