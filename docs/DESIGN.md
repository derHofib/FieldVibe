# UI/Design-Richtlinien — "Industry"

Verbindliches Design-System der App (Feld-App, Office, Super-Admin,
Kundenportal) seit der App-weiten Umstellung. Referenz-Screens:
Design-Handoff-Mockups (Feed/Vorgang-Detail/CRM-Shell). Bei neuen UI-
Elementen zuerst hier nachsehen, danach im `fieldvibe-design`-Skill
(deckungsgleich, aber mit exakten Code-Fundstellen).

## Grundprinzip: Blaupausen-Optik
- Quadratisch statt rund: `rounded-none` überall (keine `rounded-lg`/
  `rounded-full`-Karten/Buttons mehr, Ausnahmen: Avatare/Initialen-Kreise,
  kleine Zähler-Badges, echte Kreis-Formen im Whiteboard/Board-Feature)
- Haarlinien-Rahmen statt Schatten: `border border-ind-line` (bzw.
  `-ind-line-2` für verschachtelte/untergeordnete Blöcke) statt
  `shadow-xs`/`shadow-md`/Neumorphismus. Karten haben keinen Hintergrund-
  Farbwechsel gegenüber der Seite (`bg-ind-bg`), sie grenzen sich nur
  über den Rahmen ab
- Passermarken (`Blueprint`-Komponente, `components/Blueprint.tsx`):
  vier Eck-Häkchen für "hero"-Karten (Feed-Karten, Login-Karte,
  Übersichts-Karte) — nicht für jede kleine Box, das wäre zu unruhig
- Primärfarbe (`--color-ind-acc`/`-acc-txt`/`-btn-bg`) ist die einzige
  kräftige Fläche: Primär-Buttons, aktive Segmented-Zustände
  (`--color-ind-field`), Live-Indikatoren. Alles andere bleibt neutral

## Farbtoken (`frontend/src/index.css`, `@theme`-Block)
Eigene, mit `ind-` präfixierte Custom Properties statt der
ursprünglichen `slate`/`stone`-Skala — ermöglichte die seitenweise
Migration, ist jetzt aber die durchgängige Quelle:

| Token | Verwendung |
|---|---|
| `ind-bg` | Seiten-/Karten-Hintergrund |
| `ind-ink` / `ind-ink-2` / `ind-ink-3` | Text: Überschrift/Primärtext / Sekundärtext / Meta-Text |
| `ind-line` / `ind-line-2` | Rahmen: Standard / kräftiger (verschachtelte Blöcke, Divider) |
| `ind-acc` / `ind-acc-txt` / `ind-acc-soft` | Akzent: Icon/Rahmen / Text auf Akzent / dezente Flächen (Filter-aktiv) |
| `ind-hover` | Hover-Zustand neutraler Elemente |
| `ind-field` / `ind-field-ink` | Gefüllte Aktiv-Fläche (Segmented-Control, Offline-Banner) |
| `ind-btn-bg` / `-btn-bg-h` / `-btn-ink` | Primär-Button (Ruhe/Hover/Text) |
| `ind-warn` / `ind-bad` | Warnung / Fehler (Rahmen+Text, keine Fläche) |

Helle Werte in `@theme`, dunkle Werte in einem `.dark { }`-Block direkt
darunter — Tailwind löst `@theme`-Werte als CSS-Variablen auf, ein
Re-Scope unter `.dark` greift also automatisch für jede Utility-Klasse,
die dieselbe Variable nutzt (kein `dark:`-Präfix pro Klasse nötig).

Echte Semantikfarben (Status-Tags: blau=neu, violett=geplant,
amber=in Arbeit, orange=wartet auf Kunde, grün=erledigt, rot=Fehler/
überfällig) bleiben eigenständige Tailwind-Farben (`text-blue-700
dark:text-blue-300` usw.), nicht Teil der `ind-`-Palette — Statusfarbe
und Marken-Akzent sind bewusst getrennt (siehe Abschnitt Status unten).

## Typografie
- Überschriften/Marke/Labels: Barlow Condensed (`font-heading`), oft
  großgeschrieben mit Sperrung (`uppercase tracking-wide` bzw.
  `tracking-[0.14em]` für kleine Kategorie-Labels)
- Fließtext/UI: Barlow (`font-sans`, Standard-Body-Font)
- Zahlen in Tabellen/Kennzahlen: `tabular-nums`

## Icons
- Ausschließlich lucide-react, `strokeWidth={1.5}` (nicht mehr `2`)
- `IconBadge` (`components/IconBadge.tsx`): Haarlinien-Quadrat statt
  Pastell-Fläche — Rahmenfarbe + Icon in Ton-Farbe, Hintergrund
  transparent. Tonpalette/Zuordnung zu Funktionsbereichen unverändert
  (siehe `fieldvibe-design`-Skill §1)
- Office-Sidebar/Super-Admin-Sidebar: **kein** `IconBadge`, sondern
  bloße 16px-Icons + 2px-Akzent-Strich links bei aktivem Eintrag (Muster
  aus dem CRM-Shell-Mockup) — dort ist die Zeile selbst der Klick-Bereich,
  ein zusätzlicher Rahmen wäre redundant

## Bausteine (`index.css`)
- `.btn-industry` + Modifier `-primary`/`-secondary`/`-ghost`/`-icon`:
  Grundrezept für Buttons (Barlow Condensed, quadratisch, Haarlinie).
  `.btn-industry-primary` füllt mit `--color-ind-btn-bg`
- `.input-industry`: Haarlinien-Input/Select/Textarea, transparenter
  Hintergrund
- `.tag-industry` + `-accent`/`-neutral`/`-outline`: kleine Chips
- `.seg-industry`: zusammenhängende Quadrat-Reihe für Segmented-Controls
  (z. B. Liste/Karte/Filter) — aktiver Zustand `bg-ind-field`
- `.blueprint`/`Blueprint.tsx`: Passermarken-Karte, s. o.

## Status-Tags
Zentrale Quelle weiterhin `config/vorgangDarstellung.ts` (`STATUS_BADGE`)
— **jetzt tatsächlich überall importiert**, keine lokalen Kopien mehr
(siehe Historie: mehrere Seiten hatten eine eigene, veraltete Kopie mit
Pastell-Flächen). Werte sind Rahmen+Text (`border border-{farbe}-400
text-{farbe}-700 dark:border-{farbe}-600 dark:text-{farbe}-300`), keine
gefüllte Pille mehr. Aufrufer dürfen kein zusätzliches `rounded-full`/
`bg-*` mehr um den Wert legen.

## Dark Mode
- Pflicht für jede Seite, weiterhin kein Opt-out
- "Standard im Betrieb": Login/Erstaufruf zeigt nicht mehr zwingend
  Hell — es gilt schlicht die OS-/gespeicherte Präferenz wie überall,
  aber Dunkel ist der für den Field-Einsatz vorgesehene Normalfall
- Technisch unverändert: `.dark`-Klasse auf `<html>`, `ThemeContext.tsx`,
  `localStorage`-Key `fieldvibe-theme`

## Bottom-Navigation (Feld-App)
- Form/Struktur bewusst NICHT auf eckig umgestellt: "schwebende Insel"
  (`rounded-full`), Fixzone + swipebare Rotunde + FAB bleiben wie vorher
  — das ist ein eingespieltes, konfigurierbares Mobil-Pattern
  (`config/navSeiten.ts`, `BottomNavSettingsPage.tsx`), keine reine
  Optik-Frage
- Nur die Oberflächenbehandlung ist umgestellt: Haarlinie statt
  Neumorphismus-Schatten, FAB solide in `--color-ind-btn-bg` statt
  Cyan-Blau-Gradient

## Desktop/Office (office.<domain>) & Super-Admin
- Sidebar 1:1 nach CRM-Shell-Mockup: Hexagon-Logo-Box, Kategorie-Labels
  mit Sperrung, bare Icons + Akzent-Strich (siehe Icons-Abschnitt)
- `Karte` (`office/OfficeUi.tsx`) und `Layout.tsx` (Super-Admin-Shell)
  folgen demselben Rezept wie die Feld-App — eine Änderung an `Karte`
  wirkt auf alle Office-Seiten
- Rest der Desktop-Konventionen (Karte-vs-Zeile, zweispaltiges Panel,
  `max-w-3xl`-Lesespalte, `--klebe-abstand`) unverändert, siehe unten

## Freie Inhalte bleiben unangetastet
Whiteboard/Board-Feature (`office/boards/nodes/*`, `pages/feld/boards/*`):
frei wählbare Sticky-Note-/Karten-Farben sind Nutzerinhalt, nicht
Chrome — die behalten ihre Rundung/Schatten/Farbfläche. Nur die
Bedienelemente drumherum (Toolbars, Buttons, Formulare) folgen dem
Industry-Rezept.

## Formulare
- Lange Auswahllisten (Material etc.) als `SearchableSelect` (tippbare
  Combobox), kein normales `<select>`

## Desktop-Details (unverändert aus der Vorversion)
- **Karte oder Zeile?** Karte, wenn ein Eintrag für sich steht und
  angeklickt wird. Zeile/Tabelle, wenn Werte *zwischen* Einträgen
  verglichen werden (Beträge, Fälligkeiten, Mengen) — deshalb ist die
  Buchhaltung eine Tabelle mit `tabular-nums`, obwohl die Feld-App dort
  Karten zeigt
- Listen mit Detailansicht als zweispaltiges Panel (Liste links, die
  **bestehende** Detailseite rechts eingebettet, über eine optionale
  `id`-Prop statt eigenem Desktop-Nachbau)
- Übernommene Feld-App-Seiten laufen in einer begrenzten Lesespalte
  (`max-w-3xl`)
- Kein `.btn-touch`-Mindestmaß nötig, keine PWA, kein Service Worker
- `--klebe-abstand`: 6rem in der Feld-App (schwebende Bottom-Nav),
  0.75rem im Office
