import { describe, expect, it } from "vitest";

import {
  erstelleSchwaerzConfig,
  schwaerzeHeaders,
  schwaerzeText,
  schwaerzeUrl,
  schwaerzeWert,
  STANDARD_CONFIG,
} from "../schwaerzen";

const JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.c2lnbmF0dXJl";

describe("schwaerzeHeaders", () => {
  it("entfernt Denylist-Header unabhaengig von der Gross-/Kleinschreibung", () => {
    const r = schwaerzeHeaders({
      Authorization: "Bearer abc",
      COOKIE: "sid=1",
      "Set-Cookie": "sid=1",
      "Proxy-Authorization": "x",
      "X-Api-Key": "k",
      "x-auth-token": "t",
      "X-CSRF-Token": "c",
      "content-type": "application/json",
    });
    expect(r.Authorization).toBe("[entfernt]");
    expect(r.COOKIE).toBe("[entfernt]");
    expect(r["Set-Cookie"]).toBe("[entfernt]");
    expect(r["Proxy-Authorization"]).toBe("[entfernt]");
    expect(r["X-Api-Key"]).toBe("[entfernt]");
    expect(r["x-auth-token"]).toBe("[entfernt]");
    expect(r["X-CSRF-Token"]).toBe("[entfernt]");
    expect(r["content-type"]).toBe("application/json");
  });

  it("maskiert JWTs auch in unkritischen Headern", () => {
    expect(schwaerzeHeaders({ "x-foo": JWT })["x-foo"]).toBe("[entfernt]");
  });
});

describe("schwaerzeWert", () => {
  it("schwaerzt verschachtelte Schluessel case-insensitive per Teilstring", () => {
    const r = schwaerzeWert({
      user: { Passwort: "geheim", name: "Anna", meta: { apiKey: "k", mein_Token_wert: "t" } },
    });
    expect(r).toEqual({ user: { Passwort: "[entfernt]", name: "Anna", meta: { apiKey: "[entfernt]", mein_Token_wert: "[entfernt]" } } });
  });

  it("geht durch Arrays", () => {
    const r = schwaerzeWert([{ iban: "x" }, { ok: 1 }, [{ secret: "s" }]]);
    expect(r).toEqual([{ iban: "[entfernt]" }, { ok: 1 }, [{ secret: "[entfernt]" }]]);
  });

  it("verkraftet Zyklen", () => {
    const a: Record<string, unknown> = { x: 1 };
    a.self = a;
    expect(schwaerzeWert(a)).toEqual({ x: 1, self: "[zirkulaer]" });
  });

  it("laesst Nicht-Treffer unveraendert", () => {
    const eingabe = { id: 5, titel: "Heizung warten", aktiv: true, n: null, liste: [1, 2] };
    expect(schwaerzeWert(eingabe)).toEqual(eingabe);
  });

  it("veraendert das Original nicht", () => {
    const eingabe = { password: "x" };
    schwaerzeWert(eingabe);
    expect(eingabe.password).toBe("x");
  });
});

describe("schwaerzeText", () => {
  it("parst JSON-Strings, schwaerzt und serialisiert wieder", () => {
    const r = schwaerzeText(JSON.stringify({ a: { password: "x" }, ok: "y" }));
    expect(JSON.parse(r)).toEqual({ a: { password: "[entfernt]" }, ok: "y" });
  });

  it("schwaerzt JSON-Arrays", () => {
    expect(JSON.parse(schwaerzeText('[{"token":"t"}]'))).toEqual([{ token: "[entfernt]" }]);
  });

  it("maskiert JWT in Nicht-JSON-Text", () => {
    const r = schwaerzeText(`Fehler bei Anfrage mit ${JWT} abgelehnt`);
    expect(r).toBe("Fehler bei Anfrage mit [entfernt] abgelehnt");
  });

  it("schwaerzt key=value in Nicht-JSON-Text", () => {
    expect(schwaerzeText("user=anna&password=geheim&x=1")).toBe("user=anna&password=[entfernt]&x=1");
    expect(schwaerzeText("Authorization: Bearer abcdefghij12345")).toContain("[entfernt]");
    expect(schwaerzeText("Authorization: Bearer abcdefghij12345")).not.toContain("abcdefghij12345");
  });

  it("laesst harmlosen Text unveraendert", () => {
    const t = "Vorgang 42 wurde am 2026-10-04 gespeichert";
    expect(schwaerzeText(t)).toBe(t);
  });

  it("kaputtes JSON faellt auf den Regex-Pfad zurueck", () => {
    expect(schwaerzeText('{"password": "geheim", ')).not.toContain("geheim");
  });
});

describe("schwaerzeUrl", () => {
  it("ersetzt Denylist-Query-Parameter, laesst andere stehen", () => {
    const r = schwaerzeUrl("https://x.de/api/a?token=abc&seite=2&API_KEY=k");
    expect(r).toBe("https://x.de/api/a?token=[entfernt]&seite=2&API_KEY=[entfernt]");
  });

  it("verwirft das Fragment", () => {
    expect(schwaerzeUrl("https://x.de/a#access_token=zzz")).toBe("https://x.de/a");
  });

  it("URL ohne Query bleibt gleich; Telefon-Regex trifft keine Pfad-IDs", () => {
    const u = "https://x.de/api/vorgaenge/0123456789";
    expect(schwaerzeUrl(u)).toBe(u);
  });

  it("maskiert E-Mail in der Query", () => {
    expect(schwaerzeUrl("/a?q=anna@example.com")).toBe("/a?q=[email]");
  });
});

describe("Muster-Maskierung", () => {
  const text = "Mail anna@example.com, IBAN DE89 3704 0044 0532 0130 00, Tel +49 170 1234567.";

  it("maskiert E-Mail, IBAN, Telefon standardmaessig", () => {
    const r = schwaerzeText(text);
    expect(r).toBe("Mail [email], IBAN [iban], Tel [telefon].");
  });

  it("IBAN ohne Leerzeichen", () => {
    expect(schwaerzeText("DE89370400440532013000")).toBe("[iban]");
  });

  it("lokale Telefonnummer mit 0", () => {
    expect(schwaerzeText("ruf 0170/1234567 an")).toBe("ruf [telefon] an");
  });

  it("laesst ISO-Datum und Zeitstempel in Ruhe", () => {
    expect(schwaerzeText("2026-10-04T12:00:00 und 1759579200000")).toBe("2026-10-04T12:00:00 und 1759579200000");
  });

  it.each([
    [{ maskiereEmail: false }, "[email]", "anna@example.com"],
    // Telefon mit aus: die IBAN-Ziffernbloecke wuerden sonst als Telefonnummer maskiert.
    [{ maskiereIban: false, maskiereTelefon: false }, "[iban]", "DE89 3704 0044 0532 0130 00"],
    [{ maskiereTelefon: false }, "[telefon]", "+49 170 1234567"],
  ] as const)("%j laesst das Muster stehen", (opt, marker, roh) => {
    const cfg = erstelleSchwaerzConfig(opt);
    const r = schwaerzeText(text, cfg);
    expect(r).toContain(roh);
    expect(r).not.toContain(marker);
  });

  it("JWT wird auch bei abgeschalteten Optionen maskiert", () => {
    const cfg = erstelleSchwaerzConfig({ maskiereEmail: false, maskiereIban: false, maskiereTelefon: false });
    expect(schwaerzeText(JWT, cfg)).toBe("[entfernt]");
  });
});

describe("Zusatz-Denylist", () => {
  it("erweitert die Standardliste", () => {
    const cfg = erstelleSchwaerzConfig({ zusatzDenylist: ["Steuernummer"] });
    expect(schwaerzeWert({ steuernummer_kunde: "1", x: 2 }, cfg)).toEqual({ steuernummer_kunde: "[entfernt]", x: 2 });
    expect(schwaerzeText("steuernummer=123", cfg)).toBe("steuernummer=[entfernt]");
    expect(schwaerzeUrl("/a?Steuernummer=1", cfg)).toBe("/a?Steuernummer=[entfernt]");
    // Standardkonfiguration kennt den Begriff nicht.
    expect(schwaerzeWert({ steuernummer: "1" }, STANDARD_CONFIG)).toEqual({ steuernummer: "1" });
  });
});
