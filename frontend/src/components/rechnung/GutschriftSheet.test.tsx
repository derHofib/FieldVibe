// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import { rechnungenApi } from "../../api/endpoints";
import type { Rechnung, RechnungPosition } from "../../types";
import { GutschriftSheet } from "./GutschriftSheet";

vi.mock("../../api/endpoints", () => ({ rechnungenApi: { gutschrift: vi.fn() } }));

function pos(teil: Partial<RechnungPosition>): RechnungPosition {
  return {
    id: "p1",
    position: 1,
    beschreibung: "Kabel",
    menge: "10.00",
    einheit: "m",
    einzelpreis: "10.00",
    gesamt: "100.00",
    steuer_kategorie: "S",
    steuer_satz: "19.00",
    ...teil,
  } as RechnungPosition;
}

function rechnung(positionen: RechnungPosition[]): Rechnung {
  return {
    id: "r1",
    status: "versendet",
    mwst_satz: "19.00",
    betrag_netto: "100.00",
    betrag_brutto: "119.00",
    positionen,
  } as Rechnung;
}

function renderSheet(r: Rechnung) {
  const onErstellt = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <GutschriftSheet rechnung={r} onClose={vi.fn()} onErstellt={onErstellt} />
    </QueryClientProvider>,
  );
  return { onErstellt };
}

const erstellen = () => screen.getByRole("button", { name: "Erstellen" });
const grund = () => screen.getByLabelText("Grund");

const standard = rechnung([
  pos({ id: "p1", position: 1, beschreibung: "Kabel", menge: "10.00", bereits_gutgeschrieben: "4.00" }),
  pos({ id: "p2", position: 2, beschreibung: "Dose", menge: "2.00", einheit: "Stk", einzelpreis: "5.00", bereits_gutgeschrieben: "2.00" }),
  pos({ id: "p3", position: 3, beschreibung: "Abzug Abschlag", menge: "1.00", einzelpreis: "-20.00", abschlag_rechnung_id: "ab1" }),
]);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("GutschriftSheet", () => {
  it("Komplett: Summe aus den Restmengen, Grund ist Pflicht (3 bis 200 Zeichen)", () => {
    renderSheet(standard);
    // Kabel 6 m x 10 = 60, Abzug +20 (1 x -20 -> Rücknahme +20 ergibt -(-20)), Dose 0 Rest
    expect(screen.getByText("Gutschrift brutto").parentElement).toHaveTextContent(/-47,60\s*€/);
    expect(erstellen()).toBeDisabled();
    fireEvent.change(grund(), { target: { value: "ab" } });
    fireEvent.blur(grund());
    expect(screen.getByRole("alert")).toHaveTextContent("Mindestens 3 Zeichen");
    expect(screen.getByText("2/200")).toBeInTheDocument();
    expect(erstellen()).toBeDisabled();
    fireEvent.change(grund(), { target: { value: "Falsch geliefert" } });
    expect(erstellen()).toBeEnabled();
  });

  it("Komplett sendet alle:true samt getrimmtem Grund und zeigt die Warnung zur Festschreibung", async () => {
    vi.mocked(rechnungenApi.gutschrift).mockResolvedValue({ id: "g1" } as Rechnung);
    const { onErstellt } = renderSheet(standard);
    expect(screen.getByText(/sofort versendet und festgeschrieben/)).toBeInTheDocument();
    fireEvent.change(grund(), { target: { value: "  Falsch geliefert " } });
    fireEvent.click(erstellen());
    await waitFor(() => expect(onErstellt).toHaveBeenCalledWith({ id: "g1" }));
    expect(rechnungenApi.gutschrift).toHaveBeenCalledWith("r1", { alle: true, grund: "Falsch geliefert" });
  });

  it("Positionen: Abzugspositionen fehlen, voll gutgeschriebene sind gesperrt", () => {
    renderSheet(standard);
    fireEvent.click(screen.getByRole("button", { name: "Positionen auswählen" }));
    expect(screen.queryByLabelText(/Abzug Abschlag/)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Position 1 auswählen/)).toBeEnabled();
    expect(screen.getByLabelText(/Position 2 auswählen/)).toBeDisabled();
    expect(screen.getByText(/bereits vollständig gutgeschrieben/)).toBeInTheDocument();
  });

  it("Positionen: Auswahl schaltet Mengenfeld frei (Vorbelegung = Rest), Überschreitung sperrt", () => {
    renderSheet(standard);
    fireEvent.click(screen.getByRole("button", { name: "Positionen auswählen" }));
    expect(erstellen()).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/Position 1 auswählen/));
    const menge = screen.getByLabelText(/Menge \(max\. 6\)/) as HTMLInputElement;
    expect(menge.value).toBe("6");
    fireEvent.change(grund(), { target: { value: "Zu viel berechnet" } });
    expect(erstellen()).toBeEnabled();

    fireEvent.change(menge, { target: { value: "6,01" } });
    expect(screen.getByRole("alert")).toHaveTextContent("Höchstens 6 m");
    expect(erstellen()).toBeDisabled();

    fireEvent.change(menge, { target: { value: "2,5" } });
    // 2,5 m x 10 = 25 netto, 4,75 Steuer
    expect(screen.getByText("Gutschrift brutto").parentElement).toHaveTextContent(/-29,75\s*€/);
    expect(erstellen()).toBeEnabled();
  });

  it("Positionen sendet nur die gewählten Positionen mit Punkt-Dezimal", async () => {
    vi.mocked(rechnungenApi.gutschrift).mockResolvedValue({ id: "g2" } as Rechnung);
    renderSheet(standard);
    fireEvent.click(screen.getByRole("button", { name: "Positionen auswählen" }));
    fireEvent.click(screen.getByLabelText(/Position 1 auswählen/));
    fireEvent.change(screen.getByLabelText(/Menge \(max\. 6\)/), { target: { value: "2,5" } });
    fireEvent.change(grund(), { target: { value: "Zu viel berechnet" } });
    fireEvent.click(erstellen());
    await waitFor(() => expect(rechnungenApi.gutschrift).toHaveBeenCalled());
    expect(rechnungenApi.gutschrift).toHaveBeenCalledWith("r1", {
      positionen: [{ position_id: "p1", menge: "2.5" }],
      grund: "Zu viel berechnet",
    });
  });

  it("zeigt Serverfehler im Sheet und lässt das Sheet offen", async () => {
    vi.mocked(rechnungenApi.gutschrift).mockRejectedValue(
      new ApiError(409, "Zu einer Abschlagsrechnung kann keine Gutschrift erstellt werden"),
    );
    const { onErstellt } = renderSheet(standard);
    fireEvent.change(grund(), { target: { value: "Grund" } });
    fireEvent.click(erstellen());
    expect(await screen.findByText(/Zu einer Abschlagsrechnung kann keine Gutschrift/)).toBeInTheDocument();
    expect(onErstellt).not.toHaveBeenCalled();
  });

  it("Beleg ohne Positionen: nur Komplett, Summe aus dem Belegbetrag", () => {
    renderSheet(rechnung([]));
    expect(screen.queryByRole("button", { name: "Positionen auswählen" })).not.toBeInTheDocument();
    expect(screen.getByText("Gutschrift brutto").parentElement).toHaveTextContent(/-119,00\s*€/);
  });

  it("alles bereits gutgeschrieben: Komplett nicht abschickbar", () => {
    renderSheet(rechnung([pos({ id: "p1", menge: "3.00", bereits_gutgeschrieben: "3.00" })]));
    fireEvent.change(grund(), { target: { value: "Grund" } });
    expect(erstellen()).toBeDisabled();
  });
});
