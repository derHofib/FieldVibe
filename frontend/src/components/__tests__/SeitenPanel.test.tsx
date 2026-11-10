// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SeitenPanel } from "../SeitenPanel";

describe("SeitenPanel", () => {
  afterEach(cleanup);

  it("rendert nichts, solange es geschlossen ist", () => {
    render(
      <SeitenPanel offen={false} titel="Neu" onClose={() => {}}>
        <input aria-label="Name" />
      </SeitenPanel>,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("fokussiert das erste Feld und schließt per Escape", () => {
    const onClose = vi.fn();
    render(
      <SeitenPanel offen titel="Neuer Kunde" onClose={onClose}>
        <input aria-label="Name" />
      </SeitenPanel>,
    );
    expect(screen.getByRole("dialog", { name: "Neuer Kunde" })).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByLabelText("Name"));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
