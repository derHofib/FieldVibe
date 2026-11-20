// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mandantEinstellungenApi, vorOrtApi } from "../../../api/endpoints";
import type { VorOrtKontakt, VorOrtKontaktZugeordnet } from "../../../types";
import { VorOrtKontakteAbschnitt } from "./VorOrtKontakteAbschnitt";

vi.mock("../../../api/endpoints", () => ({
  vorOrtApi: {
    listeFuerZiel: vi.fn(),
    listeFuerKunde: vi.fn(),
    zuordnen: vi.fn(),
    hauptkontaktSetzen: vi.fn(),
    zuordnungEntfernen: vi.fn(),
    aendern: vi.fn(),
  },
  mandantEinstellungenApi: { get: vi.fn() },
}));

const kontakt = (id: string, extra: Partial<VorOrtKontakt> = {}): VorOrtKontakt => ({
  id,
  kunde_id: "k1",
  standort_id: "s1",
  standort_bezeichnung: "Moselstr. 14",
  name: "Anna Becker",
  rolle: "mieter",
  einheit: "Whg. 3",
  telefon: "0171 1234567",
  telefon2: null,
  email: null,
  erreichbarkeit: "nachmittags",
  hinweis: null,
  quelle: "buero",
  letzter_einsatz_am: null,
  anonymisiert_am: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  zuordnungen_anzahl: 1,
  offene_zuordnungen_anzahl: 0,
  ...extra,
});

const zugeordnet = (zid: string, k: VorOrtKontakt, extra: Partial<VorOrtKontaktZugeordnet> = {}): VorOrtKontaktZugeordnet => ({
  zuordnung_id: zid,
  kontakt: k,
  ist_hauptkontakt: false,
  herkunft: "vorgang",
  herkunft_id: "v1",
  herkunft_titel: "Heizung prüfen",
  ...extra,
});

function rendern(props: Partial<Parameters<typeof VorOrtKontakteAbschnitt>[0]> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <VorOrtKontakteAbschnitt
        ziel="vorgang"
        zielId="v1"
        kundeId="k1"
        standortId="s1"
        darfBearbeiten
        layout="office"
        kontakte={[]}
        {...props}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(vorOrtApi.listeFuerKunde).mockResolvedValue([]);
  vi.mocked(mandantEinstellungenApi.get).mockRejectedValue(new Error("403"));
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("VorOrtKontakteAbschnitt", () => {
  it("zeigt eigene und geerbte Einträge; nur eigene haben ein Menü, geerbte nennen ihre Herkunft", () => {
    rendern({
      kontakte: [
        zugeordnet("z1", kontakt("c1"), { ist_hauptkontakt: true }),
        zugeordnet("z2", kontakt("c2", { name: "Hans Meier", rolle: "hausmeister", einheit: "Keller", hinweis: "Schlüssel beim Nachbarn" }), {
          herkunft: "auftrag",
          herkunft_id: "a1",
          herkunft_titel: "Heizungstausch",
        }),
      ],
    });
    expect(screen.getByText("Anna Becker")).toBeInTheDocument();
    expect(screen.getByText("Hauptkontakt")).toBeInTheDocument();
    expect(screen.getByText("Mieter/in")).toBeInTheDocument();
    expect(screen.getByText("Whg. 3 · nachmittags")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Anna Becker anrufen" })).toHaveAttribute("href", "tel:01711234567");
    expect(screen.getByText("vom Auftrag ‚Heizungstausch‘")).toBeInTheDocument();
    expect(screen.getByText("Schlüssel beim Nachbarn")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aktionen für Anna Becker" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aktionen für Hans Meier" })).not.toBeInTheDocument();
  });

  it("anonymisierter Kontakt: fester Text, kein Anruf-Knopf", () => {
    rendern({
      kontakte: [zugeordnet("z1", kontakt("c1", { name: null, telefon: null, anonymisiert_am: "2026-06-01T00:00:00Z" }))],
    });
    expect(screen.getByText("Kontakt anonymisiert")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("Leerzustand ist ein kurzer Text", () => {
    rendern();
    expect(screen.getByText("Noch kein Kontakt vor Ort hinterlegt.")).toBeInTheDocument();
  });

  it("ohne Auftraggeber: Hinweis statt Hinzufügen", () => {
    rendern({ ziel: "projekt", zielId: "p1", kundeId: null, standortId: null });
    expect(screen.getByText("Erst einen Auftraggeber setzen")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "+ Kontakt" })).not.toBeInTheDocument();
  });

  it("ohne Bearbeitungsrecht gibt es weder Hinzufügen noch Menü", () => {
    rendern({ darfBearbeiten: false, kontakte: [zugeordnet("z1", kontakt("c1"))] });
    expect(screen.queryByRole("button", { name: "+ Kontakt" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Aktionen für/ })).not.toBeInTheDocument();
  });

  it("Menü: als Hauptkontakt setzen", async () => {
    vi.mocked(vorOrtApi.hauptkontaktSetzen).mockResolvedValue(zugeordnet("z1", kontakt("c1")));
    rendern({ kontakte: [zugeordnet("z1", kontakt("c1"))] });
    fireEvent.click(screen.getByRole("button", { name: "Aktionen für Anna Becker" }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Als Hauptkontakt setzen/ }));
    await waitFor(() => expect(vorOrtApi.hauptkontaktSetzen).toHaveBeenCalledWith("z1", true));
  });

  it("Neuer Kontakt: Name oder Telefon ist Pflicht, mit Name wird zugeordnet", async () => {
    vi.mocked(vorOrtApi.zuordnen).mockResolvedValue(zugeordnet("z9", kontakt("c9")));
    rendern();
    fireEvent.click(screen.getByRole("button", { name: "+ Kontakt" }));
    fireEvent.click(await screen.findByRole("button", { name: /Neuen Kontakt anlegen/ }));
    expect(screen.getByText("Wird 12 Monate nach dem letzten Einsatz anonymisiert.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Anlegen und hinzufügen" }));
    expect(await screen.findByText("Name oder Telefon angeben")).toBeInTheDocument();
    expect(vorOrtApi.zuordnen).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Frau Kern" } });
    fireEvent.click(screen.getByRole("button", { name: "Anlegen und hinzufügen" }));
    await waitFor(() => expect(vorOrtApi.zuordnen).toHaveBeenCalledTimes(1));
    const [ziel, zielId, body] = vi.mocked(vorOrtApi.zuordnen).mock.calls[0];
    expect(ziel).toBe("vorgang");
    expect(zielId).toBe("v1");
    expect(body.neu).toMatchObject({ name: "Frau Kern", rolle: "mieter", telefon: null });
  });

  it("Auswahl bekannter Kontakte: Standort des Ziels zuerst, bereits zugeordnete fehlen", async () => {
    vi.mocked(vorOrtApi.listeFuerKunde).mockResolvedValue([
      kontakt("c1"),
      kontakt("c2", { name: "Karl Dorn", standort_id: "s2", standort_bezeichnung: "Lindenweg 2", einheit: null }),
      kontakt("c3", { name: "Eva Lang", letzter_einsatz_am: "2026-03-15T00:00:00Z" }),
    ]);
    vi.mocked(vorOrtApi.zuordnen).mockResolvedValue(zugeordnet("z5", kontakt("c3")));
    rendern({ kontakte: [zugeordnet("z1", kontakt("c1"))] });
    fireEvent.click(screen.getByRole("button", { name: "+ Kontakt" }));
    expect(await screen.findByText("Bekannt in Moselstr. 14")).toBeInTheDocument();
    expect(screen.getByText("Whg. 3 · zuletzt 03/2026")).toBeInTheDocument();
    expect(screen.getByText("Karl Dorn")).toBeInTheDocument();
    expect(screen.getAllByText("Anna Becker")).toHaveLength(1); // nur in der Liste, nicht in der Auswahl
    fireEvent.click(screen.getByText("Eva Lang"));
    await waitFor(() => expect(vorOrtApi.zuordnen).toHaveBeenCalledWith("vorgang", "v1", { kontakt_id: "c3" }));
  });

  it("Feld: geerbte Zeile ohne Menü, Herkunft steht nur in der Fußnote", () => {
    rendern({
      layout: "feld",
      kontakte: [zugeordnet("z1", kontakt("c1", { hinweis: "Schlüssel beim Nachbarn" }), { herkunft: "auftrag", herkunft_id: "a1", herkunft_titel: "Heizungstausch" })],
    });
    expect(screen.queryByText("vom Auftrag ‚Heizungstausch‘")).not.toBeInTheDocument();
    expect(screen.getByText("Vom Auftrag ‚Heizungstausch‘ übernommen.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Aktionen für/ })).not.toBeInTheDocument();
  });

  it("Feld: Antippen der Zeile öffnet die Aktionen", () => {
    rendern({ layout: "feld", kontakte: [zugeordnet("z1", kontakt("c1"))] });
    fireEvent.click(screen.getByRole("button", { name: "Aktionen für Anna Becker" }));
    expect(screen.getByRole("menuitem", { name: /Als Hauptkontakt setzen/ })).toBeInTheDocument();
  });

  it("Auftrag: Hinweis nennt die Zahl der Vorgänge, nur mit Kontakt", () => {
    const { unmount } = rendern({ ziel: "auftrag", zielId: "a1", vorgangAnzahl: 3, kontakte: [zugeordnet("z1", kontakt("c1"), { herkunft: "auftrag" })] });
    expect(screen.getByText("Die Kontakte gelten für alle 3 Vorgänge dieses Auftrags und erscheinen dort in der Feld-App.")).toBeInTheDocument();
    unmount();
    rendern({ ziel: "auftrag", zielId: "a1", vorgangAnzahl: 3, kontakte: [] });
    expect(screen.queryByText(/Die Kontakte gelten für/)).not.toBeInTheDocument();
  });
});
