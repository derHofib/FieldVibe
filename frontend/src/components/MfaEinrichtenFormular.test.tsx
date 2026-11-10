// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mfaApi } from "../api/endpoints";
import { MfaEinrichtenFormular } from "./MfaEinrichtenFormular";

const loginMitToken = vi.fn();
const zeigeMfaCodes = vi.fn();

vi.mock("../context/AuthContext", () => ({ useAuth: () => ({ loginMitToken, zeigeMfaCodes }) }));
vi.mock("../api/endpoints", () => ({ mfaApi: { einrichten: vi.fn(), bestaetigen: vi.fn() } }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function rendern(onFertig?: () => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MfaEinrichtenFormular onFertig={onFertig} />
    </QueryClientProvider>,
  );
}

describe("MfaEinrichtenFormular", () => {
  it("zeigt den lokal erzeugten QR-Code, bestaetigt und reicht die Codes weiter", async () => {
    vi.mocked(mfaApi.einrichten).mockResolvedValue({
      secret: "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567",
      otpauth_uri: "otpauth://totp/x",
      qr_svg_data_uri: "data:image/svg+xml;base64,AAAA",
    });
    const antwort = { access_token: "a", refresh_token: "r", token_type: "bearer", wiederherstellungscodes: ["AAAA-BBBB-CCCC-DDDD"] };
    vi.mocked(mfaApi.bestaetigen).mockResolvedValue(antwort);
    const fertig = vi.fn();
    rendern(fertig);

    fireEvent.click(screen.getByRole("button", { name: "Einrichtung starten" }));
    const bild = await screen.findByAltText(/QR-Code/);
    // Kein externer Request: das Bild ist eine data:-URI vom eigenen Server.
    expect(bild.getAttribute("src")).toMatch(/^data:image\/svg\+xml/);
    expect(screen.getByTestId("mfa-secret")).toHaveTextContent("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567");

    fireEvent.change(screen.getByLabelText("Code"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "MFA aktivieren" }));

    await waitFor(() => expect(mfaApi.bestaetigen).toHaveBeenCalledWith("123456"));
    await waitFor(() => expect(fertig).toHaveBeenCalled());
    expect(zeigeMfaCodes).toHaveBeenCalledWith(["AAAA-BBBB-CCCC-DDDD"]);
    expect(loginMitToken).toHaveBeenCalledWith(antwort);
  });
});
