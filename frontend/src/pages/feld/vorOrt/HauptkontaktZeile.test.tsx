// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { HauptkontaktZeile } from "./HauptkontaktZeile";

afterEach(cleanup);

describe("HauptkontaktZeile (Feed-Karte)", () => {
  it("zeigt Name (Rolle) und einen Anrufen-Link", () => {
    render(<HauptkontaktZeile kontakt={{ name: "Anna Becker", rolle: "mieter", telefon: "0171 123 45", einheit: "Whg. 3" }} />);
    expect(screen.getByText("Anna Becker (Mieter/in)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Anna Becker anrufen" })).toHaveAttribute("href", "tel:017112345");
  });

  it("rendert nichts ohne Hauptkontakt", () => {
    const { container } = render(<HauptkontaktZeile kontakt={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("ohne Telefon: nur die Zeile, kein Link", () => {
    render(<HauptkontaktZeile kontakt={{ name: "Hans Meier", rolle: "hausmeister", telefon: null, einheit: null }} />);
    expect(screen.getByText("Hans Meier (Hausmeister/in)")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
