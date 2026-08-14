# UI/Design-Richtlinien

## Icons statt Emoji
- lucide-react statt Emoji für alle Icons (Navigation, Aktionsleisten, Kommentare)
- Icons stecken in `IconBadge` (frontend/src/components/IconBadge.tsx), nie frei im Text
- Farbpalette bewusst gedämpft ("Pastell"): hell `bg-{ton}-100 text-{ton}-600`,
  dunkel `bg-{ton}-500/15 text-{ton}-300`. Kräftige 400/600-Flächen bewusst
  vermieden — wirken "verspielt" statt "dezent".
- Verfügbare Töne, je einem Funktionsbereich fest zugeordnet: sky (Feed),
  violet (Profil), amber (Dispo), emerald (Geschäft), cyan (Rechnungen),
  indigo (Auswertung), rose (Meldungen), slate (Papierkorb/Mehr/neutral)
- `active=false` → neutrales Grau statt Farbe (z. B. inaktive Bottom-Nav-
  Items) — nur das gerade ausgewählte Element zeigt seine Farbe

## Dark Mode
- Pflicht für jede Seite, kein Opt-out (eigene Aufräum-Phase über 20 Seiten)
- Referenzfarbe für dunkle Flächen ist `stone`, nicht `slate` wie im Hellmodus

## Bottom-Navigation (Feld-App)
- "Schwebende Insel": abgerundete, freistehende Leiste am unteren Rand,
  nicht über die volle Breite
- Nur Kernaktionen dauerhaft sichtbar (Feed, Neu, Profil, Mehr) — Selteneres
  ins aufklappbare "Mehr"-Menü, damit die Leiste auf schmalen Screens nicht
  überladen wirkt
- Suche gehört in den Header, nicht in die Bottom-Nav

## Desktop/Office (office.<domain>)
- Gleiche Bildsprache wie die Feld-App — dieselben `IconBadge`-Töne,
  dieselben Statusfarben, dieselben Karten. Es ändert sich die Anordnung,
  nicht das Aussehen der einzelnen Bausteine
- Seitenleiste statt Bottom-Nav, aus `config/navSeiten.ts` erzeugt
  (dieselbe Quelle wie die Bottom-Nav, gruppiert nach `kategorie`)
- **Karte oder Zeile?** Karte, wenn ein Eintrag für sich steht und
  angeklickt wird (Vorgänge, Formular-Vorlagen). Zeile/Tabelle, wenn
  Werte *zwischen* Einträgen verglichen werden — Beträge, Fälligkeiten,
  Mengen. Deshalb ist die Buchhaltung bewusst eine Tabelle mit
  `tabular-nums`, obwohl die Feld-App dort Karten zeigt
- Listen mit Detailansicht als zweispaltiges Panel (Liste links, die
  **bestehende** Detailseite rechts eingebettet). Die Detailseiten werden
  nicht für den Desktop nachgebaut — sie bekommen nur eine optionale
  `id`-Prop, die `useParams` überschreibt
- Übernommene Feld-App-Seiten laufen in einer begrenzten Lesespalte
  (`max-w-3xl`), nicht über die volle Monitorbreite gezerrt
- Kein `.btn-touch`-Mindestmaß nötig, keine PWA, kein Service Worker
- `--klebe-abstand` steuert, wie weit klebende Leisten über dem unteren
  Rand bleiben: in der Feld-App 6rem für die schwebende Bottom-Nav, im
  Office 0.75rem

## Formulare
- Lange Auswahllisten (Material etc.) als `SearchableSelect` (tippbare
  Combobox), kein normales `<select>`

## Aktionsleisten
- Icons statt Textbuttons für Aktionen (z. B. Kommentarleiste)
