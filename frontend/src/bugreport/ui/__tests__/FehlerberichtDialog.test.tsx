// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FehlerberichtDialog } from "../FehlerberichtDialog";

vi.mock("../screenshot", () => ({
  IGNORIEREN_ATTRIBUT: "data-fehlerbericht-ignorieren",
  nimmScreenshot: vi.fn(),
  kannBildschirmFreigeben: () => false,
  nimmBildschirmfreigabe: vi.fn(),
}));

function Rahmen({ offen, titel, children }: { offen: boolean; titel: string; children: ReactNode }) {
  return offen ? <div role="dialog" aria-label={titel}>{children}</div> : null;
}

const kontext = {
  konsole: [],
  umgebung: { route: "/x" } as never,
};

function rendere(art?: "idee", apiUpload = vi.fn().mockResolvedValue({ id: 7 })) {
  render(
    <FehlerberichtDialog
      start={{ kontext, original: null, aufnahmeFehlgeschlagen: false, art }}
      onClose={vi.fn()}
      Rahmen={Rahmen}
      apiUpload={apiUpload}
    />,
  );
  return apiUpload;
}

afterEach(cleanup);

describe("FehlerberichtDialog Art-Umschalter", () => {
  it("startet als Fehler und wechselt per Umschalter zur Idee", () => {
    rendere();
    expect(screen.getByRole("dialog", { name: "Fehler melden" })).toBeTruthy();
    expect(screen.getByText("Beschreibung")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Idee" }));
    expect(screen.getByRole("dialog", { name: "Idee einreichen" })).toBeTruthy();
    expect(screen.getByText("Was soll sich ändern?")).toBeTruthy();
    expect(screen.getByText("Warum / Nutzen")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Blockierend" })).toBeNull();
    expect(screen.queryByText(/Schritte zur Reproduktion/)).toBeNull();
  });

  it("wählt bei Ideen nur die Umgebung vor und sendet art=idee", async () => {
    const api = rendere("idee");
    expect((screen.getByRole("checkbox", { name: /^Umgebung/ }) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole("checkbox", { name: /^Konsole/ }) as HTMLInputElement).checked).toBe(false);
    fireEvent.change(screen.getByLabelText("Titel"), { target: { value: "Neu" } });
    fireEvent.change(screen.getByLabelText("Was soll sich ändern?"), { target: { value: "Mehr" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Idee senden" })[0]);
    await waitFor(() => expect(api).toHaveBeenCalled());
    const payload = JSON.parse((api.mock.calls[0][0] as FormData).get("payload") as string);
    expect(payload.art).toBe("idee");
    expect(Object.keys(payload.kontext)).toEqual(["umgebung"]);
    await waitFor(() => expect(screen.getByText("Danke! Deine Idee #7 wurde eingereicht.")).toBeTruthy());
  });
});
