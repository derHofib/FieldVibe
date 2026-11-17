// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AktionsMenue } from "./AktionsMenue";

afterEach(cleanup);

describe("AktionsMenue Auswahl-Einträge", () => {
  it("markiert die aktuelle Wahl, wählt per Klick und schließt mit Escape", () => {
    const wechseln = vi.fn();
    render(
      <AktionsMenue
        label="Benutzermenü"
        eintraege={[
          { label: "Workspace: Operativ", aktiv: true, onClick: () => undefined },
          { label: "Workspace: Sales", aktiv: false, onClick: wechseln },
        ]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Benutzermenü" }));
    expect(screen.getByRole("menuitemradio", { name: "Workspace: Operativ" }).getAttribute("aria-checked")).toBe("true");
    expect(screen.getByRole("menuitemradio", { name: "Workspace: Sales" }).getAttribute("aria-checked")).toBe("false");

    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Benutzermenü" }));
    fireEvent.click(screen.getByRole("menuitemradio", { name: "Workspace: Sales" }));
    expect(wechseln).toHaveBeenCalledTimes(1);
  });
});
