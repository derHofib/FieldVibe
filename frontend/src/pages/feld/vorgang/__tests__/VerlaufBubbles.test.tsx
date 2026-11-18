// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { VorgangEvent } from "../../../../types";
import { EventBubble, istKiEvent } from "../VerlaufBubbles";

afterEach(cleanup);

function event(teil: Partial<VorgangEvent>): VorgangEvent {
  return {
    id: 1,
    vorgang_id: "v1",
    event_type: "kommentar",
    author_user_id: "u1",
    is_system: false,
    kundensichtbar: false,
    body: "Notiz",
    payload: {},
    ref_entity_type: null,
    ref_entity_id: null,
    client_uuid: null,
    created_at: "2026-11-18T10:00:00Z",
    foto_url: null,
    foto_thumbnail_url: null,
    unterschrift_url: null,
    dokument_url: null,
    dokument_dateiname: null,
    ...teil,
  };
}

describe("via Claude", () => {
  it("zeigt das Label bei KI-Kommentaren", () => {
    render(<EventBubble event={event({ payload: { via: "claude" } })} onHighlight={vi.fn()} />);
    expect(screen.getByText("via Claude")).toBeTruthy();
  });

  it("zeigt es bei System-Eintraegen (Vorgang angelegt)", () => {
    render(<EventBubble event={event({ is_system: true, body: "Vorgang angelegt", payload: { via: "claude" } })} onHighlight={vi.fn()} />);
    expect(screen.getByText("via Claude")).toBeTruthy();
  });

  it("zeigt es nicht bei normalen Eintraegen", () => {
    render(<EventBubble event={event({})} onHighlight={vi.fn()} />);
    expect(screen.queryByText("via Claude")).toBeNull();
    expect(istKiEvent(event({ payload: { via: "anderes" } }))).toBe(false);
  });
});
