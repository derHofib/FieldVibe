// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { FormField } from "../../types";
import { FormFieldRenderer } from "./FormFieldRenderer";

afterEach(cleanup);

const zahlFeld = (validation: Record<string, unknown>): FormField => ({
  id: "f1",
  key: "druck",
  feld_typ: "zahl",
  label: { de: "Druck" },
  hilfetext: null,
  pflichtfeld: false,
  validation,
  default_value: null,
  optionen: {},
  group_key: null,
  datenquelle: null,
  reihenfolge: 0,
});

function zeige(validation: Record<string, unknown>, value: unknown) {
  render(<FormFieldRenderer field={zahlFeld(validation)} value={value} onChange={() => {}} readOnly={false} required={false} />);
}

describe("FormFieldRenderer Grenzwert-Hinweis", () => {
  it("zeigt bei Wert über warn_max einen nicht blockierenden Hinweis", () => {
    zeige({ warn_max: 50 }, "60");
    expect(screen.getByRole("status")).toHaveTextContent("Über dem Grenzwert 50");
  });

  it("zeigt bei Wert unter warn_min einen Hinweis", () => {
    zeige({ warn_min: 2 }, "1");
    expect(screen.getByRole("status")).toHaveTextContent("Unter dem Grenzwert 2");
  });

  it("zeigt nichts innerhalb der Grenzen oder bei leerem Wert", () => {
    zeige({ warn_max: 50 }, "50");
    expect(screen.queryByRole("status")).toBeNull();
    cleanup();
    zeige({ warn_max: 50 }, "");
    expect(screen.queryByRole("status")).toBeNull();
  });
});
