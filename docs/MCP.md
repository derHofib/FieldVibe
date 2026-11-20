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

Seit dem Ausbau Etappe A (Konzept `analyse/konzept-mcp-ausbau.md`) gibt es wenige generische Lese-Tools statt je
Objekt eines. Inhalte und Rechte entsprechen den früheren Einzel-Tools 1:1 (dieselben REST-Routen, dieselben
Teilabfragen).

| Tool | Zweck |
| --- | --- |
| `suchen` | Einstieg: Kunden, Vorgänge, Anlagen, Rechnungen, Kontakte vor Ort, Tags finden |
| `lesen(typ, id, umfang="voll", kunde_id)` | ein Datensatz: `vorgang`, `auftrag`, `projekt`, `aufgabe`, `kunde`, `anlage`, `kontakt_vor_ort` (braucht `kunde_id`, es gibt keine Einzel-Route), `termin`, `telefonat`, `formular`, `vorlage`, `angebot`, `rechnung`, `mangel`, `ich`, `ki_aktion`. `umfang`: `kurz` (Kopf), `voll` (Kopf und Teilabfragen), `verlauf` (zusätzlich Telefonate/Termine bzw. Aufgaben, wo vorhanden). `ich` liefert Name, Rolle, wirksame Fachrechte, Zugriffsbereiche der Verbindung und die Stufen-Info |
| `auflisten(typ, filter, seite)` | `vorgang`, `auftrag`, `projekt`, `aufgabe`, `termin`, `telefonat`, `vorlage` (mit `filter.vorgang_id`: verfügbare Vorlagen für den Vorgang), `angebot`, `rechnung`, `mitarbeiter` (`/api/users/auswahl`), `ki_aktion`. Der `filter` ist je Typ eine Pydantic-Klasse (`extra=forbid`); unbekannte Filter ergeben einen Fehler mit der Liste der erlaubten |
| `dokument_abrufen(typ, id, format)` | PDF als eingebettete Ressource (Blob, bis 5 MB, sonst Hinweis auf die App): `protokoll`, `maengelprotokoll` (id = Vorgang), `angebot`, `rechnung` (zusätzlich `format=xml`) |
| `pruefungen_faellig` | fällige Prüfzyklen und Prüfmittel (Parameter `tage`, Standard 30) |
| `kennzahlen_vorgaenge`, `insights`, `offene_posten` | Auswertungen (Recht Statistik bzw. Abrechnung) |
| `auswertung` | Kennzahl nach Gruppierung über `GET /api/statistik/aggregat` (feste Whitelist, Kombinationen in der Tool-Beschreibung) |
| `arbeitszeit_saldo` | Soll/Ist/Saldo eines Mitarbeiters (`/api/arbeitszeit/saldo`) |
| `protokoll_anzeigen` | Protokoll als Zusammenfassung (Abschnitte, Ja/Nein, Grenzwerte, fehlende Pflichtfelder, Fotos nur als Anzahl) mit Link „In FieldVibe öffnen“; Ansicht im Chat per MCP Apps, sonst Text |

Alt → neu:

| bisher | jetzt |
| --- | --- |
| `vorgang_lesen`, `auftrag_lesen`, `projekt_lesen`, `kunde_lesen`, `anlage_lesen`, `formular_lesen`, `protokoll_vorlage_lesen` | `lesen(typ=…)` |
| `vorgaenge_auflisten`, `auftraege_auflisten`, `projekte_auflisten`, `termine_auflisten`, `telefonate_auflisten`, `protokoll_vorlagen_auflisten`, `formular_vorlagen` | `auflisten(typ=…, filter={…})` |
| `protokoll_pdf`, `maengelprotokoll_pdf` | `dokument_abrufen(typ="protokoll" / "maengelprotokoll")` |
| `vorgang_anlegen` | `vorgang_speichern` (ohne `id`) |
| `protokoll_entwurf_anlegen`, `protokoll_entwurf_ergaenzen` | `protokoll_entwurf` (ohne / mit `id`) |
| `protokoll_vorlage_entwerfen`, `protokoll_vorlage_ueberarbeiten` | `vorlage_entwurf` (ohne / mit `id`) |
| `kommentar_anlegen(vorgang_id)` | `kommentar_anlegen(ziel_id, ziel_typ="vorgang")` |

Ressource `fieldvibe://begriffe`: Glossar (Kopie von `docs/BEGRIFFE.md` in
`backend/app/mcp/begriffe.md`, weil das Backend-Image `docs/` nicht enthält; ein Test hält
beide gleich).

Listen sind auf 100 Einträge je Aufruf begrenzt (Parameter `seite`). Die
Vorgänge-Schnittstelle liefert höchstens 200 Einträge je Filter; darüber hinaus nur mit
engeren Filtern (die Antwort sagt das im Feld `hinweis`).

## Schreib-Tools (Scope `fieldvibe.schreiben`)

Nur sichtbar, wenn die Verbindung den Schreib-Scope hat; zusätzlich prüft jeder Aufruf das
Recht `ki_zugriff.bearbeiten` neu (`load_access_token` streicht den Scope bei entzogenem Recht,
`tools/_basis.zugriff` lehnt dann ab). Anlegen-Tools sind `NUR_ADDITIV` (`idempotentHint=false`), alle
übrigen (`*_speichern`, `verknuepfen`, `rueckgaengig`, Entwürfe) `AENDERND` (`destructiveHint=false`,
`idempotentHint=true`); alle tragen „(nur mit Schreibzugriff)“. Jede Antwort enthält `aktion_id`,
`zusammenfassung`, `aenderungen` (Vorher/Nachher als Anzeigewerte) bzw. `erzeugt`, `link` (Detailseite in der App),
`rueckgaengig_bis` und den Hinweis auf `rueckgaengig`.

| Tool | Wirkung |
| --- | --- |
| `vorgang_speichern` | ohne `id` anlegen (Pflicht: `kunde_id`, `titel`, `leistungstyp`; Status „neu“), mit `id` nur die übergebenen Felder ändern (Zuständiger, Fälligkeit, Status `neu`/`geplant`/`in_arbeit`/`wartet_kunde`, …). Leeren über `felder_leeren`. Abschließen/Stornieren/Abgerechnet sind gesperrt |
| `auftrag_speichern`, `projekt_speichern`, `aufgabe_speichern`, `termin_speichern` | Anlegen/Ändern (Aufgabe inkl. `erledigt`, Termin verschieben/umbesetzen, Status nur `geplant`/`bestaetigt`; Auftrag-Status nur `offen`/`in_arbeit`) |
| `kunde_speichern(art=kunde\|standort\|kontakt_vor_ort)` | Stammdaten; keine Bank-, Portal- oder Rechtedaten. Ändern eines Kontakts vor Ort braucht `kunde_id` |
| `verknuepfen(objekt_typ, objekt_ids, mit_typ, mit_id, loesen)` | bis 50 Datensätze zuordnen oder lösen: Vorgang → Auftrag/Projekt, Auftrag → Projekt, Vorgang → Anlage, Vorgang → Vorgang (blockiert von), Kontakt vor Ort → Vorgang/Auftrag/Projekt. Sequenziell; bei einem Fehler stoppt der Lauf, Erledigtes bleibt im Journal |
| `kommentar_anlegen` | interner Kommentar im Vorgangsverlauf, nicht kundensichtbar (nicht rückgängig zu machen) |
| `mangel_erfassen` | Mangel im Status „offen“ |
| `telefonat_erfassen` | Telefonat an Vorgang oder Kunde („via Claude“), optional Rückruf; ohne Arbeitszeit-Buchung, nicht kundensichtbar |
| `protokoll_entwurf` | ohne `id`: Protokoll (Status „offen“) aus einer **veröffentlichten** Vorlage (`vorgang_id`, `vorlage_id`); mit `id`: nur offene Protokolle ergänzen (Befülltes bleibt außer `vorhandene_ueberschreiben`, Listeneinträge werden angehängt). `werte` per Feld-Key oder Beschriftung |
| `vorlage_entwurf` | ohne `id`: neue Vorlage im Status `draft` (`name`, `abschnitte`); mit `id`: nur `draft` über `aenderungen` {`abschnitte_hinzufuegen`, `felder_hinzufuegen`, `felder_aendern`}; Ergebnis mit ID, Aufbau und Link `…/form-schemas/<id>` |
| `rueckgaengig(aktion_id)` | nimmt eine Aktion aus dem Journal zurück (siehe unten) |

Foto, Unterschrift, Datei, GPS, QR-Scan und Fotoplan kann Claude nicht füllen (Fehlermeldung).
Datenformat der Werte wie in der Feld-App: Zahl/Betrag als String, Ja/Nein als bool, nicht
wiederholbare Abschnitte als Liste mit einer Zeile. Schlüssel (Keys) werden aus Labels erzeugt
(ASCII, Umlaute transliteriert, je Vorlage eindeutig); der Link zeigt auf `frontend_base_url`
(die Seite liegt in Feld-App und Office unter derselben Route). Scheitert ein Teilschritt, nennt die
Fehlermeldung ID und Link des Entwurfs, damit ihn der Nutzer im Baukasten vollenden oder löschen kann.

**Ansichten:** Das Backend legt keine Ansichten automatisch an; im Baukasten tut das der Nutzer (Tab
Visualisierung, Typ + Name). Ohne Druckansicht scheitert das Protokoll-PDF. Deshalb legt
`vorlage_entwurf` eine Erfassungsansicht („Erfassung“) und eine Druckansicht („Druck“) an
(`POST …/views`, in der Allowlist nur POST, kein PATCH/DELETE/PUT). `vorlage_entwurf` mit `id`
ergänzt sie nur, wenn der Entwurf noch gar keine Ansicht hat. Layout-Einträge gibt es nicht: der Baukasten
übernimmt nur Felder ohne Abschnitt, KI-Entwürfe haben ausschließlich Abschnittsfelder, und neue Felder
erscheinen in Feld-App und PDF direkt aus dem Schema (Abschnitte werden im PDF aus den Werten ausgegeben).

**Rechte beim Ausfüllen:** `protokoll_entwurf` lädt die Felder über
`GET /api/form-schemas/{id}` und brauchen deshalb Formulare › sehen. Das ist dieselbe Route wie in der
Feld-App (`FormSubmissionAusfuellenPage`: Schema, Ansichten, Regeln); eine Route, die Felddefinitionen ohne dieses
Recht liefert, gibt es nicht. Ein Techniker-Account-Typ ohne Formulare › sehen kann also auch in der Feld-App
kein Formular ausfüllen. Das Recht ist dafür zu vergeben (Rechte-Matrix), im MCP nicht zu umgehen.

**Nie per KI (Stufe 3, kommt mit einer späteren Ausbaustufe):** Löschen, Abschließen/Stornieren (Vorgang-Status
`abgeschlossen`/`storniert`/`abgerechnet`, Auftrag-Status `abgeschlossen`/`storniert`), Protokoll
abschließen/unterschreiben, Vorlage veröffentlichen/archivieren oder Leistungstypen zuordnen, Angebote/Rechnungen,
E-Mails, Exporte, Rechte/Nutzer. Durchgesetzt wird das fail-closed (siehe Sicherheitsmodell, Aktions-Registry).

**Kennzeichnung:** Events, die per MCP entstehen (Kommentar, Mangel, „Vorgang angelegt“), tragen im
`payload` `via: "claude"` und `ki_verbindung_id` (nur aus dem signierten Token gesetzt, vom Client
gesendete Werte werden entfernt). Der Vorgangsverlauf zeigt „via Claude“. Zusätzlich schreiben
die genutzten Routen bei MCP-Aufrufen Audit-Einträge `ki_*` mit `quelle = "ki"`.
Vorlagen-Entwürfe: nur der Audit-Eintrag, `beschreibung` bleibt unverändert; das Tool-Ergebnis
sagt „KI-Entwurf“.

### Ansichten im Chat (MCP Apps)

Der Server meldet die Erweiterung `io.modelcontextprotocol/ui` (`mcp.server.apps`). Drei statische
HTML-Ressourcen liegen in `backend/app/mcp/ui/` (hell/dunkel per `prefers-color-scheme`, keine externen
Skripte, Daten nur aus dem Tool-Ergebnis, Texte nur per `textContent`):
`ui://fieldvibe/protokoll.html` (Tool `protokoll_anzeigen`), `ui://fieldvibe/vorlage.html`
(Ergebnis von `vorlage_entwurf`, Link „Im Baukasten prüfen“) und `ui://fieldvibe/aenderung.html` (die
Änderungs-Karte aller übrigen Schreib-Tools: Tabelle Objekt/Feld, Vorher durchgestrichen, Nachher, Frist, Knöpfe „In
FieldVibe öffnen“ und „Rückgängig“; Letzterer ruft über die Brücke (`tools/call`) das Tool `rueckgaengig` auf und
markiert die Karte danach als „Zurückgenommen“). Die Tools
tragen `_meta.ui.resourceUri`; die Daten stehen im `structuredContent`, dieselben Inhalte als Text im
`content`. Clients ohne MCP Apps ignorieren den Verweis. Fotos erscheinen nur als Anzahl, nie als
Storage-Key oder signierter Link. Links zeigen auf `frontend_base_url` (`/form-submissions/{id}`,
`/form-schemas/{id}`).

Hinweis zum Betrieb: Im zustandslosen Betrieb sieht der Server die Fähigkeiten eines Clients des
älteren Protokolls (`initialize`) nicht; `client_supports_apps` greift dort nie, es bleibt beim Text plus
`structuredContent`. Mit dem modernen Umschlag (Protokoll 2026-07-28, Fähigkeiten je Anfrage) erkennt der Server
Apps-Clients und lässt den Hinweis „Ansicht wird im Chat angezeigt“ voranstellen.

**Herkunft:** `form_schemas.erstellt_via` und `form_submissions.erstellt_via` (`app`/`ki`, NULL = `app`)
werden nur aus `auth.via == "mcp"` gesetzt (Migration 0120), nie aus dem Request.

### Prompts

`protokoll_vorlage_entwerfen` (thema, vorgaben), `wartungsprotokoll_zu_vorgang_ausfuellen`
(vorgang_id), `monatsbericht` (monat, team). Sie geben nur Anweisungen vor und nennen die neuen Tool-Namen.

### Journal und Rückgängig

Jede schreibende Tool-Aktion schreibt eine Zeile in `ki_aktionen` (Migration 0128, RLS wie alle Mandantentabellen):
Tool, Aktionsart (`vorgang.aendern`, `vorgang.verknuepfen`, …), Stufe (1 anlegen, 2 ändern/verknüpfen), Ziele,
`aenderungen` (Vorher/Nachher roh und als Anzeigetext), `erzeugt`, `rueckweg` (Gegenoperationen mit Prüfungen),
`rueckgaengig_bis` (7 Tage) und Status (`ausgefuehrt`, `rueckgaengig`, …). Die Tabelle `ki_regeln` ist für
Etappe B vorbereitet (Bestätigungsmodus je Aktionsart), wird in Etappe A noch nicht gelesen. Der Journal-ID geht als
Header `X-FieldVibe-KI-Aktion` an die Fachroute (`deps.get_current_user`, nur bei `via=mcp`) und steht als
`ki_aktion_id` im Payload der Audit-Einträge dieses Aufrufs.

Rückgängig (`app/services/ki_rueckgaengig.py`, Tool `rueckgaengig` und `POST /api/ki/aktionen/{id}/rueckgaengig`
aus der Seite KI-Aktivität): zuerst Frist, Status und Berechtigung (Auslöser oder Administrator), dann **alle**
Prüfungen (Felder noch so, wie die KI sie hinterlassen hat; angelegte Datensätze seit dem Anlegen unverändert,
also `updated_at` gleich); bei Abweichung passiert nichts und der Aufrufer bekommt die Konfliktliste (HTTP 409 bzw.
Tool-Fehler mit Klartext). Erst danach laufen die Rückweg-Operationen in umgekehrter Reihenfolge über die
Fachrouten mit den Rechten des Auslösers (Anlegen → Papierkorb per DELETE, Ändern → PATCH mit den Vorher-Werten,
Verknüpfung → Gegenoperation). Nicht zurücknehmbar: Kommentare (Verlaufseinträge), Vorlagen-Entwürfe, Ergänzen
eines Protokolls. REST-Vertrag: `GET /api/ki/aktionen` (Filter Status, Nutzer, Zeitraum, Suche; Administratoren
sehen alle, andere nur eigene), `GET /api/ki/aktionen/{id}`, `POST …/rueckgaengig`.

**Herkunft „per KI“:** `vorgaenge`, `auftraege`, `projekte`, `angebote`, `rechnungen`, `termine` tragen
`erstellt_via` (`app`/`ki`, Migration 0129), gesetzt aus `auth.via == "mcp"` (`deps.erstellt_via_aus`), nie aus dem
Request; die Read-Schemas liefern es mit.

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
- **Aktions-Registry (fail-closed).** `app/mcp/aktionen.py` ist die einzige Liste schreibender Routen
  (`AKTIONEN`: Methode, Pfadmuster, Aktionsart, Stufe). Was dort nicht steht, wirft im `rest_client` einen
  `PermissionError`; `SCHREIB_ALLOWLIST` wird daraus abgeleitet. DELETE steht in `AKTIONEN` nur zum Lösen von
  Verknüpfungen. Datensatz-DELETE und Gegenoperationen gibt es nur in `RUECKWEG_ROUTEN` und nur mit `rueckweg=True`,
  das ausschließlich `ki_rueckgaengig` setzt. Zusätzlich blockiert der Client hart `PATCH` mit Vorgang-Status
  `abgeschlossen`/`storniert`/`abgerechnet` und Auftrag-Status `abgeschlossen`/`storniert`, unabhängig vom Tool.
  Ein Test prüft, dass jede Registry-Route in der OpenAPI wirklich existiert.
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
