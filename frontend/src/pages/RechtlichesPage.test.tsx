// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { rechtlichesApi } from "../api/endpoints";
import type { Rechtliches } from "../types";
import { DatenschutzPage, ImpressumPage } from "./RechtlichesPage";

vi.mock("../api/endpoints", () => ({ rechtlichesApi: { get: vi.fn() } }));

const firma: Rechtliches = {
  impressum_url: null,
  datenschutz_url: null,
  anbieter: {
    name: "Mueller Elektro GmbH",
    strasse: "Werkstr. 5",
    plz: "12345",
    ort: "Musterstadt",
    land: null,
    telefon: "0123 456",
    email: "info@mueller.de",
    website: null,
    geschaeftsfuehrung: "Max Mueller",
    handelsregister: null,
    ust_idnr: "DE123456789",
  },
};

function renderSeite(seite: "impressum" | "datenschutz", daten: Rechtliches) {
  vi.mocked(rechtlichesApi.get).mockResolvedValue(daten);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{seite === "impressum" ? <ImpressumPage /> : <DatenschutzPage />}</MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Platzhalter-Seiten", () => {
  it("Impressum zeigt befuellte Felder und markiert fehlende Pflichtbloecke", async () => {
    renderSeite("impressum", firma);

    expect(screen.getByRole("heading", { level: 1, name: "Impressum" })).toBeInTheDocument();
    expect(await screen.findByText("Mueller Elektro GmbH")).toBeInTheDocument();
    expect(screen.getByText("Angaben gemäß § 5 DDG")).toBeInTheDocument();
    expect(screen.getByText("Werkstr. 5")).toBeInTheDocument();
    expect(screen.getByText("12345 Musterstadt")).toBeInTheDocument();
    expect(screen.getByText("0123 456")).toBeInTheDocument();
    expect(screen.getByText("DE123456789")).toBeInTheDocument();
    // Handelsregister ist leer -> Hinweiszeile statt leerem Block; Website fehlt still.
    expect(screen.getAllByText("Angaben noch nicht hinterlegt")).toHaveLength(1);
    expect(screen.queryByText("Website:")).not.toBeInTheDocument();
  });

  it("Impressum ohne Firma: Hinweiszeile je Pflichtblock", async () => {
    renderSeite("impressum", { impressum_url: null, datenschutz_url: null, anbieter: null });

    expect((await screen.findAllByText("Angaben noch nicht hinterlegt")).length).toBeGreaterThanOrEqual(6);
  });

  it("Datenschutz zeigt Verantwortlichen und nur einen Platzhaltertext", async () => {
    renderSeite("datenschutz", firma);

    expect(screen.getByRole("heading", { level: 1, name: "Datenschutzerklärung" })).toBeInTheDocument();
    expect(await screen.findByText("Mueller Elektro GmbH")).toBeInTheDocument();
    expect(screen.getByText("Verantwortlicher")).toBeInTheDocument();
    expect(screen.getByText("info@mueller.de")).toBeInTheDocument();
    expect(screen.queryByText("DE123456789")).not.toBeInTheDocument();
  });

  it("beide Seiten tragen den Platzhalter-Hinweis und genau ein h1", () => {
    for (const seite of ["impressum", "datenschutz"] as const) {
      const { unmount } = renderSeite(seite, firma);
      expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
      expect(screen.getByRole("note")).toHaveTextContent(
        "Platzhalter – der rechtsgeprüfte Text wird vom Betreiber ergänzt. Bis dahin dienen diese Angaben nur der Orientierung.",
      );
      expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
      unmount();
    }
  });
});
