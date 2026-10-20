// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import { authStore } from "./authStore";
import { ApiError, apiFetch, apiFetchBlob, sitzungAusCookieWiederherstellen } from "./client";

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

function json(status: number, body: unknown = {}) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("Refresh per HttpOnly-Cookie", () => {
  afterEach(() => authStore.clear());

  it("erneuert bei 401 ohne Refresh-Token im Speicher: credentials include, leerer Body, Cookie-Header", async () => {
    authStore.setPrimary({ accessToken: "alt" });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(401))
      .mockResolvedValueOnce(json(200, { access_token: "neu", refresh_token: null, token_type: "bearer" }))
      .mockResolvedValueOnce(json(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    expect(await apiFetch("/api/vorgaenge")).toEqual({ ok: true });

    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toMatch(/\/api\/auth\/refresh$/);
    expect(init.credentials).toBe("include");
    expect(init.body).toBe("{}");
    expect(init.headers["X-Refresh-Cookie"]).toBe("1");
    expect(authStore.getState().primary).toEqual({ accessToken: "neu" });
    expect(localStorage.getItem("fieldvibe_auth_v1")).not.toContain("refresh");
  });

  it("sendet ein aus einem aelteren Bundle gespeichertes Refresh-Token einmalig und verwirft es", async () => {
    authStore.setPrimary({ accessToken: "alt", refreshToken: "legacy-refresh" });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(401))
      .mockResolvedValueOnce(json(200, { access_token: "neu", refresh_token: null, token_type: "bearer" }))
      .mockResolvedValueOnce(json(200, {}));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/x");

    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ refresh_token: "legacy-refresh" });
    expect(authStore.getState().primary?.refreshToken).toBeUndefined();
  });

  it("meldet bei abgelehntem Cookie ab, bei Serverfehler nicht", async () => {
    authStore.setPrimary({ accessToken: "a" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(502)));
    expect(await sitzungAusCookieWiederherstellen()).toBe(false);
    expect(authStore.getState().primary).not.toBeNull();

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(401)));
    expect(await sitzungAusCookieWiederherstellen()).toBe(false);
    expect(authStore.getState().primary).toBeNull();
  });

  it("stellt die Sitzung beim Start aus dem Cookie wieder her", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(200, { access_token: "frisch", token_type: "bearer" })));
    expect(await sitzungAusCookieWiederherstellen()).toBe(true);
    expect(authStore.getActiveAccessToken()).toBe("frisch");
  });

  it("ist offline still (false statt Fehler)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    expect(await sitzungAusCookieWiederherstellen()).toBe(false);
  });

  it("schickt Cookies nur an Auth-Pfade", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => json(200, {}));
    vi.stubGlobal("fetch", fetchMock);
    await apiFetch("/api/auth/login", { method: "POST", body: "{}" });
    await apiFetch("/api/vorgaenge");
    expect(fetchMock.mock.calls[0][1].credentials).toBe("include");
    expect(fetchMock.mock.calls[1][1].credentials).toBeUndefined();
  });
});
