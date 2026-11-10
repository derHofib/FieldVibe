// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { NichtGefunden } from "./NichtGefunden";

afterEach(cleanup);

describe("NichtGefunden", () => {
  it("zeigt 404 und fuehrt zur Startseite", () => {
    render(
      <MemoryRouter initialEntries={["/gibtsnicht"]}>
        <Routes>
          <Route path="/feed" element={<p>Feed-Seite</p>} />
          <Route path="*" element={<NichtGefunden startRoute="/feed" />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Seite nicht gefunden" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("Zur Startseite"));
    expect(screen.getByText("Feed-Seite")).toBeInTheDocument();
  });
});
