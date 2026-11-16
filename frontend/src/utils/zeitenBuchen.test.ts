import { describe, expect, it } from "vitest";

import type { Zeiterfassung } from "../types";
import {
  alleAuswaehlbarenIds,
  dauerSekunden,
  gruppenBilden,
  gruppenSumme,
  kopfCheckboxZustand,
  sortiereEintraege,
  summeSekunden,
} from "./zeitenBuchen";

let zaehler = 0;
function eintrag(teil: Partial<Zeiterfassung> = {}): Zeiterfassung {
  zaehler += 1;
  return {
    id: `e${zaehler}`,
    vorgang_id: null,
    vorgangsnummer: null,
    vorgang_kunde_id: null,
    vorgang_auftrag_id: null,
    vorgang_projekt_id: null,
    techniker_id: "t1",
    start_at: "2025-03-01T08:00:00Z",
    ende_at: "2025-03-01T09:00:00Z",
    taetigkeit: null,
    abrechenbar: true,
    kategorie: "auftrag",
    lv_position_id: null,
    buchungsstatus: "vermerkt",
    vorgemerkt_von: null,
    vorgemerkt_am: null,
    gebucht_von: null,
    gebucht_am: null,
    km: null,
    fahrzeug_id: null,
    quelle: "manuell",
    km_abgerechnet_rechnung_id: null,
    created_at: "2025-03-01T00:00:00Z",
    updated_at: "2025-03-01T00:00:00Z",
    ...teil,
  };
}

const ids = (liste: Zeiterfassung[]) => liste.map((e) => e.id);

describe("gruppenBilden", () => {
  it("gruppiert nach Vorgang und ohne Vorgang nach Kategorie", () => {
    const a = eintrag({ id: "a", vorgang_id: "v1", vorgangsnummer: "V-2" });
    const b = eintrag({ id: "b", vorgang_id: "v1", vorgangsnummer: "V-2" });
    const c = eintrag({ id: "c", kategorie: "fahrzeit" });
    const gruppen = gruppenBilden([a, b, c], [], [], []);
    expect(gruppen).toHaveLength(2);
    const mitVorgang = gruppen.find((g) => g.vorgangId === "v1")!;
    expect(ids(mitVorgang.eintraege)).toEqual(["a", "b"]);
    expect(mitVorgang.kategorieLabel).toBeNull();
    expect(mitVorgang.vorgangsnummer).toBe("V-2");
    const ohne = gruppen.find((g) => g.vorgangId === null)!;
    expect(ohne.key).toBe("kategorie:fahrzeit");
    expect(ohne.kategorieLabel).toBeTruthy();
    expect(ohne.kontext).toBeNull();
  });

  it("baut den Kontext aus Kunde, Auftrag und Projekt", () => {
    const e = eintrag({
      vorgang_id: "v1",
      vorgang_kunde_id: "k1",
      vorgang_auftrag_id: "a1",
      vorgang_projekt_id: "p1",
    });
    const [g] = gruppenBilden(
      [e],
      [{ id: "k1", name: "Müller GmbH" }],
      [{ id: "a1", titel: "Wartung" }],
      [{ id: "p1", name: "Neubau" }],
    );
    expect(g.kontext).toBe("Müller GmbH · Wartung · Neubau");
  });

  it("lässt unbekannte Kontext-Teile aus", () => {
    const e = eintrag({ vorgang_id: "v1", vorgang_kunde_id: "k1", vorgang_auftrag_id: "unbekannt" });
    const [g] = gruppenBilden([e], [{ id: "k1", name: "Müller GmbH" }], [], undefined);
    expect(g.kontext).toBe("Müller GmbH");
  });

  it("sortiert die Gruppen nach Vorgangsnummer bzw. Kategorie-Label", () => {
    const b = eintrag({ vorgang_id: "v2", vorgangsnummer: "V-2" });
    const a = eintrag({ vorgang_id: "v1", vorgangsnummer: "V-1" });
    expect(gruppenBilden([b, a], [], [], []).map((g) => g.vorgangsnummer)).toEqual(["V-1", "V-2"]);
  });
});

describe("Summen", () => {
  it("berechnet Dauer in Sekunden", () => {
    expect(dauerSekunden(eintrag({ start_at: "2025-03-01T08:00:00Z", ende_at: "2025-03-01T09:30:00Z" }))).toBe(5400);
  });

  it("summiert Listen und Gruppen", () => {
    const liste = [
      eintrag({ vorgang_id: "v1" }),
      eintrag({ vorgang_id: "v1", start_at: "2025-03-02T08:00:00Z", ende_at: "2025-03-02T10:00:00Z" }),
    ];
    expect(summeSekunden(liste)).toBe(3600 + 7200);
    expect(summeSekunden([])).toBe(0);
    const [g] = gruppenBilden(liste, [], [], []);
    expect(gruppenSumme(g)).toBe(10800);
  });
});

describe("sortiereEintraege", () => {
  const name = (id: string) => ({ t1: "Zeller", t2: "Ähnlich", t3: "Meier" })[id] ?? id;

  it("sortiert nach Datum auf- und absteigend ohne Mutation", () => {
    const a = eintrag({ id: "a", start_at: "2025-03-03T08:00:00Z", ende_at: "2025-03-03T09:00:00Z" });
    const b = eintrag({ id: "b", start_at: "2025-03-01T08:00:00Z", ende_at: "2025-03-01T09:00:00Z" });
    const c = eintrag({ id: "c", start_at: "2025-03-02T08:00:00Z", ende_at: "2025-03-02T09:00:00Z" });
    const eingabe = [a, b, c];
    expect(ids(sortiereEintraege(eingabe, { key: "datum", absteigend: false }, name))).toEqual(["b", "c", "a"]);
    expect(ids(sortiereEintraege(eingabe, { key: "datum", absteigend: true }, name))).toEqual(["a", "c", "b"]);
    expect(ids(eingabe)).toEqual(["a", "b", "c"]);
  });

  it("sortiert nach Technikername (deutsche Collation) mit start_at als Zweitschlüssel", () => {
    const a = eintrag({ id: "a", techniker_id: "t1", start_at: "2025-03-01T08:00:00Z" });
    const b = eintrag({ id: "b", techniker_id: "t2", start_at: "2025-03-01T08:00:00Z" });
    const c = eintrag({ id: "c", techniker_id: "t3", start_at: "2025-03-01T08:00:00Z" });
    const d = eintrag({ id: "d", techniker_id: "t3", start_at: "2025-02-01T08:00:00Z" });
    expect(ids(sortiereEintraege([a, b, c, d], { key: "techniker", absteigend: false }, name))).toEqual([
      "b",
      "d",
      "c",
      "a",
    ]);
    // Zweitschlüssel bleibt auch absteigend aufsteigend.
    expect(ids(sortiereEintraege([a, b, c, d], { key: "techniker", absteigend: true }, name))).toEqual([
      "a",
      "d",
      "c",
      "b",
    ]);
  });

  it("sortiert nach Vorgangsnummer, sonst Kategorie-Label", () => {
    const a = eintrag({ id: "a", vorgang_id: "v2", vorgangsnummer: "V-2" });
    const b = eintrag({ id: "b", vorgang_id: "v1", vorgangsnummer: "V-1" });
    const c = eintrag({ id: "c", vorgang_id: "v1", vorgangsnummer: "V-1", start_at: "2025-02-01T08:00:00Z" });
    const aufsteigend = sortiereEintraege([a, b, c], { key: "vorgang", absteigend: false }, name);
    expect(ids(aufsteigend)).toEqual(["c", "b", "a"]);
    expect(ids(sortiereEintraege([a, b, c], { key: "vorgang", absteigend: true }, name))).toEqual(["a", "c", "b"]);

    // Ohne Vorgang zählt das Kategorie-Label (Ziffern sortieren vor "Fahrzeit" etc.).
    const ohne = eintrag({ id: "o", kategorie: "fahrzeit" });
    const mit = eintrag({ id: "m", vorgang_id: "v1", vorgangsnummer: "V-1" });
    const ergebnis = sortiereEintraege([ohne, mit], { key: "vorgang", absteigend: false }, name);
    expect(ergebnis).toHaveLength(2);
    expect(ids(sortiereEintraege([mit, ohne], { key: "vorgang", absteigend: true }, name))).toEqual(
      ids([...ergebnis].reverse()),
    );
  });

  it("sortiert nach Dauer mit Gleichstand über start_at", () => {
    const kurz = eintrag({ id: "kurz", start_at: "2025-03-05T08:00:00Z", ende_at: "2025-03-05T08:30:00Z" });
    const lang = eintrag({ id: "lang", start_at: "2025-03-04T08:00:00Z", ende_at: "2025-03-04T11:00:00Z" });
    const gleichSpaet = eintrag({ id: "g2", start_at: "2025-03-07T08:00:00Z", ende_at: "2025-03-07T09:00:00Z" });
    const gleichFrueh = eintrag({ id: "g1", start_at: "2025-03-06T08:00:00Z", ende_at: "2025-03-06T09:00:00Z" });
    const liste = [lang, gleichSpaet, kurz, gleichFrueh];
    expect(ids(sortiereEintraege(liste, { key: "dauer", absteigend: false }, name))).toEqual([
      "kurz",
      "g1",
      "g2",
      "lang",
    ]);
    expect(ids(sortiereEintraege(liste, { key: "dauer", absteigend: true }, name))).toEqual([
      "lang",
      "g1",
      "g2",
      "kurz",
    ]);
  });
});

describe("alleAuswaehlbarenIds", () => {
  const sichtbar = [
    eintrag({ id: "a", buchungsstatus: "abgerechnet" }),
    eintrag({ id: "b", buchungsstatus: "vorgemerkt" }),
    eintrag({ id: "c", buchungsstatus: "vermerkt" }),
    eintrag({ id: "d", buchungsstatus: "vorgemerkt" }),
  ];

  it("nimmt ohne Auswahl den Status des ersten auswählbaren Eintrags (abgerechnet übersprungen)", () => {
    expect([...alleAuswaehlbarenIds(sichtbar, null)].sort()).toEqual(["b", "d"]);
  });

  it("nimmt mit Vorauswahl deren Status", () => {
    expect([...alleAuswaehlbarenIds(sichtbar, "vermerkt")]).toEqual(["c"]);
  });

  it("schließt abgerechnet auch bei Vorauswahl abgerechnet aus", () => {
    expect(alleAuswaehlbarenIds(sichtbar, "abgerechnet").size).toBe(0);
  });

  it("liefert eine leere Menge, wenn nichts auswählbar ist", () => {
    expect(alleAuswaehlbarenIds([eintrag({ buchungsstatus: "abgerechnet" })], null).size).toBe(0);
    expect(alleAuswaehlbarenIds([], null).size).toBe(0);
  });
});

describe("kopfCheckboxZustand", () => {
  const sichtbar = [
    eintrag({ id: "a", buchungsstatus: "vorgemerkt" }),
    eintrag({ id: "b", buchungsstatus: "vorgemerkt" }),
    eintrag({ id: "c", buchungsstatus: "vermerkt" }),
  ];

  it("aus ohne Auswahl und bei leerer Liste", () => {
    expect(kopfCheckboxZustand(sichtbar, new Set(), null)).toBe("aus");
    expect(kopfCheckboxZustand([], new Set(), null)).toBe("aus");
  });

  it("teilweise, wenn nur ein Teil ausgewählt ist", () => {
    expect(kopfCheckboxZustand(sichtbar, new Set(["a"]), "vorgemerkt")).toBe("teilweise");
  });

  it("an, wenn alle auswählbaren des Status ausgewählt sind", () => {
    expect(kopfCheckboxZustand(sichtbar, new Set(["a", "b"]), "vorgemerkt")).toBe("an");
  });
});
