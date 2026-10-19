// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import { auswertungApi } from "../../api/endpoints";
import type { UstVaBericht } from "../../types";
import { AuswertungPage } from "./AuswertungPage";

vi.mock("../../api/endpoints", () => ({
  auswertungApi: { ustVa: vi.fn(), datevExportCsv: vi.fn(), offenePosten: vi.fn() },
}));
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ currentUser: { nur_zugewiesene_kunden: false, deaktivierte_module: [] }, hatRecht: () => true }),
}));

const bericht: UstVaBericht = {
  von: "2026-10-01",
  bis: "2026-10-31",
  umsatzsteuer_saetze: [{ satz: "19.00", netto: "100.00", steuer: "19.00" }],
  sonstige_umsaetze: [
    { kategorie: "AE", bezeichnung: "Reverse Charge (§ 13b UStG)", netto: "200.00", kennzahl: null },
    { kategorie: "Z", bezeichnung: "Photovoltaik (§ 12 Abs. 3 UStG)", netto: "50.00", kennzahl: null },
  ],
  vorsteuer_saetze: [],
  summe_umsatzsteuer: "19.00",
  summe_vorsteuer: "0.00",
  zahllast: "19.00",
};

function renderSeite() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AuswertungPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AuswertungPage", () => {
  it("zeigt die weiteren Umsätze als eigene Gruppe ohne erfundene Kennzahlen", async () => {
    vi.mocked(auswertungApi.ustVa).mockResolvedValue(bericht);
    renderSeite();
    fireEvent.click(screen.getByRole("button", { name: "USt-VA-Bericht laden" }));
    expect(await screen.findByText("Weitere Umsätze (ohne Umsatzsteuer)")).toBeInTheDocument();
    expect(screen.getByText("Reverse Charge (§ 13b UStG)")).toBeInTheDocument();
    expect(screen.getByText("200.00 EUR")).toBeInTheDocument();
    expect(screen.getByText("Photovoltaik (§ 12 Abs. 3 UStG)")).toBeInTheDocument();
    expect(screen.queryByText(/Kz\.?\s*\d+/)).toBeNull();
  });

  it("lässt die Gruppe ohne sonstige Umsätze weg", async () => {
    vi.mocked(auswertungApi.ustVa).mockResolvedValue({ ...bericht, sonstige_umsaetze: [] });
    renderSeite();
    fireEvent.click(screen.getByRole("button", { name: "USt-VA-Bericht laden" }));
    await screen.findByText("Umsatzsteuer (Ausgangsrechnungen)");
    expect(screen.queryByText("Weitere Umsätze (ohne Umsatzsteuer)")).toBeNull();
  });

  it("zeigt den 422-Text des DATEV-Exports als Hinweis mit Link zu den Firmendaten", async () => {
    const text =
      "Für Steuerkategorie AE ist kein Erlöskonto hinterlegt – bitte unter Firmendaten ➝ Buchhaltung eintragen (Schlüssel AE:0.00)";
    vi.mocked(auswertungApi.datevExportCsv).mockRejectedValue(new ApiError(422, text));
    renderSeite();
    fireEvent.click(screen.getByRole("button", { name: /DATEV-Export \(CSV\)/ }));
    expect(await screen.findByText(text)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Zu den Firmendaten" })).toHaveAttribute("href", "/integrationen");
  });

  it("verweist bei fehlenden DATEV-Stammdaten auf die Einstellungen", async () => {
    const text =
      "DATEV-Stammdaten unvollständig: Beraternummer und Mandantennummer nicht hinterlegt – bitte unter Einstellungen ➝ Buchhaltung (DATEV) eintragen";
    vi.mocked(auswertungApi.datevExportCsv).mockRejectedValue(new ApiError(422, text));
    renderSeite();
    fireEvent.click(screen.getByRole("button", { name: /DATEV-Export \(CSV\)/ }));
    expect(await screen.findByText(text)).toBeInTheDocument();
    expect(screen.getByText("DATEV-Stammdaten fehlen")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Zu den DATEV-Einstellungen" })).toHaveAttribute("href", "/integrationen");
  });

  it("zeigt andere DATEV-Fehler als normale Fehlermeldung ohne Firmendaten-Link", async () => {
    vi.mocked(auswertungApi.datevExportCsv).mockRejectedValue(new ApiError(500, "Interner Fehler"));
    renderSeite();
    fireEvent.click(screen.getByRole("button", { name: /DATEV-Export \(CSV\)/ }));
    expect(await screen.findByText("Interner Fehler")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Zu den Firmendaten" })).toBeNull();
  });
});
