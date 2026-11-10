import { describe, expect, it } from "vitest";

import { firmendatenMitKonten, kontenAusFirmendaten } from "./erloeskonten";
import {
  datevAusFirmendaten,
  datevFehler,
  firmendatenMitDatev,
  istDatevEinstellungenFehler,
  istDatevStammdatenFehler,
  standardErloeskonto,
  validiereDebitorenkonto,
  type DatevEingabe,
} from "./datev";

const gueltig: DatevEingabe = {
  beraterNr: "29098",
  mandantNr: "55003",
  wjBeginnMonat: "1",
  kontenrahmen: "SKR03",
  sachkontenlaenge: "4",
};

describe("datevFehler", () => {
  it("akzeptiert gültige und leere Nummern", () => {
    expect(datevFehler(gueltig)).toEqual({});
    expect(datevFehler({ ...gueltig, beraterNr: "", mandantNr: "" })).toEqual({});
  });

  it("prüft Berater 1001-9999999 wie das Backend", () => {
    expect(datevFehler({ ...gueltig, beraterNr: "1000" }).beraterNr).toBeDefined();
    expect(datevFehler({ ...gueltig, beraterNr: "1001" }).beraterNr).toBeUndefined();
    expect(datevFehler({ ...gueltig, beraterNr: "9999999" }).beraterNr).toBeUndefined();
    expect(datevFehler({ ...gueltig, beraterNr: "10000000" }).beraterNr).toBeDefined();
    expect(datevFehler({ ...gueltig, beraterNr: "12a4" }).beraterNr).toBeDefined();
  });

  it("prüft Mandant 1-99999", () => {
    expect(datevFehler({ ...gueltig, mandantNr: "0" }).mandantNr).toBeDefined();
    expect(datevFehler({ ...gueltig, mandantNr: "99999" }).mandantNr).toBeUndefined();
    expect(datevFehler({ ...gueltig, mandantNr: "100000" }).mandantNr).toBeDefined();
  });

  it("prüft Sachkontenlänge 4-8 und verlangt sie", () => {
    expect(datevFehler({ ...gueltig, sachkontenlaenge: "3" }).sachkontenlaenge).toBeDefined();
    expect(datevFehler({ ...gueltig, sachkontenlaenge: "8" }).sachkontenlaenge).toBeUndefined();
    expect(datevFehler({ ...gueltig, sachkontenlaenge: "9" }).sachkontenlaenge).toBeDefined();
    expect(datevFehler({ ...gueltig, sachkontenlaenge: "" }).sachkontenlaenge).toBeDefined();
  });
});

describe("datevAusFirmendaten / firmendatenMitDatev", () => {
  it("liefert Defaults ohne gespeicherte Werte", () => {
    expect(datevAusFirmendaten({})).toEqual({
      beraterNr: "",
      mandantNr: "",
      wjBeginnMonat: "1",
      kontenrahmen: "SKR03",
      sachkontenlaenge: "4",
    });
  });

  it("schreibt Zahlen als Zahlen und lässt leere Nummern weg", () => {
    const fd = firmendatenMitDatev({ name: "Muster" } as never, gueltig);
    expect(fd.buchhaltung).toEqual({
      berater_nr: 29098,
      mandant_nr: 55003,
      wirtschaftsjahr_beginn_monat: 1,
      kontenrahmen: "SKR03",
      sachkontenlaenge: 4,
    });
    const ohne = firmendatenMitDatev(fd, { ...gueltig, beraterNr: "", mandantNr: " " });
    expect(ohne.buchhaltung).not.toHaveProperty("berater_nr");
    expect(ohne.buchhaltung).not.toHaveProperty("mandant_nr");
  });

  it("erhält Erlöskonten und übrige Firmendaten – und umgekehrt", () => {
    const start = {
      ust_idnr: "DE123456789",
      buchhaltung: { erloeskonten: { "Z:0.00": { konto: "8101", bu: "11" } } },
    } as never;
    const mitDatev = firmendatenMitDatev(start, gueltig);
    expect(mitDatev.ust_idnr).toBe("DE123456789");
    expect(mitDatev.buchhaltung?.erloeskonten).toEqual({ "Z:0.00": { konto: "8101", bu: "11" } });

    const konten = kontenAusFirmendaten(mitDatev);
    const zurueck = firmendatenMitKonten(mitDatev, konten);
    expect(zurueck.buchhaltung?.berater_nr).toBe(29098);
    expect(zurueck.buchhaltung?.erloeskonten).toEqual({ "Z:0.00": { konto: "8101", bu: "11" } });
  });
});

describe("validiereDebitorenkonto", () => {
  it("lässt leer und 5 bis 9 Ziffern zu", () => {
    expect(validiereDebitorenkonto("")).toBeNull();
    expect(validiereDebitorenkonto(" 10000 ")).toBeNull();
    expect(validiereDebitorenkonto("123456789")).toBeNull();
  });

  it("lehnt zu kurze, zu lange und nicht numerische Konten ab", () => {
    expect(validiereDebitorenkonto("1000")).not.toBeNull();
    expect(validiereDebitorenkonto("1234567890")).not.toBeNull();
    expect(validiereDebitorenkonto("1000a")).not.toBeNull();
  });
});

describe("istDatevStammdatenFehler", () => {
  it("erkennt die Backend-Meldung", () => {
    expect(
      istDatevStammdatenFehler(
        "DATEV-Stammdaten unvollständig: Beraternummer und Mandantennummer nicht hinterlegt – bitte unter Einstellungen",
      ),
    ).toBe(true);
    expect(istDatevStammdatenFehler("Für Steuerkategorie Z ist kein Erlöskonto hinterlegt")).toBe(false);
    expect(istDatevStammdatenFehler(null)).toBe(false);
  });
});

describe("istDatevEinstellungenFehler", () => {
  it("erkennt auch Kontenlängen-Fehler, aber nicht fehlende Erlöskonten", () => {
    expect(istDatevEinstellungenFehler("Erlöskonto S:19.00: Konto 8400 hat 4 Stellen – bitte unter Einstellungen ➝ Buchhaltung (DATEV) angleichen")).toBe(true);
    expect(istDatevEinstellungenFehler("Für Steuerkategorie Z ist kein Erlöskonto hinterlegt – bitte unter Firmendaten ➝ Buchhaltung eintragen")).toBe(false);
  });
});

describe("standardErloeskonto", () => {
  it("liefert den Standard je Kontenrahmen", () => {
    expect(standardErloeskonto("S:19.00", "SKR03")).toBe("8400");
    expect(standardErloeskonto("S:19.00", "SKR04")).toBe("4400");
    expect(standardErloeskonto("Z:0.00", "SKR03")).toBeNull();
  });
});
