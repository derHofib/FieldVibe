// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ERechnungFelder, zeigeERechnungFelder } from "./ERechnungFelder";

afterEach(cleanup);

describe("ERechnungFelder", () => {
  it("zeigt Hinweistext zur Leitweg-ID für Behörden", () => {
    render(<ERechnungFelder leitwegId="" format="" onChange={() => {}} />);
    expect(screen.getByLabelText("Leitweg-ID")).toHaveValue("");
    expect(screen.getByText(/Nur für Behörden und öffentliche Auftraggeber/)).toBeInTheDocument();
    expect(screen.getByLabelText("Format der E-Rechnung")).toHaveValue("");
  });

  it("meldet eine falsche Prüfziffer mit Text und markiert das Feld", () => {
    render(<ERechnungFelder leitwegId="991-12345-74" format="" onChange={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Prüfziffer");
    expect(screen.getByLabelText("Leitweg-ID")).toHaveAttribute("aria-invalid", "true");
  });

  it("akzeptiert eine gültige Leitweg-ID ohne Fehler", () => {
    render(<ERechnungFelder leitwegId="991-12345-73" format="xrechnung" onChange={() => {}} />);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByLabelText("Format der E-Rechnung")).toHaveValue("xrechnung");
  });

  it("gibt Änderungen von Leitweg-ID und Format weiter", () => {
    const onChange = vi.fn();
    render(<ERechnungFelder leitwegId="991-12345-73" format="" onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Leitweg-ID"), { target: { value: "04011000-1234512345-06" } });
    expect(onChange).toHaveBeenCalledWith({ leitwegId: "04011000-1234512345-06", format: "" });
    fireEvent.change(screen.getByLabelText("Format der E-Rechnung"), { target: { value: "zugferd" } });
    expect(onChange).toHaveBeenCalledWith({ leitwegId: "991-12345-73", format: "zugferd" });
  });
});

describe("zeigeERechnungFelder", () => {
  it("zeigt die Felder bei gewerblichen Typen und bei bereits gesetzten Werten", () => {
    expect(zeigeERechnungFelder("gewerbe", "", "")).toBe(true);
    expect(zeigeERechnungFelder("oeffentlich", "", "")).toBe(true);
    expect(zeigeERechnungFelder("hausverwaltung", "", "")).toBe(true);
    expect(zeigeERechnungFelder("privat", "", "")).toBe(false);
    expect(zeigeERechnungFelder(null, "", "")).toBe(false);
    expect(zeigeERechnungFelder("privat", "991-12345-73", "")).toBe(true);
    expect(zeigeERechnungFelder(null, "", "zugferd")).toBe(true);
  });
});
