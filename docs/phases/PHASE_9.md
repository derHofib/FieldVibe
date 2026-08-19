# Phase 9 – Desktop-Oberfläche unter `office.<domain>`

Kein Abschnitt des Lastenhefts, sondern eine Produktentscheidung: die
Feld-App ist bewusst mobile-first (`FeldLayout` zwängt alles in
`max-w-2xl`, Navigation ist die schwebende Bottom-Nav-Pille, Karten statt
Tabellen). Für Techniker unterwegs ist das richtig, am Schreibtisch
verschenkt es Bildschirmfläche: wer 40 Vorgänge vergleicht oder Rechnungen
abarbeitet, scrollt durch eine schmale Kartenspalte.

Diese Phase stellt daneben eine zweite, produktivitätsorientierte
Oberfläche unter `office.<domain>`. `app.<domain>` bleibt unverändert die
mobile PWA.

## Die eine Architekturentscheidung

**Ein Vite-Build, ein `frontend`-Container, beide Subdomains zeigen
darauf. Welche Shell gerendert wird, entscheidet der Browser zur Laufzeit
am Hostnamen; der Office-Code hängt an `React.lazy`.**

Das trägt, weil die Seiten längst von ihrer Shell entkoppelt sind: es gibt
**keinen einzigen** Import von `FeldLayout`/`Layout`/`PortalLayout` in
`pages/`. Die "Mobilität" steckt ausschließlich in `FeldLayout` selbst –
`max-w-2xl`, `BottomNav`, `.btn-touch`, `env(safe-area-inset-bottom)`.
`api/endpoints.ts`, `types/`, `utils/`, `AuthContext`, `ThemeContext`,
`useEventStream` und `offline/` sind vollständig layout-agnostisch und
werden unverändert weiterbenutzt. `/portal/*` war bereits der funktionierende
Präzedenzfall für eine Sub-App mit eigener Shell.

**Verworfen: ein zweiter HTML-Entry (`office.html`).** Er hätte in Vite 8
`build.rolldownOptions.input` gebraucht (umbenannt von `rollupOptions`),
dazu eine SPA-Fallback-Sonderregel – `serve -s dist` schreibt *jeden*
unbekannten Pfad auf `index.html` um und kann dabei nicht nach Host
unterscheiden – sowie Service-Worker-Ausschlüsse. Alles das entfällt bei
der Hostname-Variante ersatzlos. Ein zweiter Container wäre derselbe
Quellcode ein zweites Mal gebaut.

Der Preis wäre, dass Office-Code im Handy-Bundle landet. Durch
`React.lazy(() => import("./office/OfficeApp"))` – dasselbe Muster, mit dem
`FeedPage` schon `MapboxFeedMap` nachlädt – liegt er in einem eigenen Chunk
(~33 kB), den ein Handy-Nutzer nie herunterlädt.

## Was implementiert wurde

### Infrastruktur

- **`Caddyfile`**: neuer `{$DOMAIN_OFFICE}`-Block, der auf denselben
  `frontend:4173` zeigt wie `{$DOMAIN_APP}`.
- **`docker-compose.prod.yml`**: `DOMAIN_OFFICE` in die `environment:` des
  `caddy`-Service – Caddy hat kein `env_file`, `{$VAR}` löst nur auf, was
  dort steht.
- **`scripts/deploy.sh`**: zusätzliche Domain-Abfrage, `CORS_ORIGINS` wird
  jetzt zweielementig geschrieben. Wichtig war ein eigener
  **Nachtrags-Zweig**: die Domain-Abfrage steckt komplett hinter
  `if [[ "$CURRENT_DOMAIN_APP" == "app.example.de" || -z ... ]]`, in das
  bestehende Installationen nie wieder hineinlaufen – ohne den Zweig bliebe
  `DOMAIN_OFFICE` dort dauerhaft leer.
- **Backend: kein Code.** Nur der Wert von `CORS_ORIGINS` wächst auf zwei
  Einträge (`cors_origins` hat genau einen Konsumenten, `main.py`;
  `allow_credentials=True` schließt Wildcards aus). `FRONTEND_BASE_URL`
  bleibt auf `app.` – es erzeugt ausschließlich den Passwort-Reset-Link
  fürs Kundenportal.

### Shell und Weiche

- **`office/hostname.ts`**: `istOfficeHost()` prüft das `office.`-Präfix,
  plus Dev-Override `?office=1|0` (in `sessionStorage` gemerkt), damit man
  ohne DNS lokal testen kann.
- **`main.tsx`**: `registerSW()` wird auf `office.` übersprungen. Die
  Desktop-Ansicht soll keine PWA sein – kein Precaching, keine
  Update-Banner. Service-Worker-Scopes sind origin-gebunden, die beiden
  Registrierungen könnten sich gar nicht in die Quere kommen; es geht
  darum, auf Office erst gar nicht zu registrieren.
- **`office/geraeteWeiche.ts`**: leitet ab 900 px Fensterbreite zwischen
  den Subdomains um, mit `location.replace` (kein History-Müll), Pfad und
  Query bleiben erhalten. Drei Regeln, damit sie nicht nervt: **nie** bei
  `/portal/*` (Kunden dürfen nie von ihrem Handy weggeleitet werden), nie
  gegen einen bewusst angeklickten "Zur mobilen Ansicht"-Link (Stopp-Flag
  in `sessionStorage`), und nur bei eindeutiger Lage – nie bei Grenzfällen
  ohne klare Richtung.
- **`office/OfficeLayout.tsx`**: Seitenleiste + breiter `<main>`. Die
  Seitenleiste wird **vollständig aus `config/navSeiten.ts` erzeugt**:
  `sichtbareNavSeiten(currentUser, hatRecht)` ist ohnehin die einzige
  Wahrheit darüber, wer welche Seite sehen darf, und liefert Icon, Ton,
  Route und `kategorie` zur Gruppierung gleich mit. Damit kann eine neue
  Seite nicht in der einen Oberfläche auftauchen und in der anderen fehlen.
- **`hooks/useAppLiveDaten.ts`**: `useOutboxSync()`, `useOnlineStatus()` und
  die vier `useEventStream`-Handler lagen inline in `FeldLayout`, sind aber
  nicht mobil-spezifisch. Jetzt ein gemeinsames Hook, das *beide* Shells
  aufrufen, statt den Block zu kopieren.

### Die vier Bereiche

Gemeinsamer Hebel: **Detailseiten werden nicht nachgebaut, sondern
eingebettet.** Alle lesen ihre ID in der ersten Zeile aus `useParams`; eine
Ein-Zeilen-Änderung je Datei macht sie einbettbar, ohne bestehende Routen
zu brechen:

```tsx
export function VorgangDetailPage({ id: idProp }: { id?: string } = {}) {
  const { id: idParam } = useParams<{ id: string }>();
  const id = idProp ?? idParam;
```

Das spart allein bei `VorgangDetailPage` einen Fork von ~2000 Zeilen und
verhindert vor allem, dass Mobil und Office fachlich auseinanderlaufen.

- **Vorgänge** (`office/vorgaenge/`): Umschalter zwischen **Liste**
  (Kartenliste + eingebettetes Detail-Panel), **Kanban** (Spalten nach
  Status) und **Raster** (dichtes Grid mit Checkboxen, Sammelaktion,
  Tastaturkürzeln `j`/`k`/`x`/`Enter`). Die Auswahl liegt in
  `localStorage` – bewusst **kein** Backend-Feld und **keine** Migration
  für V1; das bestehende `bottom_nav_items` bleibt rein mobil.
  Kanban und Raster laden alle Seiten nach, bevor sie zeichnen – sonst
  hätten einzelne Spalten Lücken, die nur nach fehlenden Vorgängen
  aussehen. Dieselbe Query samt Offline-Rückfall wie der Feed, gleicher
  `queryKey`, damit die SSE-Invalidierung beide Oberflächen frisch hält.
  **Drag & Drop im Kanban** (nachgerüstet, 19.08. -- widerruft die
  urspruengliche Entscheidung aus diesem Abschnitt): Karte auf eine andere
  Spalte ziehen aendert den Status per PATCH. Rein optimistisch -- die
  Karte springt sofort, ein Fehler vom Server (z. B. 409 bei fehlenden
  Pflichtformularen fuer "abgeschlossen") laesst sie in die
  Ausgangsspalte zurueckspringen samt Fehlermeldung, statt den Wechsel
  stillschweigend zu blockieren oder zu erzwingen.
- **Rechnungen & Angebote** (`office/rechnungen/`): Liste links, die
  bestehende `RechnungDetailPage`/`AngebotDetailPage` rechts eingebettet,
  Summen brutto/offen im Kopf, überfällige Beträge hervorgehoben.
- **Formulare** (`office/formulare/`): Übersicht als Karten-Grid (die
  Handy-App zeigt eine reine Liste, was bei vielen Vorlagen
  unübersichtlich wird), Editor ist der bestehende `FormularRasterEditor`.
  Dessen Ausbruch aus der Lesespalte (`lg:left-1/2 lg:mx-[-50vw]
  lg:w-screen`) hängt jetzt an der Prop `vollbreiteAusbruch` – in der
  ohnehin breiten Office-Shell würde er das Layout sprengen.
- **Dispo + Buchhaltung**: Dispo teilt sich die Spalten-Komponente mit den
  Vorgängen (gleiche Karten, gleiche Statusfarben, nur ein anderer
  Einstieg). Buchhaltung bewusst **nicht** als Karten: vier
  Kennzahl-Karten oben, darunter eine Tabelle – Beträge und Fälligkeiten
  vergleicht man in Spalten schneller als in Kacheln.

Alle übrigen ~30 Seiten übernimmt Office unverändert aus der Feld-App, in
einer begrenzten Lesespalte (`max-w-3xl`). Über die volle Monitorbreite
gezerrt werden Formulare und Detailansichten unlesbar, und eine zweite
Fassung wäre reiner Pflegeaufwand.

Nebenbefund aus der Live-Prüfung: die klebende Kommentar-Leiste der
Vorgangs-Detailseite stand auf `bottom-24` – 6rem Platz für die schwebende
Bottom-Nav. Im Office-Panel klebte sie damit mitten im Inhalt. Der Wert
steckt jetzt in `--klebe-abstand` und wird von der jeweiligen Shell
gesetzt.

## Verifikation

`npm run lint` und `npm run build` sauber; der Office-Chunk erscheint im
Build-Output getrennt (`OfficeApp-*.js`, 33 kB / 8,5 kB gzip), der Split
wirkt also tatsächlich.

Playwright gegen den echten Dev-Server + Backend + lokales PostgreSQL:
Regression der Handy-App zuerst (landet auf `/feed`, genau eine
Service-Worker-Registrierung, keine Konsolen- oder Seitenfehler), dann die
Office-Shell über den Dev-Override (landet auf `/vorgaenge`, **null**
Service-Worker-Registrierungen, Liste/Kanban/Raster schalten um,
`/dispo`, `/rechnungen`, `/formulare`, `/auswertung` laden fehlerfrei).
Dark Mode auf Vorgängen und Buchhaltung geprüft. Die Überlappung der
klebenden Kommentar-Leiste wurde per Bounding-Box-Vergleich zwischen Mobil
und Office nachgewiesen und nach dem Fix erneut gemessen.

## Was offen bleibt

- **Zwei Logins.** Das Token liegt im `localStorage`, der an den Origin
  gebunden ist – wer zwischen `app.` und `office.` wechselt, meldet sich
  zweimal an. Abgestimmt und bewusst zurückgestellt: ein gemeinsames
  Cookie auf `.<domain>` ist ein eigener Umbau (Backend setzt das Cookie,
  Frontend hört auf, das Token selbst zu verwalten, CSRF-Schutz), kein
  Beiwerk dieser Phase. Im Alltag der spürbarste Reibungspunkt.
- **Die Geräte-Weiche ist hier nur indirekt prüfbar.** Lokal gibt es keine
  Subdomains; verifiziert wurde, dass sie auf `localhost` korrekt *nicht*
  auslöst, und die Entscheidungsregeln wurden separat durchgespielt. Das
  echte Umleiten zwischen `app.` und `office.` zeigt sich erst auf dem
  Server.
- **Docker/Let's Encrypt weiterhin ungetestet** (kein Docker-Daemon in
  dieser Umgebung, Umgebungseinschränkung, kein Code-Mangel). Insbesondere
  der Zertifikatsbezug für die vierte Domain ist reine Konfiguration auf
  dem Papier, bis er einmal gelaufen ist. Die CI baut Backend-Images und
  `npm run build`, deckt den Caddy-Teil also auch nicht ab.
- **`npm ci` gegen das Vite-8-Lockfile** ist vor dem ersten Server-Deploy
  gezielt zu prüfen: lokal war beim Upgrade `--legacy-peer-deps` nötig. Die
  konfliktären *optionalen* Peers (`@rolldown/plugin-babel`,
  `babel-plugin-react-compiler`) stehen nicht im `package-lock.json`,
  `npm ci` sollte daher sauber durchlaufen – bestätigt ist es nicht.
- **Keine Sammelaktionen außer Statuswechsel** im Raster.
- **Office ist keine PWA** und legt bewusst nichts offline neu an – am
  Schreibtisch ist eine Verbindung vorausgesetzt. Die
  Outbox-Synchronisierung läuft trotzdem mit, damit unterwegs Angelegtes
  auch hier auftaucht.
- **Im IP-Modus (`docker-compose.ip.yml`) gibt es keine Desktop-Ansicht** –
  eine nackte IP hat keinen Hostnamen, an dem umgeschaltet werden könnte.
  Bewusst so dokumentiert statt einen zweiten Port zu erfinden.
