// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CurrentUser } from "../types";
import { RouteGuard } from "./RouteGuard";

const auth = vi.hoisted(() => ({ wert: {} as Record<string, unknown> }));
vi.mock("../context/AuthContext", () => ({ useAuth: () => auth.wert }));

function rendere(pfad: string, nutzer: Partial<CurrentUser> | undefined, isLoading = false) {
  auth.wert = {
    currentUser: nutzer && ({ deaktivierte_module: [], ...nutzer } as CurrentUser),
    isLoading,
    hatRecht: () => nutzer?.role !== "custom",
  };
  return render(
    <MemoryRouter initialEntries={[pfad]}>
      <Routes>
        <Route element={<RouteGuard oberflaeche="feld" />}>
          <Route path="/accounts" element={<p>Nutzerliste</p>} />
          <Route path="/profil" element={<p>Profil</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe("RouteGuard", () => {
  it("zeigt Kein Zugriff, wenn die Rolle fehlt", () => {
    rendere("/accounts", { role: "custom" });
    expect(screen.getByText("Kein Zugriff")).toBeInTheDocument();
    expect(screen.queryByText("Nutzerliste")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zur Startseite" })).toBeInTheDocument();
  });

  it("rendert die Kinder bei Berechtigung", () => {
    rendere("/accounts", { role: "mandant_admin" });
    expect(screen.getByText("Nutzerliste")).toBeInTheDocument();
    expect(screen.queryByText("Kein Zugriff")).not.toBeInTheDocument();
  });

  it("offene Seiten bleiben fuer custom erreichbar", () => {
    rendere("/profil", { role: "custom" });
    expect(screen.getByText("Profil")).toBeInTheDocument();
  });

  it("entscheidet nicht, solange der Nutzer laedt", () => {
    rendere("/accounts", undefined, true);
    expect(screen.queryByText("Kein Zugriff")).not.toBeInTheDocument();
    expect(screen.queryByText("Nutzerliste")).not.toBeInTheDocument();
  });
});
