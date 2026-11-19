import { describe, expect, it } from "vitest";

import { betreuungFilterFelder } from "../components/kunde/useBetreuungFilter";
import { filterAnwenden, sucheAnwenden } from "../components/filter/auswerten";
import type { Betreuer, Kunde, UserAuswahl } from "../types";
import {
  auswahlAusBetreuung,
  betreuerUmschalten,
  betreuungFilterOptionen,
  betreuungSuchtext,
  betreuungUnterzeile,
  hauptbetreuerUmschalten,
  kandidatenBilden,
  sichtverlust,
} from "./betreuung";

const kunde = (id: string, betreuung?: Kunde["betreuung"]) => ({ id, name: `Kunde ${id}`, betreuung }) as Kunde;
const K = [
  kunde("1", [
    { user_id: "u1", name: "Jonas Weber", hauptbetreuer: true },
    { user_id: "u2", name: "Lena Schulz", hauptbetreuer: false },
  ]),
  kunde("2", [{ user_id: "u2", name: "Lena Schulz", hauptbetreuer: true }]),
  kunde("3", []),
  kunde("4", undefined),
];
const felder = betreuungFilterFelder([]);
const ids = (zeilen: Kunde[]) => zeilen.map((k) => k.id);

describe("Betreuungs-Filter", () => {
  it("Betreuung ist X findet Haupt- und Vertretungsbetreuer", () => {
    expect(ids(filterAnwenden(K, [{ feld: "betreuung", op: "ist", wert: ["u2"] }], felder))).toEqual(["1", "2"]);
  });
  it("Betreuung ist leer = Ohne Betreuung", () => {
    expect(ids(filterAnwenden(K, [{ feld: "betreuung", op: "leer" }], felder))).toEqual(["3", "4"]);
  });
  it("Betreuung ist nicht X", () => {
    expect(ids(filterAnwenden(K, [{ feld: "betreuung", op: "ist_nicht", wert: ["u1"] }], felder))).toEqual(["2", "3", "4"]);
  });
  it("Hauptbetreuer ist X ignoriert Vertretungen", () => {
    expect(ids(filterAnwenden(K, [{ feld: "hauptbetreuer", op: "ist", wert: ["u2"] }], felder))).toEqual(["2"]);
  });
  it("Optionen: Ich zuerst, dann Mitarbeiter und Betreuer aus der Liste ohne Doppelte", () => {
    const o = betreuungFilterOptionen("u2", [{ id: "u3", name: "Anna Roth" }], K);
    expect(o.map((x) => x.label)).toEqual(["Ich", "Anna Roth", "Jonas Weber"]);
    expect(o[0].wert).toBe("u2");
  });
  it("einfache Suche findet Betreuernamen", () => {
    const treffer = sucheAnwenden(K, "weber", (k) => `${k.name} ${betreuungSuchtext(k.betreuung)}`);
    expect(ids(treffer)).toEqual(["1"]);
  });
});

const betreuer = (user_id: string, extra: Partial<Betreuer> = {}): Betreuer => ({
  user_id,
  name: user_id,
  avatar_url: null,
  hauptbetreuer: false,
  aktiv: true,
  nur_betreute_kunden: false,
  account_typ_name: null,
  ...extra,
});

describe("Betreuungs-Auswahl", () => {
  it("Stern setzt Häkchen mit und nimmt ihn dem bisherigen weg", () => {
    const start = auswahlAusBetreuung([betreuer("a", { hauptbetreuer: true })]);
    const neu = hauptbetreuerUmschalten(start, "b");
    expect(neu).toEqual({ userIds: ["a", "b"], hauptId: "b" });
  });
  it("erneutes Tippen nimmt den Stern weg, Häkchen bleibt", () => {
    expect(hauptbetreuerUmschalten({ userIds: ["a"], hauptId: "a" }, "a")).toEqual({ userIds: ["a"], hauptId: null });
  });
  it("Abwählen des Hauptbetreuers entfernt auch den Stern", () => {
    expect(betreuerUmschalten({ userIds: ["a", "b"], hauptId: "a" }, "a")).toEqual({ userIds: ["b"], hauptId: null });
  });
  it("Sichtverlust nur für abgewählte Betreuer mit nur_betreute_kunden", () => {
    const bisher = [betreuer("a", { nur_betreute_kunden: true }), betreuer("b", { nur_betreute_kunden: true }), betreuer("c")];
    const v = sichtverlust(bisher, { userIds: ["b"], hauptId: null });
    expect(v.map((x) => x.user_id)).toEqual(["a"]);
  });
  it("Kandidaten: aktive Mitarbeiter plus deaktivierte bisherige Betreuer", () => {
    const alle = [
      { id: "a", name: "Anna", role: "custom", aktiv: true, nur_zugewiesene_kunden: false, account_typ_name: "Büro" },
      { id: "x", name: "Inaktiv", role: "custom", aktiv: false, nur_zugewiesene_kunden: false, account_typ_name: null },
      { id: "p", name: "Portal", role: "loesch_ansicht", aktiv: true, nur_zugewiesene_kunden: false, account_typ_name: null },
    ] as UserAuswahl[];
    const k = kandidatenBilden(alle, [betreuer("alt", { name: "Alt", aktiv: false })]);
    expect(k.map((x) => x.id)).toEqual(["alt", "a"]);
    expect(k[0].aktiv).toBe(false);
  });
  it("Unterzeile", () => {
    expect(betreuungUnterzeile(betreuer("a", { hauptbetreuer: true, account_typ_name: "Techniker", nur_betreute_kunden: true }))).toBe(
      "Hauptbetreuer · Techniker · sieht nur betreute Kunden",
    );
    expect(betreuungUnterzeile(betreuer("b"))).toBe("Vertretung");
  });
});
