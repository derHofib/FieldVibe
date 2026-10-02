// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { authStore } from "./authStore";
import { kundenAuthStore } from "./kundenAuthStore";
import { partnerApiFetch } from "./partnerClient";
import { PARTNER_STORAGE_KEY, partnerAuthStore } from "./partnerAuthStore";

function antwort(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("partnerAuthStore", () => {
  beforeEach(() => {
    partnerAuthStore.clear();
    kundenAuthStore.clear();
  });

  it("speichert unter eigenem Schluessel, getrennt von Kunden- und Mitarbeiter-Token", () => {
    partnerAuthStore.setTokens({ accessToken: "p-a", refreshToken: "p-r" });
    expect(JSON.parse(localStorage.getItem(PARTNER_STORAGE_KEY)!)).toEqual({ accessToken: "p-a", refreshToken: "p-r" });
    expect(kundenAuthStore.getAccessToken()).toBeNull();
    expect(PARTNER_STORAGE_KEY).not.toBe("fieldvibe_kundenportal_auth_v1");
    expect(Object.keys(localStorage).filter((k) => k !== PARTNER_STORAGE_KEY && localStorage.getItem(k)?.includes("p-a"))).toEqual([]);
  });

  it("clear() entfernt nur den Partner-Eintrag", () => {
    kundenAuthStore.setTokens({ accessToken: "k-a", refreshToken: "k-r" });
    partnerAuthStore.setTokens({ accessToken: "p-a", refreshToken: "p-r" });
    partnerAuthStore.clear();
    expect(partnerAuthStore.getAccessToken()).toBeNull();
    expect(kundenAuthStore.getAccessToken()).toBe("k-a");
  });
});

describe("partnerApiFetch", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    partnerAuthStore.clear();
    kundenAuthStore.clear();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sendet das Partner-Token, nie Mitarbeiter- oder Kunden-Token", async () => {
    authStore.setPrimary({ accessToken: "staff-a", refreshToken: "staff-r" });
    kundenAuthStore.setTokens({ accessToken: "kunde-a", refreshToken: "kunde-r" });
    partnerAuthStore.setTokens({ accessToken: "partner-a", refreshToken: "partner-r" });
    fetchMock.mockResolvedValueOnce(antwort(200, []));

    await partnerApiFetch("/api/partnerportal/auftraege");

    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer partner-a");
    authStore.clear();
  });

  it("refresht bei 401 mit dem Partner-Refresh-Endpunkt und wiederholt die Anfrage", async () => {
    partnerAuthStore.setTokens({ accessToken: "alt", refreshToken: "ref" });
    fetchMock
      .mockResolvedValueOnce(antwort(401, { detail: "abgelaufen" }))
      .mockResolvedValueOnce(antwort(200, { access_token: "neu", refresh_token: "ref2", token_type: "bearer" }))
      .mockResolvedValueOnce(antwort(200, [{ id: "1" }]));

    const result = await partnerApiFetch<{ id: string }[]>("/api/partnerportal/auftraege");

    expect(result).toEqual([{ id: "1" }]);
    expect(fetchMock.mock.calls[1][0]).toContain("/api/partnerportal/auth/refresh");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ refresh_token: "ref" });
    expect((fetchMock.mock.calls[2][1].headers as Headers).get("Authorization")).toBe("Bearer neu");
    expect(partnerAuthStore.getState()).toEqual({ accessToken: "neu", refreshToken: "ref2" });
  });

  it("meldet ab, wenn der Refresh abgelehnt wird", async () => {
    partnerAuthStore.setTokens({ accessToken: "alt", refreshToken: "ref" });
    fetchMock
      .mockResolvedValueOnce(antwort(401, { detail: "abgelaufen" }))
      .mockResolvedValueOnce(antwort(401, { detail: "Zugang nicht gültig" }));

    await expect(partnerApiFetch("/api/partnerportal/auftraege")).rejects.toMatchObject({ status: 401 });
    expect(partnerAuthStore.getState()).toBeNull();
  });

  it("behaelt die Sitzung bei Netzwerkfehler im Refresh", async () => {
    partnerAuthStore.setTokens({ accessToken: "alt", refreshToken: "ref" });
    fetchMock.mockResolvedValueOnce(antwort(401, { detail: "x" })).mockRejectedValueOnce(new TypeError("offline"));

    await expect(partnerApiFetch("/api/partnerportal/auftraege")).rejects.toMatchObject({ status: 401 });
    expect(partnerAuthStore.getState()).not.toBeNull();
  });

  it("refresht nicht beim Login-401 (falsche Zugangsdaten)", async () => {
    partnerAuthStore.setTokens({ accessToken: "alt", refreshToken: "ref" });
    fetchMock.mockResolvedValueOnce(antwort(401, { detail: "E-Mail oder Passwort falsch" }));

    await expect(
      partnerApiFetch("/api/partnerportal/auth/login", { method: "POST", body: "{}" }),
    ).rejects.toMatchObject({ status: 401, message: "E-Mail oder Passwort falsch" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(partnerAuthStore.getState()).not.toBeNull();
  });

  it("bündelt parallele 401 auf einen einzigen Refresh", async () => {
    partnerAuthStore.setTokens({ accessToken: "alt", refreshToken: "ref" });
    fetchMock.mockImplementation(async (url: string, opts: RequestInit) => {
      if (url.includes("/auth/refresh")) return antwort(200, { access_token: "neu", refresh_token: "r2", token_type: "bearer" });
      const auth = (opts.headers as Headers).get("Authorization");
      return auth === "Bearer neu" ? antwort(200, {}) : antwort(401, { detail: "x" });
    });

    await Promise.all([partnerApiFetch("/api/partnerportal/auftraege"), partnerApiFetch("/api/partnerportal/auth/me")]);

    const refreshes = fetchMock.mock.calls.filter((c) => String(c[0]).includes("/auth/refresh"));
    expect(refreshes).toHaveLength(1);
  });
});
