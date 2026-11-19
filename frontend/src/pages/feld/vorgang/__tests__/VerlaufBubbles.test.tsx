// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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

describe("TelefonatBubble", () => {
  const payload = {
    richtung: "ausgehend",
    ergebnis: "erreicht",
    beginn: "2026-11-18T15:18:00Z",
    dauer_sekunden: 360,
    partner_name: "Marian Reichel",
    partner_nummer: "030 9928 4417",
    rueckruf_am: "2026-11-21T08:00:00Z",
    rueckruf_erledigt_am: null,
    zeit_gebucht: true,
  };
  const telefonat = (p: Record<string, unknown> = {}, teil: Partial<VorgangEvent> = {}) =>
    event({ event_type: "telefonat", body: "Absage Termin 20.11.", payload: { ...payload, ...p }, ...teil });

  it("zeigt Partner, Nummer, Richtung, Dauer, Ergebnis, Notiz und Zeit gebucht", () => {
    render(<EventBubble event={telefonat()} onHighlight={vi.fn()} autorName="Dennis Hofmann" />);
    expect(screen.getByText("Marian Reichel")).toBeTruthy();
    expect(screen.getByText(/030 9928 4417/)).toBeTruthy();
    expect(screen.getByLabelText("Ausgehend")).toBeTruthy();
    expect(screen.getByText("6 Min")).toBeTruthy();
    expect(screen.getByText("Erreicht")).toBeTruthy();
    expect(screen.getByText("Zeit gebucht")).toBeTruthy();
    expect(screen.getByText("Absage Termin 20.11.")).toBeTruthy();
    expect(screen.getByText(/erfasst von Dennis Hofmann/)).toBeTruthy();
  });

  it("zeigt bei eingehend das Eingehend-Symbol und lässt Zeit gebucht weg, wenn nicht gebucht", () => {
    render(<EventBubble event={telefonat({ richtung: "eingehend", zeit_gebucht: false })} onHighlight={vi.fn()} />);
    expect(screen.getByLabelText("Eingehend")).toBeTruthy();
    expect(screen.queryByText("Zeit gebucht")).toBeNull();
  });

  it("zeigt nicht erreicht/Mailbox ohne Dauer", () => {
    render(<EventBubble event={telefonat({ ergebnis: "mailbox", dauer_sekunden: null })} onHighlight={vi.fn()} />);
    expect(screen.getByText("Mailbox")).toBeTruthy();
    expect(screen.queryByText(/Min$/)).toBeNull();
  });

  it("zeigt den offenen Rückruf als Pille und den erledigten als erledigt", () => {
    const { unmount } = render(<EventBubble event={telefonat()} onHighlight={vi.fn()} />);
    expect(screen.getByText(/^Rückruf 21\.11\./)).toBeTruthy();
    unmount();
    render(
      <EventBubble event={telefonat({ rueckruf_erledigt_am: "2026-11-19T08:00:00Z" })} onHighlight={vi.fn()} />,
    );
    expect(screen.getByText("Rückruf erledigt")).toBeTruthy();
  });

  it("ist nur klickbar, wenn Bearbeiten erlaubt ist", () => {
    const { unmount } = render(<EventBubble event={telefonat()} onHighlight={vi.fn()} />);
    expect(screen.queryByRole("button")).toBeNull();
    unmount();
    const onBearbeiten = vi.fn();
    render(<EventBubble event={telefonat()} onHighlight={vi.fn()} onTelefonatBearbeiten={onBearbeiten} />);
    fireEvent.click(screen.getByRole("button", { name: /Telefonat mit Marian Reichel bearbeiten/ }));
    expect(onBearbeiten).toHaveBeenCalledTimes(1);
  });

  it("zeigt via Claude bei KI-Telefonaten", () => {
    render(<EventBubble event={telefonat({ via: "claude" })} onHighlight={vi.fn()} />);
    expect(screen.getByText("via Claude")).toBeTruthy();
  });
});
