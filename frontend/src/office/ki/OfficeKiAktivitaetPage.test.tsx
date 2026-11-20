// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import { ToastProvider } from "../../components/Toast";
import type { KiAktion } from "../../types/ki";
import { OfficeKiAktivitaetPage } from "./OfficeKiAktivitaetPage";

const mocks = vi.hoisted(() => ({
  aktionen: vi.fn(),
  aktion: vi.fn(),
  rueckgaengig: vi.fn(),
}));

vi.mock("../../api/endpoints", () => ({
  kiApi: { aktionen: mocks.aktionen, aktion: mocks.aktion, rueckgaengig: mocks.rueckgaengig },
  usersApi: { auswahl: vi.fn(async () => [{ id: "u2", name: "Sabine Roth" }]) },
  // Der Filter-Unterbau lädt gespeicherte Ansichten nur mit `ansichten`-Prop; hier unbenutzt.
}));
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ currentUser: { id: "u1", role: "mandant_admin", deaktivierte_module: [], rechte: {} } }),
}));

function aktion(extra: Partial<KiAktion> = {}): KiAktion {
  return {
    id: "a1",
    user_id: "u2",
    user_name: "Sabine Roth",
    ki_verbindung_id: "v1",
    client_name: "Claude",
    tool: "vorgang_anlegen",
    aktionsart: "anlegen",
    stufe: 2,
    status: "ausgefuehrt",
    zusammenfassung: "Termin verschoben",
    ziele: [{ typ: "vorgang", id: "v-1", label: "V-00412" }],
    erzeugt: [],
    aenderungen: [
      { typ: "vorgang", id: "v-1", label: "V-00412", feld: "faellig", feld_label: "Fällig", vorher: "Di 8:00", nachher: "Mi 10:00" },
    ],
    rueckgaengig_moeglich: true,
    rueckgaengig_bis: "2026-11-27T10:00:00Z",
    rueckgaengig_am: null,
    rueckgaengig_von_name: null,
    fehler: null,
    erstellt_am: "2026-11-20T08:47:00Z",
    ...extra,
  };
}

// Der Status-Umschalter hat ebenfalls einen Knopf "Rückgängig"; der Aktionsknopf liegt im Panel.
const panel = () => within(screen.getByRole("region", { name: "KI-Aktion" }));

function rendere() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/ki-aktivitaet"]}>
          <OfficeKiAktivitaetPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mocks.aktionen.mockResolvedValue({ eintraege: [aktion()], gesamt: 1 });
  mocks.aktion.mockImplementation(async () => aktion());
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("OfficeKiAktivitaetPage", () => {
  it("lädt mit Standardzeitraum und zeigt die Liste", async () => {
    rendere();
    expect(await screen.findByText("Termin verschoben")).toBeInTheDocument();
    const [filter, limit, offset] = mocks.aktionen.mock.calls[0];
    expect(filter.von).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(filter.bis).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect([limit, offset]).toEqual([50, 0]);
  });

  it("setzt den Status-Filter als Query-Parameter", async () => {
    rendere();
    await screen.findByText("Termin verschoben");
    fireEvent.click(screen.getByRole("button", { name: "Fehlgeschlagen" }));
    await waitFor(() => expect(mocks.aktionen.mock.calls.at(-1)![0].status).toBe("fehlgeschlagen"));
  });

  it("nimmt zurück: POST, Erfolgs-Toast und neu laden", async () => {
    mocks.rueckgaengig.mockResolvedValue(aktion({ status: "rueckgaengig", rueckgaengig_moeglich: false }));
    rendere();
    fireEvent.click(await screen.findByRole("button", { name: "Termin verschoben" }));
    expect(await screen.findByText(/möglich bis/)).toBeInTheDocument();
    const vorher = mocks.aktionen.mock.calls.length;
    fireEvent.click(panel().getByRole("button", { name: /Rückgängig/ }));
    await waitFor(() => expect(mocks.rueckgaengig).toHaveBeenCalledWith("a1"));
    expect(await screen.findByText("Zurückgenommen")).toBeInTheDocument();
    await waitFor(() => expect(mocks.aktionen.mock.calls.length).toBeGreaterThan(vorher));
  });

  it("zeigt bei 409 die Konflikte im Panel statt eines Fehler-Toasts", async () => {
    mocks.rueckgaengig.mockRejectedValue(
      new ApiError(409, "Conflict", {
        detail: {
          meldung: "Seit der Aktion wurde etwas geändert.",
          konflikte: [{ label: "V-00412", feld_label: "Fällig", erwartet_anzeige: "Mi 10:00", aktuell_anzeige: "Do 9:00" }],
        },
      }),
    );
    rendere();
    fireEvent.click(await screen.findByRole("button", { name: "Termin verschoben" }));
    fireEvent.click(await within(await screen.findByRole("region", { name: "KI-Aktion" })).findByRole("button", { name: /Rückgängig/ }));
    expect(await screen.findByText("Seit der Aktion wurde etwas geändert.")).toBeInTheDocument();
    expect(screen.getByText(/erwartet Mi 10:00, jetzt Do 9:00/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("zeigt keinen Rückgängig-Knopf, wenn es nicht möglich ist", async () => {
    mocks.aktionen.mockResolvedValue({ eintraege: [aktion({ rueckgaengig_moeglich: false })], gesamt: 1 });
    mocks.aktion.mockImplementation(async () => aktion({ rueckgaengig_moeglich: false }));
    rendere();
    fireEvent.click(await screen.findByRole("button", { name: "Termin verschoben" }));
    expect(await screen.findByText(/von Sabine Roth über Claude/)).toBeInTheDocument();
    expect(panel().queryByRole("button", { name: /Rückgängig/ })).not.toBeInTheDocument();
  });
});
