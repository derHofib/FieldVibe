// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { sichtbareAnker } from "../konstanten";
import { VerknuepfungPfad } from "../VerknuepfungPfad";

afterEach(cleanup);

const BASIS = { projekt_id: "p1", projekt_name: "Heizungstausch", auftrag_id: "a1", auftrag_titel: "Wärmepumpe", verknuepfung_eigenstaendig: false };

describe("VerknuepfungPfad", () => {
  it("zeigt Projekt und Auftrag als Links, wenn Links aktiv sind", () => {
    const navigate = vi.fn();
    render(<VerknuepfungPfad vorgang={BASIS} linksAktiv navigate={navigate} />);
    fireEvent.click(screen.getByRole("button", { name: "Heizungstausch" }));
    fireEvent.click(screen.getByRole("button", { name: "Wärmepumpe" }));
    expect(navigate).toHaveBeenNthCalledWith(1, "/projekte?projekt=p1");
    expect(navigate).toHaveBeenNthCalledWith(2, "/auftraege?auftrag=a1");
  });

  it("zeigt nur das Projekt, wenn es keinen Auftrag gibt", () => {
    render(<VerknuepfungPfad vorgang={{ ...BASIS, auftrag_id: null, auftrag_titel: null }} linksAktiv navigate={vi.fn()} />);
    expect(screen.getByText("Heizungstausch")).toBeTruthy();
    expect(screen.queryByText("Wärmepumpe")).toBeNull();
  });

  it("ist ohne Recht bzw. in der Feld-App reiner Text", () => {
    render(<VerknuepfungPfad vorgang={BASIS} linksAktiv={false} navigate={vi.fn()} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("Heizungstausch")).toBeTruthy();
  });

  it("zeigt nichts ohne Projekt und Auftrag", () => {
    const { container } = render(
      <VerknuepfungPfad vorgang={{ ...BASIS, projekt_id: null, projekt_name: null, auftrag_id: null, auftrag_titel: null }} linksAktiv navigate={vi.fn()} />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("ersetzt den Pfad bei eigenständiger Führung durch das Kennzeichen", () => {
    render(<VerknuepfungPfad vorgang={{ ...BASIS, verknuepfung_eigenstaendig: true }} linksAktiv navigate={vi.fn()} />);
    expect(screen.getByText(/Eigenständig geführt · Rückmeldung an Wärmepumpe aktiv/)).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("Tab Projekt", () => {
  it("steht nur bei Zugehörigkeit zwischen Positionen und Verlauf", () => {
    const mit = sichtbareAnker(true).map((a) => a.label);
    expect(mit.slice(mit.indexOf("Positionen"), mit.indexOf("Verlauf") + 1)).toEqual(["Positionen", "Projekt", "Verlauf"]);
    expect(sichtbareAnker(false).map((a) => a.label)).not.toContain("Projekt");
  });
});
