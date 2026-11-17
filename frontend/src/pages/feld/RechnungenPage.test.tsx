// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { rechnungenApi } from "../../api/endpoints";
import { RechnungenPage } from "./RechnungenPage";

vi.mock("../../api/endpoints", () => ({
  rechnungenApi: {
    list: vi.fn(async () => ({ eintraege: [], gesamt_anzahl: 0, summe_netto: "0", summe_brutto: "0", summe_offen: "0" })),
    exportCsv: vi.fn(),
  },
  angeboteApi: { list: vi.fn(async () => []) },
  kundenApi: { list: vi.fn(async () => [{ id: "k1", name: "Müller", kundennummer: "K-1" }]) },
}));
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ currentUser: { role: "mandant_admin" }, hatRecht: () => true }),
}));
vi.mock("../../office/hostname", () => ({ istOfficeHost: () => false }));
vi.mock("../../utils/module", () => ({ istModulAktiv: () => true }));

afterEach(cleanup);
beforeEach(() => vi.mocked(rechnungenApi.list).mockClear());

function rendere(pfad: string) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[pfad]}>
        <RechnungenPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RechnungenPage", () => {
  it("Filterleiste filtert serverseitig: Bedingungen werden zu API-Parametern", async () => {
    const f = encodeURIComponent('[["status","ist",["versendet"]],["faellig","relativ",{"relativ":"ueberfaellig"}]]');
    rendere(`/rechnungen?f=${f}`);
    await waitFor(() =>
      expect(rechnungenApi.list).toHaveBeenCalledWith(
        expect.objectContaining({ status: ["versendet"], nur_ueberfaellig: true, limit: 50 }),
      ),
    );
  });

  it("schickt die Suche als q an den Server", async () => {
    rendere("/rechnungen");
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "RE-2026" } });
    await waitFor(() => expect(rechnungenApi.list).toHaveBeenCalledWith(expect.objectContaining({ q: "RE-2026" })));
  });
});
