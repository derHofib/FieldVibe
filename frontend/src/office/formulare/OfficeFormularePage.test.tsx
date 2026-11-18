// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OfficeFormularePage } from "./OfficeFormularePage";
import { detail, schema, uebersicht, view } from "./testDaten";

const api = vi.hoisted(() => ({
  listSchemas: vi.fn(),
  getSchema: vi.fn(),
  listViews: vi.fn(),
  listRules: vi.fn(),
  getView: vi.fn(),
  updateSchema: vi.fn(),
  uebersicht: vi.fn(),
  subGet: vi.fn(),
  pdf: vi.fn(),
  setKundensichtbar: vi.fn(),
}));

vi.mock("../../api/endpoints", () => ({
  formModulApi: {
    listSchemas: api.listSchemas,
    getSchema: api.getSchema,
    listViews: api.listViews,
    listRules: api.listRules,
    getView: api.getView,
    updateSchema: api.updateSchema,
    createSchema: vi.fn(),
    vorschauPdf: vi.fn(),
  },
  formSubmissionsApi: { uebersicht: api.uebersicht, get: api.subGet, pdf: api.pdf, setKundensichtbar: api.setKundensichtbar },
  usersApi: { auswahl: () => Promise.resolve([{ id: "u1", name: "T. Becker" }]) },
  gespeicherteFilterApi: { list: () => Promise.resolve([]) },
}));
// Der CaptureRenderer zieht den ganzen Feld-Renderer (Kamera, QR, Karten) nach; hier zählt nur, dass er gerendert wird.
vi.mock("../../components/formModul/CaptureRenderer", () => ({ CaptureRenderer: () => <div data-testid="capture" /> }));

afterEach(cleanup);

const claudeEntwurf = schema({
  id: "s2",
  name: "Wartungsprotokoll Gas",
  status: "draft",
  erstellt_via: "ki",
  felder_anzahl: 24,
  leistungstypen: [{ leistungstyp: "wartung", pflicht_vor_abschluss: false }],
});
const pruefung = schema({
  id: "s1",
  name: "Pre Check",
  ausgefuellt_anzahl: 87,
  leistungstypen: [{ leistungstyp: "pruefung", pflicht_vor_abschluss: true }],
});
const archiviert = schema({ id: "s3", name: "Altes Formular", status: "archived" });

function Url() {
  return <output data-testid="url">{useLocation().pathname + useLocation().search}</output>;
}

function rendere(pfad = "/form-schemas") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[pfad]}>
        <Routes>
          <Route path="/form-schemas" element={<OfficeFormularePage />} />
          <Route path="/form-schemas/:id" element={<div>Baukasten</div>} />
          <Route path="/vorgaenge/:id" element={<div>Vorgang</div>} />
        </Routes>
        <Url />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.values(api).forEach((m) => m.mockReset());
  api.listSchemas.mockResolvedValue([claudeEntwurf, pruefung, archiviert]);
  api.getSchema.mockImplementation((id: string) => Promise.resolve(detail(id === "s2" ? claudeEntwurf : pruefung)));
  api.listViews.mockResolvedValue([view("vc", "capture"), view("vs", "summary")]);
  api.listRules.mockResolvedValue([]);
  api.getView.mockResolvedValue({ view: view("vc", "capture"), layouts: [], elements: [], states: {} });
  api.uebersicht.mockResolvedValue({
    eintraege: [
      uebersicht({ id: "p1" }),
      uebersicht({ id: "p2", schema_name: "Wartungsprotokoll Gas", vorgangsnummer: "V-00041", status: "offen", erstellt_via: "ki", ausgefuellt_von_name: null }),
    ],
    gesamt: 2,
  });
  api.subGet.mockResolvedValue({ id: "p1", values: { co: 72 } });
});

describe("OfficeFormularePage", () => {
  it("zeigt Vorlagen ohne Archiviertes, mit Claude-Marke, Zählern und Leistungstyp-Pflicht", async () => {
    rendere();
    await screen.findByText("Pre Check");
    expect(screen.getByText("Wartungsprotokoll Gas")).toBeInTheDocument();
    expect(screen.queryByText("Altes Formular")).toBeNull();
    // Violette Marke in der Spalte "Erstellt von"
    expect(screen.getByText("Claude")).toBeInTheDocument();
    expect(screen.getByText("Prüfung · Pflicht")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Vorlagen\s*2/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /Ausgefüllt\s*87/ })).toBeInTheDocument();
  });

  it("wechselt zu Ausgefüllt: URL, Standardzeitraum letzte 30 Tage serverseitig, Entwurf von Claude", async () => {
    rendere();
    await screen.findByText("Pre Check");
    fireEvent.click(screen.getByRole("button", { name: /Ausgefüllt/ }));
    await screen.findByText("Entwurf von Claude");
    expect(screen.getByTestId("url")).toHaveTextContent("ansicht=ausgefuellt");
    await waitFor(() => {
      const letzter = api.uebersicht.mock.calls.at(-1)![0];
      expect(letzter.von).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(letzter.bis).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(letzter.seite).toBe(1);
    });
    // Abgeschlossene Zeile: Techniker statt Claude-Marke
    expect(screen.getAllByText("T. Becker").length).toBeGreaterThan(0);
    expect(screen.getByText("Abgeschlossen")).toBeInTheDocument();
    expect(screen.getByText("Offen")).toBeInTheDocument();
  });

  it("öffnet beim Anklicken einer Claude-Entwurf-Vorlage das Panel mit Hinweis und Aktionen", async () => {
    rendere();
    fireEvent.click(await screen.findByText("Wartungsprotokoll Gas"));
    const panel = await screen.findByRole("region", { name: "Vorschau" });
    expect(await within(panel).findByText("Von Claude entworfen")).toBeInTheDocument();
    expect(within(panel).getByText(/Noch nicht veröffentlicht/)).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Im Baukasten bearbeiten" })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Veröffentlichen" })).toBeInTheDocument();
    // Erfassung ist die Startansicht, Umschalten auf Druck ohne Druckansicht zeigt den Leerzustand
    await within(panel).findByTestId("capture");
    fireEvent.click(within(panel).getByRole("button", { name: "Druck" }));
    expect(await within(panel).findByText(/noch keine Druckansicht/)).toBeInTheDocument();
  });

  it("veröffentlicht nur Entwürfe, Enter und Doppelklick öffnen den Baukasten", async () => {
    api.updateSchema.mockResolvedValue({});
    rendere();
    fireEvent.click(await screen.findByText("Pre Check"));
    const panel = await screen.findByRole("region", { name: "Vorschau" });
    expect(within(panel).queryByRole("button", { name: "Veröffentlichen" })).toBeNull();
    expect(within(panel).queryByText("Von Claude entworfen")).toBeNull();
    fireEvent.click(screen.getByText("Wartungsprotokoll Gas"));
    fireEvent.click(await within(await screen.findByRole("region", { name: "Vorschau" })).findByRole("button", { name: "Veröffentlichen" }));
    await waitFor(() => expect(api.updateSchema).toHaveBeenCalledWith("s2", { status: "published" }));

    fireEvent.keyDown(screen.getAllByRole("row")[1], { key: "Enter" });
    await screen.findByText("Baukasten");
    expect(screen.getByTestId("url")).toHaveTextContent(/^\/form-schemas\/s\d/);
  });

  it("zeigt im Ausgefüllt-Panel die Zusammenfassung mit Grenzwert-Markierung", async () => {
    rendere("/form-schemas?ansicht=ausgefuellt");
    fireEvent.click(await screen.findByText("V-00040"));
    const panel = await screen.findByRole("region", { name: "Protokoll" });
    expect(await within(panel).findByText("über 50")).toBeInTheDocument();
    expect(within(panel).getByRole("link", { name: /Zum Vorgang/ })).toHaveAttribute("href", "/vorgaenge/v1");
    expect(within(panel).getByRole("button", { name: /PDF/ })).toBeInTheDocument();
  });

  it("schaltet die Kundensichtbarkeit über das Aktionsmenü um und lädt die Übersicht neu", async () => {
    api.setKundensichtbar.mockResolvedValue({ id: "p1", values: { co: 72 }, kundensichtbar: true });
    rendere("/form-schemas?ansicht=ausgefuellt");
    fireEvent.click(await screen.findByText("V-00040"));
    const panel = await screen.findByRole("region", { name: "Protokoll" });
    const aufrufeVorher = api.uebersicht.mock.calls.length;
    fireEvent.click(within(panel).getByRole("button", { name: "Weitere Aktionen" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /Für Kunden sichtbar machen/ }));
    await waitFor(() => expect(api.setKundensichtbar).toHaveBeenCalledWith("p1", true));
    await waitFor(() => expect(api.uebersicht.mock.calls.length).toBeGreaterThan(aufrufeVorher));
    expect(await within(panel).findByText(/Für Kunden sichtbar/)).toBeInTheDocument();
    fireEvent.click(within(panel).getByRole("button", { name: "Weitere Aktionen" }));
    expect(await screen.findByRole("menuitem", { name: /Für Kunden ausblenden/ })).toBeInTheDocument();
  });

  it("zeigt Fehlerzustand und Leerzustand mit Anlegen-Aktion", async () => {
    api.listSchemas.mockRejectedValueOnce(new Error("kaputt"));
    rendere();
    expect(await screen.findByText(/Keine Verbindung|konnte nicht geladen/)).toBeInTheDocument();
    cleanup();
    api.listSchemas.mockResolvedValue([]);
    rendere();
    expect(await screen.findByText(/Noch keine Vorlage angelegt/)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Neue Vorlage/ }).length).toBeGreaterThan(1);
  });
});

