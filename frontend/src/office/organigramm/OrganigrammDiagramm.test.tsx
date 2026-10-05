// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import type { Position } from "../../types/organigramm";
import { OrganigrammDiagramm } from "./OrganigrammDiagramm";

// React Flow misst Knoten per ResizeObserver; jsdom kennt ihn nicht.
beforeAll(() => {
  class RO {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", RO);
  vi.stubGlobal("DOMMatrixReadOnly", class { m22 = 1; constructor() {} });
});
afterEach(cleanup);

const p = (id: string, parent: string | null, titel: string, extra: Partial<Position> = {}): Position => ({
  id,
  parent_id: parent,
  titel,
  typ: "linie",
  status: "vakant",
  geplant: false,
  soll_besetzung: 1,
  ist_besetzung: 0,
  besetzungen: [],
  ...extra,
});

const POSITIONEN: Position[] = [
  p("w", null, "Geschäftsführung", { status: "besetzt", ist_besetzung: 1, besetzungen: [{ id: "b", user_id: "u", name: "Max Muster", art: "regulaer", gueltig_von: "2026-01-01T00:00:00Z", gueltig_bis: null }] }),
  p("t", "w", "Technik", { account_typ: { id: "a", name: "Bereichsleiter" } }),
  p("s", "w", "Datenschutz", { typ: "stabsstelle" }),
  p("g", "t", "Montage", { status: "geplant", geplant: true }),
];

function rendere(extra: Partial<React.ComponentProps<typeof OrganigrammDiagramm>> = {}) {
  const alle = new Set(POSITIONEN.map((x) => x.id));
  return render(
    <div style={{ width: 1000, height: 600 }}>
      <OrganigrammDiagramm
        positionen={POSITIONEN}
        sichtbar={alle}
        treffer={alle}
        filterAktiv={false}
        eingeklappt={new Set()}
        ausgewaehltId={null}
        darfUmhaengen
        onWaehlen={() => {}}
        onMenue={() => {}}
        onUmschalten={() => {}}
        onUmhaengen={() => {}}
        onUngueltigerDrop={() => {}}
        {...extra}
      />
    </div>,
  );
}

describe("OrganigrammDiagramm", () => {
  it("rendert Knotenkarten mit Status, Badges und Soll/Ist", () => {
    rendere();
    expect(screen.getByText("Geschäftsführung")).toBeTruthy();
    expect(screen.getByText("Max Muster")).toBeTruthy();
    expect(screen.getByText("Bereichsleiter")).toBeTruthy();
    expect(screen.getByText("Stab")).toBeTruthy();
    expect(screen.getByText("Platzhalter", { selector: "span.rounded-full" })).toBeTruthy();
    expect(screen.getAllByText("vakant").length).toBeGreaterThan(0);
  });

  it("blendet zugeklappte Teilbaeume aus und zeigt die Kinderzahl am Umschalter", () => {
    const onUmschalten = vi.fn();
    rendere({ eingeklappt: new Set(["t"]), onUmschalten });
    expect(screen.queryByText("Montage")).toBeNull();
    fireEvent.click(screen.getByLabelText(/Aufklappen: Technik/));
    expect(onUmschalten).toHaveBeenCalledWith("t");
  });

  it("meldet Klick auf den Titel und oeffnet das Menue ueber den ...-Button", () => {
    const onWaehlen = vi.fn();
    const onMenue = vi.fn();
    rendere({ onWaehlen, onMenue });
    fireEvent.click(screen.getByTitle("Technik"));
    expect(onWaehlen).toHaveBeenCalledWith("t");
    fireEvent.click(screen.getByLabelText("Aktionen für Technik"));
    expect(onMenue).toHaveBeenCalledWith(expect.objectContaining({ id: "t" }), expect.any(Object));
  });
});
