// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useDebouncedValue } from "../useDebouncedValue";

describe("useDebouncedValue", () => {
  afterEach(() => vi.useRealTimers());

  it("übernimmt den Wert erst nach der Verzögerung", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ w }) => useDebouncedValue(w, 300), { initialProps: { w: "a" } });
    rerender({ w: "ab" });
    expect(result.current).toBe("a");
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(result.current).toBe("ab");
  });
});
