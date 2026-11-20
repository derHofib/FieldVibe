// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import type { Eingangsrechnung } from "../../types";
import { heuteIso } from "../../utils/format";
import { OfficeRechnungseingangPage } from "./OfficeRechnungseingangPage";

const mock = vi.hoisted(() => ({
  zeilen: [] as unknown[],
  listFehler: null as Error | null,
  darfErstellen: true,
  list: vi.fn(),
  eRechnungImport: vi.fn(),
}));

vi.mock("../../api/endpoints", () => ({
  eingangsrechnungenApi: { list: mock.list, eRechnungImport: mock.eRechnungImport },
  lieferantenApi: { list: vi.fn(async () => []) },
  exportApi: { eingangsrechnungenCsv: vi.fn() },
}));
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({
    currentUser: { role: "mandant_admin", aktive_module: ["abrechnung"] },
    hatRecht: (_bereich: string, aktion: string) => (aktion === "erstellen" ? mock.darfErstellen : true),
  }),
}));
vi.mock("../../office/hostname", () => ({ istOfficeHost: () => true }));
vi.mock("../../utils/module", () => ({ istModulAktiv: () => true }));
vi.mock("../../pages/feld/EingangsrechnungDetailPage", () => ({
  EingangsrechnungDetailPage: ({ id, layout }: { id: string; layout: string }) => (
    <div data-testid="detail">{`Detail ${id} ${layout}`}</div>
  ),
}));

const rechnung = (teil: Partial<Eingangsrechnung>) =>
  ({
    lieferant_name: "",
    rechnungsnummer_lieferant: "",
    rechnungsdatum: "2026-11-01",
    faellig_am: null,
    betrag_netto: "100.00",
    betrag_brutto: "119.00",
    offener_betrag: "119.00",
    kategorie: null,
    skonto_frist: null,
    skonto_prozent: null,
    skonto_betrag: null,
    bezahlt_am: null,
    hat_xml: false,
    import_hinweis: null,
    ...teil,
  }) as unknown as Eingangsrechnung;

const standard = () => [
  rechnung({ id: "e1", lieferant_name: "Elektro Meier", rechnungsnummer_lieferant: "M-1", status: "offen", faellig_am: heuteIso(-3) }),
  rechnung({ id: "e2", lieferant_name: "Sanitär Schulz", rechnungsnummer_lieferant: "S-9", status: "bezahlt", offener_betrag: "0" }),
];

beforeEach(() => {
  mock.zeilen = standard();
  mock.listFehler = null;
  mock.darfErstellen = true;
  mock.list.mockImplementation(async () => {
    if (mock.listFehler) throw mock.listFehler;
    return mock.zeilen;
  });
  mock.eRechnungImport.mockReset();
});
afterEach(cleanup);

function Url() {
  const l = useLocation();
  return <output data-testid="url">{l.pathname + l.search}</output>;
}

function rendere(pfad = "/rechnungseingang") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[pfad]}>
        <Routes>
          <Route path="/rechnungseingang" element={<OfficeRechnungseingangPage />} />
          <Route path="/rechnungseingang/:id" element={<OfficeRechnungseingangPage />} />
        </Routes>
        <Url />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const datei = (name: string) => new File(["<x/>"], name, { type: "text/xml" });

describe("OfficeRechnungseingangPage", () => {
  it("zeigt die Tabelle und blendet per Startfilter Bezahltes aus", async () => {
    rendere();
    expect(await screen.findByText("Elektro Meier")).toBeInTheDocument();
    expect(screen.queryByText("Sanitär Schulz")).toBeNull();
    expect(screen.getByRole("group", { name: "Filter: Status ist Offen, Entwurf" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /Fällig/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Rechnungseingang");
  });

  it("ein Filter in der URL ersetzt den Startfilter", async () => {
    const f = encodeURIComponent('[["status","ist",["bezahlt"]]]');
    rendere(`/rechnungseingang?f=${f}`);
    expect(await screen.findByText("Sanitär Schulz")).toBeInTheDocument();
    expect(screen.queryByText("Elektro Meier")).toBeNull();
  });

  it("Klick auf eine Zeile öffnet das Panel unter /rechnungseingang/:id und behält die Filter", async () => {
    rendere();
    fireEvent.click(await screen.findByText("Elektro Meier"));
    expect(await screen.findByTestId("detail")).toHaveTextContent("Detail e1 dicht");
    const url = screen.getByTestId("url").textContent ?? "";
    expect(url).toContain("/rechnungseingang/e1");
    expect(url).toContain("f=");
    expect(screen.getByRole("button", { name: "Ganze Seite" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Panel schließen" }));
    await waitFor(() => expect(screen.queryByTestId("detail")).toBeNull());
    expect(screen.getByTestId("url").textContent).toMatch(/^\/rechnungseingang\?/);
  });

  it("Kennzahl Überfällig setzt den passenden Filter", async () => {
    rendere();
    await screen.findByText("Elektro Meier");
    fireEvent.click(screen.getByRole("button", { name: /Überfällig/ }));
    await waitFor(() => expect(decodeURIComponent(screen.getByTestId("url").textContent ?? "")).toContain('"faellig","vor"'));
  });

  it("zeigt ohne Rechnungen die große Leerfläche mit beiden Aktionen", async () => {
    mock.zeilen = [];
    rendere();
    expect(await screen.findByText("Noch keine Eingangsrechnungen")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /E-Rechnung importieren/ }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /Neue Eingangsrechnung/ }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("searchbox")).toBeNull();
  });

  it("zeigt bei einem Ladefehler den Fehlerzustand statt einer leeren Liste", async () => {
    mock.listFehler = new ApiError(500, "kaputt");
    rendere();
    expect(await screen.findByText("Die Eingangsrechnungen konnte nicht geladen werden.")).toBeInTheDocument();
    expect(screen.queryByText("Noch keine Eingangsrechnungen")).toBeNull();
  });

  it("bietet ohne Erstellen-Recht weder Import noch Anlegen an", async () => {
    mock.darfErstellen = false;
    rendere();
    await screen.findByText("Elektro Meier");
    expect(screen.queryByRole("button", { name: /E-Rechnung importieren/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Neue Eingangsrechnung/ })).toBeNull();
  });

  it("Drop von zwei Dateien importiert beide, meldet den Fehler einer Datei und öffnet das Panel der erfolgreichen", async () => {
    mock.eRechnungImport.mockImplementation(async (f: File) => {
      if (f.name === "b.xml") throw new ApiError(422, "Keine gültige E-Rechnung");
      return rechnung({ id: "neu1", status: "entwurf" });
    });
    rendere();
    await screen.findByText("Elektro Meier");
    fireEvent.drop(screen.getByRole("heading", { level: 1 }), {
      dataTransfer: { types: ["Files"], files: [datei("a.xml"), datei("b.xml")] },
    });
    await waitFor(() => expect(mock.eRechnungImport).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Nicht importiert")).toBeInTheDocument();
    expect(screen.getByText("b.xml: Keine gültige E-Rechnung")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("url").textContent).toContain("/rechnungseingang/neu1"));
  });

  it("Drop ohne Erstellen-Recht importiert nichts", async () => {
    mock.darfErstellen = false;
    rendere();
    await screen.findByText("Elektro Meier");
    fireEvent.drop(screen.getByRole("heading", { level: 1 }), {
      dataTransfer: { types: ["Files"], files: [datei("a.xml")] },
    });
    expect(mock.eRechnungImport).not.toHaveBeenCalled();
  });
});
