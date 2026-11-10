import { describe, expect, it } from "vitest";

import {
  istErloeskontoFehler,
  nachweisStatus,
  optionZuFelder,
  positionZuEingabe,
  pruefe13bVoraussetzungen,
  steuerKurzlabel,
  validiereSteuer,
  vorbelegung,
  zerlegeListenFehler,
} from "./steuer";

describe("optionZuFelder", () => {
  it("bildet die Regelsätze auf S ohne Grund ab", () => {
    expect(optionZuFelder("s19")).toEqual({
      steuer_kategorie: "S",
      steuer_satz: "19.00",
      steuer_grund: null,
      steuer_grund_text: null,
    });
    expect(optionZuFelder("s7").steuer_satz).toBe("7.00");
  });

  it("setzt bei Z, AE und E Satz 0 und den passenden Grund", () => {
    expect(optionZuFelder("z_pv")).toMatchObject({ steuer_kategorie: "Z", steuer_satz: "0.00", steuer_grund: "pv_12_3" });
    expect(optionZuFelder("ae_13b")).toMatchObject({
      steuer_kategorie: "AE",
      steuer_satz: "0.00",
      steuer_grund: "reverse_charge_13b",
      steuer_grund_text: null,
    });
    expect(optionZuFelder("e_befreit", "  Ausfuhr  ")).toMatchObject({
      steuer_kategorie: "E",
      steuer_grund: "sonstige_befreiung",
      steuer_grund_text: "Ausfuhr",
    });
  });
});

describe("positionZuEingabe", () => {
  it("ist die Umkehrung von optionZuFelder", () => {
    for (const option of ["s19", "s7", "z_pv", "ae_13b"] as const) {
      expect(positionZuEingabe(optionZuFelder(option))?.option).toBe(option);
    }
    expect(positionZuEingabe(optionZuFelder("e_befreit", "Ausfuhr"))).toEqual({ option: "e_befreit", text: "Ausfuhr" });
  });

  it("kennt keine Option für Kleinunternehmer-Positionen", () => {
    expect(
      positionZuEingabe({
        steuer_kategorie: "E",
        steuer_satz: "0.00",
        steuer_grund: "kleinunternehmer_19",
        steuer_grund_text: null,
      }),
    ).toBeNull();
  });

  it("fällt bei Altdaten ohne Steuerfelder auf 19 % zurück", () => {
    expect(positionZuEingabe({})?.option).toBe("s19");
  });
});

describe("steuerKurzlabel", () => {
  it("liefert kurze Texte für das Badge", () => {
    expect(steuerKurzlabel(optionZuFelder("s7"))).toBe("7 %");
    expect(steuerKurzlabel(optionZuFelder("z_pv"))).toBe("0 % PV");
    expect(steuerKurzlabel(optionZuFelder("ae_13b"))).toBe("Reverse Charge");
    expect(steuerKurzlabel(optionZuFelder("e_befreit", "abc"))).toBe("Steuerfrei");
    expect(
      steuerKurzlabel({
        steuer_kategorie: "E",
        steuer_satz: "0.00",
        steuer_grund: "kleinunternehmer_19",
        steuer_grund_text: null,
      }),
    ).toBe("§ 19 UStG");
  });
});

describe("vorbelegung", () => {
  it("übernimmt den Satz des Belegs", () => {
    expect(vorbelegung("19.00").option).toBe("s19");
    expect(vorbelegung("7.00").option).toBe("s7");
    expect(vorbelegung(7).option).toBe("s7");
  });

  it("nimmt ohne Beleg-Satz 19 %", () => {
    expect(vorbelegung(undefined).option).toBe("s19");
    expect(vorbelegung(null).option).toBe("s19");
  });

  it("verlangt bei Beleg 0 % eine Begründung statt still 19 % zu nehmen", () => {
    const v = vorbelegung("0.00");
    expect(v.option).toBe("e_befreit");
    expect(validiereSteuer(v)).not.toBeNull();
  });
});

describe("validiereSteuer", () => {
  it("braucht nur bei Steuerfrei einen Text", () => {
    expect(validiereSteuer({ option: "s19", text: "" })).toBeNull();
    expect(validiereSteuer({ option: "ae_13b", text: "" })).toBeNull();
    expect(validiereSteuer({ option: "e_befreit", text: "" })).toMatch(/Begründung/);
  });

  it("prüft 3 bis 200 Zeichen nach dem Trimmen", () => {
    expect(validiereSteuer({ option: "e_befreit", text: "  ab  " })).not.toBeNull();
    expect(validiereSteuer({ option: "e_befreit", text: " abc " })).toBeNull();
    expect(validiereSteuer({ option: "e_befreit", text: "a".repeat(200) })).toBeNull();
    expect(validiereSteuer({ option: "e_befreit", text: "a".repeat(201) })).toMatch(/zu lang/);
  });
});

describe("pruefe13bVoraussetzungen", () => {
  const heute = "2026-10-19";
  const ok = { ust_idnr: "DE123456789", ust_13b_nachweis_bis: "2027-01-31" };

  it("meldet nichts bei vollständigen, gültigen Angaben", () => {
    expect(pruefe13bVoraussetzungen(ok, null, heute)).toEqual([]);
  });

  it("gilt ein Nachweis bis genau zum Leistungsdatum noch als gültig", () => {
    expect(pruefe13bVoraussetzungen({ ...ok, ust_13b_nachweis_bis: "2026-12-01" }, "2026-12-01", heute)).toEqual([]);
  });

  it("meldet einen am Vortag des Leistungsdatums abgelaufenen Nachweis", () => {
    const probleme = pruefe13bVoraussetzungen({ ...ok, ust_13b_nachweis_bis: "2026-11-30" }, "2026-12-01", heute);
    expect(probleme).toHaveLength(1);
    expect(probleme[0]).toContain("30.11.2026");
    expect(probleme[0]).toContain("Leistungsdatum 01.12.2026");
  });

  it("vergleicht ohne Leistungsdatum mit heute", () => {
    expect(pruefe13bVoraussetzungen({ ...ok, ust_13b_nachweis_bis: heute }, null, heute)).toEqual([]);
    const probleme = pruefe13bVoraussetzungen({ ...ok, ust_13b_nachweis_bis: "2026-10-18" }, "", heute);
    expect(probleme[0]).toContain("heute, 19.10.2026");
  });

  it("meldet fehlende USt-IdNr. und fehlendes Ablaufdatum getrennt", () => {
    const probleme = pruefe13bVoraussetzungen({ ust_idnr: "  ", ust_13b_nachweis_bis: null }, null, heute);
    expect(probleme).toHaveLength(2);
    expect(probleme[0]).toContain("USt-IdNr.");
    expect(probleme[1]).toContain("Ablaufdatum");
  });

  it("behandelt einen noch nicht geladenen Kunden wie fehlende Angaben", () => {
    expect(pruefe13bVoraussetzungen(undefined, null, heute)).toHaveLength(2);
  });
});

describe("nachweisStatus", () => {
  const heute = "2026-10-19";

  it("unterscheidet fehlend, gültig, läuft ab und abgelaufen", () => {
    expect(nachweisStatus(null, heute).art).toBe("fehlt");
    expect(nachweisStatus("2027-10-19", heute)).toEqual({ art: "gueltig", label: "Gültig bis 19.10.2027" });
    expect(nachweisStatus("2026-10-18", heute)).toEqual({ art: "abgelaufen", label: "Abgelaufen am 18.10.2026" });
  });

  it("zählt Kalendertage, unabhängig von der Sommerzeitumstellung", () => {
    expect(nachweisStatus("2026-10-30", heute)).toEqual({ art: "laeuft_ab", label: "Läuft in 11 Tagen ab" });
    expect(nachweisStatus("2026-10-20", heute).label).toBe("Läuft in 1 Tag ab");
  });

  it("gilt der Ablauftag selbst noch, die Warnfrist endet bei 30 Tagen", () => {
    expect(nachweisStatus(heute, heute)).toEqual({ art: "laeuft_ab", label: "Läuft heute ab" });
    expect(nachweisStatus("2026-11-18", heute).art).toBe("laeuft_ab");
    expect(nachweisStatus("2026-11-19", heute).art).toBe("gueltig");
  });
});

describe("zerlegeListenFehler", () => {
  it("trennt Titel und Punkte der Versand-Meldung", () => {
    expect(
      zerlegeListenFehler("Rechnung kann nicht versendet werden:\n- Position 1: Steuergrund fehlt\n- Beim Kunden fehlt die USt-IdNr."),
    ).toEqual({
      titel: "Rechnung kann nicht versendet werden",
      punkte: ["Position 1: Steuergrund fehlt", "Beim Kunden fehlt die USt-IdNr."],
    });
  });

  it("lässt einzeilige Meldungen unberührt", () => {
    expect(zerlegeListenFehler("Reverse Charge (§ 13b UStG) nicht möglich: Grund")).toBeNull();
    expect(zerlegeListenFehler("")).toBeNull();
    expect(zerlegeListenFehler(null)).toBeNull();
  });

  it("verwirft eine Aufzählung ohne Inhalt", () => {
    expect(zerlegeListenFehler("Titel:\n- ")).toBeNull();
  });
});

describe("istErloeskontoFehler", () => {
  it("erkennt die DATEV-Meldung", () => {
    expect(
      istErloeskontoFehler(
        "Für Steuerkategorie AE ist kein Erlöskonto hinterlegt – bitte unter Firmendaten ➝ Buchhaltung eintragen (Schlüssel AE:0.00)",
      ),
    ).toBe(true);
    expect(istErloeskontoFehler("Zeitüberschreitung")).toBe(false);
  });
});
