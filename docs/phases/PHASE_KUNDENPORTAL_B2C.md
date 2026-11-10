# Kundenportal B2C-rechtssicher (Roadmap 1.8) – technische Umsetzung

Technische Grundlage für den Verbrauchervertrieb über das Kundenportal:
Annahmenachweis, Button-Lösung, Widerrufsbutton, Barrierefreiheit. **Alle
Rechtstexte im System sind Platzhalter** und müssen von einer Rechtsberatung
geprüft werden (siehe „Was offen bleibt“). Migration `0111`.

## Annahmenachweis (immer, auch B2B)

- Tabelle **`angebot_annahmen`**: wer (Portal-Zugang + E-Mail/Name als
  Momentaufnahme), wann, IP, User-Agent (auf 300 Zeichen gekürzt), SHA-256 der
  angenommenen Fassung, `b2c_flag`, bei Verbrauchern Belehrungsversion **und
  -wortlaut**. Aktion `annahme | ablehnung | widerruf`.
- **Append-only**: Mandanten-RLS wie üblich (Policy + `FORCE`), dazu ein
  `BEFORE UPDATE OR DELETE`-Trigger, der auch Tabellenbesitzer und
  `super_admin` aussperrt. `TRUNCATE` bleibt möglich (Test-Cleanup). Die FK auf
  `angebote`/`kundenportal_zugaenge` verhindert nebenbei das endgültige Löschen
  eines Angebots mit Nachweis (Papierkorb meldet 409).
- **IP**: dieselbe Funktion wie beim Login-Limiter (`rate_limit.client_ip`),
  also nur über Uvicorns `ProxyHeadersMiddleware`/`FORWARDED_ALLOW_IPS`; ein
  gefälschter `X-Forwarded-For` von einem nicht vertrauenswürdigen Peer wird
  ignoriert (getestet).
- **Fassungs-Hash** (`angebot_service.berechne_fassung_sha256`): kanonisches
  JSON (sortierte Schlüssel, feste 2 Nachkommastellen, NFC) aus
  Angebotsnummer, Mandant/Kunde, MwSt-Satz, Gültigkeit, Positionen
  (Nummer, Beschreibung, Menge, Einheit, Einzelpreis, Gesamt) und Summen.
  **Nicht das PDF**: fpdf2 schreibt Erstellzeit/Dokument-ID, derselbe Inhalt
  ergibt bei jedem Abruf andere Bytes (Test belegt das). Der Client schickt
  den Hash der gesehenen Fassung mit; weicht er ab (z. B. Betrieb verlängert
  die Gültigkeit), antwortet das Backend 409 und ändert nichts.
- Office: `AngebotRead.letzter_nachweis`, `fassung_sha256`, `widerrufen_am`
  (alles additiv); Angebotsdetail zeigt den Nachweis und warnt, wenn das
  Angebot nach der Entscheidung verändert wurde.

## B2B/B2C-Schalter

- `firmendaten.portal_verbraucherschutz` ∈ `"aus" | "nur_privatkunden"`.
  **Neue Mandanten** (`POST /api/admin/mandanten`) starten mit
  `nur_privatkunden`. **Bestandsmandanten** haben den Schlüssel nicht und
  gelten per Code-Fallback als `aus` (keine Daten-Migration, damit sich für
  sie nichts unangekündigt ändert).
- Verbraucher = `Kunde.typ == "privat"`. `NULL`, `gewerbe`, `oeffentlich`,
  `hausverwaltung` sind es nicht.
- B2C-Annahme verlangt `bestaetigung: true` und die aktuelle
  `belehrung_version`, sonst 422. Ablehnen bleibt formlos (wird protokolliert).
- Weitere Firmendaten-Schlüssel: `widerrufsbelehrung_text`,
  `widerrufsbelehrung_version`, `barrierefreiheit_kontakt_email`,
  `barrierefreiheit_stand`, `barrierefreiheit_url`. Ohne Belehrungstext liefert
  das Backend einen als **PLATZHALTER** markierten Mustertext (Version
  `platzhalter-v1`); die Office-Einstellungen warnen. Die ausgelieferte Version
  enthält einen Fingerabdruck des Textes (`<Version>#<sha8>`), damit eine
  Textänderung ohne Versionssprung nicht unbemerkt alte Bestätigungen umdeutet.

## Widerruf (§ 356a BGB)

- `POST /api/kundenportal/angebote/{id}/widerruf` mit `{"bestaetigung": true}`;
  der Portal-Button führt auf eine Bestätigungsseite („Widerruf bestätigen“).
- Neuer Angebotsstatus **`widerrufen`** (+ `widerrufen_am`). Er steht in keiner
  Übergangstabelle, ist also per Staff-PATCH nicht setzbar; Rechnungen aus dem
  Angebot sind damit automatisch gesperrt (`rechnungsart_service` verlangt
  `angenommen`).
- Frist `WIDERRUFSFRIST_TAGE = 14` ab Annahmezeitpunkt, Ende mit Ablauf des
  14. Tages in Betriebszeit. Widerruf nur, wenn die Annahme im B2C-Ablauf
  erfolgte (Nachweis `b2c_flag`) und **keine versendete Rechnung** am Angebot
  oder am daraus entstandenen Auftrag hängt (sonst 409 „Betrieb kontaktieren“).
  Entwurfsrechnungen blockieren nicht.
- Bereits angelegte Aufträge werden **nicht** automatisch storniert; sie
  bekommen ein Ereignis, der Betrieb eine Benachrichtigung + Mail.
- Mails (über `email_service.send_email_and_log`, im E-Mail-Verlauf des
  Angebots sichtbar): Bestätigung der Beauftragung mit Angebots-PDF,
  Widerrufsbelehrung und Muster-Widerrufsformular; Eingangsbestätigung des
  Widerrufs. Versandfehler machen die Aktion nicht rückgängig, werden aber
  geloggt.

## Barrierefreiheit (BFSG / WCAG 2.1 AA)

- `frontend/e2e/portal-a11y.spec.ts`: axe-core über alle Portal-Seiten (hell
  und dunkel, 390 px), API per `page.route` gemockt, plus Tastatur-/Alert-
  Tests. Lokal: `npm run build`, `npx vite preview --host localhost --port
  4173`, `E2E_BASE_URL=http://localhost:4173 npx playwright test portal-a11y`.
  CI-Job `frontend-a11y` (`.github/workflows/ci.yml`).
- Behoben u. a.: Kontraste (Marke, aktive Navigation, Primär-/Sekundär-Buttons,
  `--st-arbeit-text` im Hellmodus global abgedunkelt), Landmarken/`<h1>` auf
  Login- und Angebotsseiten, `role="alert"` für Fehler, Skip-Link,
  Fokus auf die Überschrift nach dem Widerruf.
- `/barrierefreiheit`: Platzhalter-Erklärung aus den Firmendaten
  („teilweise konform“), verlinkt über `RechtlicheLinks` (`barrierefreiheit`-
  Prop, nur im Portal); `GET /api/public/rechtliches` liefert additiv
  `barrierefreiheit_url`, `barrierefreiheit_kontakt_email`,
  `barrierefreiheit_stand`.

## Was offen bleibt

- Alle Rechtstexte (Belehrung, Widerrufsformular, Barrierefreiheitserklärung,
  Konformitätsstatus) sind Platzhalter.
- Fristbeginn/-berechnung, Erlöschen des Widerrufsrechts bei vollständiger
  Leistung (§ 356 Abs. 4/5), Wertersatz (§ 357a) und Verzicht-Erklärung sind
  nicht abgebildet.
- Aufbewahrung/Löschkonzept für IP und User-Agent im Nachweis (DSGVO).
- Kunden ohne gepflegten Typ (`NULL`) gelten als Nicht-Verbraucher.
- Die Staff-Seite „Angenommen“/„Abgelehnt“ im Angebotsdetail (Office/Feld)
  hat weiterhin weiß-auf-grün/rot-Buttons mit zu geringem Kontrast (außerhalb
  des Portals, nicht Teil dieses Auftrags).
