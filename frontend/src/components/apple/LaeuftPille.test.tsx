// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LaeuftPille } from "./LaeuftPille";

afterEach(cleanup);

describe("LaeuftPille", () => {
  it("zeigt den Text Läuft und einen dekorativen Punkt", () => {
    render(<LaeuftPille />);
    expect(screen.getByText("Läuft")).toBeTruthy();
    expect(screen.getByTestId("laeuft-punkt").getAttribute("aria-hidden")).toBe("true");
  });

  it("pulsiert nur bei erlaubter Bewegung", () => {
    render(<LaeuftPille />);
    expect(screen.getByTestId("laeuft-punkt").className).toContain("motion-safe:animate-livepulse");
  });

  it("nimmt ein eigenes Label", () => {
    render(<LaeuftPille label="Läuft seit 08:00" />);
    expect(screen.getByText("Läuft seit 08:00")).toBeTruthy();
  });
});
