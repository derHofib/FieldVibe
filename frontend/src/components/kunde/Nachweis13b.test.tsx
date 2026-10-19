// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { datumZuIso, heuteIso } from "../../utils/format";
import { Nachweis13bFeld } from "./Nachweis13b";

afterEach(cleanup);

describe("Nachweis13bFeld", () => {
  it("zeigt Hilfetext und Status ohne Eintrag", () => {
    render(<Nachweis13bFeld wert="" onChange={() => {}} />);
    expect(screen.getByLabelText("§ 13b: Nachweis USt 1 TG gültig bis")).toHaveValue("");
    expect(screen.getByText(/nur für Reverse-Charge-Rechnungen nötig/)).toBeInTheDocument();
    expect(screen.getByText("Kein Nachweis hinterlegt")).toBeInTheDocument();
  });

  it("meldet abgelaufene Nachweise mit Text (nicht nur Farbe)", () => {
    const gestern = new Date();
    gestern.setDate(gestern.getDate() - 1);
    render(<Nachweis13bFeld wert={datumZuIso(gestern)} onChange={() => {}} />);
    expect(screen.getByText(/^Abgelaufen am /)).toBeInTheDocument();
  });

  it("meldet den heutigen Tag als letzten gültigen Tag", () => {
    render(<Nachweis13bFeld wert={heuteIso()} onChange={() => {}} />);
    expect(screen.getByText("Läuft heute ab")).toBeInTheDocument();
  });

  it("gibt Änderungen des Datums weiter", () => {
    const onChange = vi.fn();
    render(<Nachweis13bFeld wert="" onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("§ 13b: Nachweis USt 1 TG gültig bis"), { target: { value: "2027-03-31" } });
    expect(onChange).toHaveBeenCalledWith("2027-03-31");
  });
});
