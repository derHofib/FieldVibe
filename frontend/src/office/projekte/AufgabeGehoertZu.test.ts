import { describe, expect, it } from "vitest";

import type { Auftrag, ProjektAufgabe, Vorgang } from "../../types";
import { gehoertZuKette } from "./AufgabeGehoertZu";

const aufgabe = (teil: Partial<ProjektAufgabe>) => ({ projekt_id: null, vorgang_id: null, auftrag_id: null, ...teil }) as ProjektAufgabe;
const vorgang = (teil: Partial<Vorgang>) => ({ id: "v2", vorgangsnummer: "V-2", titel: "Neu", status: "neu", ...teil }) as Vorgang;

describe("gehoertZuKette", () => {
  it("übernimmt den Pfad vom Server, solange nichts geändert ist", () => {
    const a = aufgabe({
      vorgang_id: "v1",
      vorgang_vorgangsnummer: "V-1012",
      vorgang_status: "geplant",
      auftrag_titel: "Elektro",
      auftrag_status: "in_arbeit",
      pfad_auftrag_id: "au1",
      pfad_projekt_id: "p1",
      pfad_projekt_name: "Neubau Kita",
      pfad_abweichung_projekt_name: "Anderes",
    });
    const k = gehoertZuKette({ aufgabe: a, vorgangId: "v1", auftragId: "" });
    expect(k.projekt).toEqual({ id: "p1", name: "Neubau Kita" });
    expect(k.auftrag?.status).toBe("in_arbeit");
    expect(k.vorgang?.nummer).toBe("V-1012");
    expect(k.abweichung).toBe("Anderes");
  });
  it("leitet bei neuer Vorgang-Wahl Projekt und Auftrag aus dem Vorgang ab", () => {
    const v = vorgang({ projekt_id: "p9", projekt_name: "Wartung", auftrag_id: "au9", auftrag_titel: "A9" });
    const k = gehoertZuKette({ aufgabe: null, vorgangId: "v2", auftragId: "", vorgaenge: [v] });
    expect(k.projekt?.name).toBe("Wartung");
    expect(k.auftrag?.titel).toBe("A9");
    expect(k.vorgang?.id).toBe("v2");
  });
  it("Kanban-Karte behält ihr Projekt und zeigt den Hinweis bei abweichendem Vorgangsprojekt", () => {
    const a = aufgabe({ projekt_id: "p1", pfad_projekt_id: "p1", pfad_projekt_name: "Board" });
    const v = vorgang({ projekt_id: "p9", projekt_name: "Wartung" });
    const k = gehoertZuKette({ aufgabe: a, vorgangId: "v2", auftragId: "", vorgaenge: [v] });
    expect(k.projekt?.name).toBe("Board");
    expect(k.abweichung).toBe("Wartung");
  });
  it("Auftrag ohne Vorgang: Projekt des Auftrags, kein Vorgang", () => {
    const au = { id: "au1", titel: "Elektro", status: "offen", projekt_id: "p1", projekt_name: "Kita" } as Auftrag;
    const k = gehoertZuKette({ aufgabe: null, vorgangId: "", auftragId: "au1", auftraege: [au] });
    expect(k.projekt?.name).toBe("Kita");
    expect(k.auftrag).toEqual({ id: "au1", titel: "Elektro", status: "offen" });
    expect(k.vorgang).toBeNull();
  });
  it("ohne Bezug ist die Kette leer", () => {
    const k = gehoertZuKette({ aufgabe: null, vorgangId: "", auftragId: "" });
    expect(k).toEqual({ projekt: null, auftrag: null, vorgang: null, abweichung: null });
  });
});
