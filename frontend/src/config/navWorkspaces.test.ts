import { describe, expect, it } from "vitest";

import { NAV_SEITEN, seiteInWorkspace, verfuegbareWorkspaces, WORKSPACES, workspaceStartRoute } from "./navSeiten";

const alle = NAV_SEITEN.filter((s) => !s.nurFeld);

describe("Workspaces", () => {
  it("jede Seite liegt in mindestens einem Workspace", () => {
    for (const seite of alle) {
      expect(WORKSPACES.some((w) => seiteInWorkspace(seite, w)), seite.key).toBe(true);
    }
  });

  it("Operativ startet im Dispo, Sales bei Anfragen", () => {
    const op = WORKSPACES.find((w) => w.key === "operativ")!;
    const sales = WORKSPACES.find((w) => w.key === "sales")!;
    expect(workspaceStartRoute(op, alle)).toBe("/dispo");
    expect(workspaceStartRoute(sales, alle)).toBe("/anfragen");
  });

  it("blendet Workspaces ohne eigene sichtbare Seite aus", () => {
    const nurKunden = alle.filter((s) => ["kunden", "feed"].includes(s.key));
    expect(verfuegbareWorkspaces(nurKunden).map((w) => w.key)).toEqual(["sales"]);
  });
});
