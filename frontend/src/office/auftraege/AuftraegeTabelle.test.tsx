// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import type { Auftrag } from "../../types";
import { AuftraegeTabelle } from "./AuftraegeTabelle";

afterEach(cleanup);

const BASIS = { kunde_name: "Herdrich", status: "offen", created_at: "2026-11-03T00:00:00Z", beschreibung: null, kunde_id: null };
const AUFTRAEGE = [
  { ...BASIS, id: "a1", titel: "Wärmepumpe", projekt_id: "p1", projekt_name: "Heizungstausch", vorgaenge_gesamt: 4, vorgaenge_erledigt: 1 },
  { ...BASIS, id: "a2", titel: "Trailer", projekt_id: null, projekt_name: null, vorgaenge_gesamt: 1, vorgaenge_erledigt: 0 },
] as Auftrag[];

describe("AuftraegeTabelle", () => {
  it("zeigt die Projektspalte als Link und Vorgänge als erledigt / gesamt", () => {
    render(
      <MemoryRouter>
        <AuftraegeTabelle auftraege={AUFTRAEGE} onZeileKlick={() => undefined} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("columnheader", { name: /Projekt/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Heizungstausch" }).getAttribute("href")).toBe("/projekte?projekt=p1");
    expect(screen.getByText("1 / 4")).toBeTruthy();
    expect(screen.getByText("0 / 1")).toBeTruthy();
  });

  it("nimmt den Projektnamen aus der Projektliste, wenn der Server ihn noch nicht liefert", () => {
    const ohneName = [{ ...AUFTRAEGE[0], projekt_name: undefined }] as Auftrag[];
    render(
      <MemoryRouter>
        <AuftraegeTabelle auftraege={ohneName} onZeileKlick={() => undefined} projektNamen={new Map([["p1", "Aus Liste"]])} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Aus Liste" })).toBeTruthy();
  });
});
