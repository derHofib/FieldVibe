// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BezugAufgabenAbschnitt } from "./BezugAufgabenAbschnitt";

const mocks = vi.hoisted(() => ({ liste: [] as unknown[], update: vi.fn(() => Promise.resolve({})), list: vi.fn() }));

vi.mock("../../../api/endpoints", () => ({
  projektAufgabenApi: {
    list: (...a: unknown[]) => {
      mocks.list(...a);
      return Promise.resolve(mocks.liste);
    },
    update: mocks.update,
  },
  projekteApi: { spalten: () => Promise.resolve([]) },
}));
vi.mock("../../../office/projekte/ProjektAufgabeDetailPanel", () => ({
  ProjektAufgabeDetailPanel: (p: { vorbelegterVorgangId?: string }) => <div>Panel neu für {p.vorbelegterVorgangId}</div>,
}));

afterEach(cleanup);

function rendere() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <BezugAufgabenAbschnitt vorgangId="v1" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BezugAufgabenAbschnitt", () => {
  it("zeigt ohne Aufgaben nur '+ Aufgabe' und öffnet das Panel mit vorbelegtem Vorgang", async () => {
    mocks.liste = [];
    rendere();
    await waitFor(() => expect(mocks.list).toHaveBeenCalledWith({ vorgang_id: "v1", erledigt: "alle" }));
    expect(screen.queryByText("Aufgaben")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "+ Aufgabe" }));
    expect(screen.getByText("Panel neu für v1")).toBeInTheDocument();
  });

  it("listet Aufgaben ohne Unteraufgaben und hakt ab", async () => {
    mocks.liste = [
      { id: "a1", titel: "Eins", faelligkeit_am: null, erledigt_am: null, eltern_aufgabe_id: null },
      { id: "a2", titel: "Unter", faelligkeit_am: null, erledigt_am: null, eltern_aufgabe_id: "a1" },
    ];
    rendere();
    await screen.findByText("Eins");
    expect(screen.queryByText("Unter")).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: "„Eins“ als erledigt markieren" }));
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith("a1", { erledigt: true }));
  });
});
