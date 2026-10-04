// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { FehlerberichtListItem } from "../../../types";

vi.mock("../../../api/endpoints", () => ({
  fehlerberichteApi: { liste: vi.fn(), zaehler: vi.fn() },
  mandantenApi: { list: vi.fn() },
}));
vi.mock("../../../context/AuthContext", () => ({ useAuth: () => ({ isImpersonating: false }) }));

import { fehlerberichteApi, mandantenApi } from "../../../api/endpoints";
import { FehlerberichtListe } from "../FehlerberichtListe";

const basis = {
  mandant_id: "m1",
  mandant_name: "Elektro Muster",
  melder_name: "Max",
  route: "/vorgaenge",
  app_version: "1",
  commit_sha: "abc1234",
  duplikat_von_id: null,
  hat_screenshot: true,
  erledigt_am: null,
  updated_at: "2026-10-04T10:00:00Z",
};
function bericht(id: string, status: FehlerberichtListItem["status"], created_at: string, extra = {}): FehlerberichtListItem {
  return { ...basis, id, titel: `Titel ${id}`, schweregrad: "mittel", status, created_at, ...extra };
}

function rendere(mitMandantFilter = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <FehlerberichtListe mitMandantFilter={mitMandantFilter} detailPfad={(id) => `/x/${id}`} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(fehlerberichteApi.zaehler).mockResolvedValue({
    neu: 2, gesichtet: 1, in_arbeit: 3, behoben: 5, abgelehnt: 0, duplikat: 1, gesamt: 12,
  });
  vi.mocked(mandantenApi.list).mockResolvedValue([]);
  vi.mocked(fehlerberichteApi.liste).mockImplementation(async (f) => {
    if (f?.status === "neu") return [bericht("a", "neu", "2026-10-04T08:00:00Z", { schweregrad: "blockierend", duplikat_von_id: "z" })];
    if (f?.status === "in_arbeit") return [bericht("b", "in_arbeit", "2026-10-04T09:00:00Z", { schweregrad: "hoch" })];
    if (f?.status === "behoben") return [bericht("c", "behoben", "2026-10-03T09:00:00Z")];
    return [];
  });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("FehlerberichtListe", () => {
  it("lädt standardmäßig 'offen' als Mehrfachabfrage und sortiert neueste zuerst", async () => {
    rendere();
    await waitFor(() => expect(screen.getByText("Titel a")).toBeTruthy());
    const stati = vi.mocked(fehlerberichteApi.liste).mock.calls.map(([f]) => f?.status).sort();
    expect(stati).toEqual(["gesichtet", "in_arbeit", "neu"]);
    const titel = screen.getAllByRole("link").map((l) => l.textContent ?? "");
    expect(titel[0]).toContain("Titel b");
    expect(titel[1]).toContain("Titel a");
    expect(screen.getByText("Mögliches Duplikat")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Offen/ }).getAttribute("aria-pressed")).toBe("true");
  });

  it("zeigt Zähler und setzt beim Kachel-Klick den Status-Filter", async () => {
    rendere();
    await waitFor(() => expect(screen.getByRole("button", { name: /Behoben/ }).textContent).toContain("5"));
    vi.mocked(fehlerberichteApi.liste).mockClear();

    fireEvent.click(screen.getByRole("button", { name: /Behoben/ }));
    await waitFor(() => expect(screen.getByText("Titel c")).toBeTruthy());
    expect(vi.mocked(fehlerberichteApi.liste).mock.calls.map(([f]) => f?.status)).toEqual(["behoben"]);
    expect(screen.getByRole("button", { name: /Behoben/ }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.queryByText("Titel a")).toBeNull();

    // erneuter Klick -> zurück auf offen
    fireEvent.click(screen.getByRole("button", { name: /Behoben/ }));
    await waitFor(() => expect(screen.getByText("Titel a")).toBeTruthy());
    expect(screen.getByRole("button", { name: /Offen/ }).getAttribute("aria-pressed")).toBe("true");
  });

  it("'Alle' fragt ohne Status-Filter ab; Schweregrad-Filter wird durchgereicht", async () => {
    rendere();
    await waitFor(() => expect(screen.getByText("Titel a")).toBeTruthy());
    vi.mocked(fehlerberichteApi.liste).mockClear();
    fireEvent.click(screen.getByRole("button", { name: /Alle/ }));
    await waitFor(() => expect(fehlerberichteApi.liste).toHaveBeenCalled());
    expect(vi.mocked(fehlerberichteApi.liste).mock.calls[0][0]?.status).toBeUndefined();

    vi.mocked(fehlerberichteApi.liste).mockClear();
    fireEvent.change(screen.getByLabelText("Schweregrad"), { target: { value: "hoch" } });
    await waitFor(() => expect(fehlerberichteApi.liste).toHaveBeenCalled());
    expect(vi.mocked(fehlerberichteApi.liste).mock.calls[0][0]?.schweregrad).toBe("hoch");
  });

  it("blendet den Mandanten-Filter in der Office-Variante aus", async () => {
    rendere(false);
    await waitFor(() => expect(screen.getByText("Titel a")).toBeTruthy());
    expect(screen.queryByLabelText("Mandant")).toBeNull();
    expect(mandantenApi.list).not.toHaveBeenCalled();
    expect(screen.queryByText("Elektro Muster")).toBeNull();
  });
});
