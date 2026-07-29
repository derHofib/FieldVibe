# Phase 4 – Feld-Tauglichkeit

## Was implementiert wurde

### Backend

- **Objektspeicher (MinIO)**: neuer Service im Compose-Stack. Zwei S3-Clients
  gegen dieselbe MinIO-Instanz mit unterschiedlichen Hosts:
  `S3_ENDPOINT_URL` (Docker-Netzwerk-Hostname `minio`, für
  server-zu-server PUT/HEAD) und `S3_PUBLIC_URL_BASE` (was der Browser
  tatsächlich erreichen kann, für presigned URLs). Ohne diese Trennung wären
  presigned URLs für den Browser nutzlos, weil `minio` als Hostname nur
  innerhalb des Docker-Netzwerks aufgelöst werden kann.
- **Foto-Upload**: `POST /api/vorgaenge/{id}/events/foto` (multipart),
  erzeugt serverseitig eine "reduzierte Auflösung" (max. 800px, JPEG,
  Abschnitt 6) zusätzlich zum Original – beide landen in MinIO, referenziert
  über ihre Objekt-Keys im Event-`payload`. `foto_url`/`foto_thumbnail_url`
  werden bei jedem Lesen frisch signiert (presigned URLs laufen ab, dürfen
  also nicht mitgespeichert werden).
- **QR-Scan**: `GET /api/anlagen/by-qr/{qr_code}` – RLS-gescopt trotz
  global eindeutigem QR-Code (ein fremder Code liefert 404, kein Leak).
- **Zeiterfassung**: neue Tabelle nach Abschnitt 4.7. Ein laufender Timer
  pro Techniker wird über einen **partiellen Unique-Index**
  (`WHERE ende_at IS NULL`) erzwungen, nicht nur per Anwendungslogik.
  `POST /start`, `POST /{id}/stop`, `GET /laufend`. Start/Stop erzeugen
  automatisch `zeit_start`/`zeit_stop`-Events im Chat und pushen ein
  `timer`-SSE-Event. `timer_laeuft` im Feed ist jetzt echt (Phase 3 hatte es
  als festen `false`-Stub).
- **Health-Endpoint** prüft jetzt auch die Objektspeicher-Verbindung
  (Abschnitt 15.7), Scheduler-Zeitstempel folgt mit Phase 5.

### Frontend

- **PWA**: `vite-plugin-pwa` (Workbox `generateSW`), installierbar
  (Manifest + Icons), Service Worker precacht den App-Shell (JS/CSS/HTML) –
  verifiziert per Playwright gegen den echten Produktions-Build: App lädt
  vollständig offline.
- **Offline-Outbox** (IndexedDB via `idb`, `src/offline/`): Write-Through-
  Cache für Feed/Events/Kunden/Anlagen; beim Fehlschlagen eines Kommentars
  oder Foto-Uploads (Netzwerkfehler, nicht Server-Ablehnung) wird der
  Eintrag in eine Outbox-Queue geschrieben statt verworfen – sofort lokal
  sichtbar mit 🕘-Markierung "Nicht synchronisiert". Auto-Sync bei
  `online`-Event, alle 10s im Hintergrund und sofort nach jeder
  Outbox-Änderung; verworfene Verbindungen blockieren die Warteschlange
  nicht (Abbruch bei erstem Fehler, Reihenfolge bleibt erhalten).
- **Foto-Upload, QR-Scan, Zeiterfassung** im Vorgangs-Chat/"Neu"-Tab: Kamera
  (`capture="environment"`) fürs Foto, `jsQR` + `getUserMedia` für den
  QR-Scan mit Text-Eingabe-Fallback (Kamera nicht immer verfügbar –
  wichtig auch für Testbarkeit ohne echte Hardware), Start/Stop-Timer mit
  pulsierendem Live-Indikator.

## Ein reales Problem, das beim Testen aufgefallen ist

Beim End-to-End-Test mit echtem Netzwerkabbruch (`context.set_offline`)
blieb ein Kommentar-POST **unbegrenzt hängen** statt sofort fehlzuschlagen –
`fetch()` selbst bietet keine Zeitgrenze. Das hätte im Feld bei einer
Verbindung, die nicht klar "ab", sondern nur extrem langsam/instabil ist
(schwaches Kellersignal), die komplette Chat-Eingabe blockiert, ohne dass
die Outbox je zum Zug kommt. Behoben durch einen `AbortController`-Timeout
(10s) in `apiFetch`/`apiFetchForm` – jede Anfrage bekommt jetzt eine feste
Obergrenze, danach greift der normale Fehlerpfad in die Outbox. Das ist
unabhängig vom genauen Auslöser des ursprünglichen Hängers die richtige
Absicherung für echte Feldbedingungen.

## Entscheidungen, die ich dokumentiere statt nachzufragen

- **Offline-Caching-Umfang**: Die Spec beschreibt "Vorgänge der nächsten 7
  Tage" – das ist an Termine gebunden, die erst in Phase 5 existieren. Bis
  dahin cached die Outbox pragmatisch, was der Techniker tatsächlich
  geöffnet hat (Feed-Erstseite, besuchte Vorgänge/Kunden/Anlagen). Sobald
  Termine existieren, kann ein Hintergrund-Prefetch dieselben Stores anhand
  anstehender Termine vorab befüllen.
- **Zeiterfassung-Berechtigungen**: Jede der drei Mandanten-Rollen darf
  ihre eigene Zeit erfassen (nicht nur `techniker`), aber niemand die Zeit
  eines Kollegen starten/stoppen – passend zu Abschnitt 4.7 ("ein Techniker
  darf ... nur einen laufenden Timer").
- **Foto-Validierung**: nur `image/*`-Content-Types, max. 15 MB Upload.

## Wie es getestet wird

```bash
cd backend && source .venv/bin/activate && python -m pytest   # 100 Tests
```

Foto-Upload-Tests laufen gegen `moto`s **Server-Modus**
(`ThreadedMotoServer`), nicht gegen den üblichen `mock_aws`-Decorator: der
Decorator fängt nur Requests an echte AWS-Hostnamen ab, unsere Clients
reden aber absichtlich mit einem konfigurierbaren `S3_ENDPOINT_URL` (wie
MinIO). Der Server-Modus ist ein echter lokaler HTTP-Server und funktioniert
deshalb unabhängig vom Zielhost.

End-to-End manuell verifiziert gegen den echten Produktions-Build
(`npm run build && npm run preview`) mit echtem MinIO-Ersatz (`moto.server`)
und echtem Backend: Login → Vorgang öffnen → Zeit starten/stoppen → Foto
hochladen (sichtbar mit funktionierender presigned URL) → echter
Netzwerkabbruch (Kommentar wird gequeued, "Nicht synchronisiert"-Badge,
Outbox-Zähler im Header) → Wiederverbindung (automatischer Sync, Badge
verschwindet) → App-Shell lädt vollständig offline neu (Service-Worker-
Precache).

## Was offen bleibt

- Prüfmittel, Termine, Prüfzyklen-Scheduler: Phase 5.
- Kein automatisches Vorab-Cachen "der nächsten 7 Tage" (siehe oben) –
  hängt an Terminen aus Phase 5.
- Offline-Erstellung eines komplett neuen Vorgangs (nicht nur Kommentare/
  Fotos zu bestehenden) ist noch nicht Teil der Outbox – in der Praxis
  legt ein Techniker im Feld meist Kommentare/Fotos zu bereits bekannten
  Vorgängen an; ein eigener Vorgang würde eine clientseitig vorab
  vergebene `vorgangsnummer` brauchen, um Offline-Idempotenz zu garantieren.
