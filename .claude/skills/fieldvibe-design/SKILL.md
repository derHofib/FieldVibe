---
name: fieldvibe-design
description: >
  Nachschlagewerk für das visuelle Design-System von FieldVibe (Icons,
  Farben/Tones, Karten-Rezepte, Buttons, Dark Mode, Layout, Spacing) --
  ausschließlich für frontend/src in diesem Repo (SocialCRM/FieldVibe). Vor
  JEDER neuen UI-Komponente, Seite, Karte, Button, Formularfeld oder
  Statusfarbe in diesem Frontend zuerst hier nachsehen, damit bestehende
  Muster wiederverwendet statt neu erfunden werden -- auch wenn nicht
  explizit nach "Design" gefragt wird, sondern nur "baue mir eine Seite für
  X" oder "füge einen Button/eine Karte für Y hinzu". Auch nützlich bei
  Fragen nach dem FieldVibe-Styleguide, der Icon-Farbe für einen neuen
  Bereich, oder ob Slate/Stone bzw. Feld-App/Office-Konventionen greifen.
  Kein Ersatz für den separaten "design"-Skill (der baut Mockup-Canvases) --
  dieser Skill ist reine Referenz für existierenden Code.
---

# FieldVibe Design-System (frontend/src)

Dieses Dokument fasst zusammen, wie FieldVibe tatsächlich aussieht -- nicht
wie es aussehen sollte. Alle Angaben sind aus dem Code verifiziert (Datei:Zeile
wo hilfreich). Ergänzend, aber teils veraltet: `docs/DESIGN.md` (siehe
Abweichung unten bei Bottom-Nav). Bei Widerspruch zwischen den beiden gilt
dieses Dokument, weil es näher am aktuellen Code liegt -- im Zweifel trotzdem
kurz den Code selbst gegenchecken, Konventionen driften.

## Checkliste, bevor du etwas Neues baust

1. **Tone/Statusfarbe**: Passt einer der 8 IconBadge-Tones oder eine der
   bestehenden Statusfarben fachlich? Ein Tone deckt eine ganze Bereichs-
   "Familie" ab, nicht einzelne Seiten -- neue Seite zuerst einer Familie
   zuordnen, bevor ein neuer Tone erwogen wird.
2. **Welches Karten-Rezept?** Feld-App-Standard, Office-`Karte`, oder
   `.card-soft` (nur Feed)? Siehe §3.
3. **Welche Button-Variante?** Primary/Secondary/Destructive/Icon-only,
   siehe §6 -- nicht neu erfinden.
4. **`.btn-touch` nötig?** Ja in der Feld-App (48×48px-Mindestziel), nein im
   Office-Desktop-Layout (dort kein Touch-Ziel, keine PWA).
5. **Dark-Mode-Gegenstück nicht vergessen**: `slate` (hell) → `stone`
   (dunkel), nie gemischt. Jede neue Klasse mit `dark:`-Pendant ergänzen.
6. **Icon**: nur lucide-react, nur über `IconBadge`, nie Emoji, nie ein
   Icon frei im Text.

---

## 1. Icons

Einzige Icon-Quelle: **lucide-react**. Nie Emoji (im ganzen `frontend/src`
verifiziert: keine Emoji-Codepoints). Icons stecken immer in
`IconBadge` (`frontend/src/components/IconBadge.tsx`), nie frei im DOM.

```tsx
<IconBadge icon={CalendarClock} tone="amber" size="md" active={isActive} />
```

Props: `icon: LucideIcon`, `tone: IconTone`, `size?: "sm" | "md"` (default
`"md"`), `active?: boolean` (default `true`).

Farbformel pro Tone -- **bewusst gedämpfte Pastelltöne** (Code-Kommentar:
kräftige 400/600-Flächen wirken "verspielt" statt "dezent"):

```
hell:   bg-{ton}-100 text-{ton}-600
dunkel: bg-{ton}-500/15 text-{ton}-300
```

| Tone | Klassen | Funktionsbereich |
|---|---|---|
| `sky` | `bg-sky-100 text-sky-600 dark:bg-sky-500/15 dark:text-sky-300` | Feed, Prüfmittel, Kennzahlen |
| `violet` | `bg-violet-100 text-violet-600 dark:bg-violet-500/15 dark:text-violet-300` | Profil, Highlights, Account-Typen & Rechte, Formulare |
| `amber` | `bg-amber-100 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300` | Dispo, Auftragsanfragen, Nutzer verwalten |
| `emerald` | `bg-emerald-100 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300` | Geschäft, Techniker-Zuweisungen |
| `cyan` | `bg-cyan-100 text-cyan-600 dark:bg-cyan-500/15 dark:text-cyan-300` | Zeiterfassung, Rechnungen, Rechnungseingang, Team-Zeiten |
| `indigo` | `bg-indigo-100 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-300` | Buchhaltung, Integrationen |
| `rose` | `bg-rose-100 text-rose-600 dark:bg-rose-500/15 dark:text-rose-300` | Meldungen, Anlagen-Zusatzfelder |
| `slate` | `bg-slate-100 text-slate-500 dark:bg-stone-800 dark:text-stone-400` | Papierkorb (neutral) |

Single Source of Truth für diese Zuordnung: `frontend/src/config/navSeiten.ts`
(dieselbe Datei speist Feld-App-Bottom-Nav *und* Office-Sidebar).

Weitere Bausteine in `IconBadge.tsx`:

```ts
// weicheres Pendant für aktive Listenzeilen (-50/-700 statt -100/-600)
export const TONE_ROW_ACTIVE = { sky: "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-300", /* ... */ };

// Box-Größe
SIZE_BOX = { sm: "h-7 w-7 rounded-lg", md: "h-9 w-9 rounded-xl" };
SIZE_ICON = { sm: 15, md: 18 }; // immer strokeWidth={2}

// active=false -> neutral-grau statt Farbe (nur das ausgewählte Element zeigt Farbe)
MUTED = "bg-slate-100 text-slate-400 dark:bg-stone-800/80 dark:text-stone-500";
```

---

## 2. Farb-/Typografie-Basis

**Kein** `tailwind.config.js` -- Tailwind v4, komplett CSS-basiert über
`@theme` in `frontend/src/index.css`. Kein custom Font, keine custom
Farbpalette, keine custom Radius-Skala -- ausschließlich Standard-Tailwind.

Radius-Verwendung (Häufigkeit zeigt die Default-Wahl je Kontext):

| Klasse | Kontext |
|---|---|
| `rounded-md` | Standard für Buttons, Inputs, kleine Chips (mit Abstand am häufigsten) |
| `rounded-lg` | Standard für Karten |
| `rounded-full` | Pills, Avatare, Bottom-Nav-Insel, FAB |
| `rounded-xl` | wenige größere Flächen (Office-`Karte`, `IconBadge` md) |
| `rounded-xs` | selten, einzelne Detailflächen |

Body: `bg-slate-100 text-slate-900 dark:bg-stone-950 dark:text-stone-100`.

### Custom Utility-Klassen (`index.css`)

```css
.btn-touch { min-h-[48px] min-w-[48px]; }          /* 48×48px Touch-Ziel, Feld-App -- NICHT im Office nötig */
.scrollbar-none { scrollbar-width: none; ... }      /* versteckt Scrollbar, für die swipebare Bottom-Nav-Rotunde */
.card-interactive {                                 /* zusätzlich zum Karten-Rezept bei klickbaren Karten-Zeilen */
  transition-all duration-150 hover:-translate-y-0.5 hover:shadow-md active:translate-y-0 active:shadow-xs;
}
.card-soft / .card-soft-inner   /* neumorphe "Claymorphism"-Doppelschatten-Karte, --frame-color pro Status inline gesetzt -- NUR Feed-Karten */
.btn-clay                       /* neumorpher Haupt-Button-Schatten, kippt bei :active auf inset ("gedrückt") */
.navbar-soft                    /* gleiches Schatten-Rezept wie .card-soft-inner, für Bottom-Nav-Insel + FAB */
```

`--klebe-abstand` (CSS-Property, Default `6rem` in `index.css`): Abstand,
den sticky/klebende Leisten zum unteren Rand halten -- siehe §5.

---

## 3. Karten-Rezepte (wichtigstes Muster im Frontend, 150+ Vorkommen)

**Feld-App-Standard** (Default für fast alles):

```
rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800
```

`p-3` für kompakte Listenkarten, `p-4` für Formular-/Detailkarten -- der Rest
des Strings ist fix. **Zentrales, ausnahmslos beobachtetes Prinzip:**
Hellmodus hebt mit echtem `shadow-xs` vom `bg-slate-100`-Hintergrund ab;
Dunkelmodus killt den Schatten explizit (`dark:shadow-none`) und ersetzt ihn
durch einen 1px-Ring (`dark:ring-1 dark:ring-stone-800`) -- Box-Shadows wirken
auf dunklem Grund matschig, ein Ring simuliert Tiefe sauber.

**Office-Desktop** -- `Karte` in `frontend/src/office/OfficeUi.tsx`:

```
rounded-xl border border-slate-200 bg-white dark:border-stone-800 dark:bg-stone-900
```

Echter `border` statt Shadow/Ring-Split, `rounded-xl` statt `rounded-lg` --
bewusst flacher, "App-artiger" als die Feld-App-Karten.

**Feed-Karten** (einzige Ausnahme) -- `.card-soft` + `.card-soft-inner`,
neumorph mit farbigem `--frame-color`-Rahmen, der ausblendet.

**Faustregel:** Feld-App → Standard-Rezept. Feed → `.card-soft`. Office →
`Karte` aus `OfficeUi.tsx`. Keine vierte Variante erfinden.

---

## 4. Dark Mode

Pflicht für **jede** Seite, kein Opt-out. Neutral-Familie: **`slate` = hell,
`stone` = dunkel**, durchgängig, nie gemischt (kein `dark:slate-*`, kein
helles `stone-*`).

Umsetzung: Klassen-Strategie, `.dark`-Klasse auf `<html>`
(`@custom-variant dark (&:is(.dark *))` in `index.css`,
`frontend/src/context/ThemeContext.tsx`) -- **nicht** über `data-theme` oder
reines `prefers-color-scheme`. Persistiert in `localStorage` unter
`fieldvibe-theme`; Default = OS-Präferenz beim ersten Laden. Toggle:
`ThemeToggle.tsx`, Moon/Sun-Icon, `.btn-touch`.

---

## 5. Layout

**Feld-App** (`frontend/src/components/FeldLayout.tsx`, mobil):
- `min-h-screen bg-slate-100 dark:bg-stone-950`
- `<main className="mx-auto max-w-2xl px-3 py-4">` -- die schmale mobile Spalte
- Sticky-Header mit Frosted-Glass: `bg-white/80 backdrop-blur-md`
- Bottom-Padding kompensiert die schwebende Bottom-Nav

**Office-Desktop** (`frontend/src/office/OfficeLayout.tsx`):
- gleicher Seitenhintergrund, aber feste Sidebar `w-56`, generiert aus
  `config/navSeiten.ts` -- **dieselbe Quelle** wie die mobile Bottom-Nav,
  damit eine neue Seite nie nur in einer der beiden Oberflächen auftaucht
- Content-Spalte `min-w-0 flex-1` mit eigenem Sticky-Header
- Kein `.btn-touch`, keine PWA, kein Service Worker

**Bottom-Nav "schwebende Insel"** (`frontend/src/components/BottomNav.tsx`):

```
navbar-soft fixed inset-x-3 bottom-3 z-40 flex items-center gap-1 rounded-full bg-white py-1.5 dark:bg-stone-900
```

`rounded-full` (Pill), floatet 0.75rem von allen unteren Rändern ab, spannt
nicht die volle Breite. Aufbau: linke Fixzone (max. 2 Slots), zentraler FAB,
rechte swipebare "Rotunde"-Zone (`.scrollbar-none`, snap).

FAB:
```
btn-clay -mt-7 h-14 w-14 rounded-full bg-linear-to-r from-cyan-500 to-blue-600 text-white ring-4 ring-slate-100 dark:ring-stone-950
```
Negativer Top-Margin lässt ihn aus der Leiste herausragen; `ring-4` in
Seitenhintergrundfarbe erzeugt einen "Aussparungs"-Halo.

`--klebe-abstand`: `6rem` Default (Feld-App, Platz für die Bottom-Nav), in
`OfficeLayout` inline auf `0.75rem` überschrieben (kein Bottom-Nav dort).

Marken-Akzentfarbe: **cyan** (Wortmarke "Field**Vibe**" in Cyan, FAB-Gradient
`from-cyan-500 to-blue-600`).

> **Achtung, veraltete Doku:** `docs/DESIGN.md` (Zeilen 22-25) beschreibt noch
> das ältere Bottom-Nav-Modell (fixe 4 Items + "Mehr"-Menü). Das ist überholt
> -- die aktuelle Implementierung (`BottomNav.tsx` + `navSeiten.ts` +
> `BottomNavSettingsPage.tsx`) nutzt ein frei konfigurierbares Zwei-Zonen-
> System (Fixzone + swipebare Rotunde). Nicht erneut als Bug melden.

---

## 6. Buttons

**Primary** -- immer Gradient + `.btn-clay`:
```
btn-touch flex-1 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 py-1.5 text-sm font-medium text-white disabled:opacity-50
```
Office-Variante: `rounded-lg` statt `rounded-md`, kein `.btn-touch`.

**Secondary**:
```
bg-slate-100 ... text-slate-700 dark:bg-stone-800 dark:text-stone-300
```
Hover (falls vorhanden): `hover:bg-slate-200 dark:hover:bg-stone-700`.

**Destructive** -- solide für Aktions-Buttons:
```
btn-touch flex-1 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50
```
Bei reinen Icon-Löschbuttons dagegen **text-only mit Hover-Rot**, Rot nicht
im Ruhezustand:
```
text-slate-400 hover:text-red-600 dark:text-stone-500 dark:hover:text-red-400
```

**Icon-only** (identisch Feld/Office, nur ohne `.btn-touch` im Office):
```
btn-touch flex h-9 w-9 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 dark:text-stone-400 dark:hover:bg-stone-800
```

`disabled:opacity-50` ist der durchgängige Deaktiviert-Zustand überall.

**Segmented/Toggle-Gruppe** (Office, `OfficeUi.tsx`):
```
Wrapper: flex gap-0.5 rounded-lg border border-slate-200 bg-slate-100 p-0.5 dark:border-stone-700 dark:bg-stone-800
aktiv:   bg-white text-slate-800 shadow-xs dark:bg-stone-900 dark:text-stone-100
```

---

## 7. Formulare

Lange Auswahllisten (z. B. Material-Katalog) **immer** als `SearchableSelect`
(`frontend/src/components/SearchableSelect.tsx`), **nie** natives
`<select>`: tippbare Combobox mit Live-Filter (Substring, case-insensitiv),
schließt bei Klick außerhalb oder `Escape`.

Input-Rezept (auch generell für normale Formularfelder):
```
w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100
```

Dropdown-Panel nutzt ausnahmsweise `shadow-lg` auch im Dark Mode (kein
Ring-Ersatz) -- weil es ein temporäres Overlay ist, keine ruhende Karte.

---

## 8. Status-/Semantikfarben

Zentrale Quelle für Vorgang-Status: `frontend/src/config/vorgangDarstellung.ts`
(`STATUS_BADGE`). Soll laut Code-Kommentar die gemeinsame Quelle für Feld-App
*und* Office sein -- wird aber an mindestens einer Stelle (`FeedPage.tsx`)
trotzdem lokal dupliziert statt importiert. Bei neuem Code: **immer aus
`vorgangDarstellung.ts` importieren**, nicht erneut duplizieren.

Formel (Text-lastige Pills, nicht Icon-Hintergrund -- `-800`/`-300`
Textgewicht statt `-600`/`-300` wie bei IconBadge-Tones):
```
bg-{farbe}-100 text-{farbe}-800 dark:bg-{farbe}-500/15 dark:text-{farbe}-300
```

Semantische Konvention, durchgängig über alle Status-Maps (Vorgang,
Rechnung, Angebot, ...):

| Farbe | Bedeutung |
|---|---|
| blue | neu / versendet / informativ |
| amber / orange | in Arbeit / wartend / teilweise |
| green | erledigt / bezahlt |
| slate / stone (neutral) | Entwurf oder Endzustand (`entwurf`, `abgerechnet`, `storniert`) |
| rose / red | abgelehnt |
| purple | geplant / terminiert |

Bei jeder neuen Statusart: erst prüfen, ob eine der bestehenden Farben
passt, bevor eine neue gewählt wird.

Überfällig/Dringlichkeit (steht für sich, kein Teil einer Status-Map):
`text-red-600 dark:text-red-400`.

---

## 9. Spacing-Rhythmus

Basis-Einheit bewegt sich durchgängig zwischen `1`-`4` (0.25rem-1rem).

| Klasse | Verwendung |
|---|---|
| `gap-2` / `space-y-2` (0.5rem) | Standard für zusammengehörige Elemente |
| `space-y-4` (1rem) | Standard für eigenständige Abschnitte |
| `p-3` | Karten-Innenabstand, kompakte Listenkarten |
| `p-4` | Karten-Innenabstand, Formular-/Detailkarten |
| `p-6` / `p-8` | praktisch nie, außer bei Leer-/Ladezuständen ganzer Seiten (`py-10`, `space-y-8`) |
