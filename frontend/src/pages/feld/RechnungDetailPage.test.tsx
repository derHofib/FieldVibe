// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import { angeboteApi, kundenApi, rechnungenApi } from "../../api/endpoints";
import type { Angebot, Rechnung, RechnungPosition } from "../../types";
import { RechnungDetailPage } from "./RechnungDetailPage";

vi.mock("../../api/endpoints", () => ({
  rechnungenApi: {
    get: vi.fn(),
    storno: vi.fn(),
    abschlaegeAnrechnen: vi.fn(),
    removePosition: vi.fn(),
    positionsvorschlaege: vi.fn(),
  },
  kundenApi: { get: vi.fn() },
  angeboteApi: { get: vi.fn() },
  leistungsverzeichnisApi: { list: vi.fn() },
  mandantEinstellungenApi: { get: vi.fn() },
}));
vi.mock("../../components/EmailSection", () => ({ EmailSection: () => null }));
vi.mock("../../components/rechnung/VorgangHinzufuegen", () => ({ VorgangHinzufuegen: () => null }));

const recht = { abrechnung: true };
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({
    currentUser: { role: "mandant_admin" },
    hatRecht: () => recht.abrechnung,
  }),
}));

function pos(teil: Partial<RechnungPosition> = {}): RechnungPosition {
  return {
    id: "p1",
    position: 1,
    beschreibung: "Leitung verlegen",
    menge: "10.00",
    einheit: "m",
    einzelpreis: "10.00",
    gesamt: "100.00",
    steuer_kategorie: "S",
    steuer_satz: "19.00",
    ...teil,
  } as RechnungPosition;
}

function rechnung(teil: Partial<Rechnung> = {}): Rechnung {
  return {
    id: "r1",
    kunde_id: "k1",
    rechnungsnummer: "RE-2026-0001",
    status: "versendet",
    mwst_satz: "19.00",
    betrag_netto: "100.00",
    betrag_brutto: "119.00",
    bezahlter_betrag: "0.00",
    offener_betrag: "119.00",
    mahnstufe: 0,
    ist_storno: false,
    storniert_rechnung_id: null,
    positionen: [pos()],
    zahlungen: [],
    vorgaenge: [],
    steuergruppen: [],
    xml_object_key: null,
    ...teil,
  } as Rechnung;
}

function zeige(r: Rechnung, bezug?: Rechnung) {
  vi.mocked(rechnungenApi.get).mockImplementation(async (id: string) => (bezug && id === bezug.id ? bezug : r));
  vi.mocked(kundenApi.get).mockResolvedValue({ id: "k1", name: "Muster GmbH", ansprechpartner: [] } as never);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <RechnungDetailPage id={r.id} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  recht.abrechnung = true;
  vi.stubGlobal("confirm", vi.fn(() => true));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("RechnungDetailPage – Rechnungsarten", () => {
  it("normale versendete Rechnung: Gutschrift erstellen sichtbar, kein Art-Badge", async () => {
    zeige(rechnung());
    expect(await screen.findByRole("button", { name: "Gutschrift erstellen" })).toBeInTheDocument();
    expect(screen.queryByText("Abschlagsrechnung")).not.toBeInTheDocument();
  });

  it("ohne Recht abrechnung/erstellen kein Gutschrift-Button", async () => {
    recht.abrechnung = false;
    zeige(rechnung());
    await screen.findByText("Muster GmbH");
    expect(screen.queryByRole("button", { name: "Gutschrift erstellen" })).not.toBeInTheDocument();
  });

  it("Entwurf, Abschlag und Storno-Beleg: kein Gutschrift-Button", async () => {
    for (const teil of [
      { status: "entwurf" as const },
      { rechnungsart: "abschlag" as const },
      { ist_storno: true },
    ]) {
      zeige(rechnung(teil));
      await screen.findByText("Muster GmbH");
      expect(screen.queryByRole("button", { name: "Gutschrift erstellen" })).not.toBeInTheDocument();
      cleanup();
    }
  });

  it("Abschlag trägt Art-Badge Abschlagsrechnung", async () => {
    zeige(rechnung({ rechnungsart: "abschlag" }));
    expect((await screen.findAllByText(/Abschlagsrechnung/)).length).toBeGreaterThan(0);
  });

  it("Gutschrift: Grund, Link zur Bezugsrechnung, Guthaben, keine Zahlungen/Bezahlt-Aktion", async () => {
    const original = rechnung({ id: "r0", rechnungsnummer: "RE-2026-0001" });
    zeige(
      rechnung({
        id: "g1",
        rechnungsnummer: "GS-2026-0002",
        rechnungsart: "gutschrift",
        bezug_rechnung_id: "r0",
        gutschrift_grund: "Falsch geliefert",
        betrag_netto: "-100.00",
        betrag_brutto: "-119.00",
        offener_betrag: "-119.00",
        positionen: [pos({ einzelpreis: "-10.00", gesamt: "-100.00", bezug_position_id: "p1" })],
      }),
      original,
    );
    expect(await screen.findByText("Falsch geliefert")).toBeInTheDocument();
    const link = await screen.findByRole("link", { name: "RE-2026-0001" });
    expect(link).toHaveAttribute("href", "/rechnungen/r0");
    expect(screen.getByText(/Guthaben: 119.00 EUR/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Zahlungen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Als bezahlt markieren" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Gutschrift erstellen" })).not.toBeInTheDocument();
  });

  it("Original zeigt seine Gutschriften als Links", async () => {
    zeige(rechnung({ gutschriften: [{ rechnung_id: "g1", rechnungsnummer: "GS-2026-0002", brutto: "-59.50" }] }));
    expect(await screen.findByRole("heading", { name: "Gutschriften" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /GS-2026-0002/ })).toHaveAttribute("href", "/rechnungen/g1");
  });

  it("negativer offener Betrag einer normalen Rechnung heißt Guthaben", async () => {
    zeige(rechnung({ offener_betrag: "-10.00", bezahlter_betrag: "129.00", status: "bezahlt" }));
    expect(await screen.findByText(/Guthaben: 10.00 EUR/)).toBeInTheDocument();
  });

  it("Schlussrechnung: angerechnete Abschläge, Abzugsposition ohne Bearbeitung, Entfernen hebt Anrechnung auf", async () => {
    zeige(
      rechnung({
        status: "entwurf",
        rechnungsart: "schluss",
        angerechnete_abschlaege: [
          { rechnung_id: "ab1", rechnungsnummer: "RE-2026-0009", datum: "2026-10-01", netto: "300.00" },
        ],
        positionen: [
          pos(),
          pos({
            id: "p2",
            position: 2,
            beschreibung: "Abzug Abschlag RE-2026-0009",
            menge: "1.00",
            einheit: "psch",
            einzelpreis: "-300.00",
            gesamt: "-300.00",
            abschlag_rechnung_id: "ab1",
          }),
        ],
      }),
    );
    expect(await screen.findByText("Angerechnete Abschlagsrechnungen")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /RE-2026-0009/ })).toHaveAttribute("href", "/rechnungen/ab1");
    // Nur die normale Position hat Steuer-Auswahl und Preisfeld
    expect(screen.getAllByRole("button", { name: /Steuer ändern/ })).toHaveLength(1);
    expect(screen.getByText("Entfernen hebt die Anrechnung auf.")).toBeInTheDocument();
    vi.mocked(rechnungenApi.removePosition).mockResolvedValue(rechnung());
    fireEvent.click(screen.getByRole("button", { name: /Anrechnung wird aufgehoben/ }));
    await waitFor(() => expect(rechnungenApi.removePosition).toHaveBeenCalledWith("r1", "p2"));
  });

  describe("Abschläge anrechnen", () => {
    const entwurf = { status: "entwurf" as const, angebot_id: "a1" };
    const angebot = (teil: Partial<Angebot> = {}) =>
      ({
        id: "a1",
        abschlaege: [{ rechnung_id: "ab1", rechnungsnummer: "RE-9", status: "versendet", netto: "300.00" }],
        schlussrechnung_id: null,
        ...teil,
      }) as Angebot;

    it("Button bei versendetem Abschlag; 409-Meldung wird angezeigt", async () => {
      vi.mocked(angeboteApi.get).mockResolvedValue(angebot());
      vi.mocked(rechnungenApi.abschlaegeAnrechnen).mockRejectedValue(
        new ApiError(409, "Keine anrechenbaren Abschlagsrechnungen gefunden"),
      );
      zeige(rechnung(entwurf));
      fireEvent.click(await screen.findByRole("button", { name: "Abschläge anrechnen" }));
      expect(await screen.findByText("Keine anrechenbaren Abschlagsrechnungen gefunden")).toBeInTheDocument();
      expect(rechnungenApi.abschlaegeAnrechnen).toHaveBeenCalledWith("r1");
    });

    it("kein Button, wenn alle Abschläge noch Entwurf oder schon angerechnet sind", async () => {
      vi.mocked(angeboteApi.get).mockResolvedValue(
        angebot({ abschlaege: [{ rechnung_id: "ab1", rechnungsnummer: "RE-9", status: "entwurf", netto: "300.00" }] }),
      );
      zeige(rechnung(entwurf));
      await screen.findByText("Muster GmbH");
      await waitFor(() => expect(angeboteApi.get).toHaveBeenCalled());
      expect(screen.queryByRole("button", { name: "Abschläge anrechnen" })).not.toBeInTheDocument();
    });

    it("Rechnung ohne Angebotsbezug bekommt keinen Button", async () => {
      zeige(rechnung({ status: "entwurf" }));
      await screen.findByText("Muster GmbH");
      expect(angeboteApi.get).not.toHaveBeenCalled();
      expect(screen.queryByRole("button", { name: "Abschläge anrechnen" })).not.toBeInTheDocument();
    });
  });

  it("Storno-Fehler (Gutschriften vorhanden) wird angezeigt statt verschluckt", async () => {
    vi.mocked(rechnungenApi.storno).mockRejectedValue(
      new ApiError(409, "Zu dieser Rechnung existieren Gutschriften (GS-1) – ein Komplett-Storno ist nicht mehr möglich"),
    );
    zeige(rechnung());
    const buttons = await screen.findAllByRole("button", { name: "Stornieren" });
    fireEvent.click(buttons[0]);
    expect(await screen.findByText(/ein Komplett-Storno ist nicht mehr möglich/)).toBeInTheDocument();
  });
});
