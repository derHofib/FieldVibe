// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { VorgangAnfrage } from "../../types";
import { OfficeAnfragenPage } from "./OfficeAnfragenPage";

const mocks = vi.hoisted(() => ({
  anfragen: [] as unknown[],
  annehmen: vi.fn(),
  rechte: { kunden: true },
}));

vi.mock("../../api/endpoints", () => ({
  vorgangAnfragenApi: {
    list: () => Promise.resolve(mocks.anfragen),
    annehmen: (...args: unknown[]) => {
      mocks.annehmen(...args);
      return Promise.resolve({});
    },
    ablehnen: () => Promise.resolve({}),
  },
  kundenApi: { list: () => Promise.resolve([{ id: "k1", name: "Müller Haustechnik" }]) },
  gespeicherteFilterApi: { list: () => Promise.resolve([]) },
}));
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({
    currentUser: { deaktivierte_module: [] },
    hatRecht: (modul: string) => (modul === "kunden" ? mocks.rechte.kunden : true),
  }),
}));

afterEach(cleanup);
beforeEach(() => {
  mocks.annehmen.mockClear();
  mocks.rechte.kunden = true;
});

const anfrage = (id: string, extra: Partial<VorgangAnfrage> = {}): VorgangAnfrage => ({
  id,
  kunde_id: "k1",
  kundenportal_zugang_id: "z1",
  standort_id: "s1",
  anlage_id: "a1",
  titel: `Anfrage ${id}`,
  beschreibung: "Heizung macht Geräusche\nseit gestern",
  leistungstyp: "stoerung",
  status: "offen",
  ablehnungsgrund: null,
  vorgang_id: null,
  bearbeitet_von: null,
  bearbeitet_am: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  kunde_name: "Müller Haustechnik",
  standort_bezeichnung: "Werkstatt Nord",
  anlage_bezeichnung: "Heizung 1",
  gestellt_von_name: "Eva Portal",
  gestellt_von_email: "eva@example.de",
  vorgang_nummer: null,
  bearbeitet_von_name: null,
  ...extra,
});

// Das Panel erscheint schon beim Laden (Skeleton); erst die Überschrift zeigt die geladene Anfrage.
async function panelGeladen() {
  await screen.findByRole("heading", { level: 2, name: "Anfrage 1" });
  return screen.getByRole("region", { name: "Anfrage" });
}

function rendere(pfad = "/anfragen") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[pfad]}>
        <Routes>
          <Route path="/anfragen" element={<OfficeAnfragenPage />} />
          <Route path="/anfragen/:id" element={<OfficeAnfragenPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("OfficeAnfragenPage", () => {
  it("zeigt Namen aus der API und blendet angenommene per Startfilter aus", async () => {
    mocks.anfragen = [anfrage("1"), anfrage("2", { status: "angenommen", titel: "Schon erledigt" })];
    rendere();
    await screen.findByText("Anfrage 1");
    expect(screen.getByText("Werkstatt Nord")).toBeInTheDocument();
    expect(screen.getByText("Heizung 1")).toBeInTheDocument();
    expect(screen.getByText("Eva Portal")).toBeInTheDocument();
    expect(screen.queryByText("Schon erledigt")).toBeNull();
  });

  it("öffnet beim Zeilenklick das Panel", async () => {
    mocks.anfragen = [anfrage("1")];
    rendere();
    fireEvent.click(await screen.findByRole("button", { name: /Anfrage 1/ }));
    const panel = await panelGeladen();
    expect(within(panel).getByText(/über das Kundenportal/)).toBeInTheDocument();
    expect(within(panel).getByText(/eva@example.de/)).toBeInTheDocument();
  });

  it("Annehmen sendet Abrechnungsart und Priorität", async () => {
    mocks.anfragen = [anfrage("1")];
    rendere("/anfragen/1");
    const panel = await panelGeladen();
    fireEvent.change(within(panel).getByLabelText("Priorität"), { target: { value: "5" } });
    fireEvent.click(within(panel).getByRole("button", { name: "Vorgang anlegen" }));
    await waitFor(() => expect(mocks.annehmen).toHaveBeenCalledWith("1", { abrechnungsart: "aufwand", prioritaet: 5 }));
  });

  it("angenommene Anfrage verlinkt den Vorgang", async () => {
    mocks.anfragen = [anfrage("1", { status: "angenommen", vorgang_id: "v1", vorgang_nummer: "V-2026-0142", bearbeitet_von_name: "Max" })];
    rendere("/anfragen/1?f=");
    const panel = await panelGeladen();
    const link = within(panel).getByRole("link", { name: "Zum Vorgang V-2026-0142" });
    expect(link).toHaveAttribute("href", "/vorgaenge/v1");
    expect(within(panel).queryByRole("button", { name: "Vorgang anlegen" })).toBeNull();
  });

  it("zeigt ohne Anfragen den Leerzustand", async () => {
    mocks.anfragen = [];
    rendere();
    await screen.findByText("Noch keine Anfragen");
    expect(screen.getByRole("link", { name: "Zu den Kunden" })).toHaveAttribute("href", "/kunden");
    expect(screen.queryByRole("searchbox")).toBeNull();
  });

  it("verlinkt den Kunden nur mit kunden.sehen", async () => {
    mocks.anfragen = [anfrage("1")];
    rendere("/anfragen/1");
    let panel = await panelGeladen();
    expect(within(panel).getByRole("link", { name: "Müller Haustechnik" })).toHaveAttribute("href", "/kunden/k1");
    cleanup();
    mocks.rechte.kunden = false;
    rendere("/anfragen/1");
    panel = await panelGeladen();
    expect(within(panel).queryByRole("link", { name: "Müller Haustechnik" })).toBeNull();
    expect(within(panel).getByText("Müller Haustechnik")).toBeInTheDocument();
  });

  it("blendet bei offenem Panel Gestellt von und Standort · Anlage aus", async () => {
    mocks.anfragen = [anfrage("1")];
    rendere("/anfragen/1");
    await panelGeladen();
    expect(screen.queryByRole("columnheader", { name: /Gestellt von/ })).toBeNull();
    expect(screen.queryByRole("columnheader", { name: /Standort · Anlage/ })).toBeNull();
    cleanup();
    rendere();
    await screen.findByText("Anfrage 1");
    expect(screen.getByRole("columnheader", { name: /Gestellt von/ })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /Standort · Anlage/ })).toBeInTheDocument();
  });

  it("zeigt in der Standort-Zelle nur vorhandene Werte und – nur wenn beide fehlen", async () => {
    mocks.anfragen = [
      anfrage("1", { standort_bezeichnung: "Nur Standort", anlage_bezeichnung: null }),
      anfrage("2", { standort_bezeichnung: null, anlage_bezeichnung: "Nur Anlage" }),
      anfrage("3", { standort_bezeichnung: null, anlage_bezeichnung: null }),
    ];
    rendere();
    await screen.findByText("Anfrage 1");
    expect(screen.getByText("Nur Standort")).toBeInTheDocument();
    expect(screen.getByText("Nur Anlage")).toBeInTheDocument();
    const zeile3 = screen.getByText("Anfrage 3").closest("tr")!;
    expect(within(zeile3).getAllByText("–")).toHaveLength(1);
    const zeile1 = screen.getByText("Anfrage 1").closest("tr")!;
    expect(within(zeile1).queryByText("–")).toBeNull();
  });
});
