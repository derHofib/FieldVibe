// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Kunde, Partner } from "../types";
import { OfficeKundenPage } from "./kunden/OfficeKundenPage";
import { OfficePartnerPage } from "./partner/OfficePartnerPage";

const daten = vi.hoisted(() => ({ kunden: [] as unknown[], partner: [] as unknown[] }));

vi.mock("../api/endpoints", () => ({
  kundenApi: { list: () => Promise.resolve(daten.kunden) },
  partnerApi: { list: () => Promise.resolve(daten.partner) },
  usersApi: { auswahl: () => Promise.resolve([]) },
  gespeicherteFilterApi: { list: () => Promise.resolve([]) },
}));
vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ currentUser: { deaktivierte_module: [] }, hatRecht: () => true }),
}));
vi.mock("../pages/feld/KundeProfilePage", () => ({ KundeProfilePage: () => null }));
vi.mock("../pages/feld/PartnerProfilePage", () => ({ PartnerProfilePage: () => null }));

afterEach(cleanup);

const kunde = (id: string, name: string, typ: Kunde["typ"]): Kunde =>
  ({ id, kundennummer: `K-${id}`, name, typ, ansprechpartner: [], adresse: null }) as unknown as Kunde;
const partner = (id: string, name: string, aktiv: boolean): Partner =>
  ({ id, name, gewerk: null, ansprechpartner: [], telefon: null, email: null, adresse: null, aktiv }) as unknown as Partner;

function Url() {
  return <output data-testid="url">{useLocation().search}</output>;
}

function rendere(pfad: string, seite: React.ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[pfad]}>
        <Routes>
          <Route path="/*" element={seite} />
        </Routes>
        <Url />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Office-Listen mit Filterzeile", () => {
  it("Kunden: Suche und Bedingung aus der URL filtern die Tabelle", async () => {
    daten.kunden = [kunde("1", "Alpha GmbH", "gewerbe"), kunde("2", "Beta Müller", "privat")];
    rendere("/kunden", <OfficeKundenPage />);
    await screen.findByText("Alpha GmbH");
    expect(screen.getByText("Beta Müller")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "müller" } });
    await waitFor(() => expect(screen.queryByText("Alpha GmbH")).toBeNull());
    expect(screen.getByText("Beta Müller")).toBeInTheDocument();
  });

  it("Kunden: Treffer-Leerzustand bietet Zurücksetzen an", async () => {
    daten.kunden = [kunde("1", "Alpha GmbH", "gewerbe")];
    rendere("/kunden?q=zzz", <OfficeKundenPage />);
    await screen.findByText("Nichts gefunden für „zzz“");
    fireEvent.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await screen.findByText("Alpha GmbH");
  });

  it("Partner: ohne f in der URL gilt einmalig 'Status ist Aktiv'", async () => {
    daten.partner = [partner("1", "Aktiv AG", true), partner("2", "Ruhend KG", false)];
    rendere("/partner", <OfficePartnerPage />);
    await screen.findByText("Aktiv AG");
    expect(screen.queryByText("Ruhend KG")).toBeNull();
    expect(screen.getByRole("group", { name: "Filter: Status ist Aktiv" })).toBeInTheDocument();
    // Pille entfernen: der Start-Filter darf nicht wiederkehren.
    fireEvent.click(screen.getByRole("button", { name: "Filter Status ist Aktiv entfernen" }));
    await screen.findByText("Ruhend KG");
    expect(screen.getByTestId("url").textContent).not.toContain("f=");
  });

  it("Partner: ein vorhandenes f in der URL wird nicht überschrieben", async () => {
    daten.partner = [partner("1", "Aktiv AG", true), partner("2", "Ruhend KG", false)];
    rendere(`/partner?f=${encodeURIComponent('[["status","ist","inaktiv"]]')}`, <OfficePartnerPage />);
    await screen.findByText("Ruhend KG");
    expect(screen.queryByText("Aktiv AG")).toBeNull();
  });
});
