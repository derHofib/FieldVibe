import { describe, expect, it } from "vitest";

import {
  formatSaldo,
  parseStunden,
  saldoBis,
  saldoTageNachDatum,
  saldoTon,
  sollWochensumme,
  stundenFuerApi,
} from "./arbeitszeit";

describe("formatSaldo", () => {
  it("zeigt Vorzeichen und H:MM", () => {
    expect(formatSaldo("1.50")).toBe("+1:30");
    expect(formatSaldo("-0.75")).toBe("−0:45");
    expect(formatSaldo(12.25)).toBe("+12:15");
  });
  it("zeigt Null ohne Vorzeichen, auch bei Rundung auf 0 Minuten", () => {
    expect(formatSaldo("0.00")).toBe("0:00");
    expect(formatSaldo("-0.004")).toBe("0:00");
  });
});

describe("saldoTon", () => {
  it("unterscheidet plus, minus und null", () => {
    expect(saldoTon("0.50")).toBe("plus");
    expect(saldoTon("-2.00")).toBe("minus");
    expect(saldoTon("0.00")).toBe("null");
  });
});

describe("saldoBis", () => {
  it("klemmt das Monatsende auf heute", () => {
    expect(saldoBis("2026-10-01", "2026-10-31", "2026-10-05")).toBe("2026-10-05");
  });
  it("behält das Monatsende bei vergangenen Monaten", () => {
    expect(saldoBis("2026-09-01", "2026-09-30", "2026-10-05")).toBe("2026-09-30");
  });
  it("liefert null, wenn der Monat in der Zukunft liegt", () => {
    expect(saldoBis("2026-11-01", "2026-11-30", "2026-10-05")).toBeNull();
  });
  it("nimmt den ersten Monatstag als heute mit", () => {
    expect(saldoBis("2026-10-01", "2026-10-31", "2026-10-01")).toBe("2026-10-01");
  });
});

describe("sollWochensumme", () => {
  it("summiert alle sieben Tage, Komma und Leerfelder erlaubt", () => {
    expect(
      sollWochensumme({
        stunden_mo: "8",
        stunden_di: "8,5",
        stunden_mi: "8",
        stunden_do: "8",
        stunden_fr: "6.5",
        stunden_sa: "",
        stunden_so: "0",
      }),
    ).toBe(39);
  });
});

describe("Stundenwerte", () => {
  it("parst Komma und ungültige Eingaben", () => {
    expect(parseStunden("7,5")).toBe(7.5);
    expect(parseStunden("abc")).toBe(0);
    expect(stundenFuerApi("7,5")).toBe("7.50");
    expect(stundenFuerApi("")).toBe("0.00");
  });
});

describe("saldoTageNachDatum", () => {
  it("indiziert die Tage nach Datum", () => {
    const tag = {
      datum: "2026-10-03",
      soll: "0.00",
      ist: "0.00",
      saldo: "0.00",
      feiertag: true,
      abwesenheit: null,
    };
    expect(saldoTageNachDatum([tag]).get("2026-10-03")).toBe(tag);
    expect(saldoTageNachDatum([tag]).get("2026-10-04")).toBeUndefined();
  });
});
