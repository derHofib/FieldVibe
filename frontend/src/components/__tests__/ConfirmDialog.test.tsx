// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { BestaetigungProvider, useBestaetigung } from "../ConfirmDialog";

let ergebnis: boolean | null = null;

function Ausloeser() {
  const bestaetigen = useBestaetigung();
  return (
    <button
      onClick={async () => {
        ergebnis = await bestaetigen({ titel: "Löschen?", text: "Folge X", bestaetigenLabel: "Endgültig löschen" });
      }}
    >
      los
    </button>
  );
}

function oeffne() {
  ergebnis = null;
  render(
    <BestaetigungProvider>
      <Ausloeser />
    </BestaetigungProvider>,
  );
  fireEvent.click(screen.getByText("los"));
}

describe("ConfirmDialog", () => {
  afterEach(cleanup);

  it("löst mit true beim Bestätigen auf", async () => {
    oeffne();
    expect(screen.getByRole("alertdialog").textContent).toContain("Folge X");
    fireEvent.click(screen.getByText("Endgültig löschen"));
    await waitFor(() => expect(ergebnis).toBe(true));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("löst mit false bei Escape auf, Fokus startet auf Abbrechen", async () => {
    oeffne();
    expect(document.activeElement?.textContent).toBe("Abbrechen");
    fireEvent.keyDown(screen.getByRole("alertdialog"), { key: "Escape" });
    await waitFor(() => expect(ergebnis).toBe(false));
  });

  it("hält Tab im Dialog", () => {
    oeffne();
    const ok = screen.getByText("Endgültig löschen");
    ok.focus();
    fireEvent.keyDown(ok, { key: "Tab" });
    expect(document.activeElement?.textContent).toBe("Abbrechen");
  });
});
