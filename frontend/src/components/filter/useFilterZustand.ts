import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import type { FilterBedingung, FilterFeld } from "./typen";
import { bedingungenAusUrl, bedingungenZuJson } from "./url";

export interface FilterZustand {
  bedingungen: FilterBedingung[];
  setBedingungen(b: FilterBedingung[]): void;
  hinzufuegen(b: FilterBedingung): void;
  ersetzen(index: number, b: FilterBedingung): void;
  entfernen(index: number): void;
  /** Leert Bedingungen UND Suche. */
  zuruecksetzen(): void;
  suche: string;
  setSuche(s: string): void;
  sucheVerzoegert: string;
  aktiveAnzahl: number;
}

const MISCHBAR = ["auswahl", "verknuepfung", "person"];

/** Zustand lebt in der URL (`f` = Bedingungen, `q` = Suche), damit Zurück-Taste, Neuladen und Links funktionieren.
 * Andere Query-Parameter der Seite bleiben unberührt. */
export function useFilterZustand<T>(opts: { felder: FilterFeld<T>[]; praefix?: string }): FilterZustand {
  const { felder, praefix = "" } = opts;
  const fParam = `${praefix}f`;
  const qParam = `${praefix}q`;
  const [params, setParams] = useSearchParams();
  const fRoh = params.get(fParam);
  const qUrl = params.get(qParam) ?? "";

  // Aktuelle Felder per Ref: die Setter bleiben stabil, auch wenn die Seite `felder` bei jedem Render neu baut.
  const felderRef = useRef(felder);
  felderRef.current = felder;
  // Signatur statt Array-Identität, sonst würde `bedingungen` bei jedem Render der Seite neu entstehen.
  const felderSignatur = felder.map((f) => `${f.key}:${f.typ}:${(f.operatoren ?? []).join(",")}`).join("|");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const bedingungen = useMemo(() => bedingungenAusUrl(fRoh, felderRef.current), [fRoh, felderSignatur]);

  const schreibeBedingungen = useCallback(
    (aendere: (alt: FilterBedingung[]) => FilterBedingung[]) => {
      setParams(
        (prev) => {
          const n = new URLSearchParams(prev);
          const neu = aendere(bedingungenAusUrl(prev.get(fParam), felderRef.current));
          if (neu.length > 0) n.set(fParam, bedingungenZuJson(neu));
          else n.delete(fParam);
          return n;
        },
        { replace: true },
      );
    },
    [setParams, fParam],
  );

  // Lokaler Eingabezustand: das Feld darf beim Tippen nicht auf einen verspätet eintreffenden URL-Stand zurückspringen.
  const [suche, setSucheLokal] = useState(qUrl);
  const zuletztGeschrieben = useRef(qUrl);
  useEffect(() => {
    if (qUrl !== zuletztGeschrieben.current) {
      zuletztGeschrieben.current = qUrl;
      setSucheLokal(qUrl);
    }
  }, [qUrl]);

  const setSuche = useCallback(
    (s: string) => {
      setSucheLokal(s);
      zuletztGeschrieben.current = s;
      setParams(
        (prev) => {
          const n = new URLSearchParams(prev);
          if (s) n.set(qParam, s);
          else n.delete(qParam);
          return n;
        },
        { replace: true },
      );
    },
    [setParams, qParam],
  );

  const setBedingungen = useCallback((b: FilterBedingung[]) => schreibeBedingungen(() => b), [schreibeBedingungen]);

  const hinzufuegen = useCallback(
    (b: FilterBedingung) =>
      schreibeBedingungen((alt) => {
        const feld = felderRef.current.find((f) => f.key === b.feld);
        const i = alt.findIndex((x) => x.feld === b.feld && x.op === "ist");
        if (feld && MISCHBAR.includes(feld.typ) && b.op === "ist" && i >= 0 && Array.isArray(b.wert)) {
          const vorhanden = Array.isArray(alt[i].wert) ? (alt[i].wert as string[]) : [];
          // Einzelwert-Felder (Backend kennt nur einen Wert) ersetzen statt zu mischen.
          const gemischt = feld.einzelwert ? b.wert : [...new Set([...vorhanden, ...b.wert])];
          return alt.map((x, j) => (j === i ? { ...x, wert: gemischt } : x));
        }
        return [...alt, b];
      }),
    [schreibeBedingungen],
  );

  const ersetzen = useCallback(
    (index: number, b: FilterBedingung) => schreibeBedingungen((alt) => alt.map((x, i) => (i === index ? b : x))),
    [schreibeBedingungen],
  );
  const entfernen = useCallback(
    (index: number) => schreibeBedingungen((alt) => alt.filter((_, i) => i !== index)),
    [schreibeBedingungen],
  );

  const zuruecksetzen = useCallback(() => {
    setSucheLokal("");
    zuletztGeschrieben.current = "";
    setParams(
      (prev) => {
        const n = new URLSearchParams(prev);
        n.delete(fParam);
        n.delete(qParam);
        return n;
      },
      { replace: true },
    );
  }, [setParams, fParam, qParam]);

  const sucheVerzoegert = useDebouncedValue(suche, 250);

  return {
    bedingungen,
    setBedingungen,
    hinzufuegen,
    ersetzen,
    entfernen,
    zuruecksetzen,
    suche,
    setSuche,
    sucheVerzoegert,
    aktiveAnzahl: bedingungen.length,
  };
}
