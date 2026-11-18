// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Projekt } from "../../types";
import { ProjekteTabelle } from "./ProjekteTabelle";

afterEach(cleanup);

const BASIS = { archiviert: false, created_at: "2026-11-02T00:00:00Z" };

describe("ProjekteTabelle", () => {
  it("zeigt Umfang und Pille offen bzw. alle erledigt, ohne Zähler einen Strich", () => {
    render(
      <ProjekteTabelle
        onZeileKlick={() => undefined}
        projekte={[
          { ...BASIS, id: "1", name: "A", anzahl_auftraege: 3, anzahl_vorgaenge: 9, anzahl_offen: 5 },
          { ...BASIS, id: "2", name: "B", anzahl_auftraege: 0, anzahl_vorgaenge: 6, anzahl_offen: 0 },
          { ...BASIS, id: "3", name: "C" },
        ] as Projekt[]}
      />,
    );
    expect(screen.getByText("3 Aufträge · 9 Vorgänge")).toBeTruthy();
    expect(screen.getByText("5 offen")).toBeTruthy();
    expect(screen.getByText("alle erledigt")).toBeTruthy();
    expect(screen.getAllByText("—").length).toBe(2);
  });
});
