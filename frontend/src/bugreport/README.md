# bugreport -- Erfassung von Fehlerbericht-Kontext

Eigenständiges Modul (keine Imports aus der restlichen App, kopierbar in andere
Projekte). Sammelt im Hintergrund Netzwerk-Aufrufe, Konsole, Klick-/Routenpfad
und Umgebung in Ringpuffern und liefert auf Abruf einen **geschwärzten**
Snapshot. Stufe 1: nur Erfassung und Schwärzung, kein UI, kein Upload.

## Einbindung

Möglichst früh, vor dem React-Render (siehe `src/main.tsx`):

```ts
import { initFehlerbericht, registriereDebugState, sammleKontext } from "./bugreport";

initFehlerbericht({
  appVersion: __APP_VERSION__,
  commitSha: __GIT_COMMIT__,
  getSitzung: () => ({ user_id, mandant_id, rolle }), // nur IDs/Rolle, oder null
});

const abmelden = registriereDebugState("filter", () => aktuelleFilter);
const kontext = sammleKontext(["netzwerk", "konsole"]); // ohne Argument: alle Kategorien
```

`beendeFehlerbericht()` entfernt alle Patches (Tests, HMR).

## Konfiguration (nur per `initFehlerbericht`)

| Option | Default | Bedeutung |
| --- | --- | --- |
| `maxNetzwerk` / `maxKonsole` / `maxBreadcrumbs` | 50 / 100 / 100 | Ringpuffer-Größen |
| `maxBodyBytes` | 10240 | Kürzung von Request-/Response-Bodies |
| `konsoleLog` | `true` | `console.log` mit erfassen (error/warn immer) |
| `ignoreUrls` | `[]` | zusätzlich zu `/api/fehlerberichte` (Teilstring oder RegExp) |
| `zusatzDenylist` | `[]` | weitere Schlüsselnamen (Teilstring, case-insensitive) |
| `maskiereEmail` / `maskiereIban` / `maskiereTelefon` | `true` | Regex-Maskierung in Freitext |

## Datenschutz

- Schwärzung passiert **beim Erfassen** (Header, Bodies, URLs, Konsole) und
  nochmals in `sammleKontext` -- im Speicher liegen keine Klartext-Secrets.
- Header-Denylist (`authorization`, `cookie`, `set-cookie`, ...) und
  Schlüssel-Denylist (`password`, `token`, `iban`, `pin`, ...) -> `[entfernt]`.
  Die Schlüsselprüfung ist ein Teilstring-Treffer und schwärzt daher bewusst
  großzügig (z. B. `shipping` enthält `pin`). JWTs werden immer maskiert.
- Bodies werden nur bei Status >= 400 oder Netzwerkfehler erfasst; Binärdaten
  und FormData nur als Platzhalter. Bodies eines `Request`-Objekts (statt
  `init.body`) werden nicht erfasst.
- Klick-Breadcrumbs enthalten nie Werte von Eingabefeldern, bei Inputs nur
  Tag, `type` und `name`. Query-Parameter und URL-Fragmente werden bereinigt.
- Die Telefon-Maskierung greift nur bei Nummern mit führender `0`/`00`/`+`,
  um IDs und Zeitstempel nicht zu treffen. Sie ist eine Heuristik, keine
  Garantie -- Freitext kann trotzdem personenbezogene Daten enthalten.
- Der Nutzer sollte den Snapshot vor dem Absenden einsehen können (UI folgt).
