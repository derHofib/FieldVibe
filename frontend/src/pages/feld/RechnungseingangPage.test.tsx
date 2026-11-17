// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Eingangsrechnung } from "../../types";
import { RechnungseingangPage } from "./RechnungseingangPage";

const zeilen = [
  { id: "e1", lieferant_name: "Elektro Meier", rechnungsnummer_lieferant: "M-1", status: "offen", kategorie: "wareneinkauf", rechnungsdatum: "2026-03-01", faellig_am: null, betrag_brutto: "119.00" },
  { id: "e2", lieferant_name: "Sanitär Schulz", rechnungsnummer_lieferant: "S-9", status: "bezahlt", kategorie: null, rechnungsdatum: "2026-03-02", faellig_am: null, betrag_brutto: "50.00" },
] as unknown as Eingangsrechnung[];

vi.mock("../../api/endpoints", () => ({
  eingangsrechnungenApi: { list: vi.fn(async () => zeilen) },
  lieferantenApi: { list: vi.fn(async () => []) },
}));
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ currentUser: { role: "mandant_admin", aktive_module: ["abrechnung"] }, hatRecht: () => true }),
}));
vi.mock("../../office/hostname", () => ({ istOfficeHost: () => false }));
vi.mock("../../utils/module", () => ({ istModulAktiv: () => true }));

afterEach(cleanup);

function rendere(pfad = "/rechnungseingang") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[pfad]}>
        <RechnungseingangPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RechnungseingangPage", () => {
  it("Filterleiste filtert nach Status", async () => {
    const f = encodeURIComponent('[["status","ist",["bezahlt"]]]');
    rendere(`/rechnungseingang?f=${f}`);
    expect(await screen.findByText("Sanitär Schulz")).toBeInTheDocument();
    expect(screen.queryByText("Elektro Meier")).toBeNull();
  });

  it("Suche filtert über alle Spalten und zeigt bei null Treffern den Zurücksetzen-Weg", async () => {
    rendere();
    expect(await screen.findByText("Elektro Meier")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "wareneinkauf" } });
    await waitFor(() => expect(screen.queryByText("Sanitär Schulz")).toBeNull());
    expect(screen.getByText("Elektro Meier")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "gibtsnicht" } });
    expect(await screen.findByText("Nichts gefunden für „gibtsnicht“.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    expect(await screen.findByText("Sanitär Schulz")).toBeInTheDocument();
  });
});
