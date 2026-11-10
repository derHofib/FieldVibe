// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { beendeFehlerbericht, initFehlerbericht } from "../../index";

vi.mock("../screenshot", () => ({
  IGNORIEREN_ATTRIBUT: "data-fehlerbericht-ignorieren",
  nimmScreenshot: vi.fn(),
  kannBildschirmFreigeben: () => false,
  nimmBildschirmfreigabe: vi.fn(),
}));

import { FehlerberichtProvider, istKuerzel, useFehlerbericht } from "../FehlerberichtWidget";
import { nimmScreenshot } from "../screenshot";

function Rahmen({ offen, titel, children }: { offen: boolean; titel: string; children: ReactNode }) {
  return offen ? <div role="dialog" aria-label={titel}>{children}</div> : null;
}

function MenueEintrag() {
  const f = useFehlerbericht();
  return f.verfuegbar ? <button onClick={() => f.aufnahmemodusStarten()}>Fehler melden</button> : null;
}

function rendere(darfMelden: boolean, zurueck = vi.fn()) {
  render(
    <FehlerberichtProvider darfMelden={darfMelden} apiUpload={vi.fn()} Rahmen={Rahmen} zurueck={zurueck}>
      <MenueEintrag />
    </FehlerberichtProvider>,
  );
  return zurueck;
}

const kuerzel = { key: "B", ctrlKey: true, shiftKey: true };

beforeEach(() => {
  initFehlerbericht({ appVersion: "1", commitSha: "x", getSitzung: () => null });
  vi.mocked(nimmScreenshot).mockReset();
  vi.mocked(nimmScreenshot).mockRejectedValue(new Error("kein Bild"));
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => setTimeout(() => cb(0), 0));
});

afterEach(() => {
  cleanup();
  beendeFehlerbericht();
  vi.unstubAllGlobals();
});

describe("istKuerzel", () => {
  it("erkennt Strg und Cmd, aber nicht ohne Umschalt", () => {
    expect(istKuerzel({ key: "b", ctrlKey: true, metaKey: false, shiftKey: true, altKey: false })).toBe(true);
    expect(istKuerzel({ key: "b", ctrlKey: false, metaKey: true, shiftKey: true, altKey: false })).toBe(true);
    expect(istKuerzel({ key: "b", ctrlKey: true, metaKey: false, shiftKey: false, altKey: false })).toBe(false);
  });
});

describe("Tastenkürzel", () => {
  it("öffnet mit Recht Screenshot-Aufnahme und Dialog", async () => {
    rendere(true);
    fireEvent.keyDown(window, kuerzel);
    await waitFor(() => expect(screen.getByRole("dialog", { name: "Fehler melden" })).toBeTruthy());
    expect(nimmScreenshot).toHaveBeenCalledTimes(1);
  });

  it("macht ohne Recht nichts und zeigt keinen Menüeintrag", async () => {
    rendere(false);
    fireEvent.keyDown(window, kuerzel);
    await new Promise((r) => setTimeout(r, 30));
    expect(nimmScreenshot).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByText("Fehler melden")).toBeNull();
  });
});

describe("Aufnahmemodus", () => {
  it("navigiert zurück, zeigt die Kapsel und nimmt erst auf Tippen auf", async () => {
    const zurueck = rendere(true);
    fireEvent.click(screen.getByText("Fehler melden"));
    expect(zurueck).toHaveBeenCalledTimes(1);
    expect(nimmScreenshot).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText(/Zum Fehler wechseln/));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeTruthy());
    expect(nimmScreenshot).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("region", { name: /Aufnahmemodus/ })).toBeNull();
  });

  it("Abbrechen beendet den Modus ohne Aufnahme", () => {
    rendere(true);
    fireEvent.click(screen.getByText("Fehler melden"));
    fireEvent.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByRole("region", { name: /Aufnahmemodus/ })).toBeNull();
    expect(nimmScreenshot).not.toHaveBeenCalled();
  });
});
