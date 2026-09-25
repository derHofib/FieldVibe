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
eigener Web-Font mehr geladen. Beobachtete Größen-Stufen (kein benanntes
Scale-System, aus dem Code verifiziert):

| Größe | Verwendung |
|---|---|
| 17px | Listenzeilen-Text, Sheet-Titel, Formularfelder |
| 15px | `.field-ap` Eingabefeld-Text |
| 13px | Buttons, Sekundärtext, Segmented-Control |
| 11–13px | Meta-Text, Badges |
| 10px | Bottom-Nav-Tab-Label |

`tabular-nums` weiterhin für Zahlen in Tabellen/Kennzahl-Kacheln.

## Icons

Ausschließlich `lucide-react`, nie Emoji, nie frei im Text. Zwei parallele
Icon-Container mit unterschiedlicher Form — **bewusst nicht vereinheitlicht**,
siehe Begründung:

- **`SymbolKachel`** (`components/apple/SymbolKachel.tsx`) — die eigentliche
  Apple-HIG-Kachel: 29×29px, Radius 7, gefüllte Farbfläche
  (`--tile-*`), weißes Icon (`strokeWidth={2}`). Verwendung z. B. in
  `GroupedListRow`-Zeilen (Projekte-Tab, Mehr-Menü)
- **`IconBadge`**/`StatusBadge`** (`components/IconBadge.tsx`,
  `StatusBadge.tsx`) — älterer, aus der Industry-Ära übernommener
  Rahmen-Quadrat-Stil (`rounded-none`, Haarlinien-Rand statt Füllung),
  nur auf `--tone-*`-Token umgefärbt, **nicht** auf die Kachel-Form
  umgebaut. Ehrliche Einschränkung: dieses Muster ist noch nicht
  vollständig HIG-konvertiert, siehe „Was offen bleibt" unten

Bei neuen Bereichs-/Kategorie-Icons: `SymbolKachel` bevorzugen, wenn eine
gefüllte Kachel ins Layout passt (Listenzeile); `IconBadge`, wo eine
bestehende Seite das Rahmen-Muster schon konsequent nutzt.

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
.field-ap       /* Formularfeld: bg-card, border-sep, radius-ap-input (8px), 15px */
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
- Inaktive Segmented-Control-Beschriftung nutzt `text-label`, nicht
  `text-label2` — entspricht auch echten iOS-Segmented-Controls
  (Unterscheidung über Gewicht + Pille, nicht Textfarbe)

## Formulare

Lange Auswahllisten weiterhin als `SearchableSelect` (tippbare Combobox),
kein natives `<select>`. `.field-ap` für Standard-Eingabefelder (siehe
Bausteine oben); bei Feldern mit eigener Breite (`w-20` etc.) die
Klassen einzeln setzen statt `.field-ap` (setzt `width: 100%`).

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
  Lesespalte (`max-w-3xl`)

## Was offen bleibt (ehrlich dokumentiert, siehe `docs/ui-redesign/REVIEW.md`)

- **Hartkodierte Farben nicht restlos entfernt**: kategoriale Icon-Töne
  (sky/violet/…) und einzelne Randfälle (React-Flow-Handles, Modal-
  Scrim, `disabled:`-Varianten) bleiben bewusst auf Tailwind-
  Palettenfarben statt Design-Token, siehe REVIEW.md Abschnitt 5
- **`IconBadge`/`StatusBadge`** noch nicht auf die `SymbolKachel`-Form
  umgebaut (Rahmen-Quadrat statt gefüllte Kachel), siehe Icons-Abschnitt
- **Cross-Browser-Testabdeckung** nur Chromium (kein WebKit in dieser
  Entwicklungsumgebung installiert)
