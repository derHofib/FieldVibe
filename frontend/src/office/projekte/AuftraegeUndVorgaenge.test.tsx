// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Auftrag, Vorgang } from "../../types";
import { AuftraegeUndVorgaenge } from "./AuftraegeUndVorgaenge";

afterEach(cleanup);

const auftrag = (id: string, titel: string, status: string) => ({ id, titel, status, projekt_id: "p1" }) as Auftrag;
const vorgang = (id: string, nr: string, auftrag_id: string | null, status = "neu", extra = {}) =>
  ({ id, vorgangsnummer: nr, titel: `T-${nr}`, auftrag_id, status, ...extra }) as Vorgang;

function rendern(navigate = vi.fn()) {
  render(
    <AuftraegeUndVorgaenge
      projektId="p1"
      laedt={false}
      navigate={navigate}
      auftraege={[auftrag("a1", "Offener Auftrag", "in_arbeit"), auftrag("a2", "Fertiger Auftrag", "abgeschlossen")]}
      vorgaenge={[
        vorgang("v1", "V-1", "a1", "abgeschlossen"),
        vorgang("v2", "V-2", "a1", "neu", { verknuepfung_eigenstaendig: true }),
        vorgang("v3", "V-3", "a2", "abgeschlossen"),
        vorgang("v4", "V-4", null),
      ]}
    />,
  );
  return navigate;
}

describe("AuftraegeUndVorgaenge", () => {
  it("klappt offene Aufträge auf, abgeschlossene zu, und zeigt Fortschritt", () => {
    rendern();
    expect(screen.getByText("T-V-1")).toBeTruthy();
    expect(screen.queryByText("T-V-3")).toBeNull();
    expect(screen.getByText("1 / 2 erledigt")).toBeTruthy();
    expect(screen.getByText("1 / 1 erledigt")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Fertiger Auftrag aufklappen" }));
    expect(screen.getByText("T-V-3")).toBeTruthy();
  });

  it("zeigt die Gruppe Ohne Auftrag und das Schloss für eigenständige Vorgänge", () => {
    rendern();
    expect(screen.getByText("Ohne Auftrag")).toBeTruthy();
    expect(screen.getByText("T-V-4")).toBeTruthy();
    expect(screen.getAllByText("eigenständig")).toHaveLength(1);
  });

  it("öffnet Auftrag, Vorgang und das Anlegen mit vorbelegtem Auftrag", () => {
    const navigate = rendern();
    fireEvent.click(screen.getByRole("button", { name: "Offener Auftrag" }));
    fireEvent.click(screen.getByText("T-V-1"));
    fireEvent.click(screen.getByRole("button", { name: "+ Vorgang in diesem Auftrag" }));
    expect(navigate).toHaveBeenNthCalledWith(1, "/auftraege?auftrag=a1");
    expect(navigate).toHaveBeenNthCalledWith(2, "/vorgaenge/v1/vollbild");
    expect(navigate).toHaveBeenNthCalledWith(3, "/neu?auftrag_id=a1");
  });
});
