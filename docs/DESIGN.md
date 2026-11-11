# UI/Design-Richtlinien — Apple HIG

Verbindliches Design-System der App (Feld-App, Office, Super-Admin,
Kundenportal) seit dem "UI-Redesign Apple-Stil" (`docs/ui-redesign/AUDIT.md`
…`REVIEW.md`). Löst das vorherige, App-weit ersetzte "Industry"-System
(Blaupausen-Optik) vollständig ab. Bei neuen UI-Elementen zuerst hier
nachsehen, danach im `fieldvibe-design`-Skill (deckungsgleich, aber mit
exakten Code-Fundstellen).

## Grundprinzip: Apple Human Interface Guidelines

- Systemschrift statt eigener Web-Font, generöse Radien statt scharfer
  Kanten, eine einzige Akzentfarbe (`--tint`, Apple `systemBlue`) statt
  Marken-Grau/-Blau-Mix aus der Vorversion
- Flächen statt Rahmen als primäres Gliederungsmittel: Karten/Listen
  heben sich über eine eigene Hintergrundfläche (`--cell`/`--card`) vom
  Seitenhintergrund (`--gbg`) ab, Haarlinien (`--sep`) nur zusätzlich, wo
  Trennung nötig ist (Listenzeilen, Kopf-/Fußleisten)
- Farbe ausschließlich für drei Rollen: **Status** (Vorgang-/Rechnungs-
  Zustand, sechs feste Token), **Kategorie** (Bereichs-Zuordnung von
  Icons, `--tone-*`/`--tile-*`, rein illustrativ) und **Aktion**
  (`--tint`, Primär-Buttons/Links/aktive Zustände). Nie Farbe nur zur
  Dekoration
- Dark Mode ist Pflicht für jede Seite, kein Opt-out (siehe unten)
- Presentation-Layer-only: dieses Redesign hat keine Backend-/API-/
  Rechte-Änderung ausgelöst

## Farbtoken (`frontend/src/index.css`, `@theme`-Block)

| Token | Rolle |
|---|---|
| `gbg` | Äußerster Seitenhintergrund |
| `cell` | Zeilen-/Listenflächen (`GroupedList`) |
| `win` | Fenster-/Panel-Fläche (Office-Inspektor) |
| `card` | Karten-/Formularfläche (`.card-ap`, `.field-ap`) |
| `fill` / `fill2` | Neutrale Füllflächen (sekundäre Buttons, Zeilen-Hover) — `fill` dezent, `fill2` kräftiger |
| `label` / `label2` / `label3` | Text: Primär / Sekundär / Tertiär-Meta |
| `sep` / `sepstrong` | Trennlinie: Standard / kräftiger (Fokus-Ringe, Listen-Handles) |
| `tint` | Akzentfarbe (Apple `systemBlue`) — Icons, Ränder, Indikatoren, aktive Zustände. Für **echten Text** und **weißen Text auf Tint-Fläche** siehe unten |
| `tint-text` | Text-/Link-Variante von `tint` (im Dunkel-Modus aufgehellt, im Hell-Modus leicht abgedunkelt) — reines `tint` unterschreitet dort 4.5:1 |
| `tint-solid` | Button-Flächen-Variante von `tint` für weißen Text (`.btn-ap-primary`, `.btn-ap-capsule-primary`) — im Dunkel-Modus abgedunkelt, sonst identisch zu `tint` |
| `tintbg` | Dezente Akzent-Fläche (aktiver Filter, Badges) |
| `tone-sky/violet/amber/rose/emerald/indigo/cyan/slate/teal` | Kategoriale Icon-Töne (`IconBadge`/`StatusBadge`), fest in beiden Modi |
| `tile-blue/red/green/orange/indigo/gray` | Farben für `SymbolKachel` (gefüllte Icon-Kachel), fest in beiden Modi |
| `switch-on` | Aktivfarbe für `Switch` (Apple `systemGreen`) |

Helle Werte im `@theme`-Block, dunkle Werte in einem `.dark { }`-Block
direkt darunter — dieselbe Custom-Property-Strategie wie zuvor, kein
`dark:`-Präfix pro Klasse nötig.

**Warum `tint-text`/`tint-solid` als eigene Token** (Phase D, axe-core):
`tint` selbst braucht als Icon/Rand/Indikator nur 3:1 Kontrast (WCAG
1.4.11), reichte dort unverändert. Als echter Text auf neutraler Fläche
bzw. als Fläche unter weißem Text brauchte es im Dunkel-Modus
**gegensätzliche** Anpassungen (heller für Text, dunkler für die Fläche)
— deshalb zwei eigene Token statt eines geänderten `tint`.

### Statusfarben (sechs Token, `components/apple/status.ts`)

`Vorgang.status` kennt 7 echte Werte, der Auftrag nennt 5 Statusfarben +
2 Erweiterungen (`wartet`, `fehlt` für Mangel-Status). Mapping:

| Vorgang.status | Status-Token | Farbe |
|---|---|---|
| `neu` | `neu` | Blau |
| `geplant` | `geplant` | Grau |
| `in_arbeit` | `arbeit` | Orange |
| `wartet_kunde` | `wartet` | Violett |
| `abgeschlossen` | `erledigt` | Grün |
| `abgerechnet` | `erledigt` | Grün (Label bleibt „Abgerechnet") |
| `storniert` | `geplant` | Grau (Titel zusätzlich durchgestrichen) |
| — (Mangel-Status) | `fehlt` | Rot |

Jedes Token hat drei Varianten: `st-{key}` (Text), `st-{key}-bg` (Pillen-
Hintergrund), `st-{key}-dot` (kräftigerer Punkt). Nie direkt mappen —
immer über `vorgangStatusZuToken()` (`components/apple/status.ts`), sonst
entstehen Kopien, die bei künftigen Änderungen lautlos auseinanderlaufen
(genau das ist in der Vorversion mehrfach passiert, siehe AUDIT.md).

## Typografie

Systemschrift-Stack (`--font-sans: -apple-system, BlinkMacSystemFont,
'SF Pro Text', 'SF Pro Display', 'Helvetica Neue', sans-serif`), kein
eigener Web-Font mehr geladen.

Benannte Stufen als Token in `index.css` (`@theme`), daraus entstehen die Tailwind-Klassen. Keine rohen `text-[Npx]`, keine halben Pixel.

| Klasse | Größe | Verwendung |
|---|---|---|
| `text-meta` | 11px | Meta, Badges, Zeitstempel, Spaltenköpfe |
| `text-sekundaer` | 13px | Sekundärtext, Buttons (Desktop) |
| `text-fliess` | 15px | Fließtext Desktop |
| `text-zeile` | 17px | Listenzeilen, Felder, Sheet-Titel (Mobil) |
| `text-titel-mobil` | 22px | Seitentitel Mobil, Kennzahlen |
| `text-titel-desktop` | 28px | Seitentitel Desktop |
| `text-nav` | 10px | Ausnahme: Bottom-Nav-Label |

Eingabefelder bleiben mindestens 16px (iOS-Zoom). Ausnahmen ohne Token: Avatar-Initialen (proportional), SVG-Beschriftungen im Gantt, Druck-HTML, Board-Knoten (Nutzerinhalt).

**Versalien** nur in Gruppenüberschriften (`AbschnittskopfB`, Listen-Gruppenköpfe, Tabellen-Spaltenköpfe), dann `text-meta tracking-wide uppercase`. Nie in Titeln, Karten-Überschriften, Buttons, Badges oder Formular-Labels.

`tabular-nums` weiterhin für Zahlen in Tabellen/Kennzahl-Kacheln.

## Icons

Ausschließlich `lucide-react`, nie Emoji, nie frei im Text. Icon-Container:

- **`SymbolKachel`** (`components/apple/SymbolKachel.tsx`) — die eigentliche
  Apple-HIG-Kachel: 29×29px, Radius 7, gefüllte Farbfläche
  (`--tile-*`), weißes Icon (`strokeWidth={2}`). Verwendung z. B. in
  `GroupedListRow`-Zeilen (Projekte-Tab, Mehr-Menü)
- **`IconBadge`/`StatusBadge`** (`components/IconBadge.tsx`, `StatusBadge.tsx`) — dieselbe Form wie `SymbolKachel`: gefüllte Kachel, Radius 7, weißes Icon (`strokeWidth` 2). Fläche über `--tone-*-fill` (amber, emerald, cyan, teal sind dafür abgedunkelt, weißes Icon ≥3:1). `StatusBadge` ist eine getönte Pille mit Punkt und Text.

Eine Formensprache: kein nacktes `border` ohne Radius an Bedienelementen; gestrichelt nur für echte Ablageflächen (Drop-Zonen, Datei- und Karten-Platzhalter).

Bei neuen Bereichs-/Kategorie-Icons: `SymbolKachel` oder `IconBadge`, nie ein Rahmen-Quadrat.

## Bausteine (`components/apple/`, `index.css`)

| Baustein | Datei | Kurzbeschreibung |
|---|---|---|
| `GroupedList`/`GroupedListRow`/`GroupedListValueRow` | `GroupedList.tsx` | iOS-Einstellungen-Liste, `bg-cell`, eingerückte Trennlinie |
| `Sheet` | `Sheet.tsx` | Mobil: Sheet von unten mit Griff. ≥768px: zentrierter 540px-Dialog. Eine Implementierung für beides |
| `SegmentedControl` | `SegmentedControl.tsx` | Umschalter, aktiv = Pille + Fett, inaktiv = `text-label` (nicht `text-label2`, siehe Barrierefreiheit unten) |
| `StatusPille`/`StatusKreis` | `StatusPille.tsx`, `StatusKreis.tsx` | Status-Anzeige, immer Punkt **und** Text (Farbe nie alleiniger Träger) |
| `AbschnittskopfA`/`B`, `AbschnittsFusszeile` | `AbschnittsKopf.tsx` | Listen-Überschrift groß (A) bzw. kleine Versal-Gruppen-Überschrift (B) |
| `Switch` | `Switch.tsx` | Eigener `<button role="switch">`, kein natives Checkbox-Styling |
| `AbhakKreis` | `AbhakKreis.tsx` | Rund, Häkchen bei checked, für Checklisten/Tätigkeiten |
| `FilterChip` | `FilterChip.tsx` | Pille mit optionalem Status-Punkt, aktiv = `bg-tint-solid` |
| `SearchField`, `PulldownMenu`, `Herkunft`, `Monogramm` | jeweils gleichnamige Datei | Suchfeld, Dropdown-Menü, Herkunfts-Badge, Initialen-Kreis |
| `SymbolKachel` | s. o. | gefüllte Icon-Kachel |
| `SeitenKopf`, `AnsichtUmschalter`, `Karte`, `KennzahlKarte`, `TabellenRahmen` | `office/OfficeUi.tsx` | Office-Pendants: Seitentitel (`<h1>`), Ansichts-Umschalter (Liste/Kanban/…), Karte, Kennzahl-Kachel, Tabellen-Rahmen |

CSS-Rezepte (`index.css`):

```css
.card-ap        /* bg-card, 0.5px border-sep, radius-ap-card (12px), shadow-card */
.field-ap       /* Formularfeld: bg-card, border-sep, radius-ap-input (8px), 16px */
.btn-ap         /* Basis-Button: border-sepstrong, bg-card */
.btn-ap-primary /* Füllung tint-solid, weißer Text, radius-ap-sm (7px) */
.btn-ap-toolbar /* 28x28px Icon-only, transparent, hover: fill */
.btn-ap-capsule(-primary|-secondary) /* 44px hoch, radius-ap-pill (999px), für prominente CTAs */
```

Radius-Skala: `--radius-ap-sm` 7px · `-input` 8px · `-md` 10px · `-card`
12px · `-tile` 14px · `-pill` 999px. **Anders als Industry**: Radius ist
hier Standard, nicht die Ausnahme — `rounded-none` kommt praktisch nicht
mehr vor.

**Cascade-Layer-Falle**: `.card-ap`/`.btn-ap` setzen Rand/Schatten als
plain CSS außerhalb jedes `@layer` — das gewinnt immer gegen Tailwind-
Utilities (`border-*`/`ring-*`, im `utilities`-Layer). Eine Farb-/Rand-
Überschreibung auf diesen Rezept-Klassen **muss** per Inline-`style`
erfolgen, eine Tailwind-Klasse wird stillschweigend ignoriert (siehe
Beispiel `VorgaengeRaster.tsx` Auswahl-Ring).

## Dark Mode

Pflicht für jede Seite. Drei-Wege statt binär: hell/dunkel/automatisch
(`ThemeContext.tsx`, `localStorage`-Key `ui.appearance`, folgt
`prefers-color-scheme` im Automatisch-Fall). `.dark`-Klasse auf `<html>`
(`@custom-variant dark (&:is(.dark *))`), Umschaltung über `--color-*`-
Custom-Properties, kein `dark:`-Präfix pro Klasse nötig.

## Layout je Oberfläche

**Feld-App** (`components/FeldLayout.tsx`, mobil, PWA): kein
persistenter Marken-Header mehr — jede Seite trägt ihre eigene
`AbschnittskopfA`-Überschrift (`<h2>`). Für Barrierefreiheit trägt der
Rahmen zusätzlich einen unsichtbaren, routenabhängigen `<h1>` innerhalb
von `<main>` (sonst fehlt der Seite ein Top-Level-Landmark, axe-core
Phase D). `BottomNav.tsx`: vier feste Tabs (Heute/Aufträge/Projekte/
Mehr), kein FAB, kein wischbarer Zusatzbereich.

**Office-Desktop** (`office/OfficeLayout.tsx`, `office.<domain>` bzw.
lokal `?office=1`): feste Seitenleiste (`w-64`, einklappbar `w-16`),
Inhalt trägt eigenen `<h1>` über `SeitenKopf`. Kein `.btn-touch`, keine
PWA.

**Super-Admin** (`components/Layout.tsx`): eigene Sidebar-Instanz mit
eigener `NAV_ITEMS`-Liste, Header-Titel jetzt als `<h1>` (Phase D). Ein
echter `super_admin` sieht dieses Dashboard **immer**, auch auf
`office.<domain>` — nur beim Impersonieren eines Mandanten-Users
erscheint die Office-Shell (`App.tsx`, Routing-Logik, nicht Teil dieses
Redesigns).

**Kundenportal** (`components/PortalLayout.tsx`, `/portal/*`): eigener,
schlanker Rahmen, folgt denselben Token/Bausteinen.

Vier Frontends teilen sich dieselben Token/Bausteine — eine Änderung an
`index.css` oder `components/apple/*` wirkt auf alle gleichzeitig.

## Barrierefreiheit (Phase D, axe-core + Playwright)

`frontend/playwright.config.ts` + `frontend/e2e/apple-redesign.spec.ts`
prüfen automatisiert (Chromium, kein WebKit in der Entwicklungs-Sandbox
verfügbar) drei Referenz-Shells je hell/dunkel gegen einen echten
Dev-Stack. Verbindliche Konventionen daraus:

- **Genau ein `<h1>` pro Seite**, innerhalb eines Landmarks (`<main>`
  o. ä.) — sonst meldet axe-core zusätzlich einen Landmark-Fehler
- **`text-tint`/`bg-tint` nie für echten Text oder für Flächen unter
  weißem Text** — dafür `text-tint-text` bzw. `bg-tint-solid`/
  `.btn-ap-primary` verwenden (reines `tint` bleibt Icons/Rändern
  vorbehalten, siehe Farbtoken oben)
- **Kundenportal (BFSG)**: eigene Prüfung über `e2e/portal-a11y.spec.ts` (alle
  Portal-Seiten hell/dunkel, API gemockt, siehe
  `docs/phases/PHASE_KUNDENPORTAL_B2C.md`). Primär-Aktionen nie als
  `bg-st-*-dot` mit weißem Text (zu wenig Kontrast), sondern `.btn-ap-primary`;
  Fehlermeldungen als `role="alert"` (`Hinweiskasten ton="fehler"`);
  `--st-arbeit-text` ist im Hellmodus `#8f4000`, damit Orange-Text auf
  `--st-arbeit-bg` 4.5:1 erreicht
- Inaktive Segmented-Control-Beschriftung nutzt `text-label`, nicht
  `text-label2` — entspricht auch echten iOS-Segmented-Controls
  (Unterscheidung über Gewicht + Pille, nicht Textfarbe)

## Formulare

Native `<select>` nur über `components/apple/Select.tsx` (`.select-ap`, eigener Chevron, auf Mobil mind. 44px Höhe und 16px Schrift, `groesse="kompakt"` für Filterleisten ab md). Nativ bleiben nur `<select multiple>` und der zustandsgefärbte Rechte-Select im Organigramm.

Lange Auswahllisten weiterhin als `SearchableSelect` (tippbare Combobox),
kein natives `<select>`. `.field-ap` für Standard-Eingabefelder (siehe
Bausteine oben); bei Feldern mit eigener Breite (`w-20` etc.) die
Klassen einzeln setzen statt `.field-ap` (setzt `width: 100%`).

Anlegen: Button `+ Neuer X` (`NEU_BUTTON_KLASSE`) öffnet ein `AnlegenPanel`
(Sheet mobil, Seitenpanel Office), kein inline aufklappendes Formular. Felder
über `Feld` (`components/FormularFeld.tsx`): Label per htmlFor, Pflichtstern,
Feldfehler mit `role="alert"` statt nativer Tooltips (`noValidate`). Der
Absende-Button ist nur während der Anfrage deaktiviert; fehlende Pflichtfelder
melden sich beim Absenden am Feld.

## Freie Inhalte bleiben unangetastet

Whiteboard/Board-Feature (`office/boards/nodes/*`, `pages/feld/boards/*`):
frei wählbare Sticky-Note-/Karten-Farben sind Nutzerinhalt, kein Chrome —
behalten ihre eigene Rundung/Farbe. Nur die Bedienelemente drumherum
(Toolbars, Buttons) folgen dem Apple-Rezept.

## Desktop-Details (unverändert aus der Vorversion)

- **Karte oder Zeile?** Karte, wenn ein Eintrag für sich steht. Zeile/
  Tabelle, wenn Werte zwischen Einträgen verglichen werden (Beträge,
  Fälligkeiten) — Buchhaltung bleibt deshalb eine Tabelle mit
  `tabular-nums`, obwohl die Feld-App dort Karten zeigt
- Listen mit Detailansicht als zweispaltiges Panel (Liste links, die
  bestehende Detailseite rechts eingebettet)
- Übernommene Feld-App-Seiten laufen im Office in einer begrenzten
  Lesespalte (`max-w-3xl`); Ausnahmen in `max-w-[1400px]`: Leistungsverzeichnis (Übersicht als
  Tabelle, Detail mit Seitenspalte, `layout="dicht"`) und `/statistik`
  (eigene Office-Seite `office/zeit/OfficeArbeitszeitPage.tsx`: Monatsliste
  mit allen Kalendertagen statt der Feld-Wochenansicht)

## Interaktionsmuster (UX-Überarbeitung Nov. 2026)

Je Interaktion genau ein Muster; vor einem neuen Baustein hier nachsehen.

- **Rückmeldung (Toast)**: `components/Toast.tsx`, `useToast()` mit `erfolg`/`fehler`/`info`. Erfolg/Info
  als `role="status"` (4 s), Fehler als `role="alert"` (8 s). Für Mutationen genügt `meta: { erfolg: "Gespeichert" }`;
  Fehler meldet der zentrale `MutationCache` in `main.tsx` automatisch, solange die Mutation kein eigenes
  `onError` hat (`meta.stumm` unterdrückt ihn).
- **Bestätigen**: kein `window.confirm`. `useBestaetigung()` (`components/ConfirmDialog.tsx`):
  `if (!(await bestaetigen({ titel, text, bestaetigenLabel, destruktiv }))) return;`. Titel nennt die Aktion,
  Text die Folge, der Button das Verb ("Löschen", "Stornieren"); destruktiv = roter Button, Fokus startet auf "Abbrechen".
- **Anlegen**: `components/AnlegenPanel.tsx` -- Sheet in der Feld-App, Seitenpanel im Office (`istOfficeHost()`).
  Auslöser ist ein Textbutton "+ Neuer X" (ohne Unterstreichung, `font-medium`); kein Inline-Formular über der
  Liste, kein zweiter "Abbrechen"-Toggle. Schließen per X, Escape oder Hintergrund.
- **Zustände einer Datenansicht**: Laden (`SkeletonList`/`DetailSkeleton`, kein "Lädt…"-Text), Inhalt, leer
  (erklärt, warum, und bietet den nächsten Schritt an), Fehler (`components/FehlerZustand.tsx`, unterscheidet
  403/404/Netz, "Erneut versuchen" nur wo sinnvoll). Ein Fehler darf nie wie "leer" oder Dauerladen aussehen.
  Abfragen ohne Recht gar nicht starten (`enabled: hatRecht(...)`) und das zugehörige Feld ausblenden.
- **Kein Zugriff / 404**: Rechte laufen zentral über `RouteGuard` (`config/routenRechte.ts`, abgeleitet aus
  `NAV_SEITEN[].sichtbar`) und zeigen `components/KeinZugriff.tsx`; unbekannte Routen `components/NichtGefunden.tsx`.
  Keine stillen Redirects und keine seiteneigenen "Keine Berechtigung"-Texte. Menüeinträge nur anzeigen, wenn die
  Seite erreichbar ist (gleiche Regel wie das Backend).
- **Fehlerbehandlung**: `SeitenGrenze`/`ErrorBoundary` je Shell mit "Neu laden" und "Fehler melden".
- **Formulare**: Label per `htmlFor`/`useId`; Pflichtfeld mit rotem `*` (`aria-hidden`) und `noValidate`;
  eigene deutsche Fehlermeldung direkt am Feld (`role="alert"`, `aria-invalid`, `aria-describedby`);
  Absende-Button nur während der Anfrage deaktiviert (Muster: `NewVorgangPage`).
- **Suche**: Server-Suchfelder mit `useDebouncedValue` (300 ms).
- **Aktionsmenüs**: seltene/destruktive Aktionen in `AktionsMenue`/`apple/PulldownMenu` (Tippfläche 44 px mobil),
  nicht neben den Seitentitel. Die häufigste Aktion einer Seite ist ein beschrifteter Primärbutton.
- **Office-Navigation**: aktiver Eintrag und Workspace folgen der Route (`office/navAktiv.ts`); Hilfslinks
  (Seitenleiste anpassen, Fehler melden, mobile Ansicht, Abmelden) liegen im Nutzermenü.

## Button-Rangfolge

Pro Ansicht genau eine gefüllte Primäraktion (`.btn-ap-primary`), alles andere sekundär (`.btn-ap`). Anlegen-Buttons nutzen überall `NEU_BUTTON_KLASSE` (`components/FormularFeld.tsx`). Auf Mobil ist bei Detailseiten mit klebender Leiste diese Leiste die Primäraktion, Aktionen in der Karte werden sekundär. Seltene und destruktive Aktionen („Vorgang löschen“) liegen im „…“-Menü, der Bestätigungsdialog bleibt.

## Office-Hierarchie

Office-Inhalt liegt auf `gbg`, Karten sind weiße Flächen ohne Schatten (`.office-flaechen`), Haarlinie nur in Tabellenzeilen und Kopfzeilen. Detail-Panels sind eine Fläche mit Abschnitten und Trennlinien (`.office-panel`); die Kopfzeile trägt „Zurück“, „Ganze Seite“ und das „…“-Menü. Jede Office-Seite nutzt `SeitenKopf` (gleiche Größe und linke Kante). Seitenleiste: Icons `label2`, nur der aktive Eintrag in Tint; die vier Kacheln zeigen immer eine Zahl (0 gedämpft); Hilfseinträge liegen im Nutzermenü unten links.

## Gesperrt und leer

Gesperrt: `GesperrtZustand` (`components/EmptyState.tsx`; Schloss, Erklärsatz, Zurück), genutzt von `KeinZugriff` und `FehlerZustand` (403). `EmptyState` hat einen `action`-Slot; leere Listen bieten die Anlegen-Aktion an, wenn das Recht da ist.

## Markenakzent „läuft gerade“

Token `live` / `live-text` / `live-bg` (Logo-Lime, in Hell abgedunkelt). Genau eine Rolle: „läuft gerade“ (`LaeuftPille`/`LaeuftPunkt`, `components/apple/LaeuftPille.tsx`). Immer mit Text „Läuft“ und pulsierendem Punkt (nur `motion-safe`), nie dekorativ, nie für Status. Kontrast: Text ≥5,0:1, Punkt ≥3,9:1 auf den Flächen.

## Was offen bleibt (ehrlich dokumentiert, siehe `docs/ui-redesign/REVIEW.md`)

- **Hartkodierte Farben nicht restlos entfernt**: kategoriale Icon-Töne und einzelne Randfälle (React-Flow-Handles, Modal-Scrim, `disabled:`-Varianten) bleiben auf Tailwind-Palettenfarben, siehe REVIEW.md Abschnitt 5
- **Cross-Browser** nur Chromium (kein WebKit), Tablet-Breiten nicht geprüft
- **Board-Knoten** (`office/boards/nodes/*`) behalten rohe Schriftgrößen und Versalien (Nutzerinhalt)
- **`RechteTab`-Select** bleibt nativ (Zustandsfarbe am Select)
- **Löschen im Menü**: Material, Angebot, Bestellung, Rechnung, Eingangsrechnung, Standort, Partner, Anlage, Dauerauftrag und das Auftrags-Panel zeigen „… löschen“ noch dauerhaft als roten Text statt im „…“-Menü
- **Office-Panels**: Aufträge- und Projekt-Detail nutzen `.office-panel` noch nicht
- **Seitenleisten-Kacheln** zählen clientseitig (max. 200, dann „200+“); ein Zähl-Endpoint fehlt
- **`e2e/portal-a11y.spec.ts`** läuft im lokalen Stack nicht durch (Seiten rendern unter dem Mock nicht, schon vor diesem Stand)
