// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ZeichenLeistungsort } from "./ZeichenLeistungsort";

afterEach(cleanup);

const ORT = { bezeichnung: "Whg. 3, 2. OG links", strasse: "Moselstraße 14", plz: "56068", ort: "Koblenz", land: "DE" };

describe("ZeichenLeistungsort", () => {
  it("zeigt Zeichen, Bezeichnung und Adresse und im Entwurf den Übernahme-Hinweis", () => {
    render(
      <ZeichenLeistungsort beleg="Rechnung" kundenReferenz="HV-2026-0417" leistungsort={ORT} aenderbar speichern={vi.fn()} />,
    );
    expect(screen.getByText("HV-2026-0417")).toBeInTheDocument();
    expect(screen.getByText("Whg. 3, 2. OG links")).toBeInTheDocument();
    expect(screen.getByText("Moselstraße 14, 56068 Koblenz")).toBeInTheDocument();
    expect(screen.getByText(/Aus dem Auftrag übernommen/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });

  it("ist nach dem Versand nur lesend und fehlt ganz, wenn nichts gesetzt ist", () => {
    const { container, rerender } = render(
      <ZeichenLeistungsort beleg="Rechnung" kundenReferenz="HV-1" leistungsort={null} aenderbar={false} speichern={vi.fn()} />,
    );
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).toBeNull();
    expect(screen.queryByText(/Aus dem Auftrag übernommen/)).toBeNull();
    rerender(<ZeichenLeistungsort beleg="Rechnung" kundenReferenz={null} leistungsort={null} aenderbar={false} speichern={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("speichert Zeichen und Leistungsort, behält das Land und sendet bei leerer Eingabe null", async () => {
    const speichern = vi.fn().mockResolvedValue(undefined);
    render(<ZeichenLeistungsort beleg="Angebot" kundenReferenz="A-1" leistungsort={ORT} aenderbar speichern={speichern} />);
    fireEvent.click(screen.getByRole("button", { name: "Bearbeiten" }));
    fireEvent.change(screen.getByLabelText("Ihr Zeichen"), { target: { value: " HV-2 " } });
    fireEvent.change(screen.getByLabelText("Bezeichnung"), { target: { value: "Whg. 4" } });
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(speichern).toHaveBeenCalledTimes(1));
    expect(speichern).toHaveBeenLastCalledWith({
      kunden_referenz: "HV-2",
      leistungsort: { bezeichnung: "Whg. 4", strasse: "Moselstraße 14", plz: "56068", ort: "Koblenz", land: "DE" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Bearbeiten" }));
    for (const label of ["Ihr Zeichen", "Bezeichnung", "Straße", "PLZ", "Ort"]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value: "" } });
    }
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(speichern).toHaveBeenCalledTimes(2));
    expect(speichern).toHaveBeenLastCalledWith({ kunden_referenz: null, leistungsort: null });
  });

  it("zeigt den Rechnungsempfänger mit c/o beim Verwalter, auch ohne Zeichen und Leistungsort", () => {
    render(
      <ZeichenLeistungsort
        beleg="Rechnung"
        empfaengerName="WEG Moselstraße 14"
        verwaltetVonName="Hausverwaltung Rheinblick"
        kundenReferenz={null}
        leistungsort={null}
        aenderbar={false}
        speichern={vi.fn()}
      />,
    );
    expect(screen.getByText("Rechnung an")).toBeInTheDocument();
    expect(screen.getByText(/WEG Moselstraße 14/)).toBeInTheDocument();
    expect(screen.getByText("c/o Hausverwaltung Rheinblick")).toBeInTheDocument();
  });
});
