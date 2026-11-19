import { describe, expect, it } from "vitest";

import { ordnerRolle } from "./ordnerRolle";

describe("ordnerRolle", () => {
  it.each([
    ["INBOX", "posteingang"],
    ["INBOX.Sent", "gesendet"],
    ["Gesendete Elemente", "gesendet"],
    ["Sent Items", "gesendet"],
    ["INBOX/Drafts", "entwuerfe"],
    ["Entwürfe", "entwuerfe"],
    ["Archiv", "archiv"],
    ["INBOX.Archive", "archiv"],
    ["Junk-E-Mail", "spam"],
    ["INBOX.Spam", "spam"],
    ["Papierkorb", "papierkorb"],
    ["INBOX.Deleted Items", "papierkorb"],
    ["Gelöschte Objekte", "papierkorb"],
  ])("%s -> %s", (name, rolle) => {
    expect(ordnerRolle(name)).toBe(rolle);
  });

  it("eigene Ordner haben keine Rolle", () => {
    expect(ordnerRolle("INBOX.Kunden")).toBeNull();
    expect(ordnerRolle("Projekte/Sent-Archiv-2020")).toBeNull();
  });
});
