// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VorgangTabLeiste } from "../VorgangTabLeiste";

afterEach(cleanup);

const ABSCHNITTE = [
  { ziel: "a-uebersicht", label: "Übersicht" },
  { ziel: "a-zeit", label: "Zeit" },
  { ziel: "a-maengel", label: "Mängel" },
  { ziel: "a-verlauf", label: "Verlauf" },
];

describe("VorgangTabLeiste", () => {
  it("zeigt Zähler nur bei Inhalt und Mängel rot", () => {
    render(
      <VorgangTabLeiste
        abschnitte={ABSCHNITTE}
        aktiv="a-uebersicht"
        onWaehle={vi.fn()}
        zaehler={{ "a-zeit": { text: "3,5 h" }, "a-maengel": { text: "2", warnung: true } }}
      />,
    );
    expect(screen.getByRole("tab", { name: /Zeit\s*:\s*3,5 h/ })).toBeTruthy();
    expect(screen.getByText("2", { exact: false }).className).toContain("text-st-fehlt");
    expect(screen.getByRole("tab", { name: "Verlauf" }).textContent).toBe("Verlauf");
    expect(screen.getByRole("tab", { name: "Übersicht" }).getAttribute("aria-selected")).toBe("true");
  });

  it("wechselt den Tab per Klick", () => {
    const onWaehle = vi.fn();
    render(<VorgangTabLeiste abschnitte={ABSCHNITTE} aktiv="a-uebersicht" onWaehle={onWaehle} zaehler={{}} />);
    fireEvent.click(screen.getByRole("tab", { name: "Zeit" }));
    expect(onWaehle).toHaveBeenCalledWith("a-zeit");
  });
});
