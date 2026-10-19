// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetchBlob } from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("apiFetchBlob", () => {
  it("übernimmt das JSON-detail eines Fehlers statt nur des Statustextes", async () => {
    const meldung = "Für Steuerkategorie AE ist kein Erlöskonto hinterlegt";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: meldung }), {
          status: 422,
          statusText: "Unprocessable Entity",
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const fehler = await apiFetchBlob("/api/auswertung/datev-export").catch((e) => e);
    expect(fehler).toBeInstanceOf(ApiError);
    expect(fehler.status).toBe(422);
    expect(fehler.message).toBe(meldung);
  });

  it("fällt ohne JSON-Body auf den Statustext zurück", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>", { status: 502, statusText: "Bad Gateway" })));
    const fehler = await apiFetchBlob("/x").catch((e) => e);
    expect(fehler.message).toBe("Bad Gateway");
  });
});
