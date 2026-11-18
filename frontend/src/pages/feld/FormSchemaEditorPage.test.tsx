// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { detail, feld, schema, uebersicht, view } from "../../office/formulare/testDaten";
import { FormSchemaEditorPage } from "./FormSchemaEditorPage";

const api = vi.hoisted(() => ({
  getSchema: vi.fn(),
  listViews: vi.fn(),
  listRules: vi.fn(),
  getView: vi.fn(),
  replaceLayouts: vi.fn(),
  createView: vi.fn(),
  uebersicht: vi.fn(),
}));

vi.mock("../../api/endpoints", () => ({
  formModulApi: {
    getSchema: api.getSchema,
    listViews: api.listViews,
    listRules: api.listRules,
    getView: api.getView,
    replaceLayouts: api.replaceLayouts,
    createView: api.createView,
    vorschauPdf: () => Promise.resolve(new Blob(["x"], { type: "application/pdf" })),
  },
  formSubmissionsApi: { uebersicht: api.uebersicht, get: () => Promise.resolve({ values: { co: 12 } }) },
  usersApi: { auswahl: () => Promise.resolve([]) },
  gespeicherteFilterApi: { list: () => Promise.resolve([]) },
}));
vi.mock("../../components/formModul/FormBuilderCanvas", () => ({ FormBuilderCanvas: () => <div data-testid="builder" /> }));
vi.mock("../../components/formModul/CaptureRenderer", () => ({ CaptureRenderer: () => <div data-testid="capture" /> }));

afterEach(cleanup);

const s = schema({ id: "s1", name: "Wartungsprotokoll Gas", status: "draft", erstellt_via: "ki", ausgefuellt_anzahl: 4, felder_anzahl: 2 });

function rendere(layout: "feld" | "office" = "office") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/form-schemas/s1"]}>
        <Routes>
          <Route path="/form-schemas/:id" element={<FormSchemaEditorPage layout={layout} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.values(api).forEach((m) => m.mockReset());
  URL.createObjectURL = vi.fn(() => "blob:test");
  URL.revokeObjectURL = vi.fn();
  api.getSchema.mockResolvedValue(detail(s, [feld("co", "zahl", { warn_max: 50 }), feld("notiz", "text")]));
  api.listViews.mockResolvedValue([view("vc", "capture"), view("vp", "print")]);
  api.listRules.mockResolvedValue([]);
  api.getView.mockResolvedValue({
    view: view("vp", "print"),
    layouts: [{ id: "l1", field_key: "co", seite: 0, x_mm: 15, y_mm: 64, breite_mm: 45, hoehe_mm: 10 }],
    elements: [],
    states: {},
  });
  api.replaceLayouts.mockResolvedValue([]);
  api.uebersicht.mockResolvedValue({ eintraege: [uebersicht({ id: "p1", schema_id: "s1" })], gesamt: 1 });
});

describe("FormSchemaEditorPage", () => {
  it("zeigt Unterstrich-Tabs mit Zählern, Status, Version und Claude-Marke", async () => {
    rendere();
    await screen.findByRole("heading", { name: "Wartungsprotokoll Gas" });
    expect(screen.getByRole("tab", { name: /Felder\s*2/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Visualisierung" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Zuordnungen\s*0/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Ausgefüllt\s*4/ })).toBeInTheDocument();
    expect(screen.getByText("Entwurf")).toBeInTheDocument();
    expect(screen.getByText("Version 1")).toBeInTheDocument();
    expect(screen.getByText("von Claude entworfen")).toBeInTheDocument();
    expect(screen.getByTestId("builder")).toBeInTheDocument();
  });

  it("Ausgefüllt-Tab lädt die Liste vorgefiltert auf diese Vorlage", async () => {
    rendere();
    fireEvent.click(await screen.findByRole("tab", { name: /Ausgefüllt/ }));
    await screen.findByText("V-00040");
    expect(api.uebersicht).toHaveBeenCalledWith({ schema_id: "s1", seite: 1 });
  });

  it("Feld-App-Layout hat keinen Ausgefüllt-Tab", async () => {
    rendere("feld");
    await screen.findByRole("tab", { name: /Felder/ });
    expect(screen.queryByRole("tab", { name: /Ausgefüllt/ })).toBeNull();
  });

  it("Visualisierung: verständliche Namen, nur fehlende Typen hinzufügbar, Layout-Eigenschaften in mm", async () => {
    rendere();
    fireEvent.click(await screen.findByRole("tab", { name: "Visualisierung" }));
    const ansichten = await screen.findByRole("region", { name: "Ansichten" });
    expect(within(ansichten).getByText("Erfassung")).toBeInTheDocument();
    expect(within(ansichten).getByText("Druck (A4)")).toBeInTheDocument();
    expect(within(ansichten).queryByText("capture")).toBeNull();

    fireEvent.click(within(ansichten).getByRole("button", { name: "Ansicht hinzufügen" }));
    const menue = await screen.findByRole("menu");
    const eintraege = within(menue).getAllByRole("menuitem").map((e) => e.textContent);
    expect(eintraege).toEqual(["Zusammenfassung", "Tabelle", "Öffentlich"]);
    fireEvent.keyDown(menue, { key: "Escape" });

    // Druck gewählt -> Eigenschaften des ersten Feldes (co) aus dem Layout
    fireEvent.click(within(ansichten).getByRole("button", { name: /^Druck \(A4\)/ }));
    const eig = await screen.findByRole("region", { name: "Eigenschaften" });
    const breite = await within(eig).findByLabelText("Breite (mm)");
    expect(breite).toHaveValue("45");
    fireEvent.change(breite, { target: { value: "60" } });
    fireEvent.blur(breite);
    await waitFor(() =>
      expect(api.replaceLayouts).toHaveBeenCalledWith("s1", "vp", [
        { field_key: "co", seite: 0, x_mm: 15, y_mm: 64, breite_mm: 60, hoehe_mm: 10 },
      ]),
    );
    expect(screen.getByRole("button", { name: /PDF-Vorschau/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Layout aus Feldern/ })).toBeInTheDocument();
    expect(await screen.findByTitle("PDF-Vorschau der Druckansicht")).toBeInTheDocument();
  });
});
