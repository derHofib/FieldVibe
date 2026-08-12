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

## Formulare
- Lange Auswahllisten (Material etc.) als `SearchableSelect` (tippbare
  Combobox), kein normales `<select>`

## Aktionsleisten
- Icons statt Textbuttons für Aktionen (z. B. Kommentarleiste)
