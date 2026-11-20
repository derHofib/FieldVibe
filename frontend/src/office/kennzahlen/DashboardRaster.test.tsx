// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DashboardWidget } from "../../types/kennzahlen";
import { DashboardRaster } from "./DashboardRaster";

afterEach(cleanup);

const widget = (id: string): DashboardWidget => ({
  id, kennzahl: "vorgaenge.offen", darstellung: "zahl", gruppierung: null, groesse: "s", titel: null, vergleich: false,
});

describe("DashboardRaster", () => {
  it("Ansichtsmodus: keine Griffe, Karteninhalt per Tastatur erreichbar", () => {
    render(
      <DashboardRaster
        widgets={[widget("a"), widget("b")]}
        bearbeiten={false}
        onReihenfolge={() => undefined}
        renderWidget={(w) => <button type="button">Menü {w.id}</button>}
      />,
    );
    expect(screen.queryByRole("button", { name: "Widget verschieben" })).not.toBeInTheDocument();
    screen.getByRole("button", { name: "Menü a" }).focus();
    expect(screen.getByRole("button", { name: "Menü a" })).toHaveFocus();
  });

  it("Bearbeiten: Griffe sind fokussierbar und per Leertaste aufnehmbar (Tastatur-Sensor aktiv)", async () => {
    render(
      <DashboardRaster
        widgets={[widget("a"), widget("b")]}
        bearbeiten
        onReihenfolge={vi.fn()}
        renderWidget={(w, { griff }) => <div>{griff}{w.id}</div>}
      />,
    );
    const griffe = screen.getAllByRole("button", { name: "Widget verschieben" });
    expect(griffe).toHaveLength(2);
    griffe[0].focus();
    expect(griffe[0]).toHaveFocus();
    expect(griffe[0]).toHaveAttribute("aria-roledescription", "sortable");
    fireEvent.keyDown(griffe[0], { code: "Space", key: " " });
    // Tastatur-Anleitung für Screenreader ist vorhanden, die Aufnahme setzt aria-pressed.
    expect(document.body.textContent).toMatch(/To pick up a draggable item/);
    await waitFor(() => expect(griffe[0]).toHaveAttribute("aria-pressed", "true"));
  });
});
