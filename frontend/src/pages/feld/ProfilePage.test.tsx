// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CurrentUser } from "../../types";
import { ProfilePage } from "./ProfilePage";

const vorgaengeKarte = vi.fn();
vi.mock("../../api/endpoints", () => ({
  kiApi: { verbindungen: () => Promise.resolve([]), trennen: vi.fn() },
  authApi: {},
}));
vi.mock("./MfaKarte", () => ({ MfaKarte: () => <div>MFA-Zeile</div> }));
vi.mock("./PasswortAendernKarte", () => ({ PasswortAendernKarte: () => <div>Passwort-Zeile</div> }));
vi.mock("./ProfilUebersichten", () => ({
  ProfilArbeitszeitKarte: () => <div>Arbeitszeit-Karte</div>,
  ProfilUrlaubKarte: () => <div>Urlaub-Karte</div>,
  ProfilVorgaengeKarte: (p: unknown) => {
    vorgaengeKarte(p);
    return <div>Vorgänge-Karte</div>;
  },
}));
vi.mock("../../components/AppearancePicker", () => ({ AppearancePicker: () => <div>Darstellung-Picker</div> }));

let nutzer: Partial<CurrentUser>;
let hatRecht = true;
let impersoniert = false;
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ currentUser: nutzer, hatRecht: () => hatRecht, isImpersonating: impersoniert, logout: vi.fn() }),
}));

function rendern(layout: "feld" | "office") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ProfilePage layout={layout} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vorgaengeKarte.mockReset();
  hatRecht = true;
  impersoniert = false;
  nutzer = { role: "custom", name: "Max", email: "m@x.de", mandant_name: "Betrieb", deaktivierte_module: [] };
});
afterEach(cleanup);

describe("Profil Office", () => {
  it("zeigt Kopfzeile mit Abmelden-Buttons, Überblick, Einstellungen und KI-Verbindungen", async () => {
    rendern("office");
    expect(screen.getByRole("button", { name: /Auf allen Geräten abmelden/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Abmelden$/ })).toBeInTheDocument();
    expect(screen.getByText("Überblick")).toBeInTheDocument();
    expect(screen.getByText("Arbeit")).toBeInTheDocument();
    expect(screen.getByText("Darstellung")).toBeInTheDocument();
    expect(screen.getByText("Sicherheit")).toBeInTheDocument();
    expect(screen.getByText("Passwort-Zeile")).toBeInTheDocument();
    expect(await screen.findByText(/Keine aktive Verbindung/)).toBeInTheDocument();
    expect(vorgaengeKarte).toHaveBeenCalledWith(expect.objectContaining({ kurzliste: true }));
  });

  it("blendet Arbeit ohne Dispo-Recht und Zeiterfassung sowie KI ohne Modul aus", () => {
    hatRecht = false;
    nutzer = { ...nutzer, deaktivierte_module: ["zeiterfassung", "ki_zugriff"] };
    rendern("office");
    expect(screen.queryByText("Arbeit")).not.toBeInTheDocument();
    expect(screen.queryByText("KI-Verbindungen")).not.toBeInTheDocument();
    expect(screen.getByText("Darstellung")).toBeInTheDocument();
  });

  it("blendet Sicherheit und KI beim Impersonieren aus", () => {
    impersoniert = true;
    rendern("office");
    expect(screen.queryByText("Sicherheit")).not.toBeInTheDocument();
    expect(screen.queryByText("KI-Verbindungen")).not.toBeInTheDocument();
  });
});

describe("Profil Feld-App", () => {
  it("bleibt einspaltig ohne Überblick-Abschnitt und ohne Kurzliste", () => {
    rendern("feld");
    expect(screen.queryByText("Überblick")).not.toBeInTheDocument();
    expect(screen.queryByText("Sicherheit")).not.toBeInTheDocument();
    expect(screen.getByText("Passwort-Zeile")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Auf allen Geräten abmelden/ })).toBeInTheDocument();
    expect(vorgaengeKarte).toHaveBeenCalledWith(expect.not.objectContaining({ kurzliste: true }));
  });
});
