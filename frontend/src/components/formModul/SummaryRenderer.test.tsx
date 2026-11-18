// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { FormField } from "../../types";
import { grenzwertHinweis } from "../../utils/formular";
import { SummaryRenderer } from "./SummaryRenderer";

afterEach(cleanup);

const feld = (key: string, feld_typ: FormField["feld_typ"], validation: Record<string, unknown> = {}): FormField => ({
  id: key,
  key,
  feld_typ,
  label: { de: key },
  hilfetext: null,
  pflichtfeld: false,
  validation,
  default_value: null,
  optionen: {},
  group_key: null,
  datenquelle: null,
  reihenfolge: 0,
});

describe("grenzwertHinweis", () => {
  it("markiert Werte über warn_max und unter warn_min", () => {
    expect(grenzwertHinweis({ warn_max: 50 }, 60)).toBe("über 50");
    expect(grenzwertHinweis({ warn_min: 2 }, 1)).toBe("unter 2");
    expect(grenzwertHinweis({ warn_max: 50 }, 50)).toBeNull();
    expect(grenzwertHinweis({}, 99)).toBeNull();
    expect(grenzwertHinweis({ warn_max: 50 }, "")).toBeNull();
  });
});

describe("SummaryRenderer", () => {
  it("zeigt Zahl über Grenzwert rot mit 'über X', Ja/Nein mit Text", () => {
    render(
      <SummaryRenderer
        fields={[feld("co", "zahl", { warn_max: 50 }), feld("o2", "zahl", { warn_max: 50 }), feld("dicht", "ja_nein")]}
        groups={[]}
        rules={[]}
        elements={[]}
        values={{ co: 72, o2: 4, dicht: false }}
      />,
    );
    const hinweis = screen.getByText("über 50");
    expect(hinweis.parentElement).toHaveClass("text-st-fehlt");
    expect(screen.getAllByText("über 50")).toHaveLength(1);
    expect(screen.getByText("Nein")).toBeInTheDocument();
  });

  it("zeigt Unterschrift als Bild", () => {
    render(
      <SummaryRenderer
        fields={[feld("sig", "unterschrift")]}
        groups={[]}
        rules={[]}
        elements={[]}
        values={{ sig: { key: "k", url: "https://x/y.png", content_type: "image/png" } }}
      />,
    );
    expect(screen.getByAltText("Unterschrift: sig")).toHaveAttribute("src", "https://x/y.png");
  });
});
