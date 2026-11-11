// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UebersichtAbschnitt } from "../UebersichtAbschnitt";

afterEach(cleanup);

const mutation = { mutate: vi.fn(), isPending: false };

function rendern(uebernehmenKlebt: boolean) {
  const props = {
    istAktiverTab: () => true,
    tabPanelProps: () => ({}),
    vorgang: {
      id: "v1",
      vorgangsnummer: "V-1",
      titel: "Wartung",
      status: "neu",
      prioritaet: 2,
      kunde_id: "k1",
      zugewiesener_user_id: null,
      zugewiesener_name: null,
      dauerauftrag_id: null,
    },
    navigate: vi.fn(),
    currentUser: { id: "u1", darf_vorgaenge_selbst_uebernehmen: true },
    bestaetigen: vi.fn(),
    kannDisponieren: false,
    uebernehmenMutation: mutation,
    statusMutation: mutation,
    prioritaetMutation: mutation,
    uebernehmenKlebt,
  };
  // Nur die für diesen Fall gelesenen Props; der Rest ist hier ohne Wirkung.
  render(<UebersichtAbschnitt {...(props as unknown as ComponentProps<typeof UebersichtAbschnitt>)} />);
}

describe("UebersichtAbschnitt", () => {
  it("zeigt 'Vorgang übernehmen' in der Karte, wenn keine klebende Leiste aktiv ist", () => {
    rendern(false);
    expect(screen.getAllByRole("button", { name: /Vorgang übernehmen/ })).toHaveLength(1);
  });

  it("blendet den Karten-Button aus, wenn die klebende Leiste die Aktion trägt", () => {
    rendern(true);
    expect(screen.queryByRole("button", { name: /Vorgang übernehmen/ })).toBeNull();
  });
});
