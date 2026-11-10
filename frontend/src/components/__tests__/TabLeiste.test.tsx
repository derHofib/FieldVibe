// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TabLeiste } from "../TabLeiste";

afterEach(cleanup);

const TABS = [
  { key: "a", label: "Eins" },
  { key: "b", label: "Zwei", anzahl: 3 },
];

describe("TabLeiste", () => {
  it("markiert den aktiven Tab und zeigt Zähler", () => {
    render(<TabLeiste tabs={TABS} aktiv="a" onChange={vi.fn()} label="Test" />);
    expect(screen.getByRole("tab", { name: "Eins" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tab", { name: /Zwei/ }).textContent).toContain("3");
  });

  it("wechselt per Klick und Pfeiltaste", () => {
    const onChange = vi.fn();
    render(<TabLeiste tabs={TABS} aktiv="a" onChange={onChange} label="Test" />);
    fireEvent.click(screen.getByRole("tab", { name: /Zwei/ }));
    expect(onChange).toHaveBeenLastCalledWith("b");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Eins" }), { key: "ArrowRight" });
    expect(onChange).toHaveBeenLastCalledWith("b");
  });
});
