// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AufgabePfad, pfadGlieder } from "./AufgabePfad";

const BASIS = { vorgang_id: null, vorgang_vorgangsnummer: null, auftrag_id: null, auftrag_titel: null, projekt_id: null };
const VOLL = {
  ...BASIS,
  vorgang_id: "v1",
  vorgang_vorgangsnummer: "V-1012",
  auftrag_titel: "Elektro",
  pfad_auftrag_id: "au1",
  pfad_projekt_id: "p1",
  pfad_projekt_name: "Neubau Kita",
};

describe("AufgabePfad", () => {
  it("zeigt Projekt, Auftrag und Vorgang als Kette", () => {
    expect(pfadGlieder(VOLL, true).map((g) => g.ziel)).toEqual(["/projekte?projekt=p1", "/auftraege?auftrag=au1", "/vorgaenge/v1"]);
  });
  it("macht ohne Recht nur den Vorgang zum Link", () => {
    expect(pfadGlieder(VOLL, false).map((g) => g.ziel)).toEqual([null, null, "/vorgaenge/v1"]);
  });
  it("zeigt einen Strich ohne Bezug", () => {
    render(<AufgabePfad aufgabe={BASIS} linksAktiv navigate={() => {}} />);
    expect(screen.getByText("–")).toBeTruthy();
  });
  it("navigiert beim Klick auf ein Glied und stoppt die Weitergabe", () => {
    const navigate = vi.fn();
    const zeile = vi.fn();
    render(
      <div onClick={zeile}>
        <AufgabePfad aufgabe={VOLL} linksAktiv navigate={navigate} />
      </div>,
    );
    fireEvent.click(screen.getByText("V-1012"));
    expect(navigate).toHaveBeenCalledWith("/vorgaenge/v1");
    expect(zeile).not.toHaveBeenCalled();
  });
});
