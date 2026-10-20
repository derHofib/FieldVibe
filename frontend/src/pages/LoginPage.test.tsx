// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { LoginPage } from "./LoginPage";

const login = vi.fn();
const loginMfa = vi.fn();

vi.mock("../context/AuthContext", () => ({ useAuth: () => ({ login, loginMfa }) }));
vi.mock("../components/RechtlicheLinks", () => ({ RechtlicheLinks: () => null }));

function rendern() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  );
}

function anmelden() {
  fireEvent.change(screen.getByLabelText("E-Mail"), { target: { value: "a@b.de" } });
  fireEvent.change(screen.getByLabelText("Passwort"), { target: { value: "geheim-123" } });
  fireEvent.click(screen.getByRole("button", { name: "Anmelden" }));
}

beforeEach(() => {
  login.mockReset();
  loginMfa.mockReset();
});
afterEach(cleanup);

describe("LoginPage mit MFA", () => {
  it("meldet ohne MFA direkt an", async () => {
    login.mockResolvedValue(null);
    rendern();
    anmelden();
    await waitFor(() => expect(login).toHaveBeenCalledWith("a@b.de", "geheim-123"));
    expect(screen.queryByLabelText("Code")).not.toBeInTheDocument();
  });

  it("zeigt bei aktiver MFA den Code-Schritt und sendet Zwischen-Token plus Code", async () => {
    login.mockResolvedValue("zwischen-token");
    loginMfa.mockResolvedValue(undefined);
    rendern();
    anmelden();

    const feld = await screen.findByLabelText("Code");
    expect(screen.queryByLabelText("Passwort")).not.toBeInTheDocument();
    fireEvent.change(feld, { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Bestätigen" }));

    await waitFor(() => expect(loginMfa).toHaveBeenCalledWith("zwischen-token", "123456"));
    expect(login).toHaveBeenCalledTimes(1);
  });

  it("zeigt den Fehler bei falschem Code und bleibt im Code-Schritt", async () => {
    login.mockResolvedValue("zwischen-token");
    loginMfa.mockRejectedValue(new ApiError(401, "Der Code ist ungültig oder abgelaufen."));
    rendern();
    anmelden();
    fireEvent.change(await screen.findByLabelText("Code"), { target: { value: "000000" } });
    fireEvent.click(screen.getByRole("button", { name: "Bestätigen" }));

    expect(await screen.findByText("Der Code ist ungültig oder abgelaufen.")).toBeInTheDocument();
    expect(screen.getByLabelText("Code")).toBeInTheDocument();
  });

  it("fuehrt bei abgelaufenem Zwischen-Token zurueck zur Passwort-Eingabe", async () => {
    login.mockResolvedValue("zwischen-token");
    loginMfa.mockRejectedValue(new ApiError(401, "Anmeldung abgelaufen. Bitte erneut anmelden."));
    rendern();
    anmelden();
    fireEvent.change(await screen.findByLabelText("Code"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Bestätigen" }));

    expect(await screen.findByLabelText("Passwort")).toBeInTheDocument();
  });

  it("Zurueck-Knopf verwirft den Code-Schritt", async () => {
    login.mockResolvedValue("zwischen-token");
    rendern();
    anmelden();
    await screen.findByLabelText("Code");
    fireEvent.click(screen.getByRole("button", { name: "Zurück" }));
    expect(screen.getByLabelText("Passwort")).toBeInTheDocument();
  });
});
