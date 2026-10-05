// Reine Baum-Anordnung fuer das Organigramm (Top-Down-Tidy-Tree mit Konturen).
// Bewusst ohne React/React Flow, damit sie ohne DOM testbar ist.

export interface LayoutKnoten {
  id: string;
  parentId: string | null;
  typ: "linie" | "stabsstelle";
}

export interface LayoutMasse {
  knotenBreite: number;
  knotenHoehe: number;
  abstandX: number;
  // Eine Zeile = halbe Ebene: Linien-Kinder liegen 2 Zeilen unter dem Elternknoten,
  // Stabsstellen 1 Zeile (Zwischenebene). knotenHoehe muss kleiner als zeileHoehe sein,
  // sonst koennten Knoten verschiedener Zeilen einander ueberdecken.
  zeileHoehe: number;
}

export const STANDARD_MASSE: LayoutMasse = {
  knotenBreite: 232,
  knotenHoehe: 108,
  abstandX: 28,
  zeileHoehe: 124,
};

export interface LayoutKante {
  id: string;
  quelle: string;
  ziel: string;
  stab: boolean;
}

export interface LayoutErgebnis {
  // linke obere Ecke je sichtbarem Knoten (React-Flow-Konvention)
  positionen: Map<string, { x: number; y: number }>;
  kanten: LayoutKante[];
  // Anzahl direkter Kinder je Knoten, unabhaengig vom Einklappen
  kinderAnzahl: Map<string, number>;
}

const ZEILEN_LINIE = 2;
const ZEILEN_STAB = 1;

// Belegte x-Spanne [min, max] je Zeile, relativ zur Mitte des Teilbaum-Wurzelknotens.
type Kontur = Array<[number, number] | undefined>;

interface Teilbaum {
  kontur: Kontur;
  versaetze: Map<string, number>;
}

function kinderIndex(knoten: LayoutKnoten[]): { kinder: Map<string, LayoutKnoten[]>; wurzeln: LayoutKnoten[] } {
  const ids = new Set(knoten.map((k) => k.id));
  const kinder = new Map<string, LayoutKnoten[]>();
  const wurzeln: LayoutKnoten[] = [];
  for (const k of knoten) {
    if (k.parentId !== null && ids.has(k.parentId) && k.parentId !== k.id) {
      const liste = kinder.get(k.parentId) ?? [];
      liste.push(k);
      kinder.set(k.parentId, liste);
    } else {
      wurzeln.push(k);
    }
  }
  return { kinder, wurzeln };
}

function verschiebung(akk: Kontur, kontur: Kontur, zeilenVersatz: number, abstand: number): number {
  let d = Number.NEGATIVE_INFINITY;
  kontur.forEach((spanne, zeile) => {
    const belegt = akk[zeile + zeilenVersatz];
    if (spanne && belegt) d = Math.max(d, belegt[1] + abstand - spanne[0]);
  });
  return d === Number.NEGATIVE_INFINITY ? 0 : d;
}

function einmischen(akk: Kontur, kontur: Kontur, zeilenVersatz: number, dx: number): void {
  kontur.forEach((spanne, zeile) => {
    if (!spanne) return;
    const ziel = zeile + zeilenVersatz;
    const bisher = akk[ziel];
    const neu: [number, number] = [spanne[0] + dx, spanne[1] + dx];
    akk[ziel] = bisher ? [Math.min(bisher[0], neu[0]), Math.max(bisher[1], neu[1])] : neu;
  });
}

export function berechneLayout(
  knoten: LayoutKnoten[],
  eingeklappt: ReadonlySet<string>,
  masse: LayoutMasse = STANDARD_MASSE,
): LayoutErgebnis {
  const { kinder, wurzeln } = kinderIndex(knoten);
  const halbe = masse.knotenBreite / 2;
  const kinderAnzahl = new Map<string, number>();
  for (const k of knoten) kinderAnzahl.set(k.id, kinder.get(k.id)?.length ?? 0);

  const teilbaeume = new Map<string, Teilbaum>();
  const besucht = new Set<string>();

  function teilbaum(k: LayoutKnoten): Teilbaum {
    const fertig = teilbaeume.get(k.id);
    if (fertig) return fertig;
    besucht.add(k.id);

    const sichtbareKinder = eingeklappt.has(k.id) ? [] : (kinder.get(k.id) ?? []).filter((c) => !besucht.has(c.id));
    const linie = sichtbareKinder.filter((c) => c.typ !== "stabsstelle");
    const stab = sichtbareKinder.filter((c) => c.typ === "stabsstelle");

    // Rechnung im Rahmen "Kinder"; die Mitte des Elternknotens wird erst danach bekannt.
    const akk: Kontur = [];
    const versaetze = new Map<string, number>();
    for (const c of linie) {
      const t = teilbaum(c);
      const d = verschiebung(akk, t.kontur, ZEILEN_LINIE, masse.abstandX);
      versaetze.set(c.id, d);
      einmischen(akk, t.kontur, ZEILEN_LINIE, d);
    }
    const mitte =
      linie.length > 0 ? (versaetze.get(linie[0].id)! + versaetze.get(linie[linie.length - 1].id)!) / 2 : 0;
    akk[0] = [mitte - halbe, mitte + halbe];

    for (const c of stab) {
      const t = teilbaum(c);
      // Seitlich neben dem Elternknoten, bei Kollision weiter nach rechts.
      const d = Math.max(
        verschiebung(akk, t.kontur, ZEILEN_STAB, masse.abstandX),
        mitte + masse.knotenBreite + masse.abstandX,
      );
      versaetze.set(c.id, d);
      einmischen(akk, t.kontur, ZEILEN_STAB, d);
    }

    for (const [id, d] of versaetze) versaetze.set(id, d - mitte);
    const kontur: Kontur = akk.map((s) => (s ? [s[0] - mitte, s[1] - mitte] : undefined));
    const ergebnis = { kontur, versaetze };
    teilbaeume.set(k.id, ergebnis);
    return ergebnis;
  }

  const wurzelKontur: Kontur = [];
  const wurzelMitten = new Map<string, number>();
  for (const w of wurzeln) {
    const t = teilbaum(w);
    const d = verschiebung(wurzelKontur, t.kontur, 0, masse.abstandX * 2);
    wurzelMitten.set(w.id, d);
    einmischen(wurzelKontur, t.kontur, 0, d);
  }

  const positionen = new Map<string, { x: number; y: number }>();
  const kanten: LayoutKante[] = [];
  const nachId = new Map(knoten.map((k) => [k.id, k]));

  function absolut(id: string, mitteX: number, zeile: number): void {
    positionen.set(id, { x: mitteX - halbe, y: zeile * masse.zeileHoehe });
    const t = teilbaeume.get(id);
    if (!t) return;
    for (const [kindId, dx] of t.versaetze) {
      const stab = nachId.get(kindId)!.typ === "stabsstelle";
      kanten.push({ id: `${id}->${kindId}`, quelle: id, ziel: kindId, stab });
      absolut(kindId, mitteX + dx, zeile + (stab ? ZEILEN_STAB : ZEILEN_LINIE));
    }
  }
  for (const w of wurzeln) absolut(w.id, wurzelMitten.get(w.id)!, 0);

  return { positionen, kanten, kinderAnzahl };
}

/** Alle Nachfahren (ohne den Knoten selbst) -- fuer die Zyklus-Vorpruefung beim Umhaengen. */
export function nachfahren(knoten: LayoutKnoten[], id: string): Set<string> {
  const { kinder } = kinderIndex(knoten);
  const ergebnis = new Set<string>();
  const stapel = [id];
  while (stapel.length > 0) {
    const aktuell = stapel.pop()!;
    for (const k of kinder.get(aktuell) ?? []) {
      if (!ergebnis.has(k.id)) {
        ergebnis.add(k.id);
        stapel.push(k.id);
      }
    }
  }
  return ergebnis;
}

/** Standardzustand: nur die obersten `ebenenOffen` Ebenen zeigen ihre Kinder; alles darunter ist zugeklappt. */
export function standardEingeklappt(knoten: LayoutKnoten[], ebenenOffen = 3): Set<string> {
  const { kinder, wurzeln } = kinderIndex(knoten);
  const zu = new Set<string>();
  const gesehen = new Set<string>();
  const stapel: Array<[LayoutKnoten, number]> = wurzeln.map((w) => [w, 1]);
  while (stapel.length > 0) {
    const [k, ebene] = stapel.pop()!;
    if (gesehen.has(k.id)) continue;
    gesehen.add(k.id);
    const nachkommen = kinder.get(k.id) ?? [];
    if (nachkommen.length > 0 && ebene >= ebenenOffen) zu.add(k.id);
    for (const c of nachkommen) stapel.push([c, ebene + 1]);
  }
  return zu;
}

/** Alle Knoten mit Kindern -- Grundlage fuer "Alles einklappen". */
export function alleMitKindern(knoten: LayoutKnoten[]): Set<string> {
  const mit = new Set<string>();
  const ids = new Set(knoten.map((k) => k.id));
  for (const k of knoten) if (k.parentId !== null && ids.has(k.parentId)) mit.add(k.parentId);
  return mit;
}
