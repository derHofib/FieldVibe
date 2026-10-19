// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { rechnungenApi } from "../../api/endpoints";
import type { Angebot, Rechnung } from "../../types";
import { AngebotAbrechnung } from "./AngebotAbrechnung";

vi.mock("../../api/endpoints", () => ({ rechnungenApi: { ausAngebot: vi.fn() } }));

function angebot(teil: Partial<Angebot> = {}): Angebot {
  return { id: "a1", gesamt_netto: "1000.00", abgerechnet_netto: "0.00", rest_netto: "1000.00", ...teil } as Angebot;
}

function renderBlock(a: Angebot, kannErstellen = true) {
  const onRechnung = vi.fn();
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AngebotAbrechnung angebot={a} kannErstellen={kannErstellen} onRechnung={onRechnung} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { onRechnung };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AngebotAbrechnung", () => {
  it("ohne Abschläge: Abschlag und Rechnung erstellen, keine Schlussrechnung", () => {
    renderBlock(angebot());
    expect(screen.getByRole("button", { name: "Abschlag erstellen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rechnung erstellen" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Schlussrechnung erstellen" })).not.toBeInTheDocument();
  });

  it("Rechnung erstellen ruft aus-angebot mit Art rechnung und meldet die neue Rechnung", async () => {
    vi.mocked(rechnungenApi.ausAngebot).mockResolvedValue({ id: "r9" } as Rechnung);
    const { onRechnung } = renderBlock(angebot());
    fireEvent.click(screen.getByRole("button", { name: "Rechnung erstellen" }));
    await waitFor(() => expect(onRechnung).toHaveBeenCalledWith({ id: "r9" }));
    expect(rechnungenApi.ausAngebot).toHaveBeenCalledWith({ angebot_id: "a1", rechnungsart: "rechnung" });
  });

  it("mit Abschlägen: Fortschritt, Liste und Schlussrechnung statt Rechnung", () => {
    renderBlock(
      angebot({
        abgerechnet_netto: "300.00",
        rest_netto: "700.00",
        abschlaege: [{ rechnung_id: "r1", rechnungsnummer: "RE-1", status: "versendet", netto: "300.00" }],
      }),
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "30");
    expect(screen.getByRole("link", { name: /RE-1/ })).toHaveAttribute("href", "/rechnungen/r1");
    expect(screen.getByRole("button", { name: "Schlussrechnung erstellen" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Rechnung erstellen" })).not.toBeInTheDocument();
  });

  it("Entwurfs-Abschlag: Hinweis und gesperrte Schlussrechnung", () => {
    renderBlock(
      angebot({
        abgerechnet_netto: "300.00",
        rest_netto: "700.00",
        abschlaege: [{ rechnung_id: "r1", rechnungsnummer: "RE-1", status: "entwurf", netto: "300.00" }],
      }),
    );
    expect(screen.getByRole("status")).toHaveTextContent(/noch ein Entwurf \(RE-1\)/);
    expect(screen.getByRole("button", { name: "Schlussrechnung erstellen" })).toBeDisabled();
  });

  it("nach der Schlussrechnung nur noch Link, keine Aktionen", () => {
    renderBlock(angebot({ schlussrechnung_id: "s1", abgerechnet_netto: "1000.00", rest_netto: "0.00" }));
    expect(screen.getByRole("link", { name: /Zur Schlussrechnung/ })).toHaveAttribute("href", "/rechnungen/s1");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("ohne Recht keine Aktionen", () => {
    renderBlock(angebot(), false);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("zeigt Serverfehler beim Erstellen", async () => {
    const { ApiError } = await import("../../api/client");
    vi.mocked(rechnungenApi.ausAngebot).mockRejectedValue(new ApiError(409, "Zu diesem Angebot existiert bereits die Rechnung RE-7"));
    renderBlock(angebot());
    fireEvent.click(screen.getByRole("button", { name: "Rechnung erstellen" }));
    expect(await screen.findByText(/bereits die Rechnung RE-7/)).toBeInTheDocument();
  });
});
