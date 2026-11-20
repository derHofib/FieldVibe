// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mailApi } from "../../api/endpoints";
import type { MailAccount } from "../../types";
import { PostfachEinstellungenPage } from "./PostfachEinstellungenPage";
import { IONOS, STRATO } from "./testDaten";

vi.mock("../../api/endpoints", () => ({
  mailApi: {
    anbieter: vi.fn(),
    anbieterErkennen: vi.fn(),
    testVerbindung: vi.fn(),
    accounts: { list: vi.fn(), update: vi.fn(), delete: vi.fn() },
  },
}));

const KONTO: MailAccount = {
  id: "k1",
  name: "Geschäftlich",
  email_adresse: "d@hofion.de",
  imap_host: "imap.ionos.de",
  imap_port: 1993,
  imap_verschluesselung: "ssl",
  imap_benutzername: "d@hofion.de",
  smtp_host: "smtp.ionos.de",
  smtp_port: 587,
  smtp_verschluesselung: "starttls",
  smtp_benutzername: "d@hofion.de",
  signatur: null,
  aktiv: true,
  letzter_sync_am: null,
  letzter_sync_fehler: null,
  anbieter_id: "ionos",
  server_angepasst: true,
  created_at: "",
  updated_at: "",
};

function rendern() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/postfach/einstellungen?konto=k1"]}>
        <PostfachEinstellungenPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(mailApi.anbieter).mockResolvedValue([IONOS, STRATO]);
  vi.mocked(mailApi.accounts.list).mockResolvedValue([KONTO]);
  vi.mocked(mailApi.accounts.update).mockResolvedValue(KONTO);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PostfachEinstellungenPage", () => {
  it("Schalter aus -> PATCH mit den Vorgabewerten des Anbieters", async () => {
    rendern();
    const schalter = await screen.findByRole("switch", { name: "Servereinstellungen selbst festlegen" });
    expect(schalter).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText("Server angepasst")).toBeInTheDocument();
    fireEvent.click(schalter);
    expect(screen.queryByText("Posteingang (IMAP)")).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: "Speichern" }).at(-1)!);
    await waitFor(() =>
      expect(mailApi.accounts.update).toHaveBeenCalledWith("k1", {
        imap_host: "imap.ionos.de",
        imap_port: 993,
        imap_verschluesselung: "ssl",
        smtp_host: "smtp.ionos.de",
        smtp_port: 587,
        smtp_verschluesselung: "starttls",
      }),
    );
  });

  it("markiert abweichende Felder als geändert", async () => {
    rendern();
    await screen.findByRole("switch", { name: "Servereinstellungen selbst festlegen" });
    expect(screen.getAllByText("geändert")).toHaveLength(1);
  });
});
