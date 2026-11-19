// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProjektAufgabe } from "../../types";
import { heuteIso } from "../../utils/format";
import { ToastProvider } from "../../components/Toast";
import { MeineAufgabenOffice } from "./MeineAufgabenOffice";

const mocks = vi.hoisted(() => ({
  offen: [] as unknown[],
  erledigt: [] as unknown[],
  update: vi.fn(() => Promise.resolve({})),
}));

vi.mock("../../api/endpoints", () => ({
  projektAufgabenApi: {
    list: (f: { erledigt?: string }) => Promise.resolve(f.erledigt === "erledigt" ? mocks.erledigt : mocks.offen),
    get: () => Promise.resolve(mocks.offen[0]),
    update: mocks.update,
  },
  projekteApi: { spalten: () => Promise.resolve([]) },
  gespeicherteFilterApi: { list: () => Promise.resolve([]) },
  usersApi: { auswahl: () => Promise.resolve([]) },
  vorgaengeApi: { list: () => Promise.resolve([]) },
  kundenApi: { list: () => Promise.resolve([]) },
  anlagenApi: { list: () => Promise.resolve([]) },
  standorteApi: { list: () => Promise.resolve([]) },
  auftraegeApi: { list: () => Promise.resolve([]) },
}));
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ currentUser: { deaktivierte_module: [] }, hatRecht: () => true }),
}));

beforeEach(() => mocks.update.mockClear());
afterEach(cleanup);

function aufgabe(teil: Partial<ProjektAufgabe> & { id: string; titel: string }): ProjektAufgabe {
  return {
    projekt_id: null,
    spalte_id: null,
    eltern_aufgabe_id: null,
    beschreibung: null,
    faelligkeit_am: null,
    prioritaet: "mittel",
    zugewiesen_an: null,
    erledigt_am: null,
    vorgang_id: null,
    auftrag_id: null,
    anlage_id: null,
    kunde_id: null,
    standort_id: null,
    checkliste: [],
    zusatzfelder: {},
    erstellt_von: "u",
    created_at: "2026-11-01T10:00:00Z",
    updated_at: "2026-11-01T10:00:00Z",
    ...teil,
  };
}

function rendere(pfad = "/meine-aufgaben") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ToastProvider>
        <MemoryRouter initialEntries={[pfad]}>
          <Routes>
            <Route path="/*" element={<MeineAufgabenOffice />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("MeineAufgabenOffice", () => {
  beforeEach(() => {
    mocks.offen = [
      aufgabe({ id: "1", titel: "Überfällige Sache", faelligkeit_am: heuteIso(-2), pfad_projekt_id: "p1", pfad_projekt_name: "Neubau Kita", projekt_id: "p1", spalte_name: "In Arbeit" }),
      aufgabe({ id: "2", titel: "Heutige Sache", faelligkeit_am: heuteIso(), vorgang_id: "v1", vorgang_vorgangsnummer: "V-1004" }),
      aufgabe({ id: "3", titel: "Ohne Termin Sache" }),
    ];
    mocks.erledigt = [aufgabe({ id: "9", titel: "Schon fertig", erledigt_am: "2026-11-10T10:00:00Z" })];
  });

  it("zeigt Kopfzahlen und Gruppen nach Fälligkeit", async () => {
    rendere();
    await screen.findByText("Überfällige Sache");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("3 offen · 1 überfällig");
    expect(screen.getByRole("button", { name: /^Überfällig\s*\d/ })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("vor 2 Tagen")).toBeInTheDocument();
    expect(screen.getAllByText("Privat")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Offen 3" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Erledigt 1" })).toBeInTheDocument();
  });

  it("gruppiert per URL nach Projekt mit 'Ohne Projekt' am Ende und klappt Gruppen ein", async () => {
    rendere("/meine-aufgaben?gruppe=projekt");
    await screen.findByText("Überfällige Sache");
    const gruppen = screen.getAllByRole("button", { expanded: true }).map((b) => b.textContent);
    expect(gruppen[0]).toMatch(/^Neubau Kita/);
    expect(gruppen[1]).toMatch(/^Ohne Projekt/);
    const kopf = screen.getAllByRole("button", { expanded: true }).find((b) => /^Neubau Kita/.test(b.textContent ?? ""))!;
    fireEvent.click(kopf);
    expect(screen.queryByText("Überfällige Sache")).toBeNull();
    expect(kopf).toHaveAttribute("aria-expanded", "false");
  });

  it("Abhaken ruft update mit erledigt=true", async () => {
    rendere();
    await screen.findByText("Heutige Sache");
    fireEvent.click(screen.getByRole("checkbox", { name: "„Heutige Sache“ als erledigt markieren" }));
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith("2", { erledigt: true }));
  });

  it("Abhaken zeigt Toast mit Rückgängig, das erledigt=false sendet", async () => {
    rendere();
    await screen.findByText("Heutige Sache");
    fireEvent.click(screen.getByRole("checkbox", { name: "„Heutige Sache“ als erledigt markieren" }));
    fireEvent.click(await screen.findByRole("button", { name: "Rückgängig" }));
    await waitFor(() => expect(mocks.update).toHaveBeenLastCalledWith("2", { erledigt: false }));
  });

  it("Suche ohne Treffer zeigt eigenen Text", async () => {
    rendere("/meine-aufgaben?q=zzzz");
    await screen.findByText("Nichts gefunden für ‚zzzz‘");
  });

  it("Zeilenklick öffnet das Panel als Split, Taste N das leere Panel", async () => {
    rendere();
    await screen.findByText("Heutige Sache");
    const zeile = screen.getByText("Heutige Sache").closest("tr")!;
    fireEvent.click(within(zeile).getByText("Heutige Sache"));
    await screen.findByText("Gehört zu", { selector: "h3" });
    expect(screen.queryByText("Kunde · Anlage")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Zurück" }));
    await waitFor(() => expect(screen.queryByText("Gehört zu", { selector: "h3" })).toBeNull());
    fireEvent.keyDown(document.body, { key: "n" });
    await screen.findByText("Gehört zu", { selector: "h3" });
  });
});
