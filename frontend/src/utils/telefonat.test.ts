import { describe, expect, it } from "vitest";

import type { Ansprechpartner } from "../types";
import {
  ANDERE_PERSON,
  arbeitszeitSichtbar,
  baueTelefonatCreate,
  baueTelefonatUpdate,
  kontaktAuswahlWert,
  nummerErkennbar,
  dauerSichtbar,
  formatDauer,
  leeresFormular,
  naechsterWerktag9,
  sortiereAnsprechpartner,
  telefonHref,
  validiereTelefonat,
} from "./telefonat";

function formular(teil: Partial<ReturnType<typeof leeresFormular>> = {}) {
  return { ...leeresFormular({ partner: { name: "Marian Reichel" } }), notiz: "Absage", dauerMinuten: "6", ...teil };
}

describe("naechsterWerktag9", () => {
  it("nimmt morgen um 9:00, wenn morgen ein Werktag ist", () => {
    const d = naechsterWerktag9(new Date(2026, 10, 18, 16, 20)); // Mi 18.11.2026
    expect([d.getDate(), d.getHours(), d.getMinutes()]).toEqual([19, 9, 0]);
  });
  it("überspringt das Wochenende", () => {
    const d = naechsterWerktag9(new Date(2026, 10, 20, 16, 20)); // Fr 20.11.2026
    expect([d.getDate(), d.getDay()]).toEqual([23, 1]);
  });
});

describe("Formularregeln", () => {
  it("Dauer nur bei erreicht, Arbeitszeit nur mit Vorgang und erreicht", () => {
    expect(dauerSichtbar("erreicht")).toBe(true);
    expect(dauerSichtbar("mailbox")).toBe(false);
    expect(dauerSichtbar("nicht_erreicht")).toBe(false);
    expect(arbeitszeitSichtbar("v1", "erreicht")).toBe(true);
    expect(arbeitszeitSichtbar("", "erreicht")).toBe(false);
    expect(arbeitszeitSichtbar(undefined, "erreicht")).toBe(false);
    expect(arbeitszeitSichtbar("v1", "mailbox")).toBe(false);
  });

  it("Notiz ist bei erreicht Pflicht, bei Mailbox nicht", () => {
    expect(validiereTelefonat(formular({ notiz: "  " })).notiz).toBeTruthy();
    expect(validiereTelefonat(formular({ notiz: "" , ergebnis: "mailbox" })).notiz).toBeUndefined();
    expect(validiereTelefonat(formular()).notiz).toBeUndefined();
  });

  it("verlangt Partnername und bei aktivem Rückruf einen Zeitpunkt", () => {
    expect(validiereTelefonat(formular({ partnerName: "" })).partner).toBeTruthy();
    expect(validiereTelefonat(formular({ rueckrufAn: true, rueckrufAm: "" })).rueckruf).toBeTruthy();
    expect(validiereTelefonat(formular({ dauerMinuten: "5000" })).dauer).toBeTruthy();
  });
});

describe("baueTelefonatCreate", () => {
  it("setzt bei Vorgang nur vorgang_id (kunde_id kommt vom Server)", () => {
    const body = baueTelefonatCreate(formular(), { vorgangId: "v1", kundeId: "k1" });
    expect(body.vorgang_id).toBe("v1");
    expect(body.kunde_id).toBeUndefined();
    expect(body.dauer_sekunden).toBe(360);
  });

  it("nimmt am Kunden die gewählte Vorgang-Zuordnung, sonst kunde_id", () => {
    expect(baueTelefonatCreate(formular({ vorgangId: "v9" }), { kundeId: "k1" }).vorgang_id).toBe("v9");
    const ohne = baueTelefonatCreate(formular(), { kundeId: "k1" });
    expect(ohne.kunde_id).toBe("k1");
    expect(ohne.vorgang_id).toBeUndefined();
  });

  it("lässt bei Mailbox Dauer und Arbeitszeit weg, exakte Uhr-Sekunden gewinnen beim Gespräch", () => {
    const mailbox = baueTelefonatCreate(formular({ ergebnis: "mailbox", arbeitszeit: true }), { vorgangId: "v1" });
    expect(mailbox.dauer_sekunden).toBeUndefined();
    expect(mailbox.als_arbeitszeit_buchen).toBeUndefined();
    const uhr = baueTelefonatCreate(formular({ arbeitszeit: true }), { vorgangId: "v1" }, "u-1", 367);
    expect(uhr.dauer_sekunden).toBe(367);
    expect(uhr.als_arbeitszeit_buchen).toBe(true);
    expect(uhr.client_uuid).toBe("u-1");
  });

  it("bucht keine Arbeitszeit ohne Vorgang oder ohne Dauer", () => {
    expect(baueTelefonatCreate(formular({ arbeitszeit: true }), { kundeId: "k1" }).als_arbeitszeit_buchen).toBeUndefined();
    expect(baueTelefonatCreate(formular({ arbeitszeit: true, dauerMinuten: "" }), { vorgangId: "v1" }).als_arbeitszeit_buchen).toBeUndefined();
  });

  it("sendet ansprechpartner_id nur für echte Ansprechpartner", () => {
    expect(baueTelefonatCreate(formular({ partnerAuswahl: ANDERE_PERSON }), { kundeId: "k" }).ansprechpartner_id).toBeUndefined();
    expect(baueTelefonatCreate(formular({ partnerAuswahl: "a1" }), { kundeId: "k" }).ansprechpartner_id).toBe("a1");
  });
});

describe("Kontakt vor Ort als Gesprächspartner", () => {
  it("sendet vor_ort_kontakt_id statt ansprechpartner_id", () => {
    const body = baueTelefonatCreate(formular({ partnerAuswahl: kontaktAuswahlWert("c1") }), { kundeId: "k" });
    expect(body.vor_ort_kontakt_id).toBe("c1");
    expect(body.ansprechpartner_id).toBeUndefined();
  });

  it("setzt beim Ändern den jeweils anderen Verweis auf null", () => {
    const alt = { rueckruf_am: null, rueckruf_erledigt_am: null } as never;
    const kontakt = baueTelefonatUpdate(formular({ partnerAuswahl: kontaktAuswahlWert("c1") }), alt);
    expect([kontakt.vor_ort_kontakt_id, kontakt.ansprechpartner_id]).toEqual(["c1", null]);
    const person = baueTelefonatUpdate(formular({ partnerAuswahl: "a1" }), alt);
    expect([person.vor_ort_kontakt_id, person.ansprechpartner_id]).toEqual([null, "a1"]);
  });

  it("erkennt Rufnummern erst ab fünf Ziffern", () => {
    expect(nummerErkennbar("0176 22")).toBe(true);
    expect(nummerErkennbar("12-3")).toBe(false);
  });
});

describe("Hilfen", () => {
  it("rundet die Dauer auf volle Minuten auf", () => {
    expect(formatDauer(360)).toBe("6 Min");
    expect(formatDauer(361)).toBe("7 Min");
    expect(formatDauer(null)).toBeNull();
  });
  it("sortiert operative Ansprechpartner zuerst", () => {
    const a = (id: string, operativ: boolean) => ({ id, operativ }) as Ansprechpartner;
    expect(sortiereAnsprechpartner([a("1", false), a("2", true)]).map((x) => x.id)).toEqual(["2", "1"]);
  });
  it("baut tel:-Links ohne Leerzeichen und Trennzeichen", () => {
    expect(telefonHref("+49 (30) 9928-4417")).toBe("tel:+493099284417");
  });
});
