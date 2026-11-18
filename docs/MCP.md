# KI-Zugriff (MCP-Server für Claude)

Mitarbeiter eines Betriebs können FieldVibe aus Claude (claude.ai, Claude Desktop,
Claude Code) heraus abfragen und auswerten, mit genau den Rechten, die sie in der App
haben. Konzept und Etappenplan: `analyse/konzept-mcp.md`. Etappe 1 ist nur lesend,
Etappe 2 ergänzt Auswertungen, Protokoll-Tools und additive Schreib-Tools (siehe unten).

## Einrichtung

1. **Modul einschalten (Super-Admin).** Das Modul `ki_zugriff` ist wie `karten`
   opt-in und für jeden Mandanten zunächst aus. Der Super-Admin schaltet es in der
   Mandantenverwaltung ein, sobald der Betrieb zugestimmt hat (AV-Vertrag mit dem
   KI-Anbieter, Hinweis in der eigenen Datenschutzerklärung). Die Änderung steht im
   Audit-Log.
2. **Recht vergeben (Mandant-Admin).** Neuer Rechte-Bereich „KI-Assistent (Claude)“
   (`ki_zugriff`): `sehen` = Lesen, `bearbeiten` = Schreiben (ab Etappe 2). Mandant-Admins
   haben es automatisch, alle anderen bekommen es im Organigramm gezielt freigegeben.
3. **Connector einrichten (Nutzer).** URL: `https://<DOMAIN_API>/mcp`
   - claude.ai / Claude Desktop: Einstellungen, Connectors, „Benutzerdefinierten
     Connector hinzufügen“, URL eintragen.
   - Claude Code: `claude mcp add --transport http fieldvibe https://<DOMAIN_API>/mcp`,
     danach in Claude Code `/mcp` und FieldVibe anmelden.
   Beim ersten Aufruf öffnet sich die FieldVibe-Anmeldung (inkl. MFA) mit der
   Einwilligungsseite („Claude möchte auf FieldVibe zugreifen“, Lesen bzw. Lesen und
   Schreiben). Dynamic Client Registration ist aktiv, es muss nichts vorab registriert
   werden.
4. **Verbindungen verwalten.** Jeder Nutzer sieht und trennt seine Verbindungen im
   Profil, der Mandant-Admin alle des Mandanten (`GET/DELETE /api/ki/verbindungen`).
   Trennen wirkt sofort.

Konfiguration: `FIELDVIBE_API_PUBLIC_URL` (siehe `docs/DEPLOYMENT.md`) muss die Adresse
sein, unter der Claude die API erreicht, denn Issuer, Resource-URL und die
Host-Prüfung (DNS-Rebinding-Schutz) leiten sich daraus ab. Der OAuth-Issuer muss HTTPS
sein (Ausnahme `localhost`); im IP-Betrieb ohne TLS ist der MCP-Server deshalb aus.
Die OAuth-Endpunkte (`/authorize`, `/token`, `/register`, `/revoke`) und die
`/.well-known`-Metadaten liegen an der Wurzel der API-Domain, so suchen MCP-Clients sie.
Das Frontend braucht die Seite `/ki-verbinden` (Einwilligung).

## Tools (Lesen, Scope `fieldvibe.lesen`)

| Tool | Zweck |
| --- | --- |
| `suchen` | Einstieg: Kunden, Vorgänge, Anlagen, Rechnungen, Tags finden |
| `vorgaenge_auflisten`, `vorgang_lesen` | Vorgänge (Ticket/Einsatz) mit Verlauf, Mängeln, Formularen |
| `auftraege_auflisten`, `auftrag_lesen` | Entität Auftrag |
| `projekte_auflisten`, `projekt_lesen` | Projekte mit Spalten, Aufgaben, Aufträgen |
| `kunde_lesen`, `anlage_lesen` | Kunde mit Standorten/Anlagen; Anlage mit Historie und Prüfzyklen |
| `termine_auflisten` | Dispo-Termine |
| `pruefungen_faellig` | fällige Prüfzyklen und Prüfmittel (Parameter `tage`, Standard 30) |
| `formular_vorlagen`, `formular_lesen` | Protokoll-Vorlagen eines Vorgangs, ausgefüllte Protokolle |
| `kennzahlen_vorgaenge`, `insights`, `offene_posten` | Auswertungen (Recht Statistik bzw. Abrechnung) |
| `auswertung` | Kennzahl nach Gruppierung über `GET /api/statistik/aggregat` (feste Whitelist, Kombinationen in der Tool-Beschreibung) |
| `arbeitszeit_saldo` | Soll/Ist/Saldo eines Mitarbeiters (`/api/arbeitszeit/saldo`) |
| `protokoll_vorlagen_auflisten`, `protokoll_vorlage_lesen` | Protokoll-Vorlagen (Recht Formulare › sehen), Abschnitte/Felder kompakt |
| `protokoll_pdf`, `maengelprotokoll_pdf` | PDF als eingebettete Ressource (Blob, bis 5 MB, sonst Hinweis auf die App) |

Ressource `fieldvibe://begriffe`: Glossar (Kopie von `docs/BEGRIFFE.md` in
`backend/app/mcp/begriffe.md`, weil das Backend-Image `docs/` nicht enthält; ein Test hält
beide gleich).

Listen sind auf 100 Einträge je Aufruf begrenzt (Parameter `seite`). Die
Vorgänge-Schnittstelle liefert höchstens 200 Einträge je Filter; darüber hinaus nur mit
engeren Filtern (die Antwort sagt das im Feld `hinweis`).

## Schreib-Tools (Etappe 2, Scope `fieldvibe.schreiben`)

Nur sichtbar, wenn die Verbindung den Schreib-Scope hat; zusätzlich prüft jeder Aufruf das
Recht `ki_zugriff.bearbeiten` neu (`load_access_token` streicht den Scope bei entzogenem Recht,
`tools/_basis.zugriff` lehnt dann ab). Alle Tools sind `readOnlyHint=false`,
`destructiveHint=false`, `idempotentHint=false` und tragen „(nur mit Schreibzugriff)“.

| Tool | Wirkung |
| --- | --- |
| `kommentar_anlegen` | interner Kommentar im Vorgangsverlauf, nicht kundensichtbar |
| `mangel_erfassen` | Mangel im Status „offen“ |
| `vorgang_anlegen` | Vorgang im Status „neu“, ohne Zuweisung/Termin; `leistungstyp` Pflicht, `abrechnungsart` Standard `aufwand` |
| `protokoll_entwurf_anlegen` | Protokoll (Status „offen“) aus einer **veröffentlichten** Vorlage; `werte` per Feld-Key oder Beschriftung, Gruppen als Objekt bzw. Liste |
| `protokoll_entwurf_ergaenzen` | nur offene Protokolle; Befülltes bleibt (außer `vorhandene_ueberschreiben`), Listeneinträge werden angehängt |
| `protokoll_vorlage_entwerfen` | neue Vorlage im Status `draft` (Abschnitte, Felder, Optionen); Ergebnis mit ID, Zusammenfassung und Link `…/form-schemas/<id>` |
| `protokoll_vorlage_ueberarbeiten` | nur `draft`: Abschnitte/Felder hinzufügen, Beschriftung/Pflicht/Hilfetext/Optionen ändern |

Foto, Unterschrift, Datei, GPS, QR-Scan und Fotoplan kann Claude nicht füllen (Fehlermeldung).
Datenformat der Werte wie in der Feld-App: Zahl/Betrag als String, Ja/Nein als bool, nicht
wiederholbare Abschnitte als Liste mit einer Zeile. Schlüssel (Keys) werden aus Labels erzeugt
(ASCII, Umlaute transliteriert, je Vorlage eindeutig); der Link zeigt auf `frontend_base_url`
(die Seite liegt in Feld-App und Office unter derselben Route). Scheitert ein Teilschritt, nennt die
Fehlermeldung ID und Link des Entwurfs, damit ihn der Nutzer im Baukasten vollenden oder löschen kann.

**Ansichten:** Das Backend legt keine Ansichten automatisch an; im Baukasten tut das der Nutzer (Tab
Visualisierung, Typ + Name). Ohne Druckansicht scheitert das Protokoll-PDF. Deshalb legt
`protokoll_vorlage_entwerfen` eine Erfassungsansicht („Erfassung“) und eine Druckansicht („Druck“) an
(`POST …/views`, in der Allowlist nur POST, kein PATCH/DELETE/PUT). `protokoll_vorlage_ueberarbeiten`
ergänzt sie nur, wenn der Entwurf noch gar keine Ansicht hat. Layout-Einträge gibt es nicht: der Baukasten
übernimmt nur Felder ohne Abschnitt, KI-Entwürfe haben ausschließlich Abschnittsfelder, und neue Felder
erscheinen in Feld-App und PDF direkt aus dem Schema (Abschnitte werden im PDF aus den Werten ausgegeben).

**Rechte beim Ausfüllen:** `protokoll_entwurf_anlegen`/`_ergaenzen` laden die Felder über
`GET /api/form-schemas/{id}` und brauchen deshalb Formulare › sehen. Das ist dieselbe Route wie in der
Feld-App (`FormSubmissionAusfuellenPage`: Schema, Ansichten, Regeln); eine Route, die Felddefinitionen ohne dieses
Recht liefert, gibt es nicht. Ein Techniker-Account-Typ ohne Formulare › sehen kann also auch in der Feld-App
kein Formular ausfüllen. Das Recht ist dafür zu vergeben (Rechte-Matrix), im MCP nicht zu umgehen.

**Nie per KI:** Löschen, Status ändern/abschließen, Protokoll abschließen/unterschreiben, Vorlage
veröffentlichen/archivieren oder Leistungstypen zuordnen, Angebote/Rechnungen, E-Mails, Exporte,
Rechte/Nutzer. Durchgesetzt wird das fail-closed in `app/mcp/rest_client.py`
(`SCHREIB_ALLOWLIST` aus Methode und Pfadmuster; alles andere ist ein `PermissionError`, ein Test
deckt Löschen, Abschließen und das Veröffentlichen per `PATCH /api/form-schemas/{id}` ab).

**Kennzeichnung:** Events, die per MCP entstehen (Kommentar, Mangel, „Vorgang angelegt“), tragen im
`payload` `via: "claude"` und `ki_verbindung_id` (nur aus dem signierten Token gesetzt, vom Client
gesendete Werte werden entfernt). Der Vorgangsverlauf zeigt „via Claude“. Zusätzlich schreiben
die genutzten Routen bei MCP-Aufrufen Audit-Einträge `ki_*` mit `quelle = "ki"`.
Vorlagen-Entwürfe: nur der Audit-Eintrag, `beschreibung` bleibt unverändert; das Tool-Ergebnis
sagt „KI-Entwurf“.

### Prompts

`protokoll_vorlage_entwerfen` (thema, vorgaben), `wartungsprotokoll_zu_vorgang_ausfuellen`
(vorgang_id), `monatsbericht` (monat, team). Sie geben nur Anweisungen vor.

## Sicherheitsmodell

- **Nur Mitarbeiter-Konten** (Mandant-Admin und frei definierte Account-Typen). Nicht
  möglich: Super-Admin, Impersonation, Papierkorb-Rollen, Kundenportal- und
  Partner-Konten. Dieselbe Prüfung läuft bei der Einwilligung, bei jedem Token-Refresh und
  bei jedem MCP-Aufruf (Modul, Recht `ki_zugriff.sehen`, Konto aktiv).
- **Rechte wie in der App.** Jedes Tool ruft die bestehende REST-Route in-process mit einem
  2 Minuten gültigen Token des Nutzers auf. Fachrechte, Scopes (eigene/team/…),
  Kundenbeschränkung, Modul-Schalter und die Mandanten-RLS gelten dadurch unverändert und
  sind nicht dupliziert.
- **Tokens.** OAuth 2.1 mit PKCE (nur S256). Eigene JWT-Typen `mcp` (30 Minuten),
  `mcp_refresh` (14 Tage, rotiert bei jeder Nutzung, ein bereits benutzter Refresh-Token
  beendet die Verbindung), `mcp_code` (5 Minuten, einmal einlösbar) und `mcp_anfrage`
  (10 Minuten). Sie tragen `mandant_id` und `tv` signiert; die normalen API-Routen lehnen sie
  ab. „Überall abmelden“, Passwortwechsel oder Sperren (`tv`) machen sie sofort ungültig, ebenso
  Widerruf der Verbindung, Modul aus oder entzogenes Recht.
- **Kein `system_session`.** `app/mcp/` und `api/routes/ki.py` arbeiten ausschließlich in
  der `tenant_session` des Mandanten aus dem Token (ein Test stellt das sicher).
  `ki_clients` (registrierte OAuth-Clients) ist bewusst mandantenlos und ohne RLS, weil die
  Registrierung vor jedem Login passiert; sie enthält nur Client-Metadaten.
- **Scopes.** `fieldvibe.lesen` (immer dabei) und `fieldvibe.schreiben` (nur mit Recht
  `ki_zugriff.bearbeiten`). Jeder Tool-Aufruf prüft den Scope.
- **Datensparsamkeit.** Antworten enthalten keine Felder mit Namen wie IBAN/BIC, Passwort,
  MFA, Token, Secret, Hash und keine signierten Datei-Links. Listen max. 100 Einträge je Aufruf.
- **Nachvollziehbarkeit.** Einwilligung und Widerruf stehen im Audit-Log
  (`ki_verbindung_erteilt`, `ki_verbindung_widerrufen`). Jeder Audit-Eintrag, der während
  eines KI-Aufrufs entsteht, trägt `quelle = "ki"` und `ki_verbindung_id` im Payload.
- **Rate-Limit:** 120 Tool-Aufrufe pro Minute und Verbindung, die offene Client-Registrierung
  (`/register`) 30 pro Stunde und IP (In-Memory je Prozess).
- **DNS-Rebinding-Schutz:** `/mcp` akzeptiert nur den Host aus `FIELDVIBE_API_PUBLIC_URL`
  (in Dev/Test zusätzlich localhost).

## Betrieb

- Der MCP-Server läuft stateless im Backend-Prozess (kein eigener Container, keine
  Sitzungsbindung) und antwortet mit einfachem JSON statt Streaming. Caddy braucht deshalb
  keine besondere Konfiguration (`flush_interval` ist nicht nötig).
- Der Session-Manager des SDK startet im FastAPI-Lifespan (`app/main.py`).
- Der bestehende Bugreport-MCP (`tools/bugreport-mcp/`) bleibt davon getrennt.
