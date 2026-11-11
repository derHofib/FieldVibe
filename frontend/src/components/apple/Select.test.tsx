// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Select } from "./Select";

afterEach(cleanup);

describe("Select", () => {
  it("rendert Optionen und gibt value/onChange weiter", () => {
    const onChange = vi.fn();
    render(
      <Select aria-label="Status" value="b" onChange={onChange}>
        <option value="a">A</option>
        <option value="b">B</option>
      </Select>,
    );
    const sel = screen.getByLabelText("Status") as HTMLSelectElement;
    expect(sel.value).toBe("b");
    fireEvent.change(sel, { target: { value: "a" } });
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("versteckt den Chevron vor Screenreadern und reicht ref/disabled durch", () => {
    const ref = createRef<HTMLSelectElement>();
    const { container } = render(
      <Select ref={ref} aria-label="X" disabled className="w-20" groesse="kompakt">
        <option>1</option>
      </Select>,
    );
    expect(container.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
    expect(ref.current?.disabled).toBe(true);
    expect(ref.current?.className).toContain("select-ap-kompakt");
    expect(container.firstElementChild?.className).toContain("w-20");
  });
});
