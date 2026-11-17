import { useCallback, useState } from "react";

import type { FilterZustand } from "./useFilterZustand";
import { OPERATOREN_OHNE_WERT, operatorenFuer, type FilterBedingung, type FilterFeld, type FilterOperator, type FilterWert, type RelativerZeitraum } from "./typen";

export interface Entwurf {
  /** null = neue Bedingung, sonst Index der bearbeiteten. */
  index: number | null;
  feldKey: string | null;
  op: FilterOperator | null;
  wert: FilterWert | undefined;
  schritt: 1 | 2 | 3;
}

const MIT_OPTIONEN = ["auswahl", "verknuepfung", "person", "liste"];

function istRelativ(w: FilterWert | undefined): w is { relativ: RelativerZeitraum } {
  return !!w && typeof w === "object" && !Array.isArray(w) && "relativ" in w;
}

function alsBereich(w: FilterWert | undefined): { von?: string; bis?: string } | null {
  return w && typeof w === "object" && !Array.isArray(w) && !("relativ" in w) ? w : null;
}

/** Wert beim Wechsel des Operators in die passende Form bringen (Einzelwert, Bereich, relativ). */
function wertFuer(op: FilterOperator, wert: FilterWert | undefined): FilterWert | undefined {
  const bereich = alsBereich(wert);
  if (op === "zwischen") return typeof wert === "string" ? { von: wert } : (bereich ?? undefined);
  if (op === "relativ") return istRelativ(wert) ? wert : undefined;
  if (typeof wert === "string" || Array.isArray(wert)) return wert;
  return bereich?.von;
}

function wertVollstaendig(op: FilterOperator, wert: FilterWert | undefined): boolean {
  if (OPERATOREN_OHNE_WERT.includes(op)) return true;
  if (typeof wert === "string") return wert.trim() !== "";
  if (Array.isArray(wert)) return wert.length > 0;
  if (istRelativ(wert)) return true;
  const bereich = alsBereich(wert);
  return !!bereich && (!!bereich.von || !!bereich.bis);
}

/** Zustand des Anlege-/Bearbeiten-Ablaufs (Spalte -> Bedingung -> Wert), gemeinsam für Office-Popover und Feld-Sheet. */
export function useFilterEntwurf<T>(felder: FilterFeld<T>[], zustand: FilterZustand) {
  const [entwurf, setEntwurf] = useState<Entwurf | null>(null);
  const feld = entwurf?.feldKey ? (felder.find((f) => f.key === entwurf.feldKey) ?? null) : null;

  const schliessen = useCallback(() => setEntwurf(null), []);
  const starten = useCallback(() => setEntwurf({ index: null, feldKey: null, op: null, wert: undefined, schritt: 1 }), []);

  const bearbeiten = useCallback(
    (index: number, schritt: 1 | 2 | 3) => {
      const b = zustand.bedingungen[index];
      if (!b) return;
      setEntwurf({ index, feldKey: b.feld, op: b.op, wert: b.wert, schritt });
    },
    [zustand.bedingungen],
  );

  const festschreiben = useCallback(
    (b: FilterBedingung, index: number | null) => {
      if (index === null) zustand.hinzufuegen(b);
      else zustand.ersetzen(index, b);
      setEntwurf(null);
    },
    [zustand],
  );

  const zurueck = useCallback(() => {
    setEntwurf((e) => {
      if (!e || e.schritt === 1) return e;
      const f = felder.find((x) => x.key === e.feldKey);
      return { ...e, schritt: e.schritt === 3 && f?.typ !== "janein" ? 2 : 1 };
    });
  }, [felder]);

  const waehleFeld = useCallback(
    (neu: FilterFeld<T>) => {
      if (!entwurf) return;
      // Wert und Bedingung überleben den Spaltenwechsel nur bei gleichem Typ; Optionslisten gehören zur Spalte.
      const behalten = !!feld && feld.typ === neu.typ && (feld.key === neu.key || !MIT_OPTIONEN.includes(neu.typ));
      let op = behalten ? entwurf.op : null;
      let wert = behalten ? entwurf.wert : undefined;
      if (neu.typ === "janein") op = "ist";
      if (op && !operatorenFuer(neu).includes(op)) {
        op = null;
        wert = undefined;
      }
      if (op && OPERATOREN_OHNE_WERT.includes(op)) {
        festschreiben({ feld: neu.key, op }, entwurf.index);
        return;
      }
      setEntwurf({ ...entwurf, feldKey: neu.key, op, wert, schritt: op ? 3 : 2 });
    },
    [entwurf, feld, festschreiben],
  );

  const waehleOperator = useCallback(
    (op: FilterOperator) => {
      if (!entwurf || !entwurf.feldKey) return;
      if (OPERATOREN_OHNE_WERT.includes(op)) {
        festschreiben({ feld: entwurf.feldKey, op }, entwurf.index);
        return;
      }
      setEntwurf({ ...entwurf, op, wert: wertFuer(op, entwurf.wert), schritt: 3 });
    },
    [entwurf, festschreiben],
  );

  /** Operator im Wert-Schritt wechseln (Segment), ohne den Schritt zu verlassen. */
  const setOp = useCallback((op: FilterOperator) => {
    setEntwurf((e) => (e ? { ...e, op, wert: wertFuer(op, e.wert) } : e));
  }, []);

  const setWert = useCallback((wert: FilterWert | undefined) => {
    setEntwurf((e) => (e ? { ...e, wert } : e));
  }, []);

  /** Übernimmt den Entwurf; `ueberschreibe` für Schnellauswahl/Vorschlag/Ja-Nein, die sofort übernehmen. */
  const uebernehmen = useCallback(
    (ueberschreibe?: { op?: FilterOperator; wert?: FilterWert }): boolean => {
      if (!entwurf || !entwurf.feldKey) return false;
      const op = ueberschreibe?.op ?? entwurf.op;
      if (!op) return false;
      let wert = ueberschreibe && "wert" in ueberschreibe ? ueberschreibe.wert : entwurf.wert;
      if (typeof wert === "string") wert = wert.trim();
      if (!wertVollstaendig(op, wert)) return false;
      festschreiben(
        OPERATOREN_OHNE_WERT.includes(op) ? { feld: entwurf.feldKey, op } : { feld: entwurf.feldKey, op, wert },
        entwurf.index,
      );
      return true;
    },
    [entwurf, festschreiben],
  );

  return { entwurf, feld, starten, bearbeiten, schliessen, zurueck, waehleFeld, waehleOperator, setOp, setWert, uebernehmen };
}

export type FilterEntwurfZustand<T> = ReturnType<typeof useFilterEntwurf<T>>;
