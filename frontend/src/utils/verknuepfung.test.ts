import { describe, expect, it } from "vitest";

import type { Auftrag, Vorgang } from "../types";
import { auftraegeFuerProjekt, auftragGewaehlt, gruppiereNachAuftrag, projektGewaehlt } from "./verknuepfung";

const auftrag = (id: string, projekt_id: string | null): Auftrag => ({ id, projekt_id, titel: `A-${id}`, status: "offen" }) as Auftrag;
const vorgang = (id: string, auftrag_id: string | null, status = "neu"): Vorgang =>
  ({ id, auftrag_id, projekt_id: "p1", status }) as Vorgang;

const AUFTRAEGE = [auftrag("a1", "p1"), auftrag("a2", "p2"), auftrag("a3", null)];

describe("Zuordnung ändern", () => {
  it("filtert die Auftragsliste auf das gewählte Projekt", () => {
    expect(auftraegeFuerProjekt(AUFTRAEGE, "p1").map((a) => a.id)).toEqual(["a1"]);
    expect(auftraegeFuerProjekt(AUFTRAEGE, "").map((a) => a.id)).toEqual(["a1", "a2", "a3"]);
  });

  it("Auftrag wählen setzt das Projekt des Auftrags", () => {
    expect(auftragGewaehlt(AUFTRAEGE, { projektId: "", auftragId: "" }, "a2")).toEqual({ projektId: "p2", auftragId: "a2" });
    expect(auftragGewaehlt(AUFTRAEGE, { projektId: "p1", auftragId: "a1" }, "a3")).toEqual({ projektId: "", auftragId: "a3" });
  });

  it("Projektwechsel verwirft einen Auftrag aus einem anderen Projekt", () => {
    expect(projektGewaehlt(AUFTRAEGE, { projektId: "p1", auftragId: "a1" }, "p2")).toEqual({ projektId: "p2", auftragId: "" });
    expect(projektGewaehlt(AUFTRAEGE, { projektId: "p1", auftragId: "a1" }, "p1")).toEqual({ projektId: "p1", auftragId: "a1" });
  });
});

describe("gruppiereNachAuftrag", () => {
  it("gruppiert je Auftrag, zählt erledigte und sammelt Vorgänge ohne Auftrag", () => {
    const { gruppen, ohneAuftrag } = gruppiereNachAuftrag(
      [auftrag("a1", "p1"), auftrag("a2", "p1")],
      [vorgang("v1", "a1", "abgeschlossen"), vorgang("v2", "a1"), vorgang("v3", null), vorgang("v4", "fremd")],
    );
    expect(gruppen.map((g) => [g.auftrag.id, g.vorgaenge.length, g.erledigt])).toEqual([
      ["a1", 2, 1],
      ["a2", 0, 0],
    ]);
    expect(ohneAuftrag.map((v) => v.id)).toEqual(["v3", "v4"]);
  });
});
