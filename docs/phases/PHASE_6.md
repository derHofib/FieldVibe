# Phase 6 – Geschäftsprozesse

## Was implementiert wurde

### Backend

- **Mängel** (`maengel`, Abschnitt 4.6): an einen Vorgang gebunden, mit
  Schweregrad (`kritisch`/`hoch`/`mittel`/`niedrig`) und Status
  (`offen`/`in_angebot`/`in_bearbeitung`/`behoben`/`abgelehnt`). Jede Rolle
  darf einen Mangel melden und direkt "vor Ort" auf `behoben`/`abgelehnt`
  setzen (`PATCH /api/maengel/{id}`) – der Weg über `in_angebot`/
  `in_bearbeitung` wird ausschließlich von den Angebot-Routen gesteuert,
  damit der Status nie von einem tatsächlich existierenden Angebot/
  Reparatur-Vorgang abweicht.
- **Angebote** (`angebote` + `angebot_positionen`, Abschnitt 4.6):
  Status-Lifecycle `entwurf → versendet → angenommen/abgelehnt` (nur diese
  Übergänge, kein Überspringen). Positionen (Menge/Einheit/Einzelpreis)
  können im Entwurf beliebig ergänzt werden; die Summen (netto/brutto)
  werden bei jedem Lesen aus den Positionen berechnet, nicht gespeichert –
  keine Gefahr veralteter Summen nach nachträglicher Preisänderung.
- **Mangel-zu-Angebot-Workflow** (`POST /api/angebote/from-maengel`):
  erzeugt ein Angebot aus einer Liste offener Mängel (eine Position pro
  Mangel, Einzelpreis startet bei 0 – der Mangeltext beschreibt das
  Problem, nicht dessen Preis, den der Disponent wie auf einem
  Papier-Angebot vor dem Versenden nachträgt). Wird das Angebot
  **angenommen**, entsteht automatisch ein gemeinsamer Reparatur-Vorgang
  für alle verknüpften Mängel (`Mangel.reparatur_vorgang_id`); wird es
  **abgelehnt**, springen die Mängel zurück auf `offen` (erneut
  angebotsfähig). Schließt der Reparatur-Vorgang ab
  (`PATCH /api/vorgaenge/{id}` → `abgeschlossen`), gelten die verknüpften
  Mängel automatisch als `behoben` – dasselbe Muster wie
  `Pruefzyklus.offener_vorgang_id` aus Phase 5.
- **Rechnungen** (`rechnungen`, Abschnitt 4.8): Status-Lifecycle
  `entwurf → versendet → bezahlt`, `storniert` von `entwurf`/`versendet`
  aus möglich. Wird eine mit einem Vorgang verknüpfte Rechnung `bezahlt`,
  wechselt der Vorgang automatisch auf `abgerechnet` (nutzt den in Phase 2
  bereits vorgesehenen Status).
- **PDF-Protokolle** (`fpdf2`, reine Python-Bibliothek ohne
  Systemabhängigkeiten wie bei weasyprint): Angebot-PDF
  (`GET /api/angebote/{id}/pdf`), Rechnung-PDF
  (`GET /api/rechnungen/{id}/pdf`), Mängel-Protokoll-PDF pro Vorgang
  (`GET /api/maengel/protokoll/pdf?vorgang_id=`). "EUR" statt "€" im PDF,
  weil fpdf2s Core-Fonts (Windows-1252) das Euro-Zeichen nicht über alle
  Renderer hinweg zuverlässig darstellen.
- **Vorgangs-Chat-Integration**: Mangel-/Angebot-/Rechnungsstatus-Events
  laufen über die in Phase 2/3 bereits reservierten Event-Typen (`mangel`,
  `angebot`, `rechnung_status`) – die generische Chat-Bubble-Darstellung
  dafür existierte im Frontend schon (`event.body`-Fallback), ohne dass
  dafür neuer UI-Code nötig war.

### Frontend

- **Mängel-Sektion im Vorgangs-Chat**: Melden (mit Schweregrad-Auswahl),
  Liste mit "Behoben"/"Verwerfen" für offene Mängel, Mängel-Protokoll-PDF-
  Download, sowie ein "Angebot aus offenen Mängeln erstellen"-Button
  (Admin/Disponent) über den offenen Mängeln des Vorgangs.
- **Geschäft** (`/geschaeft`, neuer Bottom-Nav-Eintrag für Admin/
  Disponent): Tabs für Angebote/Rechnungen, jeweils mit Liste + Anlegen-
  Formular.
- **Angebot-Detail** (`/angebote/:id`): Positionen-Tabelle mit
  Hinzufügen-Formular (nur im Entwurf), Summenblock, Status-Buttons
  ("An Kunden senden", "Angenommen"/"Abgelehnt"), PDF-Anzeige.
- **Rechnung-Detail** (`/rechnungen/:id`): Betrag/Fälligkeit, Status-
  Buttons ("An Kunden senden", "Als bezahlt markieren", "Stornieren"),
  PDF-Anzeige.
- **PDF-Downloads über `apiFetchBlob`**: ein einfacher `<a href>` auf einen
  authentifizierten Endpunkt funktioniert nicht (der Browser sendet dabei
  keinen Authorization-Header) – stattdessen wird der PDF-Response als
  Blob mit Token geholt und über eine Object-URL in einem neuen Tab
  geöffnet.

## Entscheidungen, die ich dokumentiere statt nachzufragen

- **Direkter Mangel-Statuswechsel nur `offen → behoben/abgelehnt`**: alles
  andere läuft ausschließlich über den Angebot-Workflow, damit
  `in_angebot`/`in_bearbeitung` nie ohne ein tatsächlich existierendes
  Angebot/Reparatur-Vorgang gesetzt werden kann.
- **Ein gemeinsamer Reparatur-Vorgang für alle Mängel eines Angebots**
  statt eines Vorgangs pro Mangel – ein angenommenes Angebot ist in der
  Praxis ein Termin/Auftrag, nicht mehrere unabhängige.
- **Einzelpreis startet bei 0** bei aus Mängeln erzeugten Positionen –
  kein erfundener Preis, das ist wie bei jedem Papier-Angebot die Aufgabe
  des Disponenten vor dem Versenden.
- **`fpdf2` statt `weasyprint`**: reines Python-Package ohne
  Cairo/Pango-Systemabhängigkeiten, damit Docker-Image und CI schlank
  bleiben – für tabellarische Geschäftsdokumente ohne komplexes CSS-Layout
  ausreichend.
- **Summen (netto/brutto) werden berechnet, nicht gespeichert**: einzige
  Quelle der Wahrheit sind die Positionen; verhindert veraltete Summen
  nach nachträglicher Preisänderung im Entwurf.
- **Rechnung ohne eigene Positionen** (nur ein Gesamt-Netto-Betrag): im
  Unterschied zum Angebot ist eine Rechnung hier meist eine
  Abschlussrechnung zu einem bereits verhandelten/abgeschlossenen
  Auftrag – eine Positions-Tabelle wie beim Angebot wäre für den
  abgedeckten Anwendungsfall unnötige Komplexität; das lässt sich in
  einer späteren Phase erweitern, falls Teil-/Sammelrechnungen mit
  Einzelpositionen gebraucht werden.

## Wie es getestet wird

```bash
cd backend && source .venv/bin/activate && python -m pytest   # 145 Tests
```

Neu in Phase 6: `test_maengel.py` (Melden, Schweregrad-Validierung,
direkte Statuswechsel erlaubt/verboten, Mängel-Protokoll-PDF,
RLS-Isolation), `test_angebote.py` (Anlegen mit Positionen, kompletter
Mangel-zu-Angebot-Workflow inkl. automatisch erzeugtem Reparatur-Vorgang
und automatischem "behoben" bei dessen Abschluss, Ablehnung revertiert
Mängel, ungültige Statusübergänge, PDF), `test_rechnungen.py`
(Statuswechsel inkl. automatischem `abgerechnet` am verknüpften Vorgang,
ungültige Übergänge, PDF).

End-to-End manuell mit Playwright gegen den echten Dev-Server + Backend +
lokalem PostgreSQL + `moto`-S3-Server verifiziert: Mangel im
Vorgangs-Chat melden → Angebot daraus erstellen → Position mit echtem
Preis versehen → PDF anzeigen (Response-Status/Content-Type geprüft) →
An Kunden senden → Angenommen (Reparatur-Vorgang automatisch sichtbar
verknüpft) → über "Geschäft" eine Rechnung anlegen → PDF anzeigen →
senden → als bezahlt markieren.

## Was offen bleibt

- Kundenportal, Highlights, Materialwirtschaft, Insights: Phase 7.
- Keine echte Buchhaltungs-/Rechnungs-API-Anbindung (lexoffice, sevdesk
  o. ä.) – `mandant_integrationen` (Phase 1) ist als generischer Slot
  dafür vorgesehen, eine konkrete externe Integration ohne echte
  Zugangsdaten/API-Dokumentation zu bauen wäre geraten statt fundiert.
- Keine Teil-/Sammelrechnungen mit eigenen Positionen (siehe oben) und
  keine automatische Mahnwesen-Eskalation bei überfälligen Rechnungen.
