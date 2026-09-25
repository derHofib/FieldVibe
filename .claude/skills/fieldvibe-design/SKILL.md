---
name: fieldvibe-design
description: >
  Nachschlagewerk für das visuelle Design-System von FieldVibe (Apple Human
  Interface Guidelines: Systemschrift, --tint-Akzentfarbe, generöse Radien,
  Flächen statt Haarlinien als Gliederungsmittel). Icons, Farben/Tones,
  Karten-/Listen-Rezepte, Buttons, Dark Mode, Layout, Barrierefreiheit --
  ausschließlich für frontend/src in diesem Repo (SocialCRM/FieldVibe). Vor
  JEDER neuen UI-Komponente, Seite, Karte, Button, Formularfeld oder
  Statusfarbe in diesem Frontend zuerst hier nachsehen, damit bestehende
  Muster wiederverwendet statt neu erfunden werden -- auch wenn nicht
  explizit nach "Design" gefragt wird, sondern nur "baue mir eine Seite für
  X" oder "füge einen Button/eine Karte für Y hinzu". Auch nützlich bei
  Fragen nach dem FieldVibe-Styleguide, der Icon-Farbe für einen neuen
  Bereich, Kontrast-/Barrierefreiheits-Konventionen, oder ob Apple-HIG-Token
  bzw. Feld-App/Office-Konventionen greifen. Kein Ersatz für den separaten
  "design"-Skill (der baut Mockup-Canvases) -- dieser Skill ist reine
  Referenz für existierenden Code.
---

# FieldVibe Design-System (frontend/src) -- Apple HIG

Dieses Dokument fasst zusammen, wie FieldVibe tatsächlich aussieht -- nicht
wie es aussehen sollte. Alle Angaben sind aus dem Code verifiziert (Datei:Zeile
wo hilfreich). Ergänzend, aber kompakter: `docs/DESIGN.md`. Bei Widerspruch
zwischen den beiden gilt dieses Dokument, weil es näher am aktuellen Code
liegt -- im Zweifel trotzdem kurz den Code selbst gegenchecken, Konventionen
driften.

Die App wurde app-weit von einem quadratisch-Haarlinien-Design ("Industry",
Blaupausen-Optik) auf Apple Human Interface Guidelines umgestellt:
Systemschrift statt Barlow, generöse Radien statt `rounded-none`, eine
einzige Akzentfarbe `--tint` (Apple `systemBlue`) statt Marken-Grau, Flächen
(`--cell`/`--card`) statt Haarlinien als primäres Gliederungsmittel. Diese
Migration ist inhaltlich abgeschlossen für alle vier Frontends (Feld-App,
Office, Super-Admin, Kundenportal); ein Teil der hartkodierten Tailwind-
Palettenfarben (kategoriale Icon-Töne, einzelne Randfälle) ist bewusst noch
nicht auf Design-Token umgestellt -- siehe `docs/ui-redesign/REVIEW.md`
Abschnitt 5 für den genauen, ehrlichen Stand, bevor etwas davon als neuer
Bug gemeldet wird.

## Checkliste, bevor du etwas Neues baust

1. **Status oder Kategorie?** Status (Vorgang/Rechnung/Angebot-Zustand) läuft
   **immer** über die sechs `StatusKey`-Token (§8), nie über eine eigene
   Farbwahl. Kategorie (Bereichs-Icon, rein illustrativ) läuft über
   `--tone-*`/`--tile-*` (§1) -- die beiden Systeme nie mischen.
2. **Welcher Icon-Container?** `SymbolKachel` (gefüllte Kachel, bevorzugt
   für neue Listenzeilen) oder `IconBadge` (Rahmen-Quadrat, wo eine
   bestehende Seite das Muster schon konsequent nutzt)? Siehe §1.
3. **Welches Karten-/Listen-Rezept?** `.card-ap` (Feld-App-Standard),
   `GroupedList`/`GroupedListRow` (iOS-Einstellungen-Liste), Office-`Karte`
   (`office/OfficeUi.tsx`), oder `Sheet` (Formular/Dialog)? Siehe §3.
4. **Welche Button-Variante?** `.btn-ap`/`-primary`/`-toolbar`/
   `-capsule(-primary|-secondary)`, siehe §6 -- nicht neu erfinden.
5. **`.btn-touch` nötig?** Ja in der Feld-App (48×48px-Mindestziel), nein im
   Office-Desktop-Layout (dort kein Touch-Ziel, keine PWA).
6. **Dark-Mode-Gegenstück nicht vergessen**: Bei `--color-*`-Token passiert
   das automatisch (Werte sind unter `.dark` neu definiert, kein
   `dark:`-Präfix pro Klasse nötig).
7. **Text oder Fläche mit `--tint`?** `tint` selbst nur für Icons/Ränder/
   Indikatoren. Echter Text: `text-tint-text`. Weißer Text auf Tint-Fläche:
   `bg-tint-solid`/`.btn-ap-primary`. Sonst unterschreitet es im
   Dunkel-Modus 4.5:1 Kontrast (axe-core, Phase D) -- siehe §2 und §10.
8. **Genau ein `<h1>` pro Seite**, innerhalb eines Landmarks (`<main>`).
   Feld-App-Seiten brauchen dafür i. d. R. nichts Zusätzliches (kommt aus
   `FeldLayout.tsx`), Office/Super-Admin-Seiten über `SeitenKopf`/den
   Layout-Header. Siehe §10.
9. **Icon**: nur lucide-react, i. d. R. `strokeWidth={1.5}` (`IconBadge`)
   oder `{2}` (`SymbolKachel`), nie Emoji, nie frei im Text.
10. **Radius ist hier Standard, nicht Ausnahme** -- anders als im alten
    Industry-System kein `rounded-none` mehr per Default. Radius-Skala
    siehe §2.

---

## 1. Icons

Einzige Icon-Quelle: **lucide-react**. Nie Emoji. Zwei parallele Icon-
Container -- bewusst nicht vereinheitlicht, siehe Begründung:

### SymbolKachel (bevorzugt für neue Listenzeilen)

`frontend/src/components/apple/SymbolKachel.tsx`: die eigentliche
Apple-HIG-Kachel -- 29×29px, Radius 7 (`rounded-[7px]`), gefüllte Farbfläche,
weißes Icon:

```tsx
<SymbolKachel icon={Folder} farbe="indigo" />
```

Props: `icon: LucideIcon`, `farbe: KachelFarbe`, `groesse?: number` (Default
29, Icon-Größe skaliert automatisch mit `groesse * 0.57`). Icon fest
`strokeWidth={2}`, `text-white`.

```ts
FARB_KLASSE = {
  blue: "bg-tile-blue",     // #007aff
  red: "bg-tile-red",       // #ff3b30
  green: "bg-tile-green",   // #34c759
  orange: "bg-tile-orange", // #ff9500
  indigo: "bg-tile-indigo", // #5856d6
  gray: "bg-tile-gray",     // #8e8e93
};
```

Fest in beiden Modi identisch (Ausnahme vom "keine Farbe außer Status/
Kategorie"-Grundsatz -- Symbol-Kacheln sind rein illustrativ).

### IconBadge / StatusBadge (älteres Muster, noch verbreitet)

`frontend/src/components/IconBadge.tsx`: aus der Industry-Ära übernommenes
Rahmen-Quadrat -- Rahmenfarbe + Icon in Ton-Farbe, Hintergrund transparent,
`rounded-none`. **Nicht** auf die Kachel-Form umgebaut (ehrliche
Einschränkung, siehe REVIEW.md):

```tsx
<IconBadge icon={CalendarClock} tone="amber" size="md" active={isActive} />
```

Props: `icon: LucideIcon`, `tone: IconTone`, `size?: "sm" | "md"` (Default
`"md"`), `active?: boolean` (Default `true`, bei `false` neutral-grau statt
Farbe -- nur das ausgewählte Element zeigt Farbe).

```ts
export type IconTone = "sky" | "violet" | "amber" | "rose" | "emerald"
  | "indigo" | "cyan" | "slate" | "teal";

TONE_BADGE = {
  sky: "border-tone-sky text-tone-sky",
  violet: "border-tone-violet text-tone-violet",
  amber: "border-tone-amber text-tone-amber",
  rose: "border-tone-rose text-tone-rose",
  emerald: "border-tone-emerald text-tone-emerald",
  indigo: "border-tone-indigo text-tone-indigo",
  cyan: "border-tone-cyan text-tone-cyan",
  slate: "border-sep text-label",       // neutral, kein eigener Ton
  teal: "border-tone-teal text-tone-teal",
};
SIZE_BOX = { sm: "h-7 w-7 rounded-none", md: "h-9 w-9 rounded-none" };
SIZE_ICON = { sm: 15, md: 18 };  // strokeWidth={1.5}
MUTED = "border-sep text-label3";  // active=false
```

`TONE_ROW_ACTIVE` (gleiche Datei): weicheres Pendant für aktive Listenzeilen
(Rahmen + leichte 10%-Flächenfarbe statt nur Rahmen), z. B.
`"border-tone-sky bg-tone-sky/10 text-tone-sky"`.

`StatusBadge.tsx` dupliziert dieselbe Palette lokal als `TONE_PILL`
(gleiche Klassen wie `TONE_BADGE`, nicht aus `IconBadge.tsx` exportiert) für
eine Pillen-Variante: `<StatusBadge label="..." tone="cyan" />`.

**Kategorien-Zuordnung** (welcher Ton für welchen Bereich): Single Source of
Truth bleibt `frontend/src/config/navSeiten.ts` (`NAV_SEITEN`, Feld `tone:
IconTone` je Eintrag) -- speist sowohl die Office-Seitenleiste
(`office/OfficeLayout.tsx`) als auch den "Mehr"-Tab der Feld-App
(`pages/feld/MehrPage.tsx`), unverändert aus der Vorversion übernommen. Für
Icons **außerhalb** dieser beiden Stellen (Listenzeilen, Detailseiten-
Header) gibt es keine zentrale Tabelle -- dort zuerst prüfen, welchen Ton
verwandte/benachbarte Seiten schon nutzen, bevor ein neuer gewählt wird.

**--tone-\* Token** (`index.css`, fest in beiden Modi, Apple System Colors):

| Token | Hex |
|---|---|
| `tone-sky` | `#007aff` |
| `tone-violet` | `#af52de` |
| `tone-amber` | `#ff9500` |
| `tone-rose` | `#ff375f` |
| `tone-emerald` | `#34c759` |
| `tone-indigo` | `#5856d6` |
| `tone-cyan` | `#32ade6` |
| `tone-slate` | `#8e8e93` |
| `tone-teal` | `#30b0c7` |

---

## 2. Farb-/Typografie-Basis

**Kein** `tailwind.config.js` -- Tailwind v4, komplett CSS-basiert über
`@theme` in `frontend/src/index.css`.

### Farbtoken

| Token | Rolle |
|---|---|
| `gbg` | Äußerster Seitenhintergrund |
| `cell` | Zeilen-/Listenflächen (`GroupedList`) |
| `win` | Fenster-/Panel-Fläche (Office-Inspektor-Spalte) |
| `card` | Karten-/Formularfläche |
| `insp` | Office-Inspektor-Hintergrund |
| `side` / `bar` / `menu` | Seitenleiste / Toolbar / Dropdown-Menü (teiltransparent, `backdrop-blur`-tauglich) |
| `fill` / `fill2` | Neutrale Füllfläche: dezent (12/24% grau) / kräftiger (20/34%) |
| `thumb` | Aktiver Segmented-Control-Knopf |
| `label` / `label2` / `label3` | Text: Primär / Sekundär / Tertiär |
| `sep` / `sepstrong` | Trennlinie: Standard / kräftiger |
| `tint` | Akzentfarbe (`systemBlue`, hell `#0071e3` / dunkel `#0a84ff`) -- **nur** Icons/Ränder/Indikatoren |
| `tint-text` | Text-/Link-Variante (hell `#0068cc`, dunkel `#6ab1ff` -- derselbe Ton wie `st-neu-text`) |
| `tint-solid` | Button-Flächen-Variante für weißen Text (hell = `tint`, dunkel `#0a6ad1`) |
| `tintbg` | Dezente Akzent-Fläche |
| `st-{key}` / `-bg` / `-dot` | Status-Token, siehe §8 |
| `tone-*` | Kategoriale Icon-Töne, siehe §1 |
| `tile-*` | `SymbolKachel`-Farben, siehe §1 |
| `mono-grad-1/2` | Monogramm-Verlauf (`Monogramm.tsx`) |
| `switch-on` | `#34c759`, Aktivfarbe `Switch.tsx` |

Definiert in `index.css`: helle Werte im `@theme`-Block, dunkle Werte in
einem `.dark { }`-Block direkt darunter. Tailwind v4 löst `@theme`-Werte als
normale CSS-Variablen auf -- ein Re-Scope unter `.dark` wirkt automatisch
auf jede Utility-Klasse, die dieselbe Variable referenziert -- **kein**
`dark:`-Präfix pro Klasse nötig.

**Warum `tint-text`/`tint-solid` eigene Token sind** (Phase D, axe-core-
Befund): reines `tint` als Text auf `--card` bzw. als Fläche unter weißem
Text unterschritt im Dunkel-Modus 4.5:1. Text braucht dort **heller**,
Fläche-unter-weißem-Text braucht **dunkler** -- gegensätzliche Richtungen,
deshalb zwei Token statt eines geänderten `tint`. `tint` selbst bleibt für
Icons/Ränder unverändert (WCAG 1.4.11 verlangt dort nur 3:1). Betroffene
Rezepte: `.btn-ap-primary`, `.btn-ap-capsule-primary` (`background: var(
--tint-solid)`), Wortmarke/Links/BottomNav-Label (`text-tint-text`). Bei
neuem Code mit `bg-tint`/`text-tint` **und** `text-white`/Fließtext in
derselben Zeile: `bg-tint-solid`/`text-tint-text` verwenden, nicht `tint`
direkt.

### Typografie

- **Systemschrift** (`--font-sans: -apple-system, BlinkMacSystemFont, 'SF
  Pro Text', 'SF Pro Display', 'Helvetica Neue', sans-serif`) -- kein
  eigener Web-Font mehr geladen, kein `<link>` in `index.html`
- Beobachtete Größen-Stufen: 17px (Listenzeilen, Sheet-Titel,
  Formularfelder), 15px (`.field-ap`-Text), 13px (Buttons, Segmented-
  Control), 11–13px (Meta-Text/Badges), 10px (Bottom-Nav-Tab-Label)
- `tabular-nums` für Zahlen in Tabellen/Kennzahl-Kacheln

### Radius-Skala (`index.css`)

```
--radius-ap-sm: 7px      /* .btn-ap-primary, .btn-ap-toolbar */
--radius-ap-input: 8px   /* .field-ap */
--radius-ap-md: 10px
--radius-ap-card: 12px   /* .card-ap, GroupedList, Sheet (Desktop) */
--radius-ap-tile: 14px
--radius-ap-pill: 999px  /* .btn-ap-capsule*, StatusPille, FilterChip */
```

Radius ist hier **Standard**, nicht Ausnahme -- anders als das alte
`rounded-none`-Industry-Prinzip. Echte Kreisformen (Avatare, Zähler-Badges,
`AbhakKreis`, `Switch`-Knopf) bleiben `rounded-full`, Whiteboard-Sticky-
Notes (Nutzerinhalt) unangetastet.

### Custom Utility-Klassen (`index.css`)

```css
.card-ap                 /* bg-card, 0.5px border-sep, radius-ap-card, shadow-card */
.btn-ap                  /* Basis-Button: border-sepstrong, bg-card, 13px */
.btn-ap-primary          /* background: tint-solid, color: #fff, radius-ap-sm */
.btn-ap-toolbar          /* 28x28px Icon-only, transparent, hover: fill */
.btn-ap-capsule          /* Basis: 44px hoch, radius-ap-pill, 17px */
.btn-ap-capsule-primary  /* background: tint-solid */
.btn-ap-capsule-secondary /* background: fill, color: tint-text */
.field-ap                /* Formularfeld: bg-card, border-sep, radius-ap-input, 15px, width:100% */
```

**Cascade-Layer-Falle**: `.card-ap`/`.btn-ap` setzen Rand/Schatten als
plain CSS außerhalb jedes `@layer` -- das gewinnt **immer** gegen Tailwind-
Utilities (`border-*`/`ring-*`, im `utilities`-Layer). Eine Farb-/Rand-
Überschreibung auf diesen Klassen **muss** per Inline-`style` erfolgen,
sonst wird sie stillschweigend ignoriert. Beispiel (`office/vorgaenge/
VorgaengeRaster.tsx`): Auswahl-/Fokus-Ring auf einer `Karte` geht über
`style={{ borderColor: ..., boxShadow: ... }}`, nicht über `border-tint`.

---

## 3. Karten-/Listen-Rezepte

**Feld-App-Karte** (Default für freistehende Boxen):
```
.card-ap
```
Ersetzt das alte `border border-ind-line bg-ind-bg p-3`-Rezept. Trägt
Fläche + Rand + Radius + Schatten automatisch, kein manuelles Kombinieren
von Utility-Klassen mehr nötig.

**Gruppierte Liste** (iOS-Einstellungen-Stil, `components/apple/
GroupedList.tsx`) -- bevorzugt für Listen mit mehreren gleichartigen
Zeilen (Profil-Werte, Einstellungen, Mehr-Menü):
```tsx
<GroupedList>
  <GroupedListRow onClick={...} navigierbar last={i === n - 1}>
    <SymbolKachel icon={Folder} farbe="indigo" />
    <div className="min-w-0">
      <p className="truncate text-[17px] text-label">{titel}</p>
    </div>
  </GroupedListRow>
</GroupedList>
```
`GroupedListValueRow` für einfache Label/Wert-Paare. Trennlinie ist absolut
positioniert (beginnt bei `left-4`, nicht am Zellenrand) statt per
`border` -- `last` unterdrückt sie für die letzte Zeile.

**Sheet** (`components/apple/Sheet.tsx`) -- Formulare/Dialoge statt
eigener Vollbild-Route:
```tsx
<Sheet offen={offen} onClose={...} titel="Neuer Auftrag"
  rechts={<button type="submit" form={FORM_ID}>Anlegen</button>}>
  <form id={FORM_ID} ...>...</form>
</Sheet>
```
Mobil: von unten mit Griff (`h-[5px] w-9 rounded-full bg-label3`). Ab
768px (`md:`): zentrierter 540px-Dialog. Eine Implementierung für beides,
Umschaltung rein per CSS-Breakpoint. `links`/`rechts` sind die
Kopfzeilen-Aktionen (z. B. Abbrechen/Weiter) -- das `form`-Attribut auf
dem Submit-Button verbindet ihn mit dem `<form>` außerhalb, ohne dass der
Button selbst im DOM-Formular liegen muss.

**Office-Desktop** -- `Karte`/`KennzahlKarte`/`TabellenRahmen`/
`SeitenKopf`/`AnsichtUmschalter` in `frontend/src/office/OfficeUi.tsx`:
```tsx
<SeitenKopf titel="Vorgänge" anzahl={vorgaenge.length}>
  <AnsichtUmschalter wert={ansicht} optionen={...} onWechsel={...} />
</SeitenKopf>
<Karte className="p-4">...</Karte>
```
`SeitenKopf` rendert ein echtes `<h1>` (Pflicht, siehe §10). Änderung an
`Karte` wirkt auf alle Office-Seiten, die sie verwenden.

**Whiteboard/Board-Feature** (`office/boards/nodes/*`, `pages/feld/
boards/*`): behält bewusst Rundung/Schatten/frei wählbare Farbe -- das ist
Nutzerinhalt (Sticky-Notes, Rahmen, Vorgangs-Karten auf einer Leinwand),
kein Seiten-Chrome. Nur die Bedienelemente drumherum folgen dem
Apple-Rezept.

**Faustregel:** freistehende Box → `.card-ap`. Liste gleichartiger Zeilen
→ `GroupedList`. Formular/Dialog → `Sheet`. Office → `OfficeUi.tsx`-
Bausteine. Whiteboard-Inhalt → unangetastet.

---

## 4. Dark Mode

Pflicht für **jede** Seite, kein Opt-out. Umschaltung über `--color-*`-
Token automatisch (siehe §2) -- kein `dark:`-Pendant pro Klasse nötig.

**Drei-Wege** statt binär (anders als die Vorversion): hell / dunkel /
automatisch. `frontend/src/context/ThemeContext.tsx`, `localStorage`-Key
`ui.appearance`. Im Automatisch-Fall folgt die App live
`prefers-color-scheme`. `.dark`-Klasse auf `<html>` (`@custom-variant dark
(&:is(.dark *))` in `index.css`) -- **nicht** über `data-theme`.
`ThemeToggle.tsx` (`.btn-ap-toolbar`) in allen vier Layout-Shells
eingebunden.

---

## 5. Layout

**Feld-App** (`frontend/src/components/FeldLayout.tsx`, mobil, PWA):
- `min-h-screen bg-gbg text-label`
- `<main className="mx-auto max-w-2xl px-3 py-4">` -- schmale mobile Spalte
- **Kein persistenter Marken-Header mehr** -- jede Seite trägt ihre eigene
  `AbschnittskopfA`-Überschrift (`<h2>`). Für Barrierefreiheit trägt der
  Rahmen zusätzlich einen unsichtbaren `<h1 className="sr-only">`
  innerhalb von `<main>` (routenabhängiger Text über `useSeitentitel()`,
  Fallback `"FieldVibe"`) -- **muss** innerhalb eines Landmarks liegen,
  sonst meldet axe-core zusätzlich "region" (Phase D, siehe §10)
- Impersonation-Banner, Offline-Hinweis, schmaler Sync-Ausstehend-Streifen
  vor `<main>`
- `BottomNav.tsx`: vier feste Tabs (Heute/Aufträge/Projekte/Mehr), deren
  `TABS`-Liste direkt in der Komponente steht (eigene, kleinere Liste als
  `navSeiten.ts` -- die speist nur den Inhalt des "Mehr"-Tabs, siehe §1),
  kein FAB, kein wischbarer Zusatzbereich -- Suche/Darstellung/
  Einstellungen/Abmelden leben vollständig im "Mehr"-Tab (`MehrPage.tsx`).
  Aktiver Tab:
  Icon behält `text-tint` (Icon, 3:1 reicht), das 10px-Label bekommt
  zusätzlich `text-tint-text` (Text, braucht 4.5:1)

**Office-Desktop** (`frontend/src/office/OfficeLayout.tsx`):
- feste Sidebar `w-64` (einklappbar `w-16` über `eingeklappt`-State)
- Content-Spalte trägt eigenen `<h1>` über `SeitenKopf` (siehe §3) --
  **kein** zusätzlicher Landmark-Header nötig, anders als Feld-App
- Kein `.btn-touch`, keine PWA, kein Service Worker

**Super-Admin-Shell** (`frontend/src/components/Layout.tsx`):
- eigene Sidebar-Instanz, eigene `NAV_ITEMS`-Liste, Hexagon-Logo +
  Wortmarke (`Field<span className="text-tint-text">Vibe</span>` --
  `text-tint-text`, nicht `text-tint`, siehe §2/§10)
- Header-Titel jetzt als `<h1 className="truncate text-sm font-semibold
  text-label">{seitentitel}</h1>` (vorher `<span>`, Phase D)
- Ein echter `super_admin` sieht dieses Dashboard **immer**, auch auf
  `office.<domain>` (`App.tsx`, `isPlatformAdmin`-Weiche, Zeile ~98/124/
  128) -- nur beim Impersonieren eines Mandanten-Users fällt er in die
  Office-Shell. Das ist bestehendes Anwendungsverhalten, **nicht** Teil
  des UI-Redesigns, und kein Bug, falls ein Super-Admin-Account
  scheinbar "immer" das Plattform-Menü statt der Office-Oberfläche sieht

**Kundenportal** (`frontend/src/components/PortalLayout.tsx`,
`/portal/*`): eigener, schlanker Rahmen, folgt denselben Token/Bausteinen.

**Hostname-Weiche** (`office/hostname.ts`, unverändert durch das
Redesign): `istOfficeHost()` prüft `window.location.hostname.startsWith(
"office.")`. Lokal ohne Subdomain: `?office=1` schaltet die Office-
Oberfläche für die Sitzung frei (`sessionStorage`), `?office=0` wieder ab.

Alle vier Frontends teilen sich dieselben Token/Bausteine (`index.css`,
`components/apple/*`) -- eine Änderung wirkt auf alle gleichzeitig.

---

## 6. Buttons

**Primary**:
```
btn-touch btn-ap btn-ap-primary
```
Füllung `var(--tint-solid)`, weißer Text, `radius-ap-sm`. **Nicht**
`background: var(--tint)` direkt verwenden -- siehe §2/§10 (Kontrast).

**Sekundär** (Standard-Button ohne Füllung):
```
btn-touch btn-ap
```
`border-sepstrong`, `bg-card`, Hover `bg-fill`.

**Icon-only (Toolbar)**:
```
btn-ap-toolbar
```
28×28px, transparent, Hover `bg-fill`. Für Office-Toolbars (`AnsichtUmschalter`
daneben) und Sheet-Kopfzeilen.

**Capsule (prominente CTA, 44px)**:
```
btn-ap-capsule btn-ap-capsule-primary    /* gefüllt, tint-solid */
btn-ap-capsule btn-ap-capsule-secondary  /* bg-fill, Text tint-text */
```

**Destructive** -- weiterhin Ausnahme mit echter Semantikfarbe statt
Akzent, über die Status-Token (§8): `text-st-fehlt hover:bg-st-fehlt-bg`.

**Segmented-Control** (`components/apple/SegmentedControl.tsx`, Office-
Pendant `AnsichtUmschalter` in `OfficeUi.tsx`):
```
Wrapper: inline-flex rounded-[9px] bg-fill p-0.5
aktiv:   bg-thumb font-semibold text-label shadow-[0_1px_3px_rgba(0,0,0,.14)]
inaktiv: font-medium text-label   /* NICHT text-label2, siehe §10 */
```
Unterscheidung aktiv/inaktiv über Gewicht + Pille, nicht über Textfarbe --
entspricht echten iOS-Segmented-Controls. `text-label2` im inaktiven
Zustand unterschritt 4.5:1 Kontrast (axe-core, Phase D) und wurde deshalb
in beiden Implementierungen auf `text-label` korrigiert.

`disabled:opacity-50` ist der durchgängige Deaktiviert-Zustand;
`.btn-ap-primary:disabled`/`.field-ap`-Pendants haben zusätzlich eigene
CSS-Fallbacks (`background: var(--fill2); color: var(--label3)`).

---

## 7. Formulare

Lange Auswahllisten (z. B. Material-Katalog) weiterhin als
`SearchableSelect` (`frontend/src/components/SearchableSelect.tsx`), nie
natives `<select>`.

Input-Rezept:
```
field-ap   /* bg-card, border-sep, radius-ap-input (8px), 15px, width:100% */
```
Fokus: `outline: 2px solid var(--tint); border-color: var(--tint)`
(`.field-ap:focus-visible`). Für Felder, die **nicht** die volle Breite
haben sollen (`w-20`, `flex-1` neben einem Button): `.field-ap` nicht
verwenden (setzt `width: 100%` unlayered, gewinnt gegen eine Tailwind-
Breiten-Utility) -- stattdessen Klassen einzeln setzen: `border border-sep
bg-card px-2.5 py-1.5 text-sm text-label rounded-[var(--radius-ap-input)]`
+ gewünschte Breite.

---

## 8. Status-/Semantikfarben

Zentrale Quelle: `frontend/src/components/apple/status.ts`. **Nie** direkt
Tailwind-Farben für Status verwenden, **immer** über
`vorgangStatusZuToken()` + `StatusPille`/`StatusKreis`/`STATUS_PILLE_KLASSE`
gehen -- lokale Kopien liefen in der Vorversion mehrfach lautlos
auseinander (`KundeProfilePage`, `AnlageProfilePage`,
`DauerauftragDetailPage`, `StandortDetailPage` hatten je eine eigene,
fehlerhafte `STATUS_BADGE`-Kopie, in der `wartet_kunde` versehentlich das
Token von `in_arbeit` teilte -- beim Redesign gefunden und korrigiert).

```ts
export type StatusKey = "neu" | "geplant" | "arbeit" | "fehlt" | "erledigt" | "wartet";
```

| Vorgang.status | Status-Token | Farbe |
|---|---|---|
| `neu` | `neu` | Blau |
| `geplant` | `geplant` | Grau |
| `in_arbeit` | `arbeit` | Orange |
| `wartet_kunde` | `wartet` | Violett |
| `abgeschlossen` | `erledigt` | Grün |
| `abgerechnet` | `erledigt` (Label „Abgerechnet") | Grün |
| `storniert` | `geplant` (Titel durchgestrichen) | Grau |
| Mangel-Status | `fehlt` | Rot |

Jedes Token hat drei CSS-Varianten (`index.css`, alle mit eigenem, für
4.5:1 abgestimmtem Text-Ton -- **nicht** Apples reine Systemfarbe, die
reicht als Fließtext nicht):
```
st-{key}        /* Text (abgedunkelt/aufgehellt für Kontrast) */
st-{key}-bg     /* Pillen-Hintergrund, halbtransparent */
st-{key}-dot    /* kräftigerer Punkt/Indikator-Ton */
```

Verwendung:
```tsx
<StatusPille status={vorgangStatusZuToken(v.status)} label={STATUS_LABEL[status]} />
```
`StatusPille` (`components/apple/StatusPille.tsx`) rendert **immer** Punkt
**und** Text -- Farbe transportiert Status nie allein.

`statusDotFarbe(status)` liest den aktuell geltenden Hex-Wert eines Tokens
zur Laufzeit aus den CSS-Custom-Properties -- für imperative APIs
(Mapbox-GL-Pins), die keine Tailwind-Klassen lesen können.

Überfällig/Dringlichkeit (kein Teil einer Status-Map, steht für sich):
`text-st-fehlt`/`bg-st-fehlt-bg`.

---

## 9. Spacing-Rhythmus

Unverändert durch das Redesign, Basis-Einheit zwischen `1`-`4` (0.25rem–1rem):

| Klasse | Verwendung |
|---|---|
| `gap-2` / `space-y-2` (0.5rem) | Standard für zusammengehörige Elemente |
| `space-y-4` (1rem) | Standard für eigenständige Abschnitte |
| `p-3` | Karten-Innenabstand, kompakte Listenkarten |
| `p-4` | Karten-Innenabstand, Formular-/Detailkarten |
| `p-6` / `p-8` | praktisch nie, außer Leer-/Ladezustände ganzer Seiten |

---

## 10. Barrierefreiheit (Phase D: Playwright + axe-core)

`frontend/playwright.config.ts` + `frontend/e2e/apple-redesign.spec.ts`:
Login + Screenshot + axe-core-Prüfung für die drei Referenz-Shells
(Super-Admin, Feld-App, Office) je hell/dunkel, gegen einen echten
lokalen Dev-Stack (Postgres nativ, `moto_server` als MinIO-Ersatz, echte
Seed-User). **Nur Chromium** -- kein WebKit in der Entwicklungs-Sandbox
installiert, siehe `docs/ui-redesign/REVIEW.md`.

Aus den gefundenen und behobenen Befunden verbindlich abgeleitete Regeln
für neuen Code:

1. **Genau ein `<h1>` pro Seite, innerhalb eines Landmarks.** Ein `<h1>`
   direkt als Geschwister von `<main>` (statt darin) lässt axe-core
   zusätzlich "region: All page content should be contained by
   landmarks" melden.
2. **`tint` nie für echten Text oder für Flächen unter weißem Text.**
   `text-tint-text` für Links/Labels, `bg-tint-solid`/`.btn-ap-primary`
   für gefüllte Buttons mit weißem Text. `tint` bleibt Icons/Rändern/
   Indikatoren vorbehalten (dort reichen 3:1, WCAG 1.4.11).
3. **Inaktive Segmented-Control-Beschriftung: `text-label`, nicht
   `text-label2`.** Siehe §6.
4. Vor jedem Bulk-Sed über Farbklassen: Zahlen-Alternierungen im Regex
   **immer** mit `\b` abschließen (`(50|100|200)\b`, nicht `(50|100|200)`)
   -- ohne Wortgrenze matcht `50` als Präfix von `500` und verstümmelt
   Klassen. Ein solcher Vorfall ist in dieser Session passiert, wurde
   vorwärts gefixt (kein History-Rewrite) und ist in REVIEW.md Abschnitt 6
   vollständig dokumentiert -- als Warnung für künftige Bulk-Ersetzungen,
   nicht nur als Historie.

Vor dem Committen größerer Farb-/Layout-Änderungen: `cd frontend && npx
playwright test` laufen lassen (Dev-Server + Backend müssen laufen) und
auf `0 Verstoesse` in allen sechs Szenarien prüfen.
