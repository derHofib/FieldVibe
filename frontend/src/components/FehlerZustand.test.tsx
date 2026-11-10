// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { FehlerZustand, fehlerArt } from "./FehlerZustand";

function zeige(fehler: unknown, props: Partial<Parameters<typeof FehlerZustand>[0]> = {}) {
  return render(
    <MemoryRouter>
      <FehlerZustand fehler={fehler} was="Der Kunde" {...props} />
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe("FehlerZustand", () => {
  it("unterscheidet 403, 404, Netz und sonstige Fehler", () => {
    expect(fehlerArt(new ApiError(403, "x"))).toBe("kein_zugriff");
    expect(fehlerArt(new ApiError(404, "x"))).toBe("nicht_gefunden");
    expect(fehlerArt(new ApiError(500, "x"))).toBe("sonst");
    expect(fehlerArt(new TypeError("Failed to fetch"))).toBe("netz");
  });

  it("404: Text mit Gegenstand, kein Erneut-Button, Zurueck vorhanden", () => {
    zeige(new ApiError(404, "x"), { onErneut: () => {}, zurueck: true });
    expect(screen.getByText("Der Kunde nicht gefunden oder kein Zugriff.")).toBeTruthy();
    expect(screen.queryByText("Erneut versuchen")).toBeNull();
    expect(screen.getByText("Zurück")).toBeTruthy();
  });

  it("Netzfehler und 500 bieten Erneut versuchen", () => {
    const erneut = vi.fn();
    zeige(new TypeError("Failed to fetch"), { onErneut: erneut });
    expect(screen.getByText(/Keine Verbindung/)).toBeTruthy();
    fireEvent.click(screen.getByText("Erneut versuchen"));
    expect(erneut).toHaveBeenCalledOnce();
  });

  it("403 nennt fehlendes Recht", () => {
    zeige(new ApiError(403, "x"), { onErneut: () => {} });
    expect(screen.getByText(/Kein Zugriff/)).toBeTruthy();
    expect(screen.queryByText("Erneut versuchen")).toBeNull();
  });
});
