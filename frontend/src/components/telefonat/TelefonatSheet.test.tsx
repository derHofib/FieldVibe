// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Ansprechpartner } from "../../types";

const create = vi.fn();
vi.mock("../../api/endpoints", () => ({
  telefonateApi: { create: (b: unknown) => create(b), update: vi.fn(), remove: vi.fn() },
  kundenApi: { list: vi.fn(async () => []), get: vi.fn(async () => ({ ansprechpartner: [] })) },
  vorgaengeApi: { list: vi.fn(async () => []) },
}));
vi.mock("../../offline/outbox", () => ({ queueTelefonat: vi.fn() }));

import { TelefonatSheet } from "./TelefonatSheet";

const partner: Ansprechpartner[] = [
  { id: "a1", name: "Marian Reichel", position: "Projektleiter", telefon: "030 9928 4417", email: null, operativ: true, eskalationsstufe: null, notiz: null },
];

function rendern(extra: Partial<Parameters<typeof TelefonatSheet>[0]> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return render(<TelefonatSheet offen onClose={vi.fn()} kundeId="k1" ansprechpartner={partner} vorgaenge={[]} {...extra} />, { wrapper });
}

beforeEach(() => create.mockReset().mockResolvedValue({ id: "t1" }));
afterEach(cleanup);

describe("TelefonatSheet", () => {
  it("verlangt bei erreicht eine Notiz und sendet dann nichts", async () => {
    rendern();
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText(/Notiz Pflicht/)).toBeTruthy();
    expect(create).not.toHaveBeenCalled();
  });

  it("blendet die Dauer bei Mailbox und Nicht erreicht aus", () => {
    rendern();
    expect(screen.getByLabelText(/Dauer/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Mailbox" }));
    expect(screen.queryByLabelText(/Dauer/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Nicht erreicht" }));
    expect(screen.queryByLabelText(/Dauer/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Erreicht" }));
    expect(screen.getByLabelText(/Dauer/)).toBeTruthy();
  });

  it("zeigt den Arbeitszeit-Schalter nur mit Vorgang und Ergebnis erreicht", () => {
    const { unmount } = rendern();
    expect(screen.queryByRole("switch", { name: "Als Arbeitszeit buchen" })).toBeNull();
    unmount();
    rendern({ vorgangId: "v1" });
    expect(screen.getByRole("switch", { name: "Als Arbeitszeit buchen" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Mailbox" }));
    expect(screen.queryByRole("switch", { name: "Als Arbeitszeit buchen" })).toBeNull();
  });

  it("wählt den operativen Ansprechpartner vor und sendet vorgang_id, Partner und Arbeitszeit", async () => {
    rendern({ vorgangId: "v1" });
    fireEvent.change(screen.getByLabelText(/Notiz/), { target: { value: "Absage Termin" } });
    fireEvent.click(screen.getByRole("button", { name: "10" }));
    fireEvent.click(screen.getByRole("switch", { name: "Als Arbeitszeit buchen" }));
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    expect(create.mock.calls[0][0]).toMatchObject({
      vorgang_id: "v1",
      ansprechpartner_id: "a1",
      partner_name: "Marian Reichel",
      partner_nummer: "030 9928 4417",
      richtung: "ausgehend",
      ergebnis: "erreicht",
      dauer_sekunden: 600,
      notiz: "Absage Termin",
      als_arbeitszeit_buchen: true,
    });
    expect(create.mock.calls[0][0].client_uuid).toBeTruthy();
  });

  it("verlangt bei \"Andere Person\" einen Namen", async () => {
    rendern();
    fireEvent.change(screen.getByLabelText("Gesprächspartner", { exact: false }), { target: { value: "__andere__" } });
    fireEvent.change(screen.getByLabelText(/Notiz/), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText(/Gesprächspartner angeben/)).toBeTruthy();
    expect(create).not.toHaveBeenCalled();
  });

  it("übernimmt mit der Uhr Dauer und Beginn beim Stopp", async () => {
    vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] });
    try {
      vi.setSystemTime(new Date(2026, 10, 19, 10, 0, 0));
      const start = Date.now();
      rendern({ uhr: { start, kundeId: "k1", vorgangId: null, ansprechpartnerId: "a1", partnerName: "Marian Reichel", partnerNummer: null } });
      expect(screen.getByTestId("anruf-uhr").textContent).toBe("00:00");
      await vi.advanceTimersByTimeAsync(125_000);
      expect(screen.getByTestId("anruf-uhr").textContent).toBe("02:05");
      fireEvent.click(screen.getByRole("button", { name: "Stopp" }));
      expect(screen.getByTestId("anruf-uhr").textContent).toBe("02:05");
      expect((screen.getByLabelText(/Dauer/) as HTMLInputElement).value).toBe("3");
    } finally {
      vi.useRealTimers();
    }
  });
});
