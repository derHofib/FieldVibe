import { describe, expect, it } from "vitest";

import type { CurrentUser, Role } from "../types";
import { istAdminOderCustom, istAdminRolle } from "./rollen";

const nutzer = (role: Role) => ({ role }) as CurrentUser;

describe("istAdminRolle", () => {
  it.each(["super_admin", "mandant_admin", "loesch_operativ"] as Role[])("%s ist Admin", (rolle) => {
    expect(istAdminRolle(nutzer(rolle))).toBe(true);
  });
  it.each(["custom", "loesch_ansicht"] as Role[])("%s ist kein Admin", (rolle) => {
    expect(istAdminRolle(nutzer(rolle))).toBe(false);
  });
  it("ohne Nutzer false", () => {
    expect(istAdminRolle(undefined)).toBe(false);
  });
});

describe("istAdminOderCustom", () => {
  it("custom und Admin-Rollen ja", () => {
    expect(istAdminOderCustom(nutzer("custom"))).toBe(true);
    expect(istAdminOderCustom(nutzer("mandant_admin"))).toBe(true);
    expect(istAdminOderCustom(nutzer("loesch_operativ"))).toBe(true);
  });
  it("loesch_ansicht und kein Nutzer nein", () => {
    expect(istAdminOderCustom(nutzer("loesch_ansicht"))).toBe(false);
    expect(istAdminOderCustom(undefined)).toBe(false);
  });
});
