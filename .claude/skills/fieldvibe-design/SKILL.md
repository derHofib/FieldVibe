---
name: fieldvibe-design
description: >
  Nachschlagewerk für das visuelle Design-System von FieldVibe ("Industry" --
  Blaupausen-Optik: Haarlinien statt Schatten, quadratisch statt rund,
  Barlow/Barlow Condensed, --color-ind-*-Farbtoken). Icons, Farben/Tones,
  Karten-Rezepte, Buttons, Dark Mode, Layout, Spacing -- ausschließlich für
  frontend/src in diesem Repo (SocialCRM/FieldVibe). Vor JEDER neuen UI-
  Komponente, Seite, Karte, Button, Formularfeld oder Statusfarbe in diesem
  Frontend zuerst hier nachsehen, damit bestehende Muster wiederverwendet
  statt neu erfunden werden -- auch wenn nicht explizit nach "Design"
  gefragt wird, sondern nur "baue mir eine Seite für X" oder "füge einen
  Button/eine Karte für Y hinzu". Auch nützlich bei Fragen nach dem
  FieldVibe-Styleguide, der Icon-Farbe für einen neuen Bereich, oder ob
  Industry-Token bzw. Feld-App/Office-Konventionen greifen. Kein Ersatz für
  den separaten "design"-Skill (der baut Mockup-Canvases) -- dieser Skill
  ist reine Referenz für existierenden Code.
---

# FieldVibe Design-System (frontend/src) -- "Industry"

Dieses Dokument fasst zusammen, wie FieldVibe tatsächlich aussieht -- nicht
wie es aussehen sollte. Alle Angaben sind aus dem Code verifiziert (Datei:Zeile
wo hilfreich). Ergänzend, aber kompakter: `docs/DESIGN.md`. Bei Widerspruch
zwischen den beiden gilt dieses Dokument, weil es näher am aktuellen Code
liegt -- im Zweifel trotzdem kurz den Code selbst gegenchecken, Konventionen
driften.

Die App wurde app-weit von einem pastellfarbenen, abgerundeten Look
("Claymorphism"/Neumorphismus) auf ein Blaupausen-Design ("Industry")
umgestellt: Haarlinien-Rahmen statt Schatten, quadratische Kanten statt
Rundungen, Barlow/Barlow Condensed statt System-Font, `--color-ind-*`-
Farbtoken statt direkter `slate`/`stone`-Klassen. Diese Migration ist
inhaltlich abgeschlossen (Feld-App, Office, Super-Admin, Kundenportal),
vereinzelte seiteneigene Pillen/Chips können noch Restbestände zeigen --
im Zweifel Code gegenchecken statt dieses Dokument als absolute Wahrheit
zu nehmen.

## Checkliste, bevor du etwas Neues baust

1. **Tone/Statusfarbe**: Passt einer der 8 IconBadge-Tones oder eine der
   bestehenden Statusfarben fachlich? Ein Tone deckt eine ganze Bereichs-
   "Familie" ab, nicht einzelne Seiten -- neue Seite zuerst einer Familie
   zuordnen, bevor ein neuer Tone erwogen wird.
2. **Welches Karten-Rezept?** Haarlinien-Karte (Feld-App-Standard),
   Office-`Karte`, `Blueprint` (Passermarken für Hero-Karten), oder
   `.card-soft` (nur Feed-Story-Chips, Restbestand)? Siehe §3.
3. **Welche Button-Variante?** `.btn-industry-primary`/`-secondary`/
   `-ghost`/`-icon`, siehe §6 -- nicht neu erfinden.
4. **`.btn-touch` nötig?** Ja in der Feld-App (48×48px-Mindestziel), nein im
   Office-Desktop-Layout (dort kein Touch-Ziel, keine PWA).
5. **Dark-Mode-Gegenstück nicht vergessen**: Bei `--color-ind-*`-Token
   passiert das automatisch (Werte sind unter `.dark` neu definiert, kein
   `dark:`-Präfix pro Klasse nötig). Bei echten Semantikfarben (Status,
   Warnung) weiterhin `dark:border-{farbe}-600 dark:text-{farbe}-300` o.ä.
   explizit ergänzen.
6. **Icon**: nur lucide-react, `strokeWidth={1.5}`, i. d. R. über `IconBadge`
   (Ausnahme: Office-/Super-Admin-Sidebar, siehe §1), nie Emoji, nie frei
   im Text.
7. **Quadratisch, nicht rund**: kein `rounded-lg`/`rounded-md`/`rounded-xl`
   auf Karten/Buttons/Inputs -- `rounded-none` (Standard, meist implizit
   durch Weglassen der Klasse) oder gar keine Radius-Klasse. Rundungen
   bleiben nur für echte Kreisformen (Avatare, Zähler-Badges, Bottom-Nav-
   Insel, FAB) und für Nutzerinhalt (Whiteboard-Sticky-Notes).

---

## 1. Icons

Einzige Icon-Quelle: **lucide-react**. Nie Emoji (im ganzen `frontend/src`
verifiziert: keine Emoji-Codepoints). `strokeWidth={1.5}` (nicht `2`) --
Industry-Konvention aus dem Design-Handoff.

Icons stecken normalerweise in `IconBadge` (`frontend/src/components/
IconBadge.tsx`), nie frei im DOM:

```tsx
<IconBadge icon={CalendarClock} tone="amber" size="md" active={isActive} />
```

Props: `icon: LucideIcon`, `tone: IconTone`, `size?: "sm" | "md"` (default
`"md"`), `active?: boolean` (default `true`).

**Haarlinien-Quadrat statt Pastell-Fläche**: Rahmenfarbe + Icon in Ton-
Farbe, Hintergrund transparent, eckige Box (`rounded-none`):

```
Rahmen/Icon: border-{ton}-300 text-{ton}-600  |  dark: border-{ton}-800 text-{ton}-400
```

| Tone | Rahmen/Icon-Klassen | Funktionsbereich |
|---|---|---|
| `sky` | `border-sky-300 text-sky-600 dark:border-sky-800 dark:text-sky-400` | Feed, Prüfmittel, Kennzahlen |
| `violet` | `border-violet-300 text-violet-600 dark:border-violet-800 dark:text-violet-400` | Profil, Highlights, Account-Typen & Rechte, Formulare |
| `amber` | `border-amber-300 text-amber-600 dark:border-amber-800 dark:text-amber-400` | Dispo, Auftragsanfragen, Nutzer verwalten |
| `emerald` | `border-emerald-300 text-emerald-600 dark:border-emerald-800 dark:text-emerald-400` | Geschäft, Techniker-Zuweisungen |
| `cyan` | `border-cyan-300 text-cyan-600 dark:border-cyan-800 dark:text-cyan-400` | Zeiterfassung, Rechnungen, Rechnungseingang, Team-Zeiten |
| `indigo` | `border-indigo-300 text-indigo-600 dark:border-indigo-800 dark:text-indigo-400` | Buchhaltung, Integrationen |
| `rose` | `border-rose-300 text-rose-600 dark:border-rose-800 dark:text-rose-400` | Meldungen, Anlagen-Zusatzfelder |
| `slate` | `border-slate-300 text-slate-500 dark:border-stone-700 dark:text-stone-400` | Papierkorb (neutral) |

Single Source of Truth für diese Zuordnung: `frontend/src/config/navSeiten.ts`
(dieselbe Datei speist Feld-App-Bottom-Nav *und* Office-Sidebar-Gruppierung).

Weitere Bausteine in `IconBadge.tsx`:

```ts
// weicheres Pendant fuer aktive Listenzeilen (Rahmen+leichte Flaeche statt
// nur Rahmen) -- z.B. Super-Admin-Sidebar-Zeile
export const TONE_ROW_ACTIVE = { sky: "border-sky-400 bg-sky-50/60 text-sky-700 dark:border-sky-600 dark:bg-sky-500/10 dark:text-sky-300", /* ... */ };

// Box-Groesse -- jetzt eckig (rounded-none), nicht mehr rounded-lg/xl
SIZE_BOX = { sm: "h-7 w-7 rounded-none", md: "h-9 w-9 rounded-none" };
SIZE_ICON = { sm: 15, md: 18 }; // strokeWidth={1.5}

// active=false -> neutral-grau statt Farbe (nur das ausgewaehlte Element zeigt Farbe)
MUTED = "border-slate-300 text-slate-400 dark:border-stone-700 dark:text-stone-500";
```

**Ausnahme Office-/Super-Admin-Sidebar**: dort **kein** `IconBadge`, sondern
bloße 16px-Icons direkt in der NavLink-Zeile + ein 2px breiter Akzent-Strich
links (`absolute left-0 top-1.5 bottom-1.5 w-0.5 bg-ind-acc`, Opacity über
`isActive` gesteuert) -- Muster 1:1 aus dem CRM-Shell-Mockup übernommen
(`office/OfficeLayout.tsx`, `components/Layout.tsx`). Dort wäre ein
zusätzliches Rahmen-Quadrat pro Icon redundant, weil die ganze Zeile schon
der Klick-Bereich ist.

---

## 2. Farb-/Typografie-Basis

**Kein** `tailwind.config.js` -- Tailwind v4, komplett CSS-basiert über
`@theme` in `frontend/src/index.css`.

### Farbtoken: `--color-ind-*`

Eigene, mit `ind-` präfixierte Custom Properties (bewusst nicht die
Standard-Tailwind-Palette direkt, sondern ein eigener Satz mit halb-
transparenten Zwischenstufen):

| Token | Rolle |
|---|---|
| `ind-bg` | Seiten-/Karten-Hintergrund (kein Kontrast Karte vs. Seite -- nur der Rahmen trennt) |
| `ind-ink` | Primärtext, Überschriften |
| `ind-ink-2` | Sekundärtext |
| `ind-ink-3` | Meta-/Placeholder-Text, am meisten benutzte Muted-Stufe |
| `ind-line` | Standard-Rahmen (Karten, Buttons, Inputs) |
| `ind-line-2` | Kräftigerer Rahmen (verschachtelte Blöcke, Passermarken-Farbe) |
| `ind-acc` | Akzent für Icons/Rahmen (steel blue) |
| `ind-acc-txt` | Akzent-Text (etwas heller/lesbarer als `ind-acc`) |
| `ind-acc-soft` | Dezente Akzent-Fläche (z. B. aktiver Filter-Button-Hintergrund) |
| `ind-hover` | Hover-Zustand neutraler Elemente |
| `ind-field` / `ind-field-ink` | Gefüllte Aktiv-Fläche (Segmented-Control aktiv, Offline-Banner) |
| `ind-btn-bg` / `ind-btn-bg-h` / `ind-btn-ink` | Primär-Button: Ruhe / Hover / Text |
| `ind-warn` | Warnung (Rahmen+Text, keine Fläche) |
| `ind-bad` | Fehler (Rahmen+Text, keine Fläche) |

Definiert in `index.css`: helle Werte im `@theme`-Block, dunkle Werte in
einem `.dark { }`-Block direkt darunter. Tailwind v4 löst `@theme`-Werte
als normale CSS-Variablen auf -- ein Re-Scope unter `.dark` wirkt also
automatisch auf jede Utility-Klasse, die dieselbe Variable referenziert
(`bg-ind-bg`, `text-ind-ink-3`, `border-ind-line` usw.) -- **kein**
`dark:`-Präfix pro Klasse nötig, anders als bei den alten `slate`/`stone`-
Klassen.

**Echte Semantikfarben bleiben separat**: Status-Tags (Vorgang/Rechnung/
Angebot), Warn-/Fehlerzustände mit Bedeutung über die reine Betonung hinaus
nutzen weiterhin eigenständige Tailwind-Farben (`text-blue-700
dark:text-blue-300`, `border-red-400 dark:border-red-600` usw.), **nicht**
die `ind-`-Palette -- Marken-Akzent und Status-Semantik sind bewusst
getrennt (siehe §8).

### Typografie

- **Barlow Condensed** (`font-heading`): Überschriften, Wortmarke, Section-
  Labels, Buttons -- oft `uppercase tracking-wide` (Sperrung 0.02em) bzw.
  `tracking-[0.14em]` für sehr kleine Kategorie-Labels (10px)
- **Barlow** (`font-sans`): Fließtext, Formularfelder, normale UI-Texte --
  Tailwinds Default-Sans-Fallback bleibt in der `font-sans`-Definition
  erhalten, Barlow kommt zuerst
- `font-variant-numeric: tabular-nums` (`tabular-nums`-Klasse) für Zahlen
  in Tabellen/Kennzahl-Kacheln

Radius: **quadratisch ist der neue Standard** -- `rounded-none` explizit
oder (häufiger) einfach keine Radius-Klasse. Verbleibende Rundungen sind
absichtlich, nicht vergessen:

| Kontext | Radius |
|---|---|
| Karten, Buttons, Inputs, Tags, Segmented-Controls | keiner (`rounded-none`) |
| Bottom-Nav-Insel, FAB, Avatare/Initialen-Kreise, Zähler-Badges | `rounded-full` |
| Whiteboard-Sticky-Notes/-Karten (Nutzerinhalt) | wie vom Nutzer/Feature gewählt, unangetastet |

Body: `bg-ind-bg text-ind-ink` (löst automatisch nach Theme auf, kein
`dark:`-Zusatz mehr nötig).

### Custom Utility-Klassen (`index.css`)

```css
/* -- aktives Industry-Rezept -- */
.btn-industry                 /* Basis: Barlow-Condensed, quadratisch, 13px, uppercase, Haarlinie (transparent bis Variante sie faerbt) */
.btn-industry-primary         /* Fuellung --color-ind-btn-bg, Text --color-ind-btn-ink, Hover --color-ind-btn-bg-h */
.btn-industry-secondary       /* Rahmen --color-ind-line, Hover-Flaeche --color-ind-hover */
.btn-industry-ghost           /* transparenter Rahmen, Text --color-ind-acc-txt */
.btn-industry-icon            /* 36x36px, kein Innenabstand -- fuer Icon-only-Buttons */
.input-industry               /* Haarlinien-Input/Select/Textarea, transparenter Hintergrund, width:100% */
.tag-industry(-accent|-neutral|-outline)  /* kleine Chips */
.seg-industry                 /* zusammenhaengende Quadrat-Reihe fuer Segmented-Controls (Randlinien zwischen Kindern) */
.blueprint                    /* Haarlinien-Karte mit Platz fuer 4 Passermarken-Spans (siehe Blueprint.tsx) */

/* -- weiterhin gueltig, unabhaengig vom Reskin -- */
.btn-touch { min-h-[48px] min-w-[48px]; }          /* 48x48px Touch-Ziel, Feld-App -- NICHT im Office noetig */
.scrollbar-none { scrollbar-width: none; ... }      /* versteckt Scrollbar, fuer die swipebare Bottom-Nav-Rotunde */
.card-interactive                                   /* zusaetzlich zum Karten-Rezept bei klickbaren Karten-Zeilen (Hover-Anheben) */

/* -- Restbestand aus der Vor-Industry-Aera, nur noch punktuell verwendet -- */
.card-soft / .card-soft-inner   /* neumorphe Doppelschatten-Karte -- nur noch Feed-Story-Chip-Umgebung, NICHT fuer neue Flaechen verwenden */
.btn-clay                       /* neumorpher Schatten -- nicht mehr fuer neue Buttons verwenden, siehe §6 */
.navbar-soft                    /* dasselbe Schatten-Rezept -- durch Haarlinie in BottomNav.tsx ersetzt, Klasse bleibt nur falls noch referenziert */
```

`--klebe-abstand` (CSS-Property, Default `6rem` in `index.css`): Abstand,
den sticky/klebende Leisten zum unteren Rand halten müssen -- siehe §5.

---

## 3. Karten-Rezepte

**Feld-App-Standard** (Default für fast alles):

```
border border-ind-line bg-ind-bg p-3   /* p-3 kompakt, p-4 Formular-/Detailkarten */
```

Kein Schatten, kein Ring-Split zwischen Hell/Dunkel mehr nötig -- die
`ind-line`/`ind-bg`-Token lösen pro Theme automatisch auf. Das ist die
zentrale Vereinfachung gegenüber dem alten Rezept (`rounded-lg bg-white
p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1
dark:ring-stone-800`), das noch getrennte Light/Dark-Behandlung brauchte.

**Hero-Karten mit Passermarken** -- `Blueprint`-Komponente
(`components/Blueprint.tsx`): für die prominentesten Karten einer Seite
(Feed-Karten, Übersichtskarte auf Vorgang-Detail, Login-Karte). Rendert
automatisch 4 `<i class="corner tl/tr/bl/br">`-Spans:

```tsx
<Blueprint className="bg-ind-bg p-4">...</Blueprint>
```

Nicht für jede kleine Box verwenden -- bei zu häufigem Einsatz wirkt die
Passermarken-Deko unruhig statt akzentuierend.

**Office-Desktop** -- `Karte` in `frontend/src/office/OfficeUi.tsx`:

```
border border-ind-line bg-ind-bg
```

Wirkt auf **alle** Office-Seiten, die `Karte`/`KennzahlKarte`/
`TabellenRahmen` verwenden -- eine Änderung an dieser einen Komponente
propagiert app-weit im Office.

**Super-Admin-Shell** (`components/Layout.tsx`): gleiches Sidebar-/Header-
Rezept wie `OfficeLayout.tsx` (Hexagon-Logo, bare Icons + Akzent-Strich,
Haarlinien-Header).

**Feed-Story-Chips** (einzige verbleibende Ausnahme mit altem Rezept) --
`.card-soft`/`.card-soft-inner`, neumorph mit farbigem `--frame-color`-
Rahmen. Historischer Restbestand, nicht als Vorlage für neue Flächen
nehmen.

**Whiteboard/Board-Feature** (`office/boards/nodes/*`,
`pages/feld/boards/*`): behält bewusst Rundung/Schatten/frei wählbare
Farbe -- das sind Objekte, die der Nutzer auf einer Leinwand platziert
(Sticky-Notes, Rahmen, Vorgangs-Karten), kein Seiten-Chrome. Nur die
Bedienelemente drumherum (Toolbar, Segmented-Umschalter Liste/Canvas, FAB)
folgen dem Industry-Rezept.

**Faustregel:** Feld-App → Haarlinien-Standard. Hero-Karte → `Blueprint`.
Office → `Karte` aus `OfficeUi.tsx`. Whiteboard-Inhalt → unangetastet.
Keine fünfte Variante erfinden.

---

## 4. Dark Mode

Pflicht für **jede** Seite, kein Opt-out. Bei den `--color-ind-*`-Token
passiert die Umschaltung automatisch über die CSS-Variable (siehe §2) --
kein `dark:`-Pendant pro Klasse mehr nötig. Bei echten Semantikfarben
(Status/Warnung/Fehler, die weiterhin auf Tailwinds Standardpalette
laufen) weiterhin explizit ergänzen: `border-blue-400 text-blue-700
dark:border-blue-600 dark:text-blue-300`.

"Standard im Betrieb": Dark Mode ist der für den Feld-Einsatz gedachte
Normalfall (Design-Handoff-Vorgabe), technisch bleibt es aber Nutzer-
Präferenz + OS-Default beim ersten Laden, kein Zwang.

Umsetzung unverändert: Klassen-Strategie, `.dark`-Klasse auf `<html>`
(`@custom-variant dark (&:is(.dark *))` in `index.css`,
`frontend/src/context/ThemeContext.tsx`) -- **nicht** über `data-theme`
oder reines `prefers-color-scheme`. Persistiert in `localStorage` unter
`fieldvibe-theme`; Default = OS-Präferenz beim ersten Laden. Toggle:
`ThemeToggle.tsx` (jetzt `.btn-industry-secondary btn-industry-icon`),
Moon/Sun-Icon, `.btn-touch`.

---

## 5. Layout

**Feld-App** (`frontend/src/components/FeldLayout.tsx`, mobil):
- `min-h-screen bg-ind-bg text-ind-ink`
- `<main className="mx-auto max-w-2xl px-3 py-4">` -- die schmale mobile Spalte
- Sticky-Header solide (`bg-ind-bg border-b border-ind-line`), **kein**
  Frosted-Glass/Backdrop-Blur mehr (war `bg-white/80 backdrop-blur-md`)
- Wortmarke Barlow Condensed uppercase: `Field<span className="text-ind-acc-txt">Vibe</span>`
- Bottom-Padding kompensiert die schwebende Bottom-Nav

**Office-Desktop** (`frontend/src/office/OfficeLayout.tsx`):
- gleicher Seitenhintergrund (`bg-ind-bg`), aber feste Sidebar `w-56`
  (einklappbar auf `w-16`), generiert aus `config/navSeiten.ts` --
  **dieselbe Quelle** wie die mobile Bottom-Nav, damit eine neue Seite nie
  nur in einer der beiden Oberflächen auftaucht
- Sidebar-Kopf: 26×26px Hexagon-Logo-Box (`border border-ind-line-2 text-ind-acc`)
  + Wortmarke, darunter Kategorie-Labels (`text-[10px] tracking-[0.14em]
  uppercase text-ind-ink-3`) und Nav-Zeilen mit Akzent-Strich (siehe §1)
- Content-Spalte `min-w-0 flex-1` mit eigenem Sticky-Header (solide,
  `border-b border-ind-line`)
- Kein `.btn-touch`, keine PWA, kein Service Worker

**Super-Admin-Shell** (`frontend/src/components/Layout.tsx`): identisches
Muster zur Office-Sidebar (Hexagon-Logo, Akzent-Strich-Nav, solider
Header) -- eigene Datei, weil eigene Nav-Liste (`NAV_ITEMS`), aber
visuell 1:1 dasselbe Rezept.

**Bottom-Nav "schwebende Insel"** (`frontend/src/components/BottomNav.tsx`):

```
fixed inset-x-3 bottom-3 z-40 flex items-center gap-1 rounded-full border border-ind-line bg-ind-bg py-1.5
```

Form/Struktur bewusst **nicht** eckig gemacht -- `rounded-full` (Pill),
floatet 0.75rem von allen unteren Rändern ab, spannt nicht die volle
Breite. Das ist ein eingespieltes, konfigurierbares Mobil-Pattern
(Fixzone + zentraler FAB + swipebare "Rotunde"-Zone), keine reine Optik-
Frage -- nur die Oberflächenbehandlung wechselte von Neumorphismus-
Schatten (`.navbar-soft`) auf Haarlinie.

FAB:
```
-mt-7 flex h-14 w-14 items-center justify-center rounded-full bg-ind-btn-bg text-ind-btn-ink ring-4 ring-ind-bg hover:bg-ind-btn-bg-h
```
Solide Fläche in `--color-ind-btn-bg` statt Cyan-Blau-Gradient + Clay-
Schatten. Negativer Top-Margin lässt ihn weiterhin aus der Leiste
herausragen; `ring-4` in Seitenhintergrundfarbe erzeugt weiterhin einen
"Aussparungs"-Halo.

`--klebe-abstand`: `6rem` Default (Feld-App, Platz für die Bottom-Nav), in
`OfficeLayout` inline auf `0.75rem` überschrieben (kein Bottom-Nav dort).

Marken-Akzentfarbe: **`--color-ind-acc`/`-acc-txt`** (steel blue), nicht
mehr Cyan -- Wortmarke, FAB, Fokus-Zustände etc. nutzen durchgängig diesen
einen Akzent statt verschiedener Cyan/Blau-Gradients.

> **Erledigt, nicht mehr aktuell**: `docs/DESIGN.md` (ältere Versionen)
> beschrieb noch ein "Nur Kernaktionen + Mehr-Menü"-Bottom-Nav-Modell.
> Aktuell ist das freikonfigurierbare Zwei-Zonen-System aus `BottomNav.tsx`
> + `navSeiten.ts` + `BottomNavSettingsPage.tsx`.

---

## 6. Buttons

**Primary**:
```
btn-touch btn-industry btn-industry-primary
```
Füllung `--color-ind-btn-bg`, Text `--color-ind-btn-ink`, Hover
`--color-ind-btn-bg-h`. Ersetzt das alte `btn-clay bg-linear-to-r
from-cyan-500 to-blue-600 ... text-white` -- **kein** Gradient, **kein**
Neumorphismus-Schatten mehr. `.btn-clay` existiert nur noch als Restklasse
in `index.css`, nicht mehr für neue Buttons verwenden.

**Secondary**:
```
btn-touch btn-industry btn-industry-secondary
```
Haarlinien-Rahmen (`--color-ind-line`), Hover-Fläche `--color-ind-hover`.
Ersetzt `bg-slate-100 ... text-slate-700 dark:bg-stone-800 dark:text-stone-300`.

**Ghost**:
```
btn-industry btn-industry-ghost
```
Transparenter Rahmen, Text `--color-ind-acc-txt`, Hover
`--color-ind-acc-soft`. Für textartige Aktionen ohne eigenen Rahmen im
Ruhezustand.

**Icon-only**:
```
btn-touch btn-industry btn-industry-secondary btn-industry-icon
```
36×36px, kein Innenabstand. `.btn-touch` sorgt weiterhin für das 48px-
Zielmaß in der Feld-App (die sichtbare Box bleibt 36px, die Klick-Fläche
wächst).

**Destructive** -- weiterhin Ausnahme mit echter Semantikfarbe statt
Marken-Akzent:
```
border border-red-400 text-red-700 hover:bg-red-50 dark:border-red-600 dark:text-red-400 dark:hover:bg-red-950/30
```
Bei reinen Icon-Löschbuttons weiterhin text-only mit Hover-Rot, Rot nicht
im Ruhezustand: `text-ind-ink-3 hover:text-red-600 dark:hover:text-red-400`.

`disabled:opacity-50` (bzw. `.btn-industry:disabled` mit 0.45 als CSS-
Fallback) ist der durchgängige Deaktiviert-Zustand.

**Segmented/Toggle-Gruppe** (`.seg-industry`, bzw. das gleiche Muster
manuell in `FeedPage.tsx`/`OfficeUi.tsx`'s `AnsichtUmschalter`):
```
Wrapper: flex border border-ind-line   (Kinder durch border-l border-ind-line getrennt)
aktiv:   bg-ind-field text-ind-field-ink
inaktiv: text-ind-ink-2 hover:bg-ind-hover
```
Ersetzt das alte `bg-slate-100 p-0.5` + `bg-white shadow-xs`-Aktiv-Rezept.

---

## 7. Formulare

Lange Auswahllisten (z. B. Material-Katalog) **immer** als `SearchableSelect`
(`frontend/src/components/SearchableSelect.tsx`), **nie** natives
`<select>`: tippbare Combobox mit Live-Filter (Substring, case-insensitiv),
schließt bei Klick außerhalb oder `Escape`.

Input-Rezept (auch generell für normale Formularfelder):
```
input-industry   /* Haarlinien-Rahmen (--color-ind-line), transparenter Hintergrund, width:100% */
```
Ersetzt `w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm
dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100`. Für Inputs,
die NICHT die volle Breite haben sollen (z. B. `w-20`, `flex-1` neben
einem Button), `.input-industry` nicht verwenden (setzt `width:100%`
unlayered, das gewinnt gegen eine Tailwind-Breiten-Utility) -- statt-
dessen die Klassen einzeln setzen: `border border-ind-line bg-transparent
px-2 py-1.5 text-sm text-ind-ink` + die gewünschte Breiten-Klasse.

Dropdown-Panel nutzt weiterhin `shadow-lg` auch im Dark Mode (kein
Haarlinien-Ersatz) -- weil es ein temporäres Overlay ist, keine ruhende
Karte, plus `border border-ind-line`.

---

## 8. Status-/Semantikfarben

Zentrale Quelle für Vorgang-Status: `frontend/src/config/vorgangDarstellung.ts`
(`STATUS_BADGE`, `STATUS_LABEL`) -- **jetzt tatsächlich durchgängig
importiert**. Vorher gab es hier eine Lücke: mehrere Seiten
(`KundeProfilePage`, `AnlageProfilePage`, `DauerauftragDetailPage`,
`StandortDetailPage`) hatten eine eigene, unabhängige Kopie mit alten
Pastell-Werten -- bei einer Änderung an der zentralen Datei liefen diese
Kopien lautlos auseinander. Beim Industry-Umbau wurden alle bekannten
Kopien auf denselben Rahmen-Wert gebracht; bei neuem Code **immer aus
`vorgangDarstellung.ts` importieren**, nie erneut duplizieren -- und falls
doch eine weitere Kopie auftaucht, sie entfernen statt zu pflegen.

Formel (Rahmen-Tag statt gefüllter Pille -- Industry-Rezept):
```
border border-{farbe}-400 text-{farbe}-700 dark:border-{farbe}-600 dark:text-{farbe}-300
```
Aufrufer setzen **kein** zusätzliches `rounded-full`/`bg-*` mehr um den
Wert (das Rahmen-Rezept bringt schon `border` mit, ein umschließendes
`rounded-full px-2 py-1 ...` reicht als Wrapper-Padding, ohne eigene
Farbe/Form).

Semantische Konvention, durchgängig über alle Status-Maps (Vorgang,
Rechnung, Angebot, Mandant, Vorgang-Anfrage, ...):

| Farbe | Bedeutung |
|---|---|
| blue | neu / versendet / informativ |
| amber / orange | in Arbeit / wartend / teilweise |
| green | erledigt / bezahlt / aktiv |
| slate / stone (neutral) | Entwurf oder Endzustand (`entwurf`, `abgerechnet`, `storniert`) |
| rose / red | abgelehnt / gekündigt |
| purple | geplant / terminiert |

Bei jeder neuen Statusart: erst prüfen, ob eine der bestehenden Farben
passt, bevor eine neue gewählt wird.

Überfällig/Dringlichkeit (steht für sich, kein Teil einer Status-Map):
`text-red-600 dark:text-red-400`. Warnung/Fehler ohne Status-Semantik
(z. B. Offline-Hinweis, Formular-Validierung) nutzen dagegen die
`ind-warn`/`ind-bad`-Token, siehe §2.

---

## 9. Spacing-Rhythmus

Basis-Einheit bewegt sich durchgängig zwischen `1`-`4` (0.25rem-1rem),
unverändert durch den Industry-Umbau:

| Klasse | Verwendung |
|---|---|
| `gap-2` / `space-y-2` (0.5rem) | Standard für zusammengehörige Elemente |
| `space-y-4` (1rem) | Standard für eigenständige Abschnitte |
| `p-3` | Karten-Innenabstand, kompakte Listenkarten |
| `p-4` | Karten-Innenabstand, Formular-/Detailkarten |
| `p-6` / `p-8` | praktisch nie, außer bei Leer-/Ladezuständen ganzer Seiten (`py-10`, `space-y-8`) |
