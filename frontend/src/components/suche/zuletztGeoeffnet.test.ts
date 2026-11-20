// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { leereZuletzt, liesZuletzt, merkeZuletzt, type ZuletztEintrag } from "./zuletztGeoeffnet";

vi.mock("../../context/AuthContext", () => ({ useAuth: () => ({ currentUser: { id: "u1" } }) }));

const eintrag = (id: string, kategorie: ZuletztEintrag["kategorie"] = "vorgang"): ZuletztEintrag => ({
  kategorie,
  id,
  titel: `Titel ${id}`,
  untertitel: "",
});

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("zuletzt geöffnet", () => {
  it("neueste zuerst und dedupliziert nach Kategorie + ID", () => {
    merkeZuletzt("u1", eintrag("1"));
    merkeZuletzt("u1", eintrag("2"));
    merkeZuletzt("u1", eintrag("1"));
    merkeZuletzt("u1", eintrag("1", "kunde"));
    expect(liesZuletzt("u1").map((e) => `${e.kategorie}:${e.id}`)).toEqual(["kunde:1", "vorgang:1", "vorgang:2"]);
  });

  it("behält höchstens 8 Einträge", () => {
    for (let i = 0; i < 12; i++) merkeZuletzt("u1", eintrag(String(i)));
    const liste = liesZuletzt("u1");
    expect(liste).toHaveLength(8);
    expect(liste[0].id).toBe("11");
    expect(liste[7].id).toBe("4");
  });

  it("trennt Nutzer und kann leeren", () => {
    merkeZuletzt("u1", eintrag("1"));
    expect(liesZuletzt("u2")).toEqual([]);
    leereZuletzt("u1");
    expect(liesZuletzt("u1")).toEqual([]);
  });

  it("ignoriert kaputte Daten im Speicher", () => {
    localStorage.setItem("suche.zuletzt.u1", "{kaputt");
    expect(liesZuletzt("u1")).toEqual([]);
    localStorage.setItem("suche.zuletzt.u1", JSON.stringify([{ foo: 1 }, eintrag("1")]));
    expect(liesZuletzt("u1")).toHaveLength(1);
  });

  it("stürzt nicht ab, wenn localStorage wirft", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("gesperrt");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("voll");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("gesperrt");
    });
    expect(() => merkeZuletzt("u1", eintrag("1"))).not.toThrow();
    expect(liesZuletzt("u1")).toEqual([]);
    expect(() => leereZuletzt("u1")).not.toThrow();
  });
});
