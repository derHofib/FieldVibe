// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { FilterFeld } from "./typen";
import { useAnsichten } from "./useAnsichten";
import type { FilterZustand } from "./useFilterZustand";

const mocks = vi.hoisted(() => ({ liste: [] as unknown[], create: vi.fn((b: unknown) => Promise.resolve({ id: "neu", ...(b as object) })) }));
vi.mock("../../api/endpoints", () => ({
  gespeicherteFilterApi: { list: () => Promise.resolve(mocks.liste), create: mocks.create, update: vi.fn(), remove: vi.fn() },
}));

const felder: FilterFeld<unknown>[] = [{ key: "q", label: "Q", typ: "auswahl", icon: (() => null) as never }];
const zustand = { bedingungen: [{ feld: "q", op: "ist", wert: ["a"] }], setBedingungen: vi.fn() } as unknown as FilterZustand;
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
);

describe("useAnsichten mit Zusatzzustand", () => {
  it("speichert den Zusatz im filter_json und liefert ihn beim Anwenden zurück", async () => {
    mocks.liste = [
      { id: "1", name: "Mit", ist_standard: false, filter_json: { v: 2, bedingungen: [{ feld: "q", op: "ist", wert: ["a"] }], zusatz: { gruppe: "projekt" } } },
      { id: "2", name: "Alt", ist_standard: false, filter_json: { v: 2, bedingungen: [] } },
    ];
    const anwenden = vi.fn();
    const { result } = renderHook(
      () => useAnsichten({ entitaet: "aufgaben", zustand, felder, zusatz: { lesen: () => ({ gruppe: "kunde" }), anwenden } }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.ansichten).toHaveLength(2));
    act(() => result.current.anwenden(result.current.ansichten[0]));
    expect(anwenden).toHaveBeenCalledWith({ gruppe: "projekt" });
    act(() => result.current.anwenden(result.current.ansichten[1]));
    expect(anwenden).toHaveBeenCalledTimes(1);

    act(() => result.current.speichern("Neu", false));
    await waitFor(() => expect(mocks.create).toHaveBeenCalled());
    expect((mocks.create.mock.calls[0][0] as { filter_json: unknown }).filter_json).toEqual({
      v: 2,
      bedingungen: zustand.bedingungen,
      zusatz: { gruppe: "kunde" },
    });
  });
});
