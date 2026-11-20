// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import type { KennzahlDaten, KennzahlDef, KennzahlenDashboard } from "../../types/kennzahlen";

const api = vi.hoisted(() => ({
  katalog: vi.fn(),
  daten: vi.fn(),
  dashboards: vi.fn(),
  dashboardAnlegen: vi.fn(),
  dashboardAendern: vi.fn(),
  dashboardLoeschen: vi.fn(),
  reihenfolge: vi.fn(),
}));
vi.mock("../../api/endpoints", () => ({
  kennzahlenApi: api,
  exportApi: { vorgaengeCsv: vi.fn(), zeiterfassungCsv: vi.fn(), materialCsv: vi.fn(), eingangsrechnungenCsv: vi.fn() },
}));

const auth = vi.hoisted(() => ({ wert: {} as Record<string, unknown> }));
vi.mock("../../context/AuthContext", () => ({ useAuth: () => auth.wert }));

import { KennzahlenPage } from "./KennzahlenPage";

const MONAT = { schluessel: "monat", label: "Monat", zeit: true };
const WOCHE = { schluessel: "woche", label: "Woche", zeit: true };
const TECHNIKER = { schluessel: "techniker", label: "Techniker", zeit: false };
const STATUS = { schluessel: "status", label: "Status", zeit: false };

function def(schluessel: string, titel: string, teil: Partial<KennzahlDef> = {}): KennzahlDef {
  return {
    schluessel,
    titel,
    beschreibung: `${titel} im Zeitraum`,
    bereich: (schluessel.split(".")[0] as KennzahlDef["bereich"]) ?? "vorgaenge",
    einheit: "anzahl",
    art: "zeitraum",
    summierbar: true,
    gruppierungen: [MONAT, WOCHE, TECHNIKER],
    ...teil,
  };
}

// Ohne finanzen.*/sales.*: eine Büro-Rolle ohne Abrechnungsrecht.
const KATALOG_OHNE_FINANZEN: KennzahlDef[] = [
  def("vorgaenge.offen", "Offene Vorgänge", { art: "stand", gruppierungen: [STATUS, TECHNIKER] }),
  def("vorgaenge.erstellt", "Vorgänge erstellt"),
  def("vorgaenge.abgeschlossen", "Vorgänge abgeschlossen"),
  def("vorgaenge.durchlaufzeit", "Durchlaufzeit", { einheit: "tage", summierbar: false }),
  def("vorgaenge.ueberfaellig", "Überfällige Vorgänge", { art: "stand", gruppierungen: [TECHNIKER] }),
  def("telefonate.anzahl", "Telefonate", { gruppierungen: [MONAT, WOCHE, TECHNIKER] }),
  def("telefonate.dauer", "Gesprächsdauer", { einheit: "minuten", gruppierungen: [TECHNIKER] }),
];
const KATALOG_VOLL: KennzahlDef[] = [
  ...KATALOG_OHNE_FINANZEN,
  def("finanzen.umsatz_netto", "Umsatz netto", { einheit: "eur" }),
  def("finanzen.offene_forderungen", "Offene Forderungen", { einheit: "eur", art: "stand" }),
];

function datenFuer(p: { kennzahl: string; gruppierung?: string }): KennzahlDaten {
  const gruppe = p.gruppierung ?? "gesamt";
  return {
    kennzahl: p.kennzahl,
    einheit: "anzahl",
    art: "zeitraum",
    gruppierung: gruppe,
    von: null,
    bis: null,
    gesamt: 10,
    vorperiode_gesamt: 8,
    zeilen:
      gruppe === "gesamt"
        ? []
        : [
            { schluessel: "a", label: "Alpha", wert: 6, vorperiode: 4 },
            { schluessel: "b", label: "Beta", wert: 4, vorperiode: 4 },
          ],
    abgeschnitten: false,
    datumsbezug: null,
  };
}

function dashboard(teil: Partial<KennzahlenDashboard> = {}): KennzahlenDashboard {
  return {
    id: "d1",
    name: "Mein Board",
    layout: {
      zeitraum: "quartal",
      widgets: [
        { id: "w1", kennzahl: "vorgaenge.erstellt", darstellung: "zahl", gruppierung: null, groesse: "s", titel: null, vergleich: true },
      ],
    },
    fuer_alle: false,
    vorlage: null,
    sortierung: 0,
    eigenes: true,
    ersteller_name: "Ich",
    updated_at: "2026-11-01T10:00:00Z",
    ...teil,
  };
}

function rendere(pfad = "/kennzahlen") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[pfad]}>
        <KennzahlenPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  auth.wert = {
    currentUser: { id: "u1", role: "mandant_admin", deaktivierte_module: [] },
    hatRecht: () => true,
  };
  api.katalog.mockResolvedValue(KATALOG_VOLL);
  api.daten.mockImplementation(async (p) => datenFuer(p));
  api.dashboards.mockResolvedValue([]);
  api.dashboardAnlegen.mockImplementation(async (body) => dashboard({ id: "neu", name: body.name, layout: body.layout, vorlage: body.vorlage }));
  api.dashboardAendern.mockImplementation(async (id, body) => dashboard({ id, ...body }));
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-19T12:00:00"));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
  localStorage.clear();
});

async function anpassen() {
  fireEvent.click(await screen.findByRole("button", { name: /Anpassen/ }));
  await screen.findByRole("button", { name: /Fertig/ });
}

describe("KennzahlenPage", () => {
  it("zeigt Vorlagen-Tabs gefiltert nach dem Katalog: ohne finanzen.* kein Finanzen-Tab", async () => {
    api.katalog.mockResolvedValue(KATALOG_OHNE_FINANZEN);
    rendere();
    await screen.findByRole("tab", { name: "Überblick" });
    expect(screen.getByRole("tab", { name: "Vorgänge" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Team" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Finanzen" })).not.toBeInTheDocument();
  });

  it("zeigt mit Finanz-Kennzahlen auch den Finanzen-Tab, eigene und geteilte Dashboards dahinter", async () => {
    api.dashboards.mockResolvedValue([
      dashboard(),
      dashboard({ id: "d2", name: "Von Anna", eigenes: false, fuer_alle: true, ersteller_name: "Anna" }),
    ]);
    rendere();
    await screen.findByRole("tab", { name: "Finanzen" });
    const namen = screen.getAllByRole("tab").map((t) => t.textContent);
    expect(namen[0]).toBe("Überblick");
    expect(namen.slice(-2)).toEqual(["Mein Board", "Von Anna (geteilt von Anna)"]);
    expect(screen.getByRole("tab", { name: /Von Anna/ })).toHaveAttribute("title", "Geteilt von Anna");
  });

  it("öffnet das Dashboard aus ?dashboard= und merkt es sich", async () => {
    rendere("/kennzahlen?dashboard=finanzen");
    const tab = await screen.findByRole("tab", { name: "Finanzen" });
    expect(tab).toHaveAttribute("aria-selected", "true");
    await waitFor(() => expect(localStorage.getItem("kennzahlen.letztes.u1")).toBe("finanzen"));
  });

  it("zeigt den Zeitraum und sperrt 'Nächster Zeitraum' im laufenden Zeitraum", async () => {
    rendere();
    await screen.findByRole("tab", { name: "Überblick" });
    expect(screen.getByText("November 2026")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nächster Zeitraum" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Vorheriger Zeitraum" }));
    expect(screen.getByText("Oktober 2026")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nächster Zeitraum" })).toBeEnabled();
    fireEvent.change(screen.getByRole("combobox", { name: "Zeitraum" }), { target: { value: "quartal" } });
    expect(screen.getByText("Q4 2026")).toBeInTheDocument();
  });

  it("sendet Vergleichsparameter nur für Kennzahlen mit Zeitraum, nicht für 'Stand heute'", async () => {
    rendere("/kennzahlen?dashboard=vorgaenge");
    await screen.findByText("Offene Vorgänge nach Status");
    const aufrufe = api.daten.mock.calls.map(([p]) => p);
    const offen = aufrufe.find((p) => p.kennzahl === "vorgaenge.offen");
    expect(offen?.von).toBeUndefined();
    expect(offen?.vergleich_von).toBeUndefined();
    const erstellt = aufrufe.find((p) => p.kennzahl === "vorgaenge.erstellt");
    expect(erstellt).toMatchObject({ von: "2026-11-01", bis: "2026-11-30", vergleich_von: "2026-10-01", vergleich_bis: "2026-10-31" });
  });

  it("zeigt 403 als Berechtigungshinweis und 404 als nicht mehr verfügbar", async () => {
    api.dashboards.mockResolvedValue([
      dashboard({
        id: "d3",
        name: "Geteilt",
        eigenes: false,
        layout: {
          zeitraum: "monat",
          widgets: [
            { id: "a", kennzahl: "finanzen.umsatz_netto", darstellung: "zahl", gruppierung: null, groesse: "s", titel: null, vergleich: true },
            { id: "b", kennzahl: "vorgaenge.alt", darstellung: "zahl", gruppierung: null, groesse: "s", titel: null, vergleich: true },
          ],
        },
      }),
    ]);
    api.daten.mockImplementation(async (p) => {
      if (p.kennzahl === "finanzen.umsatz_netto") throw new ApiError(403, "Kein Recht");
      if (p.kennzahl === "vorgaenge.alt") throw new ApiError(404, "Unbekannt");
      return datenFuer(p);
    });
    rendere("/kennzahlen?dashboard=d3");
    expect(await screen.findByText("Keine Berechtigung für diese Kennzahl")).toBeInTheDocument();
    expect(await screen.findByText("Kennzahl nicht mehr verfügbar")).toBeInTheDocument();
  });
});

describe("Darstellung im Raster", () => {
  it("zeigt bei lauter Nullwerten 'Im Zeitraum keine Daten' statt leerer Achsen", async () => {
    api.daten.mockImplementation(async (p) => ({
      ...datenFuer(p),
      zeilen: [{ schluessel: "a", label: "Alpha", wert: 0, vorperiode: 0 }],
    }));
    rendere("/kennzahlen?dashboard=vorgaenge");
    expect((await screen.findAllByText("Im Zeitraum keine Daten")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("img", { name: /Balkendiagramm/ })).not.toBeInTheDocument();
  });

  it("passt die Zeitachse dem Zeitraum an: Monatszeitraum -> nach Woche, Jahr -> nach Monat", async () => {
    api.dashboards.mockResolvedValue([
      dashboard({
        layout: {
          zeitraum: "monat",
          widgets: [{ id: "w1", kennzahl: "vorgaenge.erstellt", darstellung: "saeulen", gruppierung: "monat", groesse: "l", titel: null, vergleich: true }],
        },
      }),
    ]);
    rendere("/kennzahlen?dashboard=d1");
    expect(await screen.findByText("Vorgänge erstellt nach Woche")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Zeitraum" }), { target: { value: "jahr" } });
    expect(await screen.findByText("Vorgänge erstellt nach Monat")).toBeInTheDocument();
    expect(api.daten.mock.calls.some(([p]) => p.gruppierung === "woche")).toBe(true);
  });

  it("blendet 'Stand heute' im Bearbeiten-Modus aus", async () => {
    rendere("/kennzahlen?dashboard=vorgaenge");
    expect((await screen.findAllByText("Stand heute")).length).toBeGreaterThan(0);
    await anpassen();
    expect(screen.queryByText("Stand heute")).not.toBeInTheDocument();
  });

  it("bietet 'Zeitverlauf' statt Monat und Woche an", async () => {
    rendere("/kennzahlen?dashboard=vorgaenge");
    await anpassen();
    fireEvent.click(screen.getAllByRole("button", { name: "Vorgänge erstellt bearbeiten" })[0]);
    const darstellung = await screen.findByRole("group", { name: "Darstellung" });
    fireEvent.click(within(darstellung).getByRole("button", { name: /Säulen/ }));
    const optionen = within(screen.getByRole("combobox", { name: "Aufteilen nach" })).getAllByRole("option").map((o) => o.textContent);
    expect(optionen).toContain("Zeitverlauf");
    expect(optionen).not.toContain("Monat");
    expect(optionen).not.toContain("Woche");
  });
});

describe("Anpassen", () => {
  it("Vorlage anpassen und 'Fertig' legt per POST eine Kopie mit Vorlagenschlüssel an", async () => {
    rendere("/kennzahlen?dashboard=vorgaenge");
    await anpassen();
    expect(screen.getByText(/Persönliche Kopie von „Vorgänge“/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Fertig/ }));
    await waitFor(() => expect(api.dashboardAnlegen).toHaveBeenCalledTimes(1));
    const body = api.dashboardAnlegen.mock.calls[0][0];
    expect(body).toMatchObject({ name: "Vorgänge (eigene)", vorlage: "vorgaenge" });
    expect(body.layout.zeitraum).toBe("monat");
    expect(body.layout.widgets).toHaveLength(8);
    expect(api.dashboardAendern).not.toHaveBeenCalled();
  });

  it("vergibt bei vorhandener Kopie den nächsten freien Namen", async () => {
    api.dashboards.mockResolvedValue([dashboard({ name: "Vorgänge (eigene)" })]);
    rendere("/kennzahlen?dashboard=vorgaenge");
    await anpassen();
    fireEvent.click(screen.getByRole("button", { name: /Fertig/ }));
    await waitFor(() => expect(api.dashboardAnlegen).toHaveBeenCalled());
    expect(api.dashboardAnlegen.mock.calls[0][0].name).toBe("Vorgänge (eigene 2)");
  });

  it("eigenes Dashboard anpassen speichert per PATCH", async () => {
    api.dashboards.mockResolvedValue([dashboard()]);
    rendere("/kennzahlen?dashboard=d1");
    await anpassen();
    fireEvent.change(screen.getByRole("combobox", { name: "Zeitraum" }), { target: { value: "jahr" } });
    fireEvent.click(screen.getByRole("button", { name: /Fertig/ }));
    await waitFor(() => expect(api.dashboardAendern).toHaveBeenCalledTimes(1));
    const [id, body] = api.dashboardAendern.mock.calls[0];
    expect(id).toBe("d1");
    expect(body.layout.zeitraum).toBe("jahr");
    expect(api.dashboardAnlegen).not.toHaveBeenCalled();
  });

  it("fügt eine Kennzahl über den Katalog hinzu und wählt sie aus", async () => {
    rendere("/kennzahlen?dashboard=team");
    await anpassen();
    fireEvent.click(screen.getByRole("button", { name: "Telefonate hinzufügen" }));
    // Einstellungen ersetzen den Katalog
    expect(await screen.findByRole("button", { name: /Zurück zum Katalog/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Fertig/ }));
    await waitFor(() => expect(api.dashboardAnlegen).toHaveBeenCalled());
    const widgets = api.dashboardAnlegen.mock.calls[0][0].layout.widgets;
    expect(widgets).toHaveLength(5);
    expect(widgets[4]).toMatchObject({ kennzahl: "telefonate.anzahl", darstellung: "zahl", groesse: "s", vergleich: true });
  });

  it("Darstellung wechseln ändert das gerenderte Diagramm", async () => {
    rendere("/kennzahlen?dashboard=vorgaenge");
    await anpassen();
    fireEvent.click(screen.getByRole("button", { name: "Telefonate hinzufügen" }));
    await screen.findByRole("button", { name: /Zurück zum Katalog/ });
    expect(screen.queryByRole("img", { name: /Telefonate/ })).not.toBeInTheDocument();

    const darstellung = screen.getByRole("group", { name: "Darstellung" });
    fireEvent.click(within(darstellung).getByRole("button", { name: /Säulen/ }));
    expect(await screen.findByRole("img", { name: /Säulendiagramm: Telefonate nach Woche/ })).toBeInTheDocument();

    fireEvent.click(within(darstellung).getByRole("button", { name: /Balken/ }));
    expect(await screen.findByRole("img", { name: /Balkendiagramm: Telefonate nach Techniker/ })).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Säulendiagramm: Telefonate/ })).not.toBeInTheDocument();
  });

  it("sperrt Darstellungen, die die Kennzahl nicht kann (Durchlaufzeit hat keinen Ring)", async () => {
    rendere("/kennzahlen?dashboard=vorgaenge");
    await anpassen();
    fireEvent.click(screen.getByRole("button", { name: "Durchlaufzeit bearbeiten" }));
    const darstellung = await screen.findByRole("group", { name: "Darstellung" });
    expect(within(darstellung).getByRole("button", { name: /Ring/ })).toBeDisabled();
    expect(within(darstellung).getByRole("button", { name: /Balken/ })).toBeEnabled();
  });

  it("Abbrechen verwirft alle Änderungen", async () => {
    rendere("/kennzahlen?dashboard=team");
    await anpassen();
    fireEvent.click(screen.getByRole("button", { name: "Telefonate hinzufügen" }));
    fireEvent.click(await screen.findByRole("button", { name: /Zurück zum Katalog/ }));
    fireEvent.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.getByRole("button", { name: /Anpassen/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Fertig/ })).not.toBeInTheDocument();
    expect(api.dashboardAnlegen).not.toHaveBeenCalled();
    expect(api.dashboardAendern).not.toHaveBeenCalled();
    // Das Team-Dashboard hat wieder seine vier Widgets
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(4);
  });

  it("entfernt ein Widget ohne Rückfrage; leeres Dashboard zeigt den Hinweis", async () => {
    api.dashboards.mockResolvedValue([dashboard()]);
    rendere("/kennzahlen?dashboard=d1");
    await anpassen();
    fireEvent.click(screen.getByRole("button", { name: "Vorgänge erstellt entfernen" }));
    expect(await screen.findByText("Noch keine Kennzahlen. Füge rechts welche hinzu.")).toBeInTheDocument();
  });

  it("'Darstellung ändern' im Widget-Menü startet das Bearbeiten mit geöffneten Einstellungen", async () => {
    rendere("/kennzahlen?dashboard=vorgaenge");
    fireEvent.click((await screen.findAllByRole("button", { name: "Aktionen für Vorgänge erstellt" }))[0]);
    fireEvent.click(await screen.findByRole("menuitem", { name: "Darstellung ändern" }));
    expect(await screen.findByRole("button", { name: /Zurück zum Katalog/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Fertig/ })).toBeInTheDocument();
  });

  it("jede Seite hat genau ein h1", async () => {
    rendere();
    await screen.findByRole("tab", { name: "Überblick" });
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});
