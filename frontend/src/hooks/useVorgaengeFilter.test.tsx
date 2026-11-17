// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { useVorgaengeFilter } from "./useVorgaengeFilter";

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ currentUser: { id: "u1", role: "techniker" }, hatRecht: () => true }),
}));
vi.mock("../api/endpoints", () => ({
  kundenApi: { list: async () => [{ id: "k1", name: "Müller" }] },
  projekteApi: { list: async () => [] },
  anlagenApi: { list: async () => [] },
  tagsApi: { list: async () => [] },
}));

function rendere(pfad: string) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[pfad]}>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return renderHook(() => ({ filter: useVorgaengeFilter(), ort: useLocation() }), { wrapper });
}

describe("useVorgaengeFilter", () => {
  it("rechnet alte Query-Parameter einmalig in Bedingungen um und entfernt sie aus der URL", async () => {
    const { result } = rendere("/feed?projekt_id=p1&faellig_von=2026-01-01&faellig_bis=2026-01-01");
    await waitFor(() => expect(result.current.filter.zustand.bedingungen, result.current.ort.search).toHaveLength(2));
    expect(result.current.ort.search).not.toContain("projekt_id");
    expect(result.current.ort.search).not.toContain("faellig_von");
    expect(result.current.filter.parameter).toMatchObject({ projekt_id: "p1", faellig_von: "2026-01-01", faellig_bis: "2026-01-01" });
  });

  it("gibt die Suche als q an den Server und bietet kein Anlage-Feld ohne Kunden-Bedingung", () => {
    const { result } = rendere("/feed?q=heizung%20keller");
    expect(result.current.filter.felder.map((f) => f.key)).not.toContain("anlage");
    expect(result.current.filter.felder.map((f) => f.key)).toContain("kunde");
  });
});
