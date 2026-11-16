// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { VorgangStatusPille } from "./VorgangStatusPille";

afterEach(cleanup);

describe("VorgangStatusPille", () => {
  it("nutzt für bekannte Status die Status-Tokens", () => {
    render(<VorgangStatusPille status="geplant" />);
    expect(screen.getByText("Geplant").className).toContain("text-st-geplant");
  });

  it("zeigt die Anzahl vor dem Label", () => {
    render(<VorgangStatusPille status="in_arbeit" anzahl={3} />);
    expect(screen.getByText(/3× /)).toBeTruthy();
  });

  it("fällt bei unbekanntem Status auf eine neutrale Pille zurück", () => {
    render(<VorgangStatusPille status="unbekannt" />);
    expect(screen.getByText(/unbekannt/i).className).toContain("bg-fill");
  });
});
