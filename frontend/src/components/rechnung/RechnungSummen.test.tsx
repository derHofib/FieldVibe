// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Rechnung } from "../../types";
import { FehlerMeldung } from "../Hinweiskasten";
import { RechnungSummen } from "./RechnungSummen";

function rechnung(teil: Partial<Rechnung>): Rechnung {
  return {
    betrag_netto: "300.00",
    betrag_steuer: "19.00",
    betrag_brutto: "319.00",
    steuergruppen: [],
    ...teil,
  } as Rechnung;
}

afterEach(cleanup);

describe("RechnungSummen", () => {
  it("bleibt bei einer Gruppe ohne Hinweis bei Netto und Brutto", () => {
    render(
      <RechnungSummen
        rechnung={rechnung({
          steuergruppen: [{ kategorie: "S", satz: "19.00", netto: "300.00", steuer: "57.00" }],
        })}
      />,
    );
    expect(screen.getByText("Netto: 300.00 EUR")).toBeInTheDocument();
    expect(screen.getByText("Brutto: 319.00 EUR")).toBeInTheDocument();
    expect(screen.queryByTestId("steuergruppen")).toBeNull();
    expect(screen.queryByText(/Steuer:/)).toBeNull();
  });

  it("schlüsselt mehrere Gruppen mit Netto, Steuer und Hinweis auf", () => {
    render(
      <RechnungSummen
        rechnung={rechnung({
          steuergruppen: [
            { kategorie: "S", satz: "19.00", netto: "100.00", steuer: "19.00", hinweis: null, hinweise: [] },
            {
              kategorie: "AE",
              satz: "0.00",
              netto: "200.00",
              steuer: "0.00",
              hinweis: "Steuerschuldnerschaft des Leistungsempfängers (§ 13b UStG)",
              hinweise: ["Steuerschuldnerschaft des Leistungsempfängers (§ 13b UStG)"],
            },
          ],
        })}
      />,
    );
    expect(screen.getByText("19 % USt")).toBeInTheDocument();
    expect(screen.getByText("Reverse Charge (§ 13b UStG)")).toBeInTheDocument();
    expect(screen.getByText("200.00 EUR")).toBeInTheDocument();
    expect(screen.getByText("Steuerschuldnerschaft des Leistungsempfängers (§ 13b UStG)")).toBeInTheDocument();
    expect(screen.getByText("Steuer: 19.00 EUR")).toBeInTheDocument();
    expect(screen.getByText("Brutto: 319.00 EUR")).toBeInTheDocument();
  });

  it("zeigt auch eine einzelne Gruppe mit Hinweis aufgeschlüsselt", () => {
    render(
      <RechnungSummen
        rechnung={rechnung({
          betrag_steuer: "0.00",
          steuergruppen: [
            { kategorie: "E", satz: "0.00", netto: "300.00", steuer: "0.00", hinweis: "Steuerbefreit nach § 19 UStG" },
          ],
        })}
      />,
    );
    expect(screen.getByText("Steuerfrei")).toBeInTheDocument();
    expect(screen.getByText("Steuerbefreit nach § 19 UStG")).toBeInTheDocument();
  });
});

describe("FehlerMeldung", () => {
  it("stellt die Versand-Meldung als Aufzählung dar", () => {
    render(
      <FehlerMeldung meldung={"Rechnung kann nicht versendet werden:\n- Position 1: Steuergrund fehlt\n- Beim Kunden fehlt die USt-IdNr."} />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Rechnung kann nicht versendet werden");
    const punkte = screen.getAllByRole("listitem");
    expect(punkte.map((p) => p.textContent)).toEqual(["Position 1: Steuergrund fehlt", "Beim Kunden fehlt die USt-IdNr."]);
  });

  it("zeigt einzeilige Meldungen als Text", () => {
    render(<FehlerMeldung meldung="Reverse Charge (§ 13b UStG) nicht möglich: Grund" />);
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
    expect(screen.getByRole("alert")).toHaveTextContent("nicht möglich: Grund");
  });
});
