import { describe, expect, it } from "vitest";

import type { FilterBedingung } from "../filter/typen";
import { rechnungServerParameter } from "./rechnungenFilter";

describe("rechnungServerParameter", () => {
  it("bildet Status, Kunde und Art ab; 'ist nicht' wird zur Restmenge", () => {
    const b: FilterBedingung[] = [
      { feld: "status", op: "ist_nicht", wert: ["entwurf", "storniert"] },
      { feld: "kunde", op: "ist", wert: ["k1"] },
      { feld: "art", op: "ist", wert: "abschlag" },
    ];
    expect(rechnungServerParameter(b)).toMatchObject({
      status: ["versendet", "teilweise_bezahlt", "bezahlt"],
      kunde_id: "k1",
      rechnungsart: "abschlag",
    });
  });

  it("rechnet vor/nach/am/zwischen in von/bis um", () => {
    const p = rechnungServerParameter([
      { feld: "rechnungsdatum", op: "nach", wert: "2026-02-28" },
      { feld: "rechnungsdatum", op: "vor", wert: "2026-04-01" },
      { feld: "faellig", op: "am", wert: "2026-05-10" },
    ]);
    expect(p).toMatchObject({ von: "2026-03-01", bis: "2026-03-31", faellig_von: "2026-05-10", faellig_bis: "2026-05-10" });
    expect(
      rechnungServerParameter([{ feld: "faellig", op: "zwischen", wert: { von: "2026-01-01", bis: "2026-01-31" } }]),
    ).toMatchObject({ faellig_von: "2026-01-01", faellig_bis: "2026-01-31" });
  });

  it("'Fällig ist überfällig' wird zu nur_ueberfaellig", () => {
    const p = rechnungServerParameter([{ feld: "faellig", op: "relativ", wert: { relativ: "ueberfaellig" } }]);
    expect(p.nur_ueberfaellig).toBe(true);
    expect(p.faellig_bis).toBeUndefined();
  });

  it("wandelt Beträge in Punktschreibweise für das Backend", () => {
    expect(rechnungServerParameter([{ feld: "betrag", op: "gte", wert: "1.250,50" }])).toMatchObject({ betrag_von: "1250.5" });
    expect(
      rechnungServerParameter([{ feld: "betrag", op: "zwischen", wert: { von: "100", bis: "200,5" } }]),
    ).toMatchObject({ betrag_von: "100", betrag_bis: "200.5" });
  });
});
