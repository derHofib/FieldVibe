# Phase 7 – Ausbau

## Was implementiert wurde

### Backend

- **Kundenportal-Authentifizierung** (`kundenportal_zugaenge`, Abschnitt
  9): eine strukturell getrennte Identität, nicht einfach ein neuer
  `User.role`-Wert. Eigene JWT-Token-Typen
  (`kundenportal_access`/`kundenportal_refresh`), Payload trägt
  `role="kunde"` – eine Pseudorolle, die nie einem echten `User.ROLES`-Wert
  entspricht, sodass ein Kunden-Token niemals versehentlich `require_roles(...)`
  auf der Staff-API erfüllen kann – plus einen zusätzlichen `kunde_id`-Claim,
  der die Token-Berechtigung unterhalb der Mandantenebene weiter einschränkt.
  E-Mail ist plattformweit eindeutig über alle Zugänge hinweg (nicht pro
  Mandant), da der Kunde beim Login noch nicht weiß, zu welchem Mandanten
  er gehört – dieselbe Vor-Auth-Situation wie beim Staff-Login.
- **Kundenportal-Datenrouten** (`GET/PATCH /api/kundenportal/*`): eigene
  Vorgänge, Angebote, Rechnungen. `tenant_session` (RLS) erzwingt nur die
  Mandantengrenze – für die Kunde-Grenze *innerhalb* eines Mandanten filtert
  jede Route zusätzlich explizit nach `auth.kunde_id`
  (`_require_own_vorgang`/`_require_own_angebot`/`_require_own_rechnung`,
  404 statt 403 bei Fremdzugriff, um keine Existenz zu verraten).
  `vorgang_events` filtert zusätzlich hart auf `kundensichtbar = true` –
  dieselbe Abschnitt-2/3-Grenze zwischen interner und freigegebener
  Kommunikation, hier aber als WHERE-Klausel statt als bloßer UI-Umschalter
  wie im internen Chat.
- **Kunde kann Angebote annehmen/ablehnen**: die Statusübergangslogik aus
  Phase 6 (`angebot_service.apply_status_transition`) wurde aus
  `angebote.py` in ein eigenes Service-Modul extrahiert, damit sowohl die
  Staff-Route als auch die Kundenportal-Route dieselbe Logik nutzen
  (inkl. automatischer Reparatur-Vorgang-Erstellung bei Annahme). Der
  Kunde darf ausschließlich `versendet → angenommen/abgelehnt` auslösen,
  niemals `entwurf → versendet` – das bleibt Sache des Betriebs.
  `VorgangEvent.author_user_id` ist `NULL`, wenn der Kunde selbst (ohne
  eigenen `User`-Account) die Aktion auslöst.
- **Highlights** (`highlights`, Abschnitt 10): Instagram-artiges Speichern
  einzelner Foto-Events als Portfolio. `UniqueConstraint` auf
  `vorgang_event_id` (ein Foto kann nur einmal Highlight sein, 409 bei
  Duplikat), nur `event_type == "foto"` darf markiert werden.
  Moderationsrechte gestaffelt: `mandant_admin`/`disponent` dürfen jedes
  Highlight löschen, `techniker` nur eigene.
- **Materialwirtschaft** (`material`, `material_verwendungen`, Abschnitt
  11): `Material.bestand` hat einen DB-`CHECK (bestand >= 0)`;
  Verwendungserfassung prüft den Bestand vorab in der Anwendungsschicht
  (400 bei unzureichendem Bestand) und dekrementiert dann atomar innerhalb
  derselben Transaktion. Jede Verwendung erzeugt zusätzlich ein
  `VorgangEvent(event_type="material")` – dieser Event-Typ war seit Phase
  2 reserviert, aber bis jetzt ungenutzt.
- **Insights-Dashboard** (`GET /api/insights`, nur `mandant_admin`):
  Vorgänge nach Status (SQL `GROUP BY`), offene Rechnungssumme
  (`entwurf`/`versendet`, in Python aus `betrag_netto`/`mwst_satz`
  berechnet, da `betrag_brutto` nicht gespeichert wird), Angebots-
  Versand-/Annahmequote, sowie pro-Techniker Wochenstunden aus
  `Zeiterfassung` (abgeschlossene Einträge ab Montag 00:00 UTC der
  laufenden Woche).
- **Story-Leiste erweitert**: der seit Phase 3/5 immer leere
  `material`-Array wird jetzt mit Artikeln unterhalb des Mindestbestands
  befüllt (`ampel="rot"` bei `bestand<=0`, sonst `"gelb"`).
- **Bugfix (vorbestehend, in dieser Phase gefunden)**: `StoryChip`
  im Feed routete `ziel_typ === "pruefmittel"` (seit Phase 5 existent)
  fälschlich auf eine nicht existierende `/anlagen/{id}`-URL, weil nur
  `"vorgang"` explizit behandelt wurde. Behoben mit einer vollständigen
  `STORY_ZIEL_PFAD`-Zuordnungstabelle für alle vier `ziel_typ`-Werte.

### Frontend

- **Eigener Kundenportal-Stack, komplett getrennt vom Staff-Frontend**:
  `kundenAuthStore.ts` (eigener localStorage-Key
  `socialcrm_kundenportal_auth_v1`), `kundenClient.ts`
  (`kundenApiFetch`/`kundenApiFetchBlob` mit eigenem
  401-Refresh-gegen-`/api/kundenportal/auth/refresh`),
  `KundenAuthContext.tsx`, `PortalLayout.tsx`. Kein gemeinsamer Code mit
  dem Staff-`authStore`/`AuthContext`/`client.ts` – ein Kunde und ein
  Mitarbeiter können im selben Browser gleichzeitig eingeloggt sein, ohne
  dass sich die Tokens je überschreiben oder vermischen.
- **`/portal/*`-Routenbaum** (`KundenPortalApp.tsx`): eine eigenständige,
  in sich geschlossene React-Router-`<Routes>`-Instanz, unabhängig vom
  Staff-Login erreichbar – gerendert *vor* der `isAuthenticated`-Verzweigung
  in `App.tsx`, damit ein nicht eingeloggter Mitarbeiter-Browser einen
  `/portal/*`-Aufruf nicht fälschlich auf `/login` statt `/portal/login`
  umleitet.
- **Kundenportal-Seiten**: Login, Auftragsliste + Detail (nur
  kundensichtbare Chat-Einträge, read-only), Angebotsliste + Detail (mit
  PDF-Anzeige und Annehmen/Ablehnen-Buttons bei Status `versendet`),
  Rechnungsliste (mit PDF-Anzeige je Zeile).
- **Highlights-Seite** (`/highlights`): Foto-Portfolio-Grid; ein
  "⭐ Highlight markieren"-Button im Foto-Event-Bubble des Vorgangs-Chats.
- **Material-Tab in "Geschäft"**: Bestandsliste mit Inline-Editing
  (Bestand/Mindestbestand), Anlegen-Formular; "Material verwenden"-Sektion
  im Vorgangs-Chat mit Mengenauswahl und Fehleranzeige bei unzureichendem
  Bestand.
- **Insights-Seite** (`/insights`, nur `mandant_admin`): Stat-Kacheln,
  Status-Balkendiagramm, Techniker-Auslastungsliste.

## Entscheidungen, die ich dokumentiere statt nachzufragen

- **Kundenportal als eigene Identität, nicht als neue `User.role`**: ein
  Kunde ist strukturell kein Mitarbeiter (kein Mandanten-weiter Zugriff,
  keine Rollen-Hierarchie, eigener Login-Endpunkt) – ein separater
  Token-Typ und ein `kunde_id`-Claim bilden das sauberer ab als ein
  `role="kunde"` im selben `User`-Modell, das dann an jeder Stelle
  Sonderfälle bräuchte.
- **RLS erzwingt nur die Mandantengrenze, nicht die Kunde-Grenze**:
  Postgres-RLS-Policies sind hier bewusst auf `mandant_id` beschränkt
  (dieselbe Policy wie überall sonst) – eine zusätzliche Row-Level-Policy
  pro Kunde wäre möglich, aber jede Kundenportal-Route filtert ohnehin
  explizit nach `auth.kunde_id`, weil sie sonst gar keine sinnvollen
  Kunde-spezifischen Abfragen bauen könnte. Die WHERE-Klausel ist die
  eigentliche Durchsetzung; das ist im Code (`get_kunden_db`-Docstring)
  bewusst so kommentiert, damit niemand versehentlich eine neue Route
  ohne diesen Filter ergänzt.
- **404 statt 403 bei Fremdzugriff auf Vorgang/Angebot/Rechnung**: ein
  Kunde soll nicht einmal erfahren können, dass eine fremde ID überhaupt
  existiert.
- **Geteilte Statusübergangslogik über `angebot_service.py`** statt einer
  zweiten, eigenständigen Kopie in der Kundenportal-Route: verhindert,
  dass Staff- und Kunden-Pfad bei einer künftigen Änderung
  auseinanderlaufen.
- **`UniqueConstraint` auf `Highlight.vorgang_event_id`** statt einer
  Anwendungsschicht-Prüfung vor dem Insert: race-sicher bei
  gleichzeitigen Doppelklicks, mit einem sauberen 409 statt eines
  blanken 500 bei Konflikt.
- **Bestandsprüfung sowohl in der Anwendungsschicht (400 mit
  verständlicher Meldung) als auch als DB-`CHECK`**: die
  Anwendungsschicht liefert die nutzbare Fehlermeldung fürs Frontend, der
  `CHECK` ist das eigentliche Sicherheitsnetz gegen jeden denkbaren
  Nebenpfad (Migration, direkter DB-Zugriff, künftiger Code, der die
  Prüfung vergisst).
- **Insights ausschließlich für `mandant_admin`**: Umsatz-/Auslastungs-
  Kennzahlen sind unternehmerische Steuerungsdaten, kein Werkzeug für den
  Tagesbetrieb von Disponent/Techniker.
- **Eigener `kundenAuthStore`/`kundenClient` statt Wiederverwendung der
  Staff-Auth-Infrastruktur**: der entscheidende Grund ist nicht
  Code-Duplizierung an sich, sondern dass ein gemeinsamer Store das
  Risiko schaffen würde, ein Kunden-Token und ein Staff-Token im selben
  Storage-Slot zu verwechseln oder zu überschreiben.

## Wie es getestet wird

```bash
cd backend && source .venv/bin/activate && python -m pytest   # 175 Tests
```

Neu in Phase 7: `test_kundenportal.py` (Login/Refresh, Token-Typ-Isolation
in beide Richtungen – Kunden-Token auf Staff-Endpunkten und
Staff-Token auf Kundenportal-Endpunkten jeweils 401 –, deaktivierter
Zugang, Datenisolation zwischen eigenen und fremden Vorgängen/
Rechnungen inkl. `kundensichtbar`-Filterung, kompletter
Angebot-annehmen-Workflow inkl. automatischem Reparatur-Vorgang,
Angebot-ablehnen, verbotener direkter `versendet`-Übergang durch den
Kunden, Staff-Verwaltung der Portal-Zugänge inkl. Duplikat-E-Mail und
Mindestpasswortlänge), `test_highlights.py` (Anlegen/Liste/Löschen,
Ablehnung bei Nicht-Foto-Event, Duplikat-409, Moderationsrechte
Techniker-eigene-vs-Admin-alle, Mandantenisolation), `test_material.py`
(Anlegen/Ändern nur Admin/Disponent, Verwendung durch jede Rolle,
Bestand-Dekrementierung, Ablehnung bei unzureichendem Bestand,
DB-`CHECK` gegen negativen Bestand, Mandantenisolation),
`test_insights.py` (Zugriff nur `mandant_admin`, Korrektheit der
Aggregationen anhand händisch angelegter Test-Daten, `None`-Annahmequote
ohne versendete Angebote, Mandantenisolation).

End-to-End manuell mit Playwright gegen den echten Dev-Server + Backend +
lokalem PostgreSQL + `moto`-S3-Server verifiziert: Kundenportal-Login mit
einem über die Staff-API angelegten Zugang → Auftragsliste (nur der
eigene Auftrag, korrekter Status) → Auftrag-Detail (nur der
kundensichtbare Kommentar, keine internen Vermerke) → Angebotsliste →
Angebot-Detail (Positionen, Summen) → Annehmen (Status wechselt sichtbar
auf "angenommen") → Rechnungsliste → PDF-Anzeige in neuem Tab (Blob-URL
verifiziert) → Abmelden (eigener localStorage-Key geleert, Staff-Key
unberührt geprüft). Dabei wurde auch geprüft, dass die
Kundenportal-Anmeldung zu keinem Zeitpunkt den Staff-`authStore` berührt
(kein `socialcrm_auth_v1`-Eintrag), was die strikte Trennung der beiden
Identitätsräume bestätigt.

## Was offen bleibt

- Kein eigenständiges Passwort-Reset/-Vergessen für Kundenportal-Zugänge
  – aktuell muss ein Mitarbeiter das Passwort über
  `PATCH /api/kunden/{id}/portal-zugaenge/{zugang_id}` faktisch neu
  vergeben (Endpoint erlaubt aktuell nur `name`/`aktiv`, kein
  Passwort-Reset-Feld) oder den Zugang deaktivieren und neu anlegen.
- Kein Selbstregistrierungs-Flow für Kunden – Zugänge werden ausschließlich
  von Mitarbeitern angelegt, was für ein B2B-Handwerksgeschäft mit
  bestehenden Kundenbeziehungen die passende Vertrauensgrenze ist.
- Highlights haben keine eigene Umbenennungs-/Sortier-Funktion über den
  `titel` hinaus (kein Drag-and-Drop, keine Alben) – für den aktuellen
  Anwendungsfall "Vorher-Nachher-Schaufenster" ausreichend.
- Materialwirtschaft kennt keine Lieferanten, Bestellungen oder
  automatische Nachbestell-Benachrichtigungen – die Ampel in der
  Story-Leiste macht Unterbestand nur sichtbar, löst aber keine Aktion aus.
- Insights sind rein lesend ohne Zeitraum-Auswahl (immer "aktuelle Woche"
  für die Techniker-Auslastung) – ein Zeitraum-Filter oder Export wäre
  eine natürliche Erweiterung, aber ohne konkreten Anwendungsfall aus dem
  Lastenheft nicht vorgezogen.

Damit ist der in Abschnitt 3 des Lastenhefts beschriebene 7-Phasen-Kernumfang
vollständig umgesetzt (siehe README für den Gesamtstatus).
