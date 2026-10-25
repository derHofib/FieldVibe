// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import { authStore } from "./authStore";
import { ApiError, apiFetch, apiFetchAlleSeiten, apiFetchBlob, sitzungAusCookieWiederherstellen } from "./client";
import { kundenApi } from "./endpoints";

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

describe("apiFetchAlleSeiten", () => {
  function seite(zeilen: unknown[], gesamt?: number) {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (gesamt !== undefined) headers["X-Total-Count"] = String(gesamt);
    return new Response(JSON.stringify(zeilen), { status: 200, headers });
  }
  const zeilen = (von: number, anzahl: number) => Array.from({ length: anzahl }, (_, i) => ({ id: von + i }));

  it("lädt bei vollständiger erster Seite nichts nach", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(seite(zeilen(0, 3), 3));
    vi.stubGlobal("fetch", fetchMock);

    expect(await apiFetchAlleSeiten("/api/kunden")).toHaveLength(3);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/kunden\?limit=1000&offset=0$/);
  });

  it("blättert anhand von X-Total-Count über alle Seiten", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(seite(zeilen(0, 1000), 2500))
      .mockResolvedValueOnce(seite(zeilen(1000, 1000), 2500))
      .mockResolvedValueOnce(seite(zeilen(2000, 500), 2500));
    vi.stubGlobal("fetch", fetchMock);

    const alle = await apiFetchAlleSeiten<{ id: number }>("/api/anlagen");
    expect(alle.map((z) => z.id)).toEqual(zeilen(0, 2500).map((z) => z.id));
    expect(fetchMock.mock.calls.map(([url]) => new URL(url).searchParams.get("offset"))).toEqual(["0", "1000", "2000"]);
  });

  it("hängt die Seitenparameter an einen bestehenden Querystring an", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(seite([], 0));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetchAlleSeiten("/api/material?lager_id=l1");
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/material\?lager_id=l1&limit=1000&offset=0$/);
  });

  it("liefert ohne X-Total-Count nur die erste Seite", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(seite(zeilen(0, 1000)));
    vi.stubGlobal("fetch", fetchMock);

    expect(await apiFetchAlleSeiten("/api/termine")).toHaveLength(1000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("bricht bei leerer Folgeseite ab, auch wenn die Gesamtzahl noch nicht erreicht ist", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(seite(zeilen(0, 1000), 1500))
      .mockResolvedValueOnce(seite([], 1500));
    vi.stubGlobal("fetch", fetchMock);

    expect(await apiFetchAlleSeiten("/api/maengel")).toHaveLength(1000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("wirft den Fehler einer Folgeseite statt ein Teilergebnis zu liefern", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(seite(zeilen(0, 1000), 1200))
        .mockResolvedValueOnce(json(500, { detail: "kaputt" })),
    );

    const fehler = await apiFetchAlleSeiten("/api/angebote").catch((e) => e);
    expect(fehler).toBeInstanceOf(ApiError);
    expect(fehler.status).toBe(500);
  });

  it("kundenApi.list liefert mehr als 1000 Kunden", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(seite(zeilen(0, 1000), 1001))
      .mockResolvedValueOnce(seite(zeilen(1000, 1), 1001));
    vi.stubGlobal("fetch", fetchMock);

    expect(await kundenApi.list("Müller")).toHaveLength(1001);
    expect(fetchMock.mock.calls[1][0]).toMatch(/\/api\/kunden\?q=M%C3%BCller&limit=1000&offset=1000$/);
  });
});
