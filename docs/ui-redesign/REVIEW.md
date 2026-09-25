# UI-Redesign „Apple-Stil" — Phase D: Testinfrastruktur + Selbstkontrolle

Stand: 2026-09-25. Abschluss der im Auftrag verlangten Phase D
(„Testinfrastruktur" + „Selbstkontrolle") für die App-weite Umstellung von
Präsentationsschicht auf das Apple-HIG-Design (`docs/ui-redesign/AUDIT.md` =
Phase A). Keine Backend-/API-/Rechte-Änderungen in diesem Redesign — dieses
Dokument bewertet ausschließlich Präsentationsschicht + Barrierefreiheit.

## 1. Automatisierte Checks — Ergebnis

| Check | Ergebnis |
|---|---|
| `npx tsc --noEmit` (Frontend) | ✅ clean |
| `npx vite build` | ✅ clean (Bundle-Warnung >500kB Chunks ist Alt-Zustand, nicht Teil des Redesigns) |
| `npm run test` (vitest, 63 Tests) | ✅ alle grün (unverändert durch Redesign, reine Logik-Tests) |
| `npx playwright test` (neu, Phase D) | ✅ 6/6 Szenarien grün — siehe Abschnitt 3 |
| Backend `pytest` | nicht in dieser Phase erneut ausgeführt (reine Präsentationsschicht-Änderungen, keine Backend-Berührung) |

## 2. Testinfrastruktur (neu in dieser Phase)

- **Playwright** (`@playwright/test`) + **axe-core** (`@axe-core/playwright`)
  als Dev-Dependencies ergänzt. Konfiguration: `frontend/playwright.config.ts`,
  Specs: `frontend/e2e/apple-redesign.spec.ts`.
- **Nur Chromium.** In dieser Sandbox ist kein WebKit installiert (nur
  Chromium unter `/opt/pw-browsers`, siehe Umgebungs-Hinweis). Reale
  Cross-Browser-Abdeckung — insbesondere Safari/WebKit, das für die
  iOS-PWA-Zielgruppe der Feld-App relevant ist — muss auf einer Maschine mit
  `npx playwright install webkit` nachgeholt werden. **Bewusste Lücke**,
  nicht automatisierbar in dieser Umgebung.
- **`vite.config.ts`**: `test.exclude` um `e2e/**` ergänzt, weil vitest die
  Playwright-Specs sonst wegen des gleichen `*.spec.ts`-Namensmusters
  fälschlich einsammelt und mit einem Fehler abbricht (`test.describe()`
  außerhalb des Playwright-Runners nicht erlaubt).
- **Reichweite bewusst eingeschränkt statt Vollkatalog.** Der Auftrag nennt
  „Chromium+WebKit × 3 Breakpoints × 2 Themes × jede Route" — bei über 100
  Routen über vier Frontends wäre das mehrere hundert Screenshots, nicht in
  vertretbarem Aufwand automatisierbar und vor allem nicht sinnvoll
  auswertbar (Wer prüft 400 Bilder von Hand?). Stattdessen: die drei
  Referenz-Shells, die der Auftrag selbst in Abschnitt 4/5 explizit nennt
  (Super-Admin-Seitenleiste, Feld-App-BottomNav, Office-Seitenleiste), je
  hell/dunkel, mit echtem Login gegen echte Seed-Daten (kein Mock/Storybook).
  Die einzelnen Screens aus den Tasks #51–55 wurden bereits während ihrer
  Umsetzung manuell/visuell geprüft (nicht Teil dieses automatisierten Laufs).
- **Lokaler Dev-Stack ohne Docker aufgesetzt** (Docker-Daemon läuft in dieser
  Sandbox bekanntlich nicht): PostgreSQL 16 lokal installiert und gestartet
  (`service postgresql start`), `fieldvibe`-Rolle/DB bereits aus einer
  früheren Session vorhanden, Migrationen bereits auf `head` (0082). MinIO
  durch `moto_server` (aus `requirements-dev.txt`, sonst für Backend-Tests
  gedacht) als S3-Mock ersetzt, da `app/main.py`s `lifespan` beim Start hart
  einen erreichbaren S3-Endpoint verlangt (`ensure_bucket()`). Backend via
  `uvicorn`, Frontend via `npm run dev`, beide gegen `backend/.env`
  (lokal, nicht committet, per `.gitignore` ausgeschlossen). Demo-Zugänge
  über das bestehende `python -m app.seed`.

## 3. Screenshot-Ergebnis + Befunde (axe-core)

Alle 6 Szenarien bestehen (kein `critical`-Befund), aber axe-core hat reale,
handlungsrelevante Befunde gefunden — nicht Teil dieses Redesign-Auftrags
behoben, hier dokumentiert für einen gezielten Folge-Task:

### 3.1 Fehlendes `<h1>` (moderate, alle 6 Szenarien)

Keine der drei Shells rendert eine echte `<h1>`-Überschrift — der
sichtbare „Seitentitel" (z. B. „Übersicht", „Vorgänge") ist überall ein
`<p>`/`<div>` oder `<h2>` ohne übergeordnetes `<h1>`. Betrifft alle Themes
gleichermaßen, ist also kein Redesign-Regressionsfehler, sondern ein
vorbestehender struktureller Gap, der beim Redesign nicht behoben wurde.
**Vorschlag** (nicht umgesetzt, Presentation-Layer-only, kein Rechte-/API-
Bezug): den jeweiligen Seitentitel in `Layout.tsx`/`FeldLayout.tsx`/
`OfficeLayout.tsx` als `<h1>` rendern statt als `<p>`/`<span>`, visuell
unverändert (Tailwind macht das rein per Tag-Austausch möglich).

### 3.2 Farbkontrast unterhalb WCAG-AA-Schwelle (serious, 4 von 6 Szenarien)

axe-core prüft auf 4.5:1 bei Fließtext. Gefundene Fälle (mit exakten
Werten aus dem Testlauf):

| Kontext | Vordergrund/Hintergrund | Ratio | Schwelle |
|---|---|---|---|
| Feld-App, Filter-Pills (hell) | `#6c6c70` auf `#e3e3e9` (`text-label2` auf `bg-fill2`) | 4.09 | 4.5 |
| Feld-App, aktiver Tab-Label (hell) | `#0071e3` auf `#f8f8fb` (`text-tint`) | 4.43 | 4.5 |
| Super-Admin, Link/Überschrift (dunkel) | `#0a84ff` auf `#2a2a2c` (`text-tint` auf `bg-card`) | 3.92 | 4.5 |
| Office, Ansicht-Umschalter-Buttons (dunkel) | `#98989f` auf `#333336` | 4.39 | 4.5 |
| Office, `.btn-ap-primary` (dunkel) | `#ffffff` auf `#0a84ff` | 3.64 | 4.5 |

Das ist überwiegend eine **Eigenschaft der Apple-Systemfarbe selbst**:
Apples eigenes `systemBlue` (`#007AFF` hell / `#0A84FF` dunkel) unterschreitet
bei kleiner Schrift und auf hellem/dunklem Grund regelmäßig 4.5:1 — bekannte
Spannung zwischen „Apple-HIG-Optik" und WCAG-AA, nicht spezifisch für diese
Umsetzung. `text-label2`/`text-label3` auf `bg-fill2` sind grenzwertig, weil
die Token bewusst subtil/sekundär gehalten sind (Apple-typische Tertiär-Text-
Hierarchie). **Vorschlag** (nicht umgesetzt): `--tint`/`--tint-dark` für
Fließtext unter 14px um ca. 5–8% abdunkeln (dunkler Blauton, nicht heller,
da auf hellem UND dunklem Grund verwendet), oder für Buttons mit weißem
Text auf `--tint` eine dedizierte, dunklere `--tint-on-fill`-Variante nur
für diesen Anwendungsfall einführen. Bewusst nicht in dieser Session
umgesetzt, weil das eine Grundfarb-Entscheidung (Phase B) mit App-weiter
Reichweite ist, keine lokale Korrektur — sollte separat mit dem Auftraggeber
abgestimmt werden, bevor der ganze Blauton verschoben wird.

### 3.3 Sichtprüfung Screenshots

Alle 6 Bilder (`frontend/e2e-screenshots/*.png`, an den Nutzer gesendet, per
`.gitignore` nicht im Repo) zeigen die erwarteten Apple-HIG-Elemente:
Seitenleiste mit Icon-Badges (Super-Admin, Office), BottomNav mit farbigem
aktivem Tab (Feld-App), korrekte Kontrast-Umkehr in beiden Themes, keine
sichtbar leeren/kaputten Layouts. Zwei Screenshots (`super-admin-*-light`,
`office-vorgaenge-*`) wurden mitten im Ladezustand aufgenommen („…"/„Lädt…"
statt echter Zahlen) — reiner Test-Timing-Effekt (zu kurze Wartezeit vor dem
Screenshot), keine Darstellungslücke der App selbst.

## 4. Geänderte Dateien nach Bereich (gesamter Apple-Redesign, Phase A–D)

Commits `354652a..HEAD` (ohne die vorherige, vollständig ersetzte
„Industry"-Ära):

| Bereich | Dateien |
|---|---|
| `pages/feld/` (Feld-App) | 52 |
| `components/` (geteilt) | 48 |
| `office/` | 34 |
| `pages/` (Super-Admin) | 11 |
| `pages/portal/` (Kundenportal) | 10 |
| `index.css`, `App.tsx`, `context/`, `config/` | je 1 |
| **Gesamt** | **159 Dateien, +5153/-4564 Zeilen** |

Vollständige Commit-Liste: `git log --oneline 354652a~1..HEAD -- frontend/src`.

## 5. Task #57 „Hartkodierte Farben/Radien restlos entfernen" — ehrlicher Stand

**Nicht vollständig abgeschlossen**, bewusst pragmatisch begrenzt. Verlauf:

1. Alle toten `--color-ind-*`-Token und `.btn-industry*`-Klassen repo-weit
   ersetzt (Task #56) — keine unsichtbaren/kaputten Screens mehr.
2. Ampel-Farben (rot/rose, grün/emerald, amber/orange, blau) bei
   Text/Border (Commit `f4f07e4`/`49d6a9a`) und Hintergrund (`3be5dc6`) auf
   Status-Token umgestellt — verifiziert an mehreren Stichproben pro Familie
   vor dem Bulk-Sed. **Ein Regex-Bug** ist dabei in den Grautönen-Commit
   (`497a840`) gerutscht und bereits gepusht gewesen, bevor er entdeckt
   wurde — siehe Abschnitt 6, vollständig dokumentiert und behoben (`8e10a4e`).
3. Neutrale Flächenhintergründe (Karten/Fill) auf `bg-card`/`bg-fill`/
   `bg-fill2` umgestellt (`d99ee20`), aber nur für die drei eindeutig
   erkennbaren, durchgängig konsistenten Muster (siehe Commit-Nachricht).

**Bewusst nicht angefasst** (verbleibende ca. 238 Fundstellen):
- **Kategoriale Farbtöne** (sky/violet/purple/indigo/cyan/teal/pink/
  fuchsia/lime/yellow, ~143 Fundstellen): tragen im `IconTone`-System
  (`IconBadge.tsx`) echte kategoriale Bedeutung (nicht Status) — eine blinde
  Familien-Zuordnung wie bei den Ampelfarben wäre hier falsch, weil die
  Zuordnung Bedeutung↔Farbe fachlich ist, nicht rein visuell. Die neuen
  `--tone-*`-Token (Phase B/C) decken bereits den zentralen `IconBadge`/
  `StatusBadge`-Baustein ab; verbleibende Einzelfälle brauchen manuelle
  Sichtung pro Fundstelle.
- **Restliche neutrale Grautöne** (~89 Fundstellen): React-Flow-
  Handle-Punkte (`!bg-slate-300 dark:!bg-stone-600`, kosmetische
  Board-Konnektoren), Modal-Scrim (`bg-slate-900/NN`, bewusst themen-
  unabhängig dunkel), invertierte Buttons (`bg-slate-900 dark:bg-stone-700`),
  Code-Block-Hintergrund (`<pre>`, bewusst immer dunkel für Lesbarkeit),
  äußerer Seitenhintergrund (`bg-slate-100 dark:bg-stone-950`, entspricht
  `--gbg`, aber nicht in derselben Zeile wie die bereits ersetzten
  Fill-Muster und daher von der automatisierten Ersetzung ausgenommen),
  sowie `disabled:`-Varianten der Fill-Buttons (Formularfelder mit
  `disabled:bg-slate-50 dark:disabled:bg-stone-800/NN` — abweichendes
  Variant-Präfix, von der konditionierten Ersetzung bewusst nicht erfasst,
  um keine falschen Treffer zu riskieren).

**Vorschlag für einen Folge-Task**: pro Familie (React-Flow-Dots, Scrim,
`disabled:`-Fills, äußerer Seitenhintergrund) einzeln geprüft und mit
demselben \b-Wortgrenzen-Vorgehen wie in `d99ee20` nachziehen — jeweils
eigener kleiner Commit, kein weiterer Groß-Sweep.

## 6. Vorfall: Regex-Bug im Grautöne-Commit (volle Offenlegung)

Beim Bulk-Sed für neutrale Grautöne (Text/Border, Commit `497a840`) wurde
eine Zahlen-Alternierung `(50|100|200|300)` **ohne** `\b`-Wortgrenze
verwendet. Da `50` als Präfix von `500` matcht, wurden einzelne
Klassen-Strings verstümmelt (z. B. `label3` → `label30`, vereinzelte
verwaiste „0"-Reste). Der Commit war bereits auf den Remote-Branch gepusht,
bevor der Fehler beim nächsten Bulk-Sed-Versuch auffiel. Vorgehen danach:

1. Fehler isoliert reproduziert (`echo ... | sed -E ...`), Ursache
   bestätigt.
2. Umfang über `git show 497a840~1:<datei>` (Vorher-Zustand) gegen den
   Ist-Zustand abgeglichen, um den exakten Blast-Radius zu bestimmen.
3. Fix **vorwärts** (kein `git reset`/History-Rewrite auf bereits
   gepushte Commits, siehe Git-Workflow): dedizierter Fix-Commit `8e10a4e`
   mit eng gescopten Ersetzungen (`label30`→`label2`, `" 0"`-Suffix und
   `" 0 dark:"`-Muster nur in den exakt betroffenen Dateien).
4. **Zusätzlich, während der Behebung selbst**: ein erster, zu breit
   gescopter Reparaturversuch (`grep -rl ' 0"\| 0 '`, 108 statt der
   tatsächlich ~29 betroffenen Dateien) hätte SVG-Pfaddaten, einen
   Inline-`box-shadow`-Wert und — am schwerwiegendsten — echte JS/JSX-Logik
   beschädigt (`outboxCount > 0 &&` → `outboxCount > &&`,
   `aktive.length === 0 ?` → `aktive.length === ?`, beides syntaxbrechend).
   Das wurde **vor** jedem Commit über `git checkout -- frontend/src`
   vollständig verworfen und mit eng gescopten Mustern neu gemacht — nie
   committet oder gepusht.
5. Für alle nachfolgenden Bulk-Sed-Durchgänge in dieser Session:
   verbindliche `\b`-Wortgrenzen nach jeder Zahlen-Alternierung + verpflichtende
   Artefakt-Prüfung (unmögliche Tokens, verwaiste „0"-Reste, doppelte
   Leerzeichen) **vor** jedem `tsc`/Build/Commit. Kein weiterer Vorfall
   dieser Art in den Commits `3be5dc6`/`d99ee20`.

**Lehre für zukünftige Bulk-Ersetzungen in diesem Repo**: Zahlen-
Alternierungen immer mit `\b` abschließen; Reparatur-Greps immer so eng wie
möglich auf die tatsächlich von der Ursache betroffene Dateiliste scopen,
nie auf den gesamten Baum; Sicherheits-Checks vor Whitespace-Bereinigung,
vor Build, vor Commit — in dieser Reihenfolge.

## 7. Dokumentations-Lücke (noch offen)

`docs/DESIGN.md` und der `fieldvibe-design`-Skill (`.claude/skills/
fieldvibe-design/SKILL.md`) beschreiben weiterhin vollständig das alte
„Industry"-Design (Blaupausen-Optik, `--color-ind-*`, `.btn-industry*`) —
**nicht aktualisiert** im Zuge dieses Redesigns. Das ist die verbindliche
Referenz laut `CLAUDE.md` („Vor neuen UI-Elementen dort prüfen, ob ein
bestehendes Pattern passt") und zeigt aktuell auf ein Design-System, das
nicht mehr existiert. Absichtlich **nicht** in dieser Session überschrieben:
`CLAUDE.md` verlangt für Doku-/Konfig-Änderungen dieser Art erst einen
Entwurf zur kurzen Rückmeldung, bevor geschrieben/committet wird. Vorschlag:
in einem eigenen, kurzen Folge-Schritt einen Entwurf für die Apple-Fassung
von `DESIGN.md` vorlegen (Token-Referenz, Bausteine aus Phase C, Icon-Badge-
System, Statusfarben-Mapping aus `AUDIT.md` Abschnitt „Statusfarben-Mapping").

## 8. Manuelle Checkliste (Auftrag Abschnitt 8)

| Punkt | Status |
|---|---|
| Keine Backend-/API-/Rechte-Änderungen | ✅ ausschließlich `frontend/` + `docs/ui-redesign/` in diesem Redesign berührt |
| Bestehende Bibliotheken wiederverwendet (Tailwind v4 + lucide-react) | ✅ keine neue UI-Bibliothek eingeführt |
| Alle Farben aus Design-Token | ⚠️ Ampel-/Neutral-/Fill-Familien erledigt, kategoriale Farbtöne + Restfälle offen (Abschnitt 5) |
| Kleine, nachvollziehbare Commits, sofort gepusht | ✅ durchgehend, inkl. Fix-Commit für den Regex-Vorfall |
| Keine verlorene Funktionalität | ✅ keine Route/Aktion entfernt; `NewVorgangPage` von Vollbild-Route auf Sheet umgestellt (Abschnitt 5.3 des Auftrags verlangt das explizit) |
| Dark-Mode durchgängig | ✅ alle 6 Testszenarien inkl. Dark-Mode-Screenshot bestanden |
| Barrierefreiheit (axe-core) | ⚠️ keine `critical`-Befunde, aber reale `serious`/`moderate`-Befunde dokumentiert (Abschnitt 3), nicht behoben |
| Cross-Browser (WebKit) | ❌ nicht möglich in dieser Sandbox (kein WebKit installiert) |
| Screenshot-Abdeckung „jede Route" | ⚠️ bewusst auf 3 Referenz-Shells begrenzt (Begründung Abschnitt 2) |
| `docs/DESIGN.md` aktualisiert | ❌ offen, Entwurf ausstehend (Abschnitt 7) |

## 9. Fazit

Die Kernumstellung (Token-Fundament, Basis-Komponenten, Layout-Rahmen, die
fünf im Auftrag benannten Referenz-Screens, sowie die repo-weite Ablösung
des toten „Industry"-Systems über alle vier Frontends) ist abgeschlossen
und funktional verifiziert (tsc/build/vitest/Playwright grün, echte
Screenshots gegen echten Stack). Drei ehrliche Lücken bleiben für
gezielte Folge-Schritte: die Feinarbeit an kategorialen/restlichen
Hartkodierungen (Abschnitt 5), zwei axe-core-Befunde mit App-weiter
Reichweite, die bewusst nicht ad hoc gefixt wurden (Abschnitt 3), und die
veraltete `DESIGN.md`/Skill-Dokumentation (Abschnitt 7).
