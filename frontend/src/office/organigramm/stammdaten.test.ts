import { describe, expect, it } from "vitest";

import type { Position } from "../../types/organigramm";
import { formAusPosition, updateAusFormular } from "./stammdaten";

const p: Position = {
  id: "p",
  parent_id: "w",
  titel: "Teamleitung",
  typ: "linie",
  status: "vakant",
  geplant: false,
  soll_besetzung: 1,
  ebene: 2,
  org_einheit: { id: "e1", name: "Technik", typ: "bereich" },
  account_typ: { id: "t1", name: "Teamleiter" },
  gueltig_ab: null,
  gueltig_bis: null,
  reihenfolge: 0,
};

describe("updateAusFormular", () => {
  it("sendet bei unveraendertem Formular nichts", () => {
    expect(updateAusFormular(p, formAusPosition(p))).toEqual({});
  });

  it("sendet nur geaenderte Felder und null fuer geleerte Auswahlen", () => {
    const form = { ...formAusPosition(p), titel: " Leitung ", orgEinheitId: "", ebene: "", sollBesetzung: "3", geplant: true, gueltigBis: "2027-01-31" };
    expect(updateAusFormular(p, form)).toEqual({
      titel: "Leitung",
      org_einheit_id: null,
      ebene: null,
      soll_besetzung: 3,
      geplant: true,
      gueltig_bis: "2027-01-31",
    });
  });

  it("verhindert negative Soll-Besetzung", () => {
    expect(updateAusFormular(p, { ...formAusPosition(p), sollBesetzung: "-2" }).soll_besetzung).toBe(0);
  });
});
