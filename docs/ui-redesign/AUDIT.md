# UI-Redesign „Apple-Stil" — Phase A: Bestandsaufnahme

Stand: 2026-09-24. Grundlage für die vollständige Umstellung von Präsentationsschicht
auf das Apple-HIG-Design aus dem Auftrag. Keine Backend-/API-/Rechte-Änderungen.

## 1. Stack

- **Framework:** React 19 + TypeScript + Vite (Rolldown-Variante, `vite v8`), `react-router-dom` (Client-Routing, kein SSR).
- **Styling:** Tailwind CSS **v4** (`@tailwindcss/postcss`, kein `tailwind.config.*` — Konfiguration läuft komplett über `@theme` in `frontend/src/index.css`). Kein CSS-Modules-Ansatz, keine styled-components.
- **Komponentenbibliothek:** **keine** (kein shadcn/ui, kein Radix, kein Headless UI). Abschnitt 3.4 des Auftrags („Mapping auf shadcn/ui falls vorhanden") entfällt komplett.
- **Icon-Set:** `lucide-react` (bereits das im Auftrag geforderte Set) — durchgängig verwendet, kein zweites Icon-Set im Projekt.
- **Vorhandenes Theming:** Ein bestehendes Custom-Property-basiertes System namens **„Industry"** (Blaupausen-Optik), dokumentiert in `docs/DESIGN.md` + eigenem Claude-Skill `fieldvibe-design`. Wurde in 14 abgeschlossenen Arbeitsschritten über die komplette App ausgerollt (Fonts Barlow/Barlow Condensed, `--color-ind-*`-Token, Recipe-Klassen `.btn-industry*`, `.input-industry`, `.tag-industry*`, `.seg-industry`, `.card-soft*`, `.blueprint`, `.navbar-soft`). **Wird laut Entscheidung vollständig ersetzt**, nicht ergänzt.
- **Dark-Mode-Mechanik (Ist-Zustand):**
  - `@custom-variant dark (&:is(.dark *));` in `index.css` — **exakt** der im Auftrag (2.1) geforderte Tailwind-v4-Mechanismus. Kann 1:1 weiterverwendet werden.
  - `ThemeContext.tsx` (`src/context/ThemeContext.tsx`): **nur binär** `light`/`dark`, kein drittes „Automatisch". Setzt `document.documentElement.classList.toggle("dark", …)` per `useEffect` **nach** dem ersten Render → **kein FOUC-Schutz**, kein Inline-Script im `<head>`. `localStorage`-Key `fieldvibe-theme` (Auftrag verlangt `ui.appearance`). Kein Live-Reagieren auf `prefers-color-scheme`-Änderungen im „automatisch"-Fall, weil es diesen Fall noch nicht gibt.
  - Umschalter `ThemeToggle.tsx`: reiner Mond/Sonne-Button, in 4 Layout-Shells eingebunden (`Layout.tsx`, `FeldLayout.tsx`, `OfficeLayout.tsx`, `PortalLayout.tsx`). Entspricht strukturell dem geforderten Desktop-Toolbar-Umschalter; muss nur um den Automatisch-Zustand + Einstellungen-Auswahl erweitert werden.
  - `index.html`: KEIN Inline-Script — Google-Fonts-Link für Barlow/Barlow Condensed (entfällt beim neuen Systemfont-Ansatz).

## 2. Screens/Routen → Ziel-Screens (Abschnitt 5 des Auftrags)

Die App hat **vier** eigenständige Frontends auf einer Codebase (Weiche über Hostname
bzw. React-Baum): Super-Admin (Plattform), Feld-App (Mobil/PWA), Office (Desktop,
`office.`-Subdomain bzw. `?office=1`), Kundenportal (`/portal/*`). Der Auftrag spricht
von „Auftragsliste/Projektansicht/Auftragsdetail/Neuer Auftrag" — das bildet sich wie
folgt auf die tatsächlichen Routen ab:

| Ziel-Screen (Auftrag) | Desktop (Office) | Mobil (Feld-App) |
|---|---|---|
| **Auftragsliste** | `office/vorgaenge/OfficeVorgaengePage.tsx` (`/vorgaenge`) — hat bereits 4 Ansichten: Liste (`VorgaengeListe.tsx`), Kanban (`VorgaengeKanban.tsx`), Raster (`VorgaengeRaster.tsx`), Tabelle (`VorgaengeTabelle.tsx`, gerade erst gebaut) | `pages/feld/FeedPage.tsx` (`/feed`) — aktuell Karten-Feed mit Status-Filter-Pills, kein „Aufträge"-Tab im heutigen BottomNav (Feed ist Startseite) |
| **Projektansicht** | `office/projekte/OfficeProjektePage.tsx` (`/projekte`) — aktuell Asana-artiges Kanban-Board (Spalten/Aufgaben), **fachlich anders** als der im Auftrag beschriebene „Projekt mit gruppierten Aufträgen + Phasenleiste + offene Positionen" | **kein Äquivalent** — Projekte sind aktuell eine reine Office-Funktion, kein Mobil-Screen. Auftrag verlangt einen „Projekte"-Tab in der Tab-Bar (5.3) — muss neu entstehen |
| **Auftragsdetail** | dieselbe Komponente wie Mobil: `pages/feld/VorgangDetailPage.tsx` (`/vorgaenge/:id`), auf Office zusätzlich als 340px-Inspektor-Spalte innerhalb der Auftragsliste (`VorgaengeListe.tsx` bindet sie bereits schmalspaltig ein) | `pages/feld/VorgangDetailPage.tsx` — **2671 Zeilen**, sehr umfangreich: Mängel, Angebote, Rechnungen, Termine, Formulare, Zeiterfassung, Events/Chat, Fotos — deutlich mehr Abschnitte als die 4 im Auftrag (Aktionskacheln/Projekt/Einsatz/Tätigkeiten) beschriebenen |
| **Neuer Auftrag** | `pages/feld/NewVorgangPage.tsx` (`/neu`) — 568 Zeilen, aktuell eigene Seite, kein Sheet/Dialog | dieselbe Seite, aktuell Vollbild-Route statt Sheet |

**Wichtige Lücke:** Die Projektansicht des Auftrags (gruppierte Aufträge nach
Phasen/Abschnitten, „offene Positionen aus dem Leistungsverzeichnis") passt fachlich
**nicht** zum bestehenden `OfficeProjektePage.tsx` (Asana-Kanban, siehe eigene
Session-Historie: „Projekt" wurde bewusst unabhängig von Vorgängen gehalten, erst
kürzlich um eine optionale `vertrag_id`/`Vorgang.projekt_id`-Verknüpfung erweitert).
Die im Auftrag beschriebene Projektansicht wird als **neuer** Bildschirm gebaut, der
die vorhandenen Daten (`Projekt`, per `projekt_id` verknüpfte `Vorgang`e, `Vertrag`)
nutzt — das Asana-Kanban (Spalten/Aufgaben) bleibt als eigene Funktion bestehen und
bekommt nur das neue Token-/Komponenten-Set, wird aber nicht zur „Projekt"-Ansicht
im Sinne des Auftrags umgebaut (siehe Datenlücken in REVIEW.md).

**Weitere Screens** (übrige Feld-App/Office/Super-Admin/Portal-Routen, ca. 90 Seiten
gesamt über alle vier Frontends) werden gemäß Abschnitt 8 Punkt 5 im Anschluss auf
Tokens/Bausteine umgestellt, ohne die dort jeweils vorhandene fachliche Struktur zu
verändern (nur Präsentationsschicht).

### Statusfarben-Mapping (Datenlücke, siehe auch REVIEW.md)

`Vorgang.status` kennt 7 Werte (`neu, geplant, in_arbeit, wartet_kunde, abgeschlossen,
abgerechnet, storniert`), der Auftrag (3.2) definiert aber nur 5 Statusfarben (Neu,
Geplant, In Arbeit, Material fehlt, Erledigt) — „Material fehlt" ist zudem kein
Vorgang-Status in diesem Backend (das ist ein Mangel-Konzept). Geplantes Mapping,
damit alle 7 echten Stati eine Farbe haben, ohne von der Token-Palette abzuweichen:

| Vorgang.status | Verwendetes Token |
|---|---|
| `neu` | Neu (Blau) |
| `geplant` | Geplant (Grau) |
| `in_arbeit` | In Arbeit (Orange) |
| `wartet_kunde` | **neuer** Token „Wartet auf Kunde" (Apple `systemPurple`, analog zur Palette abgeleitet — siehe Begründung REVIEW.md) |
| `abgeschlossen` | Erledigt (Grün) |
| `abgerechnet` | Erledigt (Grün), Label bleibt „Abgerechnet" — Farbe unterscheidet sich bewusst nicht von „Erledigt" (beides ein Endzustand) |
| `storniert` | Geplant-Grauton wiederverwendet, Label „Storniert“, Titel zusätzlich durchgestrichen |
| „Material fehlt" (Token bleibt reserviert) | wird für Mangel-Status verwendet (`app/models/mangel.py`), nicht für `Vorgang.status` |

## 3. Wiederverwendete Basis-Bausteine (Ist-Zustand)

Es gibt **keine** eigenständigen Komponenten-Dateien für Button/Input/Table/Badge/
Dialog/Sheet/Tabs. Stattdessen ein CSS-Recipe-Muster: Klassen mit `@apply` in
`index.css`, die auf JSX-Ebene als `className` verwendet werden:

| Klasse | Zweck | Ersetzt durch (Abschnitt 4) |
|---|---|---|
| `.btn-industry`, `-primary`, `-secondary`, `-ghost`, `-icon` | Buttons | Bordered Button, Primärbutton, Toolbar-Button, Kapsel-Button |
| `.input-industry` | Textfelder | Suchfeld-Optik / Formularfelder in Gruppierter Liste |
| `.tag-industry`, `-accent`, `-neutral`, `-outline` | Badges/Pillen | Status-Pille, Filter-Chip |
| `.seg-industry` | Segmentierte Auswahl | Segmented Control |
| `.card-soft`, `-inner` | Karten | Karte/Inspektor/Gruppenbox |
| `.blueprint` | Eckmarken-Dekor (Industry-spezifisch) | entfällt ersatzlos |
| `.btn-clay`, `.navbar-soft` | Zusatz-Buttons/Navbar-Blur | Primärbutton bzw. Toolbar/Tab-Bar-Blur |

Echte React-Komponenten, die wiederverwendet werden (bleiben strukturell bestehen,
werden nur umgestylt): `EmptyState.tsx`, `Skeleton.tsx`, `StatusBadge.tsx`,
`IconBadge.tsx`, `SeitenPanel.tsx` (Sheet-artiges Slide-over, Basis für „Sheet" im
Auftrag), `SearchableSelect.tsx`, `FilterVorlagenLeiste.tsx`.

**Neu zu bauen** (existieren als eigenständige, wiederverwendbare Komponente noch
nicht): Status-Pille, Status-Kreis, Monogramm, Segmented Control (als React-Komponente
mit `role="group"`/`aria-pressed`, aktuell nur CSS), Such-Feld-Komponente, Pull-down-
Menü (aktuell keine Menü-Komponente im Projekt), Filter-Chip, Switch (`role="switch"`),
Abhak-Kreis (`role="checkbox"`), Symbol-Kachel, Gruppierte-Liste-Bausteine
(Container/Zeile/Abschnittskopf), Sheet-Wrapper für Mobil-Bottom-Sheets (kann
`SeitenPanel.tsx` als Ausgangsbasis erweitern), Drei-Zustands-Theme-Switch.

## 4. Hartkodierte Farben — Bestand

| Art | Treffer | Dateien |
|---|---|---|
| Hex-Farben (`#…`) außerhalb `index.css` | 9 Zeilen | `MapboxFeedMap.tsx`, `MapboxMap.tsx`, `SignaturePad.tsx`, `FormFieldRenderer.tsx` (Canvas-Zeichenflächen — **legitime Ausnahme**, da Canvas-2D-API/Mapbox-GL keine CSS-Variablen lesen kann, siehe unten), `OfficeBoardPage.tsx`/`OfficeBoardsPage.tsx`/`BoardCanvasAnsicht.tsx` (React-Flow-Hintergrundraster), `UebersichtPage.tsx` (Sparkline-Farben), `FeedPage.tsx` (Status-Farb-Map für Kartenrand) |
| `rgb(`/`rgba(`/`hsl(` literal in Komponenten | 0 | — |
| Tailwind-Palettenfarben (`bg-blue-600` u. ä.) | **2870 Treffer in 118 Dateien** | Schwerpunkte: `VorgangDetailPage.tsx` (46), `KundeProfilePage.tsx` (38), `ProjektAufgabeDetailPanel.tsx` (38), `AnlageProfilePage.tsx` (27), `FormFieldRenderer.tsx` (25), `OfficeDispoPage.tsx` (24), `MailClient.tsx`/`MailKontoFormular.tsx` (21/20) — vollständige Liste in der Umsetzung je Bereich, nicht hier dupliziert |

**Canvas-/Karten-Ausnahme:** `MapboxFeedMap.tsx`, `MapboxMap.tsx`, `SignaturePad.tsx`,
`FormFieldRenderer.tsx` (Unterschrift-/Foto-Plan-Canvas), `OfficeBoardPage.tsx` u. ä.
(React-Flow-Whiteboard) setzen Farben über eine **imperative** Canvas-2D- bzw.
Mapbox-GL-API, die keine CSS-Variablen entgegennimmt. Diese werden nicht auf `0`
gescannt, sondern per `getComputedStyle(document.documentElement).getPropertyValue(...)`
zur Laufzeit aus den neuen Tokens gelesen (technisch keine hartkodierten Werte mehr,
aber im reinen Text-Scan nicht von echten Hex-Literalen unterscheidbar — wird im
REVIEW.md als bewusste, begründete Ausnahme geführt, sofern der Scan sie weiter
anzeigt).

## 5. Umsetzungsreihenfolge (konkretisiert aus Abschnitt 8)

1. Tokens (`index.css` `@theme` + `.dark`-Block) + Drei-Zustands-Dark-Mode
   (`ThemeContext.tsx` umbauen, Inline-Script in `index.html`, `ThemeToggle.tsx`
   erweitern, neue Einstellungen-Auswahl) + Systemschrift (Google-Fonts-Link
   entfernen, `font-family`/`letter-spacing`/`tabular-nums`-Utility).
2. Neue Basis-Komponenten (Abschnitt 3 oben) als eigene Dateien unter
   `src/components/apple/` (Name vorläufig — enthält nur Bausteine, keine
   Geschäftslogik), plus Recipe-Klassen in `index.css` für die reinen CSS-Bausteine
   (Buttons, Karten, Trennlinien).
3. Layout-Rahmen: `OfficeLayout.tsx` (Seitenleiste + Toolbar-Grundgerüst),
   `FeldLayout.tsx`/`BottomNav.tsx` (Tab-Bar), Breakpoint-Handling (768/1280) in
   beiden.
4. Ziel-Screens in der vorgegebenen Reihenfolge (Auftragsliste Desktop → Projekt
   [neu] → Auftragsliste Mobil → Auftragsdetail Mobil → Neuer Auftrag).
5. Übrige ~90 Screens (Formulare, Einstellungen, Tabellen, Dialoge, Login,
   Super-Admin, Kundenportal, restliche Office-/Feld-App-Seiten) auf Tokens/
   Bausteine umstellen.
6. Farb-Scan auf 0 Treffer (mit dokumentierten Canvas-Ausnahmen).
7. Testinfrastruktur (Playwright + axe-core, existiert im Projekt noch nicht —
   `@playwright/test` ist nicht in `package.json`; unter `/opt/pw-browsers` liegt in
   dieser Sandbox nur ein vorinstalliertes **Chromium**, kein WebKit — ob sich WebKit
   hier nachinstallieren lässt (Netzwerk/Systemabhängigkeiten), wird in Phase D
   geprüft und andernfalls als Einschränkung in REVIEW.md dokumentiert) + REVIEW.md.

Weiter mit Phase B.
