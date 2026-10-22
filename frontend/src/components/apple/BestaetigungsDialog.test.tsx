// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BestaetigungsDialog, BestaetigungsHost, bestaetigen } from "./BestaetigungsDialog";

afterEach(cleanup);

describe("BestaetigungsDialog", () => {
  function zeige(teil: Partial<Parameters<typeof BestaetigungsDialog>[0]> = {}) {
    const onBestaetigen = vi.fn();
    const onAbbrechen = vi.fn();
    render(
      <>
        <button>Ausloeser</button>
        <BestaetigungsDialog
          titel="Löschen?"
          text="Rechnung wirklich löschen?"
          bestaetigenLabel="Löschen"
          destruktiv
          onBestaetigen={onBestaetigen}
          onAbbrechen={onAbbrechen}
          {...teil}
        />
      </>,
    );
    return { onBestaetigen, onAbbrechen };
  }

  it("ist ein alertdialog mit Titel und Beschreibung", () => {
    zeige();
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName("Löschen?");
    expect(dialog).toHaveAccessibleDescription("Rechnung wirklich löschen?");
  });

  it("fokussiert zuerst Abbrechen", () => {
    zeige();
    expect(screen.getByRole("button", { name: "Abbrechen" })).toHaveFocus();
  });

  it("Escape bricht ab, Klick auf Bestaetigen bestaetigt", () => {
    const { onBestaetigen, onAbbrechen } = zeige();
    fireEvent.keyDown(screen.getByRole("alertdialog"), { key: "Escape" });
    expect(onAbbrechen).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Löschen" }));
    expect(onBestaetigen).toHaveBeenCalledTimes(1);
  });

  it("Klick auf den Hintergrund bricht ab, Klick im Dialog nicht", () => {
    const { onAbbrechen } = zeige();
    fireEvent.click(screen.getByRole("alertdialog"));
    expect(onAbbrechen).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("alertdialog").parentElement!);
    expect(onAbbrechen).toHaveBeenCalledTimes(1);
  });

  it("haelt Tab im Dialog (vorwaerts und rueckwaerts)", () => {
    zeige();
    const bestaetigenKnopf = screen.getByRole("button", { name: "Löschen" });
    const abbrechen = screen.getByRole("button", { name: "Abbrechen" });
    abbrechen.focus();
    fireEvent.keyDown(abbrechen, { key: "Tab" });
    expect(bestaetigenKnopf).toHaveFocus();
    fireEvent.keyDown(bestaetigenKnopf, { key: "Tab", shiftKey: true });
    expect(abbrechen).toHaveFocus();
  });

  it("gibt den Fokus beim Schliessen zurueck", () => {
    const { unmount } = render(<button>Ausloeser</button>);
    const knopf = screen.getByRole("button", { name: "Ausloeser" });
    knopf.focus();
    const dialog = render(
      <BestaetigungsDialog titel="T" text="t" bestaetigenLabel="OK" onBestaetigen={() => {}} onAbbrechen={() => {}} />,
    );
    expect(screen.getByRole("button", { name: "Abbrechen" })).toHaveFocus();
    dialog.unmount();
    expect(knopf).toHaveFocus();
    unmount();
  });
});

describe("bestaetigen + BestaetigungsHost", () => {
  it("loest mit true bei Bestaetigung und false bei Abbruch auf", async () => {
    render(<BestaetigungsHost />);
    const erste = bestaetigen("Rechnung wirklich löschen?");
    fireEvent.click(await screen.findByRole("button", { name: "Löschen" }));
    await expect(erste).resolves.toBe(true);
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());

    const zweite = bestaetigen("Rechnung wirklich löschen?");
    fireEvent.click(await screen.findByRole("button", { name: "Abbrechen" }));
    await expect(zweite).resolves.toBe(false);
  });

  it("leitet Beschriftung und Variante aus dem Text ab", async () => {
    render(<BestaetigungsHost />);
    void bestaetigen("Diese Rechnung stornieren? Es wird eine Stornorechnung erzeugt.");
    expect(await screen.findByRole("button", { name: "Stornieren" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Abbrechen" }));

    void bestaetigen("Formular abschließen? Danach nicht mehr bearbeitbar.");
    expect(await screen.findByRole("button", { name: "Bestätigen" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Abbrechen" }));
  });

  it("stellt parallele Rueckfragen hintereinander", async () => {
    render(<BestaetigungsHost />);
    const a = bestaetigen("Erstes löschen?");
    const b = bestaetigen("Zweites löschen?");
    expect(await screen.findByText("Erstes löschen?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Löschen" }));
    await expect(a).resolves.toBe(true);
    expect(await screen.findByText("Zweites löschen?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Abbrechen" }));
    await expect(b).resolves.toBe(false);
  });

  it("lehnt ohne Host ab statt zu haengen", async () => {
    await expect(bestaetigen("Egal?")).resolves.toBe(false);
  });
});
