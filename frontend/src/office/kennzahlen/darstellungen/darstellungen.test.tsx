// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { KennzahlDaten, KennzahlZeile } from "../../../types/kennzahlen";
import { Balken } from "./Balken";
import { Linie } from "./Linie";
import { Ring } from "./Ring";
import { Saeulen } from "./Saeulen";
import { Tabelle } from "./Tabelle";
import { Zahl } from "./Zahl";
import { ZahlVerlauf } from "./ZahlVerlauf";
import { achsenMaximum, alterFarben, type DarstellungProps } from "./gemeinsam";

afterEach(cleanup);

function zeilen(...paare: [string, number | null, (number | null)?][]): KennzahlZeile[] {
  return paare.map(([label, wert, vorperiode]) => ({ schluessel: label.toLowerCase(), label, wert, vorperiode: vorperiode ?? null }));
}

function props(teil: Partial<KennzahlDaten> = {}, zusatz: Partial<DarstellungProps> = {}): DarstellungProps {
  return {
    daten: {
      kennzahl: "vorgaenge.erstellt",
      einheit: "anzahl",
      art: "zeitraum",
      gruppierung: "techniker",
      von: "2026-11-01",
      bis: "2026-11-30",
      gesamt: 15,
      vorperiode_gesamt: 12,
      zeilen: zeilen(["Jonas", 8, 6], ["Lena", 5, 4], ["Tim", 2, 2]),
      abgeschnitten: false,
      datumsbezug: null,
      ...teil,
    },
    groesse: "l",
    vergleich: true,
    statusFarben: false,
    summierbar: true,
    titel: "Erstellte Vorgänge",
    vorLabel: "Oktober",
    ...zusatz,
  };
}

const LEER = props({ zeilen: [], gesamt: null, vorperiode_gesamt: null });
const OHNE_WERTE = props({ zeilen: zeilen(["Jonas", null], ["Lena", null]), gesamt: null, vorperiode_gesamt: null });

const DARSTELLUNGEN = {
  Saeulen,
  Linie,
  Balken,
  Ring,
  Tabelle,
  ZahlVerlauf,
};

describe("Zahl", () => {
  it("zeigt Wert und Abweichung als Text mit Pfeil", () => {
    render(<Zahl {...props()} />);
    expect(screen.getByText("15")).toBeInTheDocument();
    expect(screen.getByText("▲ 3 ggü. Oktober")).toBeInTheDocument();
  });

  it("färbt nur bei klarer Richtung: Durchlaufzeit sinkt = gut", () => {
    render(
      <Zahl
        {...props({ kennzahl: "vorgaenge.durchlaufzeit", einheit: "tage", gesamt: 3.4, vorperiode_gesamt: 4.2 })}
      />,
    );
    expect(screen.getByText("▼ 0,8 Tage ggü. Oktober")).toHaveClass("text-st-erledigt");
  });

  it("neutrale Kennzahl bleibt ungefärbt, ohne Vorperiode entfällt die Zeile", () => {
    const { rerender } = render(<Zahl {...props()} />);
    expect(screen.getByText("▲ 3 ggü. Oktober")).toHaveClass("text-label2");
    rerender(<Zahl {...props({ vorperiode_gesamt: null })} />);
    expect(screen.queryByText(/ggü\./)).not.toBeInTheDocument();
  });

  it("stürzt bei fehlendem Wert nicht ab", () => {
    render(<Zahl {...props({ gesamt: null, vorperiode_gesamt: null })} />);
    expect(screen.getByText("–")).toBeInTheDocument();
  });
});

describe.each(Object.entries(DARSTELLUNGEN))("%s", (_name, Komponente) => {
  it("rendert gefüllte Daten", () => {
    const { container } = render(<Komponente {...props()} />);
    expect(container.firstChild).not.toBeNull();
  });

  it("rendert leere Daten ohne Absturz", () => {
    const { container } = render(<Komponente {...LEER} />);
    expect(container).toBeInTheDocument();
  });

  it("rendert Zeilen ohne Wert ohne Absturz", () => {
    const { container } = render(<Komponente {...OHNE_WERTE} />);
    expect(container).toBeInTheDocument();
  });
});

describe("Diagramm-Beschriftung", () => {
  it.each([
    ["Säulendiagramm", Saeulen],
    ["Liniendiagramm", Linie],
    ["Balkendiagramm", Balken],
    ["Ringdiagramm", Ring],
  ])("%s trägt role=img mit Kurzbeschreibung", (name, Komponente) => {
    render(<Komponente {...props()} />);
    expect(screen.getByRole("img", { name: new RegExp(`^${name}: Erstellte Vorgänge`) })).toBeInTheDocument();
  });
});

describe("Balken", () => {
  const viele = props({
    zeilen: zeilen(...Array.from({ length: 11 }, (_, i): [string, number] => [`Kunde ${i + 1}`, 20 - i])),
  });

  it("zeigt Top 8 und fasst den Rest bei summierbaren Kennzahlen zu Weitere zusammen", () => {
    render(<Balken {...viele} />);
    expect(screen.getByText("Kunde 8")).toBeInTheDocument();
    expect(screen.queryByText("Kunde 9")).not.toBeInTheDocument();
    expect(screen.getByText("Weitere (3)")).toBeInTheDocument();
    // 12 + 11 + 10
    expect(screen.getByText("33")).toBeInTheDocument();
  });

  it("lässt den Rest bei nicht summierbaren Kennzahlen weg", () => {
    render(<Balken {...viele} summierbar={false} />);
    expect(screen.queryByText(/Weitere/)).not.toBeInTheDocument();
  });

  it("sortiert Ranglisten absteigend", () => {
    render(<Balken {...props({ zeilen: zeilen(["Klein", 1], ["Groß", 9]) })} />);
    const text = screen.getByRole("img").textContent ?? "";
    expect(text.indexOf("Groß")).toBeLessThan(text.indexOf("Klein"));
  });
});

describe("Ring", () => {
  it("zeigt Gesamtwert in der Mitte und Legende", () => {
    render(<Ring {...props()} />);
    expect(screen.getAllByText("15").length).toBeGreaterThan(0);
    expect(screen.getByText("Jonas")).toBeInTheDocument();
  });

  it("begrenzt auf sechs Teile mit grauem Weitere", () => {
    const sieben = props({ zeilen: zeilen(...Array.from({ length: 8 }, (_, i): [string, number] => [`Typ ${i + 1}`, 10 - i])) });
    render(<Ring {...sieben} />);
    expect(screen.getByText("Weitere (3)")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(6);
  });
});

describe("Tabelle", () => {
  it("zeigt mit Vorperiode zwei zusätzliche Spalten und die Summenzeile", () => {
    render(<Tabelle {...props()} />);
    expect(screen.getByRole("columnheader", { name: "Oktober" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Abweichung" })).toBeInTheDocument();
    expect(screen.getByText("Gesamt")).toBeInTheDocument();
  });

  it("benennt die Spalten nach Aufteilung und Zeitraum", () => {
    render(<Tabelle {...props({}, { gruppierungLabel: "Kunde", zeitraumLabel: "2026" })} />);
    expect(screen.getByRole("columnheader", { name: "Kunde" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "2026" })).toBeInTheDocument();
  });

  it("zeigt ohne Vergleich nur Gruppe und Wert", () => {
    render(<Tabelle {...props({}, { vergleich: false })} />);
    expect(screen.queryByRole("columnheader", { name: "Abweichung" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("columnheader")).toHaveLength(2);
  });
});

describe("Legende", () => {
  it("Säulen und Linie nennen den Zeitraum statt 'Aktuell'", () => {
    for (const Komponente of [Saeulen, Linie]) {
      const { unmount } = render(<Komponente {...props({}, { zeitraumLabel: "November 2026" })} />);
      expect(screen.getByText("November 2026")).toBeInTheDocument();
      expect(screen.queryByText("Aktuell")).not.toBeInTheDocument();
      unmount();
    }
  });
});

describe("Hilfsfunktionen", () => {
  it("achsenMaximum liefert runde Hilfslinien", () => {
    expect(achsenMaximum(11, "anzahl")).toBe(12);
    expect(achsenMaximum(0, "anzahl")).toBe(3);
    expect(achsenMaximum(48320, "eur")).toBe(60000);
  });

  it("alterFarben: nicht fällig in Akzent, danach Orange, ab dem dritten überfälligen Rot", () => {
    const farben = alterFarben(
      zeilen(["Nicht fällig", 1], ["1–30 Tage", 1], ["31–60 Tage", 1], ["61–90 Tage", 1], ["über 90 Tage", 1]),
    );
    expect(farben).toEqual(["var(--tint)", "var(--st-arbeit-dot)", "var(--st-arbeit-dot)", "var(--st-fehlt-dot)", "var(--st-fehlt-dot)"]);
  });
});
