// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../../../api/client";
import type { Vorgang } from "../../../../types";

const { update } = vi.hoisted(() => ({ update: vi.fn() }));
vi.mock("../../../../api/endpoints", () => ({
  projekteApi: { list: async () => [{ id: "p1", name: "Projekt Eins" }, { id: "p2", name: "Projekt Zwei" }] },
  auftraegeApi: {
    list: async () => [
      { id: "a1", titel: "Auftrag Eins", projekt_id: "p1" },
      { id: "a2", titel: "Auftrag Zwei", projekt_id: "p2" },
    ],
  },
  vorgaengeApi: { update },
}));

import { ZuordnungPanel } from "../ZuordnungPanel";

afterEach(() => {
  cleanup();
  update.mockReset();
});

function rendern() {
  const schliessen = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ZuordnungPanel vorgang={{ id: "v1", projekt_id: null, auftrag_id: null } as Vorgang} onSchliessen={schliessen} />
    </QueryClientProvider>,
  );
  return schliessen;
}

describe("ZuordnungPanel", () => {
  it("setzt beim Wählen des Auftrags das Projekt mit und speichert beides", async () => {
    update.mockResolvedValue({});
    const schliessen = rendern();
    fireEvent.focus(screen.getByLabelText("Auftrag"));
    fireEvent.click(await screen.findByRole("button", { name: "Auftrag Zwei" }));
    expect((screen.getByLabelText("Projekt") as HTMLInputElement).value).toBe("Projekt Zwei");
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(update).toHaveBeenCalledWith("v1", { projekt_id: "p2", auftrag_id: "a2" }));
    await waitFor(() => expect(schliessen).toHaveBeenCalled());
  });

  it("bietet nach der Projektwahl nur dessen Aufträge an", async () => {
    rendern();
    fireEvent.focus(screen.getByLabelText("Projekt"));
    fireEvent.click(await screen.findByRole("button", { name: "Projekt Eins" }));
    fireEvent.focus(screen.getByLabelText("Auftrag"));
    expect(await screen.findByRole("button", { name: "Auftrag Eins" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Auftrag Zwei" })).toBeNull();
  });

  it("zeigt Serverfehler (400/409) an und bleibt offen", async () => {
    update.mockRejectedValue(new ApiError(409, "Vorgang ist eigenständig geführt"));
    const schliessen = rendern();
    fireEvent.focus(screen.getByLabelText("Projekt"));
    fireEvent.click(await screen.findByRole("button", { name: "Projekt Eins" }));
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect((await screen.findByRole("alert")).textContent).toContain("eigenständig");
    expect(schliessen).not.toHaveBeenCalled();
  });
});
