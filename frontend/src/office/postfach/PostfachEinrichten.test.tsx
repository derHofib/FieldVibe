// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mailApi } from "../../api/endpoints";
import { PostfachEinrichten } from "./PostfachEinrichten";
import { GOOGLE, IONOS, MICROSOFT, STRATO } from "./testDaten";

vi.mock("../../api/endpoints", () => ({
  mailApi: {
    anbieter: vi.fn(),
    anbieterErkennen: vi.fn(),
    testVerbindung: vi.fn(),
    accounts: { create: vi.fn() },
  },
}));

function rendern(onFertig = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <PostfachEinrichten layout="office" onFertig={onFertig} />
    </QueryClientProvider>,
  );
  return onFertig;
}

const kachel = (name: string) => screen.getByRole("button", { name: new RegExp(name) });

beforeEach(() => {
  vi.mocked(mailApi.anbieter).mockResolvedValue([IONOS, STRATO, GOOGLE, MICROSOFT]);
  vi.mocked(mailApi.anbieterErkennen).mockResolvedValue({ anbieter: IONOS, quelle: "mx" });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function adresseEintippen(adresse = "d@hofion.de") {
  await screen.findByRole("button", { name: /STRATO/ });
  fireEvent.change(screen.getByLabelText("E-Mail-Adresse"), { target: { value: adresse } });
}

describe("PostfachEinrichten", () => {
  it("erkennt den Anbieter, wählt die Kachel und zeigt den Hinweis", async () => {
    rendern();
    await adresseEintippen();
    expect(await screen.findByText("Anbieter erkannt: IONOS")).toBeInTheDocument();
    expect(screen.getByText(/Die Domain hofion\.de nimmt Mails bei IONOS an/)).toBeInTheDocument();
    expect(kachel("IONOS")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Postfach-Passwort verwenden.")).toBeInTheDocument();
  });

  it("manuelle Kachelwahl überstimmt die Erkennung", async () => {
    rendern();
    await adresseEintippen();
    await screen.findByText("Anbieter erkannt: IONOS");
    fireEvent.click(kachel("STRATO"));
    expect(kachel("STRATO")).toHaveAttribute("aria-pressed", "true");
    // dieselbe Adresse nochmal erkannt -> Wahl bleibt
    fireEvent.change(screen.getByLabelText("E-Mail-Adresse"), { target: { value: "D@hofion.de" } });
    await waitFor(() => expect(kachel("STRATO")).toHaveAttribute("aria-pressed", "true"));
    expect(kachel("IONOS")).toHaveAttribute("aria-pressed", "false");
  });

  it("Microsoft-Kachel ist nicht wählbar", async () => {
    rendern();
    await screen.findByRole("button", { name: /Microsoft/ });
    const ms = kachel("Microsoft");
    expect(ms).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(ms);
    expect(ms).toHaveAttribute("aria-pressed", "false");
  });

  it("Anderer Anbieter öffnet die Expertenfelder", async () => {
    rendern();
    await screen.findByRole("button", { name: /STRATO/ });
    expect(screen.queryByText("Posteingang (IMAP)")).toBeNull();
    fireEvent.click(kachel("Anderer Anbieter"));
    expect(screen.getByText("Posteingang (IMAP)")).toBeInTheDocument();
    expect(screen.getAllByPlaceholderText("imap.anbieter.de")[0]).toHaveValue("");
  });

  it("Verbinden sendet die Anbieterwerte", async () => {
    vi.mocked(mailApi.accounts.create).mockResolvedValue({} as never);
    const onFertig = rendern();
    await adresseEintippen();
    await screen.findByText("Anbieter erkannt: IONOS");
    fireEvent.change(screen.getByLabelText("Passwort"), { target: { value: "geheim" } });
    const verbinden = screen.getByRole("button", { name: "Verbinden" });
    await waitFor(() => expect(verbinden).toBeEnabled());
    fireEvent.click(verbinden);
    await waitFor(() =>
      expect(mailApi.accounts.create).toHaveBeenCalledWith({
        name: "IONOS",
        email_adresse: "d@hofion.de",
        imap_host: "imap.ionos.de",
        imap_port: 993,
        imap_verschluesselung: "ssl",
        imap_benutzername: "d@hofion.de",
        smtp_host: "smtp.ionos.de",
        smtp_port: 587,
        smtp_verschluesselung: "starttls",
        smtp_benutzername: "d@hofion.de",
        passwort: "geheim",
      }),
    );
    await waitFor(() => expect(onFertig).toHaveBeenCalled());
  });

  it("zeigt den Fehler des Backends", async () => {
    vi.mocked(mailApi.accounts.create).mockRejectedValue(new Error("Anmeldung fehlgeschlagen"));
    rendern();
    await adresseEintippen();
    await screen.findByText("Anbieter erkannt: IONOS");
    fireEvent.change(screen.getByLabelText("Passwort"), { target: { value: "x" } });
    const verbinden = screen.getByRole("button", { name: "Verbinden" });
    await waitFor(() => expect(verbinden).toBeEnabled());
    fireEvent.click(verbinden);
    expect(await screen.findByText("Anmeldung fehlgeschlagen")).toBeInTheDocument();
  });
});
