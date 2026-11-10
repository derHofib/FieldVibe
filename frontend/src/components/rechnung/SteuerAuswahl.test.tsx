// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { datumZuIso } from "../../utils/format";
import type { SteuerEingabe } from "../../utils/steuer";
import { SteuerAuswahl } from "./SteuerAuswahl";

const kundeOk = { id: "k1", ust_idnr: "DE123456789", ust_13b_nachweis_bis: "2099-12-31" };

function Huelle({
  start,
  kunde,
  leistungsdatum,
  onWert,
}: {
  start: SteuerEingabe;
  kunde?: typeof kundeOk | null;
  leistungsdatum?: string | null;
  onWert?: (w: SteuerEingabe) => void;
}) {
  const [wert, setWert] = useState(start);
  return (
    <MemoryRouter>
      <SteuerAuswahl
        wert={wert}
        onChange={(w) => {
          setWert(w);
          onWert?.(w);
        }}
        kunde={kunde}
        leistungsdatum={leistungsdatum}
      />
    </MemoryRouter>
  );
}

afterEach(cleanup);

describe("SteuerAuswahl", () => {
  it("zeigt die gewählte Option und bietet alle fünf im Sheet an", () => {
    render(<Huelle start={{ option: "s19", text: "" }} />);
    fireEvent.click(screen.getByRole("button", { name: /Steuer: 19 %/ }));
    const dialog = screen.getByRole("dialog", { name: "Steuer" });
    for (const label of [
      "19 %",
      "7 %",
      "0 % – Photovoltaik (§ 12 Abs. 3 UStG)",
      "Reverse Charge (§ 13b UStG)",
      "Steuerfrei (Begründung angeben)",
    ]) {
      expect(dialog).toHaveTextContent(label);
    }
  });

  it("übernimmt eine Auswahl und schließt das Sheet", () => {
    const onWert = vi.fn();
    render(<Huelle start={{ option: "s19", text: "" }} onWert={onWert} />);
    fireEvent.click(screen.getByRole("button", { name: /Steuer: 19 %/ }));
    fireEvent.click(screen.getByRole("button", { name: "7 %" }));
    expect(onWert).toHaveBeenCalledWith({ option: "s7", text: "" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("verlangt bei Steuerfrei eine Begründung mit Zeichenzähler", () => {
    render(<Huelle start={{ option: "e_befreit", text: "" }} />);
    const feld = screen.getByLabelText("Begründung der Steuerbefreiung");
    expect(screen.getByText("0/200")).toBeInTheDocument();
    fireEvent.change(feld, { target: { value: "ab" } });
    fireEvent.blur(feld);
    expect(screen.getByText("2/200")).toBeInTheDocument();
    expect(screen.getByText(/mindestens 3 Zeichen/)).toBeInTheDocument();
    fireEvent.change(feld, { target: { value: "Ausfuhr" } });
    expect(screen.queryByText(/mindestens 3 Zeichen/)).toBeNull();
  });

  it("zeigt bei 0 % Photovoltaik den Hinweis ohne Prüfung", () => {
    render(<Huelle start={{ option: "z_pv", text: "" }} />);
    expect(screen.getByText(/Nullsteuersatz nur bei Lieferung und Installation von PV-Anlagen/)).toBeInTheDocument();
  });

  it("warnt bei Reverse Charge vor dem Speichern, wenn der Nachweis fehlt, und verlinkt das Kundenprofil", () => {
    render(<Huelle start={{ option: "ae_13b", text: "" }} kunde={{ ...kundeOk, ust_13b_nachweis_bis: null as never }} />);
    expect(screen.getByText(/Ablaufdatum der Bescheinigung USt 1 TG/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Kundenprofil" })).toHaveAttribute("href", "/kunden/k1");
  });

  it("warnt bei abgelaufenem Nachweis relativ zum Leistungsdatum", () => {
    render(
      <Huelle
        start={{ option: "ae_13b", text: "" }}
        kunde={{ ...kundeOk, ust_13b_nachweis_bis: "2026-11-30" }}
        leistungsdatum="2026-12-01"
      />,
    );
    expect(screen.getByText(/am 30.11.2026 abgelaufen \(Leistungsdatum 01.12.2026\)/)).toBeInTheDocument();
  });

  it("bleibt bei gültigem Nachweis (Ablauf = Leistungsdatum) ohne Warnung", () => {
    render(
      <Huelle
        start={{ option: "ae_13b", text: "" }}
        kunde={{ ...kundeOk, ust_13b_nachweis_bis: "2026-12-01" }}
        leistungsdatum="2026-12-01"
      />,
    );
    expect(screen.queryByRole("link", { name: "Kundenprofil" })).toBeNull();
  });

  it("warnt ohne Leistungsdatum gegen den heutigen Lokaltag", () => {
    const gestern = new Date();
    gestern.setDate(gestern.getDate() - 1);
    render(
      <Huelle start={{ option: "ae_13b", text: "" }} kunde={{ ...kundeOk, ust_13b_nachweis_bis: datumZuIso(gestern) }} />,
    );
    expect(screen.getByText(/abgelaufen \(heute,/)).toBeInTheDocument();
  });

  it("warnt nicht, solange der Kunde noch lädt", () => {
    render(<Huelle start={{ option: "ae_13b", text: "" }} kunde={undefined} />);
    expect(screen.queryByRole("link", { name: "Kundenprofil" })).toBeNull();
  });
});
